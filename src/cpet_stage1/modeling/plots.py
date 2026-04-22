"""
plots.py — M5 模型可视化模块（matplotlib Agg 无头渲染）。

提供：
- plot_roc_curve(): ROC 曲线
- plot_precision_recall_curve(): PR 曲线
- plot_calibration_curve(): 校准曲线
- plot_dca(): 决策曲线
- plot_confusion_matrix(): 混淆矩阵
- plot_bp_variant_comparison(): BP 双版本对比
- plot_cycle_consistency(): 踏车一致性对比
- generate_all_m5_plots(): 批量生成所有 M5 图表
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)

# 颜色方案
ZONE_COLORS = {"green": "#2ecc71", "yellow": "#f39c12", "red": "#e74c3c"}
MODEL_COLORS = {"lasso": "#3498db", "xgb": "#e74c3c", "ordinal_logistic": "#9b59b6",
                "lgbm": "#2ecc71", "catboost": "#f39c12"}


def plot_roc_curve(
    roc_data: dict[str, Any],
    auc_roc: float,
    model_name: str = "Model",
    save_path: Optional[str | Path] = None,
    ax: Optional[plt.Axes] = None,
) -> plt.Figure:
    """
    绘制 ROC 曲线。

    参数：
        roc_data: {"fpr": [...], "tpr": [...]}
        auc_roc: AUC-ROC 值
        model_name: 图例标签
    """
    fig = None
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 5))

    fpr = roc_data.get("fpr", [0, 1])
    tpr = roc_data.get("tpr", [0, 1])

    ax.plot(fpr, tpr, color="#e74c3c", lw=2,
            label=f"{model_name} (AUC={auc_roc:.3f})")
    ax.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.5, label="Random")
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.02])
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title(f"ROC Curve — {model_name}")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.3)

    if fig is not None:
        plt.tight_layout()
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(save_path, dpi=150, bbox_inches="tight")
            logger.info("ROC 曲线保存: %s", save_path)
        return fig
    return ax.get_figure()


def plot_precision_recall_curve(
    pr_data: dict[str, Any],
    auprc: float,
    model_name: str = "Model",
    save_path: Optional[str | Path] = None,
    ax: Optional[plt.Axes] = None,
) -> plt.Figure:
    """绘制 PR 曲线。"""
    fig = None
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 5))

    precision = pr_data.get("precision", [1, 0])
    recall = pr_data.get("recall", [0, 1])

    ax.plot(recall, precision, color="#3498db", lw=2,
            label=f"{model_name} (AUPRC={auprc:.3f})")
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1.02])
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title(f"Precision-Recall Curve — {model_name}")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)

    if fig is not None:
        plt.tight_layout()
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(save_path, dpi=150, bbox_inches="tight")
        return fig
    return ax.get_figure()


def plot_calibration_curve(
    cal_data: Any,
    model_name: str = "Model",
    save_path: Optional[str | Path] = None,
    ax: Optional[plt.Axes] = None,
) -> plt.Figure:
    """绘制校准曲线。"""
    fig = None
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 5))

    if cal_data is None:
        ax.text(0.5, 0.5, "无校准数据", transform=ax.transAxes,
                ha="center", va="center")
    else:
        frac_pos = cal_data.fraction_of_positives
        mean_pred = cal_data.mean_predicted_value
        ax.plot([0, 1], [0, 1], "k--", lw=1, label="Perfect calibration")
        ax.plot(mean_pred, frac_pos, "s-", color="#e74c3c", lw=2,
                label=f"{model_name}")

    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1])
    ax.set_xlabel("Mean Predicted Probability")
    ax.set_ylabel("Fraction of Positives")
    ax.set_title(f"Calibration Curve — {model_name}")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    if fig is not None:
        plt.tight_layout()
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(save_path, dpi=150, bbox_inches="tight")
        return fig
    return ax.get_figure()


def plot_dca(
    dca_data: Any,
    model_name: str = "Model",
    save_path: Optional[str | Path] = None,
    ax: Optional[plt.Axes] = None,
) -> plt.Figure:
    """绘制决策曲线分析（DCA）图。"""
    fig = None
    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 5))

    if dca_data is None:
        ax.text(0.5, 0.5, "无 DCA 数据", transform=ax.transAxes,
                ha="center", va="center")
    else:
        t = dca_data.thresholds
        ax.plot(t, dca_data.net_benefit_model, color="#e74c3c", lw=2,
                label=f"{model_name}")
        ax.plot(t, dca_data.net_benefit_treat_all, "b--", lw=1.5,
                label="Treat All")
        ax.plot(t, dca_data.net_benefit_treat_none, "k-", lw=1,
                label="Treat None")
        ax.set_xlim([min(t), max(t)])

    ax.set_xlabel("Threshold Probability")
    ax.set_ylabel("Net Benefit")
    ax.set_title(f"Decision Curve Analysis — {model_name}")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    if fig is not None:
        plt.tight_layout()
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(save_path, dpi=150, bbox_inches="tight")
        return fig
    return ax.get_figure()


def plot_confusion_matrix(
    cm: list[list[int]],
    class_names: Optional[list[str]] = None,
    model_name: str = "Model",
    save_path: Optional[str | Path] = None,
    ax: Optional[plt.Axes] = None,
) -> plt.Figure:
    """绘制混淆矩阵热力图。"""
    if class_names is None:
        class_names = ["green", "yellow", "red"]

    fig = None
    if ax is None:
        fig, ax = plt.subplots(figsize=(5, 4))

    cm_arr = np.array(cm)
    im = ax.imshow(cm_arr, interpolation="nearest", cmap="Blues")
    plt.colorbar(im, ax=ax)

    tick_marks = np.arange(len(class_names))
    ax.set_xticks(tick_marks)
    ax.set_xticklabels(class_names, rotation=45, ha="right")
    ax.set_yticks(tick_marks)
    ax.set_yticklabels(class_names)

    thresh = cm_arr.max() / 2.0
    for i in range(cm_arr.shape[0]):
        for j in range(cm_arr.shape[1]):
            ax.text(j, i, format(cm_arr[i, j], "d"),
                    ha="center", va="center",
                    color="white" if cm_arr[i, j] > thresh else "black")

    ax.set_ylabel("True label")
    ax.set_xlabel("Predicted label")
    ax.set_title(f"Confusion Matrix — {model_name}")

    if fig is not None:
        plt.tight_layout()
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(save_path, dpi=150, bbox_inches="tight")
        return fig
    return ax.get_figure()


def plot_bp_variant_comparison(
    with_bp_metrics: dict[str, float],
    no_bp_metrics: dict[str, float],
    model_name: str = "Model",
    save_path: Optional[str | Path] = None,
) -> plt.Figure:
    """
    绘制含 BP / 不含 BP 双版本对比条形图。

    参数：
        with_bp_metrics: {"AUC-ROC": 0.80, "AUPRC": 0.65, "Brier": 0.12}
        no_bp_metrics: 同上
    """
    metrics = list(with_bp_metrics.keys())
    x = np.arange(len(metrics))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    bars1 = ax.bar(x - width / 2, [with_bp_metrics[m] for m in metrics],
                   width, label="With BP", color="#3498db", alpha=0.8)
    bars2 = ax.bar(x + width / 2, [no_bp_metrics[m] for m in metrics],
                   width, label="No BP", color="#e74c3c", alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylim([0, 1.05])
    ax.set_ylabel("Score")
    ax.set_title(f"BP Variant Comparison — {model_name}")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)

    plt.tight_layout()
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        logger.info("BP 对比图保存: %s", save_path)
    return fig


def plot_cycle_consistency(
    full_metrics: dict[str, float],
    cycle_metrics: dict[str, float],
    model_name: str = "Model",
    save_path: Optional[str | Path] = None,
) -> plt.Figure:
    """绘制踏车子集 vs 全样本一致性对比图。"""
    metrics = list(full_metrics.keys())
    x = np.arange(len(metrics))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x - width / 2, [full_metrics[m] for m in metrics],
           width, label="Full Sample", color="#2ecc71", alpha=0.8)
    ax.bar(x + width / 2, [cycle_metrics[m] for m in metrics],
           width, label="Cycle Only", color="#9b59b6", alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylim([0, 1.05])
    ax.set_ylabel("Score")
    ax.set_title(f"Cycle Consistency — {model_name}")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)

    plt.tight_layout()
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def generate_all_m5_plots(
    p0_results: Optional[dict] = None,
    p1_results: Optional[dict] = None,
    output_dir: str | Path = "reports/figures/m5",
) -> list[str]:
    """
    批量生成所有 M5 图表。

    参数：
        p0_results: P0Trainer.run() 返回的结果字典
        p1_results: P1Trainer.run() 返回的结果字典
        output_dir: 输出目录

    返回：
        生成的文件路径列表
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    # P0 图表
    if p0_results:
        for model_name, variants in p0_results.items():
            for variant, result in variants.items():
                eval_r = result.test_metrics
                bm = eval_r.binary_metrics

                # ROC 曲线
                if eval_r.roc_curve_data and bm:
                    save_path = output_dir / f"p0_roc_{model_name}_{variant}.png"
                    try:
                        plot_roc_curve(
                            eval_r.roc_curve_data, bm.auc_roc,
                            model_name=f"P0 {model_name}", save_path=save_path
                        )
                        generated.append(str(save_path))
                    except Exception as e:
                        logger.warning("ROC 图生成失败 [%s/%s]: %s", model_name, variant, e)

                # PR 曲线
                if eval_r.pr_curve_data and bm:
                    save_path = output_dir / f"p0_pr_{model_name}_{variant}.png"
                    try:
                        plot_precision_recall_curve(
                            eval_r.pr_curve_data, bm.auprc,
                            model_name=f"P0 {model_name}", save_path=save_path
                        )
                        generated.append(str(save_path))
                    except Exception as e:
                        logger.warning("PR 图生成失败: %s", e)

                # 校准曲线
                if eval_r.calibration_data:
                    save_path = output_dir / f"p0_calibration_{model_name}_{variant}.png"
                    try:
                        plot_calibration_curve(
                            eval_r.calibration_data,
                            model_name=f"P0 {model_name}", save_path=save_path
                        )
                        generated.append(str(save_path))
                    except Exception as e:
                        logger.warning("校准图生成失败: %s", e)

                # DCA
                if eval_r.dca_data:
                    save_path = output_dir / f"p0_dca_{model_name}_{variant}.png"
                    try:
                        plot_dca(
                            eval_r.dca_data,
                            model_name=f"P0 {model_name}", save_path=save_path
                        )
                        generated.append(str(save_path))
                    except Exception as e:
                        logger.warning("DCA 图生成失败: %s", e)

            # BP 对比图（若两个变体都存在）
            if "with_bp" in variants and "no_bp" in variants:
                save_path = output_dir / f"p0_bp_comparison_{model_name}.png"
                try:
                    bm_with = variants["with_bp"].test_metrics.binary_metrics
                    bm_no = variants["no_bp"].test_metrics.binary_metrics
                    if bm_with and bm_no:
                        plot_bp_variant_comparison(
                            {"AUC-ROC": bm_with.auc_roc, "AUPRC": bm_with.auprc, "Brier": bm_with.brier},
                            {"AUC-ROC": bm_no.auc_roc, "AUPRC": bm_no.auprc, "Brier": bm_no.brier},
                            model_name=f"P0 {model_name}", save_path=save_path
                        )
                        generated.append(str(save_path))
                except Exception as e:
                    logger.warning("BP 对比图生成失败: %s", e)

    # P1 图表
    if p1_results:
        for model_name, variants in p1_results.items():
            for variant, result in variants.items():
                eval_r = result.test_metrics
                mc = eval_r.multiclass_metrics

                # 混淆矩阵
                if mc and mc.confusion_matrix:
                    save_path = output_dir / f"p1_cm_{model_name}_{variant}.png"
                    try:
                        plot_confusion_matrix(
                            mc.confusion_matrix,
                            model_name=f"P1 {model_name}", save_path=save_path
                        )
                        generated.append(str(save_path))
                    except Exception as e:
                        logger.warning("混淆矩阵图生成失败: %s", e)

            # 一致性对比图
            if "full" in variants and "cycle_only" in variants:
                save_path = output_dir / f"p1_cycle_consistency_{model_name}.png"
                try:
                    mc_full = variants["full"].test_metrics.multiclass_metrics
                    mc_cycle = variants["cycle_only"].test_metrics.multiclass_metrics
                    if mc_full and mc_cycle:
                        plot_cycle_consistency(
                            {"F1_macro": mc_full.f1_macro, "Kappa": mc_full.kappa_weighted, "Accuracy": mc_full.accuracy},
                            {"F1_macro": mc_cycle.f1_macro, "Kappa": mc_cycle.kappa_weighted, "Accuracy": mc_cycle.accuracy},
                            model_name=f"P1 {model_name}", save_path=save_path
                        )
                        generated.append(str(save_path))
                except Exception as e:
                    logger.warning("一致性对比图生成失败: %s", e)

    logger.info("M5 图表生成完成: %d 张", len(generated))
    return generated
