"""
evaluate.py — M5 模型评估模块（共享基础设施）。

提供：
- ModelEvaluator.evaluate_binary(): AUC, AUPRC, Brier, sensitivity, specificity, F1
  + 校准曲线数据 + DCA 数据
- ModelEvaluator.evaluate_multiclass(): F1_macro, kappa, accuracy, per-class, confusion matrix
- EvaluationResult dataclass: to_json() / to_markdown()
- decision_curve_analysis(): 净获益 = TP/N - FP/N × t/(1-t)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    auc,
    average_precision_score,
    brier_score_loss,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
    accuracy_score,
)

logger = logging.getLogger(__name__)


@dataclass
class BinaryMetrics:
    """二分类评估指标。"""
    auc_roc: float
    auprc: float
    brier: float
    sensitivity: float       # TPR at optimal threshold
    specificity: float       # TNR at optimal threshold
    f1: float
    optimal_threshold: float
    n_positive: int
    n_negative: int


@dataclass
class MulticlassMetrics:
    """多分类评估指标。"""
    f1_macro: float
    kappa_weighted: float
    accuracy: float
    per_class_f1: dict[str, float]
    per_class_support: dict[str, int]
    confusion_matrix: list[list[int]]


@dataclass
class CalibrationData:
    """校准曲线数据。"""
    fraction_of_positives: list[float]   # 实际阳性比例（y 轴）
    mean_predicted_value: list[float]    # 预测概率均值（x 轴）
    n_bins: int


@dataclass
class DCAData:
    """决策曲线分析数据。"""
    thresholds: list[float]          # 阈值序列
    net_benefit_model: list[float]   # 模型净获益
    net_benefit_treat_all: list[float]   # 全治疗净获益
    net_benefit_treat_none: list[float]  # 不治疗净获益（恒为 0）


@dataclass
class EvaluationResult:
    """模型评估完整结果。"""
    model_name: str
    task: str                   # "p0" 或 "p1"
    variant: str                # "with_bp", "no_bp", "full", "cycle_only"
    binary_metrics: Optional[BinaryMetrics]
    multiclass_metrics: Optional[MulticlassMetrics]
    calibration_data: Optional[CalibrationData]
    dca_data: Optional[DCAData]
    roc_curve_data: Optional[dict[str, list]]  # fpr, tpr, thresholds
    pr_curve_data: Optional[dict[str, list]]   # precision, recall, thresholds

    def to_json(self, path: Optional[str | Path] = None) -> str:
        """序列化为 JSON 字符串，可选写入文件。"""
        d: dict[str, Any] = {
            "model_name": self.model_name,
            "task": self.task,
            "variant": self.variant,
        }
        if self.binary_metrics:
            d["binary_metrics"] = asdict(self.binary_metrics)
        if self.multiclass_metrics:
            mc = asdict(self.multiclass_metrics)
            d["multiclass_metrics"] = mc
        if self.calibration_data:
            d["calibration_data"] = asdict(self.calibration_data)
        if self.dca_data:
            d["dca_data"] = asdict(self.dca_data)
        if self.roc_curve_data:
            d["roc_curve_data"] = self.roc_curve_data
        if self.pr_curve_data:
            d["pr_curve_data"] = self.pr_curve_data

        json_str = json.dumps(d, ensure_ascii=False, indent=2, default=float)
        if path is not None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json_str, encoding="utf-8")
        return json_str

    def to_markdown(self) -> str:
        """生成 Markdown 格式摘要。"""
        lines = [
            f"## {self.model_name} — {self.task.upper()} ({self.variant})",
            "",
        ]
        if self.binary_metrics:
            m = self.binary_metrics
            lines += [
                "### 二分类指标",
                "",
                "| 指标 | 值 |",
                "|---|---|",
                f"| AUC-ROC | {m.auc_roc:.4f} |",
                f"| AUPRC | {m.auprc:.4f} |",
                f"| Brier Score | {m.brier:.4f} |",
                f"| Sensitivity | {m.sensitivity:.4f} |",
                f"| Specificity | {m.specificity:.4f} |",
                f"| F1 | {m.f1:.4f} |",
                f"| 最优阈值 | {m.optimal_threshold:.4f} |",
                f"| 阳性样本 | {m.n_positive} |",
                f"| 阴性样本 | {m.n_negative} |",
                "",
            ]
        if self.multiclass_metrics:
            m = self.multiclass_metrics
            lines += [
                "### 多分类指标",
                "",
                "| 指标 | 值 |",
                "|---|---|",
                f"| F1_macro | {m.f1_macro:.4f} |",
                f"| Kappa（weighted） | {m.kappa_weighted:.4f} |",
                f"| Accuracy | {m.accuracy:.4f} |",
                "",
                "**各类别 F1：**",
                "",
            ]
            for cls_name, f1_val in m.per_class_f1.items():
                support = m.per_class_support.get(cls_name, 0)
                lines.append(f"- {cls_name}: F1={f1_val:.4f} (n={support})")
            lines.append("")
        return "\n".join(lines)


class ModelEvaluator:
    """
    统一模型评估器，支持 P0（二分类）和 P1（多分类）。

    使用方法：
        evaluator = ModelEvaluator()
        result = evaluator.evaluate_binary(model, X_test, y_test,
                                            model_name="XGBoost", variant="with_bp")
        result = evaluator.evaluate_multiclass(model, X_test, y_test,
                                                model_name="LightGBM", variant="full")
    """

    def __init__(self, n_calibration_bins: int = 10) -> None:
        self._n_cal_bins = n_calibration_bins

    def evaluate_binary(
        self,
        model: Any,
        X_test: np.ndarray,
        y_test: np.ndarray,
        model_name: str = "model",
        variant: str = "default",
        threshold_range: tuple[float, float] = (0.01, 0.99),
        n_dca_points: int = 50,
    ) -> EvaluationResult:
        """
        评估二分类模型（P0）。

        参数：
            model: 已训练分类器，需有 predict_proba
            X_test: 测试集特征
            y_test: 测试集标签 (0/1)
            model_name: 模型名称
            variant: 变体名称（with_bp / no_bp）
            threshold_range: DCA 阈值范围
            n_dca_points: DCA 阈值点数

        返回：
            EvaluationResult
        """
        y_test = np.array(y_test).astype(int)
        y_proba = model.predict_proba(X_test)[:, 1]

        # ROC 曲线
        fpr, tpr, roc_thresholds = roc_curve(y_test, y_proba)
        auc_roc = roc_auc_score(y_test, y_proba)

        # PR 曲线
        precision, recall, pr_thresholds = precision_recall_curve(y_test, y_proba)
        auprc = average_precision_score(y_test, y_proba)

        # Brier score
        brier = brier_score_loss(y_test, y_proba)

        # 最优阈值（Youden J = sensitivity + specificity - 1）
        j_scores = tpr - fpr
        optimal_idx = int(np.argmax(j_scores))
        optimal_threshold = float(roc_thresholds[optimal_idx])

        y_pred = (y_proba >= optimal_threshold).astype(int)
        tn = int(((y_pred == 0) & (y_test == 0)).sum())
        tp = int(((y_pred == 1) & (y_test == 1)).sum())
        fn = int(((y_pred == 0) & (y_test == 1)).sum())
        fp = int(((y_pred == 1) & (y_test == 0)).sum())

        sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
        f1 = f1_score(y_test, y_pred, zero_division=0)

        binary_metrics = BinaryMetrics(
            auc_roc=float(auc_roc),
            auprc=float(auprc),
            brier=float(brier),
            sensitivity=float(sensitivity),
            specificity=float(specificity),
            f1=float(f1),
            optimal_threshold=optimal_threshold,
            n_positive=int(y_test.sum()),
            n_negative=int((1 - y_test).sum()),
        )

        # 校准曲线
        n_bins = min(self._n_cal_bins, max(2, int(len(y_test) / 5)))
        try:
            frac_pos, mean_pred = calibration_curve(y_test, y_proba, n_bins=n_bins)
            cal_data = CalibrationData(
                fraction_of_positives=frac_pos.tolist(),
                mean_predicted_value=mean_pred.tolist(),
                n_bins=n_bins,
            )
        except Exception as e:
            logger.warning("校准曲线计算失败: %s", e)
            cal_data = None

        # DCA
        dca_data = self.decision_curve_analysis(
            y_test, y_proba,
            threshold_range=threshold_range,
            n_points=n_dca_points,
        )

        logger.info(
            "evaluate_binary [%s/%s]: AUC=%.4f, AUPRC=%.4f, Brier=%.4f",
            model_name, variant, auc_roc, auprc, brier,
        )

        return EvaluationResult(
            model_name=model_name,
            task="p0",
            variant=variant,
            binary_metrics=binary_metrics,
            multiclass_metrics=None,
            calibration_data=cal_data,
            dca_data=dca_data,
            roc_curve_data={
                "fpr": fpr.tolist(),
                "tpr": tpr.tolist(),
                "thresholds": roc_thresholds.tolist(),
            },
            pr_curve_data={
                "precision": precision.tolist(),
                "recall": recall.tolist(),
                "thresholds": pr_thresholds.tolist(),
            },
        )

    def evaluate_multiclass(
        self,
        model: Any,
        X_test: np.ndarray,
        y_test: np.ndarray,
        model_name: str = "model",
        variant: str = "default",
        class_names: Optional[list[str]] = None,
    ) -> EvaluationResult:
        """
        评估多分类模型（P1）。

        参数：
            model: 已训练分类器
            X_test: 测试集特征
            y_test: 测试集标签 (0/1/2)
            class_names: 类别名称列表（默认 ["green", "yellow", "red"]）

        返回：
            EvaluationResult
        """
        if class_names is None:
            class_names = ["green", "yellow", "red"]

        y_test = np.array(y_test).astype(int)
        y_pred = model.predict(X_test)

        f1_macro = float(f1_score(y_test, y_pred, average="macro", zero_division=0))
        kappa_weighted = float(cohen_kappa_score(y_test, y_pred, weights="linear"))
        accuracy = float(accuracy_score(y_test, y_pred))

        # per-class F1
        f1_per_class = f1_score(y_test, y_pred, average=None, zero_division=0)
        per_class_f1 = {
            class_names[i]: float(f1_per_class[i])
            for i in range(min(len(class_names), len(f1_per_class)))
        }

        # per-class support
        classes = np.unique(np.concatenate([y_test, y_pred]))
        per_class_support: dict[str, int] = {}
        for i, cls in enumerate(range(len(class_names))):
            name = class_names[i] if i < len(class_names) else str(cls)
            per_class_support[name] = int((y_test == cls).sum())

        # confusion matrix
        cm = confusion_matrix(y_test, y_pred, labels=list(range(len(class_names))))

        mc_metrics = MulticlassMetrics(
            f1_macro=f1_macro,
            kappa_weighted=kappa_weighted,
            accuracy=accuracy,
            per_class_f1=per_class_f1,
            per_class_support=per_class_support,
            confusion_matrix=cm.tolist(),
        )

        logger.info(
            "evaluate_multiclass [%s/%s]: F1_macro=%.4f, kappa=%.4f",
            model_name, variant, f1_macro, kappa_weighted,
        )

        return EvaluationResult(
            model_name=model_name,
            task="p1",
            variant=variant,
            binary_metrics=None,
            multiclass_metrics=mc_metrics,
            calibration_data=None,
            dca_data=None,
            roc_curve_data=None,
            pr_curve_data=None,
        )

    def decision_curve_analysis(
        self,
        y_true: np.ndarray,
        y_proba: np.ndarray,
        threshold_range: tuple[float, float] = (0.01, 0.99),
        n_points: int = 50,
    ) -> DCAData:
        """
        决策曲线分析（DCA）。

        净获益公式：
            NB = TP/N - FP/N × t/(1-t)

        其中 t 是决策阈值（愿意治疗的最低风险概率）。

        参数：
            y_true: 真实标签
            y_proba: 预测概率
            threshold_range: 阈值范围 (min, max)
            n_points: 阈值点数

        返回：
            DCAData
        """
        thresholds = np.linspace(threshold_range[0], threshold_range[1], n_points)
        n = len(y_true)

        nb_model = []
        nb_treat_all = []
        nb_treat_none = [0.0] * n_points

        for t in thresholds:
            # 模型净获益
            y_pred_t = (y_proba >= t).astype(int)
            tp = ((y_pred_t == 1) & (y_true == 1)).sum()
            fp = ((y_pred_t == 1) & (y_true == 0)).sum()
            if (1 - t) < 1e-10:
                nb_model.append(0.0)
            else:
                nb_model.append(float(tp / n - fp / n * t / (1 - t)))

            # 全治疗净获益（所有人都治疗）
            tp_all = y_true.sum()
            fp_all = (1 - y_true).sum()
            if (1 - t) < 1e-10:
                nb_treat_all.append(0.0)
            else:
                nb_treat_all.append(float(tp_all / n - fp_all / n * t / (1 - t)))

        return DCAData(
            thresholds=thresholds.tolist(),
            net_benefit_model=nb_model,
            net_benefit_treat_all=nb_treat_all,
            net_benefit_treat_none=nb_treat_none,
        )
