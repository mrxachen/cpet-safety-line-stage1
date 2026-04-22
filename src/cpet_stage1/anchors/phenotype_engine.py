"""
phenotype_engine.py — Stage 1B 主体表型引擎。

职责：
1. 根据 reference quantiles 将单变量转成 0/0.5/1.0 burden
2. 聚合 Reserve / Ventilatory 两个域的 burden 分数
3. 计算 p_lab = 0.5 * reserve_burden + 0.5 * vent_burden
4. 依据 reference subset 上 p_lab 的分布估计 phenotype cutpoints
5. 生成 phenotype zone（green/yellow/red）

适配说明：
    模板来源：docs/guide/cpet_stage1_method_package/code_templates/phenotype_engine.py
    在模板基础上增加：
    - 配置文件驱动（zone_rules_stage1b.yaml）
    - VariableSpec 从 yaml 加载
    - 报告生成
    - 缺失值处理细节
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

Direction = Literal["higher_better", "higher_worse"]


@dataclass
class VariableSpec:
    """单变量规格（与 zone_rules_stage1b.yaml 对应）。"""
    field: str
    direction: Direction
    domain: Literal["reserve", "ventilatory"]
    required: bool = False


@dataclass
class PhenotypeResult:
    """表型引擎输出结果。"""
    df: pd.DataFrame                   # 含所有 burden 列 + phenotype_zone
    cutpoints: dict[str, float]        # {"low_cut": ..., "high_cut": ...}
    variable_specs: list[VariableSpec]
    n_green: int = 0
    n_yellow: int = 0
    n_red: int = 0
    n_missing: int = 0

    def summary(self) -> str:
        n = len(self.df)
        lines = [
            "PhenotypeEngine Summary",
            f"  Total: {n}",
            f"  Green:   {self.n_green} ({100*self.n_green/n:.1f}%)",
            f"  Yellow:  {self.n_yellow} ({100*self.n_yellow/n:.1f}%)",
            f"  Red:     {self.n_red} ({100*self.n_red/n:.1f}%)",
            f"  Missing: {self.n_missing} ({100*self.n_missing/n:.1f}%)",
            f"  Cutpoints: low_cut={self.cutpoints.get('low_cut', 'N/A'):.3f}, "
            f"high_cut={self.cutpoints.get('high_cut', 'N/A'):.3f}",
        ]
        return "\n".join(lines)


def compute_variable_burden(
    values: pd.Series,
    quantiles: pd.DataFrame,
    *,
    field: str,
    direction: Direction,
) -> pd.Series:
    """
    将单变量转换为 0/0.5/1.0 burden。

    higher_better：
        >= q25  -> 0.0
        q10 <= x < q25 -> 0.5
        < q10   -> 1.0

    higher_worse：
        <= q75  -> 0.0
        q75 < x <= q90 -> 0.5
        > q90   -> 1.0

    缺失处理：原始值 NaN -> burden NaN（不强行填充，由域聚合处理）
    分位列不存在：所有值返回 NaN（跳过该变量）
    """
    # 检查分位列是否存在
    if direction == "higher_better":
        q_needed = [f"{field}_q10", f"{field}_q25"]
    else:
        q_needed = [f"{field}_q75", f"{field}_q90"]

    missing_cols = [c for c in q_needed if c not in quantiles.columns]
    if missing_cols:
        logger.warning("Quantile columns missing for %r: %s — returning NaN burden", field, missing_cols)
        return pd.Series(np.nan, index=values.index, dtype=float)

    x = pd.to_numeric(values, errors="coerce")
    out = pd.Series(np.nan, index=values.index, dtype=float)

    if direction == "higher_better":
        q10 = quantiles[f"{field}_q10"]
        q25 = quantiles[f"{field}_q25"]
        valid = x.notna() & q10.notna() & q25.notna()
        out.loc[valid & (x >= q25)] = 0.0
        out.loc[valid & (x < q25) & (x >= q10)] = 0.5
        out.loc[valid & (x < q10)] = 1.0

    elif direction == "higher_worse":
        q75 = quantiles[f"{field}_q75"]
        q90 = quantiles[f"{field}_q90"]
        valid = x.notna() & q75.notna() & q90.notna()
        out.loc[valid & (x <= q75)] = 0.0
        out.loc[valid & (x > q75) & (x <= q90)] = 0.5
        out.loc[valid & (x > q90)] = 1.0

    return out


def _domain_mean(df: pd.DataFrame, fields: list[str], *, min_available: int) -> pd.Series:
    """
    按行取均值，并对可用数量不足的样本返回 NaN。
    min_available：域内至少需要几个非 NaN 变量。
    """
    if not fields:
        return pd.Series(np.nan, index=df.index, dtype=float)

    available_cols = [c for c in fields if c in df.columns]
    if not available_cols:
        return pd.Series(np.nan, index=df.index, dtype=float)

    available_count = df[available_cols].notna().sum(axis=1)
    score = df[available_cols].mean(axis=1, skipna=True)
    score[available_count < min_available] = np.nan
    return score


def estimate_cutpoints_from_reference(
    p_lab: pd.Series,
    reference_mask: pd.Series,
    *,
    low_pct: float = 75.0,
    high_pct: float = 90.0,
    min_ref_n: int = 30,
) -> tuple[float, float]:
    """
    根据 reference subset 的 p_lab 分布估计 phenotype cutpoints。

    Returns (low_cut, high_cut)
    """
    ref = pd.to_numeric(p_lab[reference_mask], errors="coerce").dropna()
    if len(ref) < min_ref_n:
        raise ValueError(
            f"Reference subset too small for p_lab cutpoint estimation: n={len(ref)} < {min_ref_n}"
        )
    low_cut = float(np.percentile(ref, low_pct))
    high_cut = float(np.percentile(ref, high_pct))
    # 确保 low_cut < high_cut
    if low_cut >= high_cut:
        logger.warning(
            "low_cut (%.3f) >= high_cut (%.3f); adjusting high_cut slightly",
            low_cut, high_cut,
        )
        high_cut = low_cut + 1e-6
    return low_cut, high_cut


def assign_phenotype_zone(
    p_lab: pd.Series,
    low_cut: float,
    high_cut: float,
) -> pd.Series:
    """根据 low/high cutpoint 分配 phenotype zone（green/yellow/red）。"""
    out = pd.Series(index=p_lab.index, dtype="object")
    p = pd.to_numeric(p_lab, errors="coerce")
    out[p.notna() & (p < low_cut)] = "green"
    out[p.notna() & (p >= low_cut) & (p < high_cut)] = "yellow"
    out[p.notna() & (p >= high_cut)] = "red"
    out[p.isna()] = np.nan
    return out


def load_variable_specs_from_yaml(spec_path: str | Path) -> list[VariableSpec]:
    """从 zone_rules_stage1b.yaml 加载变量规格列表。"""
    path = Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(f"Zone rules not found: {path}")
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    specs: list[VariableSpec] = []
    variables_cfg = cfg.get("variables", {})

    for domain, domain_vars in variables_cfg.items():
        if domain not in ("reserve", "ventilatory"):
            continue
        for var_cfg in (domain_vars or []):
            specs.append(VariableSpec(
                field=var_cfg["field"],
                direction=var_cfg["direction"],
                domain=domain,
                required=var_cfg.get("required", False),
            ))

    return specs


def run_phenotype_engine(
    df: pd.DataFrame,
    quantiles: pd.DataFrame,
    variable_specs: list[VariableSpec],
    reference_mask: pd.Series,
    *,
    reserve_min_available: int = 2,
    ventilatory_min_available: int = 1,
    low_pct: float = 75.0,
    high_pct: float = 90.0,
) -> PhenotypeResult:
    """
    主入口：
    1. 计算单变量 burden
    2. 聚合 reserve / ventilatory burden
    3. 计算 p_lab
    4. 估计 phenotype cutpoints（在 reference subset 上）
    5. 分配 phenotype zone

    Parameters
    ----------
    df : 全量数据（或目标批次）
    quantiles : reference_quantiles.py 预测的分位 DataFrame（与 df 行对齐）
    variable_specs : 变量规格列表（reserve / ventilatory 域）
    reference_mask : reference subset 的 bool mask（用于估计切点）
    reserve_min_available : reserve 域至少需要几个非 NaN 变量
    ventilatory_min_available : ventilatory 域至少需要几个非 NaN 变量
    low_pct / high_pct : 参考子集 p_lab 的分位切点百分位
    """
    work = pd.DataFrame(index=df.index)

    reserve_burden_cols: list[str] = []
    vent_burden_cols: list[str] = []

    for spec in variable_specs:
        if spec.field not in df.columns:
            logger.debug("Field %r not in df, skipping burden computation", spec.field)
            continue

        burden_col = f"{spec.field}_burden"
        work[burden_col] = compute_variable_burden(
            df[spec.field],
            quantiles,
            field=spec.field,
            direction=spec.direction,
        )

        if spec.domain == "reserve":
            reserve_burden_cols.append(burden_col)
        elif spec.domain == "ventilatory":
            vent_burden_cols.append(burden_col)

    # 域内聚合
    work["reserve_burden"] = _domain_mean(
        work, reserve_burden_cols, min_available=reserve_min_available
    )
    work["vent_burden"] = _domain_mean(
        work, vent_burden_cols, min_available=ventilatory_min_available
    )

    # p_lab：只有两个域都有值时才计算
    both_available = work["reserve_burden"].notna() & work["vent_burden"].notna()
    one_available = (work["reserve_burden"].notna() | work["vent_burden"].notna()) & ~both_available

    p_lab = pd.Series(np.nan, index=df.index, dtype=float)
    p_lab[both_available] = (
        0.5 * work.loc[both_available, "reserve_burden"] +
        0.5 * work.loc[both_available, "vent_burden"]
    )
    # 仅有一个域时，使用该域的值（降 confidence，不强制为 NaN）
    p_lab[one_available & work["reserve_burden"].notna()] = work.loc[
        one_available & work["reserve_burden"].notna(), "reserve_burden"
    ]
    p_lab[one_available & work["vent_burden"].notna()] = work.loc[
        one_available & work["vent_burden"].notna(), "vent_burden"
    ]
    work["p_lab"] = p_lab

    # 切点估计
    low_cut, high_cut = estimate_cutpoints_from_reference(
        work["p_lab"], reference_mask, low_pct=low_pct, high_pct=high_pct
    )

    # Zone 分配
    work["phenotype_zone"] = assign_phenotype_zone(work["p_lab"], low_cut, high_cut)

    # 统计
    zone_counts = work["phenotype_zone"].value_counts(dropna=False)
    n_green = int(zone_counts.get("green", 0))
    n_yellow = int(zone_counts.get("yellow", 0))
    n_red = int(zone_counts.get("red", 0))
    n_missing = int(work["phenotype_zone"].isna().sum())

    result = PhenotypeResult(
        df=work,
        cutpoints={"low_cut": low_cut, "high_cut": high_cut},
        variable_specs=variable_specs,
        n_green=n_green,
        n_yellow=n_yellow,
        n_red=n_red,
        n_missing=n_missing,
    )

    logger.info(
        "PhenotypeEngine: green=%d, yellow=%d, red=%d, missing=%d | "
        "cutpoints=[%.3f, %.3f]",
        n_green, n_yellow, n_red, n_missing, low_cut, high_cut,
    )

    return result


def generate_phenotype_report(
    result: PhenotypeResult,
    df_original: pd.DataFrame | None = None,
    *,
    output_path: str | Path | None = None,
) -> str:
    """生成表型负担报告（Markdown）。"""
    df = result.df
    n = len(df)

    lines: list[str] = [
        "# Phenotype Burden Report (Stage 1B)\n",
        f"- 总样本数：{n}",
        f"- 参考分位切点：low_cut={result.cutpoints.get('low_cut', 'N/A'):.4f}, "
        f"high_cut={result.cutpoints.get('high_cut', 'N/A'):.4f}\n",
        "## Zone 分布\n",
        "| Zone | N | % |",
        "|---|---|---|",
        f"| green | {result.n_green} | {100*result.n_green/n:.1f}% |",
        f"| yellow | {result.n_yellow} | {100*result.n_yellow/n:.1f}% |",
        f"| red | {result.n_red} | {100*result.n_red/n:.1f}% |",
        f"| missing/NaN | {result.n_missing} | {100*result.n_missing/n:.1f}% |",
        "\n## 变量 Burden 分布（全量均值 ± std）\n",
        "| 变量 | 域 | 方向 | Burden 均值 | Burden std | 覆盖率 |",
        "|---|---|---|---|---|---|",
    ]

    for spec in result.variable_specs:
        bcol = f"{spec.field}_burden"
        if bcol not in df.columns:
            continue
        vals = df[bcol].dropna()
        coverage = 100 * len(vals) / n
        mean_b = vals.mean() if len(vals) > 0 else float("nan")
        std_b = vals.std() if len(vals) > 1 else float("nan")
        lines.append(
            f"| {spec.field} | {spec.domain} | {spec.direction} "
            f"| {mean_b:.3f} | {std_b:.3f} | {coverage:.1f}% |"
        )

    lines.append("\n## P_lab 分布统计\n")
    p_lab = df["p_lab"].dropna()
    if len(p_lab) > 0:
        lines.extend([
            f"- Mean ± std：{p_lab.mean():.4f} ± {p_lab.std():.4f}",
            f"- Median：{p_lab.median():.4f}",
            f"- Min/Max：{p_lab.min():.4f} / {p_lab.max():.4f}",
            f"- P25/P75：{p_lab.quantile(0.25):.4f} / {p_lab.quantile(0.75):.4f}",
        ])

    # 与 test_result 的构念效度（如果 df_original 提供）
    if df_original is not None and "test_result" in df_original.columns:
        lines.append("\n## 构念效度（phenotype_zone vs test_result 阳性率）\n")
        lines.append("| phenotype_zone | N | test_result 阳性率 |")
        lines.append("|---|---|---|")
        merged = df[["phenotype_zone"]].join(df_original[["test_result"]], how="inner")
        merged["positive"] = merged["test_result"].astype(str).str.contains(
            "阳性|positive|1", case=False, regex=True
        )
        for zone in ["green", "yellow", "red"]:
            sub = merged[merged["phenotype_zone"] == zone]
            if len(sub) == 0:
                continue
            pos_rate = 100 * sub["positive"].mean()
            lines.append(f"| {zone} | {len(sub)} | {pos_rate:.1f}% |")

    report = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report, encoding="utf-8")
        logger.info("Phenotype report saved to %s", output_path)

    return report
