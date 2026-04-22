"""
validators.py — QC 报告生成 + curated 数据输出。

主要函数：
  generate_qc_report(qc_result, df, output_path)
      输出 Markdown 格式 QC 报告（含四组分层统计 + EHT_ONLY 单独段落）

  apply_qc_flags(df, qc_result, output_path)
      根据 QC flags 生成 curated DataFrame（剔除 rejected + 标注 flags）
      输出 curated parquet + qc_flags parquet
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from cpet_stage1.qc.rules import QCEngine, QCResult

logger = logging.getLogger(__name__)

# EHT_ONLY 组的特殊关注字段（运动高血压相关）
_EHT_FOCUS_FIELDS = [
    "bp_peak_sys",
    "bp_rest_sys",
    "exercise_hypertension",
    "vo2_peak",
    "hr_peak",
    "ve_vco2_slope",
    "o2_pulse_trajectory",
]


def generate_qc_report(
    qc_result: QCResult,
    df: pd.DataFrame,
    output_path: str | Path,
) -> str:
    """
    生成 Markdown 格式 QC 报告。

    报告内容：
    1. 概览（总行数、分组、拒绝数）
    2. 各组缺失率热图（文字版）
    3. 范围违规字段统计
    4. 逻辑检查结果
    5. 重复记录
    6. 异常值
    7. 努力度充分性
    8. EHT_ONLY 专项诊断段落

    返回：
        报告文本（str）
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    summary = qc_result.summary
    group_summary = qc_result.group_summary
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ------------------------------------------------------------------ #
    # 标题
    # ------------------------------------------------------------------ #
    lines += [
        "# CPET Stage I — QC 报告",
        "",
        f"> 生成时间：{now_str}",
        f"> 数据规模：{summary.get('n_total', 0)} 行",
        "",
        "---",
        "",
    ]

    # ------------------------------------------------------------------ #
    # 1. 全局概览
    # ------------------------------------------------------------------ #
    lines += [
        "## 1. 全局概览",
        "",
        f"| 指标 | 数值 |",
        f"|---|---|",
        f"| 总行数 | {summary.get('n_total', 0)} |",
        f"| 拒绝行数（关键字段缺失 >50%） | {summary.get('n_rejected', 0)} |",
        f"| 范围越界行数 | {summary.get('n_range_violation', 0)} |",
        f"| 逻辑违规行数 | {summary.get('n_logic_violation', 0)} |",
        f"| 重复记录行数 | {summary.get('n_duplicate', 0)} |",
        f"| IQR 异常值行数 | {summary.get('n_outlier', 0)} |",
        f"| 努力度充分行数 | {summary.get('n_effort_adequate', 0)} ({summary.get('pct_effort_adequate', 0):.1f}%) |",
        "",
    ]

    # ------------------------------------------------------------------ #
    # 2. 分组概览
    # ------------------------------------------------------------------ #
    lines += ["## 2. 分组概览", ""]
    if group_summary:
        header_cols = ["分组", "行数", "拒绝", "范围违规", "逻辑违规", "异常值", "努力度充分"]
        lines.append("| " + " | ".join(header_cols) + " |")
        lines.append("|" + "|".join(["---"] * len(header_cols)) + "|")
        for group, gs in group_summary.items():
            row = [
                group,
                str(gs.get("n", 0)),
                str(gs.get("n_rejected", 0)),
                str(gs.get("n_range_violation", 0)),
                str(gs.get("n_logic_violation", 0)),
                str(gs.get("n_outlier", 0)),
                str(gs.get("n_effort_adequate", 0)),
            ]
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    else:
        lines += ["（无 group_code 列，跳过分组统计）", ""]

    # ------------------------------------------------------------------ #
    # 3. 关键字段缺失率（按组）
    # ------------------------------------------------------------------ #
    lines += ["## 3. 关键字段缺失率", ""]
    key_fields_for_report = ["vo2_peak", "hr_peak", "rer_peak", "vt1_vo2", "ve_vco2_slope", "o2_pulse_peak"]
    existing_kf = [f for f in key_fields_for_report if f in df.columns]
    if existing_kf and group_summary:
        header = ["字段"] + list(group_summary.keys()) + ["全样本"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        for fld in existing_kf:
            miss_rates = []
            for grp in group_summary.keys():
                rate = group_summary[grp].get("key_field_missing_rates", {}).get(fld)
                miss_rates.append(f"{rate * 100:.1f}%" if rate is not None else "N/A")
            overall = df[fld].isna().mean() if fld in df.columns else None
            miss_rates.append(f"{overall * 100:.1f}%" if overall is not None else "N/A")
            lines.append("| " + " | ".join([fld] + miss_rates) + " |")
        lines.append("")
    elif existing_kf:
        lines += [
            "| 字段 | 缺失率 |",
            "|---|---|",
        ]
        for fld in existing_kf:
            r = df[fld].isna().mean() * 100
            lines.append(f"| {fld} | {r:.1f}% |")
        lines.append("")
    else:
        lines += ["（关键字段不在数据集中）", ""]

    # ------------------------------------------------------------------ #
    # 4. 范围越界统计
    # ------------------------------------------------------------------ #
    lines += ["## 4. 范围越界字段", ""]
    if not qc_result.range_flags.empty:
        range_counts = qc_result.range_flags.sum().sort_values(ascending=False)
        range_counts = range_counts[range_counts > 0]
        if len(range_counts) > 0:
            lines += ["| 字段（范围标志） | 越界行数 |", "|---|---|"]
            for col, cnt in range_counts.items():
                lines.append(f"| {col} | {int(cnt)} |")
            lines.append("")
        else:
            lines += ["所有字段均通过范围检查。", ""]
    else:
        lines += ["（无范围检查结果）", ""]

    # ------------------------------------------------------------------ #
    # 5. 逻辑检查
    # ------------------------------------------------------------------ #
    lines += ["## 5. 逻辑一致性检查", ""]
    if not qc_result.logic_flags.empty:
        logic_counts = qc_result.logic_flags.sum().sort_values(ascending=False)
        logic_counts = logic_counts[logic_counts > 0]
        if len(logic_counts) > 0:
            lines += ["| 规则 | 违规行数 |", "|---|---|"]
            for col, cnt in logic_counts.items():
                lines.append(f"| {col} | {int(cnt)} |")
            lines.append("")
        else:
            lines += ["所有逻辑规则均通过。", ""]
    else:
        lines += ["（无逻辑检查结果）", ""]

    # ------------------------------------------------------------------ #
    # 6. 重复记录
    # ------------------------------------------------------------------ #
    lines += ["## 6. 重复记录", ""]
    n_dup = int(qc_result.duplicate_flags.sum()) if not qc_result.duplicate_flags.empty else 0
    if n_dup > 0:
        lines += [f"发现 **{n_dup}** 条重复记录（按 subject_id + test_date），已标记待处理。", ""]
    else:
        lines += ["未发现重复记录。", ""]

    # ------------------------------------------------------------------ #
    # 7. IQR 异常值
    # ------------------------------------------------------------------ #
    lines += ["## 7. IQR 异常值", ""]
    if not qc_result.outlier_flags.empty:
        out_counts = qc_result.outlier_flags.sum().sort_values(ascending=False)
        out_counts = out_counts[out_counts > 0]
        if len(out_counts) > 0:
            lines += ["| 字段（异常值标志） | 异常行数 |", "|---|---|"]
            for col, cnt in out_counts.items():
                lines.append(f"| {col} | {int(cnt)} |")
            lines.append("")
        else:
            lines += ["未检测到 IQR 异常值。", ""]
    else:
        lines += ["（未执行异常值检查）", ""]

    # ------------------------------------------------------------------ #
    # 8. 努力度充分性
    # ------------------------------------------------------------------ #
    lines += ["## 8. 努力度充分性（RER ≥ 1.05）", ""]
    n_eff = summary.get("n_effort_adequate", 0)
    n_total = summary.get("n_total", 1)
    pct_eff = summary.get("pct_effort_adequate", 0)
    lines += [
        f"- 全样本努力度充分：**{n_eff} / {n_total}（{pct_eff:.1f}%）**",
        "",
    ]
    if group_summary:
        lines += ["| 分组 | 行数 | 努力度充分 | 百分比 |", "|---|---|---|---|"]
        for grp, gs in group_summary.items():
            n_g = gs.get("n", 0)
            n_e = gs.get("n_effort_adequate", 0)
            pct_e = n_e / n_g * 100 if n_g > 0 else 0
            lines.append(f"| {grp} | {n_g} | {n_e} | {pct_e:.1f}% |")
        lines.append("")

    # ------------------------------------------------------------------ #
    # 9. EHT_ONLY 专项诊断段落
    # ------------------------------------------------------------------ #
    lines += [
        "---",
        "",
        "## 9. EHT_ONLY 组专项诊断（仅运动高血压）",
        "",
        "> 此组为本研究核心暴露组，特殊关注其 CPET 安全指标分布。",
        "",
    ]
    if "group_code" in df.columns and "EHT_ONLY" in df["group_code"].values:
        eht_df = df[df["group_code"] == "EHT_ONLY"]
        lines += [
            f"**EHT_ONLY 组 n = {len(eht_df)}**",
            "",
            "### 9.1 关注字段描述统计",
            "",
        ]
        eht_focus = [f for f in _EHT_FOCUS_FIELDS if f in eht_df.columns]
        if eht_focus:
            lines += ["| 字段 | 非缺失数 | 均值 | 中位数 | P25 | P75 |", "|---|---|---|---|---|---|"]
            for fld in eht_focus:
                col_num = pd.to_numeric(eht_df[fld], errors="coerce")
                n_valid = col_num.notna().sum()
                if n_valid > 0:
                    mean_v = col_num.mean()
                    med_v = col_num.median()
                    p25 = col_num.quantile(0.25)
                    p75 = col_num.quantile(0.75)
                    lines.append(
                        f"| {fld} | {n_valid} | {mean_v:.2f} | {med_v:.2f} | {p25:.2f} | {p75:.2f} |"
                    )
                else:
                    lines.append(f"| {fld} | 0 | — | — | — | — |")
            lines.append("")

        # EHT 特有字段
        lines += ["### 9.2 运动高血压相关标志", ""]
        for flag_col in ["exercise_hypertension", "bp_response_abnormal", "arrhythmia_flag"]:
            if flag_col in eht_df.columns:
                n_pos = (
                    pd.to_numeric(eht_df[flag_col], errors="coerce")
                    .fillna(0)
                    .astype(bool)
                    .sum()
                )
                pct = n_pos / len(eht_df) * 100
                lines.append(f"- **{flag_col}** 阳性: {n_pos} / {len(eht_df)}（{pct:.1f}%）")
        lines.append("")

        # EHT 与 CTRL 对比（若 CTRL 存在）
        if "CTRL" in df["group_code"].values:
            ctrl_df = df[df["group_code"] == "CTRL"]
            lines += ["### 9.3 EHT_ONLY vs CTRL 关键指标对比", ""]
            compare_fields = [f for f in ["vo2_peak", "hr_peak", "ve_vco2_slope"] if f in df.columns]
            if compare_fields:
                lines += ["| 字段 | EHT_ONLY 中位数 | CTRL 中位数 |", "|---|---|---|"]
                for fld in compare_fields:
                    eht_med = pd.to_numeric(eht_df[fld], errors="coerce").median()
                    ctrl_med = pd.to_numeric(ctrl_df[fld], errors="coerce").median()
                    lines.append(
                        f"| {fld} | {eht_med:.2f} | {ctrl_med:.2f} |"
                        if pd.notna(eht_med) and pd.notna(ctrl_med)
                        else f"| {fld} | — | — |"
                    )
                lines.append("")

        if "EHT_ONLY" in group_summary:
            eht_gs = group_summary["EHT_ONLY"]
            lines += [
                "### 9.4 EHT_ONLY QC 摘要",
                "",
                f"- 总行数: {eht_gs.get('n', 0)}",
                f"- 拒绝行数: {eht_gs.get('n_rejected', 0)}",
                f"- 范围越界: {eht_gs.get('n_range_violation', 0)}",
                f"- 逻辑违规: {eht_gs.get('n_logic_violation', 0)}",
                f"- 异常值: {eht_gs.get('n_outlier', 0)}",
                f"- 努力度充分: {eht_gs.get('n_effort_adequate', 0)}",
                "",
            ]
    else:
        lines += ["数据中未找到 EHT_ONLY 组（group_code='EHT_ONLY'）。", ""]

    # ------------------------------------------------------------------ #
    # 尾注
    # ------------------------------------------------------------------ #
    lines += [
        "---",
        "",
        "*本报告由 cpet_stage1 QC 管线自动生成。详细 flags 见 `data/curated/qc_flags.parquet`。*",
        "",
    ]

    report_text = "\n".join(lines)
    output_path.write_text(report_text, encoding="utf-8")
    logger.info("QC 报告已写出: %s", output_path)
    return report_text


def apply_qc_flags(
    df: pd.DataFrame,
    qc_result: QCResult,
    curated_path: str | Path | None = None,
    flags_path: str | Path | None = None,
    engine: QCEngine | None = None,
) -> pd.DataFrame:
    """
    根据 QC flags 生成 curated DataFrame。

    策略：
    - 若 engine 不为 None 且 clip_to_schema_range.enabled=true，先执行 range clip
    - 剔除 rejected_indices（关键字段缺失 >50%）
    - 剔除 duplicate_flags=True 的行（保留策略按 qc_rules 配置）
    - 保留其他行（范围越界 / 逻辑违规 仅标记，不剔除）
    - 新增 qc_flags 列（comma-separated 描述）

    参数：
        df:            原始 staging DataFrame
        qc_result:     QCEngine.run() 的返回值
        curated_path:  输出 curated parquet（None 则不写）
        flags_path:    输出 qc_flags parquet（None 则不写）
        engine:        QCEngine 实例（可选）；传入时执行 clip_to_schema_range

    返回：
        curated DataFrame（已剔除 rejected 行，已 clip 极端值，含 qc_flags 列）
    """
    # 0. Schema range clip（超出物理合理范围 → NaN）
    if engine is not None:
        df, clip_counts = engine.clip_to_schema_range(df)
        if clip_counts:
            logger.info("clip_to_schema_range: %s", clip_counts)
    else:
        df = df.copy()
    # 合并所有 flags 到一个大 DataFrame
    all_flag_dfs = []
    if not qc_result.completeness_flags.empty:
        all_flag_dfs.append(qc_result.completeness_flags)
    if not qc_result.range_flags.empty:
        all_flag_dfs.append(qc_result.range_flags)
    if not qc_result.logic_flags.empty:
        all_flag_dfs.append(qc_result.logic_flags)
    if not qc_result.outlier_flags.empty:
        all_flag_dfs.append(qc_result.outlier_flags)

    # 构建 flags DataFrame（行对齐到 df.index）
    if all_flag_dfs:
        combined_flags = pd.concat(all_flag_dfs, axis=1).reindex(df.index).fillna(False)
    else:
        combined_flags = pd.DataFrame(index=df.index)

    # 重复标志
    if not qc_result.duplicate_flags.empty:
        combined_flags["dup_flag"] = qc_result.duplicate_flags.reindex(df.index).fillna(False)

    # 努力度
    if not qc_result.effort_adequate.empty:
        combined_flags["effort_adequate"] = qc_result.effort_adequate.reindex(df.index).fillna(False)

    # 每行汇总 flag 字符串
    problem_flags = [c for c in combined_flags.columns if c != "effort_adequate"]
    def _make_flag_str(row: pd.Series) -> str:
        active = [col for col in problem_flags if row.get(col, False)]
        return ",".join(active) if active else "ok"

    combined_flags["qc_flags"] = combined_flags.apply(_make_flag_str, axis=1)
    combined_flags["qc_passed"] = combined_flags["qc_flags"] == "ok"

    # 写出 flags parquet
    if flags_path is not None:
        flags_path = Path(flags_path)
        flags_path.parent.mkdir(parents=True, exist_ok=True)
        combined_flags.to_parquet(flags_path, index=True)
        logger.info("QC flags parquet 已写出: %s", flags_path)

    # 确定要剔除的行
    rows_to_drop = set(qc_result.rejected_indices.tolist())
    if "dup_flag" in combined_flags.columns:
        dup_to_drop = combined_flags.index[combined_flags["dup_flag"]].tolist()
        rows_to_drop.update(dup_to_drop)

    curated = df.drop(index=list(rows_to_drop), errors="ignore").copy()
    # 将 flags 列附加到 curated
    curated["qc_flags"] = combined_flags.loc[curated.index, "qc_flags"]
    curated["qc_passed"] = combined_flags.loc[curated.index, "qc_passed"]
    if "effort_adequate" in combined_flags.columns:
        curated["effort_adequate"] = combined_flags.loc[curated.index, "effort_adequate"]

    logger.info(
        "curated 生成: %d → %d 行（剔除 %d 行）",
        len(df),
        len(curated),
        len(df) - len(curated),
    )

    # 写出 curated parquet
    if curated_path is not None:
        curated_path = Path(curated_path)
        curated_path.parent.mkdir(parents=True, exist_ok=True)
        curated.to_parquet(curated_path, index=False)
        logger.info("curated parquet 已写出: %s", curated_path)

    return curated
