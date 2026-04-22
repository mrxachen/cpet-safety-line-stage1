"""
tests/stats/test_outcome_anchor.py — Outcome-Anchor 验证模型 + Anomaly Audit 测试。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.modeling.train_outcome_anchor import (
    OutcomeAnchorResult,
    _build_label,
    _prepare_features,
    generate_outcome_anchor_report,
    run_outcome_anchor,
)
from cpet_stage1.stats.anomaly_audit import (
    AnomalyAuditResult,
    generate_anomaly_audit_report,
    run_anomaly_audit,
)


# ─────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────

def _make_cpet_df(n: int = 200, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "vo2_peak": rng.uniform(10, 35, n),
        "ve_vco2_slope": rng.uniform(22, 45, n),
        "oues": rng.uniform(500, 2800, n),
        "o2_pulse_peak": rng.uniform(5, 20, n),
        "mets_peak": rng.uniform(2, 14, n),
        "vt1_vo2": rng.uniform(8, 25, n),
        "hr_peak_pct_pred": rng.uniform(60, 105, n),
        "eih_status": rng.choice([False, True], n, p=[0.85, 0.15]),
        "age": rng.uniform(45, 80, n),
        "bmi": rng.uniform(18, 35, n),
        "htn_history": rng.choice([False, True], n),
        "bp_peak_sys": rng.uniform(140, 230, n),
        "test_result": rng.choice(["阴性", "阳性"], n, p=[0.8, 0.2]),
    })
    return df


# ─────────────────────────────────────────────────────
# _build_label 测试
# ─────────────────────────────────────────────────────

class TestBuildLabel:

    def test_chinese_positive(self):
        df = pd.DataFrame({"test_result": ["阳性", "阴性", "可疑阳性"]})
        y = _build_label(df)
        assert list(y) == [1, 0, 1]

    def test_missing_column_raises(self):
        df = pd.DataFrame({"other": [1]})
        with pytest.raises(KeyError):
            _build_label(df)

    def test_label_is_binary(self):
        df = _make_cpet_df()
        y = _build_label(df)
        assert set(y.unique()).issubset({0, 1})


# ─────────────────────────────────────────────────────
# _prepare_features 测试
# ─────────────────────────────────────────────────────

class TestPrepareFeatures:

    def test_no_nan_after_imputation(self):
        df = _make_cpet_df()
        df.loc[df.index[:10], "vo2_peak"] = np.nan
        X = _prepare_features(df, ["vo2_peak", "ve_vco2_slope"])
        assert X.isna().sum().sum() == 0

    def test_eih_status_converted(self):
        df = pd.DataFrame({"eih_status": [True, False, True]})
        X = _prepare_features(df, ["eih_status"])
        assert X["eih_status"].dtype in [float, np.float64, int, np.int64]


# ─────────────────────────────────────────────────────
# run_outcome_anchor 测试
# ─────────────────────────────────────────────────────

class TestRunOutcomeAnchor:

    def test_returns_result_object(self):
        df = _make_cpet_df()
        result = run_outcome_anchor(df)
        assert isinstance(result, OutcomeAnchorResult)

    def test_auc_is_reasonable(self):
        """AUC 应在 0-1 范围内。"""
        df = _make_cpet_df(n=300)
        result = run_outcome_anchor(df)
        if not np.isnan(result.test_auc):
            assert 0.0 <= result.test_auc <= 1.0

    def test_predictions_df_has_right_cols(self):
        df = _make_cpet_df(n=300)
        result = run_outcome_anchor(df)
        if result.predictions_df is not None:
            assert "outcome_risk_prob" in result.predictions_df.columns
            assert "outcome_risk_tertile" in result.predictions_df.columns

    def test_outcome_risk_tertile_values(self):
        """tertile 应为 low/mid/high。"""
        df = _make_cpet_df(n=300)
        result = run_outcome_anchor(df)
        if result.predictions_df is not None:
            tertile = result.predictions_df["outcome_risk_tertile"].dropna()
            assert set(tertile.unique()).issubset({"low", "mid", "high"})

    def test_missing_outcome_col_returns_empty(self):
        df = _make_cpet_df()
        df = df.drop(columns=["test_result"])
        result = run_outcome_anchor(df)
        assert isinstance(result, OutcomeAnchorResult)

    def test_too_small_returns_gracefully(self):
        df = _make_cpet_df(n=10)
        result = run_outcome_anchor(df)
        assert isinstance(result, OutcomeAnchorResult)

    def test_cv_auc_populated(self):
        df = _make_cpet_df(n=300)
        result = run_outcome_anchor(df, n_splits=3)
        if not np.isnan(result.cv_auc_mean):
            assert 0.0 <= result.cv_auc_mean <= 1.0


# ─────────────────────────────────────────────────────
# generate_outcome_anchor_report 测试
# ─────────────────────────────────────────────────────

class TestOutcomeAnchorReport:

    def test_report_is_string(self):
        df = _make_cpet_df(n=200)
        result = run_outcome_anchor(df)
        report = generate_outcome_anchor_report(result)
        assert isinstance(report, str)

    def test_report_saved_to_file(self, tmp_path):
        df = _make_cpet_df(n=200)
        result = run_outcome_anchor(df)
        out = tmp_path / "report.md"
        generate_outcome_anchor_report(result, output_path=out)
        assert out.exists()


# ─────────────────────────────────────────────────────
# run_anomaly_audit 测试
# ─────────────────────────────────────────────────────

class TestRunAnomalyAudit:

    def test_returns_result_object(self):
        df = _make_cpet_df()
        result = run_anomaly_audit(df)
        assert isinstance(result, AnomalyAuditResult)

    def test_anomaly_flag_is_bool(self):
        df = _make_cpet_df()
        result = run_anomaly_audit(df)
        assert result.scores["anomaly_flag"].dtype == bool

    def test_anomaly_score_non_negative(self):
        df = _make_cpet_df()
        result = run_anomaly_audit(df)
        valid_scores = result.scores["anomaly_score"].dropna()
        assert (valid_scores >= 0).all()

    def test_anomaly_flag_pct_reasonable(self):
        """anomaly_flag 比例应在 0-50% 之间（不应全是异常）。"""
        df = _make_cpet_df(n=300)
        result = run_anomaly_audit(df)
        pct = result.n_anomaly / len(df)
        assert 0.0 <= pct <= 0.50

    def test_with_reference_mask(self):
        df = _make_cpet_df(n=200)
        ref_mask = pd.Series([True] * 100 + [False] * 100, index=df.index)
        result = run_anomaly_audit(df, reference_mask=ref_mask)
        assert result.n_reference == 100 or result.n_reference <= 100

    def test_with_known_outlier(self):
        """插入极端值应触发 anomaly_flag。"""
        df = _make_cpet_df(n=200)
        df.loc[df.index[0], "vo2_peak"] = 9999.0   # 极端异常值
        result = run_anomaly_audit(df)
        # index 0 应被标记（或至少分数最高）
        if not result.scores["anomaly_score"].isna().iloc[0]:
            assert result.scores.loc[df.index[0], "anomaly_score"] == result.scores["anomaly_score"].max()

    def test_too_few_variables_returns_gracefully(self):
        df = pd.DataFrame({"only_one": [1, 2, 3]})
        result = run_anomaly_audit(df, variables=["only_one"])
        assert isinstance(result, AnomalyAuditResult)

    def test_missing_reference_too_small_returns_gracefully(self):
        df = _make_cpet_df(n=200)
        ref_mask = pd.Series([True] * 5 + [False] * 195, index=df.index)
        result = run_anomaly_audit(df, reference_mask=ref_mask, min_reference_n=50)
        assert isinstance(result, AnomalyAuditResult)


# ─────────────────────────────────────────────────────
# generate_anomaly_audit_report 测试
# ─────────────────────────────────────────────────────

class TestAnomalyAuditReport:

    def test_report_is_string(self):
        df = _make_cpet_df()
        result = run_anomaly_audit(df)
        report = generate_anomaly_audit_report(result)
        assert isinstance(report, str)

    def test_report_saved_to_file(self, tmp_path):
        df = _make_cpet_df()
        result = run_anomaly_audit(df)
        out = tmp_path / "anomaly_audit.md"
        generate_anomaly_audit_report(result, output_path=out)
        assert out.exists()

    def test_report_contains_threshold(self):
        df = _make_cpet_df()
        result = run_anomaly_audit(df)
        report = generate_anomaly_audit_report(result)
        assert "阈值" in report
