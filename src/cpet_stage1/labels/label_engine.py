"""
label_engine.py — P0/P1 标签生成引擎。

基于 label_rules_v2.yaml 配置，从 curated/cohort DataFrame 生成：
- P0：运动安全事件代理标签（binary）
    活跃条件（优雅降级版）：
      - eih_status == True（从 group_code 推导）
      - vo2_peak_pct_pred < 50
      - bp_peak_sys > 220
- P1：运动安全区（3-class ordinal: 0=green, 1=yellow, 2=red）
    green: vo2_peak_pct_pred>=70 AND ve_vco2_slope<=30 AND eih_status==False
    yellow: vo2_peak_pct_pred in [50,70) OR ve_vco2_slope in (30,36]
    red: vo2_peak_pct_pred<50 OR ve_vco2_slope>36 OR eih_status==True
    冲突：take_worst（取最大 label 值）
- HR 努力度代理 flag：hr_peak >= 85% × (220 - age)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logger = logging.getLogger(__name__)


@dataclass
class LabelResult:
    """标签生成结果。"""

    label_df: pd.DataFrame          # 含 p0_event, p0_trigger_*, p1_zone 列
    summary: dict[str, Any]          # 标签分布统计
    inactive_criteria: list[str]     # 不可用规则说明
    effort_flags: pd.Series          # HR 努力度代理标志（bool）

    def report(self) -> str:
        """返回可读摘要。"""
        lines = ["LabelEngine 结果："]

        # P0 统计
        p0 = self.label_df["p0_event"]
        n_total = len(p0)
        n_pos = int(p0.sum())
        pct_pos = 100 * n_pos / n_total if n_total > 0 else 0
        lines.append(f"  P0 阳性: {n_pos}/{n_total} ({pct_pos:.1f}%)")

        # P1 统计
        p1 = self.label_df["p1_zone"]
        for zone_name, zone_val in [("green", 0), ("yellow", 1), ("red", 2)]:
            cnt = int((p1 == zone_val).sum())
            pct = 100 * cnt / n_total if n_total > 0 else 0
            lines.append(f"  P1 {zone_name}: {cnt} ({pct:.1f}%)")
        n_nan = int(p1.isna().sum())
        if n_nan:
            lines.append(f"  P1 NaN (全缺失): {n_nan}")

        # HR effort flag
        n_effort = int(self.effort_flags.sum()) if self.effort_flags.notna().any() else 0
        lines.append(f"  HR 努力度充足: {n_effort}/{n_total}")

        # inactive criteria
        if self.inactive_criteria:
            lines.append("  Inactive 规则（不可用）：")
            for ic in self.inactive_criteria:
                lines.append(f"    - {ic}")

        return "\n".join(lines)


class LabelEngine:
    """
    从 curated/cohort DataFrame 生成 P0/P1 标签。

    使用方法：
        engine = LabelEngine("configs/data/label_rules_v2.yaml")
        result = engine.run(df)
    """

    def __init__(self, rules_path: str | Path) -> None:
        self._rules_path = Path(rules_path)
        self._cfg = self._load_rules(self._rules_path)
        self._p0_cfg: dict[str, Any] = self._cfg.get("p0", {})
        self._p1_cfg: dict[str, Any] = self._cfg.get("p1", {})

        # 收集 inactive criteria 说明
        self._inactive: list[str] = []
        for ic in self._p0_cfg.get("inactive_criteria", []):
            self._inactive.append(f"P0/{ic.get('field', '?')}: {ic.get('reason', '')}")
        for ic in self._p1_cfg.get("inactive_criteria", []):
            self._inactive.append(f"P1/{ic.get('field', '?')}: {ic.get('reason', '')}")

    @staticmethod
    def _load_rules(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"label_rules 不存在: {path}")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def generate_p0(self, df: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
        """
        生成 P0 事件标签（binary）。

        活跃条件（满足任一即为阳性）：
        1. eih_status == True
        2. vo2_peak_pct_pred < 50
        3. bp_peak_sys > 220

        返回：
            (p0_event: bool Series, trigger_df: DataFrame with p0_trigger_* 列)
        """
        n = len(df)

        # 条件 1：eih_status（推导字段，无 NaN）
        if "eih_status" in df.columns:
            trigger_eih = df["eih_status"].map(lambda x: bool(x) if pd.notna(x) else False)
        else:
            trigger_eih = pd.Series(False, index=df.index)
            logger.warning("generate_p0: eih_status 列不存在，条件1全设为 False")

        # 条件 2：vo2_peak_pct_pred < 50（NaN 不触发）
        if "vo2_peak_pct_pred" in df.columns:
            trigger_capacity = df["vo2_peak_pct_pred"].lt(50).fillna(False)
        else:
            trigger_capacity = pd.Series(False, index=df.index)
            logger.warning("generate_p0: vo2_peak_pct_pred 列不存在，条件2全设为 False")

        # 条件 3：bp_peak_sys > 220（NaN 不触发）
        if "bp_peak_sys" in df.columns:
            trigger_bp = df["bp_peak_sys"].gt(220).fillna(False)
        else:
            trigger_bp = pd.Series(False, index=df.index)
            logger.warning("generate_p0: bp_peak_sys 列不存在，条件3全设为 False")

        p0_event = trigger_eih | trigger_capacity | trigger_bp

        trigger_df = pd.DataFrame(
            {
                "p0_trigger_eih": trigger_eih,
                "p0_trigger_capacity": trigger_capacity,
                "p0_trigger_bp": trigger_bp,
            },
            index=df.index,
        )

        logger.info(
            "P0: 阳性=%d (%.1f%%)，触发器: eih=%d, capacity=%d, bp=%d",
            p0_event.sum(), 100 * p0_event.mean(),
            trigger_eih.sum(), trigger_capacity.sum(), trigger_bp.sum(),
        )

        return p0_event, trigger_df

    def generate_p1(self, df: pd.DataFrame) -> pd.Series:
        """
        生成 P1 安全区标签（0=green, 1=yellow, 2=red）。

        逻辑：
        - 先逐行评估各区域条件，生成候选区列表
        - take_worst: 取最大 label 值（最差区）
        - 若所有关键字段均为 NaN，返回 NaN

        返回：
            p1_zone (float Series，含 NaN)
        """
        # 提取关键字段，NaN 保留
        pct_pred = df["vo2_peak_pct_pred"] if "vo2_peak_pct_pred" in df.columns \
            else pd.Series(float("nan"), index=df.index)
        slope = df["ve_vco2_slope"] if "ve_vco2_slope" in df.columns \
            else pd.Series(float("nan"), index=df.index)
        eih = df["eih_status"].map(lambda x: bool(x) if pd.notna(x) else False) if "eih_status" in df.columns \
            else pd.Series(False, index=df.index)

        n = len(df)
        zone = pd.Series(float("nan"), index=df.index, dtype="float64")

        # --- green 条件（所有条件均满足，且关键字段非 NaN）---
        # green: pct_pred>=70 AND slope<=30 AND eih==False
        green_mask = (
            pct_pred.fillna(-1).ge(70)
            & slope.fillna(9999).le(30)
            & (~eih)
        )
        # 但若 pct_pred 和 slope 都是 NaN，不应判为 green
        has_data = pct_pred.notna() | slope.notna()
        green_mask = green_mask & has_data
        zone[green_mask] = 0

        # --- yellow 条件（满足任一）---
        # yellow: pct_pred in [50,70) OR slope in (30,36]
        yellow_capacity = pct_pred.fillna(-1).ge(50) & pct_pred.fillna(-1).lt(70)
        yellow_slope = slope.fillna(-1).gt(30) & slope.fillna(-1).le(36)
        yellow_mask = (yellow_capacity | yellow_slope) & has_data
        # take_worst: 若已是 green 但 yellow 条件也满足 → 升为 yellow
        zone[yellow_mask] = zone[yellow_mask].fillna(0).clip(lower=1.0)

        # --- red 条件（满足任一）---
        # red: pct_pred<50 OR slope>36 OR eih==True
        red_capacity = pct_pred.fillna(9999).lt(50)
        red_slope = slope.fillna(-1).gt(36)
        red_eih = eih
        red_mask = (red_capacity | red_slope | red_eih) & has_data
        # take_worst: 升为 red
        zone[red_mask] = zone[red_mask].fillna(0).clip(lower=2.0)

        # 全 NaN 行保持 NaN
        zone[~has_data] = float("nan")

        n_green = int((zone == 0).sum())
        n_yellow = int((zone == 1).sum())
        n_red = int((zone == 2).sum())
        n_nan = int(zone.isna().sum())
        logger.info(
            "P1: green=%d (%.1f%%), yellow=%d (%.1f%%), red=%d (%.1f%%), NaN=%d",
            n_green, 100 * n_green / n,
            n_yellow, 100 * n_yellow / n,
            n_red, 100 * n_red / n,
            n_nan,
        )

        return zone

    def compute_effort_flag(self, df: pd.DataFrame) -> pd.Series:
        """
        计算 HR 努力度代理标志。

        条件：hr_peak >= 0.85 × (220 - age)
        若 hr_peak 或 age 缺失，返回 NaN。

        返回：
            effort_hr_adequate (bool/NaN Series)
        """
        effort_cfg = self._p1_cfg.get("effort_required", {}).get("hr_fallback", {})
        threshold_pct = effort_cfg.get("threshold_pct_pred", 0.85)

        if "hr_peak" not in df.columns or "age" not in df.columns:
            logger.warning("compute_effort_flag: hr_peak 或 age 列不存在，返回全 NaN")
            return pd.Series(float("nan"), index=df.index)

        hr_max_pred = (220 - df["age"]) * threshold_pct
        # hr_peak NaN → NaN；否则比较
        effort_flag = (df["hr_peak"] >= hr_max_pred).where(
            df["hr_peak"].notna() & df["age"].notna()
        )

        n_adequate = int(effort_flag.sum()) if effort_flag.notna().any() else 0
        logger.info(
            "HR effort: 充足=%d/%d (%.1f%%)",
            n_adequate, len(df), 100 * n_adequate / len(df) if len(df) > 0 else 0,
        )

        return effort_flag

    def run(self, df: pd.DataFrame) -> LabelResult:
        """
        组合运行 P0 + P1 + effort flag，返回 LabelResult。

        参数：
            df: 含 cohort 字段的 DataFrame（需含 eih_status 推导列）

        返回：
            LabelResult
        """
        # 生成 P0
        p0_event, trigger_df = self.generate_p0(df)

        # 生成 P1
        p1_zone = self.generate_p1(df)

        # 生成 effort flag
        effort_flags = self.compute_effort_flag(df)

        # 组合 label_df
        label_df = pd.DataFrame(index=df.index)
        label_df["p0_event"] = p0_event
        label_df["p0_trigger_eih"] = trigger_df["p0_trigger_eih"]
        label_df["p0_trigger_capacity"] = trigger_df["p0_trigger_capacity"]
        label_df["p0_trigger_bp"] = trigger_df["p0_trigger_bp"]
        label_df["p1_zone"] = p1_zone
        label_df["effort_hr_adequate"] = effort_flags

        # 汇总统计
        n_total = len(df)
        summary: dict[str, Any] = {
            "n_total": n_total,
            "p0_positive": int(p0_event.sum()),
            "p0_positive_pct": float(100 * p0_event.mean()),
            "p1_green": int((p1_zone == 0).sum()),
            "p1_yellow": int((p1_zone == 1).sum()),
            "p1_red": int((p1_zone == 2).sum()),
            "p1_nan": int(p1_zone.isna().sum()),
            "effort_adequate": int(effort_flags.sum()) if effort_flags.notna().any() else 0,
        }

        return LabelResult(
            label_df=label_df,
            summary=summary,
            inactive_criteria=list(self._inactive),
            effort_flags=effort_flags,
        )

    def save(
        self,
        result: LabelResult,
        label_path: str | Path,
        zone_path: str | Path | None = None,
    ) -> None:
        """
        保存 label_table 和可选的 zone_table。

        参数：
            result: LabelResult
            label_path: label_table.parquet 路径
            zone_path: zone_table.parquet 路径（可选）
        """
        label_path = Path(label_path)
        label_path.parent.mkdir(parents=True, exist_ok=True)
        result.label_df.to_parquet(label_path, index=False)
        logger.info("label_table 保存: %s (%d 行)", label_path, len(result.label_df))

        if zone_path is not None:
            from cpet_stage1.labels.safety_zone import assign_zones

            zone_path = Path(zone_path)
            zone_path.parent.mkdir(parents=True, exist_ok=True)
            zone_df = pd.DataFrame(index=result.label_df.index)
            zone_df["p1_zone"] = result.label_df["p1_zone"]
            zone_df["z_lab_zone"] = assign_zones(result.label_df["p1_zone"])
            zone_df.to_parquet(zone_path, index=False)
            logger.info("zone_table 保存: %s (%d 行)", zone_path, len(zone_df))
