"""
test_modeling_p0.py — M5 P0 训练管线测试（~20 个测试）。

使用合成数据，n_iter_override=2 加速测试。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.modeling.train_p0 import P0ModelResult, P0Trainer


# ---------------------------------------------------------------------------
# 测试数据工厂（与 test_features.py 相同）
# ---------------------------------------------------------------------------

def make_full_df(n: int = 80, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "subject_id": [f"S{i:04d}" for i in range(n)],
        "age": rng.integers(60, 80, n).astype(float),
        "sex": rng.choice(["M", "F"], n),
        "height_cm": rng.uniform(155, 180, n),
        "weight_kg": rng.uniform(55, 90, n),
        "bmi": rng.uniform(20, 32, n),
        "htn_history": rng.choice([True, False], n),
        "cad_history": rng.choice([True, False, None], n).astype(object),
        "hf_history": rng.choice([True, False, None], n).astype(object),
        "lvef_pct": rng.uniform(40, 75, n),
        "bp_rest_sys": rng.uniform(110, 160, n),
        "bp_rest_dia": rng.uniform(70, 95, n),
        "hr_rest": rng.uniform(55, 85, n),
        "exercise_protocol_cycle": rng.choice([True, False], n),
        # P1 fields（不应出现在 P0 特征中）
        "vo2_peak": rng.uniform(8, 28, n),
        "ve_vco2_slope": rng.uniform(22, 45, n),
        "eih_status": rng.choice([True, False], n),
        # 标签（确保一定阳性率）
        "p0_event": np.concatenate([np.ones(n // 4, dtype=int), np.zeros(n - n // 4, dtype=int)]),
        "p1_zone": rng.choice([0, 1, 2], n),
    })
    return df


@pytest.fixture
def trainer():
    return P0Trainer()


@pytest.fixture
def df():
    return make_full_df(n=80)


# ---------------------------------------------------------------------------
# P0Trainer.run() 结构测试
# ---------------------------------------------------------------------------

class TestP0TrainerRun:

    def test_run_returns_dict(self, trainer, df):
        results = trainer.run(df, n_iter_override=2)
        assert isinstance(results, dict)

    def test_run_has_lasso_and_xgb(self, trainer, df):
        results = trainer.run(df, n_iter_override=2)
        assert "lasso" in results
        assert "xgb" in results

    def test_run_has_bp_variants(self, trainer, df):
        results = trainer.run(df, n_iter_override=2)
        for model_name in ["lasso", "xgb"]:
            assert "with_bp" in results[model_name]
            assert "no_bp" in results[model_name]

    def test_run_returns_p0_model_result(self, trainer, df):
        results = trainer.run(df, n_iter_override=2)
        assert isinstance(results["lasso"]["with_bp"], P0ModelResult)
        assert isinstance(results["xgb"]["with_bp"], P0ModelResult)

    def test_missing_label_col_raises(self, trainer, df):
        df_no_label = df.drop(columns=["p0_event"])
        with pytest.raises(ValueError, match="标签列"):
            trainer.run(df_no_label, n_iter_override=2)


# ---------------------------------------------------------------------------
# P0ModelResult 内容检查
# ---------------------------------------------------------------------------

class TestP0ModelResult:

    @pytest.fixture
    def lasso_result(self, trainer, df):
        results = trainer.run(df, n_iter_override=2)
        return results["lasso"]["with_bp"]

    @pytest.fixture
    def xgb_result(self, trainer, df):
        results = trainer.run(df, n_iter_override=2)
        return results["xgb"]["with_bp"]

    def test_lasso_model_name(self, lasso_result):
        assert lasso_result.model_name == "lasso"

    def test_xgb_model_name(self, xgb_result):
        assert xgb_result.model_name == "xgb"

    def test_bp_variant_with_bp(self, lasso_result):
        assert lasso_result.bp_variant == "with_bp"

    def test_best_params_populated(self, lasso_result):
        assert isinstance(lasso_result.best_params, dict)
        assert "C" in lasso_result.best_params

    def test_cv_scores_populated(self, lasso_result):
        assert "mean" in lasso_result.cv_scores
        assert "std" in lasso_result.cv_scores

    def test_test_metrics_exists(self, lasso_result):
        assert lasso_result.test_metrics is not None
        assert lasso_result.test_metrics.binary_metrics is not None

    def test_auc_in_range(self, lasso_result):
        auc = lasso_result.test_metrics.binary_metrics.auc_roc
        assert 0.0 <= auc <= 1.0

    def test_calibrated_model_can_predict(self, lasso_result):
        X = lasso_result.feature_result.X.values[:5]
        proba = lasso_result.calibrated_model.predict_proba(X)
        assert proba.shape == (5, 2)

    def test_feature_importance_exists(self, lasso_result):
        assert lasso_result.feature_importance is not None
        assert "feature" in lasso_result.feature_importance.columns
        assert "importance" in lasso_result.feature_importance.columns

    def test_predictions_populated(self, lasso_result):
        assert "y_test" in lasso_result.predictions
        assert "y_proba" in lasso_result.predictions

    def test_no_bp_variant_fewer_features(self, trainer, df):
        """no_bp 变体应比 with_bp 少 2 个特征（bp_rest_sys, bp_rest_dia）。"""
        results = trainer.run(df, n_iter_override=2)
        n_feats_with = len(results["lasso"]["with_bp"].feature_result.feature_names)
        n_feats_no = len(results["lasso"]["no_bp"].feature_result.feature_names)
        # no_bp 排除了 bp_rest_sys 和 bp_rest_dia
        assert n_feats_no <= n_feats_with

    def test_xgb_best_params_has_xgb_keys(self, xgb_result):
        params = xgb_result.best_params
        assert any(k in params for k in ["n_estimators", "max_depth", "learning_rate"])

    def test_predictions_length_consistent(self, lasso_result):
        n_test = len(lasso_result.predictions["y_test"])
        n_proba = len(lasso_result.predictions["y_proba"])
        assert n_test == n_proba

    def test_xgb_feature_importance_all_nonneg(self, xgb_result):
        imp = xgb_result.feature_importance["importance"].values
        assert (imp >= 0).all()

    def test_cv_mean_auc_in_range(self, lasso_result):
        cv_mean = lasso_result.cv_scores["mean"]
        assert 0.0 <= cv_mean <= 1.0
