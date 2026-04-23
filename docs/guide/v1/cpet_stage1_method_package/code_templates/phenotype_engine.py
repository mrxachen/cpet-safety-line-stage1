"""
phenotype_engine.py
---------------------------------
Stage I-B 主体表型引擎模板。

职责：
1. 根据 reference quantiles 将单变量转成 burden
2. 聚合 Reserve / Ventilatory 两个域
3. 计算 p_lab
4. 依据 reference subset 上 p_lab 的分布给出 phenotype zone
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


Direction = Literal["higher_better", "higher_worse"]


@dataclass
class VariableSpec:
    field: str
    direction: Direction
    domain: Literal["reserve", "ventilatory"]
    required: bool = False


def compute_variable_burden(
    values: pd.Series,
    quantiles: pd.DataFrame,
    *,
    field: str,
    direction: Direction,
) -> pd.Series:
    """
    将单变量转换为 0/0.5/1.0 burden。

    higher_better:
        >= q25  -> 0
        q10-q25 -> 0.5
        < q10   -> 1

    higher_worse:
        <= q75  -> 0
        q75-q90 -> 0.5
        > q90   -> 1
    """
    q10 = quantiles[f"{field}_q10"]
    q25 = quantiles[f"{field}_q25"]
    q75 = quantiles[f"{field}_q75"]
    q90 = quantiles[f"{field}_q90"]

    x = pd.to_numeric(values, errors="coerce")
    out = pd.Series(np.nan, index=values.index, dtype=float)

    if direction == "higher_better":
        out[(x >= q25)] = 0.0
        out[(x < q25) & (x >= q10)] = 0.5
        out[(x < q10)] = 1.0
    elif direction == "higher_worse":
        out[(x <= q75)] = 0.0
        out[(x > q75) & (x <= q90)] = 0.5
        out[(x > q90)] = 1.0
    else:
        raise ValueError(f"Unknown direction: {direction!r}")

    return out


def _domain_mean(df: pd.DataFrame, fields: list[str], *, min_available: int) -> pd.Series:
    """按行取均值，并对可用数量不足的样本返回 NaN。"""
    available = df[fields].notna().sum(axis=1)
    score = df[fields].mean(axis=1, skipna=True)
    score[available < min_available] = np.nan
    return score


def estimate_cutpoints_from_reference(
    p_lab: pd.Series,
    reference_mask: pd.Series,
    *,
    low_pct: float = 75.0,
    high_pct: float = 90.0,
) -> tuple[float, float]:
    """根据 reference subset 的 p_lab 分布估计 phenotype cutpoints。"""
    ref = pd.to_numeric(p_lab[reference_mask], errors="coerce").dropna()
    if len(ref) < 30:
        raise ValueError("Reference subset too small for p_lab cutpoint estimation")
    return float(np.percentile(ref, low_pct)), float(np.percentile(ref, high_pct))


def assign_zone(p_lab: pd.Series, low_cut: float, high_cut: float) -> pd.Series:
    """根据 low/high cutpoint 分配 phenotype zone。"""
    out = pd.Series(index=p_lab.index, dtype="object")
    out[p_lab < low_cut] = "green"
    out[(p_lab >= low_cut) & (p_lab < high_cut)] = "yellow"
    out[p_lab >= high_cut] = "red"
    out[p_lab.isna()] = np.nan
    return out


def run_phenotype_engine(
    df: pd.DataFrame,
    quantiles: pd.DataFrame,
    variable_specs: list[VariableSpec],
    reference_mask: pd.Series,
) -> pd.DataFrame:
    """
    主入口：
    - 计算单变量 burden
    - 聚合 reserve / ventilatory burden
    - 计算 p_lab
    - 估计 phenotype cutpoints
    - 返回 phenotype zone
    """
    work = pd.DataFrame(index=df.index)

    reserve_fields: list[str] = []
    vent_fields: list[str] = []

    for spec in variable_specs:
        burden_col = f"{spec.field}_burden"
        work[burden_col] = compute_variable_burden(
            df[spec.field],
            quantiles,
            field=spec.field,
            direction=spec.direction,
        )
        if spec.domain == "reserve":
            reserve_fields.append(burden_col)
        else:
            vent_fields.append(burden_col)

    work["reserve_burden"] = _domain_mean(work, reserve_fields, min_available=2)
    work["vent_burden"] = _domain_mean(work, vent_fields, min_available=1)

    work["p_lab"] = 0.5 * work["reserve_burden"] + 0.5 * work["vent_burden"]

    low_cut, high_cut = estimate_cutpoints_from_reference(
        work["p_lab"], reference_mask, low_pct=75.0, high_pct=90.0
    )
    work["phenotype_zone"] = assign_zone(work["p_lab"], low_cut, high_cut)

    work.attrs["phenotype_cutpoints"] = {"low_cut": low_cut, "high_cut": high_cut}
    return work
