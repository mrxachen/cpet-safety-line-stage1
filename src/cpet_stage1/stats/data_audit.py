"""
data_audit.py — 全字段深度数据审计

对 staging parquet 的全部列输出：
- 非缺失率（总体 + 按 4 组分层）
- 类型：连续 / 二值 / 分类
- 对连续列：均值、中位数、IQR
- 对二值/分类列：阳性率 / 前 10 高频值
- 唯一值数量

输出：reports/data_audit_full.md
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 4 组代码
GROUP_ORDER = ["CTRL", "HTN_HISTORY_NO_EHT", "HTN_HISTORY_WITH_EHT", "EHT_ONLY"]
GROUP_LABELS = {
    "CTRL": "健康对照",
    "HTN_HISTORY_NO_EHT": "HTN-无运动HTN",
    "HTN_HISTORY_WITH_EHT": "HTN-有运动HTN",
    "EHT_ONLY": "仅运动HTN",
}

# 关键字段类别（用于分节展示）
FIELD_CATEGORIES = {
    "基础人口学": ["subject_id", "sex", "age", "height_cm", "weight_kg"],
    "社会经济/生活方式": [
        "education_level", "employed", "mental_stress", "physical_labor",
        "household_activity", "exercise_habit", "exercise_duration_min",
        "exercise_type", "exercise_frequency_per_week", "exercise_intensity",
    ],
    "吸烟": [
        "smoking_status", "smoking_years", "smoking_daily_amount",
        "quit_smoking_years", "quit_smoking_months",
    ],
    "合并症/病史": [
        "diagnosis_notes", "cad_history", "tumor_history", "musculoskeletal_disease",
        "htn_history", "htn_years", "hyperlipidemia", "hyperlipidemia_years",
        "diabetes", "diabetes_years", "family_hx_cad",
    ],
    "药物（30列）": [c for c in [
        "med_ccb", "med_acei", "med_arb", "med_betablocker", "med_statin",
        "med_fibrate", "med_digoxin", "med_diuretic", "med_nitrate",
        "med_niacin", "med_aspirin", "med_clopidogrel", "med_ticagrelor",
        "med_other_antiplatelet", "med_warfarin", "med_dabigatran",
        "med_other_anticoagulant", "med_metformin", "med_sulfonylurea",
        "med_alpha_glucosidase_inhib", "med_glinide", "med_tzd",
        "med_insulin", "med_other_antidiabetic", "med_trimetazidine",
        "med_nicorandil", "med_ppi", "med_gastric_protectant",
        "med_liver_protect", "med_other",
    ]],
    "运动方案/协议": [
        "protocol_bruce", "protocol_modified_bruce", "protocol_cycle",
        "protocol_ramp_watts", "test_duration_min", "test_duration_sec",
    ],
    "肺功能": ["pulmonary_ventilation", "small_airway_function"],
    "CPET核心指标": [
        "vt1_vo2", "vt1_vo2_abs", "ve_peak", "vo2_peak", "vo2_peak_abs",
        "mets_peak", "hr_peak", "o2_pulse_peak", "bp_peak_sys", "bp_peak_dia",
        "vo2_peak_pct_pred", "exercise_capacity", "oues", "ve_vco2_slope",
        "hr_recovery",
    ],
    "事件标注": [
        "test_result", "o2_pulse_trajectory", "test_date",
    ],
    "元数据": ["group_code"],
}


def _infer_col_type(series: pd.Series) -> str:
    """推断列类型：binary / categorical / continuous / datetime / text。"""
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    n_unique = series.dropna().nunique()
    if n_unique == 0:
        return "empty"
    if n_unique <= 2:
        return "binary"
    if pd.api.types.is_numeric_dtype(series):
        if n_unique <= 10:
            return "categorical_num"
        return "continuous"
    # 字符串类型
    if n_unique <= 20:
        return "categorical"
    return "text"


def _completeness(series: pd.Series, n: int) -> str:
    non_null = series.notna().sum()
    pct = non_null / n * 100
    return f"{non_null}/{n} ({pct:.1f}%)"


def _group_completeness(df: pd.DataFrame, col: str) -> dict[str, str]:
    result = {}
    for g in GROUP_ORDER:
        sub = df[df["group_code"] == g][col] if "group_code" in df.columns else pd.Series(dtype=float)
        n_g = len(sub)
        if n_g == 0:
            result[g] = "N/A"
        else:
            non_null = sub.notna().sum()
            result[g] = f"{non_null}/{n_g} ({non_null/n_g*100:.1f}%)"
    return result


def _describe_column(df: pd.DataFrame, col: str) -> dict[str, Any]:
    """对单列输出完整描述统计。"""
    series = df[col]
    n = len(series)
    col_type = _infer_col_type(series)
    n_unique = series.dropna().nunique()

    info: dict[str, Any] = {
        "column": col,
        "type": col_type,
        "n_unique": n_unique,
        "completeness": _completeness(series, n),
        "group_completeness": _group_completeness(df, col),
    }

    if col_type == "continuous":
        vals = series.dropna()
        info["mean"] = f"{vals.mean():.2f}"
        info["median"] = f"{vals.median():.2f}"
        q1, q3 = vals.quantile(0.25), vals.quantile(0.75)
        info["IQR"] = f"[{q1:.2f}, {q3:.2f}]"
        info["min"] = f"{vals.min():.2f}"
        info["max"] = f"{vals.max():.2f}"

    elif col_type == "binary":
        vals = series.dropna()
        # 尝试将值转为数值
        try:
            pos_rate = vals.astype(float).mean() * 100
            info["positive_rate"] = f"{pos_rate:.1f}%"
        except (ValueError, TypeError):
            # 如果无法转为数值，统计最高频值
            vc = vals.value_counts()
            info["value_counts"] = dict(vc.head(5))

    elif col_type in ("categorical", "categorical_num"):
        vc = series.value_counts(dropna=False).head(10)
        info["value_counts"] = {str(k): int(v) for k, v in vc.items()}

    elif col_type == "text":
        vc = series.value_counts(dropna=False).head(5)
        info["top5"] = {str(k): int(v) for k, v in vc.items()}

    elif col_type == "datetime":
        non_null = series.dropna()
        if len(non_null) > 0:
            info["date_range"] = f"{non_null.min()} ~ {non_null.max()}"

    # 额外：全为0的列标记
    if col_type in ("binary", "continuous", "categorical_num"):
        try:
            vals_num = series.dropna().astype(float)
            if vals_num.sum() == 0 and len(vals_num) > 0:
                info["all_zero"] = True
        except (ValueError, TypeError):
            pass

    return info


def _format_group_row(gc: dict[str, str]) -> str:
    parts = []
    for g in GROUP_ORDER:
        label = GROUP_LABELS.get(g, g)
        parts.append(f"{label}: {gc.get(g, 'N/A')}")
    return " | ".join(parts)


def _info_to_md_rows(info: dict[str, Any]) -> list[str]:
    """将单列信息转为 Markdown 行。"""
    lines = []
    col = info["column"]
    col_type = info["type"]
    all_zero = info.get("all_zero", False)
    flag = " ⚠️**全零**" if all_zero else ""

    # 列标题行
    lines.append(f"#### `{col}` — {col_type}{flag}")
    lines.append(f"- **完整度（总体）**：{info['completeness']}")
    gc = info.get("group_completeness", {})
    if gc:
        lines.append(f"- **分组完整度**：{_format_group_row(gc)}")
    lines.append(f"- **唯一值数**：{info['n_unique']}")

    if col_type == "continuous":
        lines.append(f"- **均值 / 中位数 / IQR**：{info['mean']} / {info['median']} / {info['IQR']}")
        lines.append(f"- **范围**：[{info['min']}, {info['max']}]")
    elif col_type == "binary":
        if "positive_rate" in info:
            lines.append(f"- **阳性率**：{info['positive_rate']}")
        if "value_counts" in info:
            lines.append(f"- **值分布**：{info['value_counts']}")
    elif col_type in ("categorical", "categorical_num"):
        vc = info.get("value_counts", {})
        vc_str = ", ".join(f"`{k}`: {v}" for k, v in list(vc.items())[:10])
        lines.append(f"- **值分布（前10）**：{vc_str}")
    elif col_type == "text":
        top5 = info.get("top5", {})
        t_str = ", ".join(f"`{k}`: {v}" for k, v in list(top5.items())[:5])
        lines.append(f"- **高频值（前5）**：{t_str}")
    elif col_type == "datetime":
        if "date_range" in info:
            lines.append(f"- **日期范围**：{info['date_range']}")

    lines.append("")
    return lines


def run_data_audit(
    staging_path: str | Path,
    output_path: str | Path | None = None,
) -> str:
    """
    主入口：读取 staging parquet，对所有列输出完整审计报告。

    Parameters
    ----------
    staging_path : staging parquet 路径
    output_path : 输出 Markdown 路径（None 则仅返回字符串）

    Returns
    -------
    报告字符串
    """
    staging_path = Path(staging_path)
    df = pd.read_parquet(staging_path)
    n_total = len(df)
    all_cols = list(df.columns)

    logger.info("数据审计开始：%s，共 %d 行 %d 列", staging_path.name, n_total, len(all_cols))

    # ——— 全局概览 ———
    lines: list[str] = []
    lines.append("# Phase F — 深度数据审计报告")
    lines.append("")
    lines.append(f"**数据源**：`{staging_path.name}`")
    lines.append(f"**总样本量**：{n_total}")
    lines.append(f"**总列数**：{len(all_cols)}")
    lines.append("")

    # 分组样本量
    if "group_code" in df.columns:
        lines.append("## 分组样本量")
        lines.append("")
        lines.append("| 组别代码 | 中文名称 | N |")
        lines.append("|---|---|---|")
        for g in GROUP_ORDER:
            n_g = (df["group_code"] == g).sum()
            lines.append(f"| {g} | {GROUP_LABELS.get(g, g)} | {n_g} |")
        lines.append("")

    # ——— 按类别展示各字段 ———
    # 收集已展示的列
    covered: set[str] = set()

    for cat_name, cat_cols in FIELD_CATEGORIES.items():
        lines.append(f"## {cat_name}")
        lines.append("")
        for col in cat_cols:
            if col not in df.columns:
                lines.append(f"#### `{col}` — ❌ 列不存在")
                lines.append("")
                continue
            covered.add(col)
            info = _describe_column(df, col)
            lines.extend(_info_to_md_rows(info))

    # ——— 未归类列 ———
    uncovered = [c for c in all_cols if c not in covered]
    if uncovered:
        lines.append("## 其他列（未分类）")
        lines.append("")
        for col in uncovered:
            info = _describe_column(df, col)
            lines.extend(_info_to_md_rows(info))

    # ——— 汇总矩阵 ———
    lines.append("---")
    lines.append("")
    lines.append("## 汇总矩阵（所有列）")
    lines.append("")
    lines.append("| 列名 | 类型 | 完整度 | 全零 | 唯一值数 | 统计摘要 |")
    lines.append("|---|---|---|---|---|---|")

    for col in all_cols:
        info = _describe_column(df, col)
        ctype = info["type"]
        comp = info["completeness"]
        all_zero = "⚠" if info.get("all_zero") else ""
        n_uniq = info["n_unique"]

        if ctype == "continuous":
            summary = f"中位数={info['median']}, IQR={info['IQR']}"
        elif ctype == "binary" and "positive_rate" in info:
            summary = f"阳性率={info['positive_rate']}"
        elif ctype in ("categorical", "categorical_num"):
            vc = info.get("value_counts", {})
            top3 = list(vc.items())[:3]
            summary = ", ".join(f"{k}:{v}" for k, v in top3)
        else:
            summary = ""

        lines.append(f"| `{col}` | {ctype} | {comp} | {all_zero} | {n_uniq} | {summary} |")

    lines.append("")

    # ——— 关键发现摘要 ———
    lines.append("---")
    lines.append("")
    lines.append("## 关键发现摘要")
    lines.append("")

    # 全零列
    zero_cols = []
    low_completeness_cols = []
    high_completeness_cols = []

    for col in all_cols:
        series = df[col]
        non_null = series.notna().sum()
        pct = non_null / n_total * 100
        ctype = _infer_col_type(series)
        if ctype in ("binary", "continuous", "categorical_num"):
            try:
                vals = series.dropna().astype(float)
                if vals.sum() == 0 and len(vals) > 0:
                    zero_cols.append(col)
            except (ValueError, TypeError):
                pass
        if pct < 20:
            low_completeness_cols.append((col, pct))
        elif pct >= 95:
            high_completeness_cols.append((col, pct))

    lines.append(f"### 全零列（{len(zero_cols)} 个）")
    lines.append("")
    if zero_cols:
        lines.append("这些列数据全部为0，**不可用于建模**：")
        lines.append("")
        for c in zero_cols:
            lines.append(f"- `{c}`")
    else:
        lines.append("无。")
    lines.append("")

    lines.append(f"### 低完整度列（<20%，{len(low_completeness_cols)} 个）")
    lines.append("")
    if low_completeness_cols:
        for c, p in sorted(low_completeness_cols, key=lambda x: x[1]):
            lines.append(f"- `{c}`：{p:.1f}%")
    else:
        lines.append("无。")
    lines.append("")

    lines.append(f"### 高完整度列（≥95%，{len(high_completeness_cols)} 个）")
    lines.append("")
    if high_completeness_cols:
        for c, p in sorted(high_completeness_cols, key=lambda x: -x[1])[:30]:
            lines.append(f"- `{c}`：{p:.1f}%")
    lines.append("")

    # ——— Phase F 建模可用性评估 ———
    lines.append("---")
    lines.append("")
    lines.append("## Phase F 建模可用性评估")
    lines.append("")
    lines.append("基于完整度和零值检查，为 Phase F 各步骤提供数据基础评估：")
    lines.append("")

    # 关键字段评估
    key_fields = {
        "Step 1 参考方程（扩展变量）": {
            "weight_kg": "BMI派生基础",
            "height_cm": "BMI派生基础",
            "age": "核心预测变量",
            "sex": "核心预测变量",
            "vo2_peak": "目标变量",
            "hr_peak": "目标变量",
            "ve_vco2_slope": "目标变量",
            "o2_pulse_peak": "目标变量",
        },
        "Step 2 R轴（储备）": {
            "vo2_peak_pct_pred": "核心",
            "o2_pulse_peak": "辅助",
            "mets_peak": "辅助",
            "exercise_capacity": "辅助",
        },
        "Step 2 T轴（阈值）": {
            "vt1_vo2": "VT1关键",
            "ve_vco2_slope": "通气效率",
            "exercise_frequency_per_week": "运动习惯调节",
            "exercise_habit": "运动习惯调节",
        },
        "Step 2 I轴（不稳定）": {
            "bp_peak_sys": "核心",
            "bp_peak_dia": "新增",
            "o2_pulse_trajectory": "缺血标志",
            "test_result": "结局锚定",
        },
        "Step 2c 个性化因子": {
            "exercise_habit": "运动习惯分层",
            "smoking_status": "肺功能调节",
            "diabetes": "代谢负担",
            "med_betablocker": "HR影响",
            "htn_history": "HTN分层",
        },
    }

    lines.append("| 步骤 | 字段 | 作用 | 完整度 | 可用? |")
    lines.append("|---|---|---|---|---|")

    for step_name, fields in key_fields.items():
        first = True
        for col, role in fields.items():
            if col in df.columns:
                series = df[col]
                non_null = series.notna().sum()
                pct = non_null / n_total * 100
                ctype = _infer_col_type(series)
                all_zero_flag = False
                if ctype in ("binary", "continuous", "categorical_num"):
                    try:
                        vals = series.dropna().astype(float)
                        if vals.sum() == 0 and len(vals) > 0:
                            all_zero_flag = True
                    except (ValueError, TypeError):
                        pass
                avail = "❌ 全零" if all_zero_flag else ("✅" if pct >= 50 else ("⚠ 低完整度" if pct >= 20 else "❌ 严重缺失"))
                comp_str = f"{pct:.1f}%"
            else:
                avail = "❌ 不存在"
                comp_str = "—"

            step_cell = step_name if first else ""
            first = False
            lines.append(f"| {step_cell} | `{col}` | {role} | {comp_str} | {avail} |")

    lines.append("")

    report = "\n".join(lines)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        logger.info("数据审计报告已写入：%s", output_path)

    return report
