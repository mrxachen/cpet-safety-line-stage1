"""
safety_zone.py — P1 安全区字符串映射与报告生成。

功能：
- assign_zones(): 将 P1 zone 整数映射为字符串（green/yellow/red）
- generate_zone_report(): 生成标签分布 Markdown 报告
"""

from __future__ import annotations

import pandas as pd


# 区域整数 → 字符串映射
_ZONE_MAP: dict[int, str] = {
    0: "green",
    1: "yellow",
    2: "red",
}


def assign_zones(p1_zone: pd.Series) -> pd.Series:
    """
    将 P1 zone int Series 映射为字符串 Series。

    参数：
        p1_zone: int/float Series（0=green, 1=yellow, 2=red, NaN=NaN）

    返回：
        z_lab_zone: str Series（NaN 保留为 NaN）
    """
    return p1_zone.map(lambda v: _ZONE_MAP.get(int(v), None) if pd.notna(v) else None)


def generate_zone_report(label_result: "LabelResult", df: pd.DataFrame) -> str:  # noqa: F821
    """
    生成标签分布 Markdown 报告。

    参数：
        label_result: LabelResult 实例
        df: 原始 cohort DataFrame（用于分组统计）

    返回：
        Markdown 格式字符串
    """
    from cpet_stage1.labels.label_engine import LabelResult  # 本地导入避免循环

    ldf = label_result.label_df
    n = len(ldf)

    lines = [
        "# 标签分布报告",
        "",
        "## P0 运动安全事件代理",
        "",
    ]

    # P0 总体
    n_pos = int(ldf["p0_event"].sum())
    pct_pos = 100 * n_pos / n if n > 0 else 0
    lines += [
        f"- 总样本量: {n}",
        f"- P0 阳性: {n_pos} ({pct_pos:.1f}%)",
        "",
        "### P0 触发器分布",
        "",
        "| 触发器 | 阳性数 | 占比 |",
        "|---|---|---|",
    ]
    for trig_col, trig_name in [
        ("p0_trigger_eih", "EIH（运动高血压）"),
        ("p0_trigger_capacity", "VO2peak < 50%pred"),
        ("p0_trigger_bp", "BP峰值 > 220 mmHg"),
    ]:
        if trig_col in ldf.columns:
            cnt = int(ldf[trig_col].sum())
            pct = 100 * cnt / n if n > 0 else 0
            lines.append(f"| {trig_name} | {cnt} | {pct:.1f}% |")

    lines += ["", "## P1 实验室安全区", ""]

    # P1 总体
    p1 = ldf["p1_zone"]
    lines += [
        "| 区域 | 样本量 | 占比 |",
        "|---|---|---|",
    ]
    for zone_val, zone_name in [(0, "🟢 Green"), (1, "🟡 Yellow"), (2, "🔴 Red")]:
        cnt = int((p1 == zone_val).sum())
        pct = 100 * cnt / n if n > 0 else 0
        lines.append(f"| {zone_name} | {cnt} | {pct:.1f}% |")
    n_nan = int(p1.isna().sum())
    if n_nan:
        lines.append(f"| NaN（全缺失）| {n_nan} | {100 * n_nan / n:.1f}% |")

    # 按 cohort_2x2 分组统计（若列存在）
    if "cohort_2x2" in df.columns:
        lines += ["", "### P1 分区按队列分布", ""]
        p1_with_cohort = pd.concat(
            [ldf["p1_zone"], df["cohort_2x2"]], axis=1
        )
        zone_names = {0: "green", 1: "yellow", 2: "red"}
        for quad in sorted(df["cohort_2x2"].dropna().unique()):
            sub = p1_with_cohort[p1_with_cohort["cohort_2x2"] == quad]["p1_zone"]
            n_sub = len(sub)
            parts = []
            for zv, zn in zone_names.items():
                cnt = int((sub == zv).sum())
                parts.append(f"{zn}={cnt}")
            lines.append(f"- **{quad}** (N={n_sub}): {', '.join(parts)}")

    # effort flag
    if "effort_hr_adequate" in ldf.columns:
        n_eff = int(ldf["effort_hr_adequate"].sum())
        pct_eff = 100 * n_eff / n if n > 0 else 0
        lines += [
            "",
            "## HR 努力度代理",
            "",
            f"- HR 充足（>= 85% HRmax_pred）: {n_eff} ({pct_eff:.1f}%)",
        ]

    # inactive criteria
    if label_result.inactive_criteria:
        lines += ["", "## Inactive 规则（数据不可用）", ""]
        for ic in label_result.inactive_criteria:
            lines.append(f"- {ic}")

    return "\n".join(lines)
