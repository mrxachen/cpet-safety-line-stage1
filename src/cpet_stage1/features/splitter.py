"""
splitter.py — M5 数据分割模块。

基于 split_rules_v1.yaml 配置，提供：
- 20% holdout stratified 分割（train/test）
- 5-fold CV stratified 分割
- subject_id 去重（当前数据无重复 session，退化为 StratifiedKFold）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import yaml
from sklearn.model_selection import StratifiedKFold, train_test_split

logger = logging.getLogger(__name__)


@dataclass
class SplitResult:
    """数据分割结果。"""

    train_idx: pd.Index           # 训练集索引
    test_idx: pd.Index            # 测试集索引
    cv_folds: list[tuple[pd.Index, pd.Index]]  # CV fold 索引列表 (train_idx, val_idx)
    split_stats: dict[str, Any]   # 分割统计信息
    random_seed: int

    def summary(self) -> str:
        """返回分割摘要。"""
        stats = self.split_stats
        lines = [
            "DataSplitter 分割摘要：",
            f"  总样本: {stats.get('n_total', 0)}",
            f"  训练集: {stats.get('n_train', 0)} ({stats.get('train_pct', 0):.1f}%)",
            f"  测试集: {stats.get('n_test', 0)} ({stats.get('test_pct', 0):.1f}%)",
            f"  CV Folds: {stats.get('n_folds', 0)}",
        ]
        # 标签分布
        for split_name in ("train_label_dist", "test_label_dist"):
            dist = stats.get(split_name, {})
            if dist:
                lines.append(f"  {split_name}: {dist}")
        return "\n".join(lines)


class DataSplitter:
    """
    配置驱动的数据分割器。

    基于 split_rules_v1.yaml：
    - holdout: 20% test, stratify_by [p1_zone, sex], seed=42
    - cv: 5-fold, stratify_by [p1_zone], seed=42
    - 当前数据 subject_id 无重复，退化为 StratifiedKFold

    使用方法：
        splitter = DataSplitter("configs/data/split_rules_v1.yaml")
        result = splitter.split(df, label_col="p1_zone")
    """

    def __init__(
        self,
        rules_path: str | Path = "configs/data/split_rules_v1.yaml",
    ) -> None:
        self._rules_path = Path(rules_path)
        if self._rules_path.exists():
            with open(self._rules_path, encoding="utf-8") as f:
                self._cfg = yaml.safe_load(f) or {}
        else:
            logger.warning("split_rules 文件不存在: %s，使用默认配置", self._rules_path)
            self._cfg = {}

        holdout_cfg = self._cfg.get("holdout", {})
        cv_cfg = self._cfg.get("cv", {})

        self._test_fraction = holdout_cfg.get("test_fraction", 0.20)
        self._holdout_seed = holdout_cfg.get("random_seed", 42)
        self._n_folds = cv_cfg.get("n_folds", 5)
        self._cv_seed = cv_cfg.get("random_seed", 42)

    def split(
        self,
        df: pd.DataFrame,
        label_col: str = "p1_zone",
        group_col: str = "subject_id",
    ) -> SplitResult:
        """
        执行 train/test 分割 + CV 分割。

        参数：
            df: 完整数据 DataFrame（需含 label_col 列）
            label_col: 分层标签列（P1 zone 或 P0 event）
            group_col: 分组键列（防 subject 跨 fold 泄漏；当前无重复时退化）

        返回：
            SplitResult
        """
        n = len(df)
        if label_col not in df.columns:
            raise ValueError(f"label_col '{label_col}' 不存在于 DataFrame 中")

        # 1. 过滤标签 NaN（不能用于分层）
        valid_mask = df[label_col].notna()
        if not valid_mask.all():
            n_nan = int((~valid_mask).sum())
            logger.warning("label_col '%s' 有 %d 个 NaN，将排除", label_col, n_nan)

        df_valid = df[valid_mask].copy()
        y = df_valid[label_col].astype(int)

        # 2. 构建分层键（label + sex if available）
        strat_key = self._build_strat_key(df_valid, label_col)

        # 3. Holdout 分割（保证最少 2 个样本/类）
        strat_safe = self._make_strat_safe(strat_key)
        train_idx_local, test_idx_local = train_test_split(
            np.arange(len(df_valid)),
            test_size=self._test_fraction,
            stratify=strat_safe,
            random_state=self._holdout_seed,
        )

        train_idx = df_valid.index[train_idx_local]
        test_idx = df_valid.index[test_idx_local]

        # 4. CV 分割（在训练集上）
        train_df = df_valid.loc[train_idx]
        y_train = y.loc[train_idx]
        strat_cv = self._make_strat_safe(y_train.astype(str))

        cv_folds = self._build_cv_folds(train_df, y_train, strat_cv)

        # 5. 统计
        label_dist_train = y.loc[train_idx].value_counts().to_dict()
        label_dist_test = y.loc[test_idx].value_counts().to_dict()

        stats: dict[str, Any] = {
            "n_total": n,
            "n_valid": len(df_valid),
            "n_train": len(train_idx),
            "n_test": len(test_idx),
            "train_pct": 100 * len(train_idx) / len(df_valid),
            "test_pct": 100 * len(test_idx) / len(df_valid),
            "n_folds": self._n_folds,
            "train_label_dist": label_dist_train,
            "test_label_dist": label_dist_test,
        }

        logger.info(
            "DataSplitter: n_total=%d, train=%d, test=%d, folds=%d",
            n, len(train_idx), len(test_idx), self._n_folds,
        )

        return SplitResult(
            train_idx=train_idx,
            test_idx=test_idx,
            cv_folds=cv_folds,
            split_stats=stats,
            random_seed=self._holdout_seed,
        )

    def _build_strat_key(self, df: pd.DataFrame, label_col: str) -> pd.Series:
        """构建分层键（label + sex 组合）。"""
        strat = df[label_col].astype(str)
        if "sex" in df.columns:
            strat = strat + "_" + df["sex"].astype(object).fillna("U").astype(str)
        return strat

    def _make_strat_safe(self, strat: pd.Series) -> pd.Series:
        """
        确保每个分层类别有足够样本（< 2 样本的类别合并为 "other"）。
        防止 train_test_split 报错。
        """
        counts = strat.value_counts()
        rare_classes = set(counts[counts < 2].index)
        if rare_classes:
            strat = strat.copy()
            strat[strat.isin(rare_classes)] = "other"
        return strat

    def _build_cv_folds(
        self,
        train_df: pd.DataFrame,
        y_train: pd.Series,
        strat: pd.Series,
    ) -> list[tuple[pd.Index, pd.Index]]:
        """
        构建 CV folds（StratifiedKFold）。

        返回：列表 [(train_index, val_index), ...]，index 为 DataFrame index
        """
        n_folds = min(self._n_folds, len(train_df))  # 防止样本太少

        # 检查每类样本数是否满足 n_folds
        min_count = y_train.value_counts().min()
        actual_folds = min(n_folds, int(min_count))
        if actual_folds < 2:
            actual_folds = 2
        if actual_folds < n_folds:
            logger.warning(
                "部分类别样本不足 %d，CV folds 降为 %d", n_folds, actual_folds
            )

        skf = StratifiedKFold(
            n_splits=actual_folds, shuffle=True, random_state=self._cv_seed
        )

        folds = []
        arr = np.arange(len(train_df))
        for fold_train, fold_val in skf.split(arr, strat.values):
            fold_train_idx = train_df.index[fold_train]
            fold_val_idx = train_df.index[fold_val]
            folds.append((fold_train_idx, fold_val_idx))

        return folds
