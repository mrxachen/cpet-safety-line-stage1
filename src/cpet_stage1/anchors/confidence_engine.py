"""
confidence_engine.py — Stage 1B 置信度与 indeterminate 逻辑。

置信度四要素：
  A. completeness_score  — 核心字段覆盖率（0~1）
  B. effort_score        — HR 代理努力度（0/0.5/1）
  C. anchor_agreement    — 外部 vs 内部分位解释一致性（0/0.5/1）
  D. validation_agreement — final_zone vs outcome model 风险三分位（0/0.5/1）

置信度公式：
  confidence = 0.40*completeness + 0.15*effort + 0.20*anchor + 0.25*validation

置信度分层：
  ≥0.75 → high
  0.60..0.75 → medium
  <0.60 → low → indeterminate（若无 severe）

适配说明：
    模板来源：docs/guide/cpet_stage1_method_package/code_templates/confidence_engine.py
    在模板基础上增加：
    - 配置文件驱动（zone_rules_stage1b.yaml confidence 节）
    - effort_score 具体实现（HR%pred 或 hr_peak/age 代理）
    - 报告生成
    - run_confidence_engine 主入口
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceResult:
    """置信度引擎输出。"""
    df: pd.DataFrame        # 含 confidence_score, confidence_label, indeterminate_flag, final_zone
    n_high: int = 0
    n_medium: int = 0
    n_low: int = 0
    n_indeterminate: int = 0

    def summary(self) -> str:
        n = len(self.df)
        lines = [
            "ConfidenceEngine Summary",
            f"  Total: {n}",
            f"  High:          {self.n_high} ({100*self.n_high/n:.1f}%)",
            f"  Medium:        {self.n_medium} ({100*self.n_medium/n:.1f}%)",
            f"  Low:           {self.n_low} ({100*self.n_low/n:.1f}%)",
            f"  Indeterminate: {self.n_indeterminate} ({100*self.n_indeterminate/n:.1f}%)",
        ]
        return "\n".join(lines)


def compute_completeness_score(
    df: pd.DataFrame,
    *,
    reserve_fields: list[str],
    ventilatory_fields: list[str],
    instability_fields: list[str],
) -> pd.Series:
    """
    核心字段覆盖率 = (非空字段数) / (总字段数)。
    若未提供任何字段则返回 0.5（中性值）。
    """
    all_fields = reserve_fields + ventilatory_fields + instability_fields
    required = len(all_fields)
    if required == 0:
        logger.warning("No fields supplied to completeness score, returning 0.5")
        return pd.Series(0.5, index=df.index, dtype=float)

    available_fields = [f for f in all_fields if f in df.columns]
    if not available_fields:
        return pd.Series(0.0, index=df.index, dtype=float)

    available_count = df[available_fields].notna().sum(axis=1)
    return available_count / required


def compute_effort_score(
    df: pd.DataFrame,
    *,
    adequate_threshold: float = 85.0,
    uncertain_threshold: float = 70.0,
    hr_pct_field: str = "hr_peak_pct_pred",
    hr_peak_field: str = "hr_peak",
    age_field: str = "age",
) -> pd.Series:
    """
    努力度评分（基于 HR 代理）：
    - hr_peak_pct_pred ≥ adequate_threshold → 1.0（充足）
    - uncertain_threshold ≤ hr_peak_pct_pred < adequate_threshold → 0.5
    - < uncertain_threshold → 0.0（不充分）
    - NaN → 0.5（中性，不因缺失惩罚过重）

    若 hr_peak_pct_pred 不存在，尝试用 hr_peak / (220 - age) 代理。
    """
    out = pd.Series(0.5, index=df.index, dtype=float)  # 默认中性

    if hr_pct_field in df.columns:
        hr_pct = pd.to_numeric(df[hr_pct_field], errors="coerce")
    elif hr_peak_field in df.columns and age_field in df.columns:
        hr_num = pd.to_numeric(df[hr_peak_field], errors="coerce")
        age_num = pd.to_numeric(df[age_field], errors="coerce")
        max_hr = 220.0 - age_num
        hr_pct = hr_num / max_hr * 100.0
    else:
        logger.debug("HR effort fields not available, returning 0.5 for all rows")
        return out

    valid = hr_pct.notna()
    out.loc[valid & (hr_pct >= adequate_threshold)] = 1.0
    out.loc[valid & (hr_pct >= uncertain_threshold) & (hr_pct < adequate_threshold)] = 0.5
    out.loc[valid & (hr_pct < uncertain_threshold)] = 0.0

    return out


def compute_anchor_agreement(
    external_zone: pd.Series,
    internal_zone: pd.Series,
) -> pd.Series:
    """
    外部 VO2peak 参考解释 vs 内部分位解释一致性：
      same      → 1.0
      adjacent  → 0.5
      discordant→ 0.0
      任一缺失  → 0.5（中性）
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
    final_zone vs outcome model 风险三分位比对：
      tertile 约定：low / mid / high（与 green/yellow/red 对应）
      same      → 1.0
      adjacent  → 0.5
      discordant→ 0.0
      任一缺失  → 0.5（中性）
    """
    zone_map = {"green": 0, "yellow": 1, "red": 2}
    tertile_map = {"low": 0, "mid": 1, "high": 2}

    a = zone.map(zone_map)
    b = outcome_risk_tertile.map(tertile_map)

    out = pd.Series(0.5, index=zone.index, dtype=float)
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
    *,
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """
    综合置信度公式。
    默认权重：completeness=0.40, effort=0.15, anchor=0.20, validation=0.25
    """
    if weights is None:
        weights = {
            "completeness": 0.40,
            "effort": 0.15,
            "anchor_agreement": 0.20,
            "validation_agreement": 0.25,
        }

    return (
        weights["completeness"] * completeness.fillna(0.0)
        + weights["effort"] * effort_score.fillna(0.5)
        + weights["anchor_agreement"] * anchor_agreement.fillna(0.5)
        + weights["validation_agreement"] * validation_agreement.fillna(0.5)
    )


def label_confidence(
    score: pd.Series,
    *,
    high_threshold: float = 0.75,
    medium_threshold: float = 0.60,
) -> pd.Series:
    """
    置信度数值分层：
      ≥ high_threshold  → "high"
      ≥ medium_threshold → "medium"
      < medium_threshold → "low"
    """
    out = pd.Series(index=score.index, dtype="object")
    out[score >= high_threshold] = "high"
    out[(score >= medium_threshold) & (score < high_threshold)] = "medium"
    out[score < medium_threshold] = "low"
    out[score.isna()] = np.nan
    return out


def finalize_zone_with_uncertainty(
    zone_before_confidence: pd.Series,
    confidence_score: pd.Series,
    instability_severe: pd.Series,
    *,
    indeterminate_threshold: float = 0.60,
) -> pd.DataFrame:
    """
    应用 indeterminate 逻辑：
    - severe instability 一律保留 red（confidence 无法覆盖）
    - 无 severe + confidence < threshold → final_zone = "yellow_gray"（indeterminate）
    - 否则 final_zone = zone_before_confidence

    Returns DataFrame with:
    - confidence_score
    - confidence_label
    - indeterminate_flag
    - final_zone
    """
    out = pd.DataFrame(index=zone_before_confidence.index)
    out["confidence_score"] = confidence_score
    out["confidence_label"] = label_confidence(
        confidence_score, high_threshold=0.75, medium_threshold=0.60
    )

    severe = instability_severe.fillna(False).astype(bool)
    low_conf = confidence_score < indeterminate_threshold

    final_zone = zone_before_confidence.astype("object").copy()

    # 非 severe + low confidence → indeterminate
    indeterminate_mask = (~severe) & low_conf
    final_zone[indeterminate_mask] = "yellow_gray"

    out["indeterminate_flag"] = indeterminate_mask
    out["final_zone"] = final_zone

    return out


def load_confidence_config(cfg_path: str | Path) -> dict[str, Any]:
    """从 zone_rules_stage1b.yaml 读取 confidence 节配置。"""
    path = Path(cfg_path)
    if not path.exists():
        raise FileNotFoundError(f"Zone rules not found: {path}")
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get("confidence", {})


def run_confidence_engine(
    df: pd.DataFrame,
    zone_before_confidence: pd.Series,
    instability_severe: pd.Series,
    *,
    cfg_path: str | Path = "configs/data/zone_rules_stage1b.yaml",
    external_zone: pd.Series | None = None,
    outcome_risk_tertile: pd.Series | None = None,
    variable_roles_path: str | Path = "configs/data/variable_roles_stage1b.yaml",
) -> ConfidenceResult:
    """
    主入口：计算置信度四要素 → 综合分数 → 分层 → finalize zone。

    Parameters
    ----------
    df : 包含所有字段的数据
    zone_before_confidence : instability override 后的 zone
    instability_severe : bool Series（severe instability flag）
    cfg_path : zone_rules_stage1b.yaml 路径
    external_zone : 外部参考解释（如无则用 internal zone 自身）
    outcome_risk_tertile : outcome model 风险三分位（如无则给 NaN，weight 用中性 0.5）
    variable_roles_path : variable_roles_stage1b.yaml（加载 confidence_fields）
    """
    # 加载 confidence 权重配置
    conf_cfg = load_confidence_config(cfg_path)
    weights = conf_cfg.get("weights", {})
    thresholds = conf_cfg.get("thresholds", {})
    high_thr = thresholds.get("high", 0.75)
    medium_thr = thresholds.get("medium", 0.60)
    indet_thr = conf_cfg.get("indeterminate_if_below", 0.60)

    # 加载字段分类（从 variable_roles_stage1b.yaml）
    reserve_fields: list[str] = []
    ventilatory_fields: list[str] = []
    instability_fields: list[str] = []
    hr_pct_field = "hr_peak_pct_pred"
    adequate_thr = 85.0

    if Path(variable_roles_path).exists():
        with open(variable_roles_path, encoding="utf-8") as f:
            vr_cfg = yaml.safe_load(f) or {}
        cf = vr_cfg.get("confidence_fields", {})
        reserve_fields = cf.get("reserve", [])
        ventilatory_fields = cf.get("ventilatory", [])
        instability_fields = cf.get("instability", [])
        ep = cf.get("effort_proxy", {})
        hr_pct_field = ep.get("field", "hr_peak_pct_pred")
        adequate_thr = float(ep.get("adequate_threshold", 85.0))

    # A. Completeness
    completeness = compute_completeness_score(
        df,
        reserve_fields=reserve_fields,
        ventilatory_fields=ventilatory_fields,
        instability_fields=instability_fields,
    )

    # B. Effort
    effort = compute_effort_score(
        df,
        adequate_threshold=adequate_thr,
        hr_pct_field=hr_pct_field,
    )

    # C. Anchor agreement
    if external_zone is not None:
        anchor_agr = compute_anchor_agreement(external_zone, zone_before_confidence)
    else:
        # 无外部参考时给中性值
        anchor_agr = pd.Series(0.5, index=df.index, dtype=float)

    # D. Validation agreement
    if outcome_risk_tertile is not None:
        valid_agr = compute_validation_agreement(zone_before_confidence, outcome_risk_tertile)
    else:
        valid_agr = pd.Series(0.5, index=df.index, dtype=float)

    # 合并置信度
    conf_weights = {
        "completeness": weights.get("completeness", 0.40),
        "effort": weights.get("effort", 0.15),
        "anchor_agreement": weights.get("anchor_agreement", 0.20),
        "validation_agreement": weights.get("validation_agreement", 0.25),
    }
    confidence_score = compute_confidence(
        completeness, effort, anchor_agr, valid_agr, weights=conf_weights
    )

    # Finalize
    finalized = finalize_zone_with_uncertainty(
        zone_before_confidence,
        confidence_score,
        instability_severe,
        indeterminate_threshold=indet_thr,
    )

    # 合并调试列
    result_df = finalized.copy()
    result_df["completeness_score"] = completeness
    result_df["effort_score"] = effort

    # 统计
    conf_label = finalized["confidence_label"]
    n_high = int((conf_label == "high").sum())
    n_medium = int((conf_label == "medium").sum())
    n_low = int((conf_label == "low").sum())
    n_indet = int(finalized["indeterminate_flag"].sum())

    logger.info(
        "ConfidenceEngine: high=%d, medium=%d, low=%d, indeterminate=%d",
        n_high, n_medium, n_low, n_indet,
    )

    return ConfidenceResult(
        df=result_df,
        n_high=n_high,
        n_medium=n_medium,
        n_low=n_low,
        n_indeterminate=n_indet,
    )


def generate_confidence_report(
    result: ConfidenceResult,
    df_original: pd.DataFrame | None = None,
    *,
    output_path: str | Path | None = None,
) -> str:
    """生成置信度报告（Markdown）。"""
    df = result.df
    n = len(df)

    lines: list[str] = [
        "# Confidence Engine Report (Stage 1B)\n",
        f"- 总样本数：{n}",
        f"- High confidence：{result.n_high} ({100*result.n_high/n:.1f}%)",
        f"- Medium confidence：{result.n_medium} ({100*result.n_medium/n:.1f}%)",
        f"- Low confidence：{result.n_low} ({100*result.n_low/n:.1f}%)",
        f"- Indeterminate（低置信度覆盖为 yellow_gray）：{result.n_indeterminate} ({100*result.n_indeterminate/n:.1f}%)\n",
        "## final_zone 分布\n",
        "| Zone | N | % |",
        "|---|---|---|",
    ]

    if "final_zone" in df.columns:
        zone_vals = ["green", "yellow", "red", "yellow_gray"]
        for zone in zone_vals:
            cnt = int((df["final_zone"] == zone).sum())
            if cnt > 0:
                lines.append(f"| {zone} | {cnt} | {100*cnt/n:.1f}% |")
        nan_cnt = int(df["final_zone"].isna().sum())
        if nan_cnt > 0:
            lines.append(f"| NaN | {nan_cnt} | {100*nan_cnt/n:.1f}% |")

    lines.append("\n## 置信度分数分布\n")
    if "confidence_score" in df.columns:
        cs = df["confidence_score"].dropna()
        if len(cs) > 0:
            lines.extend([
                f"- Mean ± std：{cs.mean():.3f} ± {cs.std():.3f}",
                f"- Median：{cs.median():.3f}",
                f"- P25/P75：{cs.quantile(0.25):.3f} / {cs.quantile(0.75):.3f}",
            ])

    # 高置信度 vs 低置信度 final_zone 梯度
    if "final_zone" in df.columns and "confidence_label" in df.columns:
        lines.append("\n## 高置信度样本中的 final_zone 梯度（对比低置信度）\n")
        lines.append("| confidence_label | green% | yellow% | red% | indeterminate% |")
        lines.append("|---|---|---|---|---|")
        for lbl in ["high", "medium", "low"]:
            sub = df[df["confidence_label"] == lbl]
            if len(sub) == 0:
                continue
            g = 100 * (sub["final_zone"] == "green").mean()
            y = 100 * (sub["final_zone"] == "yellow").mean()
            r = 100 * (sub["final_zone"] == "red").mean()
            yg = 100 * (sub["final_zone"] == "yellow_gray").mean()
            lines.append(f"| {lbl} | {g:.1f}% | {y:.1f}% | {r:.1f}% | {yg:.1f}% |")

    # 与 test_result 的构念效度（仅高置信度样本）
    if df_original is not None and "test_result" in df_original.columns and "final_zone" in df.columns:
        lines.append("\n## 高置信度样本 final_zone vs test_result 阳性率\n")
        lines.append("| Zone | N | test_result 阳性率 |")
        lines.append("|---|---|---|")
        merged = df[["final_zone", "confidence_label"]].join(
            df_original[["test_result"]], how="inner"
        )
        merged["positive"] = merged["test_result"].astype(str).str.contains(
            "阳性|positive|1", case=False, regex=True
        )
        high_sub = merged[merged["confidence_label"] == "high"]
        for zone in ["green", "yellow", "red"]:
            sub = high_sub[high_sub["final_zone"] == zone]
            if len(sub) == 0:
                continue
            pos_rate = 100 * sub["positive"].mean()
            lines.append(f"| {zone}（高置信） | {len(sub)} | {pos_rate:.1f}% |")

    report = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report, encoding="utf-8")
        logger.info("Confidence report saved to %s", output_path)

    return report
