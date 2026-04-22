"""
train_p0.py — M5 P0 模型训练管线。

训练两类模型 × 两个 BP 变体 = 4 组合：
- (LASSO, XGBoost) × (with_bp, no_bp)

工作流程：
1. DataSplitter 分割训练集/测试集
2. FeatureEngineer.build_p0() 构建特征（分别对 train/test）
3. GridSearchCV / RandomizedSearchCV 超参数搜索
4. 在 train 上 fit，在 test 上评估
5. isotonic 校准（CalibratedClassifierCV prefit）
6. 返回 P0ModelResult

配置文件：
- configs/model/p0_lasso.yaml
- configs/model/p0_xgb.yaml
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV, RandomizedSearchCV

from cpet_stage1.features.feature_engineer import FeatureEngineer, FeatureResult
from cpet_stage1.features.splitter import DataSplitter, SplitResult
from cpet_stage1.modeling.calibrate import calibrate_binary
from cpet_stage1.modeling.evaluate import EvaluationResult, ModelEvaluator

logger = logging.getLogger(__name__)


@dataclass
class P0ModelResult:
    """P0 单模型单变体训练结果。"""
    model_name: str                          # "lasso" 或 "xgb"
    bp_variant: str                          # "with_bp" 或 "no_bp"
    best_params: dict[str, Any]              # 最优超参数
    cv_scores: dict[str, float]              # CV 分数统计（mean, std）
    test_metrics: EvaluationResult           # 测试集评估结果
    calibrated_model: Any                    # 校准后模型
    feature_importance: Optional[pd.DataFrame]  # 特征重要性
    predictions: dict[str, np.ndarray]      # {"y_test": ..., "y_proba": ...}
    feature_result: FeatureResult           # 特征工程结果（含 fitted_imputer/scaler）


class P0Trainer:
    """
    P0 模型训练管线。

    使用方法：
        trainer = P0Trainer(
            lasso_config="configs/model/p0_lasso.yaml",
            xgb_config="configs/model/p0_xgb.yaml",
        )
        results = trainer.run(df, label_col="p0_event")
    """

    def __init__(
        self,
        lasso_config: str | Path = "configs/model/p0_lasso.yaml",
        xgb_config: str | Path = "configs/model/p0_xgb.yaml",
        feature_config: str | Path = "configs/features/feature_config_v1.yaml",
        label_rules: str | Path = "configs/data/label_rules_v2.yaml",
        split_rules: str | Path = "configs/data/split_rules_v1.yaml",
        **kwargs,   # 兼容性：忽略未知参数
    ) -> None:
        self._lasso_cfg = self._load_yaml(lasso_config)
        self._xgb_cfg = self._load_yaml(xgb_config)
        self._fe = FeatureEngineer(feature_config, label_rules)
        self._splitter = DataSplitter(split_rules)
        self._evaluator = ModelEvaluator()

    @staticmethod
    def _load_yaml(path: str | Path) -> dict[str, Any]:
        p = Path(path)
        if not p.exists():
            logger.warning("配置文件不存在: %s，使用空配置", p)
            return {}
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def run(
        self,
        df: pd.DataFrame,
        label_col: str = "p0_event",
        n_iter_override: Optional[int] = None,  # 测试时可设为小值（如 3）
    ) -> dict[str, dict[str, P0ModelResult]]:
        """
        运行 P0 训练管线。

        参数：
            df: 含所有字段和 p0_event 标签的 DataFrame
            label_col: P0 标签列名
            n_iter_override: 覆盖 RandomizedSearchCV n_iter（测试用）

        返回：
            {model_name: {bp_variant: P0ModelResult}}
            model_name: "lasso", "xgb"
            bp_variant: "with_bp", "no_bp"
        """
        if label_col not in df.columns:
            raise ValueError(f"标签列 '{label_col}' 不存在")

        # 分割数据
        split = self._splitter.split(df, label_col=label_col)
        logger.info("P0 数据分割: %s", split.summary())

        results: dict[str, dict[str, P0ModelResult]] = {}

        for include_bp, variant_name in [(True, "with_bp"), (False, "no_bp")]:
            # 构建训练集特征（LASSO 需要 fit imputer + scaler）
            fe_train_lasso = self._fe.build_p0(
                df.loc[split.train_idx], include_bp=include_bp, model_type="lasso_logistic"
            )
            fe_test_lasso = self._fe.build_p0(
                df.loc[split.test_idx], include_bp=include_bp, model_type="lasso_logistic",
                fitted_imputer=fe_train_lasso.fitted_imputer,
                fitted_scaler=fe_train_lasso.scaler,
            )
            fe_train_xgb = self._fe.build_p0(
                df.loc[split.train_idx], include_bp=include_bp, model_type="xgboost"
            )
            fe_test_xgb = self._fe.build_p0(
                df.loc[split.test_idx], include_bp=include_bp, model_type="xgboost",
                fitted_imputer=fe_train_xgb.fitted_imputer,
                fitted_scaler=fe_train_xgb.scaler,
            )

            y_train = df.loc[split.train_idx, label_col].astype(int).values
            y_test = df.loc[split.test_idx, label_col].astype(int).values

            # LASSO
            lasso_result = self._train_lasso(
                fe_train_lasso, fe_test_lasso, y_train, y_test, variant_name
            )
            results.setdefault("lasso", {})[variant_name] = lasso_result

            # XGBoost
            xgb_result = self._train_xgb(
                fe_train_xgb, fe_test_xgb, y_train, y_test, variant_name,
                n_iter_override=n_iter_override,
            )
            results.setdefault("xgb", {})[variant_name] = xgb_result

        return results

    def _train_lasso(
        self,
        fe_train: FeatureResult,
        fe_test: FeatureResult,
        y_train: np.ndarray,
        y_test: np.ndarray,
        variant: str,
    ) -> P0ModelResult:
        """LASSO Logistic Regression + GridSearchCV。"""
        cfg_hp = self._lasso_cfg.get("hyperparameters", {})
        cfg_cv = self._lasso_cfg.get("cv", {})

        C_grid = cfg_hp.get("C", [0.001, 0.01, 0.1, 1.0, 10.0])
        max_iter = cfg_hp.get("max_iter", 1000)
        n_folds = cfg_cv.get("n_folds", 5)
        scoring = cfg_cv.get("scoring", "roc_auc")

        X_train = fe_train.X.values
        X_test = fe_test.X.values

        base_model = LogisticRegression(
            l1_ratio=1.0, solver="saga", max_iter=max_iter, random_state=42
        )
        param_grid = {"C": C_grid}

        n_folds_safe = min(n_folds, int(y_train.sum()), int((1 - y_train).sum()))
        n_folds_safe = max(2, n_folds_safe)

        gs = GridSearchCV(base_model, param_grid, cv=n_folds_safe, scoring=scoring, n_jobs=-1)
        gs.fit(X_train, y_train)

        best_model = gs.best_estimator_
        best_params = gs.best_params_
        cv_scores = {
            "mean": float(gs.best_score_),
            "std": float(gs.cv_results_["std_test_score"][gs.best_index_]),
        }

        # 校准
        cal_method = self._lasso_cfg.get("calibration", {}).get("method", "isotonic")
        cal_model = calibrate_binary(best_model, X_train, y_train, method=cal_method)

        # 评估
        eval_result = self._evaluator.evaluate_binary(
            cal_model, X_test, y_test, model_name="LASSO", variant=variant
        )

        # 特征重要性（系数绝对值）
        coef = np.abs(best_model.coef_[0])
        feat_imp = pd.DataFrame({
            "feature": fe_train.feature_names,
            "importance": coef,
        }).sort_values("importance", ascending=False).reset_index(drop=True)

        y_proba = cal_model.predict_proba(X_test)[:, 1]

        logger.info("P0 LASSO [%s]: AUC=%.4f, best_C=%.4f", variant, eval_result.binary_metrics.auc_roc, best_params.get("C", 0))

        return P0ModelResult(
            model_name="lasso",
            bp_variant=variant,
            best_params=best_params,
            cv_scores=cv_scores,
            test_metrics=eval_result,
            calibrated_model=cal_model,
            feature_importance=feat_imp,
            predictions={"y_test": y_test, "y_proba": y_proba},
            feature_result=fe_train,
        )

    def _train_xgb(
        self,
        fe_train: FeatureResult,
        fe_test: FeatureResult,
        y_train: np.ndarray,
        y_test: np.ndarray,
        variant: str,
        n_iter_override: Optional[int] = None,
    ) -> P0ModelResult:
        """XGBoost + RandomizedSearchCV。"""
        try:
            from xgboost import XGBClassifier
        except ImportError:
            raise ImportError("请安装 xgboost: pip install xgboost")

        cfg_hp = self._xgb_cfg.get("hyperparameters", {})
        cfg_cv = self._xgb_cfg.get("cv", {})

        n_iter = n_iter_override or cfg_cv.get("n_iter", 50)
        n_folds = cfg_cv.get("n_folds", 5)
        scoring = cfg_cv.get("scoring", "roc_auc")

        X_train = fe_train.X.values
        X_test = fe_test.X.values

        # 类别不平衡处理
        n_neg = int((1 - y_train).sum())
        n_pos = int(y_train.sum())
        scale_pos_weight = n_neg / max(n_pos, 1)

        # 参数空间（快速测试模式）
        est_options = [20, 50] if n_iter_override is not None else cfg_hp.get("n_estimators", [100, 300])
        param_dist = {
            "n_estimators": est_options,
            "max_depth": cfg_hp.get("max_depth", [3, 5]),
            "learning_rate": cfg_hp.get("learning_rate", [0.05, 0.1]),
            "subsample": cfg_hp.get("subsample", [0.8]),
            "colsample_bytree": cfg_hp.get("colsample_bytree", [0.8]),
            "min_child_weight": cfg_hp.get("min_child_weight", [1, 3]),
        }

        base_model = XGBClassifier(
            scale_pos_weight=scale_pos_weight,
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,
            verbosity=0,
            use_label_encoder=False,
        )

        n_folds_safe = min(n_folds, max(2, min(int(y_train.sum()), int((1 - y_train).sum()))))

        rs = RandomizedSearchCV(
            base_model, param_dist,
            n_iter=n_iter, cv=n_folds_safe, scoring=scoring,
            random_state=42, n_jobs=-1,
        )
        rs.fit(X_train, y_train)

        best_model = rs.best_estimator_
        best_params = rs.best_params_
        cv_scores = {
            "mean": float(rs.best_score_),
            "std": float(rs.cv_results_["std_test_score"][rs.best_index_]),
        }

        # 校准
        cal_method = self._xgb_cfg.get("calibration", {}).get("method", "isotonic")
        cal_model = calibrate_binary(best_model, X_train, y_train, method=cal_method)

        # 评估
        eval_result = self._evaluator.evaluate_binary(
            cal_model, X_test, y_test, model_name="XGBoost", variant=variant
        )

        # 特征重要性
        feat_imp = pd.DataFrame({
            "feature": fe_train.feature_names,
            "importance": best_model.feature_importances_,
        }).sort_values("importance", ascending=False).reset_index(drop=True)

        y_proba = cal_model.predict_proba(X_test)[:, 1]

        logger.info("P0 XGBoost [%s]: AUC=%.4f", variant, eval_result.binary_metrics.auc_roc)

        return P0ModelResult(
            model_name="xgb",
            bp_variant=variant,
            best_params=best_params,
            cv_scores=cv_scores,
            test_metrics=eval_result,
            calibrated_model=cal_model,
            feature_importance=feat_imp,
            predictions={"y_test": y_test, "y_proba": y_proba},
            feature_result=fe_train,
        )
