"""
train_outcome.py — Phase G Method 1：结局锚定安全区训练管线

核心创新：直接以 test_result（CPET 临床结局：阳性/可疑阳性 vs 阴性）为标签，
全特征建模（含 vo2_peak_pct_pred、ve_vco2_slope、eih_status），消除 P1 循环依赖。

为什么不存在泄漏：
  test_result 是临床医生的综合判断结局，不是由任何单一 CPET 变量确定性定义的。
  使用全部 CPET 指标预测 test_result，正是临床医生的日常工作。

配置文件：configs/model/outcome_lgbm.yaml
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# ── 默认特征列表（当 YAML 中未配置时使用）──────────────────────────────────────
_DEFAULT_FEATURES = [
    "vo2_peak",
    "vo2_peak_pct_pred",
    "hr_peak",
    "o2_pulse_peak",
    "mets_peak",
    "ve_vco2_slope",
    "oues",
    "vt1_vo2",
    "eih_status",
    "age",
    "htn_history",
]

_DEFAULT_POSITIVE_VALUES = {"阳性", "可疑阳性"}
_DEFAULT_NEGATIVE_VALUES = {"阴性"}


@dataclass
class OutcomeModelResult:
    """结局锚定模型训练结果。"""
    model_name: str = "outcome_lgbm"
    best_params: dict[str, Any] = field(default_factory=dict)
    cv_auc_mean: float = float("nan")
    cv_auc_std: float = float("nan")
    test_auc: float = float("nan")
    test_ap: float = float("nan")         # Average Precision
    test_brier: float = float("nan")      # Brier Score
    calibrated_model: Any = None
    feature_names: list[str] = field(default_factory=list)
    feature_importance: Optional[pd.DataFrame] = None
    predictions: dict[str, np.ndarray] = field(default_factory=dict)
    cutpoints: Optional[Any] = None       # OutcomeZoneCutpoints
    zone_distribution: dict = field(default_factory=dict)
    n_train: int = 0
    n_test: int = 0
    n_positive_train: int = 0
    positive_rate: float = float("nan")
    leakage_guard_applied: bool = False   # outcome 任务不需要排除 CPET 指标


def _load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        logger.warning("配置文件不存在: %s，使用空配置", p)
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_outcome_label(
    df: pd.DataFrame,
    outcome_col: str = "test_result",
    positive_values: Optional[set] = None,
) -> pd.Series:
    """
    构建 test_result 二分类标签（1=阳性/可疑阳性, 0=阴性）。
    NaN 和未知值统一置为 NaN（后续 dropna 处理）。
    """
    if positive_values is None:
        positive_values = _DEFAULT_POSITIVE_VALUES

    if outcome_col not in df.columns:
        raise KeyError(f"结局列 '{outcome_col}' 不在 DataFrame 中。")

    raw = df[outcome_col]
    y = pd.Series(np.nan, index=df.index, name="test_result_binary")
    y[raw.isin(positive_values)] = 1.0
    y[raw.isin(_DEFAULT_NEGATIVE_VALUES)] = 0.0
    # NaN 保留为 NaN（后续 dropna 处理）

    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    n_na = int(y.isna().sum())
    logger.info(
        "结局标签构建：阳性=%d (%.1f%%), 阴性=%d, NaN=%d",
        n_pos, n_pos / (n_pos + n_neg) * 100 if (n_pos + n_neg) > 0 else 0,
        n_neg, n_na,
    )
    return y


def _prepare_features(
    df: pd.DataFrame,
    feature_names: list[str],
) -> pd.DataFrame:
    """
    从 DataFrame 中提取并预处理特征矩阵。

    处理：
    - eih_status: bool → int（0/1）
    - sex_binary: 派生（若 sex 列存在）
    - bmi: 派生（若 height_cm/weight_kg 存在）
    - 其余数值列：保留原始值（含 NaN，由模型内部处理）
    """
    X = pd.DataFrame(index=df.index)

    for col in feature_names:
        if col == "sex_binary":
            if "sex" in df.columns:
                X["sex_binary"] = (df["sex"] == "F").astype(float)
            else:
                X["sex_binary"] = np.nan
        elif col == "bmi":
            if "height_cm" in df.columns and "weight_kg" in df.columns:
                h = df["height_cm"].replace(0, np.nan)
                X["bmi"] = df["weight_kg"] / (h / 100) ** 2
            else:
                X["bmi"] = np.nan
        elif col == "eih_status":
            if col in df.columns:
                X[col] = df[col].map({True: 1, False: 0, 1: 1, 0: 0}).astype(float)
            else:
                X[col] = np.nan
        elif col in df.columns:
            X[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            logger.debug("特征列 '%s' 不在 DataFrame 中，填充 NaN", col)
            X[col] = np.nan

    return X


class OutcomeTrainer:
    """
    结局锚定安全区训练管线。

    使用方法：
        trainer = OutcomeTrainer("configs/model/outcome_lgbm.yaml")
        result = trainer.run(df)
        print(f"AUC: {result.test_auc:.3f}")
    """

    def __init__(
        self,
        config_path: str | Path = "configs/model/outcome_lgbm.yaml",
        random_state: int = 42,
    ) -> None:
        self._cfg = _load_yaml(config_path)
        self._random_state = random_state
        self._feature_names = self._cfg.get("features", _DEFAULT_FEATURES)
        self._positive_values = set(
            self._cfg.get("positive_values", list(_DEFAULT_POSITIVE_VALUES))
        )

    def run(
        self,
        df: pd.DataFrame,
        outcome_col: str = "test_result",
        n_iter_override: Optional[int] = None,
    ) -> OutcomeModelResult:
        """
        运行结局锚定训练管线。

        参数：
            df: 包含所有特征和 outcome_col 的 DataFrame
            outcome_col: 结局列名（默认 "test_result"）
            n_iter_override: 测试时设为小值（如 3）以加速

        返回：
            OutcomeModelResult
        """
        try:
            from lightgbm import LGBMClassifier
            from sklearn.calibration import CalibratedClassifierCV
            from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
            from sklearn.model_selection import RandomizedSearchCV, StratifiedKFold
            from cpet_stage1.labels.outcome_zone import (
                compute_outcome_cutpoints,
                assign_outcome_zones_series,
                compute_zone_distribution,
            )
        except ImportError as e:
            raise ImportError(f"结局锚定模型依赖缺失: {e}") from e

        result = OutcomeModelResult(
            feature_names=self._feature_names,
            leakage_guard_applied=False,  # outcome 任务不排除 CPET 指标
        )

        # ── 1. 构建标签 ──────────────────────────────────────────────────────────
        y_raw = _build_outcome_label(df, outcome_col, self._positive_values)
        valid_mask = y_raw.notna()
        df_valid = df[valid_mask].copy()
        y = y_raw[valid_mask].astype(int)

        if len(y) < 50:
            logger.error("有效样本量过少（%d），无法训练", len(y))
            return result

        n_pos = int(y.sum())
        if n_pos < 10:
            logger.error("阳性样本量过少（%d），无法训练", n_pos)
            return result

        result.positive_rate = float(n_pos / len(y))
        logger.info("有效样本: %d, 阳性: %d (%.1f%%)", len(y), n_pos, result.positive_rate * 100)

        # ── 2. 构建特征矩阵 ──────────────────────────────────────────────────────
        X = _prepare_features(df_valid, self._feature_names)

        # ── 3. 训练/测试分割（80/20，分层）─────────────────────────────────────
        from sklearn.model_selection import train_test_split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=self._random_state, stratify=y
        )
        result.n_train = len(y_train)
        result.n_test = len(y_test)
        result.n_positive_train = int(y_train.sum())

        # ── 4. 超参数搜索 ────────────────────────────────────────────────────────
        cv_cfg = self._cfg.get("cv", {})
        n_folds = cv_cfg.get("n_folds", 5)
        n_iter = n_iter_override or cv_cfg.get("n_iter", 40)

        param_grid = {
            "n_estimators": self._cfg.get("hyperparameters", {}).get("n_estimators", [100, 200]),
            "max_depth": self._cfg.get("hyperparameters", {}).get("max_depth", [4, 6]),
            "learning_rate": self._cfg.get("hyperparameters", {}).get("learning_rate", [0.05, 0.1]),
            "num_leaves": self._cfg.get("hyperparameters", {}).get("num_leaves", [31]),
            "subsample": self._cfg.get("hyperparameters", {}).get("subsample", [0.8]),
            "colsample_bytree": self._cfg.get("hyperparameters", {}).get("colsample_bytree", [0.8]),
            "min_child_samples": self._cfg.get("hyperparameters", {}).get("min_child_samples", [20]),
        }

        base_model = LGBMClassifier(
            random_state=self._random_state,
            class_weight="balanced",
            verbose=-1,
            n_jobs=1,           # 避免 WSL 多线程问题
            num_threads=1,      # LightGBM 内部线程数
        )

        cv = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=self._random_state)
        # n_jobs=1: 避免 WSL 下多进程开销导致的超时
        # 当 n_iter 很小（测试模式）时使用更少的 CV 折数
        cv_for_search = cv if n_iter >= 10 else StratifiedKFold(
            n_splits=2, shuffle=True, random_state=self._random_state
        )
        search = RandomizedSearchCV(
            base_model,
            param_grid,
            n_iter=n_iter,
            scoring="roc_auc",
            cv=cv_for_search,
            random_state=self._random_state,
            n_jobs=1,
            refit=True,
        )

        # 中位数填充训练集 NaN（简单策略）
        X_train_filled = X_train.fillna(X_train.median())
        X_test_filled = X_test.fillna(X_train.median())

        search.fit(X_train_filled, y_train)

        result.best_params = search.best_params_
        result.cv_auc_mean = float(search.best_score_)
        result.cv_auc_std = float(
            search.cv_results_["std_test_score"][search.best_index_]
        )
        logger.info("CV AUC: %.3f ± %.3f", result.cv_auc_mean, result.cv_auc_std)

        # ── 5. Isotonic 校准（3折内部 CV 校准）────────────────────────────────────
        # sklearn 1.8+ 移除了 cv="prefit"，改用 cv=int 内部校准
        calibrated = CalibratedClassifierCV(
            search.best_estimator_, cv=2, method="isotonic", n_jobs=1,
        )
        calibrated.fit(X_train_filled, y_train)
        result.calibrated_model = calibrated

        # ── 6. 测试集评估 ────────────────────────────────────────────────────────
        y_proba = calibrated.predict_proba(X_test_filled)[:, 1]
        result.predictions = {
            "y_test": y_test.values,
            "y_proba": y_proba,
        }

        result.test_auc = float(roc_auc_score(y_test, y_proba))
        result.test_ap = float(average_precision_score(y_test, y_proba))
        result.test_brier = float(brier_score_loss(y_test, y_proba))
        logger.info(
            "测试集 AUC=%.3f, AP=%.3f, Brier=%.3f",
            result.test_auc, result.test_ap, result.test_brier,
        )

        # ── 7. 特征重要性 ────────────────────────────────────────────────────────
        try:
            best_lgbm = search.best_estimator_
            importances = best_lgbm.feature_importances_
            result.feature_importance = pd.DataFrame({
                "feature": self._feature_names[:len(importances)],
                "importance": importances,
            }).sort_values("importance", ascending=False).reset_index(drop=True)
        except Exception:
            pass

        # ── 8. 切点计算与安全区分配 ───────────────────────────────────────────────
        # 在训练集上计算切点（防止测试集信息泄漏）
        y_proba_train = calibrated.predict_proba(X_train_filled)[:, 1]
        cutpoints = compute_outcome_cutpoints(y_train.values, y_proba_train)
        result.cutpoints = cutpoints

        # 全数据集（含测试）的安全区分配
        X_all_filled = _prepare_features(df_valid, self._feature_names).fillna(
            X_train.median()
        )
        y_proba_all = calibrated.predict_proba(X_all_filled)[:, 1]
        y_proba_series = pd.Series(y_proba_all, index=df_valid.index)
        zone_series = assign_outcome_zones_series(y_proba_series, cutpoints)

        outcome_binary = y  # 仅有效样本
        result.zone_distribution = compute_zone_distribution(zone_series, outcome_binary)

        logger.info(
            "安全区分布: Green=%d (%.1f%%), Yellow=%d (%.1f%%), Red=%d (%.1f%%)",
            result.zone_distribution.get("green", {}).get("n", 0),
            result.zone_distribution.get("green", {}).get("pct", 0),
            result.zone_distribution.get("yellow", {}).get("n", 0),
            result.zone_distribution.get("yellow", {}).get("pct", 0),
            result.zone_distribution.get("red", {}).get("n", 0),
            result.zone_distribution.get("red", {}).get("pct", 0),
        )

        return result

    def generate_report(self, result: OutcomeModelResult) -> str:
        """生成 Markdown 格式的结局锚定模型报告。"""
        lines = [
            "# 结局锚定安全区模型报告（Method 1 / Phase G）",
            "",
            "## 方法概述",
            "",
            "直接以 `test_result`（CPET 临床结局）为标签，全特征建模，消除 P1 循环依赖。",
            "",
            "## 模型性能",
            "",
            f"| 指标 | 值 |",
            f"|---|---|",
            f"| CV AUC (5折) | {result.cv_auc_mean:.3f} ± {result.cv_auc_std:.3f} |",
            f"| 测试集 AUC | {result.test_auc:.3f} |",
            f"| 测试集 AP | {result.test_ap:.3f} |",
            f"| 测试集 Brier | {result.test_brier:.3f} |",
            f"| 阳性率 | {result.positive_rate:.1%} |",
            f"| 训练集 N | {result.n_train} |",
            f"| 测试集 N | {result.n_test} |",
            "",
            "## 安全区切点",
            "",
        ]

        if result.cutpoints is not None:
            cp = result.cutpoints
            lines += [
                f"| 参数 | 值 |",
                f"|---|---|",
                f"| Green/Yellow 界 | P < {cp.low_cut:.3f} |",
                f"| Yellow/Red 界 | P ≥ {cp.high_cut:.3f} |",
                f"| 方法 | {cp.method} |",
                f"| Green/Yellow 处敏感度 | {cp.sensitivity_at_low:.3f} |",
                f"| Green/Yellow 处特异度 | {cp.specificity_at_low:.3f} |",
                f"| Youden J (Yellow/Red) | {cp.youden_j:.3f} |",
                "",
            ]

        lines += ["## 安全区分布", ""]
        dist = result.zone_distribution
        for z in ["green", "yellow", "red"]:
            info = dist.get(z, {})
            n = info.get("n", 0)
            pct = info.get("pct", 0)
            pos_rate = info.get("positive_rate", None)
            pos_str = f", 阳性率 {pos_rate:.1f}%" if pos_rate is not None else ""
            lines.append(f"- **{z.capitalize()}**: {n} ({pct:.1f}%){pos_str}")

        lines += ["", "## 特征重要性（Top 10）", ""]
        if result.feature_importance is not None:
            lines.append("| 特征 | 重要性 |")
            lines.append("|---|---|")
            for _, row in result.feature_importance.head(10).iterrows():
                lines.append(f"| {row['feature']} | {row['importance']:.0f} |")

        return "\n".join(lines)
