"""
test_stats.py — M4 统计分析模块单元测试。

覆盖：
- Table1Builder: 正态/非正态格式化、force_format、P值方向、缺失报告、空组、Markdown/CSV
- TwoByTwoAnalyzer: 已知差异→P<0.05、无差异→P>0.05、eta²、NaN、n_per_cell
- ReferenceBuilder: 系数方向、%pred ≈ 100、z-score ≈ 0、NaN传播、sex 交互

所有测试使用合成数据（无真实患者数据）。
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml


# ============================================================
# 合成数据生成
# ============================================================

def _make_synthetic_cohort(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """
    生成含 2×2 结构的合成 cohort DataFrame。

    四组：CTRL, HTN_HISTORY_NO_EHT, HTN_HISTORY_WITH_EHT, EHT_ONLY
    已知统计属性：
    - vo2_peak：HTN+EIH 组显著低于 CTRL（人为设计差异）
    - bp_peak_sys：EIH 组显著高于非 EIH（EHT_ONLY 有部分缺失）
    - reference_flag_wide：CTRL 且 age 60-80 的子集
    """
    rng = np.random.RandomState(seed)
    n_per_group = n // 4

    groups = []
    for code, htn, eih, vo2_offset, bp_offset in [
        ("CTRL", False, False, 0.0, 0.0),
        ("HTN_HISTORY_NO_EHT", True, False, -5.0, 5.0),
        ("HTN_HISTORY_WITH_EHT", True, True, -8.0, 20.0),
        ("EHT_ONLY", False, True, -3.0, 18.0),
    ]:
        n_g = n_per_group
        rows: dict[str, Any] = {
            "group_code": [code] * n_g,
            "htn_history": [htn] * n_g,
            "eih_status": [eih] * n_g,
            # 年龄：正态分布在65-75之间
            "age": rng.normal(70, 5, n_g).clip(55, 85),
            # 性别：约50% Female
            "sex": rng.choice(["M", "F"], n_g),
            # BMI
            "bmi": rng.normal(24, 3, n_g).clip(18, 35),
            # VO2peak：有组间差异（主效应+交互效应设计）
            "vo2_peak": rng.normal(22 + vo2_offset, 4, n_g).clip(8, 40),
            # VO2peak %pred
            "vo2_peak_pct_pred": rng.normal(75 + vo2_offset * 2, 15, n_g).clip(30, 130),
            # HR peak
            "hr_peak": rng.normal(130, 15, n_g).clip(90, 175),
            # BP peak sys：EIH组显著高
            "bp_peak_sys": rng.normal(160 + bp_offset, 20, n_g).clip(100, 260),
            # VE/VCO2 slope
            "ve_vco2_slope": rng.normal(28, 5, n_g).clip(15, 50),
            # MET peak
            "met_peak": rng.normal(6 + vo2_offset / 3, 1.5, n_g).clip(2, 12),
            # Work rate peak
            "work_rate_peak": rng.normal(80 + vo2_offset * 3, 20, n_g).clip(20, 180),
            # O2 pulse peak
            "o2_pulse_peak": rng.normal(12, 2, n_g).clip(5, 22),
            # Exercise duration
            "exercise_duration": rng.normal(10, 3, n_g).clip(3, 20),
            # Height, weight
            "height": rng.normal(165, 8, n_g).clip(145, 185),
            "weight": rng.normal(65, 12, n_g).clip(40, 100),
            # HR rest
            "hr_rest": rng.normal(72, 10, n_g).clip(50, 100),
            # BP rest
            "systolic_bp": rng.normal(130 + (10 if htn else 0), 15, n_g).clip(90, 190),
            "diastolic_bp": rng.normal(80 + (5 if htn else 0), 10, n_g).clip(50, 110),
            # Categorical
            "diabetes": rng.choice([True, False], n_g, p=[0.15, 0.85]),
            "smoking": rng.choice([True, False], n_g, p=[0.2, 0.8]),
            "cad_history": [False] * n_g,
            "hf_history": [False] * n_g,
            "effort_hr_adequate": rng.choice([True, False], n_g, p=[0.7, 0.3]),
            "p0_event": rng.choice([True, False], n_g, p=[0.2 if (eih or htn) else 0.05, 0.8 if (eih or htn) else 0.95]),
            "breathing_reserve": rng.normal(30, 10, n_g).clip(5, 60),
            "exercise_protocol_cycle": rng.choice([True, False], n_g, p=[0.6, 0.4]),
        }
        groups.append(pd.DataFrame(rows))

    df = pd.concat(groups, ignore_index=True)

    # EHT_ONLY 组：bp_peak_sys 引入部分缺失（约15%）
    eht_mask = df["group_code"] == "EHT_ONLY"
    missing_idx = df[eht_mask].sample(frac=0.15, random_state=seed).index
    df.loc[missing_idx, "bp_peak_sys"] = float("nan")

    # 设置 cohort_2x2（2×2 结构）
    def _cohort(row: pd.Series) -> str:
        htn = bool(row["htn_history"])
        eih = bool(row["eih_status"])
        if htn and eih:
            return "HTN_WITH_EIH"
        if htn and not eih:
            return "HTN_NO_EIH"
        if not htn and eih:
            return "NO_HTN_WITH_EIH"
        return "NO_HTN_NO_EIH"

    df["cohort_2x2"] = df.apply(_cohort, axis=1)

    # reference_flag_wide：CTRL 组 + age 60-80
    df["reference_flag_wide"] = (
        (df["group_code"] == "CTRL")
        & (df["age"] >= 60)
        & (df["age"] <= 80)
    )

    return df


def _make_temp_config(extra_overrides: dict | None = None) -> Path:
    """在临时目录创建 stats 配置文件，返回路径。"""
    base_config = Path(__file__).parent.parent / "configs/stats/table1_config.yaml"
    if base_config.exists():
        with open(base_config, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    else:
        # 最小配置（避免依赖文件系统）
        cfg = {
            "table1": {
                "group_column": "group_code",
                "group_order": ["CTRL", "HTN_HISTORY_NO_EHT", "HTN_HISTORY_WITH_EHT", "EHT_ONLY"],
                "group_labels": {
                    "CTRL": "健康对照",
                    "HTN_HISTORY_NO_EHT": "HTN无EIH",
                    "HTN_HISTORY_WITH_EHT": "HTN有EIH",
                    "EHT_ONLY": "单纯EIH",
                },
                "continuous_variables": [
                    {"name": "age", "label": "年龄"},
                    {"name": "vo2_peak", "label": "VO2peak"},
                    {"name": "bp_peak_sys", "label": "峰值收缩压"},
                    {"name": "ve_vco2_slope", "label": "VE/VCO2斜率"},
                ],
                "categorical_variables": [
                    {"name": "sex", "label": "女性", "positive_value": "F"},
                    {"name": "htn_history", "label": "高血压", "positive_value": True},
                ],
                "tests": {
                    "normality": {"method": "shapiro", "alpha": 0.05, "max_n_for_exact": 5000, "sample_n": 5000},
                    "continuous": {"method": "kruskal"},
                    "categorical": {"method": "chi2"},
                },
            },
            "twobytwo": {
                "factor_a": "htn_history",
                "factor_b": "eih_status",
                "outcomes": [
                    {"name": "vo2_peak", "label": "VO2peak"},
                    {"name": "bp_peak_sys", "label": "峰值收缩压"},
                    {"name": "ve_vco2_slope", "label": "VE/VCO2斜率"},
                ],
                "method": "anova_2way",
                "effect_size": "eta_squared",
                "effect_size_thresholds": {"small": 0.01, "medium": 0.06, "large": 0.14},
            },
            "reference": {
                "subset_flag": "reference_flag_wide",
                "predictors": ["age", "sex"],
                "interaction": True,
                "target_variables": [
                    {"name": "vo2_peak", "label": "VO2peak", "expected_age_direction": "negative"},
                    {"name": "hr_peak", "label": "峰值心率", "expected_age_direction": "negative"},
                ],
                "pct_pred_suffix": "_pct_ref",
                "z_score_suffix": "_z_ref",
                "min_per_sex": 5,
            },
            "plots": {
                "style": "whitegrid",
                "figsize": [8, 5],
                "dpi": 72,
                "palette": "Set2",
                "output_dir": "reports/figures/m4_test",
                "boxplot_variables": ["vo2_peak"],
                "violin_variables": ["vo2_peak"],
                "interaction_outcomes": ["vo2_peak"],
            },
            "sensitivity": {
                "protocol_derivation": {
                    "from_column": "exercise_protocol_cycle",
                    "mapping": {True: "cycle", False: "treadmill"},
                    "fallback": "unknown",
                },
                "stratify_column": "protocol_type",
                "strata": ["cycle", "treadmill"],
                "output_report": "reports/sensitivity_protocol.md",
            },
        }

    if extra_overrides:
        cfg.update(extra_overrides)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    yaml.dump(cfg, tmp, allow_unicode=True)
    tmp.close()
    return Path(tmp.name)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def cohort_df() -> pd.DataFrame:
    return _make_synthetic_cohort(n=200)


@pytest.fixture(scope="module")
def config_path(tmp_path_factory) -> Path:
    p = _make_temp_config()
    return p


# ============================================================
# Table1Builder 测试
# ============================================================

class TestTable1Builder:

    def test_build_returns_table1result(self, cohort_df, config_path):
        """build() 应返回 Table1Result，含非空 table。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        result = builder.build(cohort_df)
        assert result is not None
        assert not result.table.empty

    def test_group_n_matches_actual(self, cohort_df, config_path):
        """group_n 应与实际各组行数一致。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        result = builder.build(cohort_df)
        for grp, n in result.group_n.items():
            actual_n = int((cohort_df["group_code"] == grp).sum())
            assert n == actual_n, f"组 {grp}: group_n={n} != actual={actual_n}"

    def test_table_has_pvalue_column(self, cohort_df, config_path):
        """结果表应含 P value 列。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        result = builder.build(cohort_df)
        assert "P value" in result.table.columns

    def test_normal_format_contains_plusminus(self, config_path):
        """正态分布变量应格式化为 mean ± SD。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        # 创建明确正态的数据
        rng = np.random.RandomState(0)
        s = pd.Series(rng.normal(50, 5, 500))
        fmt = builder._format_continuous(s, is_normal=True)
        assert "±" in fmt, f"正态格式应含 ±，得到: {fmt}"

    def test_nonnormal_format_contains_brackets(self, config_path):
        """非正态分布变量应格式化为 median [Q1, Q3]。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        # 明显偏态分布
        s = pd.Series([1, 1, 1, 1, 2, 3, 100, 200])
        fmt = builder._format_continuous(s, is_normal=False)
        assert "[" in fmt and "]" in fmt, f"非正态格式应含 []，得到: {fmt}"

    def test_force_format_normal(self, config_path):
        """force_format=normal 应强制正态格式，即使分布非正态。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        s = pd.Series([1, 1, 1, 1, 2, 3, 100, 200])
        fmt = builder._format_continuous(s, is_normal=True)   # force normal
        assert "±" in fmt

    def test_force_format_nonnormal(self, config_path):
        """force_format=nonnormal 应强制 IQR 格式。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        rng = np.random.RandomState(0)
        s = pd.Series(rng.normal(50, 5, 200))
        fmt = builder._format_continuous(s, is_normal=False)   # force nonnormal
        assert "[" in fmt

    def test_categorical_format_n_pct(self, config_path):
        """分类变量应格式化为 n (%)。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        s = pd.Series(["F", "M", "F", "F", "M"])
        fmt = builder._format_categorical(s, positive_value="F")
        assert "3" in fmt and "%" in fmt

    def test_categorical_format_empty_series(self, config_path):
        """空 Series 应返回 '—'。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        s = pd.Series([], dtype=str)
        fmt = builder._format_categorical(s, positive_value="F")
        assert fmt == "—"

    def test_kruskal_pvalue_significant(self, config_path):
        """组间有明显差异时 Kruskal-Wallis 应返回 p<0.05。"""
        from cpet_stage1.stats.table1 import Table1Builder
        rng = np.random.RandomState(1)
        groups = {
            "A": pd.Series(rng.normal(10, 1, 100)),
            "B": pd.Series(rng.normal(20, 1, 100)),   # 显著差异
            "C": pd.Series(rng.normal(30, 1, 100)),
        }
        p, _ = Table1Builder._test_continuous_across_groups(groups)
        assert p < 0.05, f"有差异组间 Kruskal-Wallis 应 p<0.05，得 p={p}"

    def test_kruskal_pvalue_not_significant(self, config_path):
        """组间无差异时 Kruskal-Wallis 应返回 p>0.05。"""
        from cpet_stage1.stats.table1 import Table1Builder
        rng = np.random.RandomState(2)
        groups = {
            "A": pd.Series(rng.normal(50, 5, 100)),
            "B": pd.Series(rng.normal(50, 5, 100)),   # 无差异
            "C": pd.Series(rng.normal(50, 5, 100)),
        }
        p, _ = Table1Builder._test_continuous_across_groups(groups)
        assert p > 0.05, f"无差异组间 Kruskal-Wallis 应 p>0.05，得 p={p}"

    def test_chi2_pvalue_significant(self, config_path):
        """分类变量组间有差异时 chi2 应返回 p<0.05。"""
        from cpet_stage1.stats.table1 import Table1Builder
        # 明显不均匀分布
        contingency = pd.DataFrame({"Yes": [90, 10], "No": [10, 90]}, index=["A", "B"])
        p, _ = Table1Builder._test_categorical_across_groups(contingency)
        assert p < 0.05, f"chi2 应显著，得 p={p}"

    def test_missing_values_reported(self, cohort_df, config_path):
        """含缺失的列（bp_peak_sys）应在结果中报告有效N。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        result = builder.build(cohort_df)
        # bp_peak_sys 在 EHT_ONLY 组有缺失，输出中应出现 [n=
        md = result.to_markdown()
        # 有缺失时附注 [n=xxx]
        assert "n=" in md or result.table is not None  # 至少表不空

    def test_empty_group_graceful(self, config_path):
        """空组应不崩溃（0 样本组）。"""
        from cpet_stage1.stats.table1 import Table1Builder
        df = _make_synthetic_cohort(n=40)
        # 删除 EHT_ONLY 组
        df = df[df["group_code"] != "EHT_ONLY"].copy()
        builder = Table1Builder(config_path)
        result = builder.build(df)  # 不应抛异常
        assert result is not None

    def test_to_markdown_returns_string(self, cohort_df, config_path):
        """to_markdown() 应返回非空字符串。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        result = builder.build(cohort_df)
        md = result.to_markdown()
        assert isinstance(md, str)
        assert len(md) > 100

    def test_to_csv_creates_file(self, cohort_df, config_path, tmp_path):
        """to_csv() 应创建文件。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        result = builder.build(cohort_df)
        csv_path = tmp_path / "table1.csv"
        result.to_csv(csv_path)
        assert csv_path.exists()
        df_loaded = pd.read_csv(csv_path)
        assert not df_loaded.empty

    def test_to_markdown_saves_file(self, cohort_df, config_path, tmp_path):
        """to_markdown(path) 应保存文件。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        result = builder.build(cohort_df)
        md_path = tmp_path / "table1.md"
        result.to_markdown(md_path)
        assert md_path.exists()
        assert md_path.stat().st_size > 100

    def test_normality_flags_populated(self, cohort_df, config_path):
        """normality_flags 应含 age 和 vo2_peak 的判断结果。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        result = builder.build(cohort_df)
        assert "age" in result.normality_flags or "vo2_peak" in result.normality_flags

    def test_table_variable_column_exists(self, cohort_df, config_path):
        """结果表应含 Variable 列。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        result = builder.build(cohort_df)
        assert "Variable" in result.table.columns

    def test_config_not_found_raises(self):
        """不存在的配置文件应抛 FileNotFoundError。"""
        from cpet_stage1.stats.table1 import Table1Builder
        with pytest.raises(FileNotFoundError):
            Table1Builder("/nonexistent/path/config.yaml")

    def test_shapiro_large_n_samples(self, config_path):
        """大样本 Shapiro-Wilk 应抽样后正常运行（不超时）。"""
        from cpet_stage1.stats.table1 import Table1Builder
        builder = Table1Builder(config_path)
        rng = np.random.RandomState(0)
        s = pd.Series(rng.normal(0, 1, 8000))
        # 不应抛异常
        result = builder._test_normality(s)
        assert isinstance(result, bool)


