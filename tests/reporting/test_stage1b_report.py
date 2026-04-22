"""
tests/reporting/test_stage1b_report.py — Stage 1B 总报告聚合测试。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.reporting.stage1b_report import (
    assess_acceptance,
    build_stage1b_output_table,
    compute_construct_validity,
    compute_reference_validity,
    generate_stage1b_summary_report,
)


# ─────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────

def _make_base_df(n: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    zones = rng.choice(["green", "yellow", "red"], n, p=[0.5, 0.3, 0.2])
    test_results = []
    for z in zones:
        if z == "green":
            test_results.append(rng.choice(["阴性", "阳性"], p=[0.9, 0.1]))
        elif z == "yellow":
            test_results.append(rng.choice(["阴性", "阳性"], p=[0.7, 0.3]))
        else:
            test_results.append(rng.choice(["阴性", "阳性"], p=[0.5, 0.5]))
    return pd.DataFrame({
        "reserve_burden": rng.uniform(0, 1, n),
        "vent_burden": rng.uniform(0, 1, n),
        "p_lab": rng.uniform(0, 1, n),
        "phenotype_zone": rng.choice(["green", "yellow", "red"], n, p=[0.6, 0.25, 0.15]),
        "instability_severe": rng.choice([False, True], n, p=[0.9, 0.1]),
        "instability_mild": rng.choice([False, True], n, p=[0.8, 0.2]),
        "final_zone_before_confidence": zones,
        "confidence_score": rng.uniform(0.4, 1.0, n),
        "confidence_label": rng.choice(["high", "medium", "low"], n, p=[0.3, 0.4, 0.3]),
        "indeterminate_flag": rng.choice([False, True], n, p=[0.8, 0.2]),
        "final_zone": zones,
        "test_result": test_results,
    })


def _make_monotone_df(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """构建 final_zone 与 test_result 严格单调的测试数据。"""
    rng = np.random.default_rng(seed)
    n_each = n // 3
    data = []
    for zone, pos_rate in [("green", 0.05), ("yellow", 0.25), ("red", 0.60)]:
        for _ in range(n_each):
            result = "阳性" if rng.random() < pos_rate else "阴性"
            data.append({"final_zone": zone, "test_result": result})
    return pd.DataFrame(data)


# ─────────────────────────────────────────────────────
# build_stage1b_output_table 测试
# ─────────────────────────────────────────────────────

class TestBuildStage1bOutputTable:

    def test_returns_dataframe(self):
        df = _make_base_df()
        out = build_stage1b_output_table(df)
        assert isinstance(out, pd.DataFrame)

    def test_preserves_base_columns(self):
        df = _make_base_df()
        out = build_stage1b_output_table(df)
        for col in ["final_zone", "confidence_label"]:
            assert col in out.columns

    def test_none_parquets_returns_base_df(self):
        df = _make_base_df()
        out = build_stage1b_output_table(df, phenotype_parquet=None, instability_parquet=None)
        assert len(out) == len(df)

    def test_nonexistent_parquet_logs_warning(self, tmp_path):
        df = _make_base_df()
        out = build_stage1b_output_table(
            df,
            phenotype_parquet=str(tmp_path / "nonexistent.parquet"),
        )
        assert isinstance(out, pd.DataFrame)

    def test_merges_phenotype_parquet(self, tmp_path):
        df = _make_base_df(n=50)
        pheno_df = pd.DataFrame({
            "reserve_burden": np.ones(50) * 0.999,
            "vent_burden": np.ones(50) * 0.888,
            "p_lab": np.ones(50) * 0.777,
            "phenotype_zone": ["red"] * 50,
        }, index=df.index)
        p = tmp_path / "pheno.parquet"
        pheno_df.to_parquet(p)
        out = build_stage1b_output_table(df, phenotype_parquet=str(p))
        # 应该从 parquet 中覆盖列
        assert (out["phenotype_zone"] == "red").all()

    def test_merges_outcome_parquet(self, tmp_path):
        df = _make_base_df(n=50)
        out_df = pd.DataFrame({
            "outcome_risk_prob": np.linspace(0.1, 0.9, 50),
            "outcome_risk_tertile": ["low"] * 17 + ["mid"] * 17 + ["high"] * 16,
        }, index=df.index)
        p = tmp_path / "outcome.parquet"
        out_df.to_parquet(p)
        result = build_stage1b_output_table(df, outcome_parquet=str(p))
        assert "outcome_risk_prob" in result.columns
        assert "outcome_risk_tertile" in result.columns

    def test_merges_anomaly_parquet(self, tmp_path):
        df = _make_base_df(n=50)
        anom_df = pd.DataFrame({
            "anomaly_score": np.random.uniform(0, 5, 50),
            "anomaly_flag": [False] * 45 + [True] * 5,
        }, index=df.index)
        p = tmp_path / "anomaly.parquet"
        anom_df.to_parquet(p)
        result = build_stage1b_output_table(df, anomaly_parquet=str(p))
        assert "anomaly_flag" in result.columns


# ─────────────────────────────────────────────────────
# compute_construct_validity 测试
# ─────────────────────────────────────────────────────

class TestComputeConstructValidity:

    def test_monotone_correct_direction(self):
        df = _make_monotone_df()
        cv = compute_construct_validity(df)
        assert cv["direction"] == "correct"
        assert cv["monotone_gradient"] is True

    def test_reversed_direction(self):
        df = _make_monotone_df()
        # 反转 zone 标签使方向相反
        reverse_map = {"green": "red", "red": "green", "yellow": "yellow"}
        df["final_zone"] = df["final_zone"].map(reverse_map)
        cv = compute_construct_validity(df)
        assert cv["direction"] in ("reversed", "non-monotone")
        assert cv["monotone_gradient"] is False

    def test_missing_zone_col_returns_insufficient(self):
        df = pd.DataFrame({"test_result": ["阳性", "阴性"]})
        cv = compute_construct_validity(df)
        assert cv["direction"] == "insufficient_data"

    def test_missing_test_result_col_returns_insufficient(self):
        df = pd.DataFrame({"final_zone": ["green", "red"]})
        cv = compute_construct_validity(df)
        assert cv["direction"] == "insufficient_data"

    def test_zone_positive_rates_in_0_1(self):
        df = _make_monotone_df()
        cv = compute_construct_validity(df)
        for zone, rate in cv["zone_positive_rates"].items():
            assert 0.0 <= rate <= 1.0, f"{zone} rate={rate} out of range"

    def test_empty_zone_returns_nan_rate(self):
        """某个 zone 无样本时 rate 应为 nan。"""
        df = pd.DataFrame({
            "final_zone": ["green"] * 50 + ["red"] * 50,
            "test_result": ["阴性"] * 40 + ["阳性"] * 10 + ["阴性"] * 20 + ["阳性"] * 30,
        })
        cv = compute_construct_validity(df)
        assert np.isnan(cv["zone_positive_rates"]["yellow"])
        assert cv["direction"] == "insufficient_data"

    def test_all_negative_returns_rate_zero(self):
        df = pd.DataFrame({
            "final_zone": ["green", "yellow", "red"],
            "test_result": ["阴性", "阴性", "阴性"],
        })
        cv = compute_construct_validity(df)
        for z in ["green", "yellow", "red"]:
            assert cv["zone_positive_rates"][z] == 0.0


# ─────────────────────────────────────────────────────
# compute_reference_validity 测试
# ─────────────────────────────────────────────────────

class TestComputeReferenceValidity:

    def test_good_reference_passes(self):
        n = 200
        zone = ["green"] * 140 + ["yellow"] * 50 + ["red"] * 10
        df = pd.DataFrame({"phenotype_zone": zone})
        mask = pd.Series([True] * n)
        rv = compute_reference_validity(df, reference_mask=mask)
        assert rv["reference_ok"] is True
        assert rv["green_pct"] > 0.50
        assert rv["red_pct"] < 0.15

    def test_bad_reference_fails(self):
        n = 100
        zone = ["green"] * 30 + ["yellow"] * 30 + ["red"] * 40
        df = pd.DataFrame({"phenotype_zone": zone})
        mask = pd.Series([True] * n)
        rv = compute_reference_validity(df, reference_mask=mask)
        assert rv["reference_ok"] is False

    def test_no_mask_returns_empty(self):
        df = _make_base_df()
        rv = compute_reference_validity(df, reference_mask=None)
        assert rv == {}

    def test_missing_zone_col_returns_empty(self):
        df = pd.DataFrame({"other": [1, 2, 3]})
        mask = pd.Series([True, True, False])
        rv = compute_reference_validity(df, zone_col="phenotype_zone", reference_mask=mask)
        assert rv == {}

    def test_empty_reference_returns_empty(self):
        df = _make_base_df()
        mask = pd.Series([False] * len(df), index=df.index)
        rv = compute_reference_validity(df, reference_mask=mask)
        assert rv == {}


# ─────────────────────────────────────────────────────
# assess_acceptance 测试
# ─────────────────────────────────────────────────────

class TestAssessAcceptance:

    def test_accept_verdict_good_data(self):
        df = _make_monotone_df(n=300)
        # 补充 confidence_label 使高置信度超过 10%
        df["confidence_label"] = ["high"] * 150 + ["medium"] * 100 + ["low"] * 50
        # reference mask 只取 green 样本（strict reference 应以 green 为主）
        df["phenotype_zone"] = df["final_zone"]
        green_idx = df[df["final_zone"] == "green"].index
        mask = pd.Series(False, index=df.index)
        mask[green_idx] = True
        verdict = assess_acceptance(df, reference_mask=mask)
        assert verdict["verdict"] in ("Accept", "Warn")

    def test_fail_on_reversed_gradient(self):
        df = _make_monotone_df()
        reverse_map = {"green": "red", "red": "green", "yellow": "yellow"}
        df["final_zone"] = df["final_zone"].map(reverse_map)
        verdict = assess_acceptance(df)
        assert verdict["verdict"] == "Fail"
        assert "reversed" in verdict["reason"]

    def test_warn_on_high_red_in_reference(self):
        df = _make_base_df(n=200)
        df["phenotype_zone"] = ["red"] * 100 + ["green"] * 100
        mask = pd.Series([True] * 200, index=df.index)
        verdict = assess_acceptance(df, reference_mask=mask)
        assert verdict["verdict"] in ("Warn", "Fail")

    def test_returns_dict_with_required_keys(self):
        df = _make_base_df()
        verdict = assess_acceptance(df)
        assert "verdict" in verdict
        assert "reason" in verdict
        assert "details" in verdict

    def test_verdict_values_valid(self):
        df = _make_base_df()
        verdict = assess_acceptance(df)
        assert verdict["verdict"] in ("Accept", "Warn", "Fail")

    def test_low_confidence_warns(self):
        df = _make_monotone_df(n=300)
        df["phenotype_zone"] = df["final_zone"]
        # 全部 low confidence
        df["confidence_label"] = "low"
        verdict = assess_acceptance(df)
        # 低 high confidence 比例应触发 warn
        assert verdict["verdict"] in ("Warn", "Fail")


# ─────────────────────────────────────────────────────
# generate_stage1b_summary_report 测试
# ─────────────────────────────────────────────────────

class TestGenerateStage1bSummaryReport:

    def test_report_is_string(self):
        df = _make_base_df()
        report = generate_stage1b_summary_report(df)
        assert isinstance(report, str)

    def test_report_not_empty(self):
        df = _make_base_df()
        report = generate_stage1b_summary_report(df)
        assert len(report) > 100

    def test_report_contains_summary_header(self):
        df = _make_base_df()
        report = generate_stage1b_summary_report(df)
        assert "Stage 1B" in report

    def test_report_saved_to_file(self, tmp_path):
        df = _make_base_df()
        out = tmp_path / "report.md"
        generate_stage1b_summary_report(df, output_path=out)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert len(content) > 100

    def test_report_with_reference_mask(self):
        df = _make_base_df(n=100)
        mask = pd.Series([True] * 60 + [False] * 40, index=df.index)
        report = generate_stage1b_summary_report(df, reference_mask=mask)
        assert isinstance(report, str)
        assert "参考" in report

    def test_final_zone_distribution_in_report(self):
        df = _make_base_df()
        report = generate_stage1b_summary_report(df)
        assert "final_zone" in report

    def test_confidence_distribution_in_report(self):
        df = _make_base_df()
        report = generate_stage1b_summary_report(df)
        assert "置信度" in report

    def test_verdict_in_report(self):
        df = _make_base_df()
        report = generate_stage1b_summary_report(df)
        assert any(v in report for v in ["Accept", "Warn", "Fail"])

    def test_with_legacy_col(self):
        df = _make_base_df()
        df["zone_v2"] = df["final_zone"]
        report = generate_stage1b_summary_report(df)
        assert "Legacy" in report or "legacy" in report.lower() or "zone_v2" in report

    def test_with_outcome_risk_prob(self):
        df = _make_base_df()
        df["outcome_risk_prob"] = np.random.uniform(0, 1, len(df))
        report = generate_stage1b_summary_report(df)
        assert "Outcome" in report or "outcome" in report.lower()

    def test_report_no_nan_in_metrics(self):
        """报告中不应出现 'nan%' 这样的格式错误。"""
        df = _make_base_df()
        report = generate_stage1b_summary_report(df)
        assert "nan%" not in report

    def test_minimal_df_no_crash(self):
        """极简 DataFrame 不应崩溃。"""
        df = pd.DataFrame({"id": [1, 2, 3]})
        report = generate_stage1b_summary_report(df)
        assert isinstance(report, str)
