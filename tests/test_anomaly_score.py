"""
test_anomaly_score.py — Phase G Method 2 单元测试

覆盖：
- anomaly_score.py: fit_anomaly_model, compute_anomaly_scores, run_anomaly_scoring
- AnomalyModelParams, AnomalyScoreResult
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.stats.anomaly_score import (
    AnomalyModelParams,
    AnomalyScoreResult,
    _compute_mahal_d2_batch,
    _select_valid_variables,
    fit_anomaly_model,
    compute_anomaly_scores,
    run_anomaly_scoring,
)


# ── 合成数据工厂 ──────────────────────────────────────────────────────────────

def make_reference_df(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """生成参考人群 DataFrame（正常分布）。"""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "subject_id": [f"R{i:04d}" for i in range(n)],
        "vo2_peak": rng.normal(25, 4, n),
        "hr_peak": rng.normal(150, 15, n),
        "o2_pulse_peak": rng.normal(14, 3, n),
        "oues": rng.normal(2.5, 0.4, n),
        "mets_peak": rng.normal(7, 1.5, n),
        "group_code": "CTRL",
        "reference_flag_wide": True,
    })


def make_full_df(n_ref: int = 100, n_patients: int = 200, seed: int = 42) -> pd.DataFrame:
    """生成完整 DataFrame（参考 + 患者）。"""
    rng = np.random.default_rng(seed)
    df_ref = make_reference_df(n_ref, seed)

    # 患者：部分正常（预期低 D²），部分异常（预期高 D²）
    n_normal = n_patients // 2
    n_abnormal = n_patients - n_normal

    df_normal = pd.DataFrame({
        "subject_id": [f"PN{i:04d}" for i in range(n_normal)],
        "vo2_peak": rng.normal(24, 4, n_normal),
        "hr_peak": rng.normal(148, 15, n_normal),
        "o2_pulse_peak": rng.normal(13, 3, n_normal),
        "oues": rng.normal(2.4, 0.4, n_normal),
        "mets_peak": rng.normal(6.8, 1.5, n_normal),
        "group_code": "HTN_HISTORY_NO_EHT",
        "reference_flag_wide": False,
        "test_result": "阴性",
    })

    df_abnormal = pd.DataFrame({
        "subject_id": [f"PA{i:04d}" for i in range(n_abnormal)],
        "vo2_peak": rng.normal(13, 3, n_abnormal),     # 明显低
        "hr_peak": rng.normal(165, 20, n_abnormal),    # 偏高（变时不全）
        "o2_pulse_peak": rng.normal(7, 2, n_abnormal), # 低
        "oues": rng.normal(1.5, 0.3, n_abnormal),      # 低
        "mets_peak": rng.normal(3.5, 1, n_abnormal),   # 低
        "group_code": "HTN_HISTORY_WITH_EHT",
        "reference_flag_wide": False,
        "test_result": rng.choice(["阳性", "可疑阳性", "阴性"], n_abnormal, p=[0.3, 0.2, 0.5]),
    })

    df = pd.concat([df_ref, df_normal, df_abnormal], ignore_index=True)
    return df


# ── TestMahalanobisD2 ─────────────────────────────────────────────────────────

class TestMahalanobisD2:
    """测试 Mahalanobis 距离计算。"""

    def test_zero_distance_at_mean(self):
        """均值处的 D² 应为 0。"""
        mu = np.array([25.0, 150.0, 14.0])
        Sigma_inv = np.eye(3)
        X = mu.reshape(1, -1)
        d2 = _compute_mahal_d2_batch(X, mu, Sigma_inv)
        assert abs(d2[0]) < 1e-10

    def test_positive_distance(self):
        """偏离均值的点 D² 应 > 0。"""
        mu = np.array([25.0, 150.0])
        Sigma_inv = np.eye(2)
        X = np.array([[30.0, 160.0]])
        d2 = _compute_mahal_d2_batch(X, mu, Sigma_inv)
        assert d2[0] > 0

    def test_correlation_structure(self):
        """正相关变量中，沿相关方向偏离的 D² 应小于反相关方向偏离。"""
        # 构建正相关协方差
        Sigma = np.array([[4.0, 3.0], [3.0, 4.0]])
        Sigma_inv = np.linalg.inv(Sigma)
        mu = np.zeros(2)
        # 沿正相关方向偏离（(1,1)方向）
        X_correlated = np.array([[2.0, 2.0]])
        # 沿反相关方向偏离（(1,-1)方向）
        X_anticorrelated = np.array([[2.0, -2.0]])
        d2_corr = _compute_mahal_d2_batch(X_correlated, mu, Sigma_inv)
        d2_anti = _compute_mahal_d2_batch(X_anticorrelated, mu, Sigma_inv)
        # 反相关方向偏离应获得更高 D²（更"异常"）
        assert d2_anti[0] > d2_corr[0]


# ── TestFitAnomalyModel ───────────────────────────────────────────────────────

class TestFitAnomalyModel:
    """测试模型拟合。"""

    def test_fit_basic(self):
        """基本拟合：返回 AnomalyModelParams。"""
        df_ref = make_reference_df(n=80)
        params = fit_anomaly_model(df_ref)
        assert isinstance(params, AnomalyModelParams)
        assert len(params.variable_names) >= 2
        assert params.n_reference == 80

    def test_percentile_cutpoints(self):
        """拟合后 P75/P95 切点有效且 P75 < P95。"""
        df_ref = make_reference_df(n=80)
        params = fit_anomaly_model(df_ref)
        assert not np.isnan(params.d2_p75_ref)
        assert not np.isnan(params.d2_p95_ref)
        assert params.d2_p75_ref < params.d2_p95_ref

    def test_chi2_theoretical_cutpoints(self):
        """χ² 理论切点有效（5个变量时 P75>0, P95>P75）。"""
        df_ref = make_reference_df(n=80)
        params = fit_anomaly_model(df_ref)
        assert params.d2_chi2_p75 > 0
        assert params.d2_chi2_p95 > params.d2_chi2_p75

    def test_insufficient_samples(self):
        """参考样本量不足时应抛出 ValueError。"""
        df_ref = make_reference_df(n=5)  # 远少于最小要求
        with pytest.raises(ValueError):
            fit_anomaly_model(df_ref)

    def test_select_valid_variables(self):
        """高缺失率变量应被排除。"""
        df = make_reference_df(n=60)
        df["high_missing"] = np.nan  # 100% 缺失
        valid = _select_valid_variables(df, ["vo2_peak", "high_missing"])
        assert "high_missing" not in valid
        assert "vo2_peak" in valid


# ── TestComputeAnomalyScores ──────────────────────────────────────────────────

class TestComputeAnomalyScores:
    """测试异常评分计算。"""

    @pytest.fixture
    def params_and_df(self):
        df_full = make_full_df(n_ref=80, n_patients=120)
        df_ref = df_full[df_full["reference_flag_wide"].astype(bool)]
        params = fit_anomaly_model(df_ref)
        return params, df_full

    def test_scores_shape(self, params_and_df):
        """评分 DataFrame 行数应等于输入行数。"""
        params, df_full = params_and_df
        result = compute_anomaly_scores(df_full, params)
        assert len(result.scores) == len(df_full)

    def test_scores_has_required_columns(self, params_and_df):
        """评分结果应包含必要列。"""
        params, df_full = params_and_df
        result = compute_anomaly_scores(df_full, params)
        assert "mahal_d2" in result.scores.columns
        assert "mahal_pvalue" in result.scores.columns
        assert "anomaly_zone" in result.scores.columns

    def test_d2_nonnegative(self, params_and_df):
        """D² 值应非负。"""
        params, df_full = params_and_df
        result = compute_anomaly_scores(df_full, params)
        assert (result.scores["mahal_d2"] >= 0).all()

    def test_pvalue_in_01(self, params_and_df):
        """p 值应在 [0, 1] 范围内。"""
        params, df_full = params_and_df
        result = compute_anomaly_scores(df_full, params)
        pvals = result.scores["mahal_pvalue"]
        assert (pvals >= 0).all() and (pvals <= 1).all()

    def test_zone_values(self, params_and_df):
        """安全区值应为 green/yellow/red。"""
        params, df_full = params_and_df
        result = compute_anomaly_scores(df_full, params)
        valid_zones = {"green", "yellow", "red"}
        assert set(result.scores["anomaly_zone"].unique()).issubset(valid_zones)

    def test_abnormal_patients_higher_d2(self, params_and_df):
        """异常患者（人工生成）的平均 D² 应高于正常患者。"""
        params, df_full = params_and_df
        result = compute_anomaly_scores(df_full, params)
        scores_with_group = df_full[["group_code"]].join(result.scores["mahal_d2"])
        d2_normal = scores_with_group.loc[
            scores_with_group["group_code"] == "HTN_HISTORY_NO_EHT", "mahal_d2"
        ].mean()
        d2_abnormal = scores_with_group.loc[
            scores_with_group["group_code"] == "HTN_HISTORY_WITH_EHT", "mahal_d2"
        ].mean()
        # 异常患者 D² 应显著更高
        assert d2_abnormal > d2_normal

    def test_zone_distribution(self, params_and_df):
        """安全区分布应存在且百分比之和约 100。"""
        params, df_full = params_and_df
        result = compute_anomaly_scores(df_full, params)
        total_pct = sum(
            result.zone_distribution.get(z, {}).get("pct", 0)
            for z in ["green", "yellow", "red"]
        )
        assert abs(total_pct - 100.0) < 1.0


# ── TestRunAnomalyScoring ─────────────────────────────────────────────────────

class TestRunAnomalyScoring:
    """测试端到端管线。"""

    def test_run_without_config(self):
        """无配置文件时应使用默认配置成功运行。"""
        df = make_full_df(n_ref=60, n_patients=100)
        result = run_anomaly_scoring(
            df,
            config_path="nonexistent_config.yaml",
            reference_flag_col="reference_flag_wide",
        )
        assert isinstance(result, AnomalyScoreResult)
        assert len(result.scores) == len(df)

    def test_correlation_with_outcome(self):
        """提供 test_result 时应计算相关性。"""
        df = make_full_df(n_ref=60, n_patients=100)
        result = run_anomaly_scoring(
            df,
            config_path="nonexistent_config.yaml",
            reference_flag_col="reference_flag_wide",
            outcome_col="test_result",
        )
        assert result.correlation_with_outcome is not None
        assert -1.0 <= result.correlation_with_outcome <= 1.0

    def test_fallback_when_ref_col_missing(self):
        """参考标志列不存在时应使用 group_code=CTRL 兜底。"""
        df = make_full_df(n_ref=60, n_patients=100)
        df_no_ref = df.drop(columns=["reference_flag_wide"])
        result = run_anomaly_scoring(
            df_no_ref,
            config_path="nonexistent_config.yaml",
            reference_flag_col="reference_flag_wide",
        )
        assert isinstance(result, AnomalyScoreResult)
