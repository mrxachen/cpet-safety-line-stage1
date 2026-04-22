"""
test_features.py — M5 特征工程模块测试（~25 个测试）。

使用合成数据，不依赖真实患者数据。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.features.feature_engineer import FeatureEngineer, FeatureResult
from cpet_stage1.labels.leakage_guard import LeakageGuard


# ---------------------------------------------------------------------------
# 测试数据工厂
# ---------------------------------------------------------------------------

def make_full_df(n: int = 30, seed: int = 42) -> pd.DataFrame:
    """生成含 P0/P1 所有字段的合成 DataFrame。"""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        # 人口学
        "subject_id": [f"S{i:04d}" for i in range(n)],
        "age": rng.integers(60, 80, n).astype(float),
        "sex": rng.choice(["M", "F"], n),
        "height_cm": rng.uniform(155, 180, n),
        "weight_kg": rng.uniform(55, 90, n),
        "bmi": rng.uniform(20, 32, n),
        # 临床
        "htn_history": rng.choice([True, False], n),
        "cad_history": rng.choice([True, False, None], n).astype(object),
        "hf_history": rng.choice([True, False, None], n).astype(object),
        "lvef_pct": rng.uniform(40, 75, n),
        "nyha_class": rng.integers(1, 4, n).astype(float),
        # 静息 BP / HR
        "bp_rest_sys": rng.uniform(110, 160, n),
        "bp_rest_dia": rng.uniform(70, 95, n),
        "hr_rest": rng.uniform(55, 85, n),
        # 协议
        "exercise_protocol_cycle": rng.choice([True, False], n),
        # P1 CPET 结果
        "vo2_peak": rng.uniform(8, 28, n),
        "vo2_peak_pct_pred": rng.uniform(30, 100, n),
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
        # 标签
        "p0_event": rng.choice([0, 1], n, p=[0.8, 0.2]),
        "p1_zone": rng.choice([0, 1, 2], n),
    })
    return df


@pytest.fixture
def fe() -> FeatureEngineer:
    return FeatureEngineer(
        config_path="configs/features/feature_config_v1.yaml",
        label_rules_path="configs/data/label_rules_v2.yaml",
    )


@pytest.fixture
def df() -> pd.DataFrame:
    return make_full_df(n=30)


# ---------------------------------------------------------------------------
# FeatureEngineer — build_p0
# ---------------------------------------------------------------------------

class TestBuildP0:

    def test_build_p0_returns_feature_result(self, fe, df):
        result = fe.build_p0(df)
        assert isinstance(result, FeatureResult)

    def test_build_p0_task_is_p0(self, fe, df):
        result = fe.build_p0(df)
        assert result.task == "p0"

    def test_build_p0_has_features(self, fe, df):
        result = fe.build_p0(df)
        assert len(result.feature_names) > 0
        assert result.X.shape[1] == len(result.feature_names)

    def test_build_p0_no_nan_after_imputation(self, fe, df):
        result = fe.build_p0(df)
        # 连续列应全部插补
        assert not result.X.isna().any().any()

    def test_build_p0_no_leakage(self, fe, df):
        result = fe.build_p0(df)
        guard = LeakageGuard.from_config("configs/data/label_rules_v2.yaml")
        # assert_no_leakage 不应抛出异常
        guard.assert_no_leakage(result.X, task="p0")

    def test_build_p0_exclude_bp_peak_sys(self, fe, df):
        """bp_peak_sys 被 leakage_guard 排除，不应出现在 P0 特征中。"""
        df2 = df.copy()
        df2["bp_peak_sys"] = 200.0
        result = fe.build_p0(df2)
        assert "bp_peak_sys" not in result.feature_names

    def test_build_p0_exclude_post_exercise_fields(self, fe, df):
        """vo2_peak 等运动后字段不应出现在 P0 特征中。"""
        result = fe.build_p0(df)
        assert "vo2_peak" not in result.feature_names
        assert "hr_peak" not in result.feature_names

    def test_build_p0_with_bp_True(self, fe, df):
        result = fe.build_p0(df, include_bp=True)
        assert "bp_rest_sys" in result.feature_names

    def test_build_p0_with_bp_False(self, fe, df):
        result = fe.build_p0(df, include_bp=False)
        assert "bp_rest_sys" not in result.feature_names
        assert "bp_rest_dia" not in result.feature_names

    def test_build_p0_sex_encoded(self, fe, df):
        result = fe.build_p0(df)
        assert "sex" in result.feature_names
        sex_vals = result.X["sex"].unique()
        # 编码后只有 0 和 1
        assert set(sex_vals).issubset({0.0, 1.0, -1.0})

    def test_build_p0_fitted_imputer_in_result(self, fe, df):
        result = fe.build_p0(df)
        assert result.fitted_imputer is not None

    def test_build_p0_imputer_reuse_for_test(self, fe, df):
        """用 train 集 fit 的 imputer 可复用于 test 集。"""
        train_df = df.iloc[:20].copy()
        test_df = df.iloc[20:].copy()
        r_train = fe.build_p0(train_df)
        r_test = fe.build_p0(test_df, fitted_imputer=r_train.fitted_imputer)
        assert r_test.X.shape[1] == r_train.X.shape[1]
        assert not r_test.X.isna().any().any()

    def test_build_p0_lasso_has_scaler(self, fe, df):
        result = fe.build_p0(df, model_type="lasso_logistic")
        assert result.scaler is not None

    def test_build_p0_xgb_no_scaler(self, fe, df):
        result = fe.build_p0(df, model_type="xgboost")
        assert result.scaler is None

    def test_build_p0_imputer_stats_populated(self, fe, df):
        result = fe.build_p0(df)
        assert len(result.imputer_stats) > 0

    def test_build_p0_leakage_report_populated(self, fe, df):
        result = fe.build_p0(df)
        assert "p0_exclusions" in result.leakage_report


# ---------------------------------------------------------------------------
# FeatureEngineer — build_p1
# ---------------------------------------------------------------------------

class TestBuildP1:

    def test_build_p1_returns_feature_result(self, fe, df):
        result = fe.build_p1(df)
        assert isinstance(result, FeatureResult)

    def test_build_p1_task_is_p1(self, fe, df):
        result = fe.build_p1(df)
        assert result.task == "p1"

    def test_build_p1_has_features(self, fe, df):
        result = fe.build_p1(df)
        assert len(result.feature_names) > 0

    def test_build_p1_no_nan(self, fe, df):
        result = fe.build_p1(df)
        assert not result.X.isna().any().any()

    def test_build_p1_no_leakage(self, fe, df):
        result = fe.build_p1(df)
        guard = LeakageGuard.from_config("configs/data/label_rules_v2.yaml")
        guard.assert_no_leakage(result.X, task="p1")

    def test_build_p1_excludes_vo2_peak_pct_pred(self, fe, df):
        """vo2_peak_pct_pred 被 leakage_guard 排除（P1 区域边界用字段）。"""
        result = fe.build_p1(df)
        assert "vo2_peak_pct_pred" not in result.feature_names

    def test_build_p1_excludes_p0_event(self, fe, df):
        """p0_event 不应出现在 P1 特征中。"""
        result = fe.build_p1(df)
        assert "p0_event" not in result.feature_names

    def test_build_p1_cycle_only_filter(self, fe, df):
        """cycle_only=True 时仅保留踏车协议记录。"""
        df_with_cycle = df.copy()
        df_with_cycle["exercise_protocol_cycle"] = True
        result = fe.build_p1(df_with_cycle, cycle_only=True)
        assert len(result.X) == len(df_with_cycle)

    def test_build_p1_cycle_only_empty_raises(self, fe, df):
        """cycle_only=True 且无踏车记录时应抛出 ValueError。"""
        df_no_cycle = df.copy()
        df_no_cycle["exercise_protocol_cycle"] = False
        with pytest.raises(ValueError, match="cycle_only"):
            fe.build_p1(df_no_cycle, cycle_only=True)

    def test_build_p1_ordinal_logistic_has_scaler(self, fe, df):
        result = fe.build_p1(df, model_type="ordinal_logistic")
        assert result.scaler is not None

    def test_build_p1_lightgbm_no_scaler(self, fe, df):
        result = fe.build_p1(df, model_type="lightgbm")
        assert result.scaler is None


# ---------------------------------------------------------------------------
# FeatureResult — to_parquet / summary
# ---------------------------------------------------------------------------

class TestFeatureResult:

    def test_to_parquet(self, fe, df, tmp_path):
        result = fe.build_p0(df)
        out = tmp_path / "features_p0.parquet"
        result.to_parquet(out)
        assert out.exists()
        loaded = pd.read_parquet(out)
        assert loaded.shape == result.X.shape

    def test_summary_returns_string(self, fe, df):
        result = fe.build_p0(df)
        s = result.summary()
        assert isinstance(s, str)
        assert "p0" in s.lower()
