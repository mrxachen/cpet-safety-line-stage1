"""
instability_rules.py — Stage 1B 不稳定覆盖规则引擎。

职责：
1. 从 zone_rules_stage1b.yaml 加载 severe / mild 规则
2. 对每行评估 severe / mild instability
3. 应用 override 逻辑：
   - severe → 强制 red（不管 phenotype zone）
   - mild + green → yellow
   - mild + yellow/red → 不降级
   - 缺失值不误报 severe

适配说明：
    模板来源：docs/guide/cpet_stage1_method_package/code_templates/instability_rules.py
    在模板基础上增加：
    - 配置文件驱动（zone_rules_stage1b.yaml）
    - eih_status 字符串/bool 两种格式支持
    - 报告生成
    - override 不改变置信度（供 confidence engine 另行处理）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


@dataclass
class RuleConfig:
    """单条规则配置（对应 yaml 中的 instability 规则条目）。"""
    field_name: str
    op: str
    value: Any | None = None
    low: float | None = None
    high: float | None = None


@dataclass
class InstabilityResult:
    """不稳定评估输出。"""
    df: pd.DataFrame        # 含 instability_severe, instability_mild, final_zone_before_confidence
    n_severe: int = 0
    n_mild: int = 0
    n_override_up: int = 0  # 因 override 从 green→yellow 或 any→red 的数量

    def summary(self) -> str:
        n = len(self.df)
        lines = [
            "InstabilityOverride Summary",
            f"  Total: {n}",
            f"  Severe: {self.n_severe} ({100*self.n_severe/n:.1f}%)",
            f"  Mild:   {self.n_mild} ({100*self.n_mild/n:.1f}%)",
            f"  Override(升级): {self.n_override_up} ({100*self.n_override_up/n:.1f}%)",
        ]
        return "\n".join(lines)


def _parse_bool_field(series: pd.Series) -> pd.Series:
    """统一解析 eih_status / bp_peak_dia 等 bool/str 混合列。"""
    s = series.copy()
    # 处理字符串 "True"/"False"/"1"/"0"
    if s.dtype == object:
        s = s.astype(str).str.strip().str.lower()
        bool_map = {"true": True, "1": True, "false": False, "0": False, "nan": False}
        s = s.map(bool_map).fillna(False)
    return s.astype(bool)


def _evaluate_rule(df: pd.DataFrame, rule: RuleConfig) -> pd.Series:
    """
    执行单条规则，返回布尔 Series。
    缺失值（NaN）始终返回 False（不误报）。
    """
    fname = rule.field_name

    if fname not in df.columns:
        logger.debug("Rule field %r not in dataframe, returning all False", fname)
        return pd.Series(False, index=df.index)

    s = df[fname]

    if rule.op == "eq":
        # bool 或字符串比较
        if rule.value is True or str(rule.value).lower() == "true":
            return _parse_bool_field(s)
        elif rule.value is False or str(rule.value).lower() == "false":
            return ~_parse_bool_field(s)
        else:
            return s.astype(str).str.lower() == str(rule.value).lower()

    elif rule.op == "gt":
        x = pd.to_numeric(s, errors="coerce")
        return (x > float(rule.value)).fillna(False)

    elif rule.op == "in":
        vals = [str(v).lower() for v in (rule.value or [])]
        return s.astype(str).str.lower().isin(vals).fillna(False)

    elif rule.op == "between_open_closed":
        x = pd.to_numeric(s, errors="coerce")
        lo = float(rule.low)  # type: ignore[arg-type]
        hi = float(rule.high)  # type: ignore[arg-type]
        return ((x > lo) & (x <= hi)).fillna(False)

    else:
        raise ValueError(f"Unsupported instability rule op: {rule.op!r}")


def load_instability_rules(cfg_path: str | Path) -> tuple[list[RuleConfig], list[RuleConfig]]:
    """
    从 zone_rules_stage1b.yaml 加载 severe / mild 规则列表。

    Returns (severe_rules, mild_rules)
    """
    path = Path(cfg_path)
    if not path.exists():
        raise FileNotFoundError(f"Zone rules not found: {path}")

    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    instab_cfg = cfg.get("instability", {})

    def _parse_rules(entries: list[dict]) -> list[RuleConfig]:
        rules = []
        for entry in (entries or []):
            rules.append(RuleConfig(
                field_name=entry["field"],
                op=entry["op"],
                value=entry.get("value"),
                low=entry.get("low"),
                high=entry.get("high"),
            ))
        return rules

    severe_rules = _parse_rules(instab_cfg.get("severe", []))
    mild_rules = _parse_rules(instab_cfg.get("mild", []))

    logger.info(
        "Loaded instability rules: %d severe, %d mild",
        len(severe_rules), len(mild_rules)
    )
    return severe_rules, mild_rules


def evaluate_instability(
    df: pd.DataFrame,
    severe_rules: list[RuleConfig],
    mild_rules: list[RuleConfig],
) -> pd.DataFrame:
    """
    评估每行的 severe / mild instability。

    Returns DataFrame with columns:
    - instability_severe (bool)
    - instability_mild (bool)  ← mild AND NOT severe

    设计原则：
    - 缺失值不触发 severe（fillna(False)）
    - mild 标记仅在非 severe 时给出（更严格的 severe 覆盖 mild）
    """
    severe = pd.Series(False, index=df.index)
    mild = pd.Series(False, index=df.index)

    for rule in severe_rules:
        flag = _evaluate_rule(df, rule)
        severe = severe | flag

    for rule in mild_rules:
        flag = _evaluate_rule(df, rule)
        mild = mild | flag

    out = pd.DataFrame(index=df.index)
    out["instability_severe"] = severe.astype(bool)
    out["instability_mild"] = (mild & ~severe).astype(bool)
    return out


def apply_override(
    phenotype_zone: pd.Series,
    instability_df: pd.DataFrame,
) -> pd.Series:
    """
    应用不稳定覆盖规则：

    规则：
    1. severe=True → final_zone = "red"（任何 phenotype）
    2. mild=True + phenotype="green" → final_zone = "yellow"（升级，不降级）
    3. mild=True + phenotype="yellow"/"red" → 保持不变
    4. NaN phenotype → 保持 NaN（不强行覆盖）

    Returns Series: final_zone_before_confidence
    """
    final_zone = phenotype_zone.astype("object").copy()

    severe = instability_df["instability_severe"].fillna(False)
    mild = instability_df["instability_mild"].fillna(False)

    # Severe override（包括 NaN phenotype → 如果有 severe flag，仍覆盖为 red）
    final_zone[severe] = "red"

    # Mild upgrade（green → yellow 仅；NaN 不升级）
    mild_green_mask = mild & (final_zone == "green")
    final_zone[mild_green_mask] = "yellow"

    return final_zone


def run_instability_engine(
    df: pd.DataFrame,
    phenotype_zone: pd.Series,
    cfg_path: str | Path = "configs/data/zone_rules_stage1b.yaml",
) -> InstabilityResult:
    """
    主入口：加载规则 → 评估 → 应用覆盖。

    Parameters
    ----------
    df : 包含所有 instability 相关字段的数据
    phenotype_zone : 表型引擎输出的 phenotype_zone（green/yellow/red/NaN）
    cfg_path : zone_rules_stage1b.yaml 路径

    Returns InstabilityResult
    """
    severe_rules, mild_rules = load_instability_rules(cfg_path)

    instab_df = evaluate_instability(df, severe_rules, mild_rules)

    # 记录覆盖前 zone
    zone_before = phenotype_zone.copy()
    final_zone = apply_override(zone_before, instab_df)

    # 统计
    n_severe = int(instab_df["instability_severe"].sum())
    n_mild = int(instab_df["instability_mild"].sum())

    changed_mask = (final_zone != zone_before) & zone_before.notna()
    n_override_up = int(changed_mask.sum())

    result_df = instab_df.copy()
    result_df["final_zone_before_confidence"] = final_zone

    logger.info(
        "InstabilityEngine: severe=%d, mild=%d, override_changes=%d",
        n_severe, n_mild, n_override_up,
    )

    return InstabilityResult(
        df=result_df,
        n_severe=n_severe,
        n_mild=n_mild,
        n_override_up=n_override_up,
    )


def generate_instability_report(
    result: InstabilityResult,
    df_original: pd.DataFrame | None = None,
    *,
    output_path: str | Path | None = None,
) -> str:
    """生成不稳定覆盖报告（Markdown）。"""
    df = result.df
    n = len(df)

    lines: list[str] = [
        "# Instability Override Report (Stage 1B)\n",
        f"- 总样本数：{n}",
        f"- Severe instability：{result.n_severe} ({100*result.n_severe/n:.1f}%)",
        f"- Mild instability（非severe）：{result.n_mild} ({100*result.n_mild/n:.1f}%)",
        f"- 覆盖升级行数：{result.n_override_up} ({100*result.n_override_up/n:.1f}%)\n",
        "## final_zone_before_confidence 分布\n",
        "| Zone | N | % |",
        "|---|---|---|",
    ]

    if "final_zone_before_confidence" in df.columns:
        zone_counts = df["final_zone_before_confidence"].value_counts(dropna=False)
        for zone in ["green", "yellow", "red"]:
            cnt = int(zone_counts.get(zone, 0))
            lines.append(f"| {zone} | {cnt} | {100*cnt/n:.1f}% |")
        nan_cnt = int(df["final_zone_before_confidence"].isna().sum())
        lines.append(f"| NaN | {nan_cnt} | {100*nan_cnt/n:.1f}% |")

    # 与 test_result 的验证
    if df_original is not None and "test_result" in df_original.columns:
        lines.append("\n## 构念效度（final_zone_before_confidence vs test_result）\n")
        lines.append("| Zone | N | test_result 阳性率 |")
        lines.append("|---|---|---|")
        merged = df[["final_zone_before_confidence"]].join(
            df_original[["test_result"]], how="inner"
        )
        merged["positive"] = merged["test_result"].astype(str).str.contains(
            "阳性|positive|1", case=False, regex=True
        )
        for zone in ["green", "yellow", "red"]:
            sub = merged[merged["final_zone_before_confidence"] == zone]
            if len(sub) == 0:
                continue
            pos_rate = 100 * sub["positive"].mean()
            lines.append(f"| {zone} | {len(sub)} | {pos_rate:.1f}% |")

    report = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report, encoding="utf-8")
        logger.info("Instability report saved to %s", output_path)

    return report