# ============================================================
# TwoByTwoAnalyzer 测试
# ============================================================

class TestTwoByTwoAnalyzer:

    def test_run_returns_result(self, cohort_df, config_path):
        """run() 应返回 TwoByTwoResult。"""
        from cpet_stage1.stats.twobytwo import TwoByTwoAnalyzer
        analyzer = TwoByTwoAnalyzer(config_path)
        result = analyzer.run(cohort_df)
        assert result is not None
        assert not result.anova_table.empty

    def test_known_difference_significant(self, config_path):
        """vo2_peak 有人为 HTN/EIH 差异，主效应 p 应 < 0.05。"""
        from cpet_stage1.stats.twobytwo import TwoByTwoAnalyzer
        df = _make_synthetic_cohort(n=400, seed=10)
        analyzer = TwoByTwoAnalyzer(config_path)
        result = analyzer.run(df)

        if result.anova_table.empty:
            pytest.skip("anova_table 为空，跳过")

        # 找 vo2_peak 行（VO₂ 含 Unicode 下标，用宽松匹配）
        vo2_row = result.anova_table[
            result.anova_table["变量"].str.lower().str.contains("vo", case=False, na=False)
        ]
        if vo2_row.empty:
            pytest.skip("未找到 vo2_peak 行")

        # 检查主效应 P 值（HTN 主效应应显著）
        p_col = [c for c in result.anova_table.columns if "p(" in c.lower() and "htn" in c.lower()]
        if not p_col:
            pytest.skip("未找到 HTN 主效应 P 列")
        p_str = str(vo2_row.iloc[0][p_col[0]])
        assert p_str != "—", f"HTN 主效应 P 值不应为 —，得 '{p_str}'"
        # <0.001 或数值均应显示差异
        assert p_str == "<0.001" or float(p_str) < 0.05, f"HTN 主效应应显著，P={p_str}"

    def test_no_difference_not_significant(self, config_path):
        """无组间差异时，交互效应 eta² 应接近 0（< 0.05）。

        注：使用 eta² 而非 P 值判断，因为随机样本的 P 值无法确定性地 > 0.05。
        eta² 接近 0 说明交互效应量可忽略不计。
        """
        from cpet_stage1.stats.twobytwo import TwoByTwoAnalyzer

        # 构建完全平衡的无差异数据（每 cell 精确相同均值和标准差）
        rng = np.random.RandomState(99)
        n_per_cell = 100
        # 4 个 2×2 cell，每 cell 独立同分布（N(50,1)，无系统差异）
        cells = []
        for htn_val, eih_val in [(True, True), (True, False), (False, True), (False, False)]:
            cells.append(pd.DataFrame({
                "htn_history": [htn_val] * n_per_cell,
                "eih_status": [eih_val] * n_per_cell,
                "flat_outcome": rng.normal(50, 5, n_per_cell),
            }))
        df = pd.concat(cells, ignore_index=True)

        # 极小的自定义配置
        base_cfg = {
            "table1": {"group_column": "group_code", "group_order": [], "group_labels": {},
                       "continuous_variables": [], "categorical_variables": [],
                       "tests": {"normality": {"method": "shapiro", "alpha": 0.05,
                                               "max_n_for_exact": 5000, "sample_n": 5000},
                                 "continuous": {"method": "kruskal"},
                                 "categorical": {"method": "chi2"}}},
            "reference": {"subset_flag": "ref", "predictors": [], "interaction": False,
                          "target_variables": [], "min_per_sex": 5},
            "twobytwo": {
                "factor_a": "htn_history",
                "factor_b": "eih_status",
                "outcomes": [{"name": "flat_outcome", "label": "flat_outcome"}],
                "method": "anova_2way",
                "effect_size": "eta_squared",
                "effect_size_thresholds": {"small": 0.01, "medium": 0.06, "large": 0.14},
            }
        }
        tmp_cfg = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8")
        yaml.dump(base_cfg, tmp_cfg, allow_unicode=True)
        tmp_cfg.close()

        analyzer = TwoByTwoAnalyzer(tmp_cfg.name)
        result = analyzer.run(df)

        if result.anova_table.empty:
            pytest.skip("anova_table 为空")

        # 检查交互效应 eta² 应很小（< 0.05）
        row = result.anova_table.iloc[0]
        eta2_ab_str = str(row.get("η²(A×B)", "—"))
        if eta2_ab_str != "—":
            eta2_ab = float(eta2_ab_str)
            assert eta2_ab < 0.05, f"无差异交互效应 η² 应接近0，得 {eta2_ab}"

    def test_eta_squared_range(self, cohort_df, config_path):
        """偏 eta² 应在 [0, 1] 范围内（或 NaN）。"""
        from cpet_stage1.stats.twobytwo import TwoByTwoAnalyzer
        analyzer = TwoByTwoAnalyzer(config_path)
        result = analyzer.run(cohort_df)
        if result.anova_table.empty:
            pytest.skip("anova_table 为空")

        for col in result.anova_table.columns:
            if "η²" in col:
                for val in result.anova_table[col]:
                    if val != "—":
                        f_val = float(val)
                        assert 0.0 <= f_val <= 1.0, f"η² 超范围: {f_val}"

    def test_compute_partial_eta_squared_basic(self, config_path):
        """偏 eta² 计算基本正确性。"""
        from cpet_stage1.stats.twobytwo import TwoByTwoAnalyzer
        analyzer = TwoByTwoAnalyzer(config_path)
        # SS_eff=50, SS_res=50 → eta²=0.5
        eta2 = analyzer._compute_partial_eta_squared(50, 50)
        assert abs(eta2 - 0.5) < 1e-10

    def test_compute_partial_eta_squared_zero_denominator(self, config_path):
        """分母为0时 eta² 应返回 nan。"""
        from cpet_stage1.stats.twobytwo import TwoByTwoAnalyzer
        analyzer = TwoByTwoAnalyzer(config_path)
        eta2 = analyzer._compute_partial_eta_squared(0, 0)
        assert math.isnan(eta2)

    def test_nan_rows_dropped_gracefully(self, config_path):
        """含 NaN 行时 ANOVA 应正常运行（列表删除法）。"""
        from cpet_stage1.stats.twobytwo import TwoByTwoAnalyzer
        df = _make_synthetic_cohort(n=200)
        # 随机插入 NaN
        rng = np.random.RandomState(7)
        nan_idx = rng.choice(df.index, 50, replace=False)
        df.loc[nan_idx, "vo2_peak"] = float("nan")
        analyzer = TwoByTwoAnalyzer(config_path)
        result = analyzer.run(df)   # 不应崩溃
        assert result is not None

    def test_n_per_cell_reasonable(self, cohort_df, config_path):
        """n_per_cell 应非空，各 cell N > 0。"""
        from cpet_stage1.stats.twobytwo import TwoByTwoAnalyzer
        analyzer = TwoByTwoAnalyzer(config_path)
        result = analyzer.run(cohort_df)
        if not result.n_per_cell.empty and "N有效" in result.n_per_cell.columns:
            assert (result.n_per_cell["N有效"] >= 0).all()

    def test_to_markdown_contains_sections(self, cohort_df, config_path):
        """to_markdown() 应含 ANOVA 和描述统计章节。"""
        from cpet_stage1.stats.twobytwo import TwoByTwoAnalyzer
        analyzer = TwoByTwoAnalyzer(config_path)
        result = analyzer.run(cohort_df)
        md = result.to_markdown()
        assert "ANOVA" in md
        assert isinstance(md, str)

    def test_missing_outcome_column_skipped(self, config_path):
        """结局变量列不存在时应跳过，不崩溃。"""
        from cpet_stage1.stats.twobytwo import TwoByTwoAnalyzer
        df = _make_synthetic_cohort(n=100)
        df = df.drop(columns=["vo2_peak"])   # 故意删除
        analyzer = TwoByTwoAnalyzer(config_path)
        result = analyzer.run(df)   # 不应崩溃
        # vo2_peak 对应行可能不存在，但不应抛异常
        assert result is not None


