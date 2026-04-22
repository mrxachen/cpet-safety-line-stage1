"""
anomaly_score.py — Phase G Method 2：多变量异常评分（Mahalanobis 距离）

核心创新：
  不逐变量比较 %pred，而是计算患者在多变量 CPET 空间中相对参考人群的
  Mahalanobis 距离 D²，捕获变量间协方差信息。

为什么优于单变量 %pred：
  - 高 VO₂peak + 高 HRpeak = 正常（良好运动反应）
  - 低 VO₂peak + 高 HRpeak = 异常（变时功能不全）
  - 单变量 %pred 无法区分；Mahalanobis 距离天然捕获协方差

理论基础：
  D² = (x - μ)ᵀ Σ⁻¹ (x - μ)
  在多变量正态参考人群中，D² 服从 χ²(k) 分布（k = 变量数），
  提供自然的概率解释：D² > χ²(k, 0.95) → 患者处于参考人群 95 百分位以上。

配置文件：configs/stats/anomaly_config.yaml
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)

# ── 默认配置 ──────────────────────────────────────────────────────────────────
_DEFAULT_VARIABLES = ["vo2_peak", "hr_peak", "o2_pulse_peak", "oues", "mets_peak"]
_DEFAULT_GREEN_YELLOW_PCT = 75
_DEFAULT_YELLOW_RED_PCT = 95
_MIN_REF_N = 30


@dataclass
class AnomalyModelParams:
    """Mahalanobis 模型参数（从参考子集拟合）。"""
    mu: np.ndarray                      # 均值向量（k,）
    sigma_inv: np.ndarray               # 逆协方差矩阵（k×k）
    variable_names: list[str]           # 变量名列表
    n_reference: int                    # 参考子集样本量
    stratum_label: str = "global"       # 分层标识
    # D² 在参考子集中的分位数（用于切点）
    d2_p75_ref: float = float("nan")
    d2_p95_ref: float = float("nan")
    # χ² 理论分位数
    d2_chi2_p75: float = float("nan")
    d2_chi2_p95: float = float("nan")

    def to_dict(self) -> dict:
        return {
            "variable_names": self.variable_names,
            "n_reference": self.n_reference,
            "stratum_label": self.stratum_label,
            "d2_p75_ref": self.d2_p75_ref,
            "d2_p95_ref": self.d2_p95_ref,
            "d2_chi2_p75": self.d2_chi2_p75,
            "d2_chi2_p95": self.d2_chi2_p95,
        }


@dataclass
class AnomalyScoreResult:
    """多变量异常评分结果。"""
    scores: pd.DataFrame = field(default_factory=pd.DataFrame)
    # scores 列：subject_id, mahal_d2, mahal_pvalue, mahal_pct_ref, anomaly_zone
    params: Optional[AnomalyModelParams] = None
    zone_cutpoints: dict[str, float] = field(default_factory=dict)
    zone_distribution: dict = field(default_factory=dict)
    # 与 test_result 的相关性（若提供 test_result）
    correlation_with_outcome: Optional[float] = None
    n_valid: int = 0
    n_missing_excluded: int = 0

    def to_summary_dict(self) -> dict:
        return {
            "n_valid": self.n_valid,
            "n_missing_excluded": self.n_missing_excluded,
            "zone_cutpoints": self.zone_cutpoints,
            "zone_distribution": self.zone_distribution,
            "correlation_with_outcome": self.correlation_with_outcome,
            "params": self.params.to_dict() if self.params else None,
        }


def _select_valid_variables(
    df_ref: pd.DataFrame,
    variables: list[str],
    max_missing_pct: float = 0.50,
) -> list[str]:
    """选择缺失率低于阈值的变量子集。"""
    valid_vars = []
    for v in variables:
        if v not in df_ref.columns:
            logger.warning("变量 '%s' 不在 DataFrame 中，跳过", v)
            continue
        missing_pct = df_ref[v].isna().mean()
        if missing_pct > max_missing_pct:
            logger.warning("变量 '%s' 缺失率 %.1f%% 超过阈值，排除", v, missing_pct * 100)
        else:
            valid_vars.append(v)
    return valid_vars


def fit_anomaly_model(
    df_reference: pd.DataFrame,
    variables: Optional[list[str]] = None,
    stratum_label: str = "global",
) -> AnomalyModelParams:
    """
    在参考子集上拟合 Mahalanobis 模型。

    参数：
        df_reference: 参考人群 DataFrame（已过滤 reference_flag）
        variables: CPET 变量列表（默认 _DEFAULT_VARIABLES）
        stratum_label: 分层标识（用于多层模型）

    返回：
        AnomalyModelParams
    """
    if variables is None:
        variables = _DEFAULT_VARIABLES

    # 选择有效变量（过滤缺失率过高的列）
    valid_vars = _select_valid_variables(df_reference, variables)
    if len(valid_vars) < 2:
        raise ValueError(f"有效变量不足（{len(valid_vars)} < 2），无法计算 Mahalanobis 距离")

    # 提取数值矩阵，中位数填充 NaN
    X_ref = df_reference[valid_vars].apply(pd.to_numeric, errors="coerce")
    medians = X_ref.median()
    X_ref_filled = X_ref.fillna(medians)

    # 至少需要 k+1 个样本
    n = len(X_ref_filled)
    k = len(valid_vars)
    if n < max(_MIN_REF_N, k + 1):
        raise ValueError(
            f"参考子集样本量不足：需要 ≥{max(_MIN_REF_N, k+1)}，实际 {n}"
        )

    # 计算均值向量和逆协方差矩阵
    mu = X_ref_filled.values.mean(axis=0)
    Sigma = np.cov(X_ref_filled.values.T)

    # 处理协方差矩阵奇异性（正则化）
    try:
        Sigma_inv = np.linalg.inv(Sigma)
    except np.linalg.LinAlgError:
        # 添加小的正则化项
        Sigma_reg = Sigma + np.eye(k) * 1e-6 * np.trace(Sigma) / k
        Sigma_inv = np.linalg.inv(Sigma_reg)
        logger.warning("协方差矩阵奇异，已添加正则化项")

    # 计算参考子集的 D² 分布（用于数据驱动切点）
    d2_ref = _compute_mahal_d2_batch(X_ref_filled.values, mu, Sigma_inv)

    # χ² 理论分位数
    d2_chi2_p75 = float(scipy_stats.chi2.ppf(0.75, df=k))
    d2_chi2_p95 = float(scipy_stats.chi2.ppf(0.95, df=k))

    return AnomalyModelParams(
        mu=mu,
        sigma_inv=Sigma_inv,
        variable_names=valid_vars,
        n_reference=n,
        stratum_label=stratum_label,
        d2_p75_ref=float(np.percentile(d2_ref, 75)),
        d2_p95_ref=float(np.percentile(d2_ref, 95)),
        d2_chi2_p75=d2_chi2_p75,
        d2_chi2_p95=d2_chi2_p95,
    )


def _compute_mahal_d2_batch(
    X: np.ndarray,
    mu: np.ndarray,
    Sigma_inv: np.ndarray,
) -> np.ndarray:
    """
    批量计算 Mahalanobis D²。

    D²_i = (x_i - μ)ᵀ Σ⁻¹ (x_i - μ)

    参数：
        X: 数据矩阵（n × k）
        mu: 均值向量（k,）
        Sigma_inv: 逆协方差矩阵（k × k）

    返回：
        D² 数组（n,）
    """
    delta = X - mu  # (n, k)
    # D²_i = delta_i @ Sigma_inv @ delta_i.T（对角线元素）
    d2 = np.sum(delta @ Sigma_inv * delta, axis=1)
    return np.maximum(d2, 0.0)  # 数值稳定性


def compute_anomaly_scores(
    df: pd.DataFrame,
    params: AnomalyModelParams,
    cutpoint_method: str = "percentile_reference",
    green_yellow_pct: float = _DEFAULT_GREEN_YELLOW_PCT,
    yellow_red_pct: float = _DEFAULT_YELLOW_RED_PCT,
    outcome_col: Optional[str] = None,
) -> AnomalyScoreResult:
    """
    计算每个患者的 Mahalanobis 异常评分并分配安全区。

    参数：
        df: 包含 CPET 变量的 DataFrame
        params: 从参考子集拟合的模型参数
        cutpoint_method: "percentile_reference"（参考子集分位）或 "chi2_theoretical"（理论分位）
        green_yellow_pct: Green/Yellow 界的参考子集百分位（默认 P75）
        yellow_red_pct: Yellow/Red 界的参考子集百分位（默认 P95）
        outcome_col: test_result 列名（可选，用于计算相关性）

    返回：
        AnomalyScoreResult
    """
    result = AnomalyScoreResult(params=params)
    valid_vars = params.variable_names
    k = len(valid_vars)

    # ── 提取和填充特征 ────────────────────────────────────────────────────────
    X_raw = df[valid_vars].apply(pd.to_numeric, errors="coerce")
    missing_rows = X_raw.isna().all(axis=1)
    result.n_missing_excluded = int(missing_rows.sum())

    # 用参考子集均值填充缺失值（params.mu 对应各变量的参考均值）
    X_filled = X_raw.copy()
    for i, v in enumerate(valid_vars):
        X_filled[v] = X_filled[v].fillna(params.mu[i])

    result.n_valid = len(df) - result.n_missing_excluded

    # ── 计算 Mahalanobis D² ───────────────────────────────────────────────────
    d2_values = _compute_mahal_d2_batch(X_filled.values, params.mu, params.sigma_inv)
    # χ² 检验 p 值（概率解释）
    pvalues = 1.0 - scipy_stats.chi2.cdf(d2_values, df=k)
    # 在参考子集分布中的近似百分位
    d2_ref_p75 = params.d2_p75_ref
    d2_ref_p95 = params.d2_p95_ref

    # ── 安全区切点 ────────────────────────────────────────────────────────────
    if cutpoint_method == "percentile_reference":
        low_cut = d2_ref_p75 if not np.isnan(d2_ref_p75) else params.d2_chi2_p75
        high_cut = d2_ref_p95 if not np.isnan(d2_ref_p95) else params.d2_chi2_p95
    else:  # chi2_theoretical
        low_cut = params.d2_chi2_p75
        high_cut = params.d2_chi2_p95

    result.zone_cutpoints = {
        "green_yellow": float(low_cut),
        "yellow_red": float(high_cut),
        "method": cutpoint_method,
        "d2_chi2_p75": params.d2_chi2_p75,
        "d2_chi2_p95": params.d2_chi2_p95,
    }

    # ── 分配安全区 ────────────────────────────────────────────────────────────
    zones = np.where(
        d2_values < low_cut, "green",
        np.where(d2_values < high_cut, "yellow", "red")
    )

    # ── 构建结果 DataFrame ────────────────────────────────────────────────────
    scores_df = pd.DataFrame(
        {
            "mahal_d2": d2_values,
            "mahal_pvalue": pvalues,
            "anomaly_zone": zones,
        },
        index=df.index,
    )
    result.scores = scores_df

    # ── 安全区分布统计 ────────────────────────────────────────────────────────
    total = len(zones)
    for z in ["green", "yellow", "red"]:
        mask = zones == z
        n = int(mask.sum())
        result.zone_distribution[z] = {
            "n": n,
            "pct": round(n / total * 100, 1) if total > 0 else 0.0,
        }
        if outcome_col is not None and outcome_col in df.columns:
            # 计算各区阳性率
            pos_vals = {"阳性", "可疑阳性"}
            outcome_in_zone = df.loc[scores_df.index[mask], outcome_col]
            pos_n = int(outcome_in_zone.isin(pos_vals).sum())
            result.zone_distribution[z]["positive_rate"] = (
                round(pos_n / n * 100, 1) if n > 0 else 0.0
            )

    # ── 与 test_result 的相关性 ───────────────────────────────────────────────
    if outcome_col is not None and outcome_col in df.columns:
        pos_vals = {"阳性", "可疑阳性"}
        outcome_binary = df[outcome_col].isin(pos_vals).astype(float)
        valid_for_corr = outcome_binary.notna() & ~missing_rows
        if valid_for_corr.sum() > 10:
            corr, _ = scipy_stats.pointbiserialr(
                outcome_binary[valid_for_corr].values,
                d2_values[valid_for_corr.values],
            )
            result.correlation_with_outcome = float(corr)
            logger.info(
                "Mahalanobis D² vs test_result 相关性: r=%.3f (n=%d)",
                corr, valid_for_corr.sum(),
            )

    return result


def generate_anomaly_report(result: AnomalyScoreResult) -> str:
    """生成 Markdown 格式的多变量异常评分报告。"""
    lines = [
        "# 多变量异常评分报告（Method 2 / Phase G）",
        "",
        "## 方法概述",
        "",
        "基于参考人群的 Mahalanobis 距离 D² 捕获多变量 CPET 空间中的异常模式，",
        "克服单变量 %pred 无法处理变量间协方差的局限。",
        "",
        f"D² ~ χ²(k) 分布（k = 变量数），提供概率解释。",
        "",
    ]

    if result.params is not None:
        p = result.params
        lines += [
            "## 参考模型参数",
            "",
            f"| 参数 | 值 |",
            f"|---|---|",
            f"| 变量数 k | {len(p.variable_names)} |",
            f"| 变量列表 | {', '.join(p.variable_names)} |",
            f"| 参考子集 N | {p.n_reference} |",
            f"| D²-P75（参考子集经验） | {p.d2_p75_ref:.3f} |",
            f"| D²-P95（参考子集经验） | {p.d2_p95_ref:.3f} |",
            f"| D²-P75（χ² 理论） | {p.d2_chi2_p75:.3f} |",
            f"| D²-P95（χ² 理论） | {p.d2_chi2_p95:.3f} |",
            "",
        ]

    lines += [
        "## 安全区切点",
        "",
        f"| 参数 | 值 |",
        f"|---|---|",
        f"| 方法 | {result.zone_cutpoints.get('method', 'N/A')} |",
        f"| Green/Yellow 界 D² | {result.zone_cutpoints.get('green_yellow', float('nan')):.3f} |",
        f"| Yellow/Red 界 D² | {result.zone_cutpoints.get('yellow_red', float('nan')):.3f} |",
        "",
        "## 安全区分布",
        "",
        "| 区 | N | 占比 | 阳性率 |",
        "|---|---|---|---|",
    ]

    for z in ["green", "yellow", "red"]:
        info = result.zone_distribution.get(z, {})
        n = info.get("n", 0)
        pct = info.get("pct", 0)
        pos_rate = info.get("positive_rate", None)
        pos_str = f"{pos_rate:.1f}%" if pos_rate is not None else "N/A"
        lines.append(f"| {z.capitalize()} | {n} | {pct:.1f}% | {pos_str} |")

    lines += [""]

    if result.correlation_with_outcome is not None:
        lines += [
            "## D² 与 test_result 相关性",
            "",
            f"Point-biserial r = **{result.correlation_with_outcome:.3f}**",
            f"（有效样本 N = {result.n_valid}）",
            "",
        ]

    lines += [
        "## 样本量",
        "",
        f"- 有效样本: {result.n_valid}",
        f"- 因全缺失排除: {result.n_missing_excluded}",
    ]

    return "\n".join(lines)


def run_anomaly_scoring(
    df: pd.DataFrame,
    config_path: str | Path = "configs/stats/anomaly_config.yaml",
    reference_flag_col: str = "reference_flag_wide",
    outcome_col: Optional[str] = "test_result",
) -> AnomalyScoreResult:
    """
    端到端运行异常评分管线（拟合参考模型 + 计算全局评分）。

    参数：
        df: 包含所有 CPET 变量的 DataFrame
        config_path: 配置文件路径
        reference_flag_col: 参考人群标志列名
        outcome_col: test_result 列名（可选）

    返回：
        AnomalyScoreResult
    """
    import yaml
    cfg_path = Path(config_path)
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        logger.warning("配置文件不存在: %s，使用默认配置", config_path)
        cfg = {}

    variables = cfg.get("variables", {}).get("primary", _DEFAULT_VARIABLES)
    ref_col = cfg.get("reference", {}).get("flag_column", reference_flag_col)
    min_n = cfg.get("reference", {}).get("min_n", _MIN_REF_N)
    green_yellow_pct = cfg.get("zone_cutpoints", {}).get("green_yellow_percentile", _DEFAULT_GREEN_YELLOW_PCT)
    yellow_red_pct = cfg.get("zone_cutpoints", {}).get("yellow_red_percentile", _DEFAULT_YELLOW_RED_PCT)
    cutpoint_method = cfg.get("zone_cutpoints", {}).get("method", "percentile_reference")

    # ── 提取参考子集 ──────────────────────────────────────────────────────────
    if ref_col in df.columns:
        df_ref = df[df[ref_col].astype(bool)]
    else:
        logger.warning("参考标志列 '%s' 不存在，使用 group_code==CTRL 作为参考", ref_col)
        if "group_code" in df.columns:
            df_ref = df[df["group_code"] == "CTRL"]
        else:
            df_ref = df

    if len(df_ref) < min_n:
        logger.warning("参考子集样本量不足（%d < %d），使用全部数据", len(df_ref), min_n)
        df_ref = df

    # ── 拟合模型 + 评分 ───────────────────────────────────────────────────────
    params = fit_anomaly_model(df_ref, variables, stratum_label="global")
    result = compute_anomaly_scores(
        df,
        params,
        cutpoint_method=cutpoint_method,
        green_yellow_pct=green_yellow_pct,
        yellow_red_pct=yellow_red_pct,
        outcome_col=outcome_col,
    )

    return result
