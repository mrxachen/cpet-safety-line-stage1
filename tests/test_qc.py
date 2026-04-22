"""
test_qc.py — QC 模块单元测试。

覆盖：
- 完整性检查（required 字段缺失率）
- 范围越界检查
- 逻辑一致性检查（VT1 < peak）
- 重复记录检测
- IQR 异常值检测
- QC 报告生成
- curated 输出不含 rejected 行
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.qc.rules import QCEngine, QCResult
from cpet_stage1.qc.validators import apply_qc_flags, generate_qc_report

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = PROJECT_ROOT / "configs/data/qc_rules_v1.yaml"
SCHEMA_PATH = PROJECT_ROOT / "configs/data/schema_v2.yaml"


@pytest.fixture(scope="module")
def engine():
    return QCEngine(rules_path=RULES_PATH, schema_path=SCHEMA_PATH)


def _make_minimal_df(n: int = 10, group: str = "CTRL") -> pd.DataFrame:
    """构造最小合法测试 DataFrame（保证 vt1_vo2 < vo2_peak < rcp_vo2）。"""
    rng = np.random.default_rng(42)
    vo2_peak = rng.uniform(20, 30, n)      # 峰值：20–30
    vt1_vo2 = vo2_peak * rng.uniform(0.5, 0.7, n)   # 无氧阈：峰值的 50–70%
    rcp_vo2 = vo2_peak * rng.uniform(0.85, 0.98, n)  # RCP：峰值的 85–98%
    return pd.DataFrame({
        "subject_id": [f"S{i:04d}" for i in range(n)],
        "age": rng.uniform(55, 80, n),
        "sex": rng.choice(["M", "F"], n),
        "group_code": group,
        "vo2_peak": vo2_peak,
        "hr_peak": rng.uniform(100, 180, n),
        "rer_peak": rng.uniform(1.0, 1.3, n),
        "vt1_vo2": vt1_vo2,
        "rcp_vo2": rcp_vo2,
        "ve_vco2_slope": rng.uniform(25, 40, n),
        "o2_pulse_peak": rng.uniform(8, 18, n),
        "vt1_pct_vo2peak": rng.uniform(40, 75, n),
    })


# ------------------------------------------------------------------ #
# 1. 完整性检查
# ------------------------------------------------------------------ #

class TestCompletenessCheck:
    def test_no_missing_no_rejected(self, engine):
        df = _make_minimal_df()
        flags, rejected = engine.check_completeness(df)
        assert len(rejected) == 0, "无缺失数据不应有拒绝行"

    def test_fully_missing_row_rejected(self, engine):
        df = _make_minimal_df()
        # 将第 0 行的所有关键字段置为 NaN
        for col in ["subject_id", "age", "sex", "vo2_peak", "hr_peak", "rer_peak"]:
            if col in df.columns:
                df.loc[0, col] = np.nan
        _, rejected = engine.check_completeness(df)
        assert 0 in rejected, "关键字段全部缺失的行应被拒绝"

    def test_partial_missing_not_rejected(self, engine):
        """只有 1 个必填字段缺失，不超过 50% 阈值，不应被拒绝。"""
        df = _make_minimal_df()
        df.loc[0, "rer_peak"] = np.nan  # 仅 1/6 必填字段缺失
        _, rejected = engine.check_completeness(df)
        assert 0 not in rejected


# ------------------------------------------------------------------ #
# 2. 范围检查
# ------------------------------------------------------------------ #

class TestRangeCheck:
    def test_no_violations_for_valid_data(self, engine):
        df = _make_minimal_df()
        flags = engine.check_range(df)
        # 构造的数据应全部在范围内
        assert not flags.any(axis=1).any(), "合法数据不应有范围越界"

    def test_vo2_peak_too_high(self, engine):
        df = _make_minimal_df()
        df.loc[0, "vo2_peak"] = 100.0  # 超过 max=60
        flags = engine.check_range(df)
        assert flags.loc[0, "range_vo2_peak"], "VO2peak=100 应触发范围越界"

    def test_age_too_low(self, engine):
        df = _make_minimal_df()
        df.loc[0, "age"] = 10.0  # 低于 min=40
        flags = engine.check_range(df)
        assert flags.loc[0, "range_age"]

    def test_nan_not_flagged(self, engine):
        """NaN 不应被标记为范围越界。"""
        df = _make_minimal_df()
        df.loc[0, "vo2_peak"] = np.nan
        flags = engine.check_range(df)
        assert not flags.loc[0, "range_vo2_peak"]

    def test_rer_peak_bounds(self, engine):
        df = _make_minimal_df()
        df.loc[0, "rer_peak"] = 0.5   # 低于 min=0.7
        df.loc[1, "rer_peak"] = 2.0   # 高于 max=1.6
        flags = engine.check_range(df)
        assert flags.loc[0, "range_rer_peak"]
        assert flags.loc[1, "range_rer_peak"]


# ------------------------------------------------------------------ #
# 3. 逻辑一致性检查
# ------------------------------------------------------------------ #

class TestLogicCheck:
    def test_vt1_lt_peak_valid(self, engine):
        """VT1 < VO2peak：合法时不应有违规。"""
        df = _make_minimal_df()
        # _make_minimal_df 中 vt1_vo2 < vo2_peak
        flags = engine.check_logic(df)
        vt1_flag = "logic_vt1_lt_peak"
        if vt1_flag in flags.columns:
            assert not flags[vt1_flag].any(), "vt1 < peak 合法时不应有违规"

    def test_vt1_gt_peak_violation(self, engine):
        """VT1 > VO2peak：应产生违规标记。"""
        df = _make_minimal_df()
        df.loc[0, "vt1_vo2"] = df.loc[0, "vo2_peak"] + 5  # vt1 > peak
        flags = engine.check_logic(df)
        vt1_flag = "logic_vt1_lt_peak"
        if vt1_flag in flags.columns:
            assert flags.loc[0, vt1_flag], "vt1 > peak 应违规"


# ------------------------------------------------------------------ #
# 4. 重复检测
# ------------------------------------------------------------------ #

class TestDuplicateCheck:
    def test_no_duplicates(self, engine):
        df = _make_minimal_df()
        df["test_date"] = pd.date_range("2023-01-01", periods=len(df))
        flags = engine.check_duplicates(df)
        assert not flags.any(), "无重复数据不应有重复标记"

    def test_detect_duplicate(self, engine):
        df = _make_minimal_df(n=4)
        df["test_date"] = "2023-01-01"  # 同日期
        # 同一 subject_id + test_date
        df.loc[0, "subject_id"] = "S_DUP"
        df.loc[2, "subject_id"] = "S_DUP"
        flags = engine.check_duplicates(df)
        assert flags.any(), "应检测到重复记录"

    def test_keep_latest_keeps_last(self, engine):
        """keep_latest 策略：应保留最后一条，标记前面的为重复。"""
        df = pd.DataFrame({
            "subject_id": ["S001", "S001"],
            "test_date": ["2023-01-01", "2023-01-01"],
            "vo2_peak": [18.0, 20.0],
        })
        flags = engine.check_duplicates(df)
        # keep_latest → 标记第 0 行（保留第 1 行）
        assert flags.iloc[0] == True
        assert flags.iloc[1] == False


# ------------------------------------------------------------------ #
# 5. IQR 异常值检测
# ------------------------------------------------------------------ #

class TestOutlierCheck:
    def test_no_outliers_normal_data(self, engine):
        df = _make_minimal_df(n=50)
        flags = engine.check_outliers(df)
        assert not flags.any(axis=1).all(), "正常分布数据不应全部标记为异常值"

    def test_extreme_value_flagged(self, engine):
        df = _make_minimal_df(n=100)
        df.loc[0, "vo2_peak"] = 999.0  # 极端值
        flags = engine.check_outliers(df)
        if "outlier_vo2_peak" in flags.columns:
            assert flags.loc[0, "outlier_vo2_peak"], "极端值应被标记为异常"

    def test_nan_not_flagged_outlier(self, engine):
        df = _make_minimal_df(n=50)
        df.loc[0, "vo2_peak"] = np.nan
        flags = engine.check_outliers(df)
        if "outlier_vo2_peak" in flags.columns:
            assert not flags.loc[0, "outlier_vo2_peak"]


# ------------------------------------------------------------------ #
# 5b. Schema Range Clip 测试
# ------------------------------------------------------------------ #

class TestClipToSchemaRange:
    """clip_to_schema_range() 将超出 schema range 的值替换为 NaN。"""

    def test_extreme_hr_peak_clipped_to_nan(self, engine):
        """hr_peak=147148 应被 clip 为 NaN（range [50, 230]）。"""
        df = _make_minimal_df(n=5)
        df.loc[0, "hr_peak"] = 147148.0
        clipped, counts = engine.clip_to_schema_range(df)
        assert pd.isna(clipped.loc[0, "hr_peak"]), "hr_peak=147148 应被 clip 为 NaN"
        assert counts.get("hr_peak", 0) >= 1

    def test_extreme_bp_peak_sys_clipped_to_nan(self, engine):
        """bp_peak_sys=29242 应被 clip 为 NaN（range [80, 300]）。"""
        df = _make_minimal_df(n=5)
        df["bp_peak_sys"] = [160.0, 165.0, 29242.0, 155.0, 170.0]
        clipped, counts = engine.clip_to_schema_range(df)
        assert pd.isna(clipped.loc[2, "bp_peak_sys"]), "bp_peak_sys=29242 应被 clip 为 NaN"
        assert counts.get("bp_peak_sys", 0) >= 1

    def test_extreme_ve_vco2_slope_clipped(self, engine):
        """ve_vco2_slope=1744 应被 clip 为 NaN（range [15, 70]）。"""
        df = _make_minimal_df(n=5)
        df["ve_vco2_slope"] = [28.0, 32.0, 1744.0, 25.0, 30.0]
        clipped, counts = engine.clip_to_schema_range(df)
        assert pd.isna(clipped.loc[2, "ve_vco2_slope"])
        assert counts.get("ve_vco2_slope", 0) >= 1

    def test_normal_values_not_clipped(self, engine):
        """正常范围内的值不应被 clip。"""
        df = _make_minimal_df(n=5)
        df["hr_peak"] = [120.0, 130.0, 140.0, 150.0, 160.0]
        original_hr = df["hr_peak"].copy()
        clipped, counts = engine.clip_to_schema_range(df)
        pd.testing.assert_series_equal(
            clipped["hr_peak"].reset_index(drop=True),
            original_hr.reset_index(drop=True),
            check_names=False,
        )
        assert counts.get("hr_peak", 0) == 0

    def test_nan_values_not_clipped(self, engine):
        """已经是 NaN 的值不应被计入 clip 统计。"""
        df = _make_minimal_df(n=5)
        df.loc[0, "hr_peak"] = float("nan")
        clipped, counts = engine.clip_to_schema_range(df)
        assert pd.isna(clipped.loc[0, "hr_peak"])
        assert counts.get("hr_peak", 0) == 0

    def test_original_df_not_modified(self, engine):
        """clip_to_schema_range 不应修改原始 DataFrame。"""
        df = _make_minimal_df(n=5)
        df.loc[0, "hr_peak"] = 147148.0
        original_val = df.loc[0, "hr_peak"]
        engine.clip_to_schema_range(df)
        assert df.loc[0, "hr_peak"] == original_val, "原始 DataFrame 不应被修改"

    def test_apply_qc_flags_with_engine_clips_values(self, engine, tmp_path):
        """apply_qc_flags 传入 engine 时应执行 clip。"""
        df = _make_minimal_df(n=5)
        df.loc[0, "hr_peak"] = 147148.0
        result = engine.run(df)
        curated = apply_qc_flags(df, result, engine=engine)
        assert pd.isna(curated.loc[0, "hr_peak"]), "apply_qc_flags+engine 应 clip hr_peak"

    def test_apply_qc_flags_without_engine_no_clip(self, engine):
        """apply_qc_flags 不传 engine 时，极端值保留在 curated 中。"""
        df = _make_minimal_df(n=5)
        df.loc[0, "hr_peak"] = 147148.0
        result = engine.run(df)
        curated = apply_qc_flags(df, result)  # 不传 engine
        # 不应 clip（保持原行为兼容性）
        assert curated.loc[0, "hr_peak"] == 147148.0


# ------------------------------------------------------------------ #
# 6. 完整 run() 测试
# ------------------------------------------------------------------ #

class TestQCEngineRun:
    def test_run_returns_qc_result(self, engine):
        df = _make_minimal_df()
        result = engine.run(df)
        assert isinstance(result, QCResult)

    def test_run_summary_keys(self, engine):
        df = _make_minimal_df()
        result = engine.run(df)
        for key in ["n_total", "n_rejected", "n_range_violation", "n_effort_adequate"]:
            assert key in result.summary

    def test_run_n_total_correct(self, engine):
        df = _make_minimal_df(n=20)
        result = engine.run(df)
        assert result.summary["n_total"] == 20

    def test_run_group_summary_populated(self, engine):
        df = pd.concat([
            _make_minimal_df(n=10, group="CTRL"),
            _make_minimal_df(n=5, group="EHT_ONLY"),
        ], ignore_index=True)
        result = engine.run(df)
        assert "CTRL" in result.group_summary
        assert "EHT_ONLY" in result.group_summary
        assert result.group_summary["CTRL"]["n"] == 10
        assert result.group_summary["EHT_ONLY"]["n"] == 5

    def test_effort_adequate_flag(self, engine):
        df = _make_minimal_df(n=5)
        df["rer_peak"] = [1.1, 0.9, 1.2, 0.8, 1.05]  # 行 0,2,3 RER≥1.05
        result = engine.run(df)
        assert result.effort_adequate.iloc[0] == True
        assert result.effort_adequate.iloc[1] == False


# ------------------------------------------------------------------ #
# 7. 报告生成测试
# ------------------------------------------------------------------ #

class TestQCReport:
    def test_generate_report_creates_file(self, engine, tmp_path):
        df = pd.concat([
            _make_minimal_df(n=10, group="CTRL"),
            _make_minimal_df(n=5, group="EHT_ONLY"),
        ], ignore_index=True)
        result = engine.run(df)
        report_path = tmp_path / "qc_report.md"
        text = generate_qc_report(result, df, report_path)
        assert report_path.exists()
        assert len(text) > 100

    def test_report_contains_global_overview(self, engine, tmp_path):
        df = _make_minimal_df(n=10, group="CTRL")
        result = engine.run(df)
        text = generate_qc_report(result, df, tmp_path / "qc_report.md")
        assert "全局概览" in text or "Global" in text

    def test_report_contains_eht_section(self, engine, tmp_path):
        """报告应包含 EHT_ONLY 专项段落。"""
        df = pd.concat([
            _make_minimal_df(n=10, group="CTRL"),
            _make_minimal_df(n=5, group="EHT_ONLY"),
        ], ignore_index=True)
        result = engine.run(df)
        text = generate_qc_report(result, df, tmp_path / "qc_report_eht.md")
        assert "EHT_ONLY" in text


# ------------------------------------------------------------------ #
# 8. curated 输出测试
# ------------------------------------------------------------------ #

class TestApplyQCFlags:
    def test_no_rejected_rows_in_curated(self, engine, tmp_path):
        df = _make_minimal_df(n=10)
        # 强制第 0 行关键字段缺失 → 应被拒绝
        for col in ["subject_id", "age", "sex", "vo2_peak", "hr_peak", "rer_peak"]:
            if col in df.columns:
                df.loc[0, col] = np.nan

        result = engine.run(df)
        curated = apply_qc_flags(
            df,
            result,
            curated_path=tmp_path / "curated.parquet",
            flags_path=tmp_path / "flags.parquet",
        )
        assert 0 not in curated.index, "rejected 行不应出现在 curated 中"

    def test_curated_parquet_written(self, engine, tmp_path):
        df = _make_minimal_df(n=5)
        result = engine.run(df)
        curated_path = tmp_path / "curated.parquet"
        apply_qc_flags(df, result, curated_path=curated_path)
        assert curated_path.exists()

    def test_qc_flags_column_in_curated(self, engine, tmp_path):
        df = _make_minimal_df(n=5)
        result = engine.run(df)
        curated = apply_qc_flags(df, result)
        assert "qc_flags" in curated.columns
        assert "qc_passed" in curated.columns

    def test_curated_has_less_or_equal_rows(self, engine, tmp_path):
        df = _make_minimal_df(n=10)
        result = engine.run(df)
        curated = apply_qc_flags(df, result)
        assert len(curated) <= len(df)
