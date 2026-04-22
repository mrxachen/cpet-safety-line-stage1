"""
test_modeling_p1.py — M5 P1 训练管线测试（~25 个测试）。

使用合成数据，n_iter_override=2 加速测试。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.modeling.calibrate import TemperatureScaler
from cpet_stage1.modeling.train_p1 import (
    CalibratedP1Model,
    P1ModelResult,
    P1Trainer,
    _OrdinalLogisticWrapper,
)


# ---------------------------------------------------------------------------
# 测试数据工厂
# ---------------------------------------------------------------------------

def make_p1_df(n: int = 90, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # 确保三个区都有足够样本
    zone = np.array([0] * (n // 3) + [1] * (n // 3) + [2] * (n - 2 * (n // 3)))
    rng.shuffle(zone)

    df = pd.DataFrame({
        "subject_id": [f"S{i:04d}" for i in range(n)],
        "age": rng.integers(60, 80, n).astype(float),
        "sex": rng.choice(["M", "F"], n),
        # P1 CPET 结果
        "vo2_peak": rng.uniform(8, 28, n),
        "hr_peak": rng.uniform(100, 170, n),
        "load_peak_w": rng.uniform(40, 160, n),
        "o2_pulse_peak": rng.uniform(6, 16, n),
        "ve_vco2_slope": rng.uniform(22, 45, n),
        "vt1_vo2": rng.uniform(6, 20, n),
        "vt1_hr": rng.uniform(90, 145, n),
        "vt1_load_w": rng.uniform(30, 120, n),
        "vt1_pct_vo2peak": rng.uniform(55, 80, n),
        "eih_nadir_spo2": rng.uniform(82, 99, n),
        "eih_status": rng.choice([True, False], n),
        "bp_response_abnormal": rng.choice([True, False], n),
        "exercise_protocol_cycle": rng.choice([True, False], n),
        # 标签（leakage guard P1 排除 vo2_peak_pct_pred，但我们仍放入 df 测试排除逻辑）
        "vo2_peak_pct_pred": rng.uniform(30, 100, n),
        "p0_event": rng.choice([0, 1], n, p=[0.8, 0.2]),
        "p1_zone": zone,
    })
    return df


@pytest.fixture
def trainer():
    return P1Trainer()


@pytest.fixture
def df():
    return make_p1_df(n=90)


@pytest.fixture(scope="session")
def p1_results_cached():
    """Session-scoped fixture：只跑一次 trainer.run()，所有测试共享结果。"""
    t = P1Trainer()
    d = make_p1_df(n=90)
    return t.run(d, n_iter_override=2)


# ---------------------------------------------------------------------------
# _OrdinalLogisticWrapper 测试
# ---------------------------------------------------------------------------

class TestOrdinalLogisticWrapper:

    def test_fit_predict(self):
        rng = np.random.default_rng(42)
        X = rng.normal(0, 1, (60, 4))
        y = np.array([0] * 20 + [1] * 20 + [2] * 20)
        model = _OrdinalLogisticWrapper(C=1.0)
        model.fit(X, y)
        pred = model.predict(X)
        assert len(pred) == len(y)
        assert set(pred).issubset({0, 1, 2})

    def test_predict_proba_shape(self):
        rng = np.random.default_rng(42)
        X = rng.normal(0, 1, (60, 4))
        y = np.array([0] * 20 + [1] * 20 + [2] * 20)
        model = _OrdinalLogisticWrapper(C=1.0)
        model.fit(X, y)
        proba = model.predict_proba(X)
        assert proba.shape == (60, 3)

    def test_predict_proba_sums_to_one(self):
        rng = np.random.default_rng(42)
        X = rng.normal(0, 1, (30, 3))
        y = np.array([0] * 10 + [1] * 10 + [2] * 10)
        model = _OrdinalLogisticWrapper(C=1.0)
        model.fit(X, y)
        proba = model.predict_proba(X)
        np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-6)


# ---------------------------------------------------------------------------
# TemperatureScaler 测试
# ---------------------------------------------------------------------------

class TestTemperatureScaler:

    def test_fit_learns_temperature(self):
        rng = np.random.default_rng(42)
        proba = rng.dirichlet([1, 1, 1], 50)
        y = rng.integers(0, 3, 50)
        ts = TemperatureScaler(bounds=(0.1, 10.0))
        ts.fit(proba, y)
        assert ts.temperature_ is not None
        assert 0.1 <= ts.temperature_ <= 10.0

    def test_transform_sums_to_one(self):
        rng = np.random.default_rng(42)
        proba = rng.dirichlet([1, 1, 1], 30)
        y = rng.integers(0, 3, 30)
        ts = TemperatureScaler()
        ts.fit(proba, y)
        cal = ts.transform(proba)
        np.testing.assert_allclose(cal.sum(axis=1), 1.0, atol=1e-6)

    def test_transform_before_fit_raises(self):
        ts = TemperatureScaler()
        proba = np.ones((5, 3)) / 3
        with pytest.raises(RuntimeError):
            ts.transform(proba)


# ---------------------------------------------------------------------------
# CalibratedP1Model 测试
# ---------------------------------------------------------------------------

class TestCalibratedP1Model:

    def test_predict_returns_class_labels(self):
        rng = np.random.default_rng(42)
        X = rng.normal(0, 1, (30, 4))
        y = np.array([0] * 10 + [1] * 10 + [2] * 10)
        from sklearn.linear_model import LogisticRegression
        base = LogisticRegression(solver="lbfgs", max_iter=300).fit(X, y)
        wrapped = CalibratedP1Model(base_model=base, temperature_scaler=None)
        pred = wrapped.predict(X)
        assert len(pred) == len(y)
        assert set(pred).issubset({0, 1, 2})


# ---------------------------------------------------------------------------
# P1Trainer.run() 结构测试
# ---------------------------------------------------------------------------

class TestP1TrainerRun:
    """P1 trainer 结构测试，使用 session-scoped 缓存结果加速。"""

    def test_run_returns_dict(self, p1_results_cached):
        assert isinstance(p1_results_cached, dict)

    def test_run_has_expected_models(self, p1_results_cached):
        assert len(p1_results_cached) >= 1  # 至少有一个模型成功

    def test_run_has_sample_variants(self, p1_results_cached):
        for model_name, variants in p1_results_cached.items():
            assert len(variants) >= 1

    def test_run_missing_label_raises(self, trainer, df):
        df_no_label = df.drop(columns=["p1_zone"])
        with pytest.raises(ValueError, match="标签列"):
            trainer.run(df_no_label, n_iter_override=2)

    def test_p1_model_result_structure(self, p1_results_cached):
        for model_name, variants in p1_results_cached.items():
            for variant, result in variants.items():
                assert isinstance(result, P1ModelResult)

    def test_f1_macro_in_range(self, p1_results_cached):
        for model_name, variants in p1_results_cached.items():
            for variant, result in variants.items():
                mc = result.test_metrics.multiclass_metrics
                if mc:
                    assert 0.0 <= mc.f1_macro <= 1.0

    def test_cv_scores_populated(self, p1_results_cached):
        for model_name, variants in p1_results_cached.items():
            for variant, result in variants.items():
                assert "mean" in result.cv_scores

    def test_predictions_populated(self, p1_results_cached):
        for model_name, variants in p1_results_cached.items():
            for variant, result in variants.items():
                preds = result.predictions
                assert "y_test" in preds
                assert "y_pred" in preds

    def test_calibrated_model_predict_proba(self, p1_results_cached):
        for model_name, variants in p1_results_cached.items():
            for variant, result in variants.items():
                X = result.feature_result.X.values[:5]
                proba = result.calibrated_model.predict_proba(X)
                assert proba.shape[1] == 3  # 3 classes
                np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-5)
                break
            break

    def test_feature_importance_for_lgbm(self, p1_results_cached):
        if "lgbm" in p1_results_cached and "full" in p1_results_cached["lgbm"]:
            feat_imp = p1_results_cached["lgbm"]["full"].feature_importance
            assert feat_imp is not None
            assert "importance" in feat_imp.columns

    def test_ordinal_logistic_in_results(self, p1_results_cached):
        assert "ordinal_logistic" in p1_results_cached

    def test_p1_zone_col_excluded_from_features(self, p1_results_cached):
        """p1_zone 标签列不应出现在 P1 特征中。"""
        for model_name, variants in p1_results_cached.items():
            for variant, result in variants.items():
                assert "p1_zone" not in result.feature_result.feature_names
                break
            break

    def test_vo2_peak_pct_pred_excluded_from_features(self, p1_results_cached):
        """vo2_peak_pct_pred 被 leakage_guard P1 排除。"""
        for model_name, variants in p1_results_cached.items():
            for variant, result in variants.items():
                assert "vo2_peak_pct_pred" not in result.feature_result.feature_names
                break
            break

    def test_consistency_analysis_runs(self, trainer, df):
        """踏车子集有足够样本时应进行一致性分析。"""
        df_with_cycle = df.copy()
        # 确保有足够的 cycle 样本
        df_with_cycle["exercise_protocol_cycle"] = True
        results = trainer.run(df_with_cycle, n_iter_override=2)
        # 有 cycle_only 变体
        for model_name, variants in results.items():
            if "cycle_only" in variants:
                assert variants["cycle_only"].sample_variant == "cycle_only"
                break
