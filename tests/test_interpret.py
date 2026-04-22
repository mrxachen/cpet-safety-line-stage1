"""
test_interpret.py — M5 SHAP 解释模块测试（~12 个测试）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

from cpet_stage1.modeling.interpret import InterpretResult, SHAPInterpreter


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------

def make_binary_model():
    rng = np.random.default_rng(42)
    X = rng.normal(0, 1, (60, 5))
    y = (X[:, 0] > 0).astype(int)
    model = DecisionTreeClassifier(max_depth=3, random_state=42)
    model.fit(X, y)
    return model, X, y


def make_multiclass_model():
    rng = np.random.default_rng(42)
    X = rng.normal(0, 1, (90, 5))
    y = np.array([0] * 30 + [1] * 30 + [2] * 30)
    model = DecisionTreeClassifier(max_depth=3, random_state=42)
    model.fit(X, y)
    return model, X, y


@pytest.fixture
def interpreter():
    return SHAPInterpreter()


# ---------------------------------------------------------------------------
# 测试（跳过 shap 未安装的情况）
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    not __import__("importlib").util.find_spec("shap"),
    reason="shap 未安装，跳过 SHAP 测试"
)


class TestSHAPInterpreter:

    def test_explain_returns_interpret_result(self, interpreter):
        model, X, y = make_binary_model()
        result = interpreter.explain(model, X, model_type="tree", task="p0", model_name="DT")
        assert isinstance(result, InterpretResult)

    def test_explain_task_p0(self, interpreter):
        model, X, y = make_binary_model()
        result = interpreter.explain(model, X, model_type="tree", task="p0")
        assert result.task == "p0"

    def test_explain_task_p1(self, interpreter):
        model, X, y = make_multiclass_model()
        result = interpreter.explain(model, X, model_type="tree", task="p1")
        assert result.task == "p1"

    def test_top_features_global_not_empty(self, interpreter):
        model, X, y = make_binary_model()
        result = interpreter.explain(model, X, model_type="tree", task="p0")
        assert len(result.top_features_global) > 0
        assert "feature" in result.top_features_global.columns
        assert "mean_abs_shap" in result.top_features_global.columns

    def test_top_features_nonneg(self, interpreter):
        model, X, y = make_binary_model()
        result = interpreter.explain(model, X, model_type="tree", task="p0")
        assert (result.top_features_global["mean_abs_shap"] >= 0).all()

    def test_representative_indices_populated(self, interpreter):
        model, X, y = make_binary_model()
        result = interpreter.explain(model, X, model_type="tree", task="p0")
        assert len(result.representative_indices) >= 1

    def test_feature_names_from_dataframe(self, interpreter):
        model, X, y = make_binary_model()
        X_df = pd.DataFrame(X, columns=[f"feat_{i}" for i in range(5)])
        result = interpreter.explain(model, X_df, model_type="tree", task="p0")
        assert result.feature_names == [f"feat_{i}" for i in range(5)]

    def test_explain_summary_returns_string(self, interpreter):
        model, X, y = make_binary_model()
        result = interpreter.explain(model, X, model_type="tree", task="p0")
        s = result.summary()
        assert isinstance(s, str)

    def test_save_plots_generates_files(self, interpreter, tmp_path):
        model, X, y = make_binary_model()
        X_df = pd.DataFrame(X, columns=[f"feat_{i}" for i in range(5)])
        result = interpreter.explain(model, X_df, model_type="tree", task="p0",
                                      model_name="DT", variant="test")
        generated = interpreter.save_plots(result, X_df, output_dir=tmp_path)
        assert len(generated) >= 1
        assert all(str(p).endswith(".png") for p in generated)

    def test_max_samples_limit(self, interpreter):
        model, X, y = make_binary_model()
        X_large = np.vstack([X] * 5)  # 300 samples
        result = interpreter.explain(model, X_large, model_type="tree", task="p0",
                                      max_samples=50)
        assert isinstance(result, InterpretResult)

    def test_linear_model_explain(self, interpreter):
        """线性模型使用 LinearExplainer（或回退到 PermutationExplainer）。"""
        rng = np.random.default_rng(42)
        X = rng.normal(0, 1, (50, 4))
        y = (X[:, 0] > 0).astype(int)
        model = LogisticRegression(random_state=42).fit(X, y)
        result = interpreter.explain(model, X, model_type="linear", task="p0")
        assert isinstance(result, InterpretResult)

    def test_top_features_sorted_descending(self, interpreter):
        model, X, y = make_binary_model()
        result = interpreter.explain(model, X, model_type="tree", task="p0")
        vals = result.top_features_global["mean_abs_shap"].values
        assert all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
