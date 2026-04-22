"""
reference_subset.py — Reference-normal 子集构建模块。

功能：
    基于 reference_rules_v2.yaml 筛选参考正常子集（wide + strict）。
    - wide: 无高血压史、无运动高血压、无冠心病/心衰（NaN=absent）、
            VO2peak >= 70%pred、VE/VCO2 slope <= 30、年龄 [60, 80]
    - strict: wide + HR 努力度代理（hr_peak >= 85% × (220 - age)）

输出列：
    reference_flag_wide (bool): 符合 wide 标准
    reference_flag_strict (bool): 符合 strict 标准（需 hr_peak + age 非 NaN）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logger = logging.getLogger(__name__)


@dataclass
class ReferenceSubsetResult:
    """子集筛选结果。"""

    df: pd.DataFrame            # 原 df + reference_flag_wide + reference_flag_strict
    n_wide: int                 # wide 子集样本量
    n_strict: int               # strict 子集样本量
    n_total: int                # 总样本量
    min_sample_size: int        # 配置中的最小样本量

    def summary(self) -> str:
        lines = [
            f"ReferenceSubset: {self.n_total} 行",
            f"  wide:   {self.n_wide} ({100 * self.n_wide / self.n_total:.1f}%)",
            f"  strict: {self.n_strict} ({100 * self.n_strict / self.n_total:.1f}%)",
        ]
        if self.n_wide < self.min_sample_size:
            lines.append(f"  ⚠ wide 样本量 {self.n_wide} < 最小要求 {self.min_sample_size}")
        if self.n_strict < self.min_sample_size:
            lines.append(f"  ⚠ strict 样本量 {self.n_strict} < 最小要求 {self.min_sample_size}")
        return "\n".join(lines)


class ReferenceSubsetBuilder:
    """
    构建 reference-normal 子集（wide + strict）。

    使用方法：
        builder = ReferenceSubsetBuilder("configs/data/reference_rules_v2.yaml")
        result = builder.build(df)
    """

    def __init__(self, rules_path: str | Path) -> None:
        self._rules = self._load_rules(Path(rules_path))
        self._min_sample = self._rules.get("reference_subset", {}).get("min_sample_size", 50)
        self._wide_cfg: dict[str, Any] = (
            self._rules.get("reference_subset", {}).get("wide", {})
        )
        self._strict_cfg: dict[str, Any] = (
            self._rules.get("reference_subset", {}).get("strict", {})
        )

    @staticmethod
    def _load_rules(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"reference_rules 不存在: {path}")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _apply_wide_mask(self, df: pd.DataFrame) -> pd.Series:
        """
        计算 wide 筛选 mask。
        规则（均须满足）：
        - htn_history == False
        - eih_status == False
        - cad_history == False（NaN 视为 False）
        - hf_history == False（NaN 视为 False）
        - vo2_peak_pct_pred >= 70
        - ve_vco2_slope <= 30
        - age in [60, 80]
        """
        criteria = self._wide_cfg.get("criteria", {})
        age_range = self._wide_cfg.get("age_range", [60, 80])

        mask = pd.Series(True, index=df.index)

        # 布尔字段（必须为 False，NaN 视为 False → NaN 符合条件）
        for bool_field in ["htn_history", "eih_status"]:
            if bool_field in criteria and criteria[bool_field] is False:
                if bool_field in df.columns:
                    mask = mask & (df[bool_field].fillna(False) == False)  # noqa: E712

        # 稀疏布尔字段（NaN = absent = False）
        for sparse_field in ["cad_history", "hf_history"]:
            if sparse_field in criteria and criteria[sparse_field] is False:
                if sparse_field in df.columns:
                    filled = df[sparse_field].map(lambda x: bool(x) if pd.notna(x) else False)
                    mask = mask & (~filled)

        # CPET 性能门槛
        if "vo2_peak_pct_pred" in criteria and "vo2_peak_pct_pred" in df.columns:
            thresh = criteria["vo2_peak_pct_pred"]
            if isinstance(thresh, dict) and "gte" in thresh:
                mask = mask & (df["vo2_peak_pct_pred"].fillna(-1) >= thresh["gte"])

        if "ve_vco2_slope" in criteria and "ve_vco2_slope" in df.columns:
            thresh = criteria["ve_vco2_slope"]
            if isinstance(thresh, dict) and "lte" in thresh:
                mask = mask & (df["ve_vco2_slope"].fillna(9999) <= thresh["lte"])

        # 年龄范围
        if "age" in df.columns and age_range:
            mask = mask & (df["age"].fillna(-1) >= age_range[0])
            mask = mask & (df["age"].fillna(9999) <= age_range[1])

        return mask

    def _apply_strict_mask(self, df: pd.DataFrame, wide_mask: pd.Series) -> pd.Series:
        """
        计算 strict 筛选 mask（wide 的超集条件）。
        额外条件：hr_peak >= 0.85 × (220 - age)
        """
        mask = wide_mask.copy()

        extra = self._strict_cfg.get("additional_criteria", {})
        if extra.get("hr_effort_proxy", False):
            threshold_pct = extra.get("hr_effort_threshold_pct", 0.85)
            if "hr_peak" in df.columns and "age" in df.columns:
                hr_max_pred = (220 - df["age"].fillna(70)) * threshold_pct
                # hr_peak NaN → 不满足条件
                hr_ok = df["hr_peak"].fillna(-1) >= hr_max_pred
                mask = mask & hr_ok
            else:
                logger.warning(
                    "ReferenceSubset strict: hr_peak 或 age 列不存在，"
                    "strict 退化为 wide"
                )

        return mask

    def build(self, df: pd.DataFrame) -> ReferenceSubsetResult:
        """
        执行筛选，添加 reference_flag_wide / reference_flag_strict 列。

        参数：
            df: 注册后的 DataFrame（含 htn_history, eih_status, cohort_2x2 等）

        返回：
            ReferenceSubsetResult（含修改后 df）
        """
        result_df = df.copy()

        wide_mask = self._apply_wide_mask(result_df)
        strict_mask = self._apply_strict_mask(result_df, wide_mask)

        result_df["reference_flag_wide"] = wide_mask
        result_df["reference_flag_strict"] = strict_mask

        n_wide = int(wide_mask.sum())
        n_strict = int(strict_mask.sum())

        if n_wide < self._min_sample:
            logger.warning(
                "ReferenceSubset wide: 样本量 %d 低于最小要求 %d",
                n_wide, self._min_sample,
            )
        if n_strict < self._min_sample:
            logger.warning(
                "ReferenceSubset strict: 样本量 %d 低于最小要求 %d",
                n_strict, self._min_sample,
            )

        logger.info(
            "ReferenceSubset 完成: 总=%d, wide=%d, strict=%d",
            len(result_df), n_wide, n_strict,
        )

        return ReferenceSubsetResult(
            df=result_df,
            n_wide=n_wide,
            n_strict=n_strict,
            n_total=len(result_df),
            min_sample_size=self._min_sample,
        )
