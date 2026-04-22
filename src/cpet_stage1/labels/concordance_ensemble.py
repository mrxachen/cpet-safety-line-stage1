"""
concordance_ensemble.py — Phase G Method 3：多定义一致性框架

核心创新：
  不争论"哪个安全区定义最正确"（不可回答），
  而是利用多个定义的一致性/分歧本身作为信息：
  - 一致 = 高信度分区（临床可信）
  - 分歧 = 不确定区域（临床需深度评估 → Stage 2 优先人群）

为什么有意义：
  - 当前 39.5% 重分类率说明定义间存在系统性分歧
  - 将分歧量化为"不确定性"比选择任何单一定义更诚实
  - 不确定区域患者恰好是 Stage 2 深度检测的优先对象

投票流程：
  1. 收集 K 个安全区定义（列）
  2. 对每个患者统计各区得票数
  3. 多数票区（> K/2）→ zone_consensus
  4. 无多数票 or Green/Red 冲突 → "uncertain"
  5. 一致性比例 = 最高票数 / K → zone_confidence

配置文件：configs/data/concordance_config.yaml
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

ZONE_VALUES = {"green", "yellow", "red"}
UNCERTAIN_LABEL = "uncertain"


@dataclass
class ConcordanceSource:
    """单个安全区定义的描述。"""
    name: str
    column: str
    weight: float = 1.0
    description: str = ""


@dataclass
class ConcordanceResult:
    """多定义一致性分析结果。"""
    scores: pd.DataFrame = field(default_factory=pd.DataFrame)
    # scores 列：zone_consensus, zone_confidence, is_high_confidence,
    #            has_green_red_conflict, zone_vote_detail（可选）
    sources_used: list[str] = field(default_factory=list)
    n_sources: int = 0
    zone_distribution: dict = field(default_factory=dict)
    high_confidence_stats: dict = field(default_factory=dict)
    # 各区按 is_high_confidence 分组的 test_result 阳性率
    outcome_by_zone_confidence: dict = field(default_factory=dict)

    def to_summary_dict(self) -> dict:
        return {
            "n_sources": self.n_sources,
            "sources_used": self.sources_used,
            "zone_distribution": self.zone_distribution,
            "high_confidence_stats": self.high_confidence_stats,
            "outcome_by_zone_confidence": self.outcome_by_zone_confidence,
        }


def _canonicalize_zone(val) -> Optional[str]:
    """
    将各种安全区表示统一为 "green"/"yellow"/"red"/None。

    处理：
    - 字符串："green", "yellow", "red", "Green", "0", "1", "2", ...
    - 数值：0→green, 1→yellow, 2→red
    - NaN/None → None
    """
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    if isinstance(val, (int, np.integer)):
        mapping = {0: "green", 1: "yellow", 2: "red"}
        return mapping.get(int(val), None)
    if isinstance(val, (float, np.floating)):
        mapping = {0.0: "green", 1.0: "yellow", 2.0: "red"}
        return mapping.get(float(val), None)
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ZONE_VALUES:
            return v
        # 处理中文标签
        cn_map = {
            "绿": "green", "绿区": "green",
            "黄": "yellow", "黄区": "yellow",
            "红": "red", "红区": "red",
        }
        if v in cn_map:
            return cn_map[v]
    return None


def compute_concordance(
    df: pd.DataFrame,
    sources: list[ConcordanceSource],
    high_confidence_threshold: float = 0.60,
    outcome_col: Optional[str] = "test_result",
) -> ConcordanceResult:
    """
    计算多定义一致性分析。

    参数：
        df: 包含各安全区定义列的 DataFrame
        sources: 安全区定义列表（name, column, weight）
        high_confidence_threshold: 高信度一致性比例阈值（默认 0.60）
        outcome_col: test_result 列名（可选，用于各区阳性率分析）

    返回：
        ConcordanceResult
    """
    result = ConcordanceResult()

    # ── 过滤有效列 ────────────────────────────────────────────────────────────
    valid_sources = []
    for src in sources:
        if src.column in df.columns:
            valid_sources.append(src)
        else:
            logger.info("安全区列 '%s' 不在 DataFrame 中，跳过源 '%s'", src.column, src.name)

    if len(valid_sources) < 2:
        logger.warning(
            "有效安全区定义不足（%d < 2），无法进行一致性分析",
            len(valid_sources)
        )
        result.scores = pd.DataFrame(
            {
                "zone_consensus": UNCERTAIN_LABEL,
                "zone_confidence": 0.0,
                "is_high_confidence": False,
                "has_green_red_conflict": False,
            },
            index=df.index,
        )
        return result

    result.sources_used = [s.name for s in valid_sources]
    result.n_sources = len(valid_sources)
    K = len(valid_sources)

    # ── 构建规范化投票矩阵 ────────────────────────────────────────────────────
    # votes_matrix: DataFrame，列=各定义，值="green"/"yellow"/"red"/None
    votes_matrix = pd.DataFrame(index=df.index)
    for src in valid_sources:
        votes_matrix[src.name] = df[src.column].map(_canonicalize_zone)

    # ── 逐行计算投票结果 ──────────────────────────────────────────────────────
    consensus_list = []
    confidence_list = []
    high_conf_list = []
    green_red_conflict_list = []

    for idx in df.index:
        row_votes = [votes_matrix.at[idx, s.name] for s in valid_sources]
        valid_votes = [v for v in row_votes if v is not None]

        if len(valid_votes) == 0:
            consensus_list.append(UNCERTAIN_LABEL)
            confidence_list.append(0.0)
            high_conf_list.append(False)
            green_red_conflict_list.append(False)
            continue

        # 计算各区票数（加权）
        zone_counts: dict[str, float] = {"green": 0.0, "yellow": 0.0, "red": 0.0}
        for v in valid_votes:
            zone_counts[v] = zone_counts.get(v, 0.0) + 1.0

        total_votes = len(valid_votes)
        max_zone = max(zone_counts, key=lambda z: zone_counts[z])
        max_count = zone_counts[max_zone]
        confidence = max_count / K  # 一致性比例（分母是总定义数 K，非有效票数）

        # 检测 Green/Red 冲突
        has_conflict = zone_counts["green"] > 0 and zone_counts["red"] > 0
        green_red_conflict_list.append(has_conflict)

        # 一致性判断
        if has_conflict or max_count / total_votes <= 0.5:
            # Green/Red 冲突 or 无多数票 → 不确定
            consensus_list.append(UNCERTAIN_LABEL)
        else:
            consensus_list.append(max_zone)

        confidence_list.append(confidence)
        high_conf_list.append(confidence >= high_confidence_threshold and not has_conflict)

    # ── 构建结果 DataFrame ────────────────────────────────────────────────────
    result.scores = pd.DataFrame(
        {
            "zone_consensus": consensus_list,
            "zone_confidence": confidence_list,
            "is_high_confidence": high_conf_list,
            "has_green_red_conflict": green_red_conflict_list,
        },
        index=df.index,
    )

    # ── 安全区分布统计 ────────────────────────────────────────────────────────
    total = len(df)
    for z in ["green", "yellow", "red", "uncertain"]:
        mask = result.scores["zone_consensus"] == z
        n = int(mask.sum())
        result.zone_distribution[z] = {
            "n": n,
            "pct": round(n / total * 100, 1) if total > 0 else 0.0,
        }

    # ── 高信度统计 ────────────────────────────────────────────────────────────
    n_high = int(result.scores["is_high_confidence"].sum())
    n_uncertain = int((result.scores["zone_consensus"] == UNCERTAIN_LABEL).sum())
    n_conflict = int(result.scores["has_green_red_conflict"].sum())
    result.high_confidence_stats = {
        "n_high_confidence": n_high,
        "pct_high_confidence": round(n_high / total * 100, 1) if total > 0 else 0.0,
        "n_uncertain": n_uncertain,
        "pct_uncertain": round(n_uncertain / total * 100, 1) if total > 0 else 0.0,
        "n_green_red_conflict": n_conflict,
        "pct_green_red_conflict": round(n_conflict / total * 100, 1) if total > 0 else 0.0,
    }

    logger.info(
        "一致性分析：高信度 %d (%.1f%%), 不确定 %d (%.1f%%), Green/Red冲突 %d",
        n_high, n_high / total * 100,
        n_uncertain, n_uncertain / total * 100,
        n_conflict,
    )

    # ── 各区按 test_result 阳性率分析 ─────────────────────────────────────────
    if outcome_col is not None and outcome_col in df.columns:
        pos_vals = {"阳性", "可疑阳性"}
        outcome_binary = df[outcome_col].isin(pos_vals)

        for z in ["green", "yellow", "red", "uncertain"]:
            zone_mask = result.scores["zone_consensus"] == z
            # 总体阳性率
            n_zone = zone_mask.sum()
            pos_in_zone = int(outcome_binary[zone_mask].sum()) if n_zone > 0 else 0
            pos_rate_all = round(pos_in_zone / n_zone * 100, 1) if n_zone > 0 else 0.0

            # 高信度子集阳性率
            hc_mask = zone_mask & result.scores["is_high_confidence"]
            n_hc = hc_mask.sum()
            pos_hc = int(outcome_binary[hc_mask].sum()) if n_hc > 0 else 0
            pos_rate_hc = round(pos_hc / n_hc * 100, 1) if n_hc > 0 else 0.0

            result.outcome_by_zone_confidence[z] = {
                "positive_rate_all": pos_rate_all,
                "positive_rate_high_confidence": pos_rate_hc,
                "n_high_confidence": int(n_hc),
            }

    return result


def run_concordance_analysis(
    df: pd.DataFrame,
    config_path: str | Path = "configs/data/concordance_config.yaml",
    outcome_col: Optional[str] = "test_result",
) -> ConcordanceResult:
    """
    端到端运行多定义一致性分析。

    参数：
        df: 包含各安全区定义列的 DataFrame
        config_path: 配置文件路径
        outcome_col: test_result 列名（可选）

    返回：
        ConcordanceResult
    """
    import yaml
    cfg_path = Path(config_path)
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        logger.warning("配置文件不存在: %s，使用默认配置", config_path)
        cfg = {}

    sources_cfg = cfg.get("sources", [])
    sources = [
        ConcordanceSource(
            name=s["name"],
            column=s["column"],
            weight=float(s.get("weight", 1.0)),
            description=s.get("description", ""),
        )
        for s in sources_cfg
    ]

    high_threshold = float(
        cfg.get("confidence", {}).get("high_threshold", 0.60)
    )

    if not sources:
        # 默认源：尝试常见列名
        logger.warning("配置中无 sources，尝试默认列名")
        sources = [
            ConcordanceSource("p1_rules", "p1_zone_label"),
            ConcordanceSource("zone_engine_v2", "z_lab_zone"),
            ConcordanceSource("outcome_anchored", "outcome_zone"),
            ConcordanceSource("anomaly_score", "anomaly_zone"),
        ]

    # 应用简单 VO₂peak 阈值规则（若 vo2_zone_simple 不存在）
    if "vo2_zone_simple" not in df.columns and "vo2_peak" in df.columns:
        vo2_cfg = cfg.get("vo2_simple_thresholds", {})
        red_upper = float(vo2_cfg.get("red_upper", 16.0))
        yellow_upper = float(vo2_cfg.get("yellow_upper", 22.0))
        df = df.copy()
        df["vo2_zone_simple"] = np.where(
            df["vo2_peak"].isna(), None,
            np.where(df["vo2_peak"] < red_upper, "red",
                     np.where(df["vo2_peak"] < yellow_upper, "yellow", "green"))
        )
        logger.info("已生成 vo2_zone_simple（阈值 red<%g, yellow<%g）", red_upper, yellow_upper)

    return compute_concordance(df, sources, high_threshold, outcome_col)


def generate_concordance_report(result: ConcordanceResult) -> str:
    """生成 Markdown 格式的一致性分析报告。"""
    lines = [
        "# 多定义一致性框架报告（Method 3 / Phase G）",
        "",
        "## 方法概述",
        "",
        "利用多个安全区定义的一致性/分歧量化患者分类的可靠性。",
        "一致 = 高信度；分歧 = 不确定区域（Stage 2 优先人群）。",
        "",
        f"**使用定义数**: {result.n_sources}",
        f"**定义列表**: {', '.join(result.sources_used)}",
        "",
        "## 安全区分布",
        "",
        "| 区 | N | 占比 |",
        "|---|---|---|",
    ]
    for z in ["green", "yellow", "red", "uncertain"]:
        info = result.zone_distribution.get(z, {})
        lines.append(f"| {z.capitalize()} | {info.get('n', 0)} | {info.get('pct', 0):.1f}% |")

    lines += [
        "",
        "## 信度统计",
        "",
        f"| 指标 | 值 |",
        f"|---|---|",
        f"| 高信度患者数 | {result.high_confidence_stats.get('n_high_confidence', 0)} |",
        f"| 高信度比例 | {result.high_confidence_stats.get('pct_high_confidence', 0):.1f}% |",
        f"| 不确定患者数 | {result.high_confidence_stats.get('n_uncertain', 0)} |",
        f"| 不确定比例 | {result.high_confidence_stats.get('pct_uncertain', 0):.1f}% |",
        f"| Green/Red 冲突数 | {result.high_confidence_stats.get('n_green_red_conflict', 0)} |",
        "",
    ]

    if result.outcome_by_zone_confidence:
        lines += [
            "## 各区 test_result 阳性率",
            "",
            "| 区 | 整体阳性率 | 高信度阳性率 | 高信度N |",
            "|---|---|---|---|",
        ]
        for z in ["green", "yellow", "red", "uncertain"]:
            info = result.outcome_by_zone_confidence.get(z, {})
            lines.append(
                f"| {z.capitalize()} | "
                f"{info.get('positive_rate_all', 0):.1f}% | "
                f"{info.get('positive_rate_high_confidence', 0):.1f}% | "
                f"{info.get('n_high_confidence', 0)} |"
            )

    return "\n".join(lines)
