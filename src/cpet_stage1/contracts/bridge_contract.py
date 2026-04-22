"""
bridge_contract.py — 跨阶段桥接合约验证器。

验证 anchor_table 是否包含合约要求的核心字段，并生成 contract_snapshot.json。

合约核心字段（来自 PLANNING.md 第十一节）：
    cpet_session_id, reserve_axis, threshold_axis, instability_axis,
    a_lab_vector, s_lab_score, z_lab_zone
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# 合约必填字段（不可省略）
_CONTRACT_REQUIRED_FIELDS = [
    "cpet_session_id",
    "reserve_axis",
    "threshold_axis",
    "instability_axis",
    "a_lab_vector",
    "s_lab_score",
    "z_lab_zone",
]

# 合约推荐字段（缺失发出警告但不失败）
_CONTRACT_RECOMMENDED_FIELDS = [
    "subject_id",
    "cohort_2x2",
    "p0_event",
    "p1_zone",
    "instability_i1_eih_status",
    "reserve_r1_vo2peak_pct_pred",
]

_VALID_ZONES = {"green", "yellow", "red"}


@dataclass
class BridgeContractResult:
    """桥接合约验证结果。"""

    passed: bool
    contract_version: str = "contract_v1"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    snapshot: dict[str, Any] = field(default_factory=dict)

    def report(self) -> str:
        lines = ["=== Bridge Contract 验证报告 ==="]
        lines.append(f"版本: {self.contract_version}")
        lines.append(f"结果: {'通过 ✅' if self.passed else '失败 ❌'}")
        if self.errors:
            lines.append(f"\n错误 ({len(self.errors)} 项):")
            for e in self.errors:
                lines.append(f"  ✗ {e}")
        if self.warnings:
            lines.append(f"\n警告 ({len(self.warnings)} 项):")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        return "\n".join(lines)

    def save_snapshot(self, path: str | Path) -> None:
        """保存 contract_snapshot.json。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.snapshot, f, ensure_ascii=False, indent=2)
        logger.info("contract_snapshot.json 已保存: %s", path)


class BridgeContractValidator:
    """
    桥接合约验证器。

    使用方法：
        validator = BridgeContractValidator("configs/bridge/contract_rules_v1.yaml")
        result = validator.validate(anchor_df)
        result.save_snapshot("data/contracts/contract_snapshot.json")
    """

    def __init__(self, contract_rules_path: str | Path | None = None) -> None:
        self._rules_path = Path(contract_rules_path) if contract_rules_path else None
        self._rules: dict[str, Any] = {}
        if self._rules_path and self._rules_path.exists():
            with open(self._rules_path, encoding="utf-8") as f:
                self._rules = yaml.safe_load(f) or {}

    def validate(self, anchor_df: pd.DataFrame) -> BridgeContractResult:
        """
        验证 anchor_table DataFrame 是否满足合约要求。

        参数：
            anchor_df: anchor_table.parquet 加载后的 DataFrame

        返回：
            BridgeContractResult
        """
        errors: list[str] = []
        warnings: list[str] = []

        # 1. 必填字段存在性和非全 NaN 检查
        for fname in _CONTRACT_REQUIRED_FIELDS:
            if fname not in anchor_df.columns:
                errors.append(f"合约必填字段缺失: {fname!r}")
            elif anchor_df[fname].isna().all():
                errors.append(f"合约必填字段全为 NaN: {fname!r}")

        # 2. 推荐字段（仅警告）
        for fname in _CONTRACT_RECOMMENDED_FIELDS:
            if fname not in anchor_df.columns:
                warnings.append(f"推荐字段缺失: {fname!r}")

        # 3. z_lab_zone 合法值检查
        if "z_lab_zone" in anchor_df.columns:
            invalid_zones = anchor_df["z_lab_zone"].dropna().apply(
                lambda x: str(x) not in _VALID_ZONES
            )
            n_invalid = int(invalid_zones.sum())
            if n_invalid > 0:
                errors.append(
                    f"z_lab_zone 包含非法值: {n_invalid} 行（合法值: green/yellow/red）"
                )

        # 4. s_lab_score 范围检查
        if "s_lab_score" in anchor_df.columns:
            score = pd.to_numeric(anchor_df["s_lab_score"], errors="coerce")
            n_out = int(((score < 0) | (score > 100)).fillna(False).sum())
            if n_out > 0:
                warnings.append(f"s_lab_score: {n_out} 行超出 [0,100] 范围")

        passed = len(errors) == 0

        # 构建 snapshot
        now = datetime.now(timezone.utc).isoformat()
        snapshot: dict[str, Any] = {
            "contract_version": "contract_v1",
            "validated_at": now,
            "n_rows": len(anchor_df),
            "passed": passed,
            "errors": errors,
            "warnings": warnings,
            "field_inventory": {
                "required": {f: f in anchor_df.columns for f in _CONTRACT_REQUIRED_FIELDS},
                "recommended": {f: f in anchor_df.columns for f in _CONTRACT_RECOMMENDED_FIELDS},
                "all_columns": list(anchor_df.columns),
            },
            "zone_distribution": {},
            "score_stats": {},
        }

        if "z_lab_zone" in anchor_df.columns:
            snapshot["zone_distribution"] = anchor_df["z_lab_zone"].value_counts().to_dict()

        if "s_lab_score" in anchor_df.columns:
            score = pd.to_numeric(anchor_df["s_lab_score"], errors="coerce")
            snapshot["score_stats"] = {
                "mean": round(float(score.mean()), 2) if score.notna().any() else None,
                "std": round(float(score.std()), 2) if score.notna().any() else None,
                "min": round(float(score.min()), 2) if score.notna().any() else None,
                "max": round(float(score.max()), 2) if score.notna().any() else None,
                "n_valid": int(score.notna().sum()),
                "n_nan": int(score.isna().sum()),
            }

        result = BridgeContractResult(
            passed=passed,
            errors=errors,
            warnings=warnings,
            snapshot=snapshot,
        )

        if passed:
            logger.info("Bridge Contract 验证通过: 0 errors, %d warnings", len(warnings))
        else:
            logger.warning(
                "Bridge Contract 验证失败: %d errors, %d warnings",
                len(errors),
                len(warnings),
            )

        return result
