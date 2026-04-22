"""
feature_engineer.py — M5 特征工程核心模块。

基于 feature_config_v1.yaml 配置，为 P0（运动前先验风险）和 P1（运动后后验分层）
构建特征矩阵，包含：选列 → 编码 → 插补 → LeakageGuard.assert

设计原则：
- imputer 仅在 train 集上 fit（防数据泄漏）
- scaler 仅对 LASSO / OrdinalLogistic 适用，树模型跳过
- FeatureResult 携带 fitted imputer/scaler，供 test 集变换复用
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd
import yaml
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from cpet_stage1.labels.leakage_guard import LeakageGuard

logger = logging.getLogger(__name__)


@dataclass
class FeatureResult:
    """特征工程输出结果，含特征矩阵和拟合的预处理器。"""

    X: pd.DataFrame                          # 特征矩阵（已编码、插补、可选缩放）
    feature_names: list[str]                 # 最终特征列名列表
    imputer_stats: dict[str, Any]            # 插补统计（各列插补值）
    scaler: Optional[StandardScaler]         # 缩放器（树模型为 None）
    leakage_report: dict[str, list[str]]     # LeakageGuard 报告
    fitted_imputer: Optional[SimpleImputer]  # 拟合的插补器（复用于 test 集）
    task: str                                # "p0" 或 "p1"

    def to_parquet(self, path: str | Path) -> None:
        """将特征矩阵保存为 parquet 文件。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.X.to_parquet(path, index=False)
        logger.info("特征矩阵保存: %s (%d 行 × %d 列)", path, len(self.X), len(self.feature_names))

    def summary(self) -> str:
        """返回可读摘要。"""
        lines = [
            f"FeatureResult [{self.task}]:",
            f"  形状: {self.X.shape[0]} 行 × {self.X.shape[1]} 列",
            f"  特征数: {len(self.feature_names)}",
            f"  缩放器: {'StandardScaler' if self.scaler else 'None（树模型）'}",
            f"  泄漏检查 P0 排除: {self.leakage_report.get('p0_exclusions', [])}",
            f"  泄漏检查 P1 排除: {self.leakage_report.get('p1_exclusions', [])}",
        ]
        return "\n".join(lines)


