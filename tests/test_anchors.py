"""
tests/test_anchors.py — 锚点资产构建与导出测试。

覆盖范围：
- AnchorBuilder.build() 基本功能
- R/T/I 三轴变量提取（含缺失处理）
- 轴综合评分计算
- S_lab_score 范围合法性
- Z_lab_zone 来自 P1 zone 映射
- Z_lab_zone 从 S_lab 推导（无 P1 zone）
- 覆盖率统计
- export_anchor_package 文件输出
- BridgeContractValidator 验证通过/失败
- contract_snapshot.json 生成
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.anchors.anchor_builder import AnchorBuilder, AnchorTableResult
from cpet_stage1.anchors.export_anchor_package import export_anchor_package
from cpet_stage1.contracts.bridge_contract import BridgeContractValidator, BridgeContractResult

# ============================================================
# 配置路径
# ============================================================
ANCHOR_RULES_PATH = Path("configs/bridge/anchor_rules_v1.yaml")


# ============================================================
# 辅助函数
# ============================================================

def _make_cohort_df(n: int = 20) -> pd.DataFrame:
    """构建含完整字段的测试 cohort DataFrame。"""
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "subject_id": [f"S{i:04d}" for i in range(n)],
        "cpet_session_id": [f"S{i:04d}" for i in range(n)],
        "group_code": (["CTRL"] * 5 + ["EHT_ONLY"] * 5 + ["HTN_HISTORY_NO_EHT"] * 5 + ["HTN_HISTORY_WITH_EHT"] * 5)[:n],
        "cohort_2x2": (["HTN-/EIH-"] * 5 + ["HTN-/EIH+"] * 5 + ["HTN+/EIH-"] * 5 + ["HTN+/EIH+"] * 5)[:n],
        "age": rng.integers(60, 80, size=n).astype(float),
        "vo2_peak_pct_pred": rng.uniform(40, 120, size=n),
        "o2_pulse_peak": rng.uniform(6, 20, size=n),
        "vt1_vo2": rng.uniform(8, 16, size=n),
        "vo2_peak": rng.uniform(15, 35, size=n),
        "ve_vco2_slope": rng.uniform(22, 45, size=n),
        "hr_peak": rng.integers(110, 170, size=n).astype(float),
        "bp_peak_sys": rng.integers(130, 230, size=n).astype(float),
        "eih_status": ([False] * 10 + [True] * 10)[:n],
        "htn_history": ([False] * 5 + [False] * 5 + [True] * 5 + [True] * 5)[:n],
    })


def _make_label_df(n: int = 20) -> pd.DataFrame:
    """构建含 P0/P1 标签的测试 DataFrame。"""
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "p0_event": ([False] * 10 + [True] * 10)[:n],
        "p1_zone": ([0] * 7 + [1] * 7 + [2] * 6)[:n],
        "effort_hr_adequate": [True] * n,
    })


# ============================================================
# AnchorBuilder 基本功能测试
# ============================================================

class TestAnchorBuilder:
    def _get_builder(self) -> AnchorBuilder:
        return AnchorBuilder(ANCHOR_RULES_PATH)

    def test_build_returns_result(self):
        builder = self._get_builder()
        cohort_df = _make_cohort_df()
        result = builder.build(cohort_df)
        assert isinstance(result, AnchorTableResult)

    def test_build_n_total_correct(self):
        builder = self._get_builder()
        cohort_df = _make_cohort_df(15)
        result = builder.build(cohort_df)
        assert result.n_total == 15

    def test_build_with_label_df(self):
        builder = self._get_builder()
        cohort_df = _make_cohort_df()
        label_df = _make_label_df()
        result = builder.build(cohort_df, label_df=label_df)
        assert "p0_event" in result.df.columns
        assert "p1_zone" in result.df.columns

    def test_required_output_columns_present(self):
        builder = self._get_builder()
        cohort_df = _make_cohort_df()
        label_df = _make_label_df()
        result = builder.build(cohort_df, label_df=label_df)
        required = [
            "reserve_axis", "threshold_axis", "instability_axis",
            "a_lab_vector", "s_lab_score", "z_lab_zone",
        ]
        for col in required:
            assert col in result.df.columns, f"缺少列: {col}"

    def test_z_lab_zone_values_from_p1(self):
        builder = self._get_builder()
        cohort_df = _make_cohort_df()
        label_df = _make_label_df()
        result = builder.build(cohort_df, label_df=label_df)
        valid_zones = {"green", "yellow", "red"}
        non_null = result.df["z_lab_zone"].dropna()
        assert set(non_null.unique()).issubset(valid_zones)

    def test_z_lab_zone_without_p1(self):
        builder = self._get_builder()
        cohort_df = _make_cohort_df()
        result = builder.build(cohort_df)  # 无 label_df
        valid_zones = {"green", "yellow", "red"}
        non_null = result.df["z_lab_zone"].dropna()
        assert set(non_null.unique()).issubset(valid_zones)

    def test_s_lab_score_range(self):
        builder = self._get_builder()
        cohort_df = _make_cohort_df()
        result = builder.build(cohort_df)
        score = result.df["s_lab_score"].dropna()
        assert (score >= 0).all(), "S_lab_score < 0 存在"
        assert (score <= 100).all(), "S_lab_score > 100 存在"

    def test_reserve_axis_range(self):
        builder = self._get_builder()
        cohort_df = _make_cohort_df()
        result = builder.build(cohort_df)
        r_axis = result.df["reserve_axis"].dropna()
        assert (r_axis >= 0).all()
        assert (r_axis <= 100).all()

    def test_instability_axis_range(self):
        builder = self._get_builder()
        cohort_df = _make_cohort_df()
        result = builder.build(cohort_df)
        i_axis = result.df["instability_axis"].dropna()
        assert (i_axis >= 0).all()
        assert (i_axis <= 100).all()

    def test_eih_positive_increases_instability(self):
        """EIH 阳性组的 instability_axis 均值应高于阴性组。"""
        builder = self._get_builder()
        cohort_df = _make_cohort_df(20)
        result = builder.build(cohort_df)
        df = result.df.copy()
        df["eih_orig"] = cohort_df["eih_status"].values
        eih_pos = df.loc[df["eih_orig"], "instability_axis"].mean()
        eih_neg = df.loc[~df["eih_orig"], "instability_axis"].mean()
        assert eih_pos > eih_neg, f"EIH+ instability ({eih_pos:.1f}) 应 > EIH- ({eih_neg:.1f})"

    def test_high_vo2_pct_pred_high_reserve(self):
        """高 vo2_peak_pct_pred 应产生高 reserve_axis。"""
        builder = self._get_builder()
        df_high = pd.DataFrame({
            "cpet_session_id": ["H1", "H2"],
            "vo2_peak_pct_pred": [120.0, 115.0],
            "o2_pulse_peak": [18.0, 16.0],
            "ve_vco2_slope": [25.0, 26.0],
            "eih_status": [False, False],
        })
        df_low = pd.DataFrame({
            "cpet_session_id": ["L1", "L2"],
            "vo2_peak_pct_pred": [40.0, 35.0],
            "o2_pulse_peak": [8.0, 7.0],
            "ve_vco2_slope": [25.0, 26.0],
            "eih_status": [False, False],
        })
        r_high = builder.build(df_high).df["reserve_axis"].mean()
        r_low = builder.build(df_low).df["reserve_axis"].mean()
        assert r_high > r_low, f"高 VO2%pred 的 reserve ({r_high:.1f}) 应 > 低 VO2%pred ({r_low:.1f})"

    def test_a_lab_vector_valid_json(self):
        builder = self._get_builder()
        cohort_df = _make_cohort_df(5)
        result = builder.build(cohort_df)
        for val in result.df["a_lab_vector"]:
            parsed = json.loads(val)
            assert set(parsed.keys()) == {"R", "T", "I"}

    def test_anchor_coverage_dict(self):
        builder = self._get_builder()
        cohort_df = _make_cohort_df()
        result = builder.build(cohort_df)
        assert isinstance(result.anchor_coverage, dict)
        # 有 vo2_peak_pct_pred 和 o2_pulse_peak → R1/R2 应为 True
        assert result.anchor_coverage.get("reserve_r1_vo2peak_pct_pred", False)
        assert result.anchor_coverage.get("reserve_r2_o2_pulse_peak", False)

    def test_missing_optional_fields_handled(self):
        """缺失 vt1_hr/rcp_hr/vt1_load_w 时不应报错，对应列应为 NaN。"""
        builder = self._get_builder()
        df = pd.DataFrame({
            "cpet_session_id": ["X1"],
            "vo2_peak_pct_pred": [75.0],
            "ve_vco2_slope": [28.0],
            "eih_status": [False],
        })
        result = builder.build(df)
        assert result.df["threshold_t1_vt1_hr"].isna().all()
        assert result.df["threshold_t2_rcp_hr"].isna().all()
        assert result.df["threshold_t3_vt1_load_w"].isna().all()

    def test_bp_response_derived_from_bp_peak_sys(self):
        """bp_response_abnormal 应从 bp_peak_sys > 180 自动推导。"""
        builder = self._get_builder()
        df = pd.DataFrame({
            "cpet_session_id": ["A", "B"],
            "bp_peak_sys": [200.0, 160.0],   # A > 180, B ≤ 180
            "ve_vco2_slope": [28.0, 28.0],
            "eih_status": [False, False],
        })
        result = builder.build(df)
        assert result.df["instability_i3_bp_response_abnormal"].iloc[0], "A 应为 True"
        assert not result.df["instability_i3_bp_response_abnormal"].iloc[1], "B 应为 False"

    def test_vt1_pct_vo2peak_derived(self):
        """vt1_pct_vo2peak 应从 vt1_vo2/vo2_peak × 100 派生。"""
        builder = self._get_builder()
        df = pd.DataFrame({
            "cpet_session_id": ["A"],
            "vt1_vo2": [12.0],
            "vo2_peak": [20.0],
            "ve_vco2_slope": [28.0],
            "eih_status": [False],
        })
        result = builder.build(df)
        expected = 12.0 / 20.0 * 100
        actual = result.df["reserve_r3_vt1_pct_vo2peak"].iloc[0]
        assert abs(actual - expected) < 0.01

    def test_n_per_zone_counts_correct(self):
        builder = self._get_builder()
        cohort_df = _make_cohort_df()
        label_df = _make_label_df()
        result = builder.build(cohort_df, label_df=label_df)
        total_counted = sum(result.n_per_zone.values())
        assert total_counted == result.n_total

    def test_summary_string(self):
        builder = self._get_builder()
        result = builder.build(_make_cohort_df())
        s = result.summary()
        assert "AnchorBuilder" in s
        assert "Z_lab" in s

    def test_coverage_report_string(self):
        builder = self._get_builder()
        result = builder.build(_make_cohort_df())
        report = result.coverage_report()
        assert "覆盖率" in report
        assert "reserve_r1" in report


# ============================================================
# export_anchor_package 测试
# ============================================================

class TestExportAnchorPackage:
    def test_parquet_written(self, tmp_path):
        builder = AnchorBuilder(ANCHOR_RULES_PATH)
        result = builder.build(_make_cohort_df(), label_df=_make_label_df())
        parquet_path = tmp_path / "anchor_table.parquet"
        exported = export_anchor_package(
            result,
            anchor_parquet_path=parquet_path,
            coverage_report_path=tmp_path / "coverage.md",
        )
        assert parquet_path.exists()
        df = pd.read_parquet(parquet_path)
        assert len(df) == result.n_total

    def test_coverage_report_written(self, tmp_path):
        builder = AnchorBuilder(ANCHOR_RULES_PATH)
        result = builder.build(_make_cohort_df())
        cov_path = tmp_path / "coverage.md"
        export_anchor_package(
            result,
            anchor_parquet_path=tmp_path / "anchor_table.parquet",
            coverage_report_path=cov_path,
        )
        assert cov_path.exists()
        assert "覆盖率" in cov_path.read_text(encoding="utf-8")

    def test_package_dir_created(self, tmp_path):
        builder = AnchorBuilder(ANCHOR_RULES_PATH)
        result = builder.build(_make_cohort_df(), label_df=_make_label_df())
        pkg_dir = tmp_path / "pkg"
        export_anchor_package(
            result,
            anchor_parquet_path=tmp_path / "anchor_table.parquet",
            coverage_report_path=tmp_path / "coverage.md",
            package_dir=pkg_dir,
        )
        assert (pkg_dir / "anchor_summary.json").exists()
        assert (pkg_dir / "anchor_table_preview.csv").exists()


# ============================================================
# BridgeContractValidator 测试
# ============================================================

class TestBridgeContractValidator:
    def _make_valid_anchor_df(self, n: int = 10) -> pd.DataFrame:
        rng = np.random.default_rng(0)
        return pd.DataFrame({
            "cpet_session_id": [f"S{i:04d}" for i in range(n)],
            "reserve_axis": rng.uniform(30, 90, n),
            "threshold_axis": rng.uniform(30, 80, n),
            "instability_axis": rng.uniform(0, 60, n),
            "a_lab_vector": ['{"R": 60.0, "T": 55.0, "I": 20.0}'] * n,
            "s_lab_score": rng.uniform(10, 80, n),
            "z_lab_zone": (["green"] * 4 + ["yellow"] * 3 + ["red"] * 3)[:n],
        })

    def test_valid_anchor_df_passes(self):
        validator = BridgeContractValidator()
        df = self._make_valid_anchor_df()
        result = validator.validate(df)
        assert result.passed
        assert len(result.errors) == 0

    def test_missing_required_field_fails(self):
        validator = BridgeContractValidator()
        df = self._make_valid_anchor_df().drop(columns=["reserve_axis"])
        result = validator.validate(df)
        assert not result.passed
        assert any("reserve_axis" in e for e in result.errors)

    def test_all_nan_required_field_fails(self):
        validator = BridgeContractValidator()
        df = self._make_valid_anchor_df()
        df["s_lab_score"] = float("nan")
        result = validator.validate(df)
        assert not result.passed

    def test_invalid_zone_value_fails(self):
        validator = BridgeContractValidator()
        df = self._make_valid_anchor_df()
        df.loc[0, "z_lab_zone"] = "purple"  # 非法值
        result = validator.validate(df)
        assert not result.passed
        assert any("非法" in e for e in result.errors)

    def test_missing_recommended_field_warns(self):
        validator = BridgeContractValidator()
        df = self._make_valid_anchor_df()  # 无 subject_id
        result = validator.validate(df)
        # 必填字段都有 → passed=True
        assert result.passed
        # 推荐字段缺失 → 有 warnings
        assert len(result.warnings) > 0

    def test_snapshot_structure(self):
        validator = BridgeContractValidator()
        df = self._make_valid_anchor_df()
        result = validator.validate(df)
        snap = result.snapshot
        assert "contract_version" in snap
        assert "validated_at" in snap
        assert "passed" in snap
        assert "zone_distribution" in snap
        assert "score_stats" in snap

    def test_save_snapshot_json(self, tmp_path):
        validator = BridgeContractValidator()
        df = self._make_valid_anchor_df()
        result = validator.validate(df)
        snap_path = tmp_path / "contract_snapshot.json"
        result.save_snapshot(snap_path)
        assert snap_path.exists()
        with open(snap_path) as f:
            loaded = json.load(f)
        assert loaded["passed"] is True

    def test_zone_distribution_in_snapshot(self):
        validator = BridgeContractValidator()
        df = self._make_valid_anchor_df(9)
        df["z_lab_zone"] = ["green"] * 3 + ["yellow"] * 3 + ["red"] * 3
        result = validator.validate(df)
        dist = result.snapshot["zone_distribution"]
        assert dist.get("green", 0) == 3
        assert dist.get("yellow", 0) == 3
        assert dist.get("red", 0) == 3

    def test_score_stats_computed(self):
        validator = BridgeContractValidator()
        df = self._make_valid_anchor_df()
        result = validator.validate(df)
        stats = result.snapshot["score_stats"]
        assert stats["n_valid"] == len(df)
        assert stats["mean"] is not None

    def test_report_string_contains_status(self):
        validator = BridgeContractValidator()
        df = self._make_valid_anchor_df()
        result = validator.validate(df)
        report = result.report()
        assert "Bridge Contract" in report
        assert "通过" in report or "失败" in report

    def test_with_contract_rules_file(self):
        rules_path = Path("configs/bridge/contract_rules_v1.yaml")
        if not rules_path.exists():
            pytest.skip("contract_rules_v1.yaml 不存在，跳过")
        validator = BridgeContractValidator(rules_path)
        df = self._make_valid_anchor_df()
        result = validator.validate(df)
        assert isinstance(result, BridgeContractResult)

    def test_full_pipeline_build_and_validate(self):
        """端到端：AnchorBuilder → BridgeContractValidator。"""
        builder = AnchorBuilder(ANCHOR_RULES_PATH)
        cohort_df = _make_cohort_df(20)
        label_df = _make_label_df(20)
        anchor_result = builder.build(cohort_df, label_df=label_df)

        validator = BridgeContractValidator()
        contract_result = validator.validate(anchor_result.df)
        assert contract_result.passed, f"合约验证失败: {contract_result.errors}"
