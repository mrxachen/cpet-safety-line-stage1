"""
train_outcome_anchor.py — Stage 1B Outcome-Anchor 验证模型。

定位（Stage 1B 降级用途）：
  不再作为主标签制造器，而是：
  1. 检验 final_zone 是否与临床结局代理同向（构念效度验证）
  2. 提供 outcome_risk_tertile 给 confidence engine
  3. 作为补充材料的辅助模型，不作主结果

主模型：ElasticNet Logistic（透明）
辅模型：LightGBM（高性能，用于灵敏度）
评估：AUC, AUPRC, Brier, calibration intercept/slope, DCA 简化版
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_DEFAULT_FEATURES = [
    "vo2_peak",
    "vo2_peak_pct_pred",
    "ve_vco2_slope",
    "oues",
    "o2_pulse_peak",
    "mets_peak",
    "vt1_vo2",
    "hr_peak_pct_pred",
    "eih_status",
    "age",
    "bmi",
    "htn_history",
    "bp_peak_sys",
]

_POSITIVE_VALUES = {"阳性", "可疑阳性", "positive", "1"}


@dataclass
class OutcomeAnchorResult:
    """Outcome-Anchor 验证模型结果。"""
    cv_auc_mean: float = float("nan")
    cv_auc_std: float = float("nan")
    test_auc: float = float("nan")
    test_auprc: float = float("nan")
    test_brier: float = float("nan")
    cal_intercept: float = float("nan")
    cal_slope: float = float("nan")
    n_train: int = 0
    n_test: int = 0
    positive_rate: float = float("nan")
    feature_names: list[str] = field(default_factory=list)
    predictions_df: pd.DataFrame | None = None
    model_type: str = "elastic_net"


def _build_label(df: pd.DataFrame, col: str = "test_result") -> pd.Series:
    """构建二元结局标签（1=阳性，0=阴性）。"""
    if col not in df.columns:
        raise KeyError(f"Outcome column '{col}' not in DataFrame")
    y = df[col].astype(str).str.strip().str.lower().map(
        lambda v: 1 if any(p in v for p in ["阳性", "positive", "1"]) else 0
    )
    return y.astype(int)


def _prepare_features(
    df: pd.DataFrame,
    feature_list: list[str],
) -> pd.DataFrame:
    """准备特征矩阵：数值化 + 填充中位数。"""
    from sklearn.impute import SimpleImputer

    available = [f for f in feature_list if f in df.columns]
    X = df[available].copy()

    # eih_status → int
    for col in X.columns:
        if X[col].dtype == object or X[col].dtype.name == "bool":
            X[col] = X[col].astype(str).str.lower().map(
                {"true": 1, "false": 0, "1": 1, "0": 0}
            ).fillna(0)

    X = X.apply(pd.to_numeric, errors="coerce")
    imputer = SimpleImputer(strategy="median")
    X_filled = pd.DataFrame(imputer.fit_transform(X), columns=X.columns, index=X.index)
    return X_filled


def run_outcome_anchor(
    df: pd.DataFrame,
    *,
    outcome_col: str = "test_result",
    feature_list: list[str] | None = None,
    n_splits: int = 5,
    test_size: float = 0.2,
    random_state: int = 42,
    model_type: str = "elastic_net",
) -> OutcomeAnchorResult:
    """
    训练并评估 outcome-anchor 验证模型（nested CV）。

    Parameters
    ----------
    df : 完整数据集（含 outcome_col）
    feature_list : 特征列表（默认使用 _DEFAULT_FEATURES）
    n_splits : CV folds
    test_size : hold-out test 比例
    model_type : "elastic_net"（主） or "lightgbm"（辅）

    Returns OutcomeAnchorResult（含 predictions_df）
    """
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        roc_auc_score,
    )
    from sklearn.model_selection import StratifiedKFold, train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    if feature_list is None:
        feature_list = _DEFAULT_FEATURES

    result = OutcomeAnchorResult(model_type=model_type)

    # 构建标签
    try:
        y = _build_label(df, outcome_col)
    except KeyError as e:
        logger.warning("Cannot build outcome label: %s. Returning empty result.", e)
        return result

    valid_mask = y.isin([0, 1])
    df_valid = df[valid_mask].copy()
    y_valid = y[valid_mask]

    if len(df_valid) < 50:
        logger.warning("Too few valid samples (%d) for outcome model", len(df_valid))
        return result

    # 特征准备
    X = _prepare_features(df_valid, feature_list)
    result.feature_names = list(X.columns)
    result.positive_rate = float(y_valid.mean())

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_valid, test_size=test_size, stratify=y_valid, random_state=random_state
    )
    result.n_train = len(X_train)
    result.n_test = len(X_test)

    # 构建模型
    if model_type == "elastic_net":
        base_model = LogisticRegression(
            solver="saga",
            l1_ratio=0.5,
            C=0.1,
            max_iter=2000,
            random_state=random_state,
        )
        pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", base_model),
        ])
    else:
        try:
            import lightgbm as lgb
            base_model = lgb.LGBMClassifier(
                n_estimators=100,
                learning_rate=0.05,
                num_leaves=31,
                random_state=random_state,
                verbose=-1,
            )
            pipe = base_model
        except ImportError:
            logger.warning("LightGBM not available, falling back to elastic_net")
            base_model = LogisticRegression(
                penalty="elasticnet", solver="saga", l1_ratio=0.5, C=0.1,
                max_iter=2000, random_state=random_state
            )
            pipe = Pipeline([("scaler", StandardScaler()), ("clf", base_model)])

    # Nested CV for AUC estimate
    cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    cv_aucs: list[float] = []
    for train_idx, val_idx in cv.split(X_train, y_train):
        Xf, Xv = X_train.iloc[train_idx], X_train.iloc[val_idx]
        yf, yv = y_train.iloc[train_idx], y_train.iloc[val_idx]
        if yv.nunique() < 2:
            continue
        try:
            pipe.fit(Xf, yf)
            if hasattr(pipe, "predict_proba"):
                prob = pipe.predict_proba(Xv)[:, 1]
            else:
                from sklearn.calibration import CalibratedClassifierCV
                calibrated = CalibratedClassifierCV(pipe, cv=2)
                calibrated.fit(Xf, yf)
                prob = calibrated.predict_proba(Xv)[:, 1]
            cv_aucs.append(float(roc_auc_score(yv, prob)))
        except Exception as exc:
            logger.debug("CV fold failed: %s", exc)

    if cv_aucs:
        result.cv_auc_mean = float(np.mean(cv_aucs))
        result.cv_auc_std = float(np.std(cv_aucs))

    # 最终训练
    try:
        pipe.fit(X_train, y_train)

        if hasattr(pipe, "predict_proba"):
            prob_test = pipe.predict_proba(X_test)[:, 1]
            prob_full = pipe.predict_proba(X)[:, 1]
        else:
            from sklearn.calibration import CalibratedClassifierCV
            cal_pipe = CalibratedClassifierCV(pipe, cv=2)
            cal_pipe.fit(X_train, y_train)
            prob_test = cal_pipe.predict_proba(X_test)[:, 1]
            prob_full = cal_pipe.predict_proba(X)[:, 1]

        if y_test.nunique() >= 2:
            result.test_auc = float(roc_auc_score(y_test, prob_test))
            result.test_auprc = float(average_precision_score(y_test, prob_test))
            result.test_brier = float(brier_score_loss(y_test, prob_test))

            # Calibration (intercept / slope)
            try:
                from sklearn.linear_model import LogisticRegression as LR
                logit_prob = np.log(np.clip(prob_test, 1e-6, 1 - 1e-6) / (1 - np.clip(prob_test, 1e-6, 1 - 1e-6)))
                cal_lr = LR(fit_intercept=True)
                cal_lr.fit(logit_prob.reshape(-1, 1), y_test)
                result.cal_intercept = float(cal_lr.intercept_[0])
                result.cal_slope = float(cal_lr.coef_[0, 0])
            except Exception:
                pass

    except Exception as exc:
        logger.warning("Final training failed: %s", exc)
        return result

    # 全量预测（用于 confidence engine 输入）
    try:
        prob_series = pd.Series(prob_full, index=df_valid.index, name="outcome_risk_prob")
        tertile_cuts = np.percentile(prob_full, [33.33, 66.67])
        tertile_labels = pd.cut(
            prob_full,
            bins=[-np.inf, tertile_cuts[0], tertile_cuts[1], np.inf],
            labels=["low", "mid", "high"],
        )
        tertile_series = pd.Series(tertile_labels, index=df_valid.index, name="outcome_risk_tertile")
        result.predictions_df = pd.concat([prob_series, tertile_series], axis=1)
    except Exception as exc:
        logger.warning("Prediction export failed: %s", exc)

    logger.info(
        "OutcomeAnchor[%s]: CV AUC=%.3f±%.3f, Test AUC=%.3f, AUPRC=%.3f, Brier=%.3f",
        model_type,
        result.cv_auc_mean or 0,
        result.cv_auc_std or 0,
        result.test_auc,
        result.test_auprc,
        result.test_brier,
    )

    return result


def generate_outcome_anchor_report(
    result: OutcomeAnchorResult,
    *,
    output_path: str | Path | None = None,
) -> str:
    """生成 outcome-anchor 验证报告（Markdown）。"""
    lines: list[str] = [
        "# Outcome-Anchor Validation Report (Stage 1B)\n",
        f"- 模型类型：{result.model_type}",
        f"- 训练集：{result.n_train}，测试集：{result.n_test}",
        f"- 阳性率：{result.positive_rate:.1%}\n",
        "## 性能指标\n",
        "| 指标 | 值 |",
        "|---|---|",
        f"| CV AUC (mean ± std) | {result.cv_auc_mean:.3f} ± {result.cv_auc_std:.3f} |",
        f"| Test AUC | {result.test_auc:.3f} |",
        f"| Test AUPRC | {result.test_auprc:.3f} |",
        f"| Brier Score | {result.test_brier:.3f} |",
        f"| Calibration intercept | {result.cal_intercept:.3f} |",
        f"| Calibration slope | {result.cal_slope:.3f} |",
        "\n## 说明\n",
        "本模型定位为**验证器**，而非主标签制造器。",
        f"AUC 预期范围：0.55-0.65（summary-level CPET 本身信息限制）。",
        "- AUC > 0.65：提示 outcome model 有额外信息，可作为 confidence engine 补充",
        "- AUC < 0.55：final zone 与 test_result 关系弱，需关注数据质量",
    ]

    if result.predictions_df is not None:
        preds = result.predictions_df
        lines.append("\n## 风险分位分布\n")
        if "outcome_risk_tertile" in preds.columns:
            tertile_counts = preds["outcome_risk_tertile"].value_counts()
            n_total = len(preds)
            for t in ["low", "mid", "high"]:
                cnt = int(tertile_counts.get(t, 0))
                lines.append(f"- {t}: {cnt} ({100*cnt/n_total:.1f}%)")

    report = "\n".join(lines)
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report, encoding="utf-8")
        logger.info("Outcome anchor report saved to %s", output_path)
    return report
