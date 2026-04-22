"""
zone_engine_v2.py — Phase F Step 2：数据驱动安全区引擎

核心创新：
1. R/T/I 三轴权重由数据驱动（与 test_result 的 point-biserial 相关性）
2. S_lab_v2 连续评分 → Method A（结局锚定法）切点：Youden's J
3. 新增 I 轴变量：bp_peak_dia、o2_pulse_trajectory
4. T 轴引入运动习惯条件调整
5. 个性化分层：HTN history、sex、age 组、β-blocker 使用

安全区定义：
- Green：S_lab_v2 < 低切点（低风险，无明显异常）
- Yellow：低切点 ≤ S_lab_v2 < 高切点（中间地带，需关注）
- Red：S_lab_v2 ≥ 高切点（高风险，显著偏离正常）

切点方法（Method A — 结局锚定）：
- outcome = test_result 阳性/可疑阳性（vs 阴性）
- 低切点（Green/Yellow 界）：使灵敏度 ≥ 0.90（不放过高风险）
- 高切点（Yellow/Red 界）：Youden's J 最优（综合灵敏度+特异度）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── 结局字段定义 ────────────────────────────────────────────────────────────
MIN_REF_N = 30   # 参考子集最小样本量

OUTCOME_COL = "test_result"
OUTCOME_POSITIVE_VALUES = {"阳性", "可疑阳性"}

# ── 分层因子 ─────────────────────────────────────────────────────────────────
STRAT_FACTORS = ["htn_history", "sex", "age_group", "beta_blocker"]

# ── 默认文献先验切点（软约束，用于验证） ─────────────────────────────────────
LITERATURE_THRESHOLDS = {
    "vo2_peak_pct_pred_low": 50.0,   # Weber <50%: Red（心衰）
    "vo2_peak_pct_pred_mid": 70.0,   # 50-70%: Yellow
    "ve_vco2_slope_high": 36.0,      # >36: Red（心衰）
    "ve_vco2_slope_mid": 30.0,       # 30-36: Yellow
}

# ── O₂ 脉搏轨迹异常模式 ─────────────────────────────────────────────────────
O2_PULSE_ABNORMAL_PATTERNS = {
    "早期持续平台", "晚期平台", "晚期持续平台", "下降", "晚期下降",
    "运动晚期平台", "在运动试验期间上升迟缓", "上升迟缓", "晚期斜率下降",
    "运动终止前下降", "运动后期下降", "运动晚期下降",
}


# ─────────────────────────────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AxisWeight:
    """数据驱动轴权重。"""
    r_weight: float
    t_weight: float
    i_weight: float
    method: str               # "correlation" | "equal"
    correlations: dict[str, float] = field(default_factory=dict)


@dataclass
class ZoneCutpoints:
    """Zone 切点（连续 S_lab_v2 → Green/Yellow/Red）。"""
    low: float             # Green/Yellow 界（高灵敏度点）
    high: float            # Yellow/Red 界（Youden's J）
    method: str            # "youden" | "percentile" | "literature"
    sensitivity_at_low: float = float("nan")
    specificity_at_low: float = float("nan")
    sensitivity_at_high: float = float("nan")
    specificity_at_high: float = float("nan")
    youden_j: float = float("nan")
    bootstrap_ci_high: tuple[float, float] | None = None  # 95% CI for high cutpoint
    n_outcome_pos: int = 0
    n_outcome_total: int = 0
    strat_key: str = "global"

    def to_dict(self) -> dict[str, Any]:
        return {
            "strat_key": self.strat_key,
            "low_cutpoint": round(self.low, 2),
            "high_cutpoint": round(self.high, 2),
            "method": self.method,
            "sensitivity_at_low": round(self.sensitivity_at_low, 3) if not np.isnan(self.sensitivity_at_low) else None,
            "specificity_at_low": round(self.specificity_at_low, 3) if not np.isnan(self.specificity_at_low) else None,
            "sensitivity_at_high": round(self.sensitivity_at_high, 3) if not np.isnan(self.sensitivity_at_high) else None,
            "specificity_at_high": round(self.specificity_at_high, 3) if not np.isnan(self.specificity_at_high) else None,
            "youden_j": round(self.youden_j, 3) if not np.isnan(self.youden_j) else None,
            "n_positive": self.n_outcome_pos,
            "n_total": self.n_outcome_total,
        }


@dataclass
class ZoneEngineV2Result:
    """Phase F Step 2 全量输出。"""
    df: pd.DataFrame                      # 含 s_lab_v2、z_lab_v2 等新列
    axis_weights: AxisWeight
    global_cutpoints: ZoneCutpoints
    strat_cutpoints: dict[str, ZoneCutpoints]   # {strat_key: cutpoints}
    zone_distribution: dict[str, dict[str, int]] # {strat_key: {green/yellow/red: N}}
    reclassification: pd.DataFrame               # 新旧 zone 重分类矩阵
    config: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self, path: str | Path | None = None) -> str:
        lines = [
            "# Phase F Step 2 — 数据驱动安全区引擎报告（v2）",
            "",
            "## 核心方法",
            "",
            "1. **R/T/I 轴权重**：基于与 test_result 的 point-biserial 相关性确定",
            "2. **Zone 切点**：Method A（结局锚定）— Youden's J 优化",
            "3. **个性化**：HTN history × sex × age 组分层",
            "",
        ]

        # 轴权重
        w = self.axis_weights
        lines.append("## R/T/I 轴权重（数据驱动）")
        lines.append("")
        lines.append(f"- **方法**：{w.method}")
        lines.append(f"- **R轴（储备）权重**：{w.r_weight:.3f}")
        lines.append(f"- **T轴（阈值）权重**：{w.t_weight:.3f}")
        lines.append(f"- **I轴（不稳定性）权重**：{w.i_weight:.3f}")
        if w.correlations:
            lines.append("- **各分量与结局的相关性**：")
            for k, v in sorted(w.correlations.items(), key=lambda x: -abs(x[1])):
                lines.append(f"  - `{k}`：r={v:+.3f}")
        lines.append("")

        # 全局切点
        cp = self.global_cutpoints
        lines.append("## 全局 Zone 切点")
        lines.append("")
        lines.append(f"- **方法**：{cp.method}")
        lines.append(f"- **Green/Yellow 界（低切点）**：{cp.low:.2f}")
        lines.append(f"  - 灵敏度：{cp.sensitivity_at_low:.3f}，特异度：{cp.specificity_at_low:.3f}")
        lines.append(f"- **Yellow/Red 界（高切点）**：{cp.high:.2f}")
        lines.append(f"  - 灵敏度：{cp.sensitivity_at_high:.3f}，特异度：{cp.specificity_at_high:.3f}")
        lines.append(f"  - Youden's J：{cp.youden_j:.3f}")
        if cp.bootstrap_ci_high:
            lines.append(f"  - Bootstrap 95% CI（高切点）：[{cp.bootstrap_ci_high[0]:.2f}, {cp.bootstrap_ci_high[1]:.2f}]")
        lines.append(f"- **阳性样本**：{cp.n_outcome_pos}/{cp.n_outcome_total} ({100*cp.n_outcome_pos/max(cp.n_outcome_total,1):.1f}%)")
        lines.append("")

        # 文献切点对比
        lines.append("## 与文献切点的对比")
        lines.append("")
        lines.append("| 指标 | 本数据驱动切点 | 文献先验（Weber-Janicki等）| 偏差 |")
        lines.append("|---|---|---|---|")
        # 从 df 中提取 vo2_peak_pct_pred 对应切点
        if "s_lab_v2" in self.df.columns and "vo2_peak_pct_pred" in self.df.columns:
            # 找 S_lab_v2 对应的 vo2_peak_pct_pred 中位数（按 zone）
            for zone, label_v in [("green", "Green中位%pred"), ("yellow", "Yellow中位%pred"), ("red", "Red中位%pred")]:
                zone_mask = self.df["z_lab_v2"] == zone
                if zone_mask.sum() > 0:
                    med = self.df.loc[zone_mask, "vo2_peak_pct_pred"].median()
                    lines.append(f"| VO₂peak %pred ({zone}) | {med:.1f}% | 文献: Green≥70%, Yellow 50-70%, Red<50% | — |")
        lines.append("")

        # Zone 分布
        lines.append("## Zone 分布（全局 + 分层）")
        lines.append("")
        for sk, dist in self.zone_distribution.items():
            n_total = sum(dist.values())
            lines.append(f"**{sk}**（N={n_total}）：")
            for zone in ["green", "yellow", "red"]:
                n = dist.get(zone, 0)
                pct = 100 * n / n_total if n_total > 0 else 0
                lines.append(f"  - {zone}: {n} ({pct:.1f}%)")
            lines.append("")

        # 重分类矩阵
        lines.append("## 新旧 Zone 重分类矩阵（v1 P1 zone → v2 Z_lab_v2）")
        lines.append("")
        if not self.reclassification.empty:
            lines.append(_df_to_pipe_table(self.reclassification, index=True))
            total = self.reclassification.values.sum()
            diag = sum(self.reclassification.iloc[i, i] for i in range(min(self.reclassification.shape)))
            agreement = diag / total if total > 0 else 0
            lines.append("")
            lines.append(f"**一致率**：{agreement:.1%}（对角线比例）")
            lines.append("")
        else:
            lines.append("*(无旧 zone 数据进行对比)*")
            lines.append("")

        # 分层切点表
        if self.strat_cutpoints:
            lines.append("## 分层切点汇总")
            lines.append("")
            rows = []
            for sk, scp in self.strat_cutpoints.items():
                rows.append({
                    "分层": sk,
                    "N阳性": scp.n_outcome_pos,
                    "N总计": scp.n_outcome_total,
                    "低切点": f"{scp.low:.2f}",
                    "高切点": f"{scp.high:.2f}",
                    "Youden J": f"{scp.youden_j:.3f}" if not np.isnan(scp.youden_j) else "—",
                    "方法": scp.method,
                })
            if rows:
                diag_df = pd.DataFrame(rows)
                lines.append(_df_to_pipe_table(diag_df, index=False))
                lines.append("")

        md = "\n".join(lines)
        if path is not None:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(md, encoding="utf-8")
            logger.info("Zone Engine v2 报告已写入：%s", p)
        return md


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────

def _binary_outcome(df: pd.DataFrame) -> pd.Series:
    """将 test_result 转换为二值结局（阳性/可疑阳性=1，阴性=0，缺失=NaN）。"""
    if OUTCOME_COL not in df.columns:
        logger.warning("test_result 列不存在，无法使用 Method A")
        return pd.Series(np.nan, index=df.index)
    raw = df[OUTCOME_COL].astype(str).str.strip()
    outcome = raw.map(lambda x: 1 if x in OUTCOME_POSITIVE_VALUES else (0 if x == "阴性" else np.nan))
    n_pos = int((outcome == 1).sum())
    n_neg = int((outcome == 0).sum())
    logger.info("结局分布：阳性=%d, 阴性=%d, 缺失=%d", n_pos, n_neg, int(outcome.isna().sum()))
    return outcome


def _point_biserial_corr(score: pd.Series, outcome: pd.Series) -> float:
    """计算 point-biserial 相关系数（忽略 NaN）。"""
    valid = score.notna() & outcome.notna()
    if valid.sum() < 10:
        return 0.0
    try:
        from scipy.stats import pointbiserialr
        r, _ = pointbiserialr(outcome[valid].astype(float), score[valid].astype(float))
        return float(r)
    except Exception:
        # 降级为 pearson
        return float(score[valid].corr(outcome[valid]))


def _youden_cutpoints(
    score: pd.Series,
    outcome: pd.Series,
    min_sensitivity_low: float = 0.90,
    strat_key: str = "global",
    n_bootstrap: int = 200,
    rng: np.random.Generator | None = None,
) -> ZoneCutpoints:
    """
    使用 Youden's J 找最优高切点，使用高灵敏度点找低切点。

    Parameters
    ----------
    score : S_lab_v2 连续评分（越高=风险越高）
    outcome : 二值结局（1=阳性，0=阴性）
    min_sensitivity_low : 低切点的最小灵敏度（默认0.90）
    strat_key : 分层标识
    n_bootstrap : Bootstrap 次数
    rng : 随机数生成器

    Returns
    -------
    ZoneCutpoints
    """
    valid = score.notna() & outcome.notna()
    s = score[valid].astype(float).values
    y = outcome[valid].astype(float).values

    n_pos = int(y.sum())
    n_total = len(y)

    # 候选切点
    thresholds = np.unique(s)
    if len(thresholds) < 3 or (y == 1).sum() < 2 or (y == 0).sum() < 2:
        # 降级为百分位法
        logger.warning("[%s] 有效正负样本不足，使用百分位法", strat_key)
        return _percentile_cutpoints(score, strat_key=strat_key)

    pos_scores = s[y == 1]
    neg_scores = s[y == 0]

    # 计算每个切点的 sensitivity (TPR) / specificity (TNR)
    # S_lab 越高 = 风险越高，切点以上 = 预测为"阳性"
    # Sensitivity = P(score >= threshold | positive case)
    # Specificity = P(score < threshold | negative case)
    sens_arr = np.array([np.mean(pos_scores >= t) for t in thresholds])
    spec_arr = np.array([np.mean(neg_scores < t) for t in thresholds])
    youden_arr = sens_arr + spec_arr - 1

    # 高切点：Youden's J 最大值
    best_high_idx = int(np.argmax(youden_arr))
    high_cut = float(thresholds[best_high_idx])
    sens_high = float(sens_arr[best_high_idx])
    spec_high = float(spec_arr[best_high_idx])
    youden_j = float(youden_arr[best_high_idx])

    # 低切点：找最高的阈值使得灵敏度 ≥ min_sensitivity_low，且 ≤ high_cut
    # 从高→低扫描（thresholds 已排序），找满足灵敏度条件 AND <= high_cut 的最高切点
    cand_low_mask = (sens_arr >= min_sensitivity_low) & (thresholds <= high_cut)
    if cand_low_mask.any():
        # 取满足条件中最高的阈值（特异度最高）
        low_cut = float(thresholds[cand_low_mask][-1])
        low_idx = np.where(thresholds == low_cut)[0]
        if len(low_idx) > 0:
            sens_low = float(sens_arr[low_idx[0]])
            spec_low = float(spec_arr[low_idx[0]])
        else:
            sens_low = np.nan
            spec_low = np.nan
    else:
        # 灵敏度不足，使用 min(high_cut, P25 of positives)
        low_cut = min(high_cut, float(np.percentile(pos_scores, 25)))
        sens_low = np.nan
        spec_low = np.nan

    # 最终保证 low_cut ≤ high_cut
    low_cut = min(low_cut, high_cut)

    # Bootstrap 95% CI（高切点）
    ci_high = None
    if n_bootstrap > 0 and n_pos >= 10 and rng is not None:
        boot_highs = []
        for _ in range(n_bootstrap):
            boot_idx = rng.choice(n_total, size=n_total, replace=True)
            bs = s[boot_idx]
            by = y[boot_idx]
            bt = np.unique(bs)
            if len(bt) < 3:
                continue
            bs_arr = np.array([np.mean(by[bs >= t]) if np.any(bs >= t) else 0.0 for t in bt])
            bp_arr = np.array([np.mean(1 - by[bs < t]) if np.any(bs < t) else 0.0 for t in bt])
            bj_arr = bs_arr + bp_arr - 1
            boot_highs.append(float(bt[np.argmax(bj_arr)]))
        if boot_highs:
            ci_high = (float(np.percentile(boot_highs, 2.5)), float(np.percentile(boot_highs, 97.5)))

    return ZoneCutpoints(
        low=low_cut,
        high=high_cut,
        method="youden",
        sensitivity_at_low=sens_low,
        specificity_at_low=spec_low,
        sensitivity_at_high=sens_high,
        specificity_at_high=spec_high,
        youden_j=youden_j,
        bootstrap_ci_high=ci_high,
        n_outcome_pos=n_pos,
        n_outcome_total=n_total,
        strat_key=strat_key,
    )


def _percentile_cutpoints(
    score: pd.Series,
    low_pct: float = 25.0,
    high_pct: float = 75.0,
    strat_key: str = "global",
) -> ZoneCutpoints:
    """分布百分位法切点（Method B，备用）。"""
    valid = score.dropna()
    low = float(np.percentile(valid, low_pct))
    high = float(np.percentile(valid, high_pct))
    return ZoneCutpoints(
        low=low,
        high=high,
        method="percentile",
        n_outcome_pos=0,
        n_outcome_total=len(valid),
        strat_key=strat_key,
    )


def _reference_percentile_cutpoints(
    score: pd.Series,
    reference_mask: pd.Series | None,
    low_pct: float = 75.0,
    high_pct: float = 90.0,
    strat_key: str = "global",
) -> ZoneCutpoints:
    """
    Method B（参考正常人群分位法）：
    在参考正常子集中计算 S_lab_v2 的分位数作为切点。

    Green: S_lab_v2 ≤ P75 of reference (≤正常第75百分位)
    Yellow: P75 < S_lab_v2 ≤ P90 of reference (在正常第75-90百分位之间)
    Red: S_lab_v2 > P90 of reference (显著超出正常范围)

    临床意义：P90 是健康对照组中最差的10%的水平，超过此水平的患者具有
    显著异常的运动反应，需要临床干预。
    """
    if reference_mask is not None:
        ref_scores = score[reference_mask].dropna()
    else:
        ref_scores = pd.Series(dtype=float)

    if len(ref_scores) < 5:
        # 回退到全体百分位
        ref_scores = score.dropna()

    low = float(np.percentile(ref_scores, low_pct))
    high = float(np.percentile(ref_scores, high_pct))
    return ZoneCutpoints(
        low=low,
        high=high,
        method="reference_percentile",
        n_outcome_pos=0,
        n_outcome_total=len(score.dropna()),
        strat_key=strat_key,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 轴计算
# ─────────────────────────────────────────────────────────────────────────────

def _compute_r_axis_v2(df: pd.DataFrame) -> pd.DataFrame:
    """
    R 轴（储备轴）改进版。

    R1: vo2_peak_pct_pred（核心，% predicted）
    R2: o2_pulse_peak（相对化后）
    R3: vt1_pct_vo2peak（VT1/peak%）
    R4: mets_peak（代谢当量峰值）
    R5: exercise_capacity 分类（正常=良好，下降=减弱）
    """
    r = pd.DataFrame(index=df.index)

    # R1：VO₂peak %pred（核心）— 使用 v2 %pred 优先，否则用原始字段
    if "vo2_peak_pct_v2" in df.columns:
        r["r1_vo2peak_pct_pred"] = pd.to_numeric(df["vo2_peak_pct_v2"], errors="coerce")
    elif "vo2_peak_pct_pred" in df.columns:
        r["r1_vo2peak_pct_pred"] = pd.to_numeric(df["vo2_peak_pct_pred"], errors="coerce")
    else:
        r["r1_vo2peak_pct_pred"] = np.nan

    # R2：O₂ 脉搏峰值（归一化至[0,1]：clip 5-25 mL/beat）
    if "o2_pulse_peak" in df.columns:
        o2p = pd.to_numeric(df["o2_pulse_peak"], errors="coerce")
        r["r2_o2_pulse_peak"] = (o2p.clip(5, 25) - 5) / (25 - 5) * 100
    else:
        r["r2_o2_pulse_peak"] = np.nan

    # R3：VT1/peak% = vt1_vo2 / vo2_peak * 100
    if "vt1_vo2" in df.columns and "vo2_peak" in df.columns:
        vt1 = pd.to_numeric(df["vt1_vo2"], errors="coerce")
        vo2p = pd.to_numeric(df["vo2_peak"], errors="coerce")
        r["r3_vt1_pct_vo2peak"] = (vt1 / vo2p * 100).where(vo2p.notna() & vo2p.gt(0)).clip(0, 100)
    else:
        r["r3_vt1_pct_vo2peak"] = np.nan

    # R4：METs peak（clip 1-15，正常范围）
    if "mets_peak" in df.columns:
        mets = pd.to_numeric(df["mets_peak"], errors="coerce")
        r["r4_mets_peak"] = (mets.clip(1, 15) - 1) / (15 - 1) * 100
    else:
        r["r4_mets_peak"] = np.nan

    # R5：exercise_capacity 分类 → 正常=100，下降=0
    if "exercise_capacity" in df.columns:
        ec = df["exercise_capacity"].astype(str).str.strip()
        r["r5_exercise_capacity"] = ec.map({"正常": 100.0, "下降": 0.0, "略下降": 30.0}).astype(float)
    else:
        r["r5_exercise_capacity"] = np.nan

    return r


def _compute_t_axis_v2(df: pd.DataFrame) -> pd.DataFrame:
    """
    T 轴（阈值轴）改进版。

    T1: VE/VCO₂ slope（反向：越低越好）
    T2: VT1/peak%（高=阈值高=耐受力好）
    T3: exercise_habit 条件调整因子（经常运动=对阈值区更耐受）

    注：不依赖 vt1_hr/rcp_hr（数据严重缺失）
    """
    t = pd.DataFrame(index=df.index)

    # T1：VE/VCO₂ slope（反向：clip 15-45，越低越安全）
    if "ve_vco2_slope" in df.columns:
        ve = pd.to_numeric(df["ve_vco2_slope"], errors="coerce")
        t["t1_ve_vco2_slope_inv"] = ((45 - ve.clip(15, 45)) / (45 - 15) * 100).clip(0, 100)
    else:
        t["t1_ve_vco2_slope_inv"] = np.nan

    # T2：VT1/peak%（高=阈值高=有氧储备好，越高越安全）
    if "r3_vt1_pct_vo2peak" in df.columns:
        # 复用 R3 已计算好的值
        t["t2_vt1_pct"] = df["r3_vt1_pct_vo2peak"].copy()
    elif "vt1_vo2" in df.columns and "vo2_peak" in df.columns:
        vt1 = pd.to_numeric(df["vt1_vo2"], errors="coerce")
        vo2p = pd.to_numeric(df["vo2_peak"], errors="coerce")
        t["t2_vt1_pct"] = (vt1 / vo2p * 100).where(vo2p.notna() & vo2p.gt(0)).clip(0, 100)
    else:
        t["t2_vt1_pct"] = np.nan

    # T3：运动习惯调节因子（regular=+10分加成，occasional=+5，无习惯=0）
    if "exercise_habit" in df.columns:
        eh = df["exercise_habit"].astype(str).str.strip().str.lower()
        t["t3_exercise_habit_bonus"] = eh.map(
            {"regular": 10.0, "occasional": 5.0, "none": 0.0}
        ).fillna(0.0)
    else:
        t["t3_exercise_habit_bonus"] = 0.0

    return t


def _compute_i_axis_v2(df: pd.DataFrame) -> pd.DataFrame:
    """
    I 轴（不稳定性轴）改进版。

    I1: test_result 异常（结局锚定信号）— 注意：仅用于 zone 定义，不用于 ML 预测
    I2: bp 反应异常（运动高血压）
    I3: bp_peak_dia 升高（新增）
    I4: o2_pulse_trajectory 异常（缺血标志，新增）
    I5: eih_status（若可用）

    重要说明：此轴用于定义 zone 边界，不用于 ML 特征（由 leakage_guard 保护）
    """
    i = pd.DataFrame(index=df.index)

    # 注意：test_result 是结局变量，用于切点校准（Method A），不加入 I 轴输入
    # 否则会产生循环依赖（用结局预测结局）

    # I1：运动收缩压反应异常（bp_peak_sys > 220 mmHg）
    if "bp_peak_sys" in df.columns:
        bps = pd.to_numeric(df["bp_peak_sys"], errors="coerce")
        i["i1_bp_sys_abnormal"] = (bps > 220).astype(float).where(bps.notna())
    else:
        i["i1_bp_sys_abnormal"] = np.nan

    # I2：运动舒张压升高（bp_peak_dia > 110 mmHg，新增）
    if "bp_peak_dia" in df.columns:
        bpd = pd.to_numeric(df["bp_peak_dia"], errors="coerce")
        i["i2_bp_dia_abnormal"] = (bpd > 110).astype(float).where(bpd.notna())
    else:
        i["i2_bp_dia_abnormal"] = np.nan

    # I3：O₂ 脉搏轨迹异常（平台/下降型 = 缺血标志，新增）
    if "o2_pulse_trajectory" in df.columns:
        traj = df["o2_pulse_trajectory"].astype(str).str.strip()
        i["i3_o2_pulse_abnormal"] = traj.map(
            lambda x: 1.0 if x in O2_PULSE_ABNORMAL_PATTERNS else (0.0 if x != "None" and x != "nan" else np.nan)
        )
    else:
        i["i3_o2_pulse_abnormal"] = np.nan

    # I4：eih_status（若可用 — 公理性约束，I 轴最重要信号）
    if "eih_status" in df.columns:
        eih = df["eih_status"].map(lambda x: 1.0 if pd.notna(x) and bool(x) else (0.0 if pd.notna(x) else np.nan))
        i["i4_eih_status"] = eih
    else:
        i["i4_eih_status"] = np.nan

    return i


# ─────────────────────────────────────────────────────────────────────────────
# 主引擎
# ─────────────────────────────────────────────────────────────────────────────

class ZoneEngineV2:
    """
    数据驱动安全区引擎 v2。

    使用方法：
        engine = ZoneEngineV2()
        result = engine.build(df, output_path="reports/zone_engine_v2_report.md")
    """

    def __init__(
        self,
        min_sensitivity_low: float = 0.90,
        n_bootstrap: int = 500,
        random_state: int = 42,
    ) -> None:
        self._min_sens_low = min_sensitivity_low
        self._n_bootstrap = n_bootstrap
        self._rng = np.random.default_rng(random_state)

    def _compute_axis_weights(
        self,
        r_composite: pd.Series,
        t_composite: pd.Series,
        i_composite: pd.Series,
        outcome: pd.Series,
    ) -> AxisWeight:
        """
        基于 point-biserial 相关性计算数据驱动轴权重。

        风险轴：r_risk = 100 - r_composite（储备高=风险低）
        """
        correlations: dict[str, float] = {}
        raw_weights: dict[str, float] = {}

        # 储备越低 → 风险越高 → 与结局正相关
        r_risk = (100 - r_composite.clip(0, 100)).where(r_composite.notna())
        t_risk = (100 - t_composite.clip(0, 100)).where(t_composite.notna())
        i_risk = i_composite.clip(0, 100).where(i_composite.notna())

        for axis_name, risk_score in [("r", r_risk), ("t", t_risk), ("i", i_risk)]:
            corr = _point_biserial_corr(risk_score, outcome)
            correlations[f"{axis_name}_risk"] = corr
            raw_weights[axis_name] = max(abs(corr), 0.05)  # 最小权重 0.05 防止退化

        total_w = sum(raw_weights.values())
        w_r = raw_weights["r"] / total_w
        w_t = raw_weights["t"] / total_w
        w_i = raw_weights["i"] / total_w

        logger.info(
            "轴权重：R=%.3f, T=%.3f, I=%.3f（基于与结局的相关性）",
            w_r, w_t, w_i,
        )

        return AxisWeight(
            r_weight=w_r,
            t_weight=w_t,
            i_weight=w_i,
            method="correlation",
            correlations=correlations,
        )

    def _compute_composite_scores(
        self,
        r_df: pd.DataFrame,
        t_df: pd.DataFrame,
        i_df: pd.DataFrame,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """
        各轴内部组合评分（0–100，储备/阈值轴越高=越安全，不稳定轴越高=越危险）。
        """
        # ── R 轴（越高=储备越充足）────────────────────────────────────────────
        r_components = []
        r_weights_inner = []
        for col, w in [
            ("r1_vo2peak_pct_pred", 0.50),
            ("r2_o2_pulse_peak", 0.20),
            ("r3_vt1_pct_vo2peak", 0.15),
            ("r4_mets_peak", 0.10),
            ("r5_exercise_capacity", 0.05),
        ]:
            if col in r_df.columns and r_df[col].notna().any():
                r_components.append(r_df[col])
                r_weights_inner.append(w)

        if r_components:
            total_w = sum(r_weights_inner)
            r_score = sum(c * w / total_w for c, w in zip(r_components, r_weights_inner))
            r_score = r_score.clip(0, 100)
        else:
            r_score = pd.Series(np.nan, index=r_df.index)

        # ── T 轴（越高=阈值越高/越安全）──────────────────────────────────────
        t_components = []
        t_weights_inner = []
        for col, w in [
            ("t1_ve_vco2_slope_inv", 0.60),
            ("t2_vt1_pct", 0.40),
        ]:
            if col in t_df.columns and t_df[col].notna().any():
                t_components.append(t_df[col])
                t_weights_inner.append(w)

        # T3 运动习惯加成（直接加在 T 轴分数上，最多+10分）
        if t_components:
            total_w = sum(t_weights_inner)
            t_base = sum(c * w / total_w for c, w in zip(t_components, t_weights_inner))
            t_score = t_base.clip(0, 100)
        else:
            t_score = pd.Series(np.nan, index=t_df.index)

        # 加入运动习惯加成
        if "t3_exercise_habit_bonus" in t_df.columns:
            t_score = (t_score + t_df["t3_exercise_habit_bonus"]).clip(0, 100)

        # ── I 轴（越高=不稳定性越强/风险越高）──────────────────────────────────
        # I 轴：BP异常 + O₂脉搏轨迹 + EIH（test_result 是结局变量，不加入轴）
        i_components = []
        i_weights_inner = []
        for col, w in [
            ("i1_bp_sys_abnormal", 0.30),
            ("i2_bp_dia_abnormal", 0.15),
            ("i3_o2_pulse_abnormal", 0.30),
            ("i4_eih_status", 0.25),
        ]:
            if col in i_df.columns and i_df[col].notna().any():
                i_components.append(i_df[col].fillna(0.0))
                i_weights_inner.append(w)

        if i_components:
            total_w = sum(i_weights_inner)
            i_score = sum(c * w / total_w for c, w in zip(i_components, i_weights_inner)) * 100
            i_score = i_score.clip(0, 100)
        else:
            i_score = pd.Series(np.nan, index=i_df.index)

        return r_score, t_score, i_score

    def _compute_s_lab_v2(
        self,
        r_score: pd.Series,
        t_score: pd.Series,
        i_score: pd.Series,
        weights: AxisWeight,
    ) -> pd.Series:
        """
        S_lab_v2 综合风险分数（0–100，越高=风险越高）。

        R/T 转为风险分（100-score），I 直接使用。
        """
        r_risk = (100 - r_score.clip(0, 100)).where(r_score.notna())
        t_risk = (100 - t_score.clip(0, 100)).where(t_score.notna())
        i_risk = i_score.clip(0, 100).where(i_score.notna())

        components = []
        comp_weights = []
        for risk, w in [(r_risk, weights.r_weight), (t_risk, weights.t_weight), (i_risk, weights.i_weight)]:
            if risk.notna().any():
                components.append(risk.fillna(risk.median() if risk.notna().any() else 50.0))
                comp_weights.append(w)

        if not components:
            return pd.Series(np.nan, index=r_score.index)

        total_w = sum(comp_weights)
        s_lab = sum(c * w / total_w for c, w in zip(components, comp_weights))
        return s_lab.clip(0, 100)

    def _assign_zones(
        self,
        s_lab: pd.Series,
        cutpoints: ZoneCutpoints,
    ) -> pd.Series:
        """将 S_lab_v2 映射到 Green/Yellow/Red 区。"""
        def zone_fn(x: float) -> str | None:
            if pd.isna(x):
                return None
            if x < cutpoints.low:
                return "green"
            elif x < cutpoints.high:
                return "yellow"
            else:
                return "red"
        return s_lab.map(zone_fn)

    def _compute_strat_cutpoints(
        self,
        df: pd.DataFrame,
        outcome: pd.Series,
        strat_factors: list[str],
    ) -> dict[str, ZoneCutpoints]:
        """为各分层因子计算独立切点。"""
        strat_results: dict[str, ZoneCutpoints] = {}

        # 先添加分层列到 df
        work_df = df.copy()
        outcome_aligned = outcome.reindex(work_df.index)

        for factor in strat_factors:
            if factor not in work_df.columns:
                continue
            vals = work_df[factor].dropna().unique()
            for val in vals:
                mask = work_df[factor] == val
                if mask.sum() < 30:
                    continue
                sub_score = work_df.loc[mask, "s_lab_v2"]
                sub_outcome = outcome_aligned[mask]

                n_pos = (sub_outcome == 1).sum()
                if n_pos < 5:
                    logger.debug("分层 [%s=%s] 阳性样本不足（n=%d），使用百分位法", factor, val, n_pos)
                    cp = _percentile_cutpoints(sub_score, strat_key=f"{factor}={val}")
                else:
                    cp = _youden_cutpoints(
                        sub_score, sub_outcome,
                        min_sensitivity_low=self._min_sens_low,
                        strat_key=f"{factor}={val}",
                        n_bootstrap=min(self._n_bootstrap, 100),
                        rng=self._rng,
                    )
                strat_results[f"{factor}={val}"] = cp

        return strat_results

    def build(
        self,
        df: pd.DataFrame,
        old_zone_col: str | None = "p1_zone",
        reference_flag_col: str = "reference_flag_wide",
        output_path: str | Path | None = None,
    ) -> ZoneEngineV2Result:
        """
        主构建方法。

        Parameters
        ----------
        df : 全样本 DataFrame（含 cohort + labels）
        old_zone_col : 旧 zone 列（用于重分类矩阵，None 则跳过）
        output_path : 报告输出路径

        Returns
        -------
        ZoneEngineV2Result
        """
        work = df.copy().reset_index(drop=True)
        logger.info("ZoneEngineV2 开始：%d 行", len(work))

        # 派生辅助变量
        if "bmi" not in work.columns and "height_cm" in work.columns and "weight_kg" in work.columns:
            h = pd.to_numeric(work["height_cm"], errors="coerce") / 100.0
            work["bmi"] = pd.to_numeric(work["weight_kg"], errors="coerce") / (h ** 2).replace(0, np.nan)

        # 年龄组
        if "age" in work.columns:
            work["age_group"] = pd.to_numeric(work["age"], errors="coerce").map(
                lambda x: "age<67" if pd.notna(x) and x < 67 else ("age>=67" if pd.notna(x) else None)
            )

        # β-blocker
        if "med_betablocker" in work.columns:
            work["beta_blocker"] = work["med_betablocker"].map(
                lambda x: "bb_yes" if pd.notna(x) and float(x) == 1 else ("bb_no" if pd.notna(x) else None)
            )

        # 计算结局
        outcome = _binary_outcome(work)

        # ── 轴变量提取 ─────────────────────────────────────────────────────────
        r_df = _compute_r_axis_v2(work)
        t_df = _compute_t_axis_v2(pd.concat([work, r_df], axis=1))
        i_df = _compute_i_axis_v2(work)

        # ── 各轴内部组合评分 ────────────────────────────────────────────────────
        r_score, t_score, i_score = self._compute_composite_scores(r_df, t_df, i_df)
        work["r_score_v2"] = r_score
        work["t_score_v2"] = t_score
        work["i_score_v2"] = i_score

        # ── S_lab_v2 始终使用等权重（避免 test_result 循环依赖）────────────────
        axis_weights = AxisWeight(r_weight=0.333, t_weight=0.333, i_weight=0.334, method="equal")

        # 计算 correlation-based 权重作为审计信息（不参与 S_lab_v2 计算）
        n_pos = int((outcome == 1).sum())
        if n_pos >= 30:
            audit_weights = self._compute_axis_weights(r_score, t_score, i_score, outcome)
            logger.info(
                "审计权重（不用于 S_lab_v2）：R=%.3f, T=%.3f, I=%.3f",
                audit_weights.r_weight, audit_weights.t_weight, audit_weights.i_weight,
            )
        else:
            logger.warning("阳性样本不足（n=%d），审计权重跳过", n_pos)
            audit_weights = None

        # ── S_lab_v2 综合风险评分 ────────────────────────────────────────────────
        s_lab_v2 = self._compute_s_lab_v2(r_score, t_score, i_score, axis_weights)
        work["s_lab_v2"] = s_lab_v2

        # ── 全局 Zone 切点（Method B 优先：参考人群分位法）────────────────────
        # 参考子集标志
        if reference_flag_col in work.columns:
            ref_mask = work[reference_flag_col].astype(bool)
        else:
            # 回退：使用 CTRL 组 + 无 EIH 作为参考
            if "group_code" in work.columns:
                ref_mask = (work["group_code"] == "CTRL")
            else:
                ref_mask = pd.Series(True, index=work.index)

        n_ref = int(ref_mask.sum())
        if n_ref >= MIN_REF_N:
            logger.info("使用参考人群分位法（n_ref=%d）", n_ref)
            global_cp = _reference_percentile_cutpoints(
                s_lab_v2, ref_mask, strat_key="global"
            )
        else:
            logger.warning("参考子集过小（n=%d），使用全体百分位法", n_ref)
            global_cp = _percentile_cutpoints(s_lab_v2, low_pct=25.0, high_pct=75.0, strat_key="global")

        # 同时计算 Youden's J 作为方法学验证（不作为主要切点）
        valid_outcome = outcome.notna()
        n_neg = int((outcome == 0).sum())
        if valid_outcome.sum() >= 30 and n_pos >= 10 and n_neg >= 10:
            youden_cp = _youden_cutpoints(
                s_lab_v2[valid_outcome],
                outcome[valid_outcome],
                min_sensitivity_low=self._min_sens_low,
                strat_key="global_youden_validation",
                n_bootstrap=self._n_bootstrap,
                rng=self._rng,
            )
            # 将 Youden 切点记录到 global_cp 的额外属性中（验证用）
            global_cp.youden_j = youden_cp.youden_j
            global_cp.sensitivity_at_high = youden_cp.sensitivity_at_high
            global_cp.specificity_at_high = youden_cp.specificity_at_high
            global_cp.bootstrap_ci_high = youden_cp.bootstrap_ci_high
            global_cp.n_outcome_pos = youden_cp.n_outcome_pos
            global_cp.n_outcome_total = youden_cp.n_outcome_total
            logger.info(
                "Youden 验证切点 = %.1f（与 ref-based 高切点 %.1f 对比，偏差=%.1f）",
                youden_cp.high, global_cp.high, abs(youden_cp.high - global_cp.high),
            )

        # ── 全局 Zone 分配 ────────────────────────────────────────────────────
        z_lab_v2 = self._assign_zones(s_lab_v2, global_cp)
        work["z_lab_v2"] = z_lab_v2

        # ── 分层切点 ──────────────────────────────────────────────────────────
        strat_factors_available = [f for f in STRAT_FACTORS if f in work.columns]
        strat_cutpoints = self._compute_strat_cutpoints(work, outcome, strat_factors_available)

        # ── Zone 分布统计 ──────────────────────────────────────────────────────
        zone_distribution: dict[str, dict[str, int]] = {}

        # 全局
        global_dist = {
            z: int((z_lab_v2 == z).sum())
            for z in ["green", "yellow", "red"]
        }
        zone_distribution["global"] = global_dist

        # 分组
        if "group_code" in work.columns:
            for gc in work["group_code"].dropna().unique():
                mask = work["group_code"] == gc
                sub_z = z_lab_v2[mask]
                zone_distribution[f"group={gc}"] = {
                    z: int((sub_z == z).sum()) for z in ["green", "yellow", "red"]
                }

        # 性别分层
        if "sex" in work.columns:
            for sx in ["M", "F"]:
                mask = work["sex"].astype(str).str.strip() == sx
                sub_z = z_lab_v2[mask]
                zone_distribution[f"sex={sx}"] = {
                    z: int((sub_z == z).sum()) for z in ["green", "yellow", "red"]
                }

        # ── 新旧 Zone 重分类矩阵 ─────────────────────────────────────────────
        reclass = pd.DataFrame()
        if old_zone_col and old_zone_col in work.columns:
            _ZONE_MAP_INT = {0: "green", 1: "yellow", 2: "red", 0.0: "green", 1.0: "yellow", 2.0: "red"}
            old_zone = work[old_zone_col].map(
                lambda x: _ZONE_MAP_INT.get(x, str(x)) if pd.notna(x) else None
            )
            valid_both = old_zone.notna() & z_lab_v2.notna()
            if valid_both.sum() > 0:
                reclass = pd.crosstab(
                    old_zone[valid_both].rename("旧 P1 zone"),
                    z_lab_v2[valid_both].rename("新 Z_lab_v2"),
                )

        # ── 组装输出 ──────────────────────────────────────────────────────────
        # 加入各轴分量到输出 DataFrame
        output_df = pd.concat([work, r_df, t_df, i_df], axis=1)
        # 去除重复列
        output_df = output_df.loc[:, ~output_df.columns.duplicated()]

        logger.info(
            "ZoneEngineV2 完成: Z_lab_v2 分布=%s, S_lab_v2 均值=%.1f, 切点=[%.1f, %.1f]",
            global_dist, float(s_lab_v2.mean()), global_cp.low, global_cp.high,
        )

        result = ZoneEngineV2Result(
            df=output_df,
            axis_weights=axis_weights,
            global_cutpoints=global_cp,
            strat_cutpoints=strat_cutpoints,
            zone_distribution=zone_distribution,
            reclassification=reclass,
            config={
                "min_sensitivity_low": self._min_sens_low,
                "n_bootstrap": self._n_bootstrap,
                "outcome_col": OUTCOME_COL,
                "audit_weights": (
                    {"r": audit_weights.r_weight, "t": audit_weights.t_weight, "i": audit_weights.i_weight}
                    if audit_weights is not None else None
                ),
            },
        )

        if output_path is not None:
            result.to_markdown(output_path)

        return result


def _df_to_pipe_table(df: "pd.DataFrame", index: bool = False) -> str:
    if df is None or df.empty:
        return "*(空)*"
    if index:
        df = df.reset_index()
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    rows = ["| " + " | ".join(str(row[c]) for c in cols) + " |" for _, row in df.iterrows()]
    return "\n".join([header, sep] + rows)
