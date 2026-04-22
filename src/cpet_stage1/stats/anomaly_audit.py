"""
anomaly_audit.py — Stage 1B 异常表型审计（Robust Mahalanobis）。

定位（Stage 1B）：
  不再作为主风险分层器，而是：
  1. QC：发现异常输入（数据错误/设备问题）
  2. Atypical phenotype flag：不典型表型样本标记
  3. Stage II 优先抽样池

区别于 Phase G anomaly_score.py：
  - 仅在 reference-normalized 的核心变量上计算
  - 使用 MinCovDet（Robust）替代普通协方差
  - 输出 anomaly_flag（布尔）而非 anomaly_zone
  - 定位明确为 QC/audit，不用于 zone 定义
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_DEFAULT_VARIABLES = [
    "vo2_peak",
    "ve_vco2_slope",
    "oues",
    "o2_pulse_peak",
    "mets_peak",
    "vt1_vo2",
]

_ANOMALY_THRESHOLD_PCT = 97.5  # chi2 分布的百分位


@dataclass
class AnomalyAuditResult:
    """异常审计结果。"""
    scores: pd.DataFrame           # index-aligned, with anomaly_score + anomaly_flag
    n_anomaly: int = 0
    threshold: float = float("nan")
    variables_used: list[str] = field(default_factory=list)
    n_reference: int = 0

    def summary(self) -> str:
        n = len(self.scores)
        return (
            f"AnomalyAudit: n={n}, anomaly_flag={self.n_anomaly} "
            f"({100*self.n_anomaly/n:.1f}%), threshold={self.threshold:.2f}, "
            f"variables={self.variables_used}"
        )


def run_anomaly_audit(
    df: pd.DataFrame,
    *,
    reference_mask: pd.Series | None = None,
    variables: list[str] | None = None,
    threshold_pct: float = _ANOMALY_THRESHOLD_PCT,
    use_robust: bool = True,
    min_reference_n: int = 50,
) -> AnomalyAuditResult:
    """
    基于 Mahalanobis 距离的异常表型审计。

    Parameters
    ----------
    df : 完整数据集
    reference_mask : 参考子集 mask（在 reference subset 上估计分布）
    variables : 用于计算的变量列表（默认 _DEFAULT_VARIABLES）
    threshold_pct : chi2 分布的百分位阈值（默认 97.5%）
    use_robust : 是否用 MinCovDet（Robust）
    min_reference_n : 参考子集最小样本量

    Returns AnomalyAuditResult
    """
    from scipy import stats as scipy_stats

    if variables is None:
        variables = _DEFAULT_VARIABLES

    # 筛选存在的变量
    avail_vars = [v for v in variables if v in df.columns]
    if len(avail_vars) < 2:
        logger.warning("Too few variables (%d) for anomaly audit, skipping", len(avail_vars))
        empty = pd.DataFrame({
            "anomaly_score": np.nan,
            "anomaly_flag": False,
        }, index=df.index)
        return AnomalyAuditResult(scores=empty, variables_used=avail_vars)

    # 构建特征矩阵
    X = df[avail_vars].apply(pd.to_numeric, errors="coerce")

    # 参考子集
    if reference_mask is not None:
        X_ref = X[reference_mask].dropna()
    else:
        X_ref = X.dropna()

    if len(X_ref) < min_reference_n:
        logger.warning(
            "Reference subset too small for anomaly audit: n=%d < %d",
            len(X_ref), min_reference_n,
        )
        empty = pd.DataFrame({
            "anomaly_score": np.nan,
            "anomaly_flag": False,
        }, index=df.index)
        return AnomalyAuditResult(scores=empty, variables_used=avail_vars, n_reference=len(X_ref))

    # 估计均值和协方差
    if use_robust:
        try:
            from sklearn.covariance import MinCovDet
            mcd = MinCovDet(random_state=42)
            mcd.fit(X_ref.values)
            center = mcd.location_
            cov = mcd.covariance_
        except Exception as exc:
            logger.warning("MinCovDet failed (%s), falling back to empirical", exc)
            center = X_ref.mean().values
            cov = np.cov(X_ref.values.T)
    else:
        center = X_ref.mean().values
        cov = np.cov(X_ref.values.T)

    # 确保协方差矩阵可逆
    try:
        cov_inv = np.linalg.pinv(cov)
    except np.linalg.LinAlgError:
        cov_inv = np.eye(len(avail_vars))

    # 计算 Mahalanobis 距离
    X_full = X.values
    scores = np.full(len(df), np.nan)
    valid_rows = ~np.isnan(X_full).any(axis=1)

    if valid_rows.any():
        diff = X_full[valid_rows] - center
        d2 = np.einsum("ij,jk,ik->i", diff, cov_inv, diff)
        scores[valid_rows] = np.sqrt(np.maximum(d2, 0))

    # 阈值：chi2 分位（k 个变量）
    threshold = float(np.sqrt(scipy_stats.chi2.ppf(threshold_pct / 100, df=len(avail_vars))))

    anomaly_flag = pd.Series(scores >= threshold, index=df.index, dtype=bool)
    anomaly_flag[np.isnan(scores)] = False

    result_df = pd.DataFrame({
        "anomaly_score": pd.Series(scores, index=df.index),
        "anomaly_flag": anomaly_flag,
    })

    n_anomaly = int(anomaly_flag.sum())
    logger.info(
        "AnomalyAudit: n_anomaly=%d (%.1f%%), threshold=%.2f, vars=%s",
        n_anomaly, 100 * n_anomaly / len(df), threshold, avail_vars,
    )

    return AnomalyAuditResult(
        scores=result_df,
        n_anomaly=n_anomaly,
        threshold=threshold,
        variables_used=avail_vars,
        n_reference=len(X_ref),
    )


def generate_anomaly_audit_report(
    result: AnomalyAuditResult,
    *,
    output_path: str | Path | None = None,
) -> str:
    """生成异常审计报告（Markdown）。"""
    df = result.scores
    n = len(df)

    lines: list[str] = [
        "# Anomaly Audit Report (Stage 1B)\n",
        f"- 总样本数：{n}",
        f"- 使用变量：{result.variables_used}",
        f"- 参考子集样本量：{result.n_reference}",
        f"- 异常阈值（chi2 P{_ANOMALY_THRESHOLD_PCT}）：{result.threshold:.3f}",
        f"- 标记异常样本数：{result.n_anomaly} ({100*result.n_anomaly/n:.1f}%)\n",
        "## anomaly_score 分布\n",
    ]

    if "anomaly_score" in df.columns:
        scores = df["anomaly_score"].dropna()
        if len(scores) > 0:
            lines.extend([
                f"- Mean ± std：{scores.mean():.3f} ± {scores.std():.3f}",
                f"- Median：{scores.median():.3f}",
                f"- P75/P90/P95：{scores.quantile(0.75):.3f} / {scores.quantile(0.90):.3f} / {scores.quantile(0.95):.3f}",
                f"- P97.5（阈值对应）：{scores.quantile(0.975):.3f}",
            ])

    lines.append("\n## 定位说明\n")
    lines.append("异常表型（anomaly_flag=True）样本建议：")
    lines.append("- 人工复核原始记录，排查数据录入错误")
    lines.append("- 检查设备校准（尤其是气体分析仪）")
    lines.append("- 作为 Stage II 原始数据分析的优先抽样池")
    lines.append("- **不用于 final_zone 定义**（仅作 QC/atypical flag）")

    report = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report, encoding="utf-8")
        logger.info("Anomaly audit report saved to %s", output_path)

    return report
