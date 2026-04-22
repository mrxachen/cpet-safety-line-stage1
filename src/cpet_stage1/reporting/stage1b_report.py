"""
stage1b_report.py — Stage 1B 总报告聚合。

职责：
1. 汇聚各步骤输出（quantile bundle, phenotype, instability, confidence, outcome, anomaly）
2. 生成全量 13+ 列输出表（stage1b_output_table.parquet）
3. 统计验证（构念效度 + 参考合理性 + 分层稳健性 + Legacy 对照）
4. 生成 Markdown 摘要报告
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 验收标准（对应 04_预期结果.md §五）
ACCEPT_THRESHOLDS = {
    "reference_red_pct_max": 0.15,    # strict reference 中 red < 15%
    "reference_green_pct_min": 0.50,  # strict reference 中 green > 50%
    "high_confidence_min": 0.10,      # 至少 10% 高置信度
    "monotone_gradient": True,        # final_zone 对 test_result 单调
}


def build_stage1b_output_table(
    df_staging: pd.DataFrame,
    *,
    phenotype_parquet: str | Path | None = None,
    instability_parquet: str | Path | None = None,
    confidence_parquet: str | Path | None = None,
    outcome_parquet: str | Path | None = None,
    anomaly_parquet: str | Path | None = None,
) -> pd.DataFrame:
    """
    汇聚所有 Stage 1B 中间输出，构建最终输出表（每人一行）。

    Required columns in output:
      reserve_burden, vent_burden, p_lab, phenotype_zone,
      instability_severe, instability_mild,
      final_zone_before_confidence,
      confidence_score, confidence_label, indeterminate_flag, final_zone,
      outcome_risk_prob (optional), outcome_risk_tertile (optional),
      anomaly_score (optional), anomaly_flag (optional)
    """
    result = df_staging.copy()

    def _merge_parquet(path: str | Path | None, desc: str) -> pd.DataFrame | None:
        if path is None:
            return None
        p = Path(path)
        if not p.exists():
            logger.warning("%s parquet not found: %s", desc, p)
            return None
        try:
            return pd.read_parquet(p)
        except Exception as exc:
            logger.warning("Failed to read %s: %s", p, exc)
            return None

    # 合并各阶段输出（按 index 对齐）
    stage_dfs = [
        (_merge_parquet(phenotype_parquet, "phenotype"), [
            "reserve_burden", "vent_burden", "p_lab", "phenotype_zone",
        ]),
        (_merge_parquet(instability_parquet, "instability"), [
            "instability_severe", "instability_mild", "final_zone_before_confidence",
        ]),
        (_merge_parquet(confidence_parquet, "confidence"), [
            "confidence_score", "confidence_label", "indeterminate_flag", "final_zone",
            "completeness_score", "effort_score",
        ]),
    ]

    for df_stage, expected_cols in stage_dfs:
        if df_stage is None:
            continue
        for col in expected_cols:
            if col in df_stage.columns:
                result[col] = df_stage[col].reindex(result.index)

    # outcome（可选）
    outcome_df = _merge_parquet(outcome_parquet, "outcome")
    if outcome_df is not None:
        for col in ["outcome_risk_prob", "outcome_risk_tertile"]:
            if col in outcome_df.columns:
                result[col] = outcome_df[col].reindex(result.index)

    # anomaly（可选）
    anomaly_df = _merge_parquet(anomaly_parquet, "anomaly")
    if anomaly_df is not None:
        for col in ["anomaly_score", "anomaly_flag"]:
            if col in anomaly_df.columns:
                result[col] = anomaly_df[col].reindex(result.index)

    return result


def compute_construct_validity(
    df: pd.DataFrame,
    *,
    zone_col: str = "final_zone",
    test_result_col: str = "test_result",
) -> dict[str, Any]:
    """
    构念效度：final_zone 对 test_result 阳性率的单调梯度。

    Returns dict with:
    - zone_positive_rates: {green: ..., yellow: ..., red: ...}
    - monotone_gradient: bool（green < yellow < red 阳性率）
    - direction: "correct" / "reversed" / "non-monotone" / "insufficient_data"
    """
    if zone_col not in df.columns or test_result_col not in df.columns:
        return {"direction": "insufficient_data"}

    positive = df[test_result_col].astype(str).str.contains(
        "阳性|positive|1", case=False, regex=True
    )

    rates: dict[str, float] = {}
    for zone in ["green", "yellow", "red"]:
        sub = df[df[zone_col] == zone]
        if len(sub) == 0:
            rates[zone] = float("nan")
        else:
            rates[zone] = float(positive[sub.index].mean())

    g, y, r = rates.get("green", float("nan")), rates.get("yellow", float("nan")), rates.get("red", float("nan"))

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
        "zone_positive_rates": rates,
        "monotone_gradient": monotone,
        "direction": direction,
    }


def compute_reference_validity(
    df: pd.DataFrame,
    *,
    zone_col: str = "phenotype_zone",
    reference_mask: pd.Series | None = None,
) -> dict[str, Any]:
    """
    参考合理性：strict reference 中 red < 15%, green > 50%。
    """
    if reference_mask is None:
        logger.warning("No reference mask provided for reference validity check")
        return {}

    if zone_col not in df.columns:
        return {}

    ref_zone = df.loc[reference_mask, zone_col]
    n_ref = len(ref_zone)
    if n_ref == 0:
        return {}

    counts = ref_zone.value_counts(normalize=True, dropna=False)
    green_pct = float(counts.get("green", 0))
    red_pct = float(counts.get("red", 0))

    return {
        "n_reference": n_ref,
        "green_pct": green_pct,
        "red_pct": red_pct,
        "reference_ok": red_pct < ACCEPT_THRESHOLDS["reference_red_pct_max"]
                        and green_pct > ACCEPT_THRESHOLDS["reference_green_pct_min"],
    }


def assess_acceptance(
    df: pd.DataFrame,
    *,
    reference_mask: pd.Series | None = None,
) -> dict[str, str]:
    """
    根据验收标准评估 Stage 1B 结果质量。

    Returns dict: {"verdict": "Accept"/"Warn"/"Fail", "reason": ..., "details": ...}
    """
    issues: list[str] = []
    warns: list[str] = []

    # 构念效度
    cv = compute_construct_validity(df)
    if not cv.get("monotone_gradient", False):
        direction = cv.get("direction", "unknown")
        if direction == "reversed":
            issues.append(f"final_zone vs test_result 方向相反（reversed）")
        elif direction == "non-monotone":
            warns.append("final_zone vs test_result 单调梯度不完整")

    # 参考合理性
    if reference_mask is not None:
        rv = compute_reference_validity(df, reference_mask=reference_mask)
        if rv:
            if rv.get("red_pct", 0) > ACCEPT_THRESHOLDS["reference_red_pct_max"]:
                issues.append(f"reference 中 red 比例过高: {rv['red_pct']:.1%}")
            if rv.get("green_pct", 0) < ACCEPT_THRESHOLDS["reference_green_pct_min"]:
                warns.append(f"reference 中 green 比例偏低: {rv['green_pct']:.1%}")

    # 高置信度比例
    if "confidence_label" in df.columns:
        high_pct = (df["confidence_label"] == "high").mean()
        if high_pct < ACCEPT_THRESHOLDS["high_confidence_min"]:
            warns.append(f"high confidence 比例过低: {high_pct:.1%}")

    # 总体判定
    if issues:
        return {"verdict": "Fail", "reason": "; ".join(issues), "details": warns}
    elif warns:
        return {"verdict": "Warn", "reason": "; ".join(warns), "details": []}
    else:
        return {"verdict": "Accept", "reason": "所有验收标准满足", "details": []}


def generate_stage1b_summary_report(
    df: pd.DataFrame,
    *,
    reference_mask: pd.Series | None = None,
    output_path: str | Path | None = None,
) -> str:
    """生成 Stage 1B 汇总报告（Markdown）。"""
    n = len(df)
    lines: list[str] = [
        "# Stage 1B Summary Report\n",
        f"- 总样本数：{n}",
        f"- 输出列：{[c for c in df.columns if c in ['reserve_burden', 'vent_burden', 'p_lab', 'phenotype_zone', 'instability_severe', 'instability_mild', 'final_zone_before_confidence', 'confidence_score', 'confidence_label', 'indeterminate_flag', 'final_zone', 'outcome_risk_prob', 'anomaly_flag']]}",
        "",
    ]

    # final_zone 分布
    if "final_zone" in df.columns:
        lines.append("## final_zone 分布\n")
        lines.append("| Zone | N | % |")
        lines.append("|---|---|---|")
        for zone in ["green", "yellow", "red", "yellow_gray"]:
            cnt = int((df["final_zone"] == zone).sum())
            lines.append(f"| {zone} | {cnt} | {100*cnt/n:.1f}% |")
        nan_cnt = int(df["final_zone"].isna().sum())
        if nan_cnt > 0:
            lines.append(f"| NaN | {nan_cnt} | {100*nan_cnt/n:.1f}% |")

    # confidence 分布
    if "confidence_label" in df.columns:
        lines.append("\n## 置信度分布\n")
        lines.append("| Label | N | % |")
        lines.append("|---|---|---|")
        for lbl in ["high", "medium", "low"]:
            cnt = int((df["confidence_label"] == lbl).sum())
            lines.append(f"| {lbl} | {cnt} | {100*cnt/n:.1f}% |")
        indet = int(df.get("indeterminate_flag", pd.Series([False]*n)).sum())
        lines.append(f"| indeterminate | {indet} | {100*indet/n:.1f}% |")

    # 构念效度
    cv = compute_construct_validity(df)
    lines.append("\n## 构念效度（final_zone vs test_result）\n")
    if "direction" in cv:
        lines.append(f"- 方向：**{cv['direction']}**")
        lines.append(f"- 单调梯度：{'✅' if cv.get('monotone_gradient') else '❌'}")
        rates = cv.get("zone_positive_rates", {})
        for zone in ["green", "yellow", "red"]:
            rate = rates.get(zone, float("nan"))
            if not np.isnan(rate):
                lines.append(f"- {zone} 阳性率：{rate:.1%}")

    # 参考合理性
    if reference_mask is not None:
        rv = compute_reference_validity(df, reference_mask=reference_mask)
        if rv:
            lines.append("\n## 参考子集合理性\n")
            lines.append(f"- 参考子集 N：{rv.get('n_reference', 'N/A')}")
            lines.append(f"- green%：{rv.get('green_pct', 0):.1%}")
            lines.append(f"- red%：{rv.get('red_pct', 0):.1%}")
            lines.append(f"- 参考合理：{'✅' if rv.get('reference_ok') else '❌'}")

    # 验收判定
    verdict = assess_acceptance(df, reference_mask=reference_mask)
    lines.append(f"\n## 验收判定：**{verdict['verdict']}**\n")
    lines.append(f"- 原因：{verdict['reason']}")
    if verdict.get("details"):
        for d in verdict["details"]:
            lines.append(f"- 警告：{d}")

    # Legacy 对比
    if "p1_zone" in df.columns or "zone_v2" in df.columns:
        lines.append("\n## 与 Legacy 对照\n")
        legacy_col = "zone_v2" if "zone_v2" in df.columns else "p1_zone"
        if "final_zone" in df.columns:
            merged = df[[legacy_col, "final_zone"]].dropna()
            n_agree = int((merged[legacy_col] == merged["final_zone"]).sum())
            lines.append(f"- Legacy ({legacy_col}) vs Stage1B final_zone 一致率：{n_agree/len(merged):.1%}")

    # Outcome model 性能（如果有）
    if "outcome_risk_prob" in df.columns:
        lines.append("\n## Outcome Risk 分布\n")
        prob = df["outcome_risk_prob"].dropna()
        if len(prob) > 0:
            lines.append(f"- Mean prob：{prob.mean():.3f}")
            lines.append(f"- Median prob：{prob.median():.3f}")

    report = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report, encoding="utf-8")
        logger.info("Stage 1B summary report saved to %s", output_path)

    return report
