"""
test_splitter.py — M5 DataSplitter 测试（~15 个测试）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.features.splitter import DataSplitter, SplitResult


def make_df(n: int = 50, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "subject_id": [f"S{i:04d}" for i in range(n)],
        "age": rng.integers(60, 80, n).astype(float),
        "sex": rng.choice(["M", "F"], n),
        "p1_zone": rng.choice([0, 1, 2], n),
        "p0_event": rng.choice([0, 1], n, p=[0.8, 0.2]),
    })


@pytest.fixture
def splitter() -> DataSplitter:
    return DataSplitter("configs/data/split_rules_v1.yaml")


@pytest.fixture
def df() -> pd.DataFrame:
    return make_df(n=60)


class TestDataSplitter:

    def test_split_returns_split_result(self, splitter, df):
        result = splitter.split(df, label_col="p1_zone")
        assert isinstance(result, SplitResult)

    def test_split_sizes_add_up(self, splitter, df):
        result = splitter.split(df, label_col="p1_zone")
        total = len(result.train_idx) + len(result.test_idx)
        assert total == len(df)

    def test_test_fraction_approximately_20pct(self, splitter, df):
        result = splitter.split(df, label_col="p1_zone")
        test_pct = len(result.test_idx) / len(df)
        assert 0.15 <= test_pct <= 0.30

    def test_no_overlap_between_train_and_test(self, splitter, df):
        result = splitter.split(df, label_col="p1_zone")
        overlap = set(result.train_idx) & set(result.test_idx)
        assert len(overlap) == 0

    def test_cv_folds_correct_count(self, splitter, df):
        result = splitter.split(df, label_col="p1_zone")
        assert len(result.cv_folds) >= 2

    def test_cv_folds_within_train_idx(self, splitter, df):
        result = splitter.split(df, label_col="p1_zone")
        train_set = set(result.train_idx)
        for fold_train, fold_val in result.cv_folds:
            assert set(fold_train).issubset(train_set)
            assert set(fold_val).issubset(train_set)

    def test_cv_folds_no_overlap(self, splitter, df):
        result = splitter.split(df, label_col="p1_zone")
        for fold_train, fold_val in result.cv_folds:
            assert len(set(fold_train) & set(fold_val)) == 0

    def test_split_stats_populated(self, splitter, df):
        result = splitter.split(df, label_col="p1_zone")
        assert result.split_stats["n_total"] == len(df)
        assert result.split_stats["n_train"] > 0
        assert result.split_stats["n_test"] > 0

    def test_split_label_dist_populated(self, splitter, df):
        result = splitter.split(df, label_col="p1_zone")
        assert "train_label_dist" in result.split_stats
        assert "test_label_dist" in result.split_stats

    def test_split_missing_label_col_raises(self, splitter, df):
        with pytest.raises(ValueError, match="label_col"):
            splitter.split(df, label_col="nonexistent_col")

    def test_split_with_nan_labels(self, splitter, df):
        df2 = df.copy()
        df2.loc[df2.index[:5], "p1_zone"] = float("nan")
        result = splitter.split(df2, label_col="p1_zone")
        # 应排除 NaN 行，总数应小
        assert len(result.train_idx) + len(result.test_idx) <= len(df)

    def test_split_p0_binary_label(self, splitter, df):
        result = splitter.split(df, label_col="p0_event")
        assert isinstance(result, SplitResult)
        assert len(result.train_idx) > 0

    def test_summary_returns_string(self, splitter, df):
        result = splitter.split(df, label_col="p1_zone")
        s = result.summary()
        assert isinstance(s, str)
        assert "DataSplitter" in s

    def test_random_seed_reproducibility(self, splitter, df):
        r1 = splitter.split(df, label_col="p1_zone")
        r2 = splitter.split(df, label_col="p1_zone")
        # 相同 seed 应产生相同分割
        assert list(r1.train_idx) == list(r2.train_idx)

    def test_small_df_fallback(self):
        """小样本 DataFrame 应能正常运行（降级 CV folds）。"""
        splitter = DataSplitter("configs/data/split_rules_v1.yaml")
        df_small = pd.DataFrame({
            "subject_id": [f"S{i}" for i in range(12)],
            "p1_zone": [0, 0, 0, 1, 1, 1, 2, 2, 2, 0, 1, 2],
        })
        result = splitter.split(df_small, label_col="p1_zone")
        assert len(result.cv_folds) >= 2
