"""
test_stratified_validation.py — 分层验证矩阵模块单元测试
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.stats.stratified_validation import (
    StratifiedValidationResult,
    _zone_positive_rates,
    generate_stratified_validation_report,
    run_stratified_validation,
)


def _make_df(n: int = 90) -> pd.DataFrame:
    """构建含所有必要列的测试 DataFrame。"""
    rng = np.random.default_rng(42)

    # zone 分配（等比例）
    zones = ["green", "yellow", "red"] * (n // 3) + ["green"] * (n % 3)
    # 阳性率梯度：green < yellow < red（正确方向）
    pos_rate = {"green": 0.10, "yellow": 0.20, "red": 0.40}
    test_result = []
    for z in zones:
        if rng.random() < pos_rate[z]:
            test_result.append("阳性")
        else:
            test_result.append("阴性")

    df = pd.DataFrame({
        "phenotype_zone": zones,
        "final_zone": zones,
        "test_result": test_result,
        "instability_severe": [False] * n,
        "confidence_label": ["high"] * (n // 2) + ["medium"] * (n - n // 2),
    })
    return df


def _make_df_non_monotone() -> pd.DataFrame:
    """构建 non-monotone 方向的测试 DataFrame。"""
    n = 90
    zones = ["green", "yellow", "red"] * (n // 3)
    # non-monotone: green > red
    pos_rate = {"green": 0.40, "yellow": 0.20, "red": 0.10}
    rng = np.random.default_rng(0)
    test_result = ["阳性" if rng.random() < pos_rate[z] else "阴性" for z in zones]
    return pd.DataFrame({
        "phenotype_zone": zones,
        "final_zone": zones,
        "test_result": test_result,
        "instability_severe": [False] * n,
        "confidence_label": ["high"] * n,
    })


# ─────────────────────────────────────────────────────
# _zone_positive_rates
# ─────────────────────────────────────────────────────

class TestZonePositiveRates:

    def test_returns_rates_for_each_zone(self):
        df = _make_df()
        result = _zone_positive_rates(df, "final_zone", "test_result")
        assert "positive_rates" in result
        assert "green" in result["positive_rates"]
        assert "red" in result["positive_rates"]

    def test_missing_column_returns_error(self):
        df = _make_df()
        result = _zone_positive_rates(df, "nonexistent_zone", "test_result")
        assert "error" in result

    def test_correct_direction_detected(self):
        df = _make_df()
        result = _zone_positive_rates(df, "final_zone", "test_result")
        assert result["direction"] == "correct"
        assert result["monotone_gradient"] is True

    def test_reversed_direction_detected(self):
        df = _make_df_non_monotone()
        result = _zone_positive_rates(df, "final_zone", "test_result")
        # 方向可能是 "reversed" 或 "non-monotone"，均不应为 "correct"
        assert result["direction"] != "correct"
        assert result["monotone_gradient"] is False


# ─────────────────────────────────────────────────────
# run_stratified_validation
# ─────────────────────────────────────────────────────

class TestRunStratifiedValidation:

    def test_returns_result_object(self):
        df = _make_df()
        result = run_stratified_validation(df)
        assert isinstance(result, StratifiedValidationResult)

    def test_group3_final_zone(self):
        df = _make_df()
        result = run_stratified_validation(df)
        assert "direction" in result.group3_final_zone

    def test_group1_phenotype_zone(self):
        df = _make_df()
        result = run_stratified_validation(df)
        assert "direction" in result.group1_phenotype

    def test_group2_instability(self):
        n = 30
        df_data = {
            "final_zone": ["green"] * 10 + ["red"] * 10 + ["yellow"] * 10,
            "phenotype_zone": ["green"] * 10 + ["red"] * 10 + ["yellow"] * 10,
            "test_result": ["阳性"] * 5 + ["阴性"] * 5 + ["阳性"] * 8 + ["阴性"] * 2 + ["阴性"] * 10,
            "instability_severe": [False] * 10 + [True] * 10 + [False] * 10,
            "confidence_label": ["high"] * n,
        }
        df = pd.DataFrame(df_data)
        result = run_stratified_validation(df)
        assert "severe_n" in result.group2_instability
        assert result.group2_instability["severe_n"] == 10

    def test_group4_high_confidence(self):
        df = _make_df()
        result = run_stratified_validation(df)
        # 高置信度子集应比全量小
        n_all = result.group3_final_zone.get("n_total", 0)
        n_high = result.group4_high_conf.get("n_subset", 0)
        assert n_high <= n_all

    def test_group5_no_override(self):
        n = 30
        df = pd.DataFrame({
            "phenotype_zone": ["green"] * 10 + ["yellow"] * 10 + ["red"] * 10,
            "final_zone": ["green"] * 10 + ["yellow"] * 10 + ["red"] * 10,
            "test_result": ["阴性"] * 20 + ["阳性"] * 10,
            "instability_severe": [True] * 5 + [False] * 25,
            "confidence_label": ["high"] * n,
        })
        result = run_stratified_validation(df)
        # 去掉 severe(5 个) 后应有 25 个
        assert result.group5_phenotype_no_override.get("n_subset") == 25

    def test_missing_test_result_col(self):
        df = _make_df().drop(columns=["test_result"])
        result = run_stratified_validation(df)
        # 所有组应返回 error 或 insufficient_data
        for group in [result.group3_final_zone, result.group1_phenotype]:
            dir_val = group.get("direction")
            assert dir_val in [None, "insufficient_data"] or "error" in group


# ─────────────────────────────────────────────────────
# generate_stratified_validation_report
# ─────────────────────────────────────────────────────

class TestGenerateStratifiedValidationReport:

    def test_returns_string(self):
        df = _make_df()
        result = run_stratified_validation(df)
        report = generate_stratified_validation_report(result)
        assert isinstance(report, str)
        assert len(report) > 100

    def test_contains_all_groups(self):
        df = _make_df()
        result = run_stratified_validation(df)
        report = generate_stratified_validation_report(result)
        assert "Group 1" in report
        assert "Group 2" in report
        assert "Group 3" in report
        assert "Group 4" in report
        assert "Group 5" in report

    def test_summary_table_present(self):
        df = _make_df()
        result = run_stratified_validation(df)
        report = generate_stratified_validation_report(result)
        assert "汇总对比" in report

    def test_saves_to_file(self, tmp_path):
        df = _make_df()
        result = run_stratified_validation(df)
        output_path = tmp_path / "test_stratified_report.md"
        generate_stratified_validation_report(result, output_path=output_path)
        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert len(content) > 100