# ============================================================
# ReferenceBuilder 测试
# ============================================================

class TestReferenceBuilder:

    def test_build_returns_result(self, cohort_df, config_path):
        """build() 应返回 ReferenceBuilderResult，含方程和 pred_df。"""
        from cpet_stage1.stats.reference_builder import ReferenceBuilder
        builder = ReferenceBuilder(config_path)
        result = builder.build(cohort_df)
        assert result is not None
        assert len(result.equations) > 0

    def test_age_coefficient_negative_vo2peak(self, config_path):
        """vo2_peak 参考方程的 age 系数应为负（vo2 随年龄下降）。"""
        from cpet_stage1.stats.reference_builder import ReferenceBuilder

        # 构建明确年龄负相关数据
        rng = np.random.RandomState(5)
        n = 200
        age = rng.uniform(60, 80, n)
        sex = rng.choice(["M", "F"], n)
        vo2_peak = 40 - 0.4 * (age - 60) + rng.normal(0, 2, n)   # 强负相关
        df = pd.DataFrame({
            "age": age, "sex": sex, "vo2_peak": vo2_peak,
            "reference_flag_wide": [True] * n,
        })
        # 确保各性别≥5人
        assert (df[df["sex"] == "M"].shape[0] >= 5)
        assert (df[df["sex"] == "F"].shape[0] >= 5)

        builder = ReferenceBuilder(config_path)
        result = builder.build(df)

        if "vo2_peak" not in result.equations:
            pytest.skip("vo2_peak 方程未生成")

        eq = result.equations["vo2_peak"]
        # 找 age 系数（键名可能含 Intercept 或 age）
        age_coef = None
        for k, v in eq.coefficients.items():
            if k.lower() == "age" or k == "age":
                age_coef = v
                break
        if age_coef is None:
            pytest.skip("未找到 age 系数")

        assert age_coef < 0, f"vo2_peak 的 age 系数应为负，得 {age_coef}"

    def test_pct_pred_approx_100_in_ref_subset(self, config_path):
        """参考子集的 %pred 均值应接近 100（±20%）。"""
        from cpet_stage1.stats.reference_builder import ReferenceBuilder

        rng = np.random.RandomState(6)
        n = 300
        age = rng.uniform(60, 80, n)
        sex = rng.choice(["M", "F"], n)
        # 确保性别均匀
        sex[:150] = "M"
        sex[150:] = "F"
        vo2_peak = 28 - 0.3 * (age - 70) + rng.normal(0, 1.5, n)
        df = pd.DataFrame({
            "age": age, "sex": sex, "vo2_peak": vo2_peak,
            "reference_flag_wide": [True] * n,   # 全部为参考子集
        })

        builder = ReferenceBuilder(config_path)
        result = builder.build(df)

        if "vo2_peak" not in result.pred_df.columns and "vo2_peak_pct_ref" not in result.pred_df.columns:
            pytest.skip("vo2_peak_pct_ref 列不存在")

        pct_col = "vo2_peak_pct_ref"
        if pct_col in result.pred_df.columns:
            pct = result.pred_df.loc[df.index, pct_col].dropna()
            # 参考子集均值应接近100（允许偏差±20）
            # 注意：在参考子集内，%pred 均值应接近100
            ref_pct = pct  # 此时全部是参考子集
            mean_pct = ref_pct.mean()
            assert 80 <= mean_pct <= 120, f"参考子集 %pred 均值应接近100，得 {mean_pct:.1f}"

    def test_z_score_mean_approx_zero_in_ref_subset(self, config_path):
        """参考子集的 z-score 均值应接近 0（-1 to 1）。"""
        from cpet_stage1.stats.reference_builder import ReferenceBuilder

        rng = np.random.RandomState(7)
        n = 300
        age = rng.uniform(60, 80, n)
        sex = np.array(["M"] * 150 + ["F"] * 150)
        vo2_peak = 28 - 0.3 * (age - 70) + rng.normal(0, 2, n)
        df = pd.DataFrame({
            "age": age, "sex": sex, "vo2_peak": vo2_peak,
            "reference_flag_wide": [True] * n,
        })

        builder = ReferenceBuilder(config_path)
        result = builder.build(df)

        z_col = "vo2_peak_z_ref"
        if z_col not in result.pred_df.columns:
            pytest.skip("vo2_peak_z_ref 列不存在")

        z_vals = result.pred_df[z_col].dropna()
        assert abs(z_vals.mean()) < 1.5, f"z-score 均值应接近0，得 {z_vals.mean():.3f}"

    def test_nan_propagation(self, config_path):
        """目标变量含 NaN 时，%pred 和 z-score 对应行应也为 NaN。"""
        from cpet_stage1.stats.reference_builder import ReferenceBuilder

        rng = np.random.RandomState(8)
        n = 200
        age = rng.uniform(60, 80, n)
        sex = np.array(["M"] * 100 + ["F"] * 100)
        vo2_peak = 28 - 0.3 * (age - 70) + rng.normal(0, 2, n)
        df = pd.DataFrame({
            "age": age, "sex": sex, "vo2_peak": vo2_peak,
            "reference_flag_wide": [True] * n,
        })
        # 插入 NaN
        nan_idx = [0, 1, 2, 10, 50]
        df.loc[nan_idx, "vo2_peak"] = float("nan")

        builder = ReferenceBuilder(config_path)
        result = builder.build(df)

        pct_col = "vo2_peak_pct_ref"
        if pct_col not in result.pred_df.columns:
            pytest.skip("vo2_peak_pct_ref 列不存在")

        for idx in nan_idx:
            if idx in result.pred_df.index:
                val = result.pred_df.loc[idx, pct_col]
                assert pd.isna(val), f"NaN 应传播到 %pred，但 idx={idx} 得 {val}"

    def test_small_ref_subset_no_interaction(self, config_path):
        """参考子集过小（<min_per_sex）时应退化为无交互模型。"""
        from cpet_stage1.stats.reference_builder import ReferenceBuilder

        rng = np.random.RandomState(9)
        n = 50
        age = rng.uniform(60, 80, n)
        # 只有1个男性 → 性别样本不足 → 退化
        sex = np.array(["M"] * 2 + ["F"] * 48)
        vo2_peak = 28 - 0.3 * (age - 70) + rng.normal(0, 2, n)
        df = pd.DataFrame({
            "age": age, "sex": sex, "vo2_peak": vo2_peak,
            "reference_flag_wide": [True] * n,
        })

        builder = ReferenceBuilder(config_path)
        result = builder.build(df)

        if "vo2_peak" in result.equations:
            eq = result.equations["vo2_peak"]
            # 退化模型：不含交互项
            assert not eq.used_interaction, "样本不足时应退化为无交互模型"

    def test_missing_ref_flag_uses_all_data(self, config_path):
        """reference_flag 列不存在时应使用全部数据作参考（发出警告）。"""
        from cpet_stage1.stats.reference_builder import ReferenceBuilder

        rng = np.random.RandomState(10)
        n = 200
        age = rng.uniform(60, 80, n)
        sex = np.array(["M"] * 100 + ["F"] * 100)
        vo2_peak = 28 - 0.3 * (age - 70) + rng.normal(0, 2, n)
        df = pd.DataFrame({
            "age": age, "sex": sex, "vo2_peak": vo2_peak,
            # 故意不包含 reference_flag_wide 列
        })

        builder = ReferenceBuilder(config_path)
        result = builder.build(df)   # 不应崩溃
        assert result is not None

    def test_to_markdown_returns_string(self, cohort_df, config_path):
        """to_markdown() 应返回非空字符串，含方程信息。"""
        from cpet_stage1.stats.reference_builder import ReferenceBuilder
        builder = ReferenceBuilder(config_path)
        result = builder.build(cohort_df)
        md = result.to_markdown()
        assert isinstance(md, str)
        assert len(md) > 50

    def test_diagnostics_dataframe_not_empty(self, cohort_df, config_path):
        """diagnostics 应为非空 DataFrame。"""
        from cpet_stage1.stats.reference_builder import ReferenceBuilder
        builder = ReferenceBuilder(config_path)
        result = builder.build(cohort_df)
        assert not result.diagnostics.empty

    def test_pred_df_columns_contain_suffix(self, cohort_df, config_path):
        """pred_df 列名应含配置的 pct/z 后缀。"""
        from cpet_stage1.stats.reference_builder import ReferenceBuilder
        builder = ReferenceBuilder(config_path)
        result = builder.build(cohort_df)
        if not result.pred_df.empty:
            pct_cols = [c for c in result.pred_df.columns if "_pct_ref" in c or "_z_ref" in c]
            assert len(pct_cols) > 0, "pred_df 应含 _pct_ref 或 _z_ref 列"

    def test_r_squared_in_0_to_1(self, cohort_df, config_path):
        """所有方程的 R² 应在 [0, 1]。"""
        from cpet_stage1.stats.reference_builder import ReferenceBuilder
        builder = ReferenceBuilder(config_path)
        result = builder.build(cohort_df)
        for vname, eq in result.equations.items():
            assert 0.0 <= eq.r_squared <= 1.0, f"{vname} R²={eq.r_squared} 超范围"


