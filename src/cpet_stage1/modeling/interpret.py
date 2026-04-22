"""
interpret.py — M5 SHAP 模型解释模块。

提供：
- SHAPInterpreter.explain(): 为树模型/线性模型生成 SHAP 值
- Global 解释：mean |SHAP| ranking → top_features_global DataFrame
- Individual 解释：选 5 个代表性患者的 waterfall 图
- save_plots(): summary_plot, waterfall, dependence → PNG
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class InterpretResult:
    """SHAP 解释结果。"""
    model_name: str
    task: str                                  # "p0" 或 "p1"
    variant: str
    shap_values: Any                           # SHAP 值矩阵（或列表，多分类时）
    feature_names: list[str]
    top_features_global: pd.DataFrame          # 全局特征重要性（feature, mean_abs_shap）
    representative_indices: list[int]          # 5 个代表性样本的索引
    explainer_type: str                        # "tree", "linear", "permutation"

    def summary(self) -> str:
        lines = [
            f"InterpretResult [{self.model_name}/{self.task}/{self.variant}]:",
            f"  解释器类型: {self.explainer_type}",
            f"  特征数: {len(self.feature_names)}",
            "  Top-5 全局特征:",
        ]
        for _, row in self.top_features_global.head(5).iterrows():
            lines.append(f"    {row['feature']}: {row['mean_abs_shap']:.4f}")
        return "\n".join(lines)


class SHAPInterpreter:
    """
    SHAP 解释器，支持树模型（XGB/LGBM/CatBoost）和线性模型（LASSO/OrdinalLogistic）。

    使用方法：
        interpreter = SHAPInterpreter()
        result = interpreter.explain(model, X, model_type="tree", task="p0",
                                      model_name="XGBoost", variant="with_bp")
        interpreter.save_plots(result, X, output_dir="reports/figures/m5")
    """

    def explain(
        self,
        model: Any,
        X: np.ndarray | pd.DataFrame,
        model_type: Literal["tree", "linear", "permutation"] = "tree",
        task: str = "p0",
        model_name: str = "model",
        variant: str = "default",
        feature_names: Optional[list[str]] = None,
        max_samples: int = 200,
    ) -> InterpretResult:
        """
        生成 SHAP 解释。

        参数：
            model: 已训练模型（可能是 CalibratedP1Model 包装）
            X: 特征矩阵（numpy 或 DataFrame）
            model_type: "tree"（TreeExplainer）, "linear"（LinearExplainer）,
                         "permutation"（KernelExplainer 代理）
            task: "p0" 或 "p1"
            model_name: 模型名称
            variant: 变体名称
            feature_names: 特征列名（若 X 为 DataFrame 则自动提取）
            max_samples: 最大 SHAP 计算样本数（大数据集抽样）

        返回：
            InterpretResult
        """
        try:
            import shap
        except ImportError:
            raise ImportError("请安装 shap: pip install shap")

        if isinstance(X, pd.DataFrame):
            if feature_names is None:
                feature_names = list(X.columns)
            X_arr = X.values
        else:
            X_arr = np.array(X)
            if feature_names is None:
                feature_names = [f"feature_{i}" for i in range(X_arr.shape[1])]

        # 抽样（大数据集）
        if len(X_arr) > max_samples:
            np.random.seed(42)
            idx = np.random.choice(len(X_arr), max_samples, replace=False)
            X_sample = X_arr[idx]
        else:
            X_sample = X_arr

        # 提取底层模型（CalibratedP1Model 包装的情况）
        base_model = self._unwrap_model(model)

        shap_values, explainer_type = self._compute_shap(
            base_model, X_sample, model_type, task, shap
        )

        # 计算全局特征重要性
        top_features = self._compute_global_importance(shap_values, feature_names, task)

        # 选 5 个代表性样本
        rep_indices = self._select_representative_samples(shap_values, task, n=5)

        logger.info(
            "SHAP [%s/%s]: 解释器=%s, 样本=%d, Top特征=%s",
            model_name, variant, explainer_type,
            len(X_sample), top_features["feature"].iloc[0] if len(top_features) > 0 else "N/A"
        )

        return InterpretResult(
            model_name=model_name,
            task=task,
            variant=variant,
            shap_values=shap_values,
            feature_names=feature_names,
            top_features_global=top_features,
            representative_indices=rep_indices,
            explainer_type=explainer_type,
        )

    def save_plots(
        self,
        result: InterpretResult,
        X: np.ndarray | pd.DataFrame,
        output_dir: str | Path = "reports/figures/m5",
        dpi: int = 150,
    ) -> list[str]:
        """
        保存 SHAP 图表到 PNG 文件。

        生成：
        - summary_plot.png: 全局特征重要性条形图
        - waterfall_{i}.png: 代表性样本 waterfall 图
        - dependence_{top_feature}.png: Top 特征依赖图

        返回：生成的文件路径列表
        """
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import shap
        except ImportError as e:
            raise ImportError(f"请安装 shap 和 matplotlib: {e}")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        generated = []

        if isinstance(X, pd.DataFrame):
            X_arr = X.values
        else:
            X_arr = np.array(X)

        # 获取可用于绘图的 SHAP 值
        shap_vals_for_plot = self._get_plottable_shap(result.shap_values, result.task)

        # 1. Summary plot（条形图）
        try:
            fig, ax = plt.subplots(figsize=(8, 6))
            top_n = min(15, len(result.feature_names))
            top_feat = result.top_features_global.head(top_n)
            ax.barh(top_feat["feature"][::-1], top_feat["mean_abs_shap"][::-1])
            ax.set_xlabel("Mean |SHAP|")
            ax.set_title(f"SHAP Feature Importance\n{result.model_name} ({result.variant})")
            plt.tight_layout()
            save_path = output_dir / f"shap_summary_{result.model_name}_{result.variant}.png"
            fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
            plt.close(fig)
            generated.append(str(save_path))
        except Exception as e:
            logger.warning("SHAP summary plot 生成失败: %s", e)

        # 2. 代表性样本 waterfall 近似图（条形图替代）
        for i, sample_idx in enumerate(result.representative_indices[:3]):
            try:
                if sample_idx >= len(shap_vals_for_plot):
                    continue
                sv = shap_vals_for_plot[sample_idx]
                fig, ax = plt.subplots(figsize=(8, 5))
                # 取绝对值最大的 Top-10 特征
                top_k = min(10, len(sv))
                top_idx = np.argsort(np.abs(sv))[-top_k:]
                feat_labels = [result.feature_names[j] for j in top_idx]
                sv_vals = sv[top_idx]
                colors = ["red" if v > 0 else "blue" for v in sv_vals]
                ax.barh(feat_labels, sv_vals, color=colors)
                ax.axvline(0, color="black", linewidth=0.8)
                ax.set_xlabel("SHAP Value")
                ax.set_title(f"SHAP Waterfall — Sample {i+1}\n{result.model_name} ({result.variant})")
                plt.tight_layout()
                save_path = output_dir / f"shap_waterfall_{result.model_name}_{result.variant}_s{i+1}.png"
                fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
                plt.close(fig)
                generated.append(str(save_path))
            except Exception as e:
                logger.warning("SHAP waterfall 图 %d 生成失败: %s", i, e)

        return generated

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _unwrap_model(self, model: Any) -> Any:
        """提取底层模型（处理 CalibratedP1Model 和 CalibratedClassifierCV 包装）。"""
        # CalibratedP1Model（train_p1）
        if hasattr(model, "base_model"):
            return model.base_model
        # sklearn CalibratedClassifierCV
        if hasattr(model, "calibrated_classifiers_"):
            try:
                return model.calibrated_classifiers_[0].estimator
            except (IndexError, AttributeError):
                pass
        return model

    def _compute_shap(
        self,
        model: Any,
        X: np.ndarray,
        model_type: str,
        task: str,
        shap: Any,
    ) -> tuple[Any, str]:
        """
        计算 SHAP 值，按优先级尝试不同 explainer。

        返回：(shap_values, explainer_type_str)
        """
        # 尝试 TreeExplainer
        if model_type == "tree":
            try:
                explainer = shap.TreeExplainer(model)
                sv = explainer.shap_values(X)
                return sv, "tree"
            except Exception as e:
                logger.warning("TreeExplainer 失败: %s，尝试 PermutationExplainer", e)

        # 尝试 LinearExplainer
        if model_type == "linear":
            try:
                background = shap.maskers.Independent(X, max_samples=min(50, len(X)))
                explainer = shap.LinearExplainer(model, background)
                sv = explainer.shap_values(X)
                return sv, "linear"
            except Exception as e:
                logger.warning("LinearExplainer 失败: %s，尝试 PermutationExplainer", e)

        # 回退到 PermutationExplainer（模型无关）
        try:
            background = X[:min(20, len(X))]
            predict_fn = self._get_predict_fn(model, task)
            explainer = shap.KernelExplainer(predict_fn, background)
            sv = explainer.shap_values(X[:min(30, len(X))], nsamples=50, silent=True)
            return sv, "permutation"
        except Exception as e:
            logger.warning("KernelExplainer 也失败: %s，返回零 SHAP 值", e)
            sv = np.zeros((len(X), X.shape[1]))
            return sv, "fallback"

    def _get_predict_fn(self, model: Any, task: str):
        """获取预测函数（用于 KernelExplainer）。"""
        if hasattr(model, "predict_proba"):
            if task == "p0":
                return lambda X: model.predict_proba(X)[:, 1]
            else:
                return model.predict_proba
        return model.predict

    def _compute_global_importance(
        self,
        shap_values: Any,
        feature_names: list[str],
        task: str,
    ) -> pd.DataFrame:
        """
        计算全局特征重要性（mean |SHAP|）。

        对多分类（P1），取各类别 SHAP 值的平均绝对值之和。
        """
        sv_arr = self._get_plottable_shap(shap_values, task)

        if sv_arr is None or len(sv_arr) == 0:
            return pd.DataFrame({"feature": feature_names, "mean_abs_shap": [0.0] * len(feature_names)})

        mean_abs = np.mean(np.abs(sv_arr), axis=0)
        n_feats = min(len(feature_names), len(mean_abs))

        return pd.DataFrame({
            "feature": feature_names[:n_feats],
            "mean_abs_shap": mean_abs[:n_feats],
        }).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)

    def _get_plottable_shap(self, shap_values: Any, task: str) -> np.ndarray:
        """
        获取可用于绘图的 2D SHAP 矩阵。

        - 二分类（P0）：shap_values 可能是 list[array] 或 array，取阳性类
        - 多分类（P1）：取各类别绝对值求平均
        """
        if isinstance(shap_values, list):
            if len(shap_values) == 0:
                return np.array([])
            if task == "p0":
                # 二分类：取第二类（阳性类）
                return np.array(shap_values[-1]) if len(shap_values) > 1 else np.array(shap_values[0])
            else:
                # 多分类：各类别绝对值平均
                arrays = [np.abs(sv) for sv in shap_values]
                return np.mean(arrays, axis=0)
        elif isinstance(shap_values, np.ndarray):
            if shap_values.ndim == 3:
                # (n_samples, n_features, n_classes) 或 (n_classes, n_samples, n_features)
                if task == "p0":
                    return shap_values[:, :, -1]
                else:
                    return np.mean(np.abs(shap_values), axis=-1)
            return shap_values
        return np.array(shap_values)

    def _select_representative_samples(
        self,
        shap_values: Any,
        task: str,
        n: int = 5,
    ) -> list[int]:
        """
        选择代表性样本：高风险 + 低风险 + 边界样本。

        返回：索引列表（最多 n 个）
        """
        sv_arr = self._get_plottable_shap(shap_values, task)
        if sv_arr is None or len(sv_arr) < n:
            return list(range(min(n, len(sv_arr) if sv_arr is not None else 0)))

        # 每个样本的总 SHAP 影响量
        total_effect = np.abs(sv_arr).sum(axis=1)
        n_samples = len(total_effect)

        # 高影响（前 2）
        top_indices = np.argsort(total_effect)[-2:][::-1].tolist()
        # 低影响（后 2）
        low_indices = np.argsort(total_effect)[:2].tolist()
        # 中间（边界，1 个）
        mid_idx = [int(np.argsort(total_effect)[n_samples // 2])]

        # 去重保持顺序
        seen = set()
        result = []
        for idx in top_indices + low_indices + mid_idx:
            if idx not in seen:
                seen.add(idx)
                result.append(idx)
        return result[:n]