class FeatureEngineer:
    """
    配置驱动的特征工程引擎。

    使用方法：
        fe = FeatureEngineer("configs/features/feature_config_v1.yaml",
                              "configs/data/label_rules_v2.yaml")
        result_train = fe.build_p0(train_df, include_bp=True)
        result_test  = fe.build_p0(test_df, include_bp=True,
                                    fitted_imputer=result_train.fitted_imputer,
                                    fitted_scaler=result_train.scaler)
    """

    def __init__(
        self,
        config_path: str | Path = "configs/features/feature_config_v1.yaml",
        label_rules_path: str | Path = "configs/data/label_rules_v2.yaml",
    ) -> None:
        self._config_path = Path(config_path)
        with open(self._config_path, encoding="utf-8") as f:
            self._cfg = yaml.safe_load(f) or {}

        self._guard = LeakageGuard.from_config(label_rules_path)

        self._impute_cfg = self._cfg.get("imputation", {})
        self._scale_cfg = self._cfg.get("scaling", {})

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def derive_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        派生特征预处理（在 build_p0/build_p1 调用前执行）。

        当前支持的派生逻辑（由 configs 中 derived_features 配置驱动）：
        - bmi: weight_kg / (height_cm / 100)²

        参数：
            df: 原始 DataFrame

        返回：
            添加了派生列的新 DataFrame（不修改原始 df）
        """
        df_out = df.copy()

        # 检查所有任务配置（p0 + p1）中的 derived_features
        for task_key in ("p0", "p1"):
            task_cfg = self._cfg.get(task_key, {})
            derived_cfg = task_cfg.get("derived_features", {})

            if "bmi" in derived_cfg and "bmi" not in df_out.columns:
                if "height_cm" in df_out.columns and "weight_kg" in df_out.columns:
                    height_m = df_out["height_cm"] / 100.0
                    # 避免除以零
                    safe_h = height_m.replace(0, np.nan)
                    df_out["bmi"] = df_out["weight_kg"] / (safe_h ** 2)
                    logger.info("派生列 'bmi' 已添加")
                else:
                    logger.warning("无法派生 bmi：height_cm 或 weight_kg 不存在")

        return df_out

    def build_p0(
        self,
        df: pd.DataFrame,
        include_bp: bool = True,
        model_type: str = "xgboost",
        fitted_imputer: Optional[SimpleImputer] = None,
        fitted_scaler: Optional[StandardScaler] = None,
    ) -> FeatureResult:
        """
        构建 P0 特征矩阵（运动前先验风险）。

        参数：
            df: 含原始字段的 DataFrame
            include_bp: 是否包含静息 BP 列（False 时排除 bp_rest_sys, bp_rest_dia）
            model_type: 模型类型，决定是否应用 StandardScaler
            fitted_imputer: 已拟合的插补器（train 集）；None 则在 df 上 fit
            fitted_scaler: 已拟合的缩放器；None 则按需 fit

        返回：
            FeatureResult
        """
        # 0. 派生预处理（bmi 等配置驱动的派生字段）
        df = self.derive_features(df)

        p0_cfg = self._cfg.get("p0", {})
        bp_fields = set(p0_cfg.get("bp_fields", []))

        # 1. 收集候选特征列
        cont_cols = list(p0_cfg.get("continuous", []))
        bin_cols = list(p0_cfg.get("binary", []))
        cat_cols = list(p0_cfg.get("categorical", []))
        proto_cols = list(p0_cfg.get("protocol", []))

        # no_bp 变体：排除静息 BP 列
        if not include_bp:
            cont_cols = [c for c in cont_cols if c not in bp_fields]

        all_cols = cont_cols + bin_cols + cat_cols + proto_cols

        # 2. 过滤存在于 df 中的列
        available_cols = [c for c in all_cols if c in df.columns]
        missing_cols = [c for c in all_cols if c not in df.columns]
        if missing_cols:
            logger.warning("P0 特征列缺失（将跳过）: %s", missing_cols)

        X = df[available_cols].copy()

        # 3. 编码分类列
        X = self._encode_categorical(X, cat_cols)

        # 4. Binary 字段：NaN → 0
        bin_avail = [c for c in bin_cols if c in X.columns]
        for col in bin_avail:
            X[col] = X[col].map(lambda v: float(v) if pd.notna(v) else 0.0)

        # 5. Protocol 字段：bool → int
        proto_avail = [c for c in proto_cols if c in X.columns]
        for col in proto_avail:
            X[col] = X[col].map(lambda v: 1.0 if v is True or v == 1 or v == "True" else 0.0)

        # 6. 确保全数值型
        X = X.astype(float, errors="ignore")

        # 7. LeakageGuard（在插补之前执行，确保特征列不含泄漏字段）
        X = self._guard.filter(X, task="p0")
        self._guard.assert_no_leakage(X, task="p0")

        # 8. 插补
        cont_avail = [c for c in cont_cols if c in X.columns]
        X, fitted_imp, imp_stats = self._impute(
            X, cont_cols=cont_avail, fitted_imputer=fitted_imputer
        )

        # 9. 缩放（仅 LASSO 等线性模型）
        X, fitted_scl = self._scale(X, model_type=model_type, fitted_scaler=fitted_scaler)

        feature_names = list(X.columns)

        return FeatureResult(
            X=X,
            feature_names=feature_names,
            imputer_stats=imp_stats,
            scaler=fitted_scl,
            leakage_report=self._guard.report(),
            fitted_imputer=fitted_imp,
            task="p0",
        )

    def build_p1(
        self,
        df: pd.DataFrame,
        cycle_only: bool = False,
        model_type: str = "lightgbm",
        fitted_imputer: Optional[SimpleImputer] = None,
        fitted_scaler: Optional[StandardScaler] = None,
    ) -> FeatureResult:
        """
        构建 P1 特征矩阵（运动后后验分层）。

        参数：
            df: 含 CPET 运动结果的 DataFrame
            cycle_only: 是否仅保留踏车协议记录
            model_type: 模型类型
            fitted_imputer: 已拟合的插补器；None 则 fit
            fitted_scaler: 已拟合的缩放器；None 则按需 fit

        返回：
            FeatureResult
        """
        # 0. 派生预处理
        df = self.derive_features(df)

        p1_cfg = self._cfg.get("p1", {})

        # 1. 踏车协议过滤
        cycle_col = p1_cfg.get("cycle_filter_col", "exercise_protocol_cycle")
        if cycle_only and cycle_col in df.columns:
            df = df[df[cycle_col].map(lambda v: v is True or v == 1 or v == "True")]
            logger.info("P1 cycle_only 过滤后: %d 行", len(df))
        if len(df) == 0:
            raise ValueError("P1 cycle_only 过滤后无数据，请检查 exercise_protocol_cycle 字段")

        # 2. 收集候选特征列
        cont_cols = list(p1_cfg.get("continuous", []))
        bin_cols = list(p1_cfg.get("binary", []))
        cat_cols = list(p1_cfg.get("categorical", []))
        all_cols = cont_cols + bin_cols + cat_cols

        available_cols = [c for c in all_cols if c in df.columns]
        missing_cols = [c for c in all_cols if c not in df.columns]
        if missing_cols:
            logger.warning("P1 特征列缺失（将跳过）: %s", missing_cols)

        X = df[available_cols].copy()

        # 3. 编码分类列
        X = self._encode_categorical(X, cat_cols)

        # 4. Binary 字段：NaN → 0
        bin_avail = [c for c in bin_cols if c in X.columns]
        for col in bin_avail:
            X[col] = X[col].map(lambda v: float(v) if pd.notna(v) else 0.0)

        # 5. 连续列强制转换为数值（处理 '23.5.6' 等脏字符串 → NaN）
        cont_avail_raw = [c for c in cont_cols if c in X.columns]
        for col in cont_avail_raw:
            X[col] = pd.to_numeric(X[col], errors="coerce")

        # 确保全数值型
        X = X.astype(float, errors="ignore")

        # 6. LeakageGuard
        X = self._guard.filter(X, task="p1")
        self._guard.assert_no_leakage(X, task="p1")

        # 7. 插补
        cont_avail = [c for c in cont_cols if c in X.columns]
        X, fitted_imp, imp_stats = self._impute(
            X, cont_cols=cont_avail, fitted_imputer=fitted_imputer
        )

        # 8. 缩放
        X, fitted_scl = self._scale(X, model_type=model_type, fitted_scaler=fitted_scaler)

        feature_names = list(X.columns)

        return FeatureResult(
            X=X,
            feature_names=feature_names,
            imputer_stats=imp_stats,
            scaler=fitted_scl,
            leakage_report=self._guard.report(),
            fitted_imputer=fitted_imp,
            task="p1",
        )

    # ------------------------------------------------------------------
    # 内部工具方法
    # ------------------------------------------------------------------

    def _encode_categorical(self, X: pd.DataFrame, cat_cols: list[str]) -> pd.DataFrame:
        """对分类列做简单编码（sex: M→0, F→1；其余用 pd.factorize）。"""
        for col in cat_cols:
            if col not in X.columns:
                continue
            if col == "sex":
                mapped = X[col].astype(object).map({"M": 0, "F": 1, 0: 0, 1: 1})
                X[col] = mapped.fillna(-1)
            else:
                # 其他分类字段：factorize（NaN → -1）
                codes, _ = pd.factorize(X[col])
                X[col] = codes.astype(float)
                X[col] = X[col].replace(-1, float("nan"))
        return X

    def _impute(
        self,
        X: pd.DataFrame,
        cont_cols: list[str],
        fitted_imputer: Optional[SimpleImputer],
    ) -> tuple[pd.DataFrame, SimpleImputer, dict[str, Any]]:
        """
        对连续列做插补。binary/categorical 列已在外部处理。

        返回：(插补后 DataFrame, 拟合的 SimpleImputer, 插补统计字典)
        """
        strategy_cont = self._impute_cfg.get("continuous", "median")
        # 仅对连续列做中位数插补
        cont_present = [c for c in cont_cols if c in X.columns]

        if not cont_present:
            return X.copy(), SimpleImputer(strategy=strategy_cont), {}

        imp = fitted_imputer if fitted_imputer is not None else SimpleImputer(strategy=strategy_cont)

        X_cont = X[cont_present].copy()
        if fitted_imputer is None:
            X_arr = imp.fit_transform(X_cont)
        else:
            X_arr = imp.transform(X_cont)

        X_imputed = X.copy()
        X_imputed[cont_present] = X_arr

        # 记录插补统计
        imp_stats: dict[str, Any] = {
            col: float(stat)
            for col, stat in zip(cont_present, imp.statistics_)
        }

        return X_imputed, imp, imp_stats

    def _scale(
        self,
        X: pd.DataFrame,
        model_type: str,
        fitted_scaler: Optional[StandardScaler],
    ) -> tuple[pd.DataFrame, Optional[StandardScaler]]:
        """
        对特征矩阵做 StandardScaler 缩放（仅对需要缩放的模型类型）。

        返回：(缩放后 DataFrame, StandardScaler 或 None)
        """
        scale_models = set(self._scale_cfg.get("apply_to_model_types", []))
        if model_type not in scale_models:
            return X, None

        scaler = fitted_scaler if fitted_scaler is not None else StandardScaler()
        feature_names = list(X.columns)

        if fitted_scaler is None:
            X_arr = scaler.fit_transform(X)
        else:
            X_arr = scaler.transform(X)

        X_scaled = pd.DataFrame(X_arr, columns=feature_names, index=X.index)
        return X_scaled, scaler