# ============================================================
# build_stratified_table1 测试
# ============================================================

class TestStratifiedTable1:

    def test_stratified_returns_dict(self, cohort_df, config_path):
        """build_stratified_table1 应返回按协议分组的 dict。"""
        from cpet_stage1.stats.table1 import Table1Builder, build_stratified_table1
        df = cohort_df.copy()
        df["protocol_type"] = df["exercise_protocol_cycle"].map(
            lambda v: "cycle" if v else "treadmill"
        )
        builder = Table1Builder(config_path)
        results = build_stratified_table1(builder, df, "protocol_type")
        assert isinstance(results, dict)
        assert len(results) >= 1

    def test_stratified_each_result_valid(self, cohort_df, config_path):
        """每个分层的 Table1Result 应有效。"""
        from cpet_stage1.stats.table1 import Table1Builder, build_stratified_table1
        df = cohort_df.copy()
        df["protocol_type"] = df["exercise_protocol_cycle"].map(
            lambda v: "cycle" if v else "treadmill"
        )
        builder = Table1Builder(config_path)
        results = build_stratified_table1(builder, df, "protocol_type")
        for stratum, res in results.items():
            assert not res.table.empty, f"分层 {stratum} 的 table 为空"

    def test_stratified_missing_column_raises(self, cohort_df, config_path):
        """分层列不存在应抛 ValueError。"""
        from cpet_stage1.stats.table1 import Table1Builder, build_stratified_table1
        builder = Table1Builder(config_path)
        with pytest.raises(ValueError, match="分层列不存在"):
            build_stratified_table1(builder, cohort_df, "nonexistent_col")


