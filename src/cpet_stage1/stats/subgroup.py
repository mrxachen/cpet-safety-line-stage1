"""
subgroup.py — 亚组分析模块。

目的：在性别、年龄（≥/< 中位数）、EIH 状态等亚组中展示 P1 zone 分布和关键指标差异。

提供：
- SubgroupAnalyzer.run(): 生成分层统计摘要
- SubgroupResult: 包含每个亚组的 zone 分布表 + 中位数对比
- generate_subgroup_report(): 生成 Markdown 报告
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)

# 关键 CPET 指标（亚组对比用）
KEY_CPET_VARS = [
    "vo2_peak",
    "hr_peak",
    "o2_pulse_peak",
    "vt1_vo2",
    "ve_vco2_slope",
    "hr_recovery",
    "oues",
    "mets_peak",
]

# P1 zone 顺序
ZONE_ORDER = ["green", "yellow", "red"]


@dataclass
class StratumSummary:
    """单个亚组的摘要统计。"""
    stratum_name: str          # 亚组名称（如 "male"）
    n_total: int
    zone_counts: dict          # {"green": n, "yellow": n, "red": n}
    zone_rates: dict           # {"green": pct, "yellow": pct, "red": pct}
    median_vo2_peak: Optional[float]
    median_vevco2_slope: Optional[float]
    kw_p_vs_complement: Optional[float]  # 与互补组的 KW 检验 p 值（vo2_peak）


@dataclass
class SubgroupResult:
    """亚组分析完整结果。"""
    strata_def: str            # 分层依据（如 "sex", "age_median", "eih_status"）
    summaries: list[StratumSummary]
    n_total: int

    def to_markdown(self) -> str:
        lines = [
            f"## 亚组分析：{self.strata_def}",
            f"",
            f"- 总样本量: N={self.n_total}",
            f"",
            f"### Zone 分布",
            f"",
            f"| 亚组 | N | Green | Yellow | Red | VO₂peak 中位数 | VE/VCO₂斜率中位数 |",
            f"|---|---|---|---|---|---|---|",
        ]
        for s in self.summaries:
            g = f"{s.zone_rates.get('green', 0):.1%}"
            y = f"{s.zone_rates.get('yellow', 0):.1%}"
            r = f"{s.zone_rates.get('red', 0):.1%}"
            vo2 = f"{s.median_vo2_peak:.1f}" if s.median_vo2_peak is not None else "—"
            vevco2 = f"{s.median_vevco2_slope:.1f}" if s.median_vevco2_slope is not None else "—"
            lines.append(f"| {s.stratum_name} | {s.n_total} | {g} | {y} | {r} | {vo2} | {vevco2} |")
        return "\n".join(lines)


class SubgroupAnalyzer:
    """
    亚组分析器。

    使用方法：
        analyzer = SubgroupAnalyzer()
        result = analyzer.run_sex(df, zone_col="p1_zone")
        result2 = analyzer.run_age_median(df, zone_col="p1_zone")
        result3 = analyzer.run_eih(df, zone_col="p1_zone")
        report = generate_subgroup_report([result, result2, result3])
    """

    def run_sex(
        self,
        df: pd.DataFrame,
        zone_col: str = "p1_zone",
        sex_col: str = "sex",
    ) -> SubgroupResult:
        """性别亚组分析（M vs F）。"""
        if sex_col not in df.columns:
            raise ValueError(f"性别列 '{sex_col}' 不存在")

        df_w = df.copy()
        # 标准化 sex 字段
        if df_w[sex_col].dtype == object:
            sex_upper = df_w[sex_col].str.upper()
        else:
            sex_upper = df_w[sex_col].astype(str).str.upper()

        summaries = []
        for label, mask_func in [
            ("男性（M）", lambda s: s == "M"),
            ("女性（F）", lambda s: s == "F"),
        ]:
            mask = mask_func(sex_upper)
            sub = df_w[mask]
            complement = df_w[~mask]
            summaries.append(self._make_summary(label, sub, complement, zone_col))

        return SubgroupResult(
            strata_def="性别（sex）",
            summaries=summaries,
            n_total=len(df_w),
        )

    def run_age_median(
        self,
        df: pd.DataFrame,
        zone_col: str = "p1_zone",
        age_col: str = "age",
    ) -> SubgroupResult:
        """年龄中位数分层（<中位 vs ≥中位）。"""
        if age_col not in df.columns:
            raise ValueError(f"年龄列 '{age_col}' 不存在")

        median_age = df[age_col].median()
        logger.info("年龄中位数: %.1f 岁", median_age)

        summaries = []
        for label, mask in [
            (f"年龄 <{median_age:.0f}岁", df[age_col] < median_age),
            (f"年龄 ≥{median_age:.0f}岁", df[age_col] >= median_age),
        ]:
            sub = df[mask]
            complement = df[~mask]
            summaries.append(self._make_summary(label, sub, complement, zone_col))

        return SubgroupResult(
            strata_def=f"年龄（中位数 {median_age:.0f}岁）",
            summaries=summaries,
            n_total=len(df),
        )

    def run_eih(
        self,
        df: pd.DataFrame,
        zone_col: str = "p1_zone",
        eih_col: str = "eih_status",
    ) -> SubgroupResult:
        """EIH 状态分层（EIH+ vs EIH-）。"""
        if eih_col not in df.columns:
            raise ValueError(f"EIH 状态列 '{eih_col}' 不存在")

        eih = df[eih_col].astype(bool)

        summaries = []
        for label, mask in [
            ("EIH+（运动性低氧）", eih),
            ("EIH-（无低氧）", ~eih),
        ]:
            sub = df[mask]
            complement = df[~mask]
            summaries.append(self._make_summary(label, sub, complement, zone_col))

        return SubgroupResult(
            strata_def="EIH 状态",
            summaries=summaries,
            n_total=len(df),
        )

    def run_htn(
        self,
        df: pd.DataFrame,
        zone_col: str = "p1_zone",
        htn_col: str = "htn_history",
    ) -> SubgroupResult:
        """高血压史分层（HTN+ vs HTN-）。"""
        if htn_col not in df.columns:
            raise ValueError(f"高血压史列 '{htn_col}' 不存在")

        htn = df[htn_col].astype(bool)

        summaries = []
        for label, mask in [
            ("HTN+（有高血压史）", htn),
            ("HTN-（无高血压史）", ~htn),
        ]:
            sub = df[mask]
            complement = df[~mask]
            summaries.append(self._make_summary(label, sub, complement, zone_col))

        return SubgroupResult(
            strata_def="高血压史（HTN）",
            summaries=summaries,
            n_total=len(df),
        )

    def _make_summary(
        self,
        name: str,
        sub: pd.DataFrame,
        complement: pd.DataFrame,
        zone_col: str,
    ) -> StratumSummary:
        """计算单个亚组的摘要统计。"""
        n = len(sub)
        zone_counts: dict = {}
        zone_rates: dict = {}

        if zone_col in sub.columns and n > 0:
            zone_series = sub[zone_col]
            # 处理整数编码的区域（0=green, 1=yellow, 2=red）
            if pd.api.types.is_numeric_dtype(zone_series):
                _INT_MAP = {0: "green", 1: "yellow", 2: "red"}
                zone_series = zone_series.map(lambda v: _INT_MAP.get(int(v), None) if pd.notna(v) else None)
            vc = zone_series.astype(str).str.lower().value_counts()
            for z in ZONE_ORDER:
                zone_counts[z] = int(vc.get(z, 0))
                zone_rates[z] = zone_counts[z] / n
        else:
            for z in ZONE_ORDER:
                zone_counts[z] = 0
                zone_rates[z] = 0.0

        # 中位数
        median_vo2 = None
        if "vo2_peak" in sub.columns and n > 0:
            median_vo2 = float(sub["vo2_peak"].median())

        median_vevco2 = None
        if "ve_vco2_slope" in sub.columns and n > 0:
            median_vevco2 = float(sub["ve_vco2_slope"].median())

        # KW 检验 p 值（亚组 vs 互补组，vo2_peak）
        kw_p = None
        if (
            "vo2_peak" in sub.columns
            and len(sub) > 1
            and len(complement) > 1
        ):
            try:
                stat, kw_p_val = scipy_stats.kruskal(
                    sub["vo2_peak"].dropna().values,
                    complement["vo2_peak"].dropna().values,
                )
                kw_p = float(kw_p_val)
            except Exception:
                pass

        return StratumSummary(
            stratum_name=name,
            n_total=n,
            zone_counts=zone_counts,
            zone_rates=zone_rates,
            median_vo2_peak=median_vo2,
            median_vevco2_slope=median_vevco2,
            kw_p_vs_complement=kw_p,
        )


def generate_subgroup_report(
    results: list[SubgroupResult],
    output_path: str | Path = "reports/subgroup_report.md",
) -> str:
    """
    生成亚组分析 Markdown 报告。

    参数：
        results: SubgroupAnalyzer.run_*() 返回值列表
        output_path: 输出路径

    返回：报告文本
    """
    lines = [
        "# 亚组分析报告",
        "",
        f"分析时间：2026-04-16",
        "",
    ]
    for r in results:
        lines.append(r.to_markdown())
        lines.append("")

    report_text = "\n".join(lines)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    logger.info("亚组分析报告已保存: %s", output_path)

    return report_text
