"""
zone_sensitivity.py — Phase F Step 3：Zone 边界验证与敏感性分析

操作：
1. 阈值敏感性扫描：在文献阈值 ±10% 范围内扫描 zone 分布变化
2. Bootstrap 95% CI：对参考人群分位切点做 1000 次 bootstrap
3. 文献阈值一致性检查：数据驱动切点 vs Weber-Janicki 文献值
4. 亚组一致性分析：按 HTN/CTRL、男/女、年龄分层验证
5. 新旧 zone 重分类汇总

输出：reports/zone_sensitivity_report.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── 文献先验阈值（Weber-Janicki 1983 + AHA 2010 等）──────────────────────────
LITERATURE_REF = {
    "vo2_peak_pct_pred_yellow_low": 50.0,   # <50% = Red（严重功能受限）
    "vo2_peak_pct_pred_green_high": 70.0,   # ≥70% = Green（轻度受限）
    "ve_vco2_slope_yellow_low": 30.0,       # ≥30 = Yellow
    "ve_vco2_slope_red_high": 36.0,         # >36 = Red
}

# ── 扫描参数 ─────────────────────────────────────────────────────────────────
SCAN_DELTAS = [-0.10, -0.05, 0.0, +0.05, +0.10]  # ±5%, ±10%


@dataclass
class SensitivityScanResult:
    """单个参数的切点敏感性扫描结果。"""
    param_name: str
    base_cutpoint: float
    scan_results: list[dict[str, Any]]   # [{delta, cutpoint, green%, yellow%, red%, n_reclassified}]


@dataclass
class ZoneSensitivityResult:
    """敏感性分析完整结果。"""
    scan_results: list[SensitivityScanResult]
    bootstrap_ci: dict[str, tuple[float, float]]  # {参数名: (low_ci, high_ci)}
    literature_check: list[dict[str, Any]]         # 文献一致性检查
    subgroup_consistency: pd.DataFrame             # 亚组 zone 分布
    reclassification_summary: dict[str, Any]

    def to_markdown(self, path: str | Path | None = None) -> str:
        lines = [
            "# Phase F Step 3 — Zone 边界验证与敏感性分析报告",
            "",
        ]

        # ── 1. 阈值敏感性扫描 ────────────────────────────────────────────────
        lines.append("## 1. 阈值敏感性扫描")
        lines.append("")
        lines.append(
            "下表展示参考分位切点在 ±5%、±10% 偏移时 zone 分布的变化。"
            "若偏移后 zone 分布变化 < 5pp，说明切点稳健。"
        )
        lines.append("")

        for sr in self.scan_results:
            lines.append(f"### {sr.param_name}（基准切点: {sr.base_cutpoint:.2f}）")
            lines.append("")
            rows = sr.scan_results
            if rows:
                df_rows = pd.DataFrame(rows)
                lines.append(_df_to_pipe_table(df_rows, index=False))
            lines.append("")

        # ── 2. Bootstrap 置信区间 ────────────────────────────────────────────
        lines.append("## 2. Bootstrap 95% 置信区间（参考分位切点）")
        lines.append("")
        lines.append("| 切点参数 | 95% CI 下界 | 95% CI 上界 | CI 宽度 | 稳定性 |")
        lines.append("|---|---|---|---|---|")
        for pname, (lo, hi) in self.bootstrap_ci.items():
            width = hi - lo
            stability = "✅ 稳定（<2）" if width < 2 else ("⚠ 中等（2-5）" if width < 5 else "❌ 不稳定（>5）")
            lines.append(f"| {pname} | {lo:.2f} | {hi:.2f} | {width:.2f} | {stability} |")
        lines.append("")
        lines.append(
            "> **解读**：CI 宽度 < 2.0 表示切点估计非常稳定；CI 宽度 > 5.0 表示需要更多数据。"
        )
        lines.append("")

        # ── 3. 文献阈值一致性检查 ────────────────────────────────────────────
        lines.append("## 3. 与文献阈值的一致性检查")
        lines.append("")
        if self.literature_check:
            lines.append("| 指标 | 文献阈值 | 数据驱动切点（对应%pred） | 偏差 | 解读 |")
            lines.append("|---|---|---|---|---|")
            for chk in self.literature_check:
                lines.append(
                    f"| {chk['metric']} | {chk['literature']:.1f} | "
                    f"{chk['data_driven']:.1f} | {chk['deviation']:+.1f} | {chk['interpretation']} |"
                )
            lines.append("")
            lines.append(
                "> **说明**：文献阈值来自 Weber & Janicki (1983) 心衰分级 + AHA/ACSM 运动测试指南。"
                "偏差 < 10% 表示本人群与文献参考基本一致；偏差 > 20% 提示人群特异性阈值的必要性。"
            )
        else:
            lines.append("*(无文献对比数据)*")
        lines.append("")

        # ── 4. 亚组一致性 ────────────────────────────────────────────────────
        lines.append("## 4. 亚组 Zone 分布一致性")
        lines.append("")
        if not self.subgroup_consistency.empty:
            lines.append(_df_to_pipe_table(self.subgroup_consistency, index=False))
        else:
            lines.append("*(无亚组数据)*")
        lines.append("")

        # ── 5. 重分类汇总 ────────────────────────────────────────────────────
        lines.append("## 5. 新旧 Zone 重分类汇总")
        lines.append("")
        rc = self.reclassification_summary
        if rc:
            lines.append(f"- **总样本量**：{rc.get('n_total', 'N/A')}")
            lines.append(f"- **一致率（对角线）**：{rc.get('agreement_rate', 'N/A'):.1%}")
            lines.append(f"- **重分类率**：{rc.get('reclassification_rate', 'N/A'):.1%}")
            lines.append("")
            lines.append("### 重分类详情")
            lines.append("")
            lines.append("| 旧 zone → 新 zone | N | 占比 |")
            lines.append("|---|---|---|")
            for trans, n in rc.get("transitions", {}).items():
                pct = 100 * n / rc["n_total"] if rc["n_total"] > 0 else 0
                flag = " ⚠️" if "red" in trans.lower() and "green" in trans.lower() else ""
                lines.append(f"| {trans}{flag} | {n} | {pct:.1f}% |")
            lines.append("")
            lines.append(
                "> **注意**：⚠️ 标记的行（Red↔Green 跨越）需要临床审查，"
                "这些患者在旧 zone 和新 zone 之间的分类存在根本差异。"
            )
        lines.append("")

        md = "\n".join(lines)
        if path is not None:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(md, encoding="utf-8")
            logger.info("敏感性分析报告已写入：%s", p)
        return md


def _df_to_pipe_table(df: pd.DataFrame, index: bool = False) -> str:
    if df is None or df.empty:
        return "*(空)*"
    if index:
        df = df.reset_index()
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    rows = ["| " + " | ".join(str(row[c]) for c in cols) + " |" for _, row in df.iterrows()]
    return "\n".join([header, sep] + rows)


def _zone_from_score(score: pd.Series, low_cut: float, high_cut: float) -> pd.Series:
    """根据切点将连续评分转为 zone。"""
    return score.map(
        lambda x: "green" if pd.notna(x) and x < low_cut else
                  ("yellow" if pd.notna(x) and x < high_cut else
                   ("red" if pd.notna(x) else None))
    )


def _zone_distribution(zone: pd.Series) -> dict[str, float]:
    """计算 zone 百分比分布。"""
    n = zone.notna().sum()
    if n == 0:
        return {"green": 0.0, "yellow": 0.0, "red": 0.0}
    return {
        z: round(100 * (zone == z).sum() / n, 1)
        for z in ["green", "yellow", "red"]
    }


def run_sensitivity_analysis(
    df: pd.DataFrame,
    s_lab_col: str = "s_lab_v2",
    z_lab_col: str = "z_lab_v2",
    old_zone_col: str | None = "p1_zone",
    reference_flag_col: str = "reference_flag_wide",
    ref_pct_low: float = 75.0,
    ref_pct_high: float = 90.0,
    n_bootstrap: int = 1000,
    random_state: int = 42,
    output_path: str | Path | None = None,
) -> ZoneSensitivityResult:
    """
    主入口：对 zone_engine_v2 的输出进行敏感性分析。

    Parameters
    ----------
    df : zone_engine_v2 输出 DataFrame（含 s_lab_v2, z_lab_v2）
    s_lab_col : S_lab_v2 连续评分列名
    z_lab_col : Z_lab_v2 zone 列名（主 zone）
    old_zone_col : 旧 P1 zone 列名（重分类对比用）
    reference_flag_col : 参考子集标志列名
    ref_pct_low : 参考分位低切点百分位（默认75th）
    ref_pct_high : 参考分位高切点百分位（默认90th）
    n_bootstrap : Bootstrap 次数
    random_state : 随机种子
    output_path : 报告输出路径

    Returns
    -------
    ZoneSensitivityResult
    """
    rng = np.random.default_rng(random_state)

    if s_lab_col not in df.columns:
        raise ValueError(f"S_lab 列不存在：{s_lab_col}")

    s_lab = df[s_lab_col].astype(float)

    # 参考子集
    if reference_flag_col in df.columns:
        ref_mask = df[reference_flag_col].astype(bool)
    else:
        ref_mask = pd.Series(False, index=df.index)
        if "group_code" in df.columns:
            ref_mask = (df["group_code"] == "CTRL")

    ref_scores = s_lab[ref_mask].dropna()
    base_low = float(np.percentile(ref_scores, ref_pct_low)) if len(ref_scores) > 0 else s_lab.quantile(0.33)
    base_high = float(np.percentile(ref_scores, ref_pct_high)) if len(ref_scores) > 0 else s_lab.quantile(0.67)

    logger.info("敏感性分析开始: base_low=%.2f, base_high=%.2f, n=%d", base_low, base_high, len(df))

    # ── 1. 阈值敏感性扫描 ────────────────────────────────────────────────────
    scan_results: list[SensitivityScanResult] = []

    base_zone = _zone_from_score(s_lab, base_low, base_high)
    base_dist = _zone_distribution(base_zone)

    for param, base_cut, scan_col in [
        ("低切点（Green/Yellow界）", base_low, "low"),
        ("高切点（Yellow/Red界）", base_high, "high"),
    ]:
        rows = []
        for delta in SCAN_DELTAS:
            if scan_col == "low":
                cut_low = base_low * (1 + delta)
                cut_high = base_high
            else:
                cut_low = base_low
                cut_high = base_high * (1 + delta)

            zone_scan = _zone_from_score(s_lab, cut_low, cut_high)
            dist = _zone_distribution(zone_scan)

            # 重分类量（与基准 zone 不同的样本数）
            valid_both = zone_scan.notna() & base_zone.notna()
            n_reclass = int((zone_scan[valid_both] != base_zone[valid_both]).sum())

            rows.append({
                "偏移": f"{delta:+.0%}",
                "切点值": f"{cut_low:.2f}" if scan_col == "low" else f"{cut_high:.2f}",
                "Green%": dist["green"],
                "Yellow%": dist["yellow"],
                "Red%": dist["red"],
                "重分类N": n_reclass,
                "重分类%": f"{100*n_reclass/valid_both.sum():.1f}%" if valid_both.sum() > 0 else "—",
            })

        scan_results.append(SensitivityScanResult(
            param_name=param,
            base_cutpoint=base_cut,
            scan_results=rows,
        ))

    # ── 2. Bootstrap 95% CI ──────────────────────────────────────────────────
    bootstrap_ci: dict[str, tuple[float, float]] = {}

    if len(ref_scores) >= 10 and n_bootstrap > 0:
        boot_lows, boot_highs = [], []
        n_ref = len(ref_scores)
        for _ in range(n_bootstrap):
            boot_idx = rng.choice(n_ref, size=n_ref, replace=True)
            boot_ref = ref_scores.values[boot_idx]
            boot_lows.append(float(np.percentile(boot_ref, ref_pct_low)))
            boot_highs.append(float(np.percentile(boot_ref, ref_pct_high)))

        bootstrap_ci["低切点（P75参考）"] = (
            float(np.percentile(boot_lows, 2.5)),
            float(np.percentile(boot_lows, 97.5)),
        )
        bootstrap_ci["高切点（P90参考）"] = (
            float(np.percentile(boot_highs, 2.5)),
            float(np.percentile(boot_highs, 97.5)),
        )
        logger.info("Bootstrap CI: low=[%.2f, %.2f], high=[%.2f, %.2f]",
                    *bootstrap_ci["低切点（P75参考）"], *bootstrap_ci["高切点（P90参考）"])

    # ── 3. 文献阈值一致性检查 ────────────────────────────────────────────────
    literature_check: list[dict[str, Any]] = []

    # 检查在 Green/Yellow 界（low_cut）处，vo2_peak_pct_pred 的中位值
    if "vo2_peak_pct_pred" in df.columns:
        # 找 S_lab_v2 ≈ base_low 附近的患者（±2个单位）
        near_low = (s_lab - base_low).abs() < 2.0
        if near_low.sum() > 5:
            vo2_at_low = df.loc[near_low, "vo2_peak_pct_pred"].median()
            dev = vo2_at_low - LITERATURE_REF["vo2_peak_pct_pred_green_high"]
            interp = (
                "✅ 基本一致（偏差<10%）" if abs(dev) < 10 else
                "⚠ 中等偏差（10-20%）" if abs(dev) < 20 else
                "❌ 显著偏差（>20%），提示人群特异阈值"
            )
            literature_check.append({
                "metric": "VO₂peak %pred @ Green/Yellow 界",
                "literature": LITERATURE_REF["vo2_peak_pct_pred_green_high"],
                "data_driven": vo2_at_low,
                "deviation": dev,
                "interpretation": interp,
            })

        near_high = (s_lab - base_high).abs() < 2.0
        if near_high.sum() > 5:
            vo2_at_high = df.loc[near_high, "vo2_peak_pct_pred"].median()
            dev_h = vo2_at_high - LITERATURE_REF["vo2_peak_pct_pred_yellow_low"]
            interp_h = (
                "✅ 基本一致（偏差<10%）" if abs(dev_h) < 10 else
                "⚠ 中等偏差（10-20%）" if abs(dev_h) < 20 else
                "❌ 显著偏差（>20%），提示人群特异阈值"
            )
            literature_check.append({
                "metric": "VO₂peak %pred @ Yellow/Red 界",
                "literature": LITERATURE_REF["vo2_peak_pct_pred_yellow_low"],
                "data_driven": vo2_at_high,
                "deviation": dev_h,
                "interpretation": interp_h,
            })

    if "ve_vco2_slope" in df.columns:
        near_high = (s_lab - base_high).abs() < 2.0
        if near_high.sum() > 5:
            ve_at_high = df.loc[near_high, "ve_vco2_slope"].median()
            dev_ve = ve_at_high - LITERATURE_REF["ve_vco2_slope_red_high"]
            interp_ve = (
                "✅ 基本一致（偏差<2）" if abs(dev_ve) < 2 else
                "⚠ 中等偏差（2-5）" if abs(dev_ve) < 5 else
                "❌ 显著偏差（>5）"
            )
            literature_check.append({
                "metric": "VE/VCO₂ slope @ Yellow/Red 界",
                "literature": LITERATURE_REF["ve_vco2_slope_red_high"],
                "data_driven": ve_at_high,
                "deviation": dev_ve,
                "interpretation": interp_ve,
            })

    # ── 4. 亚组一致性 ────────────────────────────────────────────────────────
    subgroup_rows: list[dict[str, Any]] = []

    strat_cols = {
        "group_code": ["CTRL", "HTN_HISTORY_NO_EHT", "HTN_HISTORY_WITH_EHT", "EHT_ONLY"],
        "sex": ["M", "F"],
        "age_group": ["age<67", "age>=67"],
    }

    for col, vals in strat_cols.items():
        if col not in df.columns:
            continue
        for val in vals:
            mask = df[col].astype(str) == str(val)
            if mask.sum() < 10:
                continue
            sub_z = df.loc[mask, z_lab_col] if z_lab_col in df.columns else base_zone[mask]
            dist = _zone_distribution(sub_z)
            subgroup_rows.append({
                "分层因子": col,
                "分层值": val,
                "N": int(mask.sum()),
                "Green%": dist["green"],
                "Yellow%": dist["yellow"],
                "Red%": dist["red"],
            })

    subgroup_consistency = pd.DataFrame(subgroup_rows) if subgroup_rows else pd.DataFrame()

    # ── 5. 重分类汇总 ────────────────────────────────────────────────────────
    reclassification_summary: dict[str, Any] = {}

    if old_zone_col and old_zone_col in df.columns and z_lab_col in df.columns:
        _ZONE_MAP_INT = {0: "green", 1: "yellow", 2: "red", 0.0: "green", 1.0: "yellow", 2.0: "red"}
        old_zone = df[old_zone_col].map(
            lambda x: _ZONE_MAP_INT.get(x, str(x)) if pd.notna(x) else None
        )
        new_zone = df[z_lab_col]

        valid_both = old_zone.notna() & new_zone.notna()
        n_valid = int(valid_both.sum())

        if n_valid > 0:
            agree = int((old_zone[valid_both] == new_zone[valid_both]).sum())

            # 统计所有转换
            transitions: dict[str, int] = {}
            for old_z, new_z in zip(old_zone[valid_both], new_zone[valid_both]):
                key = f"{old_z} → {new_z}"
                transitions[key] = transitions.get(key, 0) + 1

            # 按频次排序
            transitions = dict(sorted(transitions.items(), key=lambda x: -x[1]))

            reclassification_summary = {
                "n_total": n_valid,
                "agreement_rate": agree / n_valid,
                "reclassification_rate": 1 - agree / n_valid,
                "transitions": transitions,
            }

    result = ZoneSensitivityResult(
        scan_results=scan_results,
        bootstrap_ci=bootstrap_ci,
        literature_check=literature_check,
        subgroup_consistency=subgroup_consistency,
        reclassification_summary=reclassification_summary,
    )

    if output_path is not None:
        result.to_markdown(output_path)

    return result
