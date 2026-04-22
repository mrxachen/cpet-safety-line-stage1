"""
test_phase_a.py — Phase A 新增模块单元测试。

覆盖：
- DunnPosthoc: 显著/非显著检验、Bonferroni 校正、报告生成
- EIHLogisticAnalyzer: 单变量/多变量回归、OR 合理性、报告生成
- plots 补充函数: zone 堆叠图、缺失热力图、相关热力图、森林图
- feature_engineer.derive_features: BMI 派生

所有测试使用合成数据。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


# ============================================================
# 合成数据生成
# ============================================================

def _make_cohort(n: int = 400, seed: int = 42) -> pd.DataFrame:
    """生成含四组 + CPET 变量的合成 cohort DataFrame。"""
    rng = np.random.RandomState(seed)
    n_per = n // 4
    groups = []
    for code, eih, vo2_offset in [
        ("CTRL", False, 0.0),
        ("HTN_HISTORY_NO_EHT", False, -4.0),
        ("HTN_HISTORY_WITH_EHT", True, -7.0),
        ("EHT_ONLY", True, -2.0),
    ]:
        n_g = n_per
        df_g = pd.DataFrame({
            "group_code": [code] * n_g,
            "age": rng.normal(67, 6, n_g).clip(55, 85),
            "sex": rng.choice(["M", "F"], n_g),
            "height_cm": rng.normal(165, 8, n_g).clip(145, 190),
            "weight_kg": rng.normal(70, 12, n_g).clip(45, 110),
            "htn_history": [1 if "HTN_HISTORY" in code else 0] * n_g,
            "eih_status": [eih] * n_g,
            "vo2_peak": rng.normal(22 + vo2_offset, 4, n_g).clip(8, 45),
            "hr_peak": rng.normal(130, 15, n_g).clip(80, 180),
            "o2_pulse_peak": rng.normal(12, 2, n_g).clip(5, 20),
            "vt1_vo2": rng.normal(14, 3, n_g).clip(6, 25),
            "hr_recovery": rng.normal(20, 8, n_g).clip(0, 50),
            "oues": rng.normal(1500, 300, n_g).clip(600, 3000),
            "mets_peak": rng.normal(6, 1.5, n_g).clip(2, 12),
            "ve_vco2_slope": rng.normal(30 + (3 if eih else 0), 5, n_g).clip(20, 50),
            "vo2_peak_pct_pred": rng.normal(70 + vo2_offset * 2, 12, n_g).clip(30, 110),
            "htn_years": rng.choice(
                list(rng.normal(8, 4, n_g).clip(0, 30)) + [np.nan] * (n_g // 3),
                n_g
            ),
            "z_lab_zone": rng.choice(["green", "yellow", "red"], n_g,
                                       p=[0.4, 0.35, 0.25]),
        })
        groups.append(df_g)
    return pd.concat(groups, ignore_index=True)


# ============================================================
# DunnPosthoc 测试
# ============================================================

class TestDunnPosthoc:
    """DunnPosthoc 测试组。"""

    def test_basic_run(self):
        """基本运行，结果结构正确。"""
        from cpet_stage1.stats.posthoc import DunnPosthoc

        df = _make_cohort()
        analyzer = DunnPosthoc()
        results = analyzer.run(df, variables=["vo2_peak", "hr_peak"], group_col="group_code")

        assert len(results) == 2
        assert "vo2_peak" in results
        assert "hr_peak" in results

    def test_result_structure(self):
        """检查 PosthocResult 结构。"""
        from cpet_stage1.stats.posthoc import DunnPosthoc, PosthocResult

        df = _make_cohort()
        analyzer = DunnPosthoc()
        results = analyzer.run(df, variables=["vo2_peak"], group_col="group_code")
        r = results["vo2_peak"]

        assert isinstance(r, PosthocResult)
        assert r.n_comparisons == 6  # C(4,2)=6
        assert len(r.pairs) == 6
        assert r.kruskal_p >= 0.0
        assert r.alpha_adjusted == pytest.approx(0.05 / 6, rel=1e-6)

    def test_p_values_range(self):
        """P 值在 [0,1] 范围内。"""
        from cpet_stage1.stats.posthoc import DunnPosthoc

        df = _make_cohort()
        analyzer = DunnPosthoc()
        results = analyzer.run(df, variables=["vo2_peak"], group_col="group_code")

        for pair in results["vo2_peak"].pairs:
            assert 0.0 <= pair.p_value_raw <= 1.0
            assert 0.0 <= pair.p_value_adjusted <= 1.0

    def test_known_significant_difference(self):
        """已知显著差异（HTN-EIH vs CTRL 的 vo2_peak）应显著。"""
        from cpet_stage1.stats.posthoc import DunnPosthoc

        # 构造极端差异
        rng = np.random.RandomState(42)
        df = pd.DataFrame({
            "group_code": ["A"] * 100 + ["B"] * 100,
            "x": np.concatenate([rng.normal(0, 0.1, 100), rng.normal(10, 0.1, 100)]),
        })
        analyzer = DunnPosthoc()
        results = analyzer.run(df, variables=["x"], group_col="group_code")
        r = results["x"]
        assert r.significant_pairs[0].p_value_adjusted < 0.05

    def test_report_generation(self):
        """报告生成不抛异常，输出文件存在。"""
        from cpet_stage1.stats.posthoc import DunnPosthoc, generate_posthoc_report

        df = _make_cohort()
        analyzer = DunnPosthoc()
        results = analyzer.run(df, variables=["vo2_peak"], group_col="group_code")

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "posthoc.md"
            text = generate_posthoc_report(results, output_path=out)
            assert out.exists()
            assert "Dunn" in text
            assert "vo2_peak" in text

    def test_missing_variable_skipped(self):
        """不存在的变量应被跳过。"""
        from cpet_stage1.stats.posthoc import DunnPosthoc

        df = _make_cohort()
        analyzer = DunnPosthoc()
        results = analyzer.run(df, variables=["vo2_peak", "nonexistent_col"],
                               group_col="group_code")
        assert "nonexistent_col" not in results
        assert "vo2_peak" in results

    def test_to_markdown_format(self):
        """to_markdown 输出包含必要字段。"""
        from cpet_stage1.stats.posthoc import DunnPosthoc

        df = _make_cohort()
        analyzer = DunnPosthoc()
        results = analyzer.run(df, variables=["vo2_peak"], group_col="group_code")
        md = results["vo2_peak"].to_markdown()
        assert "Kruskal-Wallis" in md
        assert "Bonferroni" in md


# ============================================================
# EIHLogisticAnalyzer 测试
# ============================================================

class TestEIHLogisticAnalyzer:
    """EIHLogisticAnalyzer 测试组。"""

    def test_basic_run(self):
        """基本运行，结果结构正确。"""
        from cpet_stage1.stats.logistic_eih import EIHLogisticAnalyzer

        df = _make_cohort()
        df["eih_status"] = df["eih_status"].astype(int)
        analyzer = EIHLogisticAnalyzer()
        result = analyzer.run(df, outcome="eih_status",
                               predictors=["age", "htn_history", "vo2_peak"])

        assert result.n_total > 0
        assert result.n_eih_positive >= 0
        assert 0.0 <= result.eih_rate <= 1.0

    def test_univariable_results(self):
        """单变量结果列表非空，OR > 0。"""
        from cpet_stage1.stats.logistic_eih import EIHLogisticAnalyzer

        df = _make_cohort()
        df["eih_status"] = df["eih_status"].astype(int)
        analyzer = EIHLogisticAnalyzer()
        result = analyzer.run(df, outcome="eih_status",
                               predictors=["age", "htn_history"])

        assert len(result.univariable) >= 1
        for r in result.univariable:
            assert r.or_value > 0
            assert r.ci_lower > 0
            assert r.ci_upper > r.ci_lower

    def test_multivariable_results(self):
        """多因素回归应收敛。"""
        from cpet_stage1.stats.logistic_eih import EIHLogisticAnalyzer

        df = _make_cohort()
        df["eih_status"] = df["eih_status"].astype(int)
        analyzer = EIHLogisticAnalyzer()
        result = analyzer.run(df, outcome="eih_status",
                               predictors=["age", "htn_history", "vo2_peak"])
        assert result.converged

    def test_bmi_derivation(self):
        """BMI 缺失时自动从 height/weight 派生。"""
        from cpet_stage1.stats.logistic_eih import EIHLogisticAnalyzer

        df = _make_cohort()
        df["eih_status"] = df["eih_status"].astype(int)
        assert "bmi" not in df.columns  # 确认 bmi 不存在
        analyzer = EIHLogisticAnalyzer()
        result = analyzer.run(df, outcome="eih_status",
                               predictors=["age", "bmi"])
        # bmi 应被派生并用于分析
        assert "bmi" in result.predictors_used

    def test_to_markdown_output(self):
        """to_markdown 输出包含必要节。"""
        from cpet_stage1.stats.logistic_eih import EIHLogisticAnalyzer

        df = _make_cohort()
        df["eih_status"] = df["eih_status"].astype(int)
        analyzer = EIHLogisticAnalyzer()
        result = analyzer.run(df, outcome="eih_status",
                               predictors=["age", "htn_history"])
        md = result.to_markdown()
        assert "单变量分析" in md
        assert "多因素分析" in md

    def test_to_forest_data(self):
        """forest_data DataFrame 包含必要列。"""
        from cpet_stage1.stats.logistic_eih import EIHLogisticAnalyzer

        df = _make_cohort()
        df["eih_status"] = df["eih_status"].astype(int)
        analyzer = EIHLogisticAnalyzer()
        result = analyzer.run(df, outcome="eih_status",
                               predictors=["age", "htn_history", "vo2_peak"])
        fdf = result.to_forest_data()
        assert set(["variable", "or", "ci_lower", "ci_upper", "p_value"]).issubset(fdf.columns)

    def test_report_file_saved(self):
        """报告文件应被保存。"""
        from cpet_stage1.stats.logistic_eih import (
            EIHLogisticAnalyzer, generate_eih_logistic_report
        )

        df = _make_cohort()
        df["eih_status"] = df["eih_status"].astype(int)
        analyzer = EIHLogisticAnalyzer()
        result = analyzer.run(df, outcome="eih_status",
                               predictors=["age", "htn_history"])

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "eih_logistic.md"
            generate_eih_logistic_report(result, output_path=out)
            assert out.exists()


# ============================================================
# 补充图表函数测试
# ============================================================

class TestSupplementaryPlots:
    """Phase A3 补充图表函数测试。"""

    def test_zone_distribution_stacked(self):
        """zone 堆叠图不抛异常，返回 Figure。"""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from cpet_stage1.stats.plots import plot_zone_distribution_stacked

        df = _make_cohort()
        fig = plot_zone_distribution_stacked(df, zone_col="z_lab_zone",
                                             group_col="group_code")
        assert fig is not None
        plt.close(fig)

    def test_missing_data_heatmap(self):
        """缺失热力图不抛异常。"""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from cpet_stage1.stats.plots import plot_missing_data_heatmap

        df = _make_cohort()
        # 人为添加一些缺失值
        df.loc[:20, "vo2_peak"] = np.nan
        fig = plot_missing_data_heatmap(df, max_vars=10)
        assert fig is not None
        plt.close(fig)

    def test_feature_correlation_heatmap(self):
        """相关热力图不抛异常。"""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from cpet_stage1.stats.plots import plot_feature_correlation_heatmap

        df = _make_cohort()
        fig = plot_feature_correlation_heatmap(
            df, variables=["vo2_peak", "hr_peak", "o2_pulse_peak", "hr_recovery"]
        )
        assert fig is not None
        plt.close(fig)

    def test_eih_forest_plot(self):
        """森林图不抛异常。"""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from cpet_stage1.stats.plots import plot_eih_forest

        forest_df = pd.DataFrame({
            "variable": ["age", "htn_history", "vo2_peak"],
            "or": [1.02, 1.5, 0.85],
            "ci_lower": [0.99, 1.1, 0.75],
            "ci_upper": [1.05, 2.0, 0.95],
            "p_value": [0.12, 0.01, 0.003],
            "significant": [False, True, True],
        })
        fig = plot_eih_forest(forest_df)
        assert fig is not None
        plt.close(fig)

    def test_safety_zone_concept(self):
        """安全区概念图不抛异常。"""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from cpet_stage1.stats.plots import plot_safety_zone_concept

        fig = plot_safety_zone_concept()
        assert fig is not None
        plt.close(fig)

    def test_generate_all_supplementary_plots(self):
        """generate_all_supplementary_plots 生成至少 3 张图。"""
        from cpet_stage1.stats.plots import generate_all_supplementary_plots

        df = _make_cohort()
        with tempfile.TemporaryDirectory() as tmpdir:
            generated = generate_all_supplementary_plots(df, output_dir=tmpdir)
            assert len(generated) >= 3  # 至少：zone分布+缺失热力图+概念图
            for fp in generated:
                assert Path(fp).exists()


# ============================================================
# FeatureEngineer.derive_features 测试
# ============================================================

class TestDeriveFeatures:
    """FeatureEngineer.derive_features BMI 派生测试。"""

    def _make_fe(self, config_path="configs/features/feature_config_v2.yaml"):
        from cpet_stage1.features.feature_engineer import FeatureEngineer
        return FeatureEngineer(
            config_path=config_path,
            label_rules_path="configs/data/label_rules_v2.yaml",
        )

    def test_bmi_derived_when_missing(self):
        """BMI 不存在时，从 height_cm + weight_kg 正确派生。"""
        try:
            fe = self._make_fe()
        except FileNotFoundError:
            pytest.skip("feature_config_v2.yaml 不存在（跳过）")

        df = pd.DataFrame({
            "height_cm": [160.0, 170.0, 175.0],
            "weight_kg": [60.0, 70.0, 80.0],
        })
        result = fe.derive_features(df)
        assert "bmi" in result.columns
        # 验证计算正确：60 / (1.6)^2 ≈ 23.44
        assert abs(result.loc[0, "bmi"] - 60.0 / (1.6 ** 2)) < 0.01

    def test_bmi_not_overwritten_when_exists(self):
        """BMI 已存在时，不覆盖。"""
        try:
            fe = self._make_fe()
        except FileNotFoundError:
            pytest.skip("feature_config_v2.yaml 不存在（跳过）")

        df = pd.DataFrame({
            "height_cm": [160.0],
            "weight_kg": [60.0],
            "bmi": [99.0],  # 已存在
        })
        result = fe.derive_features(df)
        assert result.loc[0, "bmi"] == 99.0  # 不被覆盖

    def test_bmi_nan_when_no_source_cols(self):
        """无 height_cm + weight_kg 时，BMI 不被添加（跳过）。"""
        try:
            fe = self._make_fe()
        except FileNotFoundError:
            pytest.skip("feature_config_v2.yaml 不存在（跳过）")

        df = pd.DataFrame({"age": [65.0, 70.0]})
        result = fe.derive_features(df)
        assert "bmi" not in result.columns  # 无法派生，不添加


# ============================================================
# 配置文件验证测试
# ============================================================

class TestNewConfigs:
    """新增配置文件测试。"""

    def test_label_rules_v3_loads(self):
        """label_rules_v3.yaml 可正常加载。"""
        import yaml
        p = Path("configs/data/label_rules_v3.yaml")
        if not p.exists():
            pytest.skip("label_rules_v3.yaml 不存在（跳过）")
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["version"] == "3.0"
        assert "p0" in cfg
        assert "p1" in cfg

    def test_label_rules_v3_eih_removed_from_red(self):
        """v3 Red 条件中不包含 eih_status。"""
        import yaml
        p = Path("configs/data/label_rules_v3.yaml")
        if not p.exists():
            pytest.skip("label_rules_v3.yaml 不存在（跳过）")
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        red_criteria = cfg["p1"]["zone_rules"]["red"].get("criteria_any", [])
        # v3 中 eih_status 不应出现在 Red 条件里
        eih_in_red = any("eih_status" in str(c) for c in red_criteria)
        assert not eih_in_red, "v3 Red 不应包含 eih_status 条件"

    def test_feature_config_v2_loads(self):
        """feature_config_v2.yaml 可正常加载。"""
        import yaml
        p = Path("configs/features/feature_config_v2.yaml")
        if not p.exists():
            pytest.skip("feature_config_v2.yaml 不存在（跳过）")
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["version"] == "2.0"
        assert "p0" in cfg
        assert "p1" in cfg

    def test_feature_config_v2_has_new_features(self):
        """v2 P1 包含 hr_recovery, oues, mets_peak。"""
        import yaml
        p = Path("configs/features/feature_config_v2.yaml")
        if not p.exists():
            pytest.skip("feature_config_v2.yaml 不存在（跳过）")
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        p1_cont = cfg["p1"]["continuous"]
        assert "hr_recovery" in p1_cont
        assert "oues" in p1_cont
        assert "mets_peak" in p1_cont

    def test_feature_config_v2_p0_has_bmi(self):
        """v2 P0 包含 bmi。"""
        import yaml
        p = Path("configs/features/feature_config_v2.yaml")
        if not p.exists():
            pytest.skip("feature_config_v2.yaml 不存在（跳过）")
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        p0_cont = cfg["p0"]["continuous"]
        assert "bmi" in p0_cont

    def test_cost_sensitive_lgbm_config_loads(self):
        """p1_lgbm_cost_sensitive.yaml 可加载且包含显式类权重。"""
        import yaml
        p = Path("configs/model/p1_lgbm_cost_sensitive.yaml")
        if not p.exists():
            pytest.skip("p1_lgbm_cost_sensitive.yaml 不存在（跳过）")
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        class_weight = cfg["hyperparameters"]["class_weight"]
        assert isinstance(class_weight, dict)
        assert class_weight[2] > class_weight[0]  # Red > Green

    def test_cost_sensitive_catboost_config_loads(self):
        """p1_catboost_cost_sensitive.yaml 可加载且包含 class_weights 列表。"""
        import yaml
        p = Path("configs/model/p1_catboost_cost_sensitive.yaml")
        if not p.exists():
            pytest.skip("p1_catboost_cost_sensitive.yaml 不存在（跳过）")
        with open(p, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        cw = cfg["hyperparameters"]["class_weights"]
        assert isinstance(cw, list)
        assert len(cw) == 3
        assert cw[2] > cw[0]  # Red > Green


# ============================================================
# SubgroupAnalyzer 测试
# ============================================================

class TestSubgroupAnalyzer:
    """SubgroupAnalyzer 测试组。"""

    def _make_df_with_zones(self, n: int = 400, seed: int = 42) -> pd.DataFrame:
        """生成含 zone 列的合成 DataFrame。"""
        df = _make_cohort(n=n, seed=seed)
        # 派生 BMI + 简单 zone 规则
        height_m = df["height_cm"] / 100.0
        df["bmi"] = df["weight_kg"] / (height_m ** 2)
        # 简化 zone 分配：根据 vo2_peak
        conditions = [
            df["vo2_peak"] >= 20,
            (df["vo2_peak"] >= 15) & (df["vo2_peak"] < 20),
        ]
        choices = ["green", "yellow"]
        df["p1_zone"] = np.select(conditions, choices, default="red")
        df["eih_status"] = df["eih_status"].astype(int)
        return df

    def test_run_sex(self):
        """性别亚组分析结构正确。"""
        from cpet_stage1.stats.subgroup import SubgroupAnalyzer

        df = self._make_df_with_zones()
        analyzer = SubgroupAnalyzer()
        result = analyzer.run_sex(df, zone_col="p1_zone")

        assert result.strata_def == "性别（sex）"
        assert len(result.summaries) == 2
        assert result.n_total == len(df)

    def test_run_age_median(self):
        """年龄中位数分层结构正确。"""
        from cpet_stage1.stats.subgroup import SubgroupAnalyzer

        df = self._make_df_with_zones()
        analyzer = SubgroupAnalyzer()
        result = analyzer.run_age_median(df, zone_col="p1_zone")

        assert len(result.summaries) == 2
        # 两组加起来应等于总样本
        total = sum(s.n_total for s in result.summaries)
        assert total == len(df)

    def test_run_eih(self):
        """EIH 亚组分析结构正确。"""
        from cpet_stage1.stats.subgroup import SubgroupAnalyzer

        df = self._make_df_with_zones()
        analyzer = SubgroupAnalyzer()
        result = analyzer.run_eih(df, zone_col="p1_zone")

        assert len(result.summaries) == 2
        # 每个亚组都有 zone 率
        for s in result.summaries:
            total_rate = sum(s.zone_rates.values())
            assert abs(total_rate - 1.0) < 0.01 or s.n_total == 0

    def test_run_htn(self):
        """HTN 亚组分析结构正确。"""
        from cpet_stage1.stats.subgroup import SubgroupAnalyzer

        df = self._make_df_with_zones()
        analyzer = SubgroupAnalyzer()
        result = analyzer.run_htn(df, zone_col="p1_zone")

        assert len(result.summaries) == 2

    def test_stratum_summary_has_median_vo2(self):
        """每个亚组应有 vo2_peak 中位数。"""
        from cpet_stage1.stats.subgroup import SubgroupAnalyzer

        df = self._make_df_with_zones()
        analyzer = SubgroupAnalyzer()
        result = analyzer.run_sex(df, zone_col="p1_zone")

        for s in result.summaries:
            assert s.median_vo2_peak is not None
            assert s.median_vo2_peak > 0

    def test_stratum_kw_p_value(self):
        """亚组间应有 KW 检验 p 值。"""
        from cpet_stage1.stats.subgroup import SubgroupAnalyzer

        df = self._make_df_with_zones()
        analyzer = SubgroupAnalyzer()
        result = analyzer.run_sex(df, zone_col="p1_zone")

        for s in result.summaries:
            if s.kw_p_vs_complement is not None:
                assert 0.0 <= s.kw_p_vs_complement <= 1.0

    def test_to_markdown_output(self):
        """to_markdown 输出包含必要内容。"""
        from cpet_stage1.stats.subgroup import SubgroupAnalyzer

        df = self._make_df_with_zones()
        analyzer = SubgroupAnalyzer()
        result = analyzer.run_sex(df, zone_col="p1_zone")
        md = result.to_markdown()
        assert "性别" in md
        assert "Green" in md or "green" in md.lower()

    def test_generate_subgroup_report(self):
        """报告生成不抛异常，文件存在。"""
        from cpet_stage1.stats.subgroup import SubgroupAnalyzer, generate_subgroup_report

        df = self._make_df_with_zones()
        analyzer = SubgroupAnalyzer()
        results = [
            analyzer.run_sex(df, zone_col="p1_zone"),
            analyzer.run_age_median(df, zone_col="p1_zone"),
            analyzer.run_eih(df, zone_col="p1_zone"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "subgroup.md"
            text = generate_subgroup_report(results, output_path=out)
            assert out.exists()
            assert len(text) > 50

    def test_missing_zone_col_graceful(self):
        """zone 列缺失时，zone 分布全部为 0（不抛异常）。"""
        from cpet_stage1.stats.subgroup import SubgroupAnalyzer

        df = self._make_df_with_zones()
        analyzer = SubgroupAnalyzer()
        result = analyzer.run_sex(df, zone_col="nonexistent_zone_col")
        for s in result.summaries:
            assert all(v == 0 for v in s.zone_counts.values())
