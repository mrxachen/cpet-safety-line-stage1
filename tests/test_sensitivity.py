"""
test_sensitivity.py — 敏感性分析模块单元测试
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.stats.sensitivity_analysis import (
    SensitivityResult,
    generate_sensitivity_report,
    run_sensitivity_suite,
)


def _make_staging(n: int = 90) -> pd.DataFrame:
    """构建最小 staging DataFrame。"""
    rng = np.random.default_rng(7)
    zones = ["green", "yellow", "red"] * (n // 3) + ["green"] * (n % 3)
    test_results = ["阳性" if rng.random() < 0.20 else "阴性" for _ in range(n)]
    return pd.DataFrame({
        "test_result": test_results,
        "vo2_peak": rng.uniform(10, 40, n),
        "ve_vco2_slope": rng.uniform(20, 45, n),
        "age": rng.integers(40, 80, n).astype(float),
        "bmi": rng.uniform(18, 35, n),
    })


def _make_output(df_staging: pd.DataFrame) -> pd.DataFrame:
    """构建最小输出表 DataFrame。"""
    n = len(df_staging)
    rng = np.random.default_rng(7)
    zones = ["green", "yellow", "red"] * (n // 3) + ["green"] * (n % 3)
    return pd.DataFrame({
        "final_zone": zones,
        "phenotype_zone": zones,
        "confidence_score": rng.uniform(0.4, 1.0, n),
        "confidence_label": ["high"] * (n // 3) + ["medium"] * (n // 3) + ["low"] * (n - 2 * (n // 3)),
        "red_source": ["red_override" if z == "red" and i % 2 == 0 else (
            "red_phenotype" if z == "red" else np.nan) for i, z in enumerate(zones)],
        "p_lab": rng.uniform(0, 1.0, n),
        "test_result": df_staging["test_result"].values,
        "anchor_agreement": rng.choice([0.0, 0.5, 1.0], n).astype(float),
        "validation_agreement": rng.choice([0.0, 0.5, 1.0], n).astype(float),
        "instability_severe": [False] * n,
    }, index=df_staging.index)


# ─────────────────────────────────────────────────────
# run_sensitivity_suite
# ─────────────────────────────────────────────────────

class TestRunSensitivitySuite:

    def test_returns_sensitivity_result(self):
        df = _make_staging()
        result = run_sensitivity_suite(df)
        assert isinstance(result, SensitivityResult)

    def test_with_output_table(self):
        df = _make_staging()
        df_out = _make_output(df)
        result = run_sensitivity_suite(df, df_output=df_out)
        assert isinstance(result, SensitivityResult)
        # SA-4 should work with red_source
        assert "n_red_total" in result.sa4_red_split

    def test_sa1_reference(self):
        df = _make_staging()
        df_out = _make_output(df)
        result = run_sensitivity_suite(df, df_output=df_out)
        assert result.sa1_reference.get("label", "").startswith("SA-1")

    def test_sa2_phenotype_cut(self):
        df = _make_staging()
        df_out = _make_output(df)
        result = run_sensitivity_suite(df, df_output=df_out)
        # Should have cutpoints info since p_lab is in output
        assert "cutpoints" in result.sa2_phenotype_cut or "note" in result.sa2_phenotype_cut

    def test_sa3_confidence_threshold(self):
        df = _make_staging()
        df_out = _make_output(df)
        result = run_sensitivity_suite(df, df_output=df_out)
        assert "high_confidence_pct_by_threshold" in result.sa3_confidence_threshold

    def test_sa4_red_split(self):
        df = _make_staging()
        df_out = _make_output(df)
        result = run_sensitivity_suite(df, df_output=df_out)
        assert "n_red_total" in result.sa4_red_split

    def test_sa5_outcome_anchor(self):
        df = _make_staging()
        result = run_sensitivity_suite(df)
        assert "fix" in result.sa5_outcome_anchor

    def test_baseline_from_output_table(self):
        df = _make_staging()
        df_out = _make_output(df)
        result = run_sensitivity_suite(df, df_output=df_out)
        assert result.baseline.get("n", 0) > 0

    def test_no_output_table(self):
        df = _make_staging()
        result = run_sensitivity_suite(df, df_output=None)
        # Should not crash, baseline may be empty
        assert isinstance(result, SensitivityResult)


# ─────────────────────────────────────────────────────
# generate_sensitivity_report
# ─────────────────────────────────────────────────────

class TestGenerateSensitivityReport:

    def test_returns_string(self):
        df = _make_staging()
        result = run_sensitivity_suite(df)
        report = generate_sensitivity_report(result)
        assert isinstance(report, str)
        assert len(report) > 100

    def test_contains_sa_sections(self):
        df = _make_staging()
        df_out = _make_output(df)
        result = run_sensitivity_suite(df, df_output=df_out)
        report = generate_sensitivity_report(result)
        assert "SA-1" in report
        assert "SA-2" in report
        assert "SA-3" in report
        assert "SA-4" in report
        assert "SA-5" in report

    def test_saves_to_file(self, tmp_path):
        df = _make_staging()
        result = run_sensitivity_suite(df)
        output_path = tmp_path / "sensitivity_report.md"
        generate_sensitivity_report(result, output_path=output_path)
        assert output_path.exists()

    def test_baseline_section_present(self):
        df = _make_staging()
        df_out = _make_output(df)
        result = run_sensitivity_suite(df, df_output=df_out)
        report = generate_sensitivity_report(result)
        assert "Baseline" in report
