"""
leakage_guard.py — Anti-label-leakage rules for P0/P1 feature sets.

PROBLEM:
  Several CPET variables directly encode the label (e.g., arrhythmia_flag is part
  of the P0 event definition). Including these as model features causes data leakage,
  leading to inflated performance metrics that won't generalize.

SOLUTION:
  This module defines and enforces an exclusion list. It must be applied BEFORE
  any feature matrix is passed to a model.

Usage:
    from cpet_stage1.labels.leakage_guard import LeakageGuard

    guard = LeakageGuard.from_config("configs/data/label_rules_v1.yaml")
    X_clean = guard.filter(X_df, task="p0")
    guard.assert_no_leakage(X_clean, task="p0")
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

    def get_exclusions(self, task: Literal["p0", "p1"]) -> frozenset[str]:
        if task == "p0":
            return self.p0_exclusions
        elif task == "p1":
            return self.p1_exclusions
        raise ValueError(f"Unknown task: {task!r}. Expected 'p0' or 'p1'.")

    def filter(self, X: pd.DataFrame, task: Literal["p0", "p1"]) -> pd.DataFrame:
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
        return X.drop(columns=cols_to_drop, errors="ignore")

    def assert_no_leakage(self, X: pd.DataFrame, task: Literal["p0", "p1"]) -> None:
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
        }
