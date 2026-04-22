"""
tests/anchors/test_instability_rules.py — Instability Override Engine 测试。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.anchors.instability_rules import (
    InstabilityResult,
    RuleConfig,
    apply_override,
    evaluate_instability,
    generate_instability_report,
    load_instability_rules,
    run_instability_engine,
    _evaluate_rule,
)


# ─────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────

def _make_df(n: int = 50, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "eih_status": rng.choice([False, True], n, p=[0.85, 0.15]),
        "bp_peak_sys": rng.uniform(150, 230, n),
        "bp_peak_dia": rng.uniform(80, 115, n),
        "o2_pulse_trajectory": rng.choice(
            ["正常", "下降", "上升", "晚期下降", "持续平台"], n
        ),
        "effort_adequacy": rng.choice(["adequate", "uncertain", "inadequate"], n),
    })


def _default_severe_rules() -> list[RuleConfig]:
    return [
        RuleConfig("eih_status", "eq", value=True),
        RuleConfig("bp_peak_sys", "gt", value=220),
        RuleConfig("bp_peak_dia", "gt", value=110),
        RuleConfig("o2_pulse_trajectory", "in", value=["下降", "晚期下降", "运动终止前下降", "持续平台", "晚期平台"]),
    ]


def _default_mild_rules() -> list[RuleConfig]:
    return [
        RuleConfig("bp_peak_sys", "between_open_closed", low=200, high=220),
        RuleConfig("effort_adequacy", "eq", value="uncertain"),
    ]


# ─────────────────────────────────────────────────────
# _evaluate_rule 测试
# ─────────────────────────────────────────────────────

class TestEvaluateRule:

    def test_eq_bool_true(self):
        df = pd.DataFrame({"eih_status": [True, False, True]})
        rule = RuleConfig("eih_status", "eq", value=True)
        result = _evaluate_rule(df, rule)
        assert list(result) == [True, False, True]

    def test_eq_string_true(self):
        df = pd.DataFrame({"eih_status": ["True", "False", "true"]})
        rule = RuleConfig("eih_status", "eq", value=True)
        result = _evaluate_rule(df, rule)
        assert list(result) == [True, False, True]

    def test_gt_numeric(self):
        df = pd.DataFrame({"bp_peak_sys": [200.0, 220.0, 225.0, None]})
        rule = RuleConfig("bp_peak_sys", "gt", value=220)
        result = _evaluate_rule(df, rule)
        assert list(result) == [False, False, True, False]

    def test_in_string(self):
        df = pd.DataFrame({"o2_pulse_trajectory": ["正常", "下降", "晚期下降"]})
        rule = RuleConfig("o2_pulse_trajectory", "in", value=["下降", "晚期下降"])
        result = _evaluate_rule(df, rule)
        assert list(result) == [False, True, True]

    def test_between_open_closed(self):
        df = pd.DataFrame({"bp_peak_sys": [195.0, 200.0, 210.0, 220.0, 225.0]})
        rule = RuleConfig("bp_peak_sys", "between_open_closed", low=200, high=220)
        result = _evaluate_rule(df, rule)
        # > 200 and <= 220
        assert list(result) == [False, False, True, True, False]

    def test_missing_field_returns_false(self):
        df = pd.DataFrame({"other_col": [1, 2, 3]})
        rule = RuleConfig("eih_status", "eq", value=True)
        result = _evaluate_rule(df, rule)
        assert list(result) == [False, False, False]

    def test_nan_value_returns_false(self):
        """NaN 值不应误触发 severe。"""
        df = pd.DataFrame({"bp_peak_sys": [np.nan, np.nan]})
        rule = RuleConfig("bp_peak_sys", "gt", value=220)
        result = _evaluate_rule(df, rule)
        assert list(result) == [False, False]

    def test_unsupported_op_raises(self):
        df = pd.DataFrame({"x": [1]})
        rule = RuleConfig("x", "unknown_op", value=1)
        with pytest.raises(ValueError, match="Unsupported"):
            _evaluate_rule(df, rule)


# ─────────────────────────────────────────────────────
# evaluate_instability 测试
# ─────────────────────────────────────────────────────

class TestEvaluateInstability:

    def test_returns_two_columns(self):
        df = _make_df()
        severe_rules = _default_severe_rules()
        mild_rules = _default_mild_rules()
        result = evaluate_instability(df, severe_rules, mild_rules)
        assert "instability_severe" in result.columns
        assert "instability_mild" in result.columns

    def test_severe_with_eih(self):
        """eih_status=True → severe=True。"""
        df = pd.DataFrame({"eih_status": [True, False]})
        severe_rules = [RuleConfig("eih_status", "eq", value=True)]
        mild_rules: list[RuleConfig] = []
        result = evaluate_instability(df, severe_rules, mild_rules)
        assert result.loc[0, "instability_severe"] == True
        assert result.loc[1, "instability_severe"] == False

    def test_mild_not_when_severe(self):
        """mild 在 severe=True 时应为 False。"""
        df = pd.DataFrame({
            "eih_status": [True],
            "bp_peak_sys": [210.0],   # 触发 mild
        })
        severe_rules = [RuleConfig("eih_status", "eq", value=True)]
        mild_rules = [RuleConfig("bp_peak_sys", "between_open_closed", low=200, high=220)]
        result = evaluate_instability(df, severe_rules, mild_rules)
        assert result.loc[0, "instability_severe"] == True
        assert result.loc[0, "instability_mild"] == False  # mild 被 severe 覆盖

    def test_mild_when_not_severe(self):
        """只有 mild 规则触发时，mild=True, severe=False。"""
        df = pd.DataFrame({
            "eih_status": [False],
            "bp_peak_sys": [210.0],
        })
        severe_rules = [RuleConfig("eih_status", "eq", value=True)]
        mild_rules = [RuleConfig("bp_peak_sys", "between_open_closed", low=200, high=220)]
        result = evaluate_instability(df, severe_rules, mild_rules)
        assert result.loc[0, "instability_severe"] == False
        assert result.loc[0, "instability_mild"] == True

    def test_nan_does_not_trigger_severe(self):
        """缺失值不触发 severe。"""
        df = pd.DataFrame({"bp_peak_sys": [np.nan]})
        severe_rules = [RuleConfig("bp_peak_sys", "gt", value=220)]
        result = evaluate_instability(df, severe_rules, [])
        assert result.loc[0, "instability_severe"] == False


# ─────────────────────────────────────────────────────
# apply_override 测试
# ─────────────────────────────────────────────────────

class TestApplyOverride:

    def test_severe_forces_red(self):
        """severe=True → 强制 red，不管 phenotype。"""
        zone = pd.Series(["green", "yellow", "red"])
        instab = pd.DataFrame({
            "instability_severe": [True, True, True],
            "instability_mild": [False, False, False],
        })
        result = apply_override(zone, instab)
        assert list(result) == ["red", "red", "red"]

    def test_mild_upgrades_green_only(self):
        """mild=True: green→yellow, yellow→yellow(不变), red→red(不变)。"""
        zone = pd.Series(["green", "yellow", "red"])
        instab = pd.DataFrame({
            "instability_severe": [False, False, False],
            "instability_mild": [True, True, True],
        })
        result = apply_override(zone, instab)
        assert result.iloc[0] == "yellow"  # green → yellow
        assert result.iloc[1] == "yellow"  # yellow 不变
        assert result.iloc[2] == "red"     # red 不变（不降级）

    def test_no_instability_no_change(self):
        zone = pd.Series(["green", "yellow", "red"])
        instab = pd.DataFrame({
            "instability_severe": [False, False, False],
            "instability_mild": [False, False, False],
        })
        result = apply_override(zone, instab)
        assert list(result) == ["green", "yellow", "red"]

    def test_severe_wins_over_mild(self):
        """severe=True 时，即使 mild 也触发，final 应为 red。"""
        zone = pd.Series(["green"])
        instab = pd.DataFrame({
            "instability_severe": [True],
            "instability_mild": [True],
        })
        result = apply_override(zone, instab)
        assert result.iloc[0] == "red"

    def test_nan_phenotype_with_severe(self):
        """NaN phenotype + severe → red（severe 覆盖 NaN）。"""
        zone = pd.Series([np.nan])
        instab = pd.DataFrame({
            "instability_severe": [True],
            "instability_mild": [False],
        })
        result = apply_override(zone, instab)
        assert result.iloc[0] == "red"

    def test_nan_phenotype_without_severe_stays_nan(self):
        """NaN phenotype + no severe → 保持 NaN。"""
        zone = pd.Series([np.nan])
        instab = pd.DataFrame({
            "instability_severe": [False],
            "instability_mild": [True],
        })
        result = apply_override(zone, instab)
        assert pd.isna(result.iloc[0])


# ─────────────────────────────────────────────────────
# load_instability_rules 测试
# ─────────────────────────────────────────────────────

class TestLoadInstabilityRules:

    def test_loads_from_yaml(self):
        severe, mild = load_instability_rules("configs/data/zone_rules_stage1b.yaml")
        assert len(severe) > 0
        assert len(mild) > 0

    def test_severe_has_eih_rule(self):
        severe, _ = load_instability_rules("configs/data/zone_rules_stage1b.yaml")
        fields = [r.field_name for r in severe]
        assert "eih_status" in fields

    def test_severe_has_bp_rule(self):
        severe, _ = load_instability_rules("configs/data/zone_rules_stage1b.yaml")
        fields = [r.field_name for r in severe]
        assert "bp_peak_sys" in fields

    def test_mild_has_bp_border_rule(self):
        _, mild = load_instability_rules("configs/data/zone_rules_stage1b.yaml")
        ops = [r.op for r in mild]
        assert "between_open_closed" in ops

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_instability_rules("nonexistent.yaml")


# ─────────────────────────────────────────────────────
# run_instability_engine 测试
# ─────────────────────────────────────────────────────

class TestRunInstabilityEngine:

    def test_returns_instability_result(self):
        df = _make_df()
        zone = pd.Series(["green"] * len(df))
        result = run_instability_engine(df, zone)
        assert isinstance(result, InstabilityResult)

    def test_output_columns_present(self):
        df = _make_df()
        zone = pd.Series(["green"] * len(df))
        result = run_instability_engine(df, zone)
        assert "instability_severe" in result.df.columns
        assert "instability_mild" in result.df.columns
        assert "final_zone_before_confidence" in result.df.columns

    def test_severe_eih_forces_red(self):
        """eih_status=True 行的 final_zone 应为 red。"""
        df = pd.DataFrame({"eih_status": [True, False, False]})
        zone = pd.Series(["green", "yellow", "red"])
        result = run_instability_engine(df, zone)
        assert result.df.loc[0, "final_zone_before_confidence"] == "red"
        assert result.df.loc[1, "final_zone_before_confidence"] == "yellow"
        assert result.df.loc[2, "final_zone_before_confidence"] == "red"

    def test_no_downgrade_from_red(self):
        """mild instability 不应把 red 降为 yellow 或 green。"""
        df = pd.DataFrame({
            "eih_status": [False],
            "bp_peak_sys": [210.0],   # mild: 200 < x <= 220
        })
        zone = pd.Series(["red"])
        result = run_instability_engine(df, zone)
        assert result.df.loc[0, "final_zone_before_confidence"] == "red"

    def test_summary_method(self):
        df = _make_df()
        zone = pd.Series(["green"] * len(df))
        result = run_instability_engine(df, zone)
        summary = result.summary()
        assert "Severe" in summary


# ─────────────────────────────────────────────────────
# generate_instability_report 测试
# ─────────────────────────────────────────────────────

class TestGenerateInstabilityReport:

    def _run_engine(self):
        df = _make_df()
        zone = pd.Series(["green"] * len(df))
        return run_instability_engine(df, zone), df

    def test_report_is_string(self):
        result, _ = self._run_engine()
        report = generate_instability_report(result)
        assert isinstance(report, str)

    def test_report_saved_to_file(self, tmp_path):
        result, _ = self._run_engine()
        out = tmp_path / "report.md"
        generate_instability_report(result, output_path=out)
        assert out.exists()

    def test_report_with_test_result(self):
        result, df = self._run_engine()
        df_orig = df.copy()
        df_orig["test_result"] = ["阳性" if i % 6 == 0 else "阴性" for i in range(len(df))]
        report = generate_instability_report(result, df_original=df_orig)
        assert "构念效度" in report