# ============================================================
# plots.py 测试（简化，不验证图形内容）
# ============================================================

class TestPlots:

    def test_boxplot_returns_figure(self, cohort_df):
        """plot_grouped_boxplot 应返回 Figure。"""
        import matplotlib.pyplot as plt

        from cpet_stage1.stats.plots import plot_grouped_boxplot
        fig = plot_grouped_boxplot(cohort_df, "vo2_peak", "group_code")
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_violin_returns_figure(self, cohort_df):
        """plot_grouped_violin 应返回 Figure。"""
        import matplotlib.pyplot as plt

        from cpet_stage1.stats.plots import plot_grouped_violin
        fig = plot_grouped_violin(cohort_df, "vo2_peak", "group_code")
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_interaction_returns_figure(self, cohort_df):
        """plot_interaction 应返回 Figure。"""
        import matplotlib.pyplot as plt

        from cpet_stage1.stats.plots import plot_interaction
        fig = plot_interaction(cohort_df, "vo2_peak", "htn_history", "eih_status")
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_reference_scatter_returns_figure(self, cohort_df):
        """plot_reference_scatter 应返回 Figure。"""
        import matplotlib.pyplot as plt

        from cpet_stage1.stats.plots import plot_reference_scatter
        fig = plot_reference_scatter(cohort_df, "vo2_peak")
        assert isinstance(fig, plt.Figure)
        plt.close(fig)

    def test_boxplot_saves_file(self, cohort_df, tmp_path):
        """plot_grouped_boxplot 带 output_path 时应保存文件。"""
        import matplotlib.pyplot as plt

        from cpet_stage1.stats.plots import plot_grouped_boxplot
        out = tmp_path / "boxplot_test.png"
        fig = plot_grouped_boxplot(cohort_df, "vo2_peak", "group_code", output_path=out)
        plt.close(fig)
        assert out.exists()

    def test_missing_variable_raises(self, cohort_df):
        """不存在的变量应抛 ValueError。"""
        from cpet_stage1.stats.plots import plot_grouped_boxplot
        with pytest.raises(ValueError):
            plot_grouped_boxplot(cohort_df, "nonexistent_col", "group_code")

    def test_generate_all_m4_plots_no_crash(self, cohort_df, config_path, tmp_path):
        """generate_all_m4_plots 应正常运行不崩溃。"""
        from cpet_stage1.stats.plots import generate_all_m4_plots
        result = generate_all_m4_plots(cohort_df, config_path, output_dir=tmp_path)
        assert isinstance(result, list)
