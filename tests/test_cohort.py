"""
tests/test_cohort.py — 2×2 队列注册和参考正常子集测试。

覆盖范围：
- group_code → htn_history/eih_status 推导（四象限）
- cohort_2x2 字符串映射
- cpet_session_id 生成（subject_id 存在/不存在）
- 未知 group_code 处理
- reference wide 筛选（含 NaN = absent 逻辑）
- reference strict 筛选（HR 代理）
- min_sample_size 警告
- 边界值（age 边界，VO2 边界，slope 边界）
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.cohort.cohort_registry import CohortRegistry, CohortRegistryResult
from cpet_stage1.cohort.reference_subset import ReferenceSubsetBuilder, ReferenceSubsetResult

# ============================================================
# 辅助函数
# ============================================================

REF_RULES_PATH = Path("configs/data/reference_rules_v2.yaml")


def _make_df(**kwargs) -> pd.DataFrame:
    """快速构建小型测试 DataFrame。"""
    defaults: dict = {
        "subject_id": [f"S{i:03d}" for i in range(len(next(iter(kwargs.values()))))],
    }
    defaults.update(kwargs)
    return pd.DataFrame(defaults)


def _make_full_df(n: int = 10, group_code: str = "CTRL") -> pd.DataFrame:
    """构建带全量字段的测试 DataFrame。"""
    return pd.DataFrame({
        "subject_id": [f"S{i:03d}" for i in range(n)],
        "group_code": [group_code] * n,
        "age": [65.0] * n,
        "vo2_peak_pct_pred": [75.0] * n,
        "ve_vco2_slope": [28.0] * n,
        "bp_peak_sys": [160.0] * n,
        "hr_peak": [130.0] * n,
        "cad_history": [False] * n,
        "hf_history": [False] * n,
    })


# ============================================================
# CohortRegistry 测试
# ============================================================

class TestCohortRegistryGroupCode:
    """group_code → 字段推导测试。"""

    def setup_method(self):
        self.registry = CohortRegistry()

    def _register_single_group(self, group_code: str) -> pd.DataFrame:
        df = _make_df(group_code=[group_code] * 5)
        result = self.registry.register(df)
        return result.df

    def test_ctrl_derives_htn_false_eih_false(self):
        df = self._register_single_group("CTRL")
        assert (df["htn_history"] == False).all()  # noqa: E712
        assert (df["eih_status"] == False).all()  # noqa: E712

    def test_ctrl_cohort_2x2(self):
        df = self._register_single_group("CTRL")
        assert (df["cohort_2x2"] == "HTN-/EIH-").all()

    def test_eht_only_derives_htn_false_eih_true(self):
        df = self._register_single_group("EHT_ONLY")
        assert (df["htn_history"] == False).all()  # noqa: E712
        assert (df["eih_status"] == True).all()  # noqa: E712

    def test_eht_only_cohort_2x2(self):
        df = self._register_single_group("EHT_ONLY")
        assert (df["cohort_2x2"] == "HTN-/EIH+").all()

    def test_htn_no_eht_derives_htn_true_eih_false(self):
        df = self._register_single_group("HTN_HISTORY_NO_EHT")
        assert (df["htn_history"] == True).all()  # noqa: E712
        assert (df["eih_status"] == False).all()  # noqa: E712

    def test_htn_no_eht_cohort_2x2(self):
        df = self._register_single_group("HTN_HISTORY_NO_EHT")
        assert (df["cohort_2x2"] == "HTN+/EIH-").all()

    def test_htn_with_eht_derives_htn_true_eih_true(self):
        df = self._register_single_group("HTN_HISTORY_WITH_EHT")
        assert (df["htn_history"] == True).all()  # noqa: E712
        assert (df["eih_status"] == True).all()  # noqa: E712

    def test_htn_with_eht_cohort_2x2(self):
        df = self._register_single_group("HTN_HISTORY_WITH_EHT")
        assert (df["cohort_2x2"] == "HTN+/EIH+").all()


class TestCohortRegistryFourQuadrants:
    """四象限覆盖测试。"""

    def setup_method(self):
        self.registry = CohortRegistry()

    def test_all_four_quadrants_present(self):
        df = _make_df(
            group_code=["CTRL", "EHT_ONLY", "HTN_HISTORY_NO_EHT", "HTN_HISTORY_WITH_EHT"]
        )
        result = self.registry.register(df)
        expected = {"HTN-/EIH-", "HTN-/EIH+", "HTN+/EIH-", "HTN+/EIH+"}
        assert set(result.cohort_counts.keys()) == expected

    def test_cohort_counts_sum_to_total(self):
        df = _make_df(
            group_code=["CTRL"] * 10 + ["EHT_ONLY"] * 5 + ["HTN_HISTORY_NO_EHT"] * 3
        )
        result = self.registry.register(df)
        assert sum(result.cohort_counts.values()) == len(df)


class TestCohortRegistrySessionId:
    """cpet_session_id 生成测试。"""

    def setup_method(self):
        self.registry = CohortRegistry()

    def test_session_id_equals_subject_id_when_present(self):
        df = _make_df(
            subject_id=["S001", "S002", "S003"],
            group_code=["CTRL", "CTRL", "EHT_ONLY"],
        )
        result = self.registry.register(df)
        assert list(result.df["cpet_session_id"]) == ["S001", "S002", "S003"]

    def test_session_id_generated_when_no_subject_id(self):
        df = pd.DataFrame({"group_code": ["CTRL"] * 5})
        result = self.registry.register(df)
        assert "cpet_session_id" in result.df.columns
        assert len(result.df["cpet_session_id"]) == 5
        assert result.df["cpet_session_id"].str.startswith("SESSION_").all()

    def test_session_id_unique(self):
        df = _make_df(
            subject_id=[f"S{i}" for i in range(20)],
            group_code=["CTRL"] * 20,
        )
        result = self.registry.register(df)
        assert result.df["cpet_session_id"].nunique() == 20


class TestCohortRegistryUnknownGroupCode:
    """未知 group_code 测试。"""

    def setup_method(self):
        self.registry = CohortRegistry()

    def test_unknown_group_code_yields_none_columns(self):
        df = _make_df(group_code=["UNKNOWN"])
        result = self.registry.register(df)
        assert result.df["htn_history"].isna().all()
        assert result.df["cohort_2x2"].isna().all()

    def test_unknown_group_code_reported(self):
        df = _make_df(group_code=["CTRL", "UNKNOWN"])
        result = self.registry.register(df)
        assert "UNKNOWN" in result.unknown_group_codes

    def test_missing_group_code_column_raises(self):
        df = pd.DataFrame({"subject_id": ["S001"]})
        with pytest.raises(ValueError, match="group_code"):
            self.registry.register(df)


# ============================================================
# ReferenceSubsetBuilder 测试
# ============================================================

@pytest.fixture
def ref_builder():
    """加载真实配置文件。"""
    return ReferenceSubsetBuilder(REF_RULES_PATH)


@pytest.fixture
def ctrl_df():
    """已注册的 CTRL 组 DataFrame（符合 wide 条件）。"""
    n = 100
    return pd.DataFrame({
        "subject_id": [f"S{i:03d}" for i in range(n)],
        "group_code": ["CTRL"] * n,
        "htn_history": [False] * n,
        "eih_status": [False] * n,
        "cad_history": [False] * n,
        "hf_history": [False] * n,
        "vo2_peak_pct_pred": [75.0] * n,
        "ve_vco2_slope": [28.0] * n,
        "age": [65.0] * n,
        "hr_peak": [135.0] * n,  # 85% × (220 - 65) = 131.75 → 充足
    })


class TestReferenceWideFilter:
    """Wide 筛选测试。"""

    def test_ctrl_group_passes_wide(self, ref_builder, ctrl_df):
        result = ref_builder.build(ctrl_df)
        assert result.n_wide == len(ctrl_df)

    def test_htn_history_excluded_from_wide(self, ref_builder, ctrl_df):
        ctrl_df = ctrl_df.copy()
        ctrl_df.loc[0, "htn_history"] = True
        result = ref_builder.build(ctrl_df)
        assert result.n_wide == len(ctrl_df) - 1

    def test_eih_status_excluded_from_wide(self, ref_builder, ctrl_df):
        ctrl_df = ctrl_df.copy()
        ctrl_df.loc[0, "eih_status"] = True
        result = ref_builder.build(ctrl_df)
        assert result.n_wide == len(ctrl_df) - 1

    def test_nan_cad_history_passes_wide(self, ref_builder, ctrl_df):
        """NaN 视为 absent，不排除。"""
        ctrl_df = ctrl_df.copy()
        ctrl_df["cad_history"] = float("nan")
        result = ref_builder.build(ctrl_df)
        assert result.n_wide == len(ctrl_df)

    def test_nan_hf_history_passes_wide(self, ref_builder, ctrl_df):
        ctrl_df = ctrl_df.copy()
        ctrl_df["hf_history"] = float("nan")
        result = ref_builder.build(ctrl_df)
        assert result.n_wide == len(ctrl_df)

    def test_low_vo2_excluded_from_wide(self, ref_builder, ctrl_df):
        """vo2_peak_pct_pred < 70 应排除。"""
        ctrl_df = ctrl_df.copy()
        ctrl_df.loc[0, "vo2_peak_pct_pred"] = 65.0
        result = ref_builder.build(ctrl_df)
        assert result.n_wide == len(ctrl_df) - 1

    def test_boundary_vo2_70_passes_wide(self, ref_builder, ctrl_df):
        """vo2_peak_pct_pred == 70 应通过（>=）。"""
        ctrl_df = ctrl_df.copy()
        ctrl_df.loc[0, "vo2_peak_pct_pred"] = 70.0
        result = ref_builder.build(ctrl_df)
        assert result.n_wide == len(ctrl_df)

    def test_high_slope_excluded_from_wide(self, ref_builder, ctrl_df):
        """ve_vco2_slope > 30 应排除。"""
        ctrl_df = ctrl_df.copy()
        ctrl_df.loc[0, "ve_vco2_slope"] = 31.0
        result = ref_builder.build(ctrl_df)
        assert result.n_wide == len(ctrl_df) - 1

    def test_boundary_slope_30_passes_wide(self, ref_builder, ctrl_df):
        """ve_vco2_slope == 30 应通过（<=）。"""
        ctrl_df = ctrl_df.copy()
        ctrl_df.loc[0, "ve_vco2_slope"] = 30.0
        result = ref_builder.build(ctrl_df)
        assert result.n_wide == len(ctrl_df)


class TestReferenceStrictFilter:
    """Strict 筛选测试（HR 代理）。"""

    def test_adequate_hr_passes_strict(self, ref_builder, ctrl_df):
        # hr_peak=135, age=65 → 0.85×(220-65)=131.75 → 充足
        result = ref_builder.build(ctrl_df)
        assert result.n_strict == len(ctrl_df)

    def test_inadequate_hr_excluded_from_strict(self, ref_builder, ctrl_df):
        ctrl_df = ctrl_df.copy()
        # hr_peak=100, age=65 → 0.85×155=131.75 → 不充足
        ctrl_df.loc[0, "hr_peak"] = 100.0
        result = ref_builder.build(ctrl_df)
        assert result.n_strict == len(ctrl_df) - 1

    def test_nan_hr_excluded_from_strict(self, ref_builder, ctrl_df):
        ctrl_df = ctrl_df.copy()
        ctrl_df.loc[0, "hr_peak"] = float("nan")
        result = ref_builder.build(ctrl_df)
        assert result.n_strict == len(ctrl_df) - 1

    def test_strict_subset_of_wide(self, ref_builder, ctrl_df):
        ctrl_df = ctrl_df.copy()
        ctrl_df.loc[0, "hr_peak"] = 50.0  # 不充足
        result = ref_builder.build(ctrl_df)
        assert result.n_strict <= result.n_wide


class TestReferenceMinSample:
    """最小样本量警告测试。"""

    def test_warning_when_below_min_sample(self, ref_builder, caplog):
        import logging
        # 只有 5 行，< min_sample_size=50
        df = pd.DataFrame({
            "htn_history": [False] * 5,
            "eih_status": [False] * 5,
            "cad_history": [False] * 5,
            "hf_history": [False] * 5,
            "vo2_peak_pct_pred": [75.0] * 5,
            "ve_vco2_slope": [28.0] * 5,
            "age": [65.0] * 5,
            "hr_peak": [135.0] * 5,
        })
        with caplog.at_level(logging.WARNING):
            result = ref_builder.build(df)
        assert result.n_wide < 50
        assert any("最小要求" in r.message for r in caplog.records)
