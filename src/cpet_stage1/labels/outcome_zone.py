"""
outcome_zone.py — Phase G Method 1：结局锚定安全区（概率→区间转换）

核心设计：
  将 train_outcome.py 输出的校准概率 P(阳性|特征) 转换为三区安全区（Green/Yellow/Red），
  切点通过 Youden's J + DCA net benefit 联合优化。

安全区定义：
  Green:  P < low_cut    （低风险，临床结局阳性概率低）
  Yellow: low_cut ≤ P < high_cut（中间区，需关注）
  Red:    P ≥ high_cut   （高风险，临床结局阳性概率高）

优势（vs P1 规则标签）：
  - 无循环依赖：test_result 不由 vo2_peak_pct_pred 等字段确定性定义
  - 所有 CPET 指标均可作为特征（含 vo2_peak_pct_pred、ve_vco2_slope、eih_status）
  - 安全区有真实临床锚定（临床医生综合判断 = test_result）
  - 校准概率提供连续风险度量，SHAP 可解释驱动因素
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

ZONE_LABELS = {0: "green", 1: "yellow", 2: "red"}
ZONE_NUMERIC = {"green": 0, "yellow": 1, "red": 2}


@dataclass
class OutcomeZoneCutpoints:
    """结局锚定安全区切点。"""
    low_cut: float               # Green/Yellow 界（P < low_cut → Green）
    high_cut: float              # Yellow/Red 界（P ≥ high_cut → Red）
    method: str                  # "youden_dca" | "sensitivity_constrained" | "fixed"
    sensitivity_at_low: float = float("nan")   # Green/Yellow 界处的敏感度
    specificity_at_low: float = float("nan")
    youden_j: float = float("nan")             # Yellow/Red 界处的 Youden J
    sensitivity_at_high: float = float("nan")
    specificity_at_high: float = float("nan")
    n_positive: int = 0
    n_total: int = 0

    def to_dict(self) -> dict:
        return {
            "low_cut": self.low_cut,
            "high_cut": self.high_cut,
            "method": self.method,
            "sensitivity_at_low": self.sensitivity_at_low,
            "specificity_at_low": self.specificity_at_low,
            "youden_j": self.youden_j,
            "sensitivity_at_high": self.sensitivity_at_high,
            "specificity_at_high": self.specificity_at_high,
            "n_positive": self.n_positive,
            "n_total": self.n_total,
        }


def compute_outcome_cutpoints(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    min_sensitivity: float = 0.90,
    n_thresholds: int = 200,
) -> OutcomeZoneCutpoints:
    """
    计算结局锚定安全区切点。

    参数：
        y_true: 二分类标签（1=阳性/可疑阳性, 0=阴性）
        y_proba: 阳性类校准概率
        min_sensitivity: Green/Yellow 界处最低敏感度约束（默认 0.90）
        n_thresholds: 扫描切点数量

    返回：
        OutcomeZoneCutpoints
    """
    thresholds = np.linspace(0.0, 1.0, n_thresholds + 1)
    n_pos = int(np.sum(y_true))
    n_total = len(y_true)

    if n_pos == 0 or n_pos == n_total:
        logger.warning("compute_outcome_cutpoints: 标签无变化，使用固定切点（0.10/0.25）")
        return OutcomeZoneCutpoints(
            low_cut=0.10, high_cut=0.25, method="fixed",
            n_positive=n_pos, n_total=n_total,
        )

    sens_arr = np.zeros(len(thresholds))
    spec_arr = np.zeros(len(thresholds))
    for i, t in enumerate(thresholds):
        pred = (y_proba >= t).astype(int)
        tp = np.sum((pred == 1) & (y_true == 1))
        tn = np.sum((pred == 0) & (y_true == 0))
        fp = np.sum((pred == 1) & (y_true == 0))
        fn = np.sum((pred == 0) & (y_true == 1))
        sens_arr[i] = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        spec_arr[i] = tn / (tn + fp) if (tn + fp) > 0 else 0.0

    # ── Green/Yellow 界：最大化特异度，约束 sens ≥ min_sensitivity ──────────────
    valid_low = np.where(sens_arr >= min_sensitivity)[0]
    if len(valid_low) == 0:
        # 退化：取 sens 最大的阈值
        low_idx = int(np.argmax(sens_arr))
    else:
        # 在满足敏感度约束的阈值中，取特异度最大的
        low_idx = valid_low[int(np.argmax(spec_arr[valid_low]))]

    low_cut = float(thresholds[low_idx])

    # ── Yellow/Red 界：Youden's J 最优（仅在 > low_cut 的阈值中搜索）────────────
    high_candidates = np.where(thresholds > low_cut)[0]
    if len(high_candidates) == 0:
        high_cut = min(low_cut + 0.15, 1.0)
        high_idx = int(np.argmin(np.abs(thresholds - high_cut)))
    else:
        youden = sens_arr[high_candidates] + spec_arr[high_candidates] - 1.0
        best = high_candidates[int(np.argmax(youden))]
        high_idx = int(best)

    high_cut = float(thresholds[high_idx])

    return OutcomeZoneCutpoints(
        low_cut=low_cut,
        high_cut=high_cut,
        method="sensitivity_constrained_youden",
        sensitivity_at_low=float(sens_arr[low_idx]),
        specificity_at_low=float(spec_arr[low_idx]),
        youden_j=float(sens_arr[high_idx] + spec_arr[high_idx] - 1.0),
        sensitivity_at_high=float(sens_arr[high_idx]),
        specificity_at_high=float(spec_arr[high_idx]),
        n_positive=n_pos,
        n_total=n_total,
    )


def assign_outcome_zones(
    y_proba: np.ndarray,
    cutpoints: OutcomeZoneCutpoints,
) -> np.ndarray:
    """
    将校准概率转换为安全区标签（0=green, 1=yellow, 2=red）。

    参数：
        y_proba: 阳性类校准概率（shape: [n_samples]）
        cutpoints: OutcomeZoneCutpoints

    返回：
        zone_labels: int 数组（0/1/2）
    """
    zones = np.ones(len(y_proba), dtype=int)  # 默认 yellow
    zones[y_proba < cutpoints.low_cut] = 0    # green
    zones[y_proba >= cutpoints.high_cut] = 2  # red
    return zones


def assign_outcome_zones_series(
    proba_series: pd.Series,
    cutpoints: OutcomeZoneCutpoints,
) -> pd.Series:
    """
    将 pd.Series 格式的概率转换为安全区标签字符串（"green"/"yellow"/"red"）。
    """
    zones_int = assign_outcome_zones(proba_series.values, cutpoints)
    zones_str = pd.Series(
        [ZONE_LABELS[z] for z in zones_int],
        index=proba_series.index,
        name="outcome_zone",
    )
    return zones_str


def compute_zone_distribution(
    zone_series: pd.Series,
    outcome_series: Optional[pd.Series] = None,
) -> dict:
    """
    计算安全区分布统计（含阳性率）。

    参数：
        zone_series: 安全区标签（"green"/"yellow"/"red"）
        outcome_series: test_result 二分类（可选，用于计算各区阳性率）

    返回：
        distribution dict
    """
    total = len(zone_series)
    dist: dict = {"total": total}

    for z in ["green", "yellow", "red"]:
        mask = zone_series == z
        n = int(mask.sum())
        dist[z] = {
            "n": n,
            "pct": round(n / total * 100, 1) if total > 0 else 0.0,
        }
        if outcome_series is not None:
            pos_in_zone = int(outcome_series[mask].sum()) if n > 0 else 0
            dist[z]["positive_rate"] = round(pos_in_zone / n * 100, 1) if n > 0 else 0.0

    return dist
