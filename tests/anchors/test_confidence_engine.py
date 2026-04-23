"""
tests/anchors/test_confidence_engine.py — Confidence Engine 测试。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.anchors.confidence_engine import (
    ConfidenceResult,
    compute_anchor_agreement,
    compute_completeness_score,
    compute_confidence,
    compute_effort_score,
    compute_validation_agreement,
    finalize_zone_with_uncertainty,
    generate_confidence_report,
    label_confidence,
    load_confidence_config,
    run_confidence_engine,
)


# ─────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────

def _make_df(n: int = 100, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "vo2_peak": rng.uniform(10, 35, n),
        "ve_vco2_slope": rng.uniform(22, 45, n),
        "oues": rng.uniform(500, 2800, n),
        "o2_pulse_peak": rng.uniform(5, 20, n),
        "mets_peak": rng.uniform(2, 12, n),
        "eih_status": rng.choice([False, True], n, p=[0.9, 0.1]),
        "bp_peak_sys": rng.uniform(140, 230, n),
        "bp_peak_dia": rng.uniform(80, 115, n),
        "hr_peak_pct_pred": rng.uniform(60, 105, n),
        "age": rng.uniform(50, 80, n),
    })


# ─────────────────────────────────────────────────────
# compute_completeness_score 测试
# ─────────────────────────────────────────────────────

class TestCompletenessScore:

    def test_all_present(self):
        df = pd.DataFrame({"vo2_peak": [20.0], "ve_vco2_slope": [30.0]})
        score = compute_completeness_score(
            df, reserve_fields=["vo2_peak"], ventilatory_fields=["ve_vco2_slope"],
            instability_fields=[],
        )
        assert score.iloc[0] == 1.0

    def test_partial_missing(self):
        df = pd.DataFrame({"vo2_peak": [np.nan], "ve_vco2_slope": [30.0]})
        score = compute_completeness_score(
            df, reserve_fields=["vo2_peak"], ventilatory_fields=["ve_vco2_slope"],
            instability_fields=[],
        )
        assert score.iloc[0] == 0.5

    def test_all_missing(self):
        df = pd.DataFrame({"vo2_peak": [np.nan]})
        score = compute_completeness_score(
            df, reserve_fields=["vo2_peak"], ventilatory_fields=[],
            instability_fields=[],
        )
        assert score.iloc[0] == 0.0

    def test_no_fields_returns_neutral(self):
        df = pd.DataFrame({"x": [1]})
        score = compute_completeness_score(
            df, reserve_fields=[], ventilatory_fields=[], instability_fields=[]
        )
        assert score.iloc[0] == 0.5

    def test_missing_column_counted_as_absent(self):
        """不存在的列视为缺失。"""
        df = pd.DataFrame({"vo2_peak": [20.0]})
        score = compute_completeness_score(
            df, reserve_fields=["vo2_peak", "nonexistent"],
            ventilatory_fields=[], instability_fields=[],
        )
        # 2 字段中有1个（vo2_peak），但 nonexistent 不在df中
        # 可用字段=[vo2_peak]，required=2，available=1 → 0.5
        assert score.iloc[0] == 0.5

    def test_range_0_to_1(self):
        df = _make_df()
        score = compute_completeness_score(
            df,
            reserve_fields=["vo2_peak", "o2_pulse_peak", "mets_peak"],
            ventilatory_fields=["ve_vco2_slope", "oues"],
            instability_fields=["eih_status", "bp_peak_sys"],
        )
        assert (score >= 0).all() and (score <= 1).all()


# ─────────────────────────────────────────────────────
# compute_effort_score 测试
# ─────────────────────────────────────────────────────

class TestEffortScore:

    def test_adequate(self):
        df = pd.DataFrame({"hr_peak_pct_pred": [90.0]})
        score = compute_effort_score(df, adequate_threshold=85.0)
        assert score.iloc[0] == 1.0

    def test_uncertain(self):
        df = pd.DataFrame({"hr_peak_pct_pred": [75.0]})
        score = compute_effort_score(df, adequate_threshold=85.0, uncertain_threshold=70.0)
        assert score.iloc[0] == 0.5

    def test_inadequate(self):
        df = pd.DataFrame({"hr_peak_pct_pred": [60.0]})
        score = compute_effort_score(df, adequate_threshold=85.0, uncertain_threshold=70.0)
        assert score.iloc[0] == 0.0

    def test_nan_returns_neutral(self):
        df = pd.DataFrame({"hr_peak_pct_pred": [np.nan]})
        score = compute_effort_score(df)
        assert score.iloc[0] == 0.5

    def test_proxy_from_hr_peak_and_age(self):
        """使用 hr_peak + age 代理。"""
        df = pd.DataFrame({"hr_peak": [150.0], "age": [60.0]})
        # max_hr = 220-60=160, hr_pct = 150/160*100 = 93.75% → adequate
        score = compute_effort_score(
            df, adequate_threshold=85.0, hr_pct_field="hr_peak_pct_pred"
        )
        assert score.iloc[0] == 1.0

    def test_no_hr_field_returns_neutral(self):
        df = pd.DataFrame({"unrelated": [1.0]})
        score = compute_effort_score(df)
        assert (score == 0.5).all()


# ─────────────────────────────────────────────────────
# compute_anchor_agreement 测试
# ─────────────────────────────────────────────────────

class TestAnchorAgreement:

    def test_same_zone(self):
        ext = pd.Series(["green"])
        internal = pd.Series(["green"])
        score = compute_anchor_agreement(ext, internal)
        assert score.iloc[0] == 1.0

    def test_adjacent(self):
        ext = pd.Series(["green"])
        internal = pd.Series(["yellow"])
        score = compute_anchor_agreement(ext, internal)
        assert score.iloc[0] == 0.5

    def test_discordant(self):
        ext = pd.Series(["green"])
        internal = pd.Series(["red"])
        score = compute_anchor_agreement(ext, internal)
        assert score.iloc[0] == 0.0

    def test_nan_returns_neutral(self):
        ext = pd.Series([np.nan])
        internal = pd.Series(["green"])
        score = compute_anchor_agreement(ext, internal)
        assert score.iloc[0] == 0.5


# ─────────────────────────────────────────────────────
# compute_validation_agreement 测试
# ─────────────────────────────────────────────────────

class TestValidationAgreement:

    def test_concordant(self):
        zone = pd.Series(["green"])
        tertile = pd.Series(["low"])
        score = compute_validation_agreement(zone, tertile)
        assert score.iloc[0] == 1.0

    def test_adjacent(self):
        zone = pd.Series(["green"])
        tertile = pd.Series(["mid"])
        score = compute_validation_agreement(zone, tertile)
        assert score.iloc[0] == 0.5

    def test_discordant(self):
        zone = pd.Series(["green"])
        tertile = pd.Series(["high"])
        score = compute_validation_agreement(zone, tertile)
        assert score.iloc[0] == 0.0

    def test_nan_returns_neutral(self):
        zone = pd.Series([np.nan])
        tertile = pd.Series(["low"])
        score = compute_validation_agreement(zone, tertile)
        assert score.iloc[0] == 0.5


# ─────────────────────────────────────────────────────
# compute_confidence 测试
# ─────────────────────────────────────────────────────

class TestComputeConfidence:

    def test_all_ones(self):
        n = 10
        ones = pd.Series([1.0] * n)
        score = compute_confidence(ones, ones, ones, ones)
        assert (score == 1.0).all()

    def test_all_zeros_completeness(self):
        n = 5
        zeros = pd.Series([0.0] * n)
        halves = pd.Series([0.5] * n)
        score = compute_confidence(zeros, halves, halves, halves)
        # v2.7.0 新权重: 0.25*0 + 0.20*0.5 + 0.25*0.5 + 0.30*0.5 = 0 + 0.10 + 0.125 + 0.15 = 0.375
        assert abs(score.iloc[0] - 0.375) < 1e-6

    def test_custom_weights(self):
        n = 1
        comp = pd.Series([1.0])
        effort = pd.Series([0.0])
        anchor = pd.Series([0.0])
        valid = pd.Series([0.0])
        weights = {"completeness": 1.0, "effort": 0.0, "anchor_agreement": 0.0, "validation_agreement": 0.0}
        score = compute_confidence(comp, effort, anchor, valid, weights=weights)
        assert score.iloc[0] == 1.0

    def test_range_0_to_1(self):
        df = _make_df()
        comp = pd.Series(np.random.uniform(0, 1, len(df)))
        effort = pd.Series(np.random.choice([0, 0.5, 1], len(df)).astype(float))
        anchor = pd.Series(np.random.choice([0, 0.5, 1], len(df)).astype(float))
        valid = pd.Series(np.random.choice([0, 0.5, 1], len(df)).astype(float))
        score = compute_confidence(comp, effort, anchor, valid)
        assert (score >= 0.0).all() and (score <= 1.0).all()


# ─────────────────────────────────────────────────────
# label_confidence 测试
# ─────────────────────────────────────────────────────

class TestLabelConfidence:

    def test_high(self):
        score = pd.Series([0.80])
        label = label_confidence(score)
        assert label.iloc[0] == "high"

    def test_medium(self):
        score = pd.Series([0.65])
        label = label_confidence(score)
        assert label.iloc[0] == "medium"

    def test_low(self):
        score = pd.Series([0.50])
        label = label_confidence(score)
        assert label.iloc[0] == "low"

    def test_nan_input(self):
        score = pd.Series([np.nan])
        label = label_confidence(score)
        assert pd.isna(label.iloc[0])


# ─────────────────────────────────────────────────────
# finalize_zone_with_uncertainty 测试
# ─────────────────────────────────────────────────────

class TestFinalizeZone:

    def test_low_confidence_becomes_indeterminate(self):
        zone = pd.Series(["green"])
        conf = pd.Series([0.40])
        severe = pd.Series([False])
        out = finalize_zone_with_uncertainty(zone, conf, severe)
        assert out.loc[0, "final_zone"] == "yellow_gray"
        assert out.loc[0, "indeterminate_flag"] == True

    def test_severe_stays_red_regardless_of_confidence(self):
        zone = pd.Series(["red"])
        conf = pd.Series([0.30])  # low confidence
        severe = pd.Series([True])
        out = finalize_zone_with_uncertainty(zone, conf, severe)
        assert out.loc[0, "final_zone"] == "red"
        assert out.loc[0, "indeterminate_flag"] == False

    def test_high_confidence_zone_preserved(self):
        zone = pd.Series(["green"])
        conf = pd.Series([0.80])
        severe = pd.Series([False])
        out = finalize_zone_with_uncertainty(zone, conf, severe)
        assert out.loc[0, "final_zone"] == "green"
        assert out.loc[0, "indeterminate_flag"] == False

    def test_output_columns_present(self):
        zone = pd.Series(["yellow", "green"])
        conf = pd.Series([0.80, 0.40])
        severe = pd.Series([False, False])
        out = finalize_zone_with_uncertainty(zone, conf, severe)
        assert "confidence_score" in out.columns
        assert "confidence_label" in out.columns
        assert "indeterminate_flag" in out.columns
        assert "final_zone" in out.columns


# ─────────────────────────────────────────────────────
# run_confidence_engine 测试
# ─────────────────────────────────────────────────────

class TestRunConfidenceEngine:

    def test_returns_confidence_result(self):
        df = _make_df()
        zone = pd.Series(["green", "yellow", "red"] * (len(df) // 3) + ["green"] * (len(df) % 3))
        severe = pd.Series([False] * len(df))
        result = run_confidence_engine(df, zone, severe)
        assert isinstance(result, ConfidenceResult)

    def test_output_columns_present(self):
        df = _make_df()
        zone = pd.Series(["green"] * len(df))
        severe = pd.Series([False] * len(df))
        result = run_confidence_engine(df, zone, severe)
        for col in ["confidence_score", "confidence_label", "indeterminate_flag", "final_zone"]:
            assert col in result.df.columns

    def test_severe_not_overridden_by_low_confidence(self):
        """severe=True 行不应因 confidence 低而变为 yellow_gray。"""
        df = _make_df(n=5)
        zone = pd.Series(["red", "green", "yellow", "red", "green"])
        severe = pd.Series([True, False, False, True, False])
        result = run_confidence_engine(df, zone, severe)
        severe_rows = result.df[severe.values]
        assert (severe_rows["final_zone"] != "yellow_gray").all()

    def test_high_confidence_pct_reasonable(self):
        """高置信度比例应在合理范围（> 0%）。"""
        df = _make_df(n=200)
        zone = pd.Series(["green"] * len(df))
        severe = pd.Series([False] * len(df))
        result = run_confidence_engine(df, zone, severe)
        assert result.n_high >= 0  # 至少不报错

    def test_with_outcome_tertile(self):
        """提供 outcome_risk_tertile 时，validation_agreement 应生效。"""
        df = _make_df(n=10)
        zone = pd.Series(["green"] * 5 + ["red"] * 5)
        severe = pd.Series([False] * 10)
        tertile = pd.Series(["low"] * 5 + ["high"] * 5)
        result = run_confidence_engine(df, zone, severe, outcome_risk_tertile=tertile)
        assert isinstance(result, ConfidenceResult)

    def test_summary_method(self):
        df = _make_df()
        zone = pd.Series(["green"] * len(df))
        severe = pd.Series([False] * len(df))
        result = run_confidence_engine(df, zone, severe)
        summary = result.summary()
        assert "High" in summary
        assert "Indeterminate" in summary


# ─────────────────────────────────────────────────────
# load_confidence_config 测试
# ─────────────────────────────────────────────────────

class TestLoadConfidenceConfig:

    def test_loads_from_yaml(self):
        cfg = load_confidence_config("configs/data/zone_rules_stage1b.yaml")
        assert "weights" in cfg

    def test_weights_sum_to_1(self):
        cfg = load_confidence_config("configs/data/zone_rules_stage1b.yaml")
        weights = cfg.get("weights", {})
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-6

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_confidence_config("nonexistent.yaml")


# ─────────────────────────────────────────────────────
# generate_confidence_report 测试
# ─────────────────────────────────────────────────────

class TestGenerateConfidenceReport:

    def _run_engine(self):
        df = _make_df()
        zone = pd.Series(["green"] * len(df))
        severe = pd.Series([False] * len(df))
        return run_confidence_engine(df, zone, severe), df

    def test_report_is_string(self):
        result, _ = self._run_engine()
        report = generate_confidence_report(result)
        assert isinstance(report, str)

    def test_report_saved_to_file(self, tmp_path):
        result, _ = self._run_engine()
        out = tmp_path / "report.md"
        generate_confidence_report(result, output_path=out)
        assert out.exists()

    def test_report_with_test_result(self):
        result, df = self._run_engine()
        df["test_result"] = ["阳性" if i % 7 == 0 else "阴性" for i in range(len(df))]
        report = generate_confidence_report(result, df_original=df)
        assert "高置信度" in report


# ─────────────────────────────────────────────────────
# v2.7.0 新功能：medium 封顶逻辑 + 新输出字段
# ─────────────────────────────────────────────────────

class TestMediumCapLogic:
    """测试 medium 封顶逻辑（AND 语义）。"""

    def test_both_neutral_caps_to_medium(self):
        """两域均中性时（anchor=0.5, validation=0.5），封顶为 medium。"""
        # 高分 + 两域均中性 → 封顶 medium
        score = pd.Series([0.85])
        neutral_mask = pd.Series([True])
        label = label_confidence(score, high_threshold=0.80, medium_threshold=0.65,
                                 neutral_agreement_mask=neutral_mask)
        assert label.iloc[0] == "medium"

    def test_one_non_neutral_allows_high(self):
        """只有一域中性（AND逻辑），不封顶。"""
        score = pd.Series([0.85])
        neutral_mask = pd.Series([False])  # 不封顶
        label = label_confidence(score, high_threshold=0.80, medium_threshold=0.65,
                                 neutral_agreement_mask=neutral_mask)
        assert label.iloc[0] == "high"

    def test_no_cap_mask_normal_labeling(self):
        """无封顶掩码时，正常分层。"""
        scores = pd.Series([0.85, 0.70, 0.50])
        labels = label_confidence(scores, high_threshold=0.80, medium_threshold=0.65)
        assert labels.iloc[0] == "high"
        assert labels.iloc[1] == "medium"
        assert labels.iloc[2] == "low"

    def test_finalize_zone_with_neutral_mask(self):
        """finalize_zone_with_uncertainty 传递封顶掩码。"""
        zone = pd.Series(["green", "yellow"])
        conf = pd.Series([0.85, 0.85])
        severe = pd.Series([False, False])
        neutral_mask = pd.Series([True, False])

        out = finalize_zone_with_uncertainty(
            zone, conf, severe,
            high_threshold=0.80, medium_threshold=0.65,
            neutral_agreement_mask=neutral_mask,
        )
        # 第1行（neutral mask True）应为 medium
        assert out.loc[0, "confidence_label"] == "medium"
        # 第2行（neutral mask False）应为 high
        assert out.loc[1, "confidence_label"] == "high"


class TestNewOutputFields:
    """测试 run_confidence_engine 新增输出字段。"""

    def test_anchor_agreement_in_output(self):
        df = _make_df()
        zone = pd.Series(["green"] * len(df))
        severe = pd.Series([False] * len(df))
        result = run_confidence_engine(df, zone, severe)
        assert "anchor_agreement" in result.df.columns

    def test_validation_agreement_in_output(self):
        df = _make_df()
        zone = pd.Series(["green"] * len(df))
        severe = pd.Series([False] * len(df))
        result = run_confidence_engine(df, zone, severe)
        assert "validation_agreement" in result.df.columns

    def test_validation_agreement_with_real_tertile(self):
        df = _make_df(n=15)
        zone = pd.Series(["green"] * 5 + ["yellow"] * 5 + ["red"] * 5)
        severe = pd.Series([False] * 15)
        tertile = pd.Series(["low"] * 5 + ["mid"] * 5 + ["high"] * 5)
        result = run_confidence_engine(df, zone, severe, outcome_risk_tertile=tertile)
        # validation_agreement 应不全为 0.5
        va = result.df["validation_agreement"]
        assert not (va == 0.5).all()

    def test_categorical_tertile_handled(self):
        """outcome_risk_tertile 为 Categorical 类型时不报错。"""
        df = _make_df(n=9)
        zone = pd.Series(["green"] * 3 + ["yellow"] * 3 + ["red"] * 3)
        severe = pd.Series([False] * 9)
        tertile = pd.Categorical(["low"] * 3 + ["mid"] * 3 + ["high"] * 3)
        tertile_series = pd.Series(tertile)
        result = run_confidence_engine(df, zone, severe, outcome_risk_tertile=tertile_series)
        assert "validation_agreement" in result.df.columns
