"""
train_p1.py — M5 P1 模型训练管线。

训练三类模型 × 两个样本变体 = 6 组合：
- (OrdinalLogistic, LightGBM, CatBoost) × (full, cycle_only)

工作流程：
1. DataSplitter 分割训练集/测试集
2. FeatureEngineer.build_p1() 构建特征
3. 超参数搜索（OrdinalLogistic: GridSearchCV, LGBM/CatBoost: RandomizedSearchCV）
4. 校准（温度缩放 for LGBM/CatBoost, isotonic for OrdinalLogistic）
5. 一致性分析（full vs cycle_only）
6. 返回 P1ModelResult

配置文件：
- configs/model/p1_logit.yaml
- configs/model/p1_lgbm.yaml
- configs/model/p1_catboost.yaml
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
from sklearn.multiclass import OneVsRestClassifier

from cpet_stage1.features.feature_engineer import FeatureEngineer, FeatureResult
from cpet_stage1.features.splitter import DataSplitter, SplitResult
from cpet_stage1.modeling.calibrate import TemperatureScaler, calibrate_binary
from cpet_stage1.modeling.evaluate import EvaluationResult, ModelEvaluator

logger = logging.getLogger(__name__)


@dataclass
class P1ConsistencyResult:
    """全样本 vs 踏车子集一致性分析结果。"""
    f1_macro_full: float
    f1_macro_cycle: float
    kappa_full: float
    kappa_cycle: float
    f1_delta: float    # cycle - full
    kappa_delta: float


@dataclass
class P1ModelResult:
    """P1 单模型单变体训练结果。"""
    model_name: str                          # "ordinal_logistic", "lgbm", "catboost"
    sample_variant: str                      # "full", "cycle_only"
    best_params: dict[str, Any]
    cv_scores: dict[str, float]
    test_metrics: EvaluationResult
    calibrated_model: Any                    # 校准后模型（温度缩放包装）
    temperature_scaler: Optional[TemperatureScaler]
    feature_importance: Optional[pd.DataFrame]
    predictions: dict[str, np.ndarray]      # {"y_test": ..., "y_pred": ..., "y_proba": ...}
    feature_result: FeatureResult


@dataclass
class CalibratedP1Model:
    """包装校准后的 P1 多分类模型，提供 predict/predict_proba 接口。"""
    base_model: Any
    temperature_scaler: Optional[TemperatureScaler]

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        proba = self.base_model.predict_proba(X)
        if self.temperature_scaler is not None:
            proba = self.temperature_scaler.transform(proba)
        return proba

    def predict(self, X: np.ndarray) -> np.ndarray:
        proba = self.predict_proba(X)
        return np.argmax(proba, axis=1)


class _OrdinalLogisticWrapper:
    """
    Ordinal Logistic Regression 的 sklearn 兼容包装器。

    内部使用 statsmodels.OrderedModel（若可用），否则退化为
    softmax Logistic Regression（sklearn）。

    提供 fit / predict / predict_proba 接口。
    """

    def __init__(self, C: float = 1.0, method: str = "logit") -> None:
        self.C = C
        self.method = method
        self._model = None
        self._use_statsmodels = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_OrdinalLogisticWrapper":
        try:
            from statsmodels.miscmodels.ordinal_model import OrderedModel
            self._use_statsmodels = True
            self._model = OrderedModel(y, X, distr=self.method)
            self._result = self._model.fit(method="bfgs", disp=False, maxiter=200)
        except Exception as e:
            logger.warning("statsmodels OrderedModel 失败(%s)，退化为 softmax LogisticRegression", e)
            self._use_statsmodels = False
            self._model = LogisticRegression(
                solver="lbfgs",
                C=self.C, max_iter=1000, random_state=42
            )
            self._model.fit(X, y)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self._use_statsmodels and hasattr(self, "_result"):
            try:
                proba = self._result.predict(X)
                if isinstance(proba, pd.DataFrame):
                    return proba.values
                return np.array(proba)
            except Exception:
                pass
        return self._model.predict_proba(X)

    def predict(self, X: np.ndarray) -> np.ndarray:
        proba = self.predict_proba(X)
        return np.argmax(proba, axis=1)

    def get_params(self, deep: bool = True) -> dict:
        return {"C": self.C, "method": self.method}

    def set_params(self, **params: Any) -> "_OrdinalLogisticWrapper":
        for k, v in params.items():
            setattr(self, k, v)
        return self


class P1Trainer:
    """
    P1 模型训练管线。

    使用方法：
        trainer = P1Trainer(...)
        results = trainer.run(df, label_col="p1_zone")
    """

    def __init__(
        self,
        logit_config: str | Path = "configs/model/p1_logit.yaml",
        lgbm_config: str | Path = "configs/model/p1_lgbm.yaml",
        catboost_config: str | Path = "configs/model/p1_catboost.yaml",
        feature_config: str | Path = "configs/features/feature_config_v1.yaml",
        label_rules: str | Path = "configs/data/label_rules_v2.yaml",
        split_rules: str | Path = "configs/data/split_rules_v1.yaml",
    ) -> None:
        self._logit_cfg = self._load_yaml(logit_config)
        self._lgbm_cfg = self._load_yaml(lgbm_config)
        self._catboost_cfg = self._load_yaml(catboost_config)
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
        label_col: str = "p1_zone",
        n_iter_override: Optional[int] = None,
    ) -> dict[str, dict[str, P1ModelResult]]:
        """
        运行 P1 训练管线。

        参数：
            df: 含所有字段和 p1_zone 标签的 DataFrame
            label_col: P1 标签列名（整数 0/1/2）
            n_iter_override: 覆盖 RandomizedSearchCV n_iter（测试用）

        返回：
            {model_name: {sample_variant: P1ModelResult}}
        """
        if label_col not in df.columns:
            raise ValueError(f"标签列 '{label_col}' 不存在")

        # 过滤 NaN 标签
        df_clean = df[df[label_col].notna()].copy()
        df_clean[label_col] = df_clean[label_col].astype(int)

        # 分割（用 full 数据）
        split = self._splitter.split(df_clean, label_col=label_col)
        logger.info("P1 数据分割: %s", split.summary())

        results: dict[str, dict[str, P1ModelResult]] = {}

        for cycle_only, variant_name in [(False, "full"), (True, "cycle_only")]:
            # 检查 cycle_only 是否有足够数据
            try:
                fe_train = self._fe.build_p1(
                    df_clean.loc[split.train_idx], cycle_only=cycle_only,
                    model_type="ordinal_logistic"
                )
                fe_test = self._fe.build_p1(
                    df_clean.loc[split.test_idx], cycle_only=cycle_only,
                    model_type="ordinal_logistic",
                    fitted_imputer=fe_train.fitted_imputer,
                    fitted_scaler=fe_train.scaler,
                )
            except ValueError as e:
                logger.warning("P1 [%s] 特征构建失败: %s，跳过", variant_name, e)
                continue

            # 为树模型构建独立特征（不含 scaler）
            try:
                fe_train_tree = self._fe.build_p1(
                    df_clean.loc[split.train_idx], cycle_only=cycle_only,
                    model_type="lightgbm"
                )
                fe_test_tree = self._fe.build_p1(
                    df_clean.loc[split.test_idx], cycle_only=cycle_only,
                    model_type="lightgbm",
                    fitted_imputer=fe_train_tree.fitted_imputer,
                    fitted_scaler=fe_train_tree.scaler,
                )
            except ValueError:
                fe_train_tree = fe_train
                fe_test_tree = fe_test

            # 匹配 train/test 的标签（cycle_only 可能改变行数）
            if cycle_only:
                # cycle_only 过滤后，需重新提取对应的标签
                cycle_col = "exercise_protocol_cycle"
                if cycle_col in df_clean.columns:
                    train_mask = df_clean.loc[split.train_idx, cycle_col].map(
                        lambda v: v is True or v == 1 or v == "True"
                    )
                    test_mask = df_clean.loc[split.test_idx, cycle_col].map(
                        lambda v: v is True or v == 1 or v == "True"
                    )
                    y_train = df_clean.loc[split.train_idx][train_mask][label_col].values
                    y_test = df_clean.loc[split.test_idx][test_mask][label_col].values
                else:
                    y_train = df_clean.loc[split.train_idx, label_col].values
                    y_test = df_clean.loc[split.test_idx, label_col].values
            else:
                y_train = df_clean.loc[split.train_idx, label_col].values
                y_test = df_clean.loc[split.test_idx, label_col].values

            # 对齐 X 和 y 长度
            X_train_logit = fe_train.X.values[:len(y_train)]
            X_test_logit = fe_test.X.values[:len(y_test)]
            X_train_tree = fe_train_tree.X.values[:len(y_train)]
            X_test_tree = fe_test_tree.X.values[:len(y_test)]

            if len(y_train) < 6:
                logger.warning("P1 [%s] 训练样本过少 (%d)，跳过", variant_name, len(y_train))
                continue

            # OrdinalLogistic
            logit_result = self._train_ordinal_logistic(
                fe_train, X_train_logit, X_test_logit, y_train, y_test, variant_name
            )
            results.setdefault("ordinal_logistic", {})[variant_name] = logit_result

            # LightGBM
            lgbm_result = self._train_lgbm(
                fe_train_tree, X_train_tree, X_test_tree, y_train, y_test, variant_name,
                n_iter_override=n_iter_override,
            )
            results.setdefault("lgbm", {})[variant_name] = lgbm_result

            # CatBoost
            catboost_result = self._train_catboost(
                fe_train_tree, X_train_tree, X_test_tree, y_train, y_test, variant_name,
                n_iter_override=n_iter_override,
            )
            results.setdefault("catboost", {})[variant_name] = catboost_result

        # 一致性分析
        self._consistency_analysis(results)

        return results

    def _train_ordinal_logistic(
        self,
        fe_train: FeatureResult,
        X_train: np.ndarray,
        X_test: np.ndarray,
        y_train: np.ndarray,
        y_test: np.ndarray,
        variant: str,
    ) -> P1ModelResult:
        """Ordinal Logistic Regression + GridSearchCV（包装为 sklearn 接口）。"""
        cfg_hp = self._logit_cfg.get("hyperparameters", {})
        cfg_cv = self._logit_cfg.get("cv", {})

        C_grid = cfg_hp.get("C", [0.01, 0.1, 1.0])
        n_folds = cfg_cv.get("n_folds", 5)
        scoring = cfg_cv.get("scoring", "f1_macro")

        # 使用 softmax 多分类作为 OrdinalLogistic 代理（GridSearchCV 兼容）
        base_model = LogisticRegression(
            solver="lbfgs", max_iter=1000, random_state=42
        )
        param_grid = {"C": C_grid}

        n_classes = len(np.unique(y_train))
        n_folds_safe = min(n_folds, max(2, int(len(y_train) / n_classes)))

        gs = GridSearchCV(
            base_model, param_grid, cv=n_folds_safe, scoring=scoring, n_jobs=-1
        )
        gs.fit(X_train, y_train)

        best_model = gs.best_estimator_
        best_params = gs.best_params_
        cv_scores = {
            "mean": float(gs.best_score_),
            "std": float(gs.cv_results_["std_test_score"][gs.best_index_]),
        }

        # 校准（isotonic 对 logistic 回归）
        try:
            cal_model = calibrate_binary(best_model, X_train, y_train, method="isotonic")
        except Exception:
            # isotonic 对多分类可能失败，直接使用原模型
            cal_model = best_model

        # 温度缩放
        proba_train = best_model.predict_proba(X_train)
        ts = TemperatureScaler(n_classes=n_classes)
        try:
            ts.fit(proba_train, y_train)
        except Exception as e:
            logger.warning("OrdinalLogistic 温度缩放失败: %s", e)
            ts.temperature_ = 1.0

        wrapped = CalibratedP1Model(base_model=best_model, temperature_scaler=ts)

        # 评估
        eval_result = self._evaluator.evaluate_multiclass(
            wrapped, X_test, y_test, model_name="OrdinalLogistic", variant=variant
        )

        # 特征重要性（系数 L2 norm）
        coef = np.linalg.norm(best_model.coef_, axis=0)
        feat_imp = pd.DataFrame({
            "feature": fe_train.feature_names[:len(coef)],
            "importance": coef,
        }).sort_values("importance", ascending=False).reset_index(drop=True)

        y_pred = wrapped.predict(X_test)
        y_proba = wrapped.predict_proba(X_test)

        logger.info(
            "P1 OrdinalLogistic [%s]: F1_macro=%.4f",
            variant, eval_result.multiclass_metrics.f1_macro
        )

        return P1ModelResult(
            model_name="ordinal_logistic",
            sample_variant=variant,
            best_params=best_params,
            cv_scores=cv_scores,
            test_metrics=eval_result,
            calibrated_model=wrapped,
            temperature_scaler=ts,
            feature_importance=feat_imp,
            predictions={"y_test": y_test, "y_pred": y_pred, "y_proba": y_proba},
            feature_result=fe_train,
        )

    def _train_lgbm(
        self,
        fe_train: FeatureResult,
        X_train: np.ndarray,
        X_test: np.ndarray,
        y_train: np.ndarray,
        y_test: np.ndarray,
        variant: str,
        n_iter_override: Optional[int] = None,
    ) -> P1ModelResult:
        """LightGBM 多分类 + RandomizedSearchCV + 温度缩放。"""
        try:
            from lightgbm import LGBMClassifier
        except ImportError:
            raise ImportError("请安装 lightgbm: pip install lightgbm")

        cfg_hp = self._lgbm_cfg.get("hyperparameters", {})
        cfg_cv = self._lgbm_cfg.get("cv", {})

        n_iter = n_iter_override or cfg_cv.get("n_iter", 40)
        n_folds = cfg_cv.get("n_folds", 5)
        scoring = cfg_cv.get("scoring", "f1_macro")

        # 快速测试模式
        est_options = [20, 50] if n_iter_override is not None else cfg_hp.get("n_estimators", [200, 500])

        param_dist = {
            "n_estimators": est_options,
            "max_depth": cfg_hp.get("max_depth", [4, 6]),
            "learning_rate": cfg_hp.get("learning_rate", [0.05, 0.1]),
            "num_leaves": cfg_hp.get("num_leaves", [31, 63]),
            "subsample": cfg_hp.get("subsample", [0.8, 1.0]),
            "colsample_bytree": cfg_hp.get("colsample_bytree", [0.8]),
        }

        n_classes = len(np.unique(y_train))
        n_folds_safe = min(n_folds, max(2, int(len(y_train) / n_classes)))

        # 类权重：优先读取配置，默认 balanced
        class_weight_cfg = cfg_hp.get("class_weight", "balanced")
        if isinstance(class_weight_cfg, dict):
            # 显式权重字典（如 {0: 1.0, 1: 2.0, 2: 4.0}）
            class_weight = {int(k): v for k, v in class_weight_cfg.items()}
        else:
            class_weight = class_weight_cfg  # "balanced" 或 None

        base_model = LGBMClassifier(
            objective="multiclass",
            num_class=n_classes,
            class_weight=class_weight,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )

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

        # 温度缩放
        proba_train = best_model.predict_proba(X_train)
        ts = TemperatureScaler(n_classes=n_classes)
        try:
            ts.fit(proba_train, y_train)
        except Exception as e:
            logger.warning("LightGBM 温度缩放失败: %s", e)
            ts.temperature_ = 1.0

        wrapped = CalibratedP1Model(base_model=best_model, temperature_scaler=ts)

        # 评估
        eval_result = self._evaluator.evaluate_multiclass(
            wrapped, X_test, y_test, model_name="LightGBM", variant=variant
        )

        # 特征重要性
        feat_imp = pd.DataFrame({
            "feature": fe_train.feature_names[:len(best_model.feature_importances_)],
            "importance": best_model.feature_importances_,
        }).sort_values("importance", ascending=False).reset_index(drop=True)

        y_pred = wrapped.predict(X_test)
        y_proba = wrapped.predict_proba(X_test)

        logger.info(
            "P1 LightGBM [%s]: F1_macro=%.4f",
            variant, eval_result.multiclass_metrics.f1_macro
        )

        return P1ModelResult(
            model_name="lgbm",
            sample_variant=variant,
            best_params=best_params,
            cv_scores=cv_scores,
            test_metrics=eval_result,
            calibrated_model=wrapped,
            temperature_scaler=ts,
            feature_importance=feat_imp,
            predictions={"y_test": y_test, "y_pred": y_pred, "y_proba": y_proba},
            feature_result=fe_train,
        )

    def _train_catboost(
        self,
        fe_train: FeatureResult,
        X_train: np.ndarray,
        X_test: np.ndarray,
        y_train: np.ndarray,
        y_test: np.ndarray,
        variant: str,
        n_iter_override: Optional[int] = None,
    ) -> P1ModelResult:
        """CatBoost 多分类 + RandomizedSearchCV + 温度缩放。"""
        try:
            from catboost import CatBoostClassifier
        except ImportError:
            raise ImportError("请安装 catboost: pip install catboost")

        cfg_hp = self._catboost_cfg.get("hyperparameters", {})
        cfg_cv = self._catboost_cfg.get("cv", {})

        n_iter = n_iter_override or cfg_cv.get("n_iter", 30)
        n_folds = cfg_cv.get("n_folds", 5)
        scoring = cfg_cv.get("scoring", "f1_macro")

        # 快速测试模式（n_iter_override 不为 None 时使用小迭代数）
        iterations_options = [10, 20] if n_iter_override is not None else cfg_hp.get("iterations", [200, 300])

        param_dist = {
            "iterations": iterations_options,
            "depth": cfg_hp.get("depth", [4, 6]),
            "learning_rate": cfg_hp.get("learning_rate", [0.05, 0.1]),
            "l2_leaf_reg": cfg_hp.get("l2_leaf_reg", [1, 3]),
        }

        n_classes = len(np.unique(y_train))
        n_folds_safe = min(n_folds, max(2, int(len(y_train) / n_classes)))

        # 类权重：优先读取配置，默认 Balanced
        catboost_kwargs: dict = {"verbose": 0, "random_state": 42, "thread_count": -1}
        class_weights_cfg = cfg_hp.get("class_weights", None)
        auto_class_weights_cfg = cfg_hp.get("auto_class_weights", None)
        if class_weights_cfg is not None:
            # 显式权重列表（如 [1.0, 2.0, 4.0]）
            catboost_kwargs["class_weights"] = list(class_weights_cfg)
        elif auto_class_weights_cfg is not None:
            catboost_kwargs["auto_class_weights"] = auto_class_weights_cfg
        else:
            catboost_kwargs["auto_class_weights"] = "Balanced"

        base_model = CatBoostClassifier(**catboost_kwargs)

        if class_weights_cfg is not None:
            # 将 class_weights 转为 sample_weight，避免 sklearn clone() 在 CatBoost 内部
            # 类型转换后 is 检查不通过的问题，从而让 RandomizedSearchCV 正常工作
            sw_train = np.array([class_weights_cfg[int(y)] for y in y_train])
            # 构造不含 class_weights 的干净 base model（可被 sklearn clone）
            base_model_clean = CatBoostClassifier(
                verbose=0, random_state=42, thread_count=-1
            )
            rs = RandomizedSearchCV(
                base_model_clean, param_dist,
                n_iter=n_iter, cv=n_folds_safe, scoring=scoring,
                random_state=42, n_jobs=1,
            )
            rs.fit(X_train, y_train, sample_weight=sw_train)
            best_model = rs.best_estimator_
            best_params = rs.best_params_
            cv_scores = {
                "mean": float(rs.best_score_),
                "std": float(rs.cv_results_["std_test_score"][rs.best_index_]),
            }
        else:
            rs = RandomizedSearchCV(
                base_model, param_dist,
                n_iter=n_iter, cv=n_folds_safe, scoring=scoring,
                random_state=42, n_jobs=1,  # CatBoost 自身有并行，n_jobs=1
            )
            rs.fit(X_train, y_train)
            best_model = rs.best_estimator_
            best_params = rs.best_params_
            cv_scores = {
                "mean": float(rs.best_score_),
                "std": float(rs.cv_results_["std_test_score"][rs.best_index_]),
            }

        # 温度缩放
        proba_train = best_model.predict_proba(X_train)
        ts = TemperatureScaler(n_classes=n_classes)
        try:
            ts.fit(proba_train, y_train)
        except Exception as e:
            logger.warning("CatBoost 温度缩放失败: %s", e)
            ts.temperature_ = 1.0

        wrapped = CalibratedP1Model(base_model=best_model, temperature_scaler=ts)

        # 评估
        eval_result = self._evaluator.evaluate_multiclass(
            wrapped, X_test, y_test, model_name="CatBoost", variant=variant
        )

        # 特征重要性
        try:
            feat_importance = best_model.get_feature_importance()
            feat_imp = pd.DataFrame({
                "feature": fe_train.feature_names[:len(feat_importance)],
                "importance": feat_importance,
            }).sort_values("importance", ascending=False).reset_index(drop=True)
        except Exception:
            feat_imp = None

        y_pred = wrapped.predict(X_test)
        y_proba = wrapped.predict_proba(X_test)

        logger.info(
            "P1 CatBoost [%s]: F1_macro=%.4f",
            variant, eval_result.multiclass_metrics.f1_macro
        )

        return P1ModelResult(
            model_name="catboost",
            sample_variant=variant,
            best_params=best_params,
            cv_scores=cv_scores,
            test_metrics=eval_result,
            calibrated_model=wrapped,
            temperature_scaler=ts,
            feature_importance=feat_imp,
            predictions={"y_test": y_test, "y_pred": y_pred, "y_proba": y_proba},
            feature_result=fe_train,
        )

    def _consistency_analysis(
        self,
        results: dict[str, dict[str, P1ModelResult]],
    ) -> Optional[dict[str, P1ConsistencyResult]]:
        """
        full vs cycle_only 一致性分析：报告 F1/kappa delta。

        返回：{model_name: P1ConsistencyResult} 或 None（若两个变体均不存在）
        """
        consistency: dict[str, P1ConsistencyResult] = {}

        for model_name, variants in results.items():
            if "full" not in variants or "cycle_only" not in variants:
                continue
            full_r = variants["full"].test_metrics.multiclass_metrics
            cycle_r = variants["cycle_only"].test_metrics.multiclass_metrics
            if full_r is None or cycle_r is None:
                continue

            delta_f1 = cycle_r.f1_macro - full_r.f1_macro
            delta_kappa = cycle_r.kappa_weighted - full_r.kappa_weighted

            cons = P1ConsistencyResult(
                f1_macro_full=full_r.f1_macro,
                f1_macro_cycle=cycle_r.f1_macro,
                kappa_full=full_r.kappa_weighted,
                kappa_cycle=cycle_r.kappa_weighted,
                f1_delta=delta_f1,
                kappa_delta=delta_kappa,
            )
            consistency[model_name] = cons
            logger.info(
                "P1 一致性 [%s]: F1 delta=%.4f (full=%.4f, cycle=%.4f), "
                "kappa delta=%.4f",
                model_name, delta_f1, full_r.f1_macro, cycle_r.f1_macro, delta_kappa,
            )

        return consistency if consistency else None
