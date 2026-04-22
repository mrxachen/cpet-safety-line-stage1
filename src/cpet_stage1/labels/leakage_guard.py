"""
leakage_guard.py — Anti-label-leakage rules for P0/P1/outcome feature sets.

PROBLEM:
  Several CPET variables directly encode the label (e.g., arrhythmia_flag is part
  of the P0 event definition). Including these as model features causes data leakage,
  leading to inflated performance metrics that won't generalize.

SOLUTION:
  This module defines and enforces an exclusion list. It must be applied BEFORE
  any feature matrix is passed to a model.

TASKS:
  p0     — 运动前先验风险模型（排除所有测试后字段）
  p1     — 运动后后验分层模型（排除 P1 规则标签的直接定义变量）
  outcome — 结局锚定模型（Phase G Method 1）：直接预测 test_result，
            vo2_peak_pct_pred / ve_vco2_slope / eih_status 不参与 test_result 的
            确定性定义，因此不需要排除。

Usage:
    from cpet_stage1.labels.leakage_guard import LeakageGuard

    guard = LeakageGuard.from_config("configs/data/label_rules_v1.yaml")
    X_clean = guard.filter(X_df, task="p0")
    guard.assert_no_leakage(X_clean, task="p0")

    # outcome 任务：无需过滤 CPET 指标
    guard.assert_no_leakage(X_outcome_df, task="outcome")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

logger = logging.getLogger(__name__)

# Hard-coded exclusion lists (override with config if needed)
_P0_LEAKAGE_FIELDS: frozenset[str] = frozenset(
    [
        "arrhythmia_flag",
        "test_terminated_early",
        "termination_reason",
        "st_depression_mm",
        # Borderline — included in comment to trigger review:
        # "bp_peak_sys",  # can be feature if used as continuous predictor, not threshold
    ]
)

_P1_LEAKAGE_FIELDS: frozenset[str] = frozenset(
    [
        # P1 zone rules directly use these to define zones:
        "vo2_peak_pct_pred",  # used in zone boundaries — include only as continuous, not threshold
        # The following encode class membership directly:
        "p0_event",  # if P0 label is generated first, must not leak into P1 features
        # 直接定义 P1 Red 区边界的字段——eih_status=True 100% 映射到 Red，必须排除
        "eih_status",        # P1 Red 直接触发器（label_rules_v2.yaml），100% 信息泄漏
        # ve_vco2_slope 直接用于 P1 Yellow(≥30)/Red(≥36) 边界阈值，排除以防泄漏
        "ve_vco2_slope",     # P1 Yellow/Red 边界阈值字段
    ]
)


@dataclass
class LeakageGuard:
    """Manages and enforces feature exclusion rules to prevent label leakage."""

    p0_exclusions: frozenset[str] = field(default_factory=lambda: _P0_LEAKAGE_FIELDS)
    p1_exclusions: frozenset[str] = field(default_factory=lambda: _P1_LEAKAGE_FIELDS)

    @classmethod
    def from_config(cls, config_path: str | Path) -> "LeakageGuard":
        """Load exclusion rules from label_rules YAML config."""
        import yaml

        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        p0_cfg = cfg.get("p0", {}).get("leakage_guard", {})
        p0_exclusions = frozenset(p0_cfg.get("exclude_from_features", [])) | _P0_LEAKAGE_FIELDS

        return cls(p0_exclusions=p0_exclusions, p1_exclusions=_P1_LEAKAGE_FIELDS)

    def get_exclusions(self, task: Literal["p0", "p1", "outcome"]) -> frozenset[str]:
        """
        获取指定任务的排除字段集合。

        task="outcome" 路径（Phase G Method 1）：
          直接预测 test_result，不排除任何 CPET 指标。
          vo2_peak_pct_pred / ve_vco2_slope / eih_status 不参与 test_result 的确定性定义，
          使用它们预测 test_result 正是临床医生的日常工作，不构成数据泄漏。
        """
        if task == "p0":
            return self.p0_exclusions
        elif task == "p1":
            return self.p1_exclusions
        elif task == "outcome":
            # outcome 任务：test_result 不由任何单一 CPET 变量确定性定义，无需排除
            return frozenset()
        raise ValueError(f"Unknown task: {task!r}. Expected 'p0', 'p1', or 'outcome'.")

    def filter(self, X: pd.DataFrame, task: Literal["p0", "p1", "outcome"]) -> pd.DataFrame:
        """Remove leakage columns from feature DataFrame."""
        exclusions = self.get_exclusions(task)
        cols_to_drop = [c for c in X.columns if c in exclusions]
        if cols_to_drop:
            logger.warning(
                "LeakageGuard [%s]: dropping %d leakage column(s): %s",
                task,
                len(cols_to_drop),
                cols_to_drop,
            )
        elif task == "outcome":
            logger.info(
                "LeakageGuard [outcome]: no exclusions applied "
                "(test_result not deterministically defined by any CPET variable)."
            )
        return X.drop(columns=cols_to_drop, errors="ignore")

    def assert_no_leakage(self, X: pd.DataFrame, task: Literal["p0", "p1", "outcome"]) -> None:
        """Raise AssertionError if any leakage columns remain in X."""
        exclusions = self.get_exclusions(task)
        leaks = [c for c in X.columns if c in exclusions]
        if leaks:
            raise AssertionError(
                f"LeakageGuard [{task}]: found {len(leaks)} leakage column(s) "
                f"in feature matrix: {leaks}"
            )
        logger.info("LeakageGuard [%s]: no leakage detected.", task)

    def report(self) -> dict[str, list[str]]:
        """Return a dict summarizing exclusion rules."""
        return {
            "p0_exclusions": sorted(self.p0_exclusions),
            "p1_exclusions": sorted(self.p1_exclusions),
            "outcome_exclusions": [],  # outcome 任务无排除字段
        }
