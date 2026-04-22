"""
test_concordance.py — Phase G Method 3 单元测试

覆盖：
- concordance_ensemble.py: _canonicalize_zone, compute_concordance, run_concordance_analysis
- ConcordanceSource, ConcordanceResult
- generate_concordance_report
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.labels.concordance_ensemble import (
    ConcordanceSource,
    ConcordanceResult,
    _canonicalize_zone,
    compute_concordance,
    run_concordance_analysis,
    generate_concordance_report,
    UNCERTAIN_LABEL,
)


# ── 合成数据工厂 ──────────────────────────────────────────────────────────────

def make_concordance_df(n: int = 200, seed: int = 42, n_sources: int = 4) -> pd.DataFrame:
    """
    生成含多个安全区定义列的 DataFrame。
    - zone_d1: P1 规则标签
    - zone_d2: Zone Engine v2
    - zone_d3: 结局锚定
    - zone_d4: 简单阈值
    """
    rng = np.random.default_rng(seed)
    zones = ["green", "yellow", "red"]

    # 构造具有相关性的多定义（真实场景：各定义有一定一致性）
    base_zone = rng.choice(zones, size=n, p=[0.4, 0.35, 0.25])

    df = pd.DataFrame({
        "subject_id": [f"S{i:04d}" for i in range(n)],
        "vo2_peak": rng.uniform(10, 35, n),
    })

    for i in range(n_sources):
        col = f"zone_d{i+1}"
        # 以 70% 概率保持与 base_zone 一致，30% 随机
        zone_vals = []
        for z in base_zone:
            if rng.random() < 0.70:
                zone_vals.append(z)
            else:
                zone_vals.append(rng.choice(zones))
        df[col] = zone_vals

    # test_result：与 base_zone 相关
    test_results = []
    for z in base_zone:
        if z == "red":
            test_results.append(rng.choice(["阳性", "可疑阳性", "阴性"], p=[0.35, 0.20, 0.45]))
        elif z == "yellow":
            test_results.append(rng.choice(["阳性", "可疑阳性", "阴性"], p=[0.15, 0.15, 0.70]))
        else:  # green
            test_results.append(rng.choice(["阳性", "可疑阳性", "阴性"], p=[0.05, 0.05, 0.90]))
    df["test_result"] = test_results

    return df


def make_sources(n: int = 4) -> list[ConcordanceSource]:
    return [
        ConcordanceSource(name=f"d{i+1}", column=f"zone_d{i+1}")
        for i in range(n)
    ]


# ── TestCanonicalizeZone ──────────────────────────────────────────────────────

class TestCanonicalizeZone:
    """测试区间标签规范化。"""

    def test_string_values(self):
        """字符串 green/yellow/red（各种大小写）应正确规范化。"""
        assert _canonicalize_zone("green") == "green"
        assert _canonicalize_zone("Green") == "green"
        assert _canonicalize_zone("YELLOW") == "yellow"
        assert _canonicalize_zone("Red") == "red"

    def test_numeric_values(self):
        """数值 0/1/2 应映射到 green/yellow/red。"""
        assert _canonicalize_zone(0) == "green"
        assert _canonicalize_zone(1) == "yellow"
        assert _canonicalize_zone(2) == "red"
        assert _canonicalize_zone(0.0) == "green"

    def test_chinese_values(self):
        """中文标签应正确映射。"""
        assert _canonicalize_zone("绿") == "green"
        assert _canonicalize_zone("黄区") == "yellow"
        assert _canonicalize_zone("红") == "red"

    def test_none_and_nan(self):
        """None 和 NaN 应返回 None。"""
        assert _canonicalize_zone(None) is None
        assert _canonicalize_zone(np.nan) is None
        assert _canonicalize_zone(float("nan")) is None

    def test_unknown_value(self):
        """未知值应返回 None。"""
        assert _canonicalize_zone("unknown") is None
        assert _canonicalize_zone(99) is None


# ── TestComputeConcordance ────────────────────────────────────────────────────

class TestComputeConcordance:
    """测试一致性计算核心逻辑。"""

    @pytest.fixture
    def df_sources(self):
        df = make_concordance_df(n=200, seed=42, n_sources=4)
        sources = make_sources(4)
        return df, sources

    def test_result_shape(self, df_sources):
        """结果 scores 的行数应等于输入行数。"""
        df, sources = df_sources
        result = compute_concordance(df, sources)
        assert len(result.scores) == len(df)

    def test_required_columns(self, df_sources):
        """结果应包含必要列。"""
        df, sources = df_sources
        result = compute_concordance(df, sources)
        required = {"zone_consensus", "zone_confidence", "is_high_confidence", "has_green_red_conflict"}
        assert required.issubset(result.scores.columns)

    def test_consensus_values(self, df_sources):
        """zone_consensus 值应为 green/yellow/red/uncertain。"""
        df, sources = df_sources
        result = compute_concordance(df, sources)
        valid = {"green", "yellow", "red", UNCERTAIN_LABEL}
        assert set(result.scores["zone_consensus"].unique()).issubset(valid)

    def test_confidence_in_01(self, df_sources):
        """一致性比例应在 [0, 1] 范围内。"""
        df, sources = df_sources
        result = compute_concordance(df, sources)
        conf = result.scores["zone_confidence"]
        assert (conf >= 0.0).all() and (conf <= 1.0).all()

    def test_high_confidence_subset_exists(self, df_sources):
        """应存在高信度患者。"""
        df, sources = df_sources
        result = compute_concordance(df, sources)
        n_high = result.high_confidence_stats.get("n_high_confidence", 0)
        assert n_high > 0

    def test_high_confidence_pct_reasonable(self, df_sources):
        """高信度比例应在合理范围内（0-100%）。"""
        df, sources = df_sources
        result = compute_concordance(df, sources)
        pct = result.high_confidence_stats.get("pct_high_confidence", 0)
        assert 0 <= pct <= 100

    def test_green_red_conflict_detection(self):
        """Green/Red 同时出现时应标记为冲突。"""
        df = pd.DataFrame({
            "d1": ["green", "red", "yellow"],
            "d2": ["red", "red", "yellow"],
            "d3": ["green", "green", "yellow"],
        })
        sources = [
            ConcordanceSource("d1", "d1"),
            ConcordanceSource("d2", "d2"),
            ConcordanceSource("d3", "d3"),
        ]
        result = compute_concordance(df, sources)
        # 第0行（d1=green, d2=red, d3=green）：Green/Red 冲突
        assert result.scores["has_green_red_conflict"].iloc[0] == True
        # 第1行（d1=red, d2=red, d3=green）：Green/Red 冲突
        assert result.scores["has_green_red_conflict"].iloc[1] == True
        # 第2行（全 yellow）：无冲突
        assert result.scores["has_green_red_conflict"].iloc[2] == False

    def test_uncertain_when_no_majority(self):
        """无多数票时应标记为 uncertain。"""
        df = pd.DataFrame({
            "d1": ["green"],
            "d2": ["yellow"],
            "d3": ["red"],
        })
        sources = [ConcordanceSource(f"d{i+1}", f"d{i+1}") for i in range(3)]
        result = compute_concordance(df, sources)
        assert result.scores["zone_consensus"].iloc[0] == UNCERTAIN_LABEL

    def test_insufficient_sources(self):
        """有效定义不足时应优雅降级。"""
        df = pd.DataFrame({"nonexistent_col": ["green"]})
        sources = [
            ConcordanceSource("d1", "nonexistent_col_1"),
            ConcordanceSource("d2", "nonexistent_col_2"),
        ]
        result = compute_concordance(df, sources)
        assert isinstance(result, ConcordanceResult)


# ── TestRunConcordanceAnalysis ────────────────────────────────────────────────

class TestRunConcordanceAnalysis:
    """测试端到端分析管线。"""

    def test_run_without_config(self):
        """无配置文件时应使用默认逻辑成功运行。"""
        df = make_concordance_df(n=100, seed=42)
        # 添加常见列名
        df["p1_zone_label"] = df["zone_d1"].map({"green": 0, "yellow": 1, "red": 2})
        df["z_lab_zone"] = df["zone_d2"]
        result = run_concordance_analysis(
            df,
            config_path="nonexistent_config.yaml",
        )
        assert isinstance(result, ConcordanceResult)

    def test_vo2_simple_zone_generation(self):
        """当 vo2_zone_simple 不存在时应自动生成。"""
        df = pd.DataFrame({
            "vo2_peak": [12.0, 18.0, 25.0],
            "p1_zone_label": ["red", "yellow", "green"],
        })
        result = run_concordance_analysis(
            df,
            config_path="nonexistent_config.yaml",
        )
        # 应成功运行（vo2_zone_simple 被自动创建）
        assert isinstance(result, ConcordanceResult)

    def test_zone_distribution_complete(self):
        """安全区分布应包含所有区（含 uncertain）。"""
        df = make_concordance_df(n=100, seed=0)
        sources = make_sources(3)
        result = compute_concordance(df, sources)
        for z in ["green", "yellow", "red", "uncertain"]:
            assert z in result.zone_distribution

    def test_outcome_stats_with_outcome_col(self):
        """提供 test_result 时应计算各区阳性率。"""
        df = make_concordance_df(n=100, seed=0)
        sources = make_sources(3)
        result = compute_concordance(df, sources, outcome_col="test_result")
        assert len(result.outcome_by_zone_confidence) > 0


# ── TestGenerateConcordanceReport ─────────────────────────────────────────────

class TestGenerateConcordanceReport:
    """测试报告生成。"""

    def test_report_generation(self):
        """报告应成功生成且包含关键内容。"""
        df = make_concordance_df(n=100, seed=0)
        sources = make_sources(3)
        result = compute_concordance(df, sources, outcome_col="test_result")
        report = generate_concordance_report(result)
        assert "多定义一致性框架报告" in report
        assert "信度统计" in report
        assert "安全区分布" in report
