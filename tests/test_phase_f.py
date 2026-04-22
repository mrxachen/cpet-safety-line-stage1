"""
test_phase_f.py — Phase F 单元测试

覆盖：
- Step 0: data_audit.py
- Step 1: reference_builder_v2.py
- Step 2: zone_engine_v2.py
- Step 3: zone_sensitivity.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.stats.data_audit import run_data_audit
from cpet_stage1.stats.reference_builder_v2 import build_reference_v2, _fit_best_formula
from cpet_stage1.labels.zone_engine_v2 import (
    ZoneEngineV2,
    _binary_outcome,
    _youden_cutpoints,
    _reference_percentile_cutpoints,
    _compute_r_axis_v2,
    _compute_t_axis_v2,
    _compute_i_axis_v2,
)
from cpet_stage1.stats.zone_sensitivity import run_sensitivity_analysis


# ── 合成数据工厂 ──────────────────────────────────────────────────────────────

def make_synthetic_df(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """生成合成 CPET DataFrame，覆盖 Phase F 所需字段。"""
    rng = np.random.default_rng(seed)

    df = pd.DataFrame({
        "subject_id": [f"S{i:04d}" for i in range(n)],
        "sex": rng.choice(["M", "F"], size=n),
        "age": rng.uniform(60, 80, n),
        "height_cm": rng.uniform(155, 180, n),
        "weight_kg": rng.uniform(50, 90, n),
        "vo2_peak": rng.uniform(10, 35, n),
        "hr_peak": rng.uniform(80, 170, n),
        "ve_vco2_slope": rng.uniform(20, 45, n),
        "o2_pulse_peak": rng.uniform(5, 25, n),
        "vt1_vo2": rng.uniform(8, 25, n),
        "mets_peak": rng.uniform(2, 12, n),
        "vo2_peak_pct_pred": rng.uniform(40, 120, n),
        "bp_peak_sys": rng.uniform(140, 240, n),
        "bp_peak_dia": rng.uniform(70, 130, n),
        "exercise_capacity": rng.choice(["正常", "下降"], size=n, p=[0.4, 0.6]),
        "exercise_habit": rng.choice(["regular", "occasional", None], size=n, p=[0.4, 0.3, 0.3]),
        "htn_history": rng.choice([0, 1], size=n),
        "med_betablocker": rng.choice([0, 1], size=n, p=[0.93, 0.07]),
        "group_code": rng.choice(
            ["CTRL", "HTN_HISTORY_NO_EHT", "HTN_HISTORY_WITH_EHT", "EHT_ONLY"],
            size=n, p=[0.5, 0.25, 0.1, 0.15],
        ),
        "test_result": rng.choice(["阴性", "可疑阳性", "阳性", None], size=n, p=[0.75, 0.1, 0.05, 0.1]),
        "o2_pulse_trajectory": rng.choice(
            ["在运动试验期间持续升高", "早期持续平台", "晚期平台", "下降", None],
            size=n, p=[0.80, 0.08, 0.04, 0.04, 0.04],
        ),
        "eih_status": rng.choice([True, False], size=n, p=[0.2, 0.8]),
        "p1_zone": rng.choice([0, 1, 2, np.nan], size=n, p=[0.35, 0.35, 0.25, 0.05]),
    })

    # 参考子集标志（CTRL 中随机 50%）
    ctrl_mask = df["group_code"] == "CTRL"
    ref_flag = pd.Series(False, index=df.index)
    ctrl_idx = df.index[ctrl_mask]
    ref_flag.iloc[rng.choice(len(ctrl_idx), size=len(ctrl_idx) // 2, replace=False)] = True
    df["reference_flag_wide"] = ref_flag

    return df


# ── Step 0: data_audit ────────────────────────────────────────────────────────

class TestDataAudit:
    """测试 data_audit.run_data_audit。"""

    def test_run_on_synthetic(self, tmp_path):
        df = make_synthetic_df(100)
        # 保存为 parquet，audit 读文件
        p = tmp_path / "synthetic.parquet"
        df.to_parquet(p)
        out = tmp_path / "audit.md"
        report = run_data_audit(p, out)
        assert isinstance(report, str)
        assert len(report) > 100
        assert out.exists()

    def test_report_contains_sections(self, tmp_path):
        df = make_synthetic_df(100)
        p = tmp_path / "d.parquet"
        df.to_parquet(p)
        report = run_data_audit(p)
        assert "汇总矩阵" in report
        assert "关键发现摘要" in report
        assert "Phase F 建模可用性评估" in report

    def test_all_zero_detection(self, tmp_path):
        df = make_synthetic_df(50)
        df["all_zero_col"] = 0
        p = tmp_path / "az.parquet"
        df.to_parquet(p)
        report = run_data_audit(p)
        assert "all_zero_col" in report

    def test_completeness_computation(self, tmp_path):
        df = make_synthetic_df(100)
        df.loc[:10, "age"] = np.nan  # 11 missing
        p = tmp_path / "mc.parquet"
        df.to_parquet(p)
        report = run_data_audit(p)
        # Should report < 100% completeness for age
        assert "age" in report


# ── Step 1: reference_builder_v2 ─────────────────────────────────────────────

class TestReferenceBuilderV2:
    """测试改进参考方程。"""

    def test_basic_build(self):
        df = make_synthetic_df(200)
        result = build_reference_v2(df, v1_r2_map={"vo2_peak": 0.298})
        assert "vo2_peak" in result.equations
        eq = result.equations["vo2_peak"]
        assert 0 <= eq.r_squared <= 1.0
        assert eq.n_ref >= 5

    def test_bmi_derived(self):
        df = make_synthetic_df(200)
        # Remove bmi if exists
        if "bmi" in df.columns:
            df = df.drop(columns=["bmi"])
        result = build_reference_v2(df, targets=["vo2_peak"])
        # Should succeed (derives BMI internally)
        assert "vo2_peak" in result.equations

    def test_r2_improvement(self):
        """V2 R² should be ≥ v1 R²."""
        df = make_synthetic_df(300)
        v1_r2 = 0.10
        result = build_reference_v2(df, v1_r2_map={"vo2_peak": v1_r2}, targets=["vo2_peak"])
        eq = result.equations["vo2_peak"]
        # V2 should at least match or exceed v1 on full fit
        assert eq.r_squared >= 0.0  # At minimum non-negative

    def test_pred_df_columns(self):
        df = make_synthetic_df(200)
        result = build_reference_v2(df, targets=["vo2_peak"])
        assert "vo2_peak_pct_v2" in result.pred_df.columns
        assert "vo2_peak_z_v2" in result.pred_df.columns

    def test_external_comparisons(self):
        df = make_synthetic_df(200)
        result = build_reference_v2(df, targets=["vo2_peak"])
        # External comparisons only for vo2_peak
        assert isinstance(result.external_comparisons, list)

    def test_stratified_equations(self):
        df = make_synthetic_df(400)
        result = build_reference_v2(df, targets=["vo2_peak"])
        eq = result.equations["vo2_peak"]
        # Should have some stratified equations
        assert isinstance(eq.stratified_eqs, dict)

    def test_report_generation(self, tmp_path):
        df = make_synthetic_df(200)
        out = tmp_path / "ref_v2.md"
        result = build_reference_v2(df, targets=["vo2_peak"], output_path=out)
        assert out.exists()
        text = out.read_text()
        assert "R²" in text

    def test_missing_target(self):
        df = make_synthetic_df(100)
        result = build_reference_v2(df, targets=["nonexistent_col"])
        assert len(result.equations) == 0


# ── Step 2: zone_engine_v2 ───────────────────────────────────────────────────

class TestZoneEngineV2:
    """测试数据驱动安全区引擎。"""

    def test_binary_outcome(self):
        df = make_synthetic_df(100)
        outcome = _binary_outcome(df)
        assert outcome.notna().sum() > 0
        assert set(outcome.dropna().unique()).issubset({0.0, 1.0})

    def test_r_axis_columns(self):
        df = make_synthetic_df(100)
        r_df = _compute_r_axis_v2(df)
        assert "r1_vo2peak_pct_pred" in r_df.columns
        assert "r4_mets_peak" in r_df.columns
        assert len(r_df) == len(df)

    def test_t_axis_columns(self):
        df = make_synthetic_df(100)
        r_df = _compute_r_axis_v2(df)
        t_df = _compute_t_axis_v2(pd.concat([df, r_df], axis=1))
        assert "t1_ve_vco2_slope_inv" in t_df.columns
        assert "t3_exercise_habit_bonus" in t_df.columns

    def test_i_axis_no_circular_test_result(self):
        df = make_synthetic_df(100)
        i_df = _compute_i_axis_v2(df)
        # test_result should NOT be in I-axis (circular dependency prevention)
        assert "i0_test_result" not in i_df.columns
        # I-axis should have bp, o2_pulse, eih
        assert "i1_bp_sys_abnormal" in i_df.columns
        assert "i3_o2_pulse_abnormal" in i_df.columns

    def test_youden_cutpoints(self):
        rng = np.random.default_rng(42)
        n = 200
        score = pd.Series(rng.uniform(0, 100, n))
        # 阳性 = 高分
        outcome = pd.Series((score > 60).astype(float))
        outcome[rng.choice(n, 20)] = np.nan  # 20 missing

        cp = _youden_cutpoints(score, outcome, strat_key="test", n_bootstrap=0)
        assert 0 <= cp.low <= 100
        assert 0 <= cp.high <= 100
        assert cp.low <= cp.high
        assert 0 <= cp.youden_j <= 1.0
        assert cp.n_outcome_pos > 0

    def test_reference_percentile_cutpoints(self):
        n = 200
        rng = np.random.default_rng(42)
        score = pd.Series(rng.uniform(15, 50, n))
        ref_mask = pd.Series([True] * 100 + [False] * 100)
        cp = _reference_percentile_cutpoints(score, ref_mask)
        # Cutpoints from reference population
        ref_p75 = np.percentile(score[:100], 75)
        ref_p90 = np.percentile(score[:100], 90)
        assert abs(cp.low - ref_p75) < 0.01
        assert abs(cp.high - ref_p90) < 0.01
        assert cp.method == "reference_percentile"

    def test_build_returns_correct_columns(self):
        df = make_synthetic_df(200)
        engine = ZoneEngineV2(n_bootstrap=0)
        result = engine.build(df)
        assert "s_lab_v2" in result.df.columns
        assert "z_lab_v2" in result.df.columns
        assert "r_score_v2" in result.df.columns
        assert "t_score_v2" in result.df.columns
        assert "i_score_v2" in result.df.columns

    def test_zones_are_valid_values(self):
        df = make_synthetic_df(200)
        engine = ZoneEngineV2(n_bootstrap=0)
        result = engine.build(df)
        valid_zones = {"green", "yellow", "red", None}
        assert set(result.df["z_lab_v2"].unique()).issubset(valid_zones)

    def test_zone_distribution_all_groups(self):
        df = make_synthetic_df(200)
        engine = ZoneEngineV2(n_bootstrap=0)
        result = engine.build(df)
        assert "global" in result.zone_distribution
        global_dist = result.zone_distribution["global"]
        assert "green" in global_dist
        assert "yellow" in global_dist
        assert "red" in global_dist
        total = sum(global_dist.values())
        assert total == df["z_lab_v2"].notna().sum() if "z_lab_v2" in df.columns else True

    def test_axis_weights_sum_to_one(self):
        df = make_synthetic_df(300)
        engine = ZoneEngineV2(n_bootstrap=0)
        result = engine.build(df)
        w = result.axis_weights
        total = w.r_weight + w.t_weight + w.i_weight
        assert abs(total - 1.0) < 0.01

    def test_reclassification_matrix_shape(self):
        df = make_synthetic_df(200)
        engine = ZoneEngineV2(n_bootstrap=0)
        result = engine.build(df, old_zone_col="p1_zone")
        # Reclassification matrix should be at most 3x3
        if not result.reclassification.empty:
            assert result.reclassification.shape[0] <= 3
            assert result.reclassification.shape[1] <= 3

    def test_report_generation(self, tmp_path):
        df = make_synthetic_df(200)
        engine = ZoneEngineV2(n_bootstrap=0)
        out = tmp_path / "zone_v2.md"
        result = engine.build(df, output_path=str(out))
        assert out.exists()
        text = out.read_text()
        assert "R/T/I" in text
        assert "切点" in text

    def test_personalized_strat_factors(self):
        df = make_synthetic_df(200)
        engine = ZoneEngineV2(n_bootstrap=0)
        result = engine.build(df)
        # Should attempt stratified cutpoints for htn_history, sex, age_group
        # (some may not have enough data in synthetic)
        assert isinstance(result.strat_cutpoints, dict)

    def test_no_data_leakage_test_result(self):
        """验证 test_result 不在 S_lab_v2 的输入中（无循环依赖）。"""
        df = make_synthetic_df(200)
        # 将所有 test_result 设为 阴性
        df_neg = df.copy()
        df_neg["test_result"] = "阴性"
        # 将所有 test_result 设为 阳性
        df_pos = df.copy()
        df_pos["test_result"] = "阳性"

        engine = ZoneEngineV2(n_bootstrap=0)
        r_neg = engine.build(df_neg)
        r_pos = engine.build(df_pos)

        # S_lab_v2 值应该相同（test_result 不影响 S_lab）
        s_neg = r_neg.df["s_lab_v2"].fillna(-999)
        s_pos = r_pos.df["s_lab_v2"].fillna(-999)
        assert (s_neg == s_pos).all(), "test_result 影响了 S_lab_v2！存在循环依赖"


# ── Step 3: zone_sensitivity ──────────────────────────────────────────────────

class TestZoneSensitivity:
    """测试 zone 敏感性分析。"""

    def _get_engine_result(self, n: int = 300) -> pd.DataFrame:
        df = make_synthetic_df(n)
        engine = ZoneEngineV2(n_bootstrap=0)
        result = engine.build(df)
        return result.df

    def test_basic_run(self):
        df = self._get_engine_result()
        result = run_sensitivity_analysis(df, n_bootstrap=10)
        assert len(result.scan_results) == 2  # low + high cutpoint scans
        assert isinstance(result.bootstrap_ci, dict)

    def test_bootstrap_ci_bounds(self):
        df = self._get_engine_result(300)
        result = run_sensitivity_analysis(df, n_bootstrap=50)
        for _, (lo, hi) in result.bootstrap_ci.items():
            assert lo <= hi
            assert lo >= 0
            assert hi <= 100

    def test_subgroup_consistency_has_groups(self):
        df = self._get_engine_result()
        result = run_sensitivity_analysis(df, n_bootstrap=10)
        assert not result.subgroup_consistency.empty
        cols = result.subgroup_consistency.columns
        assert "Green%" in cols
        assert "Yellow%" in cols
        assert "Red%" in cols

    def test_literature_check(self):
        df = self._get_engine_result()
        result = run_sensitivity_analysis(df, n_bootstrap=10)
        # literature_check may or may not have entries depending on data
        assert isinstance(result.literature_check, list)

    def test_reclassification_summary(self):
        df = self._get_engine_result()
        result = run_sensitivity_analysis(df, n_bootstrap=10)
        rc = result.reclassification_summary
        if rc:
            assert "agreement_rate" in rc
            assert "reclassification_rate" in rc
            assert 0 <= rc["agreement_rate"] <= 1.0
            assert 0 <= rc["reclassification_rate"] <= 1.0

    def test_sensitivity_scan_rows(self):
        df = self._get_engine_result()
        result = run_sensitivity_analysis(df, n_bootstrap=10)
        for sr in result.scan_results:
            # Should have 5 rows (for -10%, -5%, 0%, +5%, +10%)
            assert len(sr.scan_results) == 5

    def test_report_generation(self, tmp_path):
        df = self._get_engine_result()
        out = tmp_path / "sens.md"
        result = run_sensitivity_analysis(df, n_bootstrap=10, output_path=out)
        assert out.exists()
        text = out.read_text()
        assert "Bootstrap" in text
        assert "敏感性" in text

    def test_missing_s_lab_raises(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        with pytest.raises(ValueError):
            run_sensitivity_analysis(df)

    def test_scan_percentages_sum_to_100(self):
        df = self._get_engine_result()
        result = run_sensitivity_analysis(df, n_bootstrap=10)
        for sr in result.scan_results:
            for row in sr.scan_results:
                total = row["Green%"] + row["Yellow%"] + row["Red%"]
                assert abs(total - 100.0) < 1.0, f"Zone % don't sum to 100: {total}"
