"""
stratified_validation.py — Stage 1B 分层验证矩阵。

生成 5 组构念效度分析，剥离不同层级的 test_result 阳性率梯度：
  1. phenotype_zone vs test_result（表型层，未经覆盖）
  2. instability_severe vs test_result（instability 覆盖层）
  3. final_zone vs test_result（整体，主要报告）
  4. 高置信度子集 final_zone vs test_result
  5. 去掉 severe override 后的 phenotype_zone vs test_result（纯表型层）

输出：reports/stratified_validation_report.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_POSITIVE_PATTERN = r"阳性|positive"


def _positive_rate(df: pd.DataFrame, test_col: str = "test_result") -> float:
    """计算 test_result 阳性率。"""
    if test_col not in df.columns or len(df) == 0:
        return float("nan")
    positive = df[test_col].astype(str).str.contains(
        _POSITIVE_PATTERN, case=False, regex=True, na=False
    )
    return float(positive.mean())


def _zone_positive_rates(
    df: pd.DataFrame,
    zone_col: str,
    test_col: str = "test_result",
    zones: list[str] | None = None,
) -> dict[str, Any]:
    """
    对 zone_col 的各层级计算 test_result 阳性率，同时检测单调性。
    """
    if zone_col not in df.columns or test_col not in df.columns:
        return {"zone_col": zone_col, "error": f"{zone_col} 或 {test_col} 不存在"}

    if zones is None:
        zones = ["green", "yellow", "red"]

    positive = df[test_col].astype(str).str.contains(
        _POSITIVE_PATTERN, case=False, regex=True, na=False
    )

    rates: dict[str, float] = {}
    counts: dict[str, int] = {}
    for zone in zones:
        mask = df[zone_col] == zone
        sub = df[mask]
        counts[zone] = len(sub)
        if len(sub) == 0:
            rates[zone] = float("nan")
        else:
            rates[zone] = float(positive[mask].mean())

    # 单调性检测（green < yellow < red）
    g, y, r = rates.get("green", np.nan), rates.get("yellow", np.nan), rates.get("red", np.nan)
    if any(np.isnan(v) for v in [g, y, r]):
        direction = "insufficient_data"
        monotone = False
    elif g <= y <= r:
        direction = "correct"
        monotone = True
    elif g >= y >= r:
        direction = "reversed"
        monotone = False
    else:
        direction = "non-monotone"
        monotone = False

    return {
        "zone_col": zone_col,
        "positive_rates": rates,
        "counts": counts,
        "monotone_gradient": monotone,
        "direction": direction,
        "n_total": len(df),
    }


@dataclass
class StratifiedValidationResult:
    """分层验证矩阵结果。"""
    group1_phenotype: dict[str, Any] = field(default_factory=dict)       # phenotype_zone（全量）
    group2_instability: dict[str, Any] = field(default_factory=dict)     # instability_severe 子组
    group3_final_zone: dict[str, Any] = field(default_factory=dict)      # final_zone（整体）
    group4_high_conf: dict[str, Any] = field(default_factory=dict)       # 高置信度子集
    group5_phenotype_no_override: dict[str, Any] = field(default_factory=dict)  # 去掉 severe 后


def run_stratified_validation(
    df: pd.DataFrame,
    *,
    test_col: str = "test_result",
) -> StratifiedValidationResult:
    """
    运行 5 组分层验证分析。

    Parameters
    ----------
    df : 含所有 Stage 1B 输出列的 DataFrame
    test_col : 结局代理列（默认 test_result）

    Returns StratifiedValidationResult
    """
    result = StratifiedValidationResult()

    # Group 1：phenotype_zone vs test_result（全量，未经 instability 覆盖）
    result.group1_phenotype = _zone_positive_rates(df, "phenotype_zone", test_col)
    result.group1_phenotype["description"] = "表型负担层（phenotype_zone，全量）"

    # Group 2：instability_severe 子组分析
    if "instability_severe" in df.columns and test_col in df.columns:
        severe_mask = df["instability_severe"].fillna(False).astype(bool)
        positive = df[test_col].astype(str).str.contains(
            _POSITIVE_PATTERN, case=False, regex=True, na=False
        )
        severe_pos = float(positive[severe_mask].mean()) if severe_mask.sum() > 0 else float("nan")
        non_severe_pos = float(positive[~severe_mask].mean()) if (~severe_mask).sum() > 0 else float("nan")
        result.group2_instability = {
            "zone_col": "instability_severe",
            "description": "Instability 覆盖层（severe vs non-severe）",
            "severe_n": int(severe_mask.sum()),
            "non_severe_n": int((~severe_mask).sum()),
            "severe_positive_rate": severe_pos,
            "non_severe_positive_rate": non_severe_pos,
            "direction": "correct" if severe_pos > non_severe_pos else "reversed",
        }
    else:
        result.group2_instability = {
            "zone_col": "instability_severe",
            "error": "instability_severe 或 test_result 不存在",
        }

    # Group 3：final_zone vs test_result（主要报告，已含覆盖层）
    result.group3_final_zone = _zone_positive_rates(df, "final_zone", test_col)
    result.group3_final_zone["description"] = "最终分区（final_zone，含 instability 覆盖）"

    # Group 4：高置信度子集（confidence_label == "high"）
    if "confidence_label" in df.columns:
        high_conf_df = df[df["confidence_label"] == "high"]
        result.group4_high_conf = _zone_positive_rates(high_conf_df, "final_zone", test_col)
        result.group4_high_conf["description"] = f"高置信度子集（n={len(high_conf_df)}）"
        result.group4_high_conf["n_subset"] = len(high_conf_df)
    else:
        result.group4_high_conf = {
            "zone_col": "final_zone",
            "description": "高置信度子集",
            "error": "confidence_label 不存在",
        }

    # Group 5：去掉 severe override 后的 phenotype_zone（纯表型层）
    if "instability_severe" in df.columns:
        severe_mask = df["instability_severe"].fillna(False).astype(bool)
        no_override_df = df[~severe_mask]
        result.group5_phenotype_no_override = _zone_positive_rates(
            no_override_df, "phenotype_zone", test_col
        )
        result.group5_phenotype_no_override["description"] = (
            f"纯表型层（去掉 severe override，n={len(no_override_df)}）"
        )
        result.group5_phenotype_no_override["n_subset"] = len(no_override_df)
    else:
        result.group5_phenotype_no_override = {
            "zone_col": "phenotype_zone",
            "description": "纯表型层（去掉 severe override）",
            "error": "instability_severe 不存在",
        }

    logger.info(
        "StratifiedValidation: group1=%s, group3=%s, group4=%s",
        result.group1_phenotype.get("direction", "?"),
        result.group3_final_zone.get("direction", "?"),
        result.group4_high_conf.get("direction", "?"),
    )

    return result


def generate_stratified_validation_report(
    result: StratifiedValidationResult,
    *,
    output_path: str | Path | None = None,
) -> str:
    """生成分层验证矩阵报告（Markdown）。"""

    def _fmt_group(group: dict[str, Any], title: str) -> list[str]:
        lines = [f"\n### {title}\n"]
        desc = group.get("description", "")
        if desc:
            lines.append(f"_{desc}_\n")

        if "error" in group:
            lines.append(f"> ⚠️ 数据不足：{group['error']}\n")
            return lines

        # instability 特殊格式
        if group.get("zone_col") == "instability_severe" and "severe_n" in group:
            lines.extend([
                "| 子组 | N | test_result 阳性率 |",
                "|---|---|---|",
                f"| Severe instability | {group['severe_n']} | {group['severe_positive_rate']:.1%} |",
                f"| Non-severe | {group['non_severe_n']} | {group['non_severe_positive_rate']:.1%} |",
                f"\n- 方向：**{group.get('direction', 'N/A')}**",
            ])
            return lines

        rates = group.get("positive_rates", {})
        counts = group.get("counts", {})
        direction = group.get("direction", "N/A")
        monotone = group.get("monotone_gradient", False)
        n_subset = group.get("n_subset", group.get("n_total", "?"))

        lines.extend([
            f"- 分析样本量：{n_subset}",
            f"- 方向：**{direction}**，单调梯度：{'✅' if monotone else '❌'}",
            "",
            "| Zone | N | test_result 阳性率 |",
            "|---|---|---|",
        ])
        for zone in ["green", "yellow", "red"]:
            rate = rates.get(zone, float("nan"))
            n = counts.get(zone, 0)
            rate_str = f"{rate:.1%}" if not np.isnan(rate) else "N/A"
            lines.append(f"| {zone} | {n} | {rate_str} |")

        return lines

    lines: list[str] = [
        "# Stratified Validation Report (Stage 1B)\n",
        "5 组分层验证，剥离表型层/覆盖层/置信度层对构念效度的贡献。\n",
    ]

    groups = [
        (result.group1_phenotype, "Group 1：表型负担层（全量 phenotype_zone）"),
        (result.group2_instability, "Group 2：Instability 覆盖层（severe 有无对比）"),
        (result.group3_final_zone, "Group 3：最终分区（final_zone，主要报告）"),
        (result.group4_high_conf, "Group 4：高置信度子集"),
        (result.group5_phenotype_no_override, "Group 5：纯表型层（去掉 severe override）"),
    ]

    for group, title in groups:
        lines.extend(_fmt_group(group, title))

    # 汇总对比表
    lines.append("\n## 汇总对比\n")
    lines.append("| 分析层 | 样本量 | 方向 | 单调 |")
    lines.append("|---|---|---|---|")
    summary_rows = [
        ("表型层（全量）", result.group1_phenotype),
        ("最终分区（整体）", result.group3_final_zone),
        ("高置信度子集", result.group4_high_conf),
        ("纯表型层（无override）", result.group5_phenotype_no_override),
    ]
    for label, group in summary_rows:
        if "error" in group:
            lines.append(f"| {label} | - | error | - |")
            continue
        n = group.get("n_subset", group.get("n_total", "?"))
        direction = group.get("direction", "N/A")
        monotone = "✅" if group.get("monotone_gradient") else "❌"
        lines.append(f"| {label} | {n} | {direction} | {monotone} |")

    report = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report, encoding="utf-8")
        logger.info("Stratified validation report saved to %s", output_path)

    return report
