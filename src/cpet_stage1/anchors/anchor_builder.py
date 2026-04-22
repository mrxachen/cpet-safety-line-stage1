"""
anchor_builder.py — R/T/I 三轴锚点资产构建器。

从 cohort_registry + label_table（+ 可选 reference_scores）提取所有锚点变量，
计算综合安全评分 S_lab 和安全区 Z_lab。

R 轴（储备）：vo2_peak_pct_pred, o2_pulse_peak, vt1_pct_vo2peak
T 轴（阈值）：vt1_hr, rcp_hr, vt1_load_w, ve_vco2_slope
I 轴（不稳定性）：eih_status, eih_nadir_spo2, bp_response_abnormal, arrhythmia_flag

S_lab_score：0–100 综合风险分数（越高=风险越高）
Z_lab_zone：green / yellow / red（来自 P1 zone 映射）
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# P1 zone 整数 → Z_lab 字符串
_ZONE_MAP = {0: "green", 1: "yellow", 2: "red"}


@dataclass
class AnchorTableResult:
    """锚点资产构建结果。"""

    df: pd.DataFrame
    anchor_coverage: dict[str, bool]
    n_total: int
    n_per_zone: dict[str, int]
    config: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [f"AnchorBuilder: {self.n_total} 行"]
        lines.append("  Z_lab 分布：")
        for zone, cnt in self.n_per_zone.items():
            pct = 100 * cnt / self.n_total if self.n_total > 0 else 0
            lines.append(f"    {zone}: {cnt} ({pct:.1f}%)")
        available = [k for k, v in self.anchor_coverage.items() if v]
        missing = [k for k, v in self.anchor_coverage.items() if not v]
        lines.append(f"  锚点变量可用: {len(available)}/{len(self.anchor_coverage)}")
        if missing:
            lines.append(f"  缺失锚点（NaN 填充）: {missing}")
        return "\n".join(lines)

    def to_parquet(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.df.to_parquet(path, index=False)
        logger.info("anchor_table 保存: %s (%d 行)", path, len(self.df))

    def coverage_report(self) -> str:
        lines = ["## 锚点变量覆盖率报告", ""]
        lines.append("| 变量 | 状态 | 有效N | 缺失N |")
        lines.append("|---|---|---|---|")
        for col, has_data in self.anchor_coverage.items():
            if col in self.df.columns:
                n_valid = int(self.df[col].notna().sum())
                n_miss = int(self.df[col].isna().sum())
                status = "✓ 可用" if has_data else "✗ 全缺失"
                lines.append(f"| {col} | {status} | {n_valid} | {n_miss} |")
        return "\n".join(lines)


class AnchorBuilder:
    """
    R/T/I 三轴锚点资产构建器。

    使用方法：
        builder = AnchorBuilder("configs/bridge/anchor_rules_v1.yaml")
        result = builder.build(cohort_df, label_df, reference_df=None)
    """

    def __init__(self, anchor_rules_path: str | Path) -> None:
        self._rules_path = Path(anchor_rules_path)
        self._cfg = self._load_rules(self._rules_path)

    @staticmethod
    def _load_rules(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"anchor_rules 不存在: {path}")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    # ------------------------------------------------------------------ #
    # 轴变量提取                                                            #
    # ------------------------------------------------------------------ #

    def _extract_r_axis(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        R 轴（储备）变量提取。

        R1: vo2_peak_pct_pred（直接字段）
        R2: o2_pulse_peak（直接字段）
        R3: vt1_pct_vo2peak（= vt1_vo2/vo2_peak × 100，派生）
        """
        r = pd.DataFrame(index=df.index)

        r["reserve_r1_vo2peak_pct_pred"] = (
            df["vo2_peak_pct_pred"].copy()
            if "vo2_peak_pct_pred" in df.columns
            else pd.Series(float("nan"), index=df.index)
        )

        r["reserve_r2_o2_pulse_peak"] = (
            df["o2_pulse_peak"].copy()
            if "o2_pulse_peak" in df.columns
            else pd.Series(float("nan"), index=df.index)
        )

        if "vt1_vo2" in df.columns and "vo2_peak" in df.columns:
            vt1 = pd.to_numeric(df["vt1_vo2"], errors="coerce")
            vo2p = pd.to_numeric(df["vo2_peak"], errors="coerce")
            r["reserve_r3_vt1_pct_vo2peak"] = (vt1 / vo2p * 100).where(
                vo2p.notna() & vo2p.gt(0)
            )
        else:
            r["reserve_r3_vt1_pct_vo2peak"] = pd.Series(float("nan"), index=df.index)

        return r

    def _extract_t_axis(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        T 轴（阈值）变量提取。

        T1: vt1_hr（可能缺失）
        T2: rcp_hr（可能缺失）
        T3: vt1_load_w（可能缺失）
        T4: ve_vco2_slope（直接字段）
        """
        t = pd.DataFrame(index=df.index)

        for col, dest in [
            ("vt1_hr", "threshold_t1_vt1_hr"),
            ("rcp_hr", "threshold_t2_rcp_hr"),
            ("vt1_load_w", "threshold_t3_vt1_load_w"),
            ("ve_vco2_slope", "threshold_t4_ve_vco2_slope"),
        ]:
            t[dest] = (
                df[col].copy()
                if col in df.columns
                else pd.Series(float("nan"), index=df.index)
            )

        return t

    def _extract_i_axis(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        I 轴（不稳定性）变量提取。

        I1: eih_status（从 group_code 推导，直接字段）
        I2: eih_nadir_spo2（可能缺失）
        I3: bp_response_abnormal（bp_peak_sys>180 派生，或直接字段）
        I4: arrhythmia_flag（inactive，全为 NaN）
        """
        i = pd.DataFrame(index=df.index)

        # I1: eih_status
        if "eih_status" in df.columns:
            i["instability_i1_eih_status"] = (
                df["eih_status"].map(lambda x: bool(x) if pd.notna(x) else False)
            )
        else:
            i["instability_i1_eih_status"] = False

        # I2: eih_nadir_spo2
        i["instability_i2_eih_nadir_spo2"] = (
            df["eih_nadir_spo2"].copy()
            if "eih_nadir_spo2" in df.columns
            else pd.Series(float("nan"), index=df.index)
        )

        # I3: bp_response_abnormal（直接字段优先；否则从 bp_peak_sys 推导）
        if "bp_response_abnormal" in df.columns:
            i["instability_i3_bp_response_abnormal"] = df["bp_response_abnormal"].map(
                lambda x: bool(x) if pd.notna(x) else False
            )
        elif "bp_peak_sys" in df.columns:
            bp = pd.to_numeric(df["bp_peak_sys"], errors="coerce")
            i["instability_i3_bp_response_abnormal"] = bp.gt(180).fillna(False)
        else:
            i["instability_i3_bp_response_abnormal"] = pd.Series(float("nan"), index=df.index)

        # I4: arrhythmia_flag（inactive）
        i["instability_i4_arrhythmia_flag"] = (
            df["arrhythmia_flag"].copy()
            if "arrhythmia_flag" in df.columns
            else pd.Series(float("nan"), index=df.index)
        )

        return i

    # ------------------------------------------------------------------ #
    # 轴综合评分                                                            #
    # ------------------------------------------------------------------ #

    def _compute_reserve_axis(self, r_df: pd.DataFrame) -> pd.Series:
        """
        R 轴综合评分（0–100，越高=储备越好）。

        R1 权重 0.6，R2 权重 0.2，R3 权重 0.2；缺失变量自动重归一化。
        """
        scores: dict[str, pd.Series] = {}
        weights: dict[str, float] = {}

        r1 = pd.to_numeric(r_df.get("reserve_r1_vo2peak_pct_pred"), errors="coerce")
        if r1.notna().any():
            scores["r1"] = (r1.clip(0, 140) / 140 * 100)
            weights["r1"] = 0.6

        r2 = pd.to_numeric(r_df.get("reserve_r2_o2_pulse_peak"), errors="coerce")
        if r2.notna().any():
            scores["r2"] = (r2.clip(0, 25) / 25 * 100)
            weights["r2"] = 0.2

        r3 = pd.to_numeric(r_df.get("reserve_r3_vt1_pct_vo2peak"), errors="coerce")
        if r3.notna().any():
            scores["r3"] = r3.clip(0, 100)
            weights["r3"] = 0.2

        if not scores:
            return pd.Series(float("nan"), index=r_df.index)

        total_w = sum(weights.values())
        result = sum(scores[k] * weights[k] / total_w for k in scores)
        return result.clip(0, 100)

    def _compute_threshold_axis(self, t_df: pd.DataFrame) -> pd.Series:
        """
        T 轴综合评分（0–100，越高=阈值越高/越安全）。

        主要使用 ve_vco2_slope（反向：越低越好）。
        """
        scores: dict[str, pd.Series] = {}
        weights: dict[str, float] = {}

        # T4: ve_vco2_slope 反向映射（slope 20→100分，slope 45→0分）
        t4 = pd.to_numeric(t_df.get("threshold_t4_ve_vco2_slope"), errors="coerce")
        if t4.notna().any():
            scores["t4"] = ((45 - t4.clip(20, 45)) / (45 - 20) * 100).clip(0, 100)
            weights["t4"] = 0.7

        t1 = pd.to_numeric(t_df.get("threshold_t1_vt1_hr"), errors="coerce")
        if t1.notna().any():
            scores["t1"] = (t1.clip(60, 160) / 160 * 100)
            weights["t1"] = 0.2

        t2 = pd.to_numeric(t_df.get("threshold_t2_rcp_hr"), errors="coerce")
        if t2.notna().any():
            scores["t2"] = (t2.clip(80, 180) / 180 * 100)
            weights["t2"] = 0.1

        if not scores:
            return pd.Series(float("nan"), index=t_df.index)

        total_w = sum(weights.values())
        result = sum(scores[k] * weights[k] / total_w for k in scores)
        return result.clip(0, 100)

    def _compute_instability_axis(self, i_df: pd.DataFrame) -> pd.Series:
        """
        I 轴综合评分（0–100，越高=越不稳定/风险越高）。

        I1 eih_status True → +80；I3 bp_response_abnormal True → +20。
        """
        risk = pd.Series(0.0, index=i_df.index)

        i1 = i_df.get("instability_i1_eih_status")
        if i1 is not None:
            risk += i1.map(lambda x: 80.0 if pd.notna(x) and bool(x) else 0.0).fillna(0.0)

        i3 = i_df.get("instability_i3_bp_response_abnormal")
        if i3 is not None:
            risk += i3.map(lambda x: 20.0 if pd.notna(x) and bool(x) else 0.0).fillna(0.0)

        i2 = pd.to_numeric(i_df.get("instability_i2_eih_nadir_spo2"), errors="coerce")
        if i2.notna().any():
            spo2_risk = ((90 - i2.clip(80, 98)) / (90 - 80) * 10).clip(0, 10).fillna(0)
            risk = (risk + spo2_risk).clip(0, 100)

        return risk.clip(0, 100)

    # ------------------------------------------------------------------ #
    # 主构建方法                                                            #
    # ------------------------------------------------------------------ #

    def build(
        self,
        cohort_df: pd.DataFrame,
        label_df: pd.DataFrame | None = None,
        reference_df: pd.DataFrame | None = None,
    ) -> AnchorTableResult:
        """
        构建锚点资产表。

        参数：
            cohort_df:    cohort_registry.parquet（含所有临床测量数据）
            label_df:     label_table.parquet（含 p0_event, p1_zone）
            reference_df: reference_scores.parquet（含 %pred/z-score，可选）

        返回：
            AnchorTableResult
        """
        df = cohort_df.copy().reset_index(drop=True)

        # 合并 label_df（避免列名冲突）
        if label_df is not None:
            ldf = label_df.reset_index(drop=True)
            for col in ldf.columns:
                if col not in df.columns:
                    df[col] = ldf[col]

        # 合并 reference_df（不覆盖已有列）
        if reference_df is not None:
            rdf = reference_df.reset_index(drop=True)
            for col in rdf.columns:
                if col not in df.columns:
                    df[col] = rdf[col]

        # 提取三轴变量
        r_df = self._extract_r_axis(df)
        t_df = self._extract_t_axis(df)
        i_df = self._extract_i_axis(df)

        # 计算轴评分
        reserve_axis = self._compute_reserve_axis(r_df)
        threshold_axis = self._compute_threshold_axis(t_df)
        instability_axis = self._compute_instability_axis(i_df)

        # A_lab_vector（三元组 JSON 字符串）
        a_lab_vector = pd.Series(
            [
                json.dumps({
                    "R": round(float(r), 2) if pd.notna(r) else None,
                    "T": round(float(t), 2) if pd.notna(t) else None,
                    "I": round(float(i_val), 2) if pd.notna(i_val) else None,
                })
                for r, t, i_val in zip(reserve_axis, threshold_axis, instability_axis)
            ],
            index=df.index,
        )

        # S_lab_score（综合风险分数，越高=风险越高）
        # 将 reserve/threshold 评分反转（越高的储备/阈值 → 越低的风险）
        risk_r = (100 - reserve_axis.clip(0, 100)).where(reserve_axis.notna())
        risk_t = (100 - threshold_axis.clip(0, 100)).where(threshold_axis.notna())
        risk_i = instability_axis.clip(0, 100).where(instability_axis.notna())

        components = []
        comp_weights: list[float] = []
        if risk_i.notna().any():
            components.append(risk_i)
            comp_weights.append(0.4)
        if risk_r.notna().any():
            components.append(risk_r)
            comp_weights.append(0.4)
        if risk_t.notna().any():
            components.append(risk_t)
            comp_weights.append(0.2)

        if components:
            total_w = sum(comp_weights)
            s_lab_score = sum(
                c * w / total_w for c, w in zip(components, comp_weights)
            ).clip(0, 100)
        else:
            s_lab_score = pd.Series(float("nan"), index=df.index)

        # Z_lab_zone（优先使用 P1 zone；否则从 S_lab 推导；NaN zone 保持 NaN）
        if "p1_zone" in df.columns:
            z_lab_zone = df["p1_zone"].map(
                lambda x: _ZONE_MAP.get(int(x)) if pd.notna(x) else None
            )
        else:
            z_lab_zone = s_lab_score.map(
                lambda x: (
                    "green" if pd.notna(x) and x < 34 else
                    "yellow" if pd.notna(x) and x < 67 else
                    "red" if pd.notna(x) else None
                )
            )

        # 组装锚点表
        anchor_df = pd.DataFrame(index=df.index)

        for id_col in ["cpet_session_id", "subject_id", "group_code", "cohort_2x2"]:
            if id_col in df.columns:
                anchor_df[id_col] = df[id_col]

        for label_col in ["p0_event", "p1_zone"]:
            if label_col in df.columns:
                anchor_df[label_col] = df[label_col]

        anchor_df = pd.concat([anchor_df, r_df, t_df, i_df], axis=1)

        anchor_df["reserve_axis"] = reserve_axis
        anchor_df["threshold_axis"] = threshold_axis
        anchor_df["instability_axis"] = instability_axis
        anchor_df["a_lab_vector"] = a_lab_vector
        anchor_df["s_lab_score"] = s_lab_score
        anchor_df["z_lab_zone"] = z_lab_zone

        # 覆盖率统计
        all_anchor_cols = list(r_df.columns) + list(t_df.columns) + list(i_df.columns)
        coverage = {
            col: bool(anchor_df[col].notna().any()) if col in anchor_df.columns else False
            for col in all_anchor_cols
        }

        n_per_zone = {
            zone: int((z_lab_zone == zone).sum())
            for zone in ["green", "yellow", "red"]
        }
        n_nan_zone = int(z_lab_zone.isna().sum())
        if n_nan_zone > 0:
            n_per_zone["NaN"] = n_nan_zone
        n_per_zone = {k: v for k, v in n_per_zone.items() if v > 0}

        logger.info(
            "AnchorBuilder 完成: %d 行, Z_lab: %s, S_lab 均值=%.1f",
            len(anchor_df),
            n_per_zone,
            float(s_lab_score.mean()) if s_lab_score.notna().any() else float("nan"),
        )

        return AnchorTableResult(
            df=anchor_df,
            anchor_coverage=coverage,
            n_total=len(anchor_df),
            n_per_zone=n_per_zone,
            config=self._cfg,
        )
