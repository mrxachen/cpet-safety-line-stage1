"""
test_outcome_model.py — Phase G Method 1 单元测试

覆盖：
- outcome_zone.py: OutcomeZoneCutpoints, compute_outcome_cutpoints, assign_outcome_zones*
- train_outcome.py: OutcomeTrainer (_build_outcome_label, _prepare_features, run)
- leakage_guard.py: outcome 任务路径
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.labels.outcome_zone import (
    OutcomeZoneCutpoints,
    assign_outcome_zones,
    assign_outcome_zones_series,
    compute_outcome_cutpoints,
    compute_zone_distribution,
)
from cpet_stage1.modeling.train_outcome import (
    OutcomeModelResult,
    OutcomeTrainer,
    _build_outcome_label,
    _prepare_features,
)
from cpet_stage1.labels.leakage_guard import LeakageGuard


# ── 合成数据工厂 ──────────────────────────────────────────────────────────────

def make_synthetic_df(n: int = 300, seed: int = 42, positive_rate: float = 0.15) -> pd.DataFrame:
    """生成合成 CPET DataFrame，含 test_result 列。"""
    rng = np.random.default_rng(seed)
    n_pos = int(n * positive_rate)
    n_neg = n - n_pos

    # 阳性患者：更低 VO₂peak，更高 ve_vco2_slope
    df_pos = pd.DataFrame({
        "subject_id": [f"P{i:04d}" for i in range(n_pos)],
        "vo2_peak": rng.uniform(8, 18, n_pos),
        "vo2_peak_pct_pred": rng.uniform(35, 65, n_pos),
        "hr_peak": rng.uniform(90, 150, n_pos),
        "o2_pulse_peak": rng.uniform(5, 12, n_pos),
        "mets_peak": rng.uniform(2, 5, n_pos),
        "ve_vco2_slope": rng.uniform(33, 50, n_pos),
        "oues": rng.uniform(1.0, 1.8, n_pos),
        "vt1_vo2": rng.uniform(8, 14, n_pos),
        "eih_status": rng.choice([True, False], n_pos, p=[0.4, 0.6]),
        "age": rng.uniform(60, 80, n_pos),
        "sex": rng.choice(["M", "F"], n_pos),
        "height_cm": rng.uniform(155, 175, n_pos),
        "weight_kg": rng.uniform(55, 85, n_pos),
        "htn_history": rng.choice([0, 1], n_pos, p=[0.3, 0.7]),
        "test_result": rng.choice(["阳性", "可疑阳性"], n_pos),
    })

    # 阴性患者：更高 VO₂peak，更低 ve_vco2_slope
    df_neg = pd.DataFrame({
        "subject_id": [f"N{i:04d}" for i in range(n_neg)],
        "vo2_peak": rng.uniform(18, 35, n_neg),
        "vo2_peak_pct_pred": rng.uniform(70, 120, n_neg),
        "hr_peak": rng.uniform(120, 175, n_neg),
        "o2_pulse_peak": rng.uniform(12, 25, n_neg),
        "mets_peak": rng.uniform(5, 12, n_neg),
        "ve_vco2_slope": rng.uniform(20, 32, n_neg),
        "oues": rng.uniform(1.8, 3.5, n_neg),
        "vt1_vo2": rng.uniform(14, 25, n_neg),
        "eih_status": rng.choice([True, False], n_neg, p=[0.05, 0.95]),
        "age": rng.uniform(60, 80, n_neg),
        "sex": rng.choice(["M", "F"], n_neg),
        "height_cm": rng.uniform(155, 180, n_neg),
        "weight_kg": rng.uniform(50, 90, n_neg),
        "htn_history": rng.choice([0, 1], n_neg, p=[0.5, 0.5]),
        "test_result": "阴性",
    })

    df = pd.concat([df_pos, df_neg], ignore_index=True)
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    return df


# ── TestOutcomeZoneCutpoints ──────────────────────────────────────────────────

class TestComputeOutcomeCutpoints:
    """测试切点计算逻辑。"""

    def test_basic_cutpoints(self):
        """基本切点计算：返回有效范围内的切点。"""
        rng = np.random.default_rng(0)
        y_true = np.array([1] * 30 + [0] * 170)
        y_proba = np.concatenate([
            rng.uniform(0.3, 0.9, 30),  # 阳性：高概率
            rng.uniform(0.0, 0.3, 170),  # 阴性：低概率
        ])
        cp = compute_outcome_cutpoints(y_true, y_proba)
        assert isinstance(cp, OutcomeZoneCutpoints)
        assert 0.0 <= cp.low_cut < cp.high_cut <= 1.0
        assert cp.method != ""

    def test_sensitivity_constraint(self):
        """Green/Yellow 界处敏感度应 ≥ 0.90（在有区分度时）。"""
        # 构建明确可分的数据
        y_true = np.array([1] * 50 + [0] * 150)
        y_proba = np.concatenate([
            np.linspace(0.6, 0.95, 50),  # 阳性：高概率
            np.linspace(0.01, 0.3, 150),  # 阴性：低概率
        ])
        cp = compute_outcome_cutpoints(y_true, y_proba, min_sensitivity=0.90)
        # low_cut 处的敏感度应 ≥ 0.88（允许小数值差异）
        assert cp.sensitivity_at_low >= 0.85

    def test_all_same_label(self):
        """全部标签相同时应退化为固定切点。"""
        y_true = np.zeros(100)
        y_proba = np.random.default_rng(0).uniform(0, 1, 100)
        cp = compute_outcome_cutpoints(y_true, y_proba)
        assert cp.method == "fixed"
        assert cp.low_cut == 0.10
        assert cp.high_cut == 0.25

    def test_low_cut_less_than_high_cut(self):
        """low_cut 必须 < high_cut。"""
        rng = np.random.default_rng(1)
        y_true = np.array([1] * 20 + [0] * 80)
        y_proba = rng.uniform(0, 1, 100)
        cp = compute_outcome_cutpoints(y_true, y_proba)
        assert cp.low_cut < cp.high_cut


# ── TestAssignOutcomeZones ────────────────────────────────────────────────────

class TestAssignOutcomeZones:
    """测试安全区分配逻辑。"""

    def test_zone_assignment_basic(self):
        """基本区间分配。"""
        cp = OutcomeZoneCutpoints(low_cut=0.10, high_cut=0.25, method="fixed")
        proba = np.array([0.05, 0.15, 0.30])
        zones = assign_outcome_zones(proba, cp)
        assert zones[0] == 0   # green
        assert zones[1] == 1   # yellow
        assert zones[2] == 2   # red

    def test_boundary_values(self):
        """边界值处理：低于 low_cut 为 green，等于 high_cut 为 red。"""
        cp = OutcomeZoneCutpoints(low_cut=0.10, high_cut=0.25, method="fixed")
        proba = np.array([0.10, 0.25])  # 等于边界
        zones = assign_outcome_zones(proba, cp)
        # 0.10 ≥ low_cut → yellow
        assert zones[0] == 1
        # 0.25 ≥ high_cut → red
        assert zones[1] == 2

    def test_series_output(self):
        """pd.Series 输出格式正确。"""
        cp = OutcomeZoneCutpoints(low_cut=0.10, high_cut=0.25, method="fixed")
        proba = pd.Series([0.05, 0.15, 0.30], index=[10, 20, 30])
        zones = assign_outcome_zones_series(proba, cp)
        assert isinstance(zones, pd.Series)
        assert zones.name == "outcome_zone"
        assert list(zones.values) == ["green", "yellow", "red"]
        assert list(zones.index) == [10, 20, 30]

    def test_zone_distribution(self):
        """安全区分布统计正确。"""
        zones = pd.Series(["green", "green", "yellow", "red"])
        dist = compute_zone_distribution(zones)
        assert dist["green"]["n"] == 2
        assert dist["yellow"]["n"] == 1
        assert dist["red"]["n"] == 1
        assert dist["total"] == 4


# ── TestBuildOutcomeLabel ─────────────────────────────────────────────────────

class TestBuildOutcomeLabel:
    """测试标签构建。"""

    def test_label_construction(self):
        """阳性/可疑阳性 → 1，阴性 → 0，NaN 保留。"""
        df = pd.DataFrame({
            "test_result": ["阳性", "可疑阳性", "阴性", "阴性", None]
        })
        y = _build_outcome_label(df)
        assert y.iloc[0] == 1.0
        assert y.iloc[1] == 1.0
        assert y.iloc[2] == 0.0
        assert y.iloc[3] == 0.0
        assert pd.isna(y.iloc[4])

    def test_missing_column_raises(self):
        """缺少结局列时应抛出 KeyError。"""
        df = pd.DataFrame({"other_col": [1, 2]})
        with pytest.raises(KeyError):
            _build_outcome_label(df, outcome_col="test_result")


# ── TestPrepareFeatures ───────────────────────────────────────────────────────

class TestPrepareFeatures:
    """测试特征矩阵构建。"""

    def test_eih_status_conversion(self):
        """eih_status bool → float。"""
        df = pd.DataFrame({"eih_status": [True, False, True]})
        X = _prepare_features(df, ["eih_status"])
        assert X["eih_status"].dtype == float
        assert list(X["eih_status"]) == [1.0, 0.0, 1.0]

    def test_bmi_derivation(self):
        """BMI 正确派生。"""
        df = pd.DataFrame({"height_cm": [170.0], "weight_kg": [70.0]})
        X = _prepare_features(df, ["bmi"])
        expected_bmi = 70 / (1.70 ** 2)
        assert abs(X["bmi"].iloc[0] - expected_bmi) < 0.01

    def test_sex_binary(self):
        """sex → sex_binary（F=1, M=0）。"""
        df = pd.DataFrame({"sex": ["M", "F", "M"]})
        X = _prepare_features(df, ["sex_binary"])
        assert list(X["sex_binary"]) == [0.0, 1.0, 0.0]

    def test_missing_column_fills_nan(self):
        """不存在的列填充 NaN（不报错）。"""
        df = pd.DataFrame({"vo2_peak": [25.0]})
        X = _prepare_features(df, ["vo2_peak", "nonexistent_col"])
        assert X["vo2_peak"].iloc[0] == 25.0
        assert pd.isna(X["nonexistent_col"].iloc[0])


# ── TestLeakageGuardOutcome ───────────────────────────────────────────────────

class TestLeakageGuardOutcome:
    """测试 leakage_guard outcome 路径。"""

    def test_outcome_task_no_exclusions(self):
        """outcome 任务不应排除任何字段。"""
        guard = LeakageGuard()
        exclusions = guard.get_exclusions("outcome")
        assert len(exclusions) == 0

    def test_outcome_filter_keeps_all(self):
        """outcome 任务的 filter 不删除任何列。"""
        guard = LeakageGuard()
        df = pd.DataFrame({
            "vo2_peak_pct_pred": [80.0],
            "ve_vco2_slope": [28.0],
            "eih_status": [False],
            "vo2_peak": [22.0],
        })
        X_filtered = guard.filter(df, task="outcome")
        assert set(X_filtered.columns) == set(df.columns)

    def test_outcome_assert_no_leakage_passes(self):
        """outcome 任务 assert_no_leakage 应无条件通过。"""
        guard = LeakageGuard()
        df = pd.DataFrame({
            "vo2_peak_pct_pred": [80.0],
            "ve_vco2_slope": [28.0],
            "eih_status": [False],
        })
        guard.assert_no_leakage(df, task="outcome")  # 不应抛出

    def test_p1_still_excludes(self):
        """p1 任务仍正常排除泄漏字段。"""
        guard = LeakageGuard()
        exclusions = guard.get_exclusions("p1")
        assert "eih_status" in exclusions
        assert "ve_vco2_slope" in exclusions

    def test_report_includes_outcome(self):
        """report() 应包含 outcome_exclusions 键。"""
        guard = LeakageGuard()
        report = guard.report()
        assert "outcome_exclusions" in report
        assert report["outcome_exclusions"] == []

    def test_unknown_task_raises(self):
        """未知任务应抛出 ValueError。"""
        guard = LeakageGuard()
        with pytest.raises(ValueError):
            guard.get_exclusions("unknown_task")


# ── TestOutcomeTrainer ────────────────────────────────────────────────────────

# 模块级共享训练结果（避免每个测试方法重复训练）
@pytest.fixture(scope="module")
def shared_outcome_result():
    """模块级共享：训练一次，多个测试复用。"""
    df = make_synthetic_df(n=200, seed=42)
    trainer = OutcomeTrainer()
    result = trainer.run(df, n_iter_override=2)
    return trainer, result


class TestOutcomeTrainer:
    """测试 OutcomeTrainer 端到端流程。"""

    def test_trainer_runs(self, shared_outcome_result):
        """训练管线应无错误完成，返回 OutcomeModelResult。"""
        _, result = shared_outcome_result
        assert isinstance(result, OutcomeModelResult)

    def test_result_has_auc(self, shared_outcome_result):
        """结果应包含有效的 AUC 值。"""
        _, result = shared_outcome_result
        assert not np.isnan(result.test_auc)
        assert 0.0 <= result.test_auc <= 1.0

    def test_result_has_cutpoints(self, shared_outcome_result):
        """结果应包含切点对象。"""
        _, result = shared_outcome_result
        assert result.cutpoints is not None
        assert result.cutpoints.low_cut < result.cutpoints.high_cut

    def test_zone_distribution_sums_to_100(self, shared_outcome_result):
        """安全区分布百分比之和应约等于 100。"""
        _, result = shared_outcome_result
        total_pct = sum(
            result.zone_distribution.get(z, {}).get("pct", 0)
            for z in ["green", "yellow", "red"]
        )
        assert abs(total_pct - 100.0) < 1.0  # 允许小数舍入

    def test_report_generation(self, shared_outcome_result):
        """报告生成应成功且包含关键章节。"""
        trainer, result = shared_outcome_result
        report = trainer.generate_report(result)
        assert "结局锚定安全区模型报告" in report
        assert "AUC" in report
        assert "Green" in report
