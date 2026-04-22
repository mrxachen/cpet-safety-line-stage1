"""
rules.py — QC 引擎：基于 qc_rules YAML 执行数据质量检查。

执行五类检查：
1. 完整性（缺失率）
2. 范围越界
3. 逻辑一致性（VT1 < peak 等）
4. 重复记录
5. IQR 异常值标记

使用示例：
    from cpet_stage1.qc.rules import QCEngine
    engine = QCEngine(rules_path="configs/data/qc_rules_v1.yaml",
                      schema_path="configs/data/schema_v2.yaml")
    result = engine.run(df)
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


def _load_yaml(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class QCResult:
    """QC 检查结果容器。"""

    # 每行的 QC 标记（True = 有问题）
    completeness_flags: pd.DataFrame = field(default_factory=pd.DataFrame)
    range_flags: pd.DataFrame = field(default_factory=pd.DataFrame)
    logic_flags: pd.DataFrame = field(default_factory=pd.DataFrame)
    duplicate_flags: pd.Series = field(default_factory=pd.Series)
    outlier_flags: pd.DataFrame = field(default_factory=pd.DataFrame)

    # 汇总统计
    summary: dict[str, Any] = field(default_factory=dict)

    # 各组分层统计（按 group_code）
    group_summary: dict[str, dict] = field(default_factory=dict)

    # 待剔除行索引（reject_missing_threshold 超标）
    rejected_indices: pd.Index = field(default_factory=lambda: pd.Index([]))

    # 努力度标志（新增列）
    effort_adequate: pd.Series = field(default_factory=pd.Series)


class QCEngine:
    """基于 qc_rules YAML 执行数据质量检查。"""

    def __init__(self, rules_path: str | Path, schema_path: str | Path) -> None:
        self.rules_path = Path(rules_path)
        self.schema_path = Path(schema_path)

        self._rules = _load_yaml(self.rules_path)
        # schema 此处仅用于字段元信息
        self._schema_raw = _load_yaml(self.schema_path)

        # 合并 v1 + extended range checks
        base_ranges = self._rules.get("range_checks", {})
        ext_ranges = self._rules.get("range_checks_extended", {})
        self._all_range_checks = {**base_ranges, **ext_ranges}

        logger.info(
            "QCEngine 初始化 — %d 个范围检查字段，%d 个逻辑检查",
            len(self._all_range_checks),
            len(self._rules.get("logic_checks", {})),
        )

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def run(self, df: pd.DataFrame) -> QCResult:
        """
        执行全部 5 类 QC 检查，返回 QCResult。

        参数：
            df: staging DataFrame（已完成列名映射和类型转换）
        """
        logger.info("开始 QC 检查: %d 行 × %d 列", len(df), len(df.columns))
        result = QCResult()

        # 1. 完整性
        result.completeness_flags, result.rejected_indices = self.check_completeness(df)

        # 2. 范围
        result.range_flags = self.check_range(df)

        # 3. 逻辑
        result.logic_flags = self.check_logic(df)

        # 4. 重复
        result.duplicate_flags = self.check_duplicates(df)

        # 5. 异常值
        result.outlier_flags = self.check_outliers(df)

        # 6. 努力度标志
        result.effort_adequate = self._compute_effort_flag(df)

        # 7. 汇总
        result.summary = self._compute_summary(df, result)
        result.group_summary = self._compute_group_summary(df, result)

        logger.info(
            "QC 完成 — rejected=%d, range_violations=%d, logic_warnings=%d, duplicates=%d",
            len(result.rejected_indices),
            int(result.range_flags.any(axis=1).sum()),
            int(result.logic_flags.any(axis=1).sum()) if not result.logic_flags.empty else 0,
            int(result.duplicate_flags.sum()) if not result.duplicate_flags.empty else 0,
        )
        return result

    # ------------------------------------------------------------------
    # 1. 完整性检查
    # ------------------------------------------------------------------

    def check_completeness(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.Index]:
        """
        检查每行关键字段的缺失情况。

        返回：
            (flags_df, rejected_index)
            flags_df: 布尔 DataFrame，列 = 关键字段，True = 该字段缺失
            rejected_index: 满足 reject_missing_threshold 的行索引
        """
        cfg = self._rules.get("completeness", {})
        required = cfg.get("required_fields", [])
        warn_thresh = cfg.get("warn_missing_threshold", 0.10)
        reject_thresh = cfg.get("reject_missing_threshold", 0.50)

        # 只检查实际存在于 DataFrame 的必填字段
        existing_required = [f for f in required if f in df.columns]
        missing_required = [f for f in required if f not in df.columns]
        if missing_required:
            logger.warning("必填字段在数据中不存在: %s", missing_required)

        flags = pd.DataFrame(index=df.index)
        for col in existing_required:
            flags[f"missing_{col}"] = df[col].isna()

        # 字段级缺失率（全列）
        for col in df.columns:
            miss_rate = df[col].isna().mean()
            if miss_rate > warn_thresh:
                logger.warning(
                    "字段 %r 缺失率 %.1f%% > 警告阈值 %.1f%%",
                    col, miss_rate * 100, warn_thresh * 100,
                )

        # 行级：关键字段缺失比例 > reject_thresh → 拒绝
        if existing_required:
            row_missing_rate = flags.mean(axis=1)
            rejected = df.index[row_missing_rate > reject_thresh]
        else:
            rejected = pd.Index([])

        if len(rejected) > 0:
            logger.warning("因关键字段缺失超过 %.0f%% 而拒绝 %d 行", reject_thresh * 100, len(rejected))

        return flags, rejected

    # ------------------------------------------------------------------
    # 2. 范围检查
    # ------------------------------------------------------------------

    def check_range(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        检查数值字段是否在合理范围内。

        返回：
            布尔 DataFrame，列 = "range_{field}"，True = 越界
        """
        flags = pd.DataFrame(index=df.index)
        for field_name, limits in self._all_range_checks.items():
            if field_name not in df.columns:
                continue
            col = pd.to_numeric(df[field_name], errors="coerce")
            low = limits.get("min")
            high = limits.get("max")
            out_of_range = pd.Series(False, index=df.index)
            if low is not None:
                out_of_range |= col < low
            if high is not None:
                out_of_range |= col > high
            # NaN 不标记为越界
            out_of_range &= col.notna()
            flags[f"range_{field_name}"] = out_of_range

        n_violations = int(flags.any(axis=1).sum())
        if n_violations:
            logger.info("范围检查: %d 行存在越界值", n_violations)
        return flags

    # ------------------------------------------------------------------
    # 3. 逻辑一致性检查
    # ------------------------------------------------------------------

    def check_logic(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        检查逻辑一致性规则（VT1 < peak 等）。

        返回：
            布尔 DataFrame，列 = 规则名，True = 违反规则
        """
        all_logic = {
            **self._rules.get("logic_checks", {}),
            **self._rules.get("logic_checks_extended", {}),
        }
        flags = pd.DataFrame(index=df.index)

        for rule_name, rule_cfg in all_logic.items():
            if not isinstance(rule_cfg, dict):
                continue
            condition = rule_cfg.get("condition", "")
            action = rule_cfg.get("action", "warn")
            if action == "flag_adequate_effort":
                continue  # 单独处理

            flag_col = f"logic_{rule_name}"
            violation = self._eval_condition_violation(df, condition)
            flags[flag_col] = violation

            n_viol = int(violation.sum())
            if n_viol > 0:
                logger.info("逻辑规则 %r: %d 行违反 (%s)", rule_name, n_viol, condition)

        return flags

    def _eval_condition_violation(self, df: pd.DataFrame, condition: str) -> pd.Series:
        """
        对 condition 字符串求值，返回"违反条件"（即 NOT condition）的布尔 Series。

        注意：pandas eval 对含 NaN 字段的比较返回 False（非 NaN），
        因此需要额外检测涉及字段的 NaN 行，将其排除在违规报告之外。
        """
        violation = pd.Series(False, index=df.index)
        try:
            # 处理 "is not null" → 直接跳过（这类规则单独评估）
            if "is not null" in condition:
                return violation

            # 从 condition 中提取字段名（简单的词法分析）
            import re
            tokens = re.findall(r'\b([a-z_][a-z0-9_]*)\b', condition)
            relevant_cols = [t for t in tokens if t in df.columns]

            # 用 pandas eval 求值
            mask_ok = df.eval(condition, engine="python")

            # 只报告"所有相关字段均有值"且条件为 False 的行
            if relevant_cols:
                any_null = pd.concat(
                    [df[c].isna() for c in relevant_cols], axis=1
                ).any(axis=1)
                # 涉及字段存在 NaN 的行 → 视为满足条件（不报告违规）
                violation = ~mask_ok & ~any_null
            else:
                violation = ~mask_ok

        except Exception as exc:
            logger.debug("逻辑规则 condition=%r 求值失败: %s", condition, exc)
        return violation

    # ------------------------------------------------------------------
    # 4. 重复检测
    # ------------------------------------------------------------------

    def check_duplicates(self, df: pd.DataFrame) -> pd.Series:
        """
        检测重复记录。

        返回：
            布尔 Series，True = 该行为重复（按配置策略确定）
        """
        cfg = self._rules.get("duplicates", {})
        key_fields = cfg.get("key_fields", ["subject_id", "test_date"])
        action = cfg.get("action", "keep_latest")

        # 只保留存在的列
        key_cols = [c for c in key_fields if c in df.columns]
        if not key_cols:
            return pd.Series(False, index=df.index)

        # 找出所有重复组
        is_dup_any = df.duplicated(subset=key_cols, keep=False)
        n_dups = int(is_dup_any.sum())
        if n_dups == 0:
            return pd.Series(False, index=df.index)

        logger.warning("发现 %d 行重复记录（key=%s）", n_dups, key_cols)

        if action == "keep_latest":
            # 保留最后一个（keep='last' → 标记除最后一个以外的为重复）
            return df.duplicated(subset=key_cols, keep="last")
        elif action == "keep_first":
            return df.duplicated(subset=key_cols, keep="first")
        else:  # flag_all
            return is_dup_any

    # ------------------------------------------------------------------
    # 5. 异常值检测
    # ------------------------------------------------------------------

    def check_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        IQR 方法检测异常值。

        返回：
            布尔 DataFrame，列 = "outlier_{field}"，True = 异常值
        """
        cfg = self._rules.get("outliers", {})
        k = cfg.get("iqr_multiplier", 3.0)
        fields = cfg.get("fields_to_check", [])
        flags = pd.DataFrame(index=df.index)

        for field_name in fields:
            if field_name not in df.columns:
                continue
            col = pd.to_numeric(df[field_name], errors="coerce")
            q1 = col.quantile(0.25)
            q3 = col.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower = q1 - k * iqr
            upper = q3 + k * iqr
            is_outlier = (col < lower) | (col > upper)
            is_outlier &= col.notna()
            flags[f"outlier_{field_name}"] = is_outlier

            n_out = int(is_outlier.sum())
            if n_out > 0:
                logger.info(
                    "IQR异常值 %r: %d 行（范围 [%.2f, %.2f]）",
                    field_name, n_out, lower, upper,
                )

        return flags

    # ------------------------------------------------------------------
    # 6. Schema Range Clip（超出物理合理范围 → NaN）
    # ------------------------------------------------------------------

    def clip_to_schema_range(self, df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
        """
        将超出 schema range 定义的值替换为 NaN。

        依据 qc_rules_v1.yaml 中 clip_to_schema_range.fields 配置执行。
        超出 [min, max] 范围（如 hr_peak=147148）的值视为录入错误，
        替换为 NaN 而非直接剔除行，以保留其他字段的有效信息。

        参数：
            df: staging/curated DataFrame（in-place 修改副本）

        返回：
            (clipped_df, clip_counts): 修改后的 DataFrame 和各字段 clip 数量
        """
        clip_cfg = self._rules.get("clip_to_schema_range", {})
        if not clip_cfg.get("enabled", False):
            return df.copy(), {}

        field_ranges = clip_cfg.get("fields", {})
        clipped_df = df.copy()
        clip_counts: dict[str, int] = {}

        for field_name, bounds in field_ranges.items():
            if field_name not in clipped_df.columns:
                continue
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                logger.warning("clip_to_schema_range: 字段 %r 的 range 格式错误 %r，跳过", field_name, bounds)
                continue

            low, high = bounds[0], bounds[1]
            col = pd.to_numeric(clipped_df[field_name], errors="coerce")
            # 超出范围（且非 NaN）的行
            out_low = col.notna() & (col < low)
            out_high = col.notna() & (col > high)
            out_mask = out_low | out_high
            n_clipped = int(out_mask.sum())

            if n_clipped > 0:
                clipped_df.loc[out_mask, field_name] = float("nan")
                clip_counts[field_name] = n_clipped
                logger.warning(
                    "clip_to_schema_range: 字段 %r clip %d 行（range [%s, %s]）",
                    field_name, n_clipped, low, high,
                )

        if clip_counts:
            logger.info(
                "clip_to_schema_range 完成: 共 %d 个字段被 clip，涉及 %d 个值",
                len(clip_counts),
                sum(clip_counts.values()),
            )

        return clipped_df, clip_counts

    # ------------------------------------------------------------------
    # 内部：努力度标志
    # ------------------------------------------------------------------

    def _compute_effort_flag(self, df: pd.DataFrame) -> pd.Series:
        """计算努力度充分标志（RER≥1.05 或 HR_peak≥85%pred）。"""
        effort_cfg = self._rules.get("effort", {})
        min_rer = effort_cfg.get("min_rer_for_adequate", 1.05)
        hr_pct = effort_cfg.get("fallback_hr_pct_pred", 0.85)

        adequate = pd.Series(False, index=df.index)
        if "rer_peak" in df.columns:
            rer = pd.to_numeric(df["rer_peak"], errors="coerce")
            adequate |= rer >= min_rer

        if "hr_peak_pct_pred" in df.columns:
            hr_pp = pd.to_numeric(df["hr_peak_pct_pred"], errors="coerce")
            # 假设字段值为百分比（如 88.0 代表 88%）
            adequate |= hr_pp >= (hr_pct * 100)

        n_adequate = int(adequate.sum())
        logger.info("努力度充分: %d / %d 行", n_adequate, len(df))
        return adequate

    # ------------------------------------------------------------------
    # 汇总统计
    # ------------------------------------------------------------------

    def _compute_summary(self, df: pd.DataFrame, result: QCResult) -> dict:
        """生成全局 QC 汇总统计。"""
        n_total = len(df)

        def _safe_any_sum(flags_df: pd.DataFrame) -> int:
            if flags_df.empty:
                return 0
            return int(flags_df.any(axis=1).sum())

        return {
            "n_total": n_total,
            "n_rejected": len(result.rejected_indices),
            "n_range_violation": _safe_any_sum(result.range_flags),
            "n_logic_violation": _safe_any_sum(result.logic_flags),
            "n_duplicate": int(result.duplicate_flags.sum()) if not result.duplicate_flags.empty else 0,
            "n_outlier": _safe_any_sum(result.outlier_flags),
            "n_effort_adequate": int(result.effort_adequate.sum()),
            "pct_effort_adequate": (
                round(result.effort_adequate.mean() * 100, 1)
                if len(df) > 0 else 0.0
            ),
            # 字段级缺失率（全部列）
            "field_missing_rates": {
                col: round(df[col].isna().mean(), 4)
                for col in df.columns
                if df[col].isna().any()
            },
        }

    def _compute_group_summary(self, df: pd.DataFrame, result: QCResult) -> dict:
        """按 group_code 分层统计。"""
        group_summary: dict[str, dict] = {}
        if "group_code" not in df.columns:
            return group_summary

        for group, sub_df in df.groupby("group_code"):
            idx = sub_df.index
            group_summary[str(group)] = {
                "n": len(sub_df),
                "n_rejected": int(idx.isin(result.rejected_indices).sum()),
                "n_range_violation": (
                    int(result.range_flags.loc[idx].any(axis=1).sum())
                    if not result.range_flags.empty else 0
                ),
                "n_logic_violation": (
                    int(result.logic_flags.loc[idx].any(axis=1).sum())
                    if not result.logic_flags.empty else 0
                ),
                "n_outlier": (
                    int(result.outlier_flags.loc[idx].any(axis=1).sum())
                    if not result.outlier_flags.empty else 0
                ),
                "n_effort_adequate": int(result.effort_adequate.loc[idx].sum()),
                "key_field_missing_rates": {
                    col: round(sub_df[col].isna().mean(), 4)
                    for col in ["vo2_peak", "hr_peak", "rer_peak", "vt1_vo2"]
                    if col in sub_df.columns
                },
            }
        return group_summary
