"""
tests/anchors/test_phenotype_engine.py — Phenotype Burden Engine 测试。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.anchors.phenotype_engine import (
    Direction,
    PhenotypeResult,
    VariableSpec,
    assign_phenotype_zone,
    compute_variable_burden,
    estimate_cutpoints_from_reference,
    generate_phenotype_report,
    load_variable_specs_from_yaml,
    run_phenotype_engine,
)


# ─────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────

def _make_quantiles(n: int = 100, seed: int = 1) -> pd.DataFrame:
    """生成模拟分位表（模拟 reference_quantiles.py 的输出）。"""
    rng = np.random.default_rng(seed)
    base = rng.uniform(10, 30, n)
    df = pd.DataFrame(index=range(n))
    df["vo2_peak_q10"] = base - 8
    df["vo2_peak_q25"] = base - 4
    df["vo2_peak_q50"] = base
    df["vo2_peak_q75"] = base + 4
    df["vo2_peak_q90"] = base + 8

    ve_base = rng.uniform(28, 36, n)
    df["ve_vco2_slope_q10"] = ve_base - 6
    df["ve_vco2_slope_q25"] = ve_base - 3
    df["ve_vco2_slope_q50"] = ve_base
    df["ve_vco2_slope_q75"] = ve_base + 3
    df["ve_vco2_slope_q90"] = ve_base + 6

    return df


def _make_df(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """生成包含 CPET 变量的测试数据。"""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "vo2_peak": rng.uniform(8, 35, n),
        "ve_vco2_slope": rng.uniform(22, 42, n),
        "oues": rng.uniform(600, 2800, n),
        "o2_pulse_peak": rng.uniform(5, 20, n),
        "mets_peak": rng.uniform(2, 14, n),
        "vt1_vo2": rng.uniform(7, 25, n),
    })


def _default_specs() -> list[VariableSpec]:
    return [
        VariableSpec("vo2_peak", "higher_better", "reserve", required=True),
        VariableSpec("o2_pulse_peak", "higher_better", "reserve"),
        VariableSpec("ve_vco2_slope", "higher_worse", "ventilatory", required=True),
    ]


# ─────────────────────────────────────────────────────
# compute_variable_burden 测试
# ─────────────────────────────────────────────────────

class TestComputeVariableBurden:

    def test_higher_better_good_value(self):
        """高于 q25 → burden=0。"""
        values = pd.Series([25.0])
        quantiles = pd.DataFrame({"vo2_peak_q10": [10.0], "vo2_peak_q25": [15.0]})
        burden = compute_variable_burden(values, quantiles, field="vo2_peak", direction="higher_better")
        assert burden.iloc[0] == 0.0

    def test_higher_better_borderline(self):
        """q10 <= x < q25 → burden=0.5。"""
        values = pd.Series([12.0])
        quantiles = pd.DataFrame({"vo2_peak_q10": [10.0], "vo2_peak_q25": [15.0]})
        burden = compute_variable_burden(values, quantiles, field="vo2_peak", direction="higher_better")
        assert burden.iloc[0] == 0.5

    def test_higher_better_poor(self):
        """低于 q10 → burden=1.0。"""
        values = pd.Series([5.0])
        quantiles = pd.DataFrame({"vo2_peak_q10": [10.0], "vo2_peak_q25": [15.0]})
        burden = compute_variable_burden(values, quantiles, field="vo2_peak", direction="higher_better")
        assert burden.iloc[0] == 1.0

    def test_higher_worse_good_value(self):
        """低于 q75 → burden=0。"""
        values = pd.Series([28.0])
        quantiles = pd.DataFrame({"ve_vco2_slope_q75": [32.0], "ve_vco2_slope_q90": [38.0]})
        burden = compute_variable_burden(values, quantiles, field="ve_vco2_slope", direction="higher_worse")
        assert burden.iloc[0] == 0.0

    def test_higher_worse_borderline(self):
        """q75 < x <= q90 → burden=0.5。"""
        values = pd.Series([35.0])
        quantiles = pd.DataFrame({"ve_vco2_slope_q75": [32.0], "ve_vco2_slope_q90": [38.0]})
        burden = compute_variable_burden(values, quantiles, field="ve_vco2_slope", direction="higher_worse")
        assert burden.iloc[0] == 0.5

    def test_higher_worse_poor(self):
        """高于 q90 → burden=1.0。"""
        values = pd.Series([42.0])
        quantiles = pd.DataFrame({"ve_vco2_slope_q75": [32.0], "ve_vco2_slope_q90": [38.0]})
        burden = compute_variable_burden(values, quantiles, field="ve_vco2_slope", direction="higher_worse")
        assert burden.iloc[0] == 1.0

    def test_nan_input_returns_nan(self):
        """NaN 输入 → NaN burden。"""
        values = pd.Series([np.nan])
        quantiles = pd.DataFrame({"vo2_peak_q10": [10.0], "vo2_peak_q25": [15.0]})
        burden = compute_variable_burden(values, quantiles, field="vo2_peak", direction="higher_better")
        assert np.isnan(burden.iloc[0])

    def test_missing_quantile_columns_returns_nan(self):
        """缺少分位列时返回 NaN（不报错）。"""
        values = pd.Series([20.0])
        quantiles = pd.DataFrame({"unrelated_col": [5.0]})
        burden = compute_variable_burden(values, quantiles, field="vo2_peak", direction="higher_better")
        assert np.isnan(burden.iloc[0])

    def test_burden_values_are_in_set(self):
        """所有非 NaN burden 值应在 {0, 0.5, 1}。"""
        n = 50
        rng = np.random.default_rng(0)
        values = pd.Series(rng.uniform(5, 30, n))
        quantiles = pd.DataFrame({
            "vo2_peak_q10": np.full(n, 10.0),
            "vo2_peak_q25": np.full(n, 15.0),
        })
        burden = compute_variable_burden(values, quantiles, field="vo2_peak", direction="higher_better")
        valid = burden.dropna()
        assert set(valid.unique()).issubset({0.0, 0.5, 1.0})


# ─────────────────────────────────────────────────────
# estimate_cutpoints_from_reference 测试
# ─────────────────────────────────────────────────────

class TestEstimateCutpoints:

    def test_returns_tuple_of_floats(self):
        p_lab = pd.Series(np.linspace(0, 1, 100))
        ref_mask = pd.Series(True, index=p_lab.index)
        low, high = estimate_cutpoints_from_reference(p_lab, ref_mask)
        assert isinstance(low, float) and isinstance(high, float)

    def test_low_lt_high(self):
        p_lab = pd.Series(np.linspace(0, 1, 200))
        ref_mask = pd.Series(True, index=p_lab.index)
        low, high = estimate_cutpoints_from_reference(p_lab, ref_mask)
        assert low < high

    def test_too_small_reference_raises(self):
        p_lab = pd.Series(np.linspace(0, 1, 100))
        ref_mask = pd.Series([True] * 10 + [False] * 90)
        with pytest.raises(ValueError, match="too small"):
            estimate_cutpoints_from_reference(p_lab, ref_mask, min_ref_n=30)

    def test_custom_percentiles(self):
        p_lab = pd.Series(np.linspace(0, 1, 200))
        ref_mask = pd.Series(True, index=p_lab.index)
        low_50, high_90 = estimate_cutpoints_from_reference(
            p_lab, ref_mask, low_pct=50.0, high_pct=90.0
        )
        # p50 ≈ 0.5, p90 ≈ 0.9
        assert abs(low_50 - 0.5) < 0.05
        assert abs(high_90 - 0.9) < 0.05


# ─────────────────────────────────────────────────────
# assign_phenotype_zone 测试
# ─────────────────────────────────────────────────────

class TestAssignPhenotypeZone:

    def test_basic_assignment(self):
        p_lab = pd.Series([0.1, 0.5, 0.9])
        zone = assign_phenotype_zone(p_lab, low_cut=0.3, high_cut=0.7)
        assert zone.iloc[0] == "green"
        assert zone.iloc[1] == "yellow"
        assert zone.iloc[2] == "red"

    def test_nan_input_returns_nan(self):
        p_lab = pd.Series([np.nan])
        zone = assign_phenotype_zone(p_lab, low_cut=0.3, high_cut=0.7)
        assert pd.isna(zone.iloc[0])

    def test_boundary_at_low_cut(self):
        """等于 low_cut 时应为 yellow。"""
        p_lab = pd.Series([0.3])
        zone = assign_phenotype_zone(p_lab, low_cut=0.3, high_cut=0.7)
        assert zone.iloc[0] == "yellow"

    def test_boundary_at_high_cut(self):
        """等于 high_cut 时应为 red。"""
        p_lab = pd.Series([0.7])
        zone = assign_phenotype_zone(p_lab, low_cut=0.3, high_cut=0.7)
        assert zone.iloc[0] == "red"


# ─────────────────────────────────────────────────────
# run_phenotype_engine 测试
# ─────────────────────────────────────────────────────

class TestRunPhenotypeEngine:

    def test_returns_phenotype_result(self):
        df = _make_df()
        quantiles = _make_quantiles()
        specs = _default_specs()
        ref_mask = pd.Series(True, index=df.index)
        result = run_phenotype_engine(df, quantiles, specs, ref_mask)
        assert isinstance(result, PhenotypeResult)

    def test_output_columns_present(self):
        df = _make_df()
        quantiles = _make_quantiles()
        specs = _default_specs()
        ref_mask = pd.Series(True, index=df.index)
        result = run_phenotype_engine(df, quantiles, specs, ref_mask)
        assert "reserve_burden" in result.df.columns
        assert "vent_burden" in result.df.columns
        assert "p_lab" in result.df.columns
        assert "phenotype_zone" in result.df.columns

    def test_zone_values_valid(self):
        """所有非 NaN zone 值应在 {green, yellow, red}。"""
        df = _make_df()
        quantiles = _make_quantiles()
        specs = _default_specs()
        ref_mask = pd.Series(True, index=df.index)
        result = run_phenotype_engine(df, quantiles, specs, ref_mask)
        valid_zones = result.df["phenotype_zone"].dropna().unique()
        assert set(valid_zones).issubset({"green", "yellow", "red"})

    def test_burden_values_in_set(self):
        """所有非 NaN burden 值应在 {0, 0.5, 1}。"""
        df = _make_df()
        quantiles = _make_quantiles()
        specs = _default_specs()
        ref_mask = pd.Series(True, index=df.index)
        result = run_phenotype_engine(df, quantiles, specs, ref_mask)
        for spec in specs:
            bcol = f"{spec.field}_burden"
            if bcol in result.df.columns:
                valid = result.df[bcol].dropna()
                assert set(valid.unique()).issubset({0.0, 0.5, 1.0}), f"{bcol} 含无效值"

    def test_reference_green_majority(self):
        """在参考子集中，green 应占多数（>50%）。

        数学原理：cutpoints = P75/P90 of reference p_lab →
        只要 p_lab 分布非退化，75% reference 自然落在 P75 以下 (green)。
        构造连续分布的 p_lab（混合 burden 0/0.5/1 各级占比）。
        """
        rng = np.random.default_rng(0)
        n = 200
        # 均匀混合三个 burden 等级：各占约 1/3
        vo2_values = np.concatenate([
            rng.uniform(19, 30, n // 3),    # burden=0 (>= q25)
            rng.uniform(8, 10, n // 3),     # burden=1 (< q10)
            rng.uniform(10, 18, n - 2 * (n // 3)),  # burden=0.5 (q10..q25)
        ])
        ve_values = np.concatenate([
            rng.uniform(24, 34, n // 3),    # burden=0 (<= q75)
            rng.uniform(43, 50, n // 3),    # burden=1 (> q90)
            rng.uniform(36, 42, n - 2 * (n // 3)),  # burden=0.5 (q75..q90)
        ])

        df = pd.DataFrame({"vo2_peak": vo2_values, "ve_vco2_slope": ve_values})
        quantiles = pd.DataFrame({
            "vo2_peak_q10": np.full(n, 10.0),
            "vo2_peak_q25": np.full(n, 18.0),
            "vo2_peak_q75": np.full(n, 32.0),
            "vo2_peak_q90": np.full(n, 40.0),
            "ve_vco2_slope_q75": np.full(n, 36.0),
            "ve_vco2_slope_q90": np.full(n, 42.0),
        })
        specs = [
            VariableSpec("vo2_peak", "higher_better", "reserve"),
            VariableSpec("ve_vco2_slope", "higher_worse", "ventilatory"),
        ]
        ref_mask = pd.Series(True, index=df.index)
        result = run_phenotype_engine(df, quantiles, specs, ref_mask, low_pct=75.0, high_pct=90.0)
        # 宽松验证：参考子集中 green ≥ 50%（数学保证是 75%，但切点退化时可能低于）
        n_green_ref = result.df.loc[ref_mask, "phenotype_zone"].eq("green").sum()
        assert n_green_ref / n >= 0.50, f"green rate={n_green_ref/n:.2f}"

    def test_reference_red_less_than_15pct(self):
        """在参考子集中，red 应 < 15%。"""
        rng = np.random.default_rng(0)
        n = 200
        df = pd.DataFrame({
            "vo2_peak": rng.uniform(18, 35, n),
            "ve_vco2_slope": rng.uniform(24, 34, n),
        })
        quantiles = pd.DataFrame({
            "vo2_peak_q10": np.full(n, 8.0),
            "vo2_peak_q25": np.full(n, 15.0),
            "vo2_peak_q75": np.full(n, 32.0),
            "vo2_peak_q90": np.full(n, 38.0),
            "ve_vco2_slope_q75": np.full(n, 36.0),
            "ve_vco2_slope_q90": np.full(n, 42.0),
        })
        specs = [
            VariableSpec("vo2_peak", "higher_better", "reserve"),
            VariableSpec("ve_vco2_slope", "higher_worse", "ventilatory"),
        ]
        ref_mask = pd.Series(True, index=df.index)
        result = run_phenotype_engine(df, quantiles, specs, ref_mask, low_pct=75.0, high_pct=90.0)
        n_red_ref = result.df.loc[ref_mask, "phenotype_zone"].eq("red").sum()
        assert n_red_ref / n < 0.15, f"red rate={n_red_ref/n:.2f}"

    def test_missing_field_skipped_gracefully(self):
        """数据中缺少某个变量字段时不应崩溃。"""
        df = _make_df()
        df = df.drop(columns=["oues"], errors="ignore")
        quantiles = _make_quantiles()
        specs = [
            VariableSpec("vo2_peak", "higher_better", "reserve"),
            VariableSpec("oues", "higher_better", "ventilatory"),  # 不存在
            VariableSpec("ve_vco2_slope", "higher_worse", "ventilatory"),
        ]
        ref_mask = pd.Series(True, index=df.index)
        result = run_phenotype_engine(df, quantiles, specs, ref_mask)
        assert "phenotype_zone" in result.df.columns

    def test_summary_method(self):
        df = _make_df()
        quantiles = _make_quantiles()
        specs = _default_specs()
        ref_mask = pd.Series(True, index=df.index)
        result = run_phenotype_engine(df, quantiles, specs, ref_mask)
        summary = result.summary()
        assert "Green" in summary
        assert "Red" in summary


# ─────────────────────────────────────────────────────
# load_variable_specs_from_yaml 测试
# ─────────────────────────────────────────────────────

class TestLoadVariableSpecs:

    def test_loads_from_zone_rules(self):
        specs = load_variable_specs_from_yaml("configs/data/zone_rules_stage1b.yaml")
        assert len(specs) > 0

    def test_domains_correct(self):
        specs = load_variable_specs_from_yaml("configs/data/zone_rules_stage1b.yaml")
        domains = {s.domain for s in specs}
        assert domains.issubset({"reserve", "ventilatory"})

    def test_directions_valid(self):
        specs = load_variable_specs_from_yaml("configs/data/zone_rules_stage1b.yaml")
        directions = {s.direction for s in specs}
        assert directions.issubset({"higher_better", "higher_worse"})

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_variable_specs_from_yaml("nonexistent.yaml")


# ─────────────────────────────────────────────────────
# generate_phenotype_report 测试
# ─────────────────────────────────────────────────────

class TestGeneratePhenotypeReport:

    def _run_engine(self):
        df = _make_df()
        quantiles = _make_quantiles()
        specs = _default_specs()
        ref_mask = pd.Series(True, index=df.index)
        return run_phenotype_engine(df, quantiles, specs, ref_mask), df

    def test_report_is_string(self):
        result, _ = self._run_engine()
        report = generate_phenotype_report(result)
        assert isinstance(report, str)
        assert "phenotype_zone" in report.lower() or "Zone" in report

    def test_report_saved_to_file(self, tmp_path):
        result, _ = self._run_engine()
        out = tmp_path / "report.md"
        generate_phenotype_report(result, output_path=out)
        assert out.exists()

    def test_report_with_test_result(self):
        result, df = self._run_engine()
        df_orig = df.copy()
        df_orig["test_result"] = ["阳性" if i % 5 == 0 else "阴性" for i in range(len(df))]
        report = generate_phenotype_report(result, df_original=df_orig)
        assert "构念效度" in report
