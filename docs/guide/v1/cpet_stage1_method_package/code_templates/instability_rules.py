"""
instability_rules.py
---------------------------------
Stage I-B 不稳定覆盖规则模板。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class Rule:
    field: str
    op: str
    value: Any | None = None
    low: float | None = None
    high: float | None = None


def evaluate_rule(df: pd.DataFrame, rule: Rule) -> pd.Series:
    """执行单条规则，返回布尔 Series。"""
    s = df.get(rule.field)
    if s is None:
        return pd.Series(False, index=df.index)

    if rule.op == "eq":
        return s == rule.value
    if rule.op == "gt":
        return pd.to_numeric(s, errors="coerce") > float(rule.value)
    if rule.op == "in":
        return s.isin(rule.value)
    if rule.op == "between_open_closed":
        x = pd.to_numeric(s, errors="coerce")
        return (x > float(rule.low)) & (x <= float(rule.high))

    raise ValueError(f"Unsupported op: {rule.op!r}")


def evaluate_instability(
    df: pd.DataFrame,
    severe_rules: list[Rule],
    mild_rules: list[Rule],
) -> pd.DataFrame:
    """汇总 severe / mild instability。"""
    out = pd.DataFrame(index=df.index)
    severe = pd.Series(False, index=df.index)
    mild = pd.Series(False, index=df.index)

    for rule in severe_rules:
        severe = severe | evaluate_rule(df, rule)
    for rule in mild_rules:
        mild = mild | evaluate_rule(df, rule)

    out["instability_severe"] = severe
    out["instability_mild"] = mild & (~severe)
    return out


def apply_override(
    phenotype_zone: pd.Series,
    instability_df: pd.DataFrame,
) -> pd.Series:
    """
    severe:
        any phenotype -> red
    mild:
        green -> yellow
        yellow/red stay unchanged
    """
    final_zone = phenotype_zone.astype("object").copy()

    severe = instability_df["instability_severe"].fillna(False)
    mild = instability_df["instability_mild"].fillna(False)

    final_zone[severe] = "red"
    final_zone[mild & (final_zone == "green")] = "yellow"
    return final_zone
