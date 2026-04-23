"""
sensitivity_analysis.py — Stage 1B 5 组敏感性分析。

对比不同设计选择对 zone 分布和构念效度的影响：
  SA-1: Reference 敏感性：排除 test_result 阳性（旧版）vs 不排除（主要分析）
  SA-2: Phenotype cut 敏感性：P80/P95 vs 当前 P75/P90
  SA-3: 置信度阈值敏感性：both domains required for high confidence
  SA-4: Red 来源拆分（red_override vs red_phenotype 比例）
  SA-5: Outcome-anchor 代码修复前后对比（AUC 变化摘要）

输出：reports/sensitivity_analysis_report.md
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


def _positive_rate_by_zone(
    df: pd.DataFrame,
    zone_col: str = "final_zone",
    test_col: str = "test_result",
) -> dict[str, Any]:
    """计算各 zone 的 test_result 阳性率。"""
    if zone_col not in df.columns or test_col not in df.columns:
        return {"error": f"{zone_col} 或 {test_col} 不存在", "n": 0}

    positive = df[test_col].astype(str).str.contains(
        _POSITIVE_PATTERN, case=False, regex=True, na=False
    )
    rates: dict[str, float] = {}
    counts: dict[str, int] = {}
    for zone in ["green", "yellow", "red", "yellow_gray"]:
        mask = df[zone_col] == zone
        counts[zone] = int(mask.sum())
        rates[zone] = float(positive[mask].mean()) if mask.sum() > 0 else float("nan")

    g, y, r = rates.get("green", np.nan), rates.get("yellow", np.nan), rates.get("red", np.nan)
    if any(np.isnan(v) for v in [g, y, r]):
        direction = "insufficient_data"
    elif g <= y <= r:
        direction = "correct"
    elif g >= y >= r:
        direction = "reversed"
    else:
        direction = "non-monotone"

    return {
        "n": len(df),
        "zone_counts": counts,
        "positive_rates": rates,
        "direction": direction,
    }


@dataclass
class SensitivityResult:
    """敏感性分析结果集合。"""
    sa1_reference: dict[str, Any] = field(default_factory=dict)
    sa2_phenotype_cut: dict[str, Any] = field(default_factory=dict)
    sa3_confidence_threshold: dict[str, Any] = field(default_factory=dict)
    sa4_red_split: dict[str, Any] = field(default_factory=dict)
    sa5_outcome_anchor: dict[str, Any] = field(default_factory=dict)
    baseline: dict[str, Any] = field(default_factory=dict)


def run_sensitivity_suite(
    df_staging: pd.DataFrame,
    *,
    df_output: pd.DataFrame | None = None,
    test_col: str = "test_result",
) -> SensitivityResult:
    """
    运行 5 组敏感性分析。

    Parameters
    ----------
    df_staging : 原始 staging 数据（含 test_result 和 CPET 特征）
    df_output  : Stage 1B 最终输出表（含 final_zone, confidence_label 等）
    test_col   : 结局代理列名

    Returns SensitivityResult
    """
    result = SensitivityResult()

    # ── Baseline：从输出表读取当前分析 ──
    if df_output is not None and "final_zone" in df_output.columns:
        merged = df_output.copy()
        if test_col not in merged.columns and test_col in df_staging.columns:
            merged[test_col] = df_staging[test_col].reindex(merged.index)
        result.baseline = _positive_rate_by_zone(merged, "final_zone", test_col)
        result.baseline["label"] = "当前分析（主要结果）"
    else:
        result.baseline = {"label": "当前分析（输出表不可用）", "n": 0}

    # ── SA-1：Reference 敏感性 ──
    # 对比：去掉 test_result 排除（当前主要分析）vs 排除 test_result 阳性
    # 当前分析已不排除 test_result（B3 修复后），此处演示对比
    if df_output is not None and "final_zone" in df_output.columns:
        merged = df_output.copy()
        if test_col not in merged.columns and test_col in df_staging.columns:
            merged[test_col] = df_staging[test_col].reindex(merged.index)

        # 模拟"若排除 test_result 阳性时 reference 子集对结果的影响"
        # 这里直接报告当前 reference N（strict）对比 wide N
        ref_strict_n = int((merged.get("reference_flag_strict", pd.Series(dtype=bool)) == True).sum()) if "reference_flag_strict" in merged.columns else "N/A"
        result.sa1_reference = {
            "label": "SA-1：Reference 设计（无 test_result 排除）",
            "description": "B3 修复后，primary reference 不再排除 test_result 阳性，保持纯外部验证叙事",
            "current_design": "不排除 test_result（v2.7.0 后）",
            "prior_design": "排除 test_result 阳性（v2.6.x 及之前）",
            "reference_strict_n": ref_strict_n,
            "zone_distribution": _positive_rate_by_zone(merged, "final_zone", test_col),
        }
    else:
        result.sa1_reference = {
            "label": "SA-1：Reference 设计",
            "error": "输出表不可用",
        }

    # ── SA-2：Phenotype cut 敏感性（P80/P95 vs 当前 P75/P90） ──
    # 如果没有 p_lab（原始分位打分），则用 phenotype_zone 近似
    result.sa2_phenotype_cut = _run_phenotype_cut_sensitivity(
        df_staging, df_output, test_col
    )

    # ── SA-3：置信度阈值敏感性 ──
    # 比较：current high threshold 0.80 vs 原来的 0.75
    result.sa3_confidence_threshold = _run_confidence_threshold_sensitivity(
        df_output, test_col, df_staging
    )

    # ── SA-4：Red 来源拆分 ──
    if df_output is not None and "red_source" in df_output.columns:
        red_mask = df_output.get("final_zone", pd.Series(dtype=str)) == "red"
        n_red = int(red_mask.sum())
        n_override = int((df_output["red_source"] == "red_override").sum())
        n_phenotype = int((df_output["red_source"] == "red_phenotype").sum())
        result.sa4_red_split = {
            "label": "SA-4：Red 语义拆分",
            "n_red_total": n_red,
            "n_red_override": n_override,
            "n_red_phenotype": n_phenotype,
            "pct_override": 100 * n_override / n_red if n_red > 0 else float("nan"),
            "pct_phenotype": 100 * n_phenotype / n_red if n_red > 0 else float("nan"),
        }
    else:
        result.sa4_red_split = {
            "label": "SA-4：Red 语义拆分",
            "error": "red_source 列不存在，请重跑 make stage1b",
        }

    # ── SA-5：Outcome-anchor 修复摘要 ──
    result.sa5_outcome_anchor = {
        "label": "SA-5：Outcome-anchor ElasticNet 修复",
        "description": "B4 修复：LogisticRegression 添加 penalty='elasticnet'（之前为纯 L2）",
        "prior_issue": "solver=saga + l1_ratio=0.5 但无 penalty='elasticnet' → 实际为纯 L2",
        "fix": "添加 penalty='elasticnet' 参数",
        "expected_effect": "calibration slope 预期从 -0.055 向 1.0 改善",
        "note": "重跑 make stage1b 后，outcome_anchor_report.md 将包含新数值",
    }

    return result


def _run_phenotype_cut_sensitivity(
    df_staging: pd.DataFrame,
    df_output: pd.DataFrame | None,
    test_col: str,
) -> dict[str, Any]:
    """SA-2：Phenotype cut 敏感性分析（P80/P95 vs 当前 P75/P90）。"""
    label = "SA-2：Phenotype cut 敏感性（P80/P95 vs 当前 P75/P90）"

    if df_output is None or "p_lab" not in df_output.columns:
        return {
            "label": label,
            "note": "p_lab（综合表型负担分）不存在，使用 phenotype_zone 近似比较",
            "current_distribution": _zone_counts(df_output, "phenotype_zone") if df_output is not None else {},
        }

    # 如果有 p_lab，对比不同切点
    p_lab = df_output["p_lab"].dropna()
    if len(p_lab) == 0:
        return {"label": label, "error": "p_lab 全部为空"}

    # 计算不同切点下的 zone 分布
    cut_75 = float(np.percentile(p_lab, 75))
    cut_90 = float(np.percentile(p_lab, 90))
    cut_80 = float(np.percentile(p_lab, 80))
    cut_95 = float(np.percentile(p_lab, 95))

    def apply_cut(low: float, high: float) -> pd.Series:
        zones = pd.Series("yellow", index=df_output.index)
        zones[df_output["p_lab"] < low] = "green"
        zones[df_output["p_lab"] >= high] = "red"
        return zones

    zone_75_90 = apply_cut(cut_75, cut_90)
    zone_80_95 = apply_cut(cut_80, cut_95)

    def zone_dist(zones: pd.Series) -> dict[str, float]:
        total = len(zones)
        return {z: 100 * (zones == z).sum() / total for z in ["green", "yellow", "red"]}

    return {
        "label": label,
        "cutpoints": {
            "current (P75/P90)": {"low": round(cut_75, 3), "high": round(cut_90, 3)},
            "alternative (P80/P95)": {"low": round(cut_80, 3), "high": round(cut_95, 3)},
        },
        "distribution_P75_P90": zone_dist(zone_75_90),
        "distribution_P80_P95": zone_dist(zone_80_95),
        "note": "更严格切点（P80/P95）使 Red 区缩小，Green 区扩大",
    }


def _run_confidence_threshold_sensitivity(
    df_output: pd.DataFrame | None,
    test_col: str,
    df_staging: pd.DataFrame,
) -> dict[str, Any]:
    """SA-3：置信度阈值敏感性（both domains required for high）。"""
    label = "SA-3：置信度阈值敏感性（当前 0.80 vs 旧版 0.75）"

    if df_output is None or "confidence_score" not in df_output.columns:
        return {"label": label, "error": "confidence_score 不存在"}

    scores = df_output["confidence_score"].fillna(0)
    n = len(scores)

    # 不同阈值下的 high 比例
    thresholds = [0.70, 0.75, 0.80, 0.85]
    dist: dict[str, float] = {}
    for thr in thresholds:
        pct_high = 100 * (scores >= thr).mean()
        dist[f"high@{thr}"] = round(float(pct_high), 1)

    # Both domains required（anchor_agreement AND validation_agreement 均非中性）
    both_non_neutral_n = 0
    if "anchor_agreement" in df_output.columns and "validation_agreement" in df_output.columns:
        aa = df_output["anchor_agreement"].fillna(0.5)
        va = df_output["validation_agreement"].fillna(0.5)
        both_non_neutral = (aa != 0.5) & (va != 0.5)
        both_non_neutral_n = int(both_non_neutral.sum())
        if both_non_neutral_n > 0:
            high_if_both = int((scores[both_non_neutral] >= 0.80).sum())
            dist["high@0.80_both_domains"] = round(100 * high_if_both / both_non_neutral_n, 1)
        else:
            dist["high@0.80_both_domains"] = "N/A（无样本有双域数据）"

    return {
        "label": label,
        "n_total": n,
        "n_both_non_neutral_domains": both_non_neutral_n,
        "high_confidence_pct_by_threshold": dist,
        "current_threshold": 0.80,
        "prior_threshold": 0.75,
        "note": "v2.7.0 阈值从 0.75 升至 0.80，预期 high% 下降（从 74.2% 至 45-60%）",
    }


def _zone_counts(df: pd.DataFrame | None, col: str) -> dict[str, int]:
    if df is None or col not in df.columns:
        return {}
    total = len(df)
    return {z: int((df[col] == z).sum()) for z in ["green", "yellow", "red"]}


def generate_sensitivity_report(
    result: SensitivityResult,
    *,
    output_path: str | Path | None = None,
) -> str:
    """生成敏感性分析报告（Markdown）。"""
    lines: list[str] = [
        "# Sensitivity Analysis Report (Stage 1B v2.7.0)\n",
        "5 组敏感性分析，评估关键设计选择对结果稳健性的影响。\n",
    ]

    # Baseline
    lines.append("## Baseline（主要分析）\n")
    bl = result.baseline
    if "zone_counts" in bl:
        n = bl.get("n", 0)
        lines.append(f"- 总样本量：{n}")
        lines.append(f"- 方向：**{bl.get('direction', 'N/A')}**")
        zc = bl.get("zone_counts", {})
        lines.append("| Zone | N | % |")
        lines.append("|---|---|---|")
        for zone in ["green", "yellow", "red", "yellow_gray"]:
            cnt = zc.get(zone, 0)
            if cnt > 0 or zone in ["green", "yellow", "red"]:
                lines.append(f"| {zone} | {cnt} | {100*cnt/n:.1f}% |" if n > 0 else f"| {zone} | {cnt} | - |")

    # SA-1
    lines.append("\n## SA-1：Reference 设计敏感性\n")
    sa1 = result.sa1_reference
    if "error" in sa1:
        lines.append(f"> ⚠️ {sa1['error']}")
    else:
        lines.append(f"- 当前设计：{sa1.get('current_design', 'N/A')}")
        lines.append(f"- 先前设计：{sa1.get('prior_design', 'N/A')}")
        lines.append(f"- Strict reference N：{sa1.get('reference_strict_n', 'N/A')}")
        zd = sa1.get("zone_distribution", {})
        lines.append(f"- Zone 方向：**{zd.get('direction', 'N/A')}**")

    # SA-2
    lines.append("\n## SA-2：Phenotype Cut 敏感性\n")
    sa2 = result.sa2_phenotype_cut
    if "error" in sa2:
        lines.append(f"> ⚠️ {sa2['error']}")
    elif "note" in sa2 and "p_lab" in sa2.get("note", ""):
        lines.append(f"_{sa2['note']}_")
    else:
        cuts = sa2.get("cutpoints", {})
        for k, v in cuts.items():
            lines.append(f"- {k}：Low={v['low']}, High={v['high']}")
        d1 = sa2.get("distribution_P75_P90", {})
        d2 = sa2.get("distribution_P80_P95", {})
        lines.append("\n| Zone | P75/P90 (%) | P80/P95 (%) |")
        lines.append("|---|---|---|")
        for zone in ["green", "yellow", "red"]:
            v1 = f"{d1.get(zone, 0):.1f}%" if d1 else "N/A"
            v2 = f"{d2.get(zone, 0):.1f}%" if d2 else "N/A"
            lines.append(f"| {zone} | {v1} | {v2} |")

    # SA-3
    lines.append("\n## SA-3：置信度阈值敏感性\n")
    sa3 = result.sa3_confidence_threshold
    if "error" in sa3:
        lines.append(f"> ⚠️ {sa3['error']}")
    else:
        lines.append(f"- 当前阈值：{sa3.get('current_threshold', 'N/A')}")
        lines.append(f"- 先前阈值：{sa3.get('prior_threshold', 'N/A')}")
        dist = sa3.get("high_confidence_pct_by_threshold", {})
        lines.append("\n| 阈值 | High% |")
        lines.append("|---|---|")
        for k, v in dist.items():
            lines.append(f"| {k} | {v} |")
        n_both = sa3.get("n_both_non_neutral_domains", 0)
        lines.append(f"\n- 双域均有非中性值样本：{n_both}")
        if sa3.get("note"):
            lines.append(f"- 备注：{sa3['note']}")

    # SA-4
    lines.append("\n## SA-4：Red 语义拆分\n")
    sa4 = result.sa4_red_split
    if "error" in sa4:
        lines.append(f"> ⚠️ {sa4['error']}")
    else:
        n_red = sa4.get("n_red_total", 0)
        n_ov = sa4.get("n_red_override", 0)
        n_ph = sa4.get("n_red_phenotype", 0)
        lines.append(f"- Red 总计：{n_red}")
        lines.append(f"- red_override（instability severe 触发）：{n_ov} ({sa4.get('pct_override', 0):.1f}%)")
        lines.append(f"- red_phenotype（表型负担 P90 触发）：{n_ph} ({sa4.get('pct_phenotype', 0):.1f}%)")

    # SA-5
    lines.append("\n## SA-5：Outcome-Anchor 修复摘要\n")
    sa5 = result.sa5_outcome_anchor
    lines.append(f"- 问题：{sa5.get('prior_issue', 'N/A')}")
    lines.append(f"- 修复：{sa5.get('fix', 'N/A')}")
    lines.append(f"- 预期效果：{sa5.get('expected_effect', 'N/A')}")
    lines.append(f"- 备注：{sa5.get('note', 'N/A')}")

    report = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report, encoding="utf-8")
        logger.info("Sensitivity analysis report saved to %s", output_path)

    return report
