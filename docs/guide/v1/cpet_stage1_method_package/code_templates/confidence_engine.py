"""
confidence_engine.py
---------------------------------
Stage I-B 置信度与 indeterminate 逻辑模板。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_completeness_score(
    df: pd.DataFrame,
    *,
    reserve_fields: list[str],
    ventilatory_fields: list[str],
    instability_fields: list[str],
) -> pd.Series:
    """核心字段覆盖率。"""
    required = len(reserve_fields) + len(ventilatory_fields) + len(instability_fields)
    if required == 0:
        raise ValueError("No fields supplied to completeness score")

    available = (
        df[reserve_fields].notna().sum(axis=1)
        + df[ventilatory_fields].notna().sum(axis=1)
        + df[instability_fields].notna().sum(axis=1)
    )
    return available / required


def compute_anchor_agreement(
    external_zone: pd.Series,
    internal_zone: pd.Series,
) -> pd.Series:
    """
    same      -> 1.0
    adjacent  -> 0.5
    discordant-> 0.0
    """
    order = {"green": 0, "yellow": 1, "red": 2}
    a = external_zone.map(order)
    b = internal_zone.map(order)

    out = pd.Series(0.5, index=external_zone.index, dtype=float)
    valid = a.notna() & b.notna()

    diff = (a - b).abs()
    out.loc[valid & (diff == 0)] = 1.0
    out.loc[valid & (diff == 1)] = 0.5
    out.loc[valid & (diff >= 2)] = 0.0
    return out


def compute_validation_agreement(
    zone: pd.Series,
    outcome_risk_tertile: pd.Series,
) -> pd.Series:
    """
    将最终分区与 outcome model 风险三分位比对。
    tertile 约定：
        low / mid / high
    """
    zone_map = {"green": 0, "yellow": 1, "red": 2}
    tertile_map = {"low": 0, "mid": 1, "high": 2}

    a = zone.map(zone_map)
    b = outcome_risk_tertile.map(tertile_map)

    out = pd.Series(0.5, index=zone.index, dtype=float)  # 缺失时给中性分
    valid = a.notna() & b.notna()
    diff = (a - b).abs()

    out.loc[valid & (diff == 0)] = 1.0
    out.loc[valid & (diff == 1)] = 0.5
    out.loc[valid & (diff >= 2)] = 0.0
    return out


def compute_confidence(
    completeness: pd.Series,
    effort_score: pd.Series,
    anchor_agreement: pd.Series,
    validation_agreement: pd.Series,
) -> pd.Series:
    """主置信度公式。"""
    return (
        0.40 * completeness.fillna(0.0)
        + 0.15 * effort_score.fillna(0.5)
        + 0.20 * anchor_agreement.fillna(0.5)
        + 0.25 * validation_agreement.fillna(0.5)
    )


def label_confidence(score: pd.Series) -> pd.Series:
    """将置信度数值分层。"""
    out = pd.Series(index=score.index, dtype="object")
    out[score >= 0.75] = "high"
    out[(score >= 0.60) & (score < 0.75)] = "medium"
    out[score < 0.60] = "low"
    out[score.isna()] = np.nan
    return out


def finalize_zone_with_uncertainty(
    zone_before_confidence: pd.Series,
    confidence_score: pd.Series,
    instability_severe: pd.Series,
) -> pd.DataFrame:
    """
    severe instability 不允许被 confidence 冲掉；
    其余样本若 confidence 过低，则进入 yellow_gray / indeterminate。
    """
    out = pd.DataFrame(index=zone_before_confidence.index)
    out["confidence_score"] = confidence_score
    out["confidence_label"] = label_confidence(confidence_score)

    severe = instability_severe.fillna(False)
    low_conf = confidence_score < 0.60

    final_zone = zone_before_confidence.astype("object").copy()
    final_zone[~severe & low_conf] = "yellow_gray"

    out["indeterminate_flag"] = (~severe) & low_conf
    out["final_zone"] = final_zone
    return out
