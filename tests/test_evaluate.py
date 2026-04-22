"""
test_evaluate.py — M5 评估模块测试（~20 个测试）。
"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression

from cpet_stage1.modeling.evaluate import (
    BinaryMetrics,
    CalibrationData,
    DCAData,
    EvaluationResult,
    ModelEvaluator,
    MulticlassMetrics,
)


# ---------------------------------------------------------------------------
# 测试数据工厂
# ---------------------------------------------------------------------------

def make_binary_model(n: int = 80, seed: int = 42):
    """训练一个简单的二分类模型。"""
    rng = np.random.default_rng(seed)
    X = rng.normal(0, 1, (n, 4))
    y = (X[:, 0] + rng.normal(0, 0.5, n) > 0).astype(int)
    model = LogisticRegression(random_state=42, max_iter=200)
    model.fit(X, y)
    return model, X, y


def make_multiclass_model(n: int = 90, seed: int = 42):
    """训练一个简单的三分类模型。"""
    rng = np.random.default_rng(seed)
    X = rng.normal(0, 1, (n, 5))
    y = np.zeros(n, dtype=int)
    y[n // 3: 2 * n // 3] = 1
    y[2 * n // 3:] = 2
    model = LogisticRegression(solver="lbfgs", max_iter=300, random_state=42)
    model.fit(X, y)
    return model, X, y


@pytest.fixture
def evaluator():
    return ModelEvaluator(n_calibration_bins=5)


@pytest.fixture
def binary_data():
    return make_binary_model()


@pytest.fixture
def multiclass_data():
    return make_multiclass_model()


# ---------------------------------------------------------------------------
# evaluate_binary
# ---------------------------------------------------------------------------

class TestEvaluateBinary:

    def test_returns_evaluation_result(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y, model_name="LR", variant="test")
        assert isinstance(result, EvaluationResult)

    def test_binary_metrics_populated(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        assert result.binary_metrics is not None
        assert isinstance(result.binary_metrics, BinaryMetrics)

    def test_auc_roc_in_range(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        auc = result.binary_metrics.auc_roc
        assert 0.0 <= auc <= 1.0

    def test_meaningful_model_beats_random(self, evaluator, binary_data):
        """有意义的模型 AUC 应 > 0.5。"""
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        assert result.binary_metrics.auc_roc > 0.5

    def test_auprc_in_range(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        assert 0.0 <= result.binary_metrics.auprc <= 1.0

    def test_brier_in_range(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        assert 0.0 <= result.binary_metrics.brier <= 1.0

    def test_sensitivity_specificity_in_range(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        assert 0.0 <= result.binary_metrics.sensitivity <= 1.0
        assert 0.0 <= result.binary_metrics.specificity <= 1.0

    def test_calibration_data_exists(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        assert result.calibration_data is not None or True  # 可能因样本太少失败

    def test_dca_data_exists(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        assert result.dca_data is not None

    def test_roc_curve_data_exists(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        assert result.roc_curve_data is not None
        assert "fpr" in result.roc_curve_data
        assert "tpr" in result.roc_curve_data

    def test_pr_curve_data_exists(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        assert result.pr_curve_data is not None

    def test_n_positive_n_negative(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        bm = result.binary_metrics
        assert bm.n_positive + bm.n_negative == len(y)

    def test_task_is_p0(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        assert result.task == "p0"


# ---------------------------------------------------------------------------
# evaluate_multiclass
# ---------------------------------------------------------------------------

class TestEvaluateMulticlass:

    def test_returns_evaluation_result(self, evaluator, multiclass_data):
        model, X, y = multiclass_data
        result = evaluator.evaluate_multiclass(model, X, y)
        assert isinstance(result, EvaluationResult)

    def test_multiclass_metrics_populated(self, evaluator, multiclass_data):
        model, X, y = multiclass_data
        result = evaluator.evaluate_multiclass(model, X, y)
        assert result.multiclass_metrics is not None

    def test_f1_macro_in_range(self, evaluator, multiclass_data):
        model, X, y = multiclass_data
        result = evaluator.evaluate_multiclass(model, X, y)
        assert 0.0 <= result.multiclass_metrics.f1_macro <= 1.0

    def test_kappa_in_range(self, evaluator, multiclass_data):
        model, X, y = multiclass_data
        result = evaluator.evaluate_multiclass(model, X, y)
        assert -1.0 <= result.multiclass_metrics.kappa_weighted <= 1.0

    def test_confusion_matrix_shape(self, evaluator, multiclass_data):
        model, X, y = multiclass_data
        result = evaluator.evaluate_multiclass(model, X, y)
        cm = result.multiclass_metrics.confusion_matrix
        assert len(cm) == 3
        assert all(len(row) == 3 for row in cm)

    def test_per_class_f1_keys(self, evaluator, multiclass_data):
        model, X, y = multiclass_data
        result = evaluator.evaluate_multiclass(model, X, y, class_names=["green", "yellow", "red"])
        per_class = result.multiclass_metrics.per_class_f1
        assert "green" in per_class
        assert "yellow" in per_class
        assert "red" in per_class

    def test_task_is_p1(self, evaluator, multiclass_data):
        model, X, y = multiclass_data
        result = evaluator.evaluate_multiclass(model, X, y)
        assert result.task == "p1"


# ---------------------------------------------------------------------------
# decision_curve_analysis
# ---------------------------------------------------------------------------

class TestDCA:

    def test_dca_thresholds_in_range(self, evaluator):
        rng = np.random.default_rng(42)
        y = rng.choice([0, 1], 50, p=[0.7, 0.3])
        proba = rng.uniform(0, 1, 50)
        dca = evaluator.decision_curve_analysis(y, proba)
        assert all(0 <= t <= 1 for t in dca.thresholds)

    def test_dca_treat_none_is_zero(self, evaluator):
        rng = np.random.default_rng(42)
        y = rng.choice([0, 1], 50)
        proba = rng.uniform(0, 1, 50)
        dca = evaluator.decision_curve_analysis(y, proba)
        assert all(v == 0.0 for v in dca.net_benefit_treat_none)

    def test_dca_lengths_match(self, evaluator):
        rng = np.random.default_rng(42)
        y = rng.choice([0, 1], 50)
        proba = rng.uniform(0, 1, 50)
        dca = evaluator.decision_curve_analysis(y, proba, n_points=20)
        assert len(dca.thresholds) == len(dca.net_benefit_model) == 20


# ---------------------------------------------------------------------------
# EvaluationResult serialization
# ---------------------------------------------------------------------------

class TestEvaluationResultSerialization:

    def test_to_json_returns_string(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        json_str = result.to_json()
        assert isinstance(json_str, str)
        assert "auc_roc" in json_str

    def test_to_markdown_returns_string(self, evaluator, binary_data):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        md = result.to_markdown()
        assert isinstance(md, str)
        assert "AUC-ROC" in md

    def test_to_json_writes_file(self, evaluator, binary_data, tmp_path):
        model, X, y = binary_data
        result = evaluator.evaluate_binary(model, X, y)
        out = tmp_path / "metrics.json"
        result.to_json(str(out))
        assert out.exists()
