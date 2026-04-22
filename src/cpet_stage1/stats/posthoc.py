"""
posthoc.py — Dunn's post-hoc 检验模块（Kruskal-Wallis 后处理）。

提供：
- DunnPosthoc.run(): 对指定变量跑 Dunn's 检验（Bonferroni 校正）
- PosthocResult: 结果容器（含 p-value 矩阵 + 显著对）
- generate_posthoc_report(): 生成 Markdown 报告

依赖：scikit-posthocs（如未安装，回退到手动 Dunn's 实现）
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)

# Dunn's 检验组合标签（中英文）
GROUP_LABEL_MAP = {
    "CTRL": "对照组",
    "HTN_HISTORY_NO_EHT": "既往HTN无运动HTN",
    "HTN_HISTORY_WITH_EHT": "既往HTN有运动HTN",
    "EHT_ONLY": "仅运动HTN",
}


@dataclass
class PosthocPairResult:
    """单个组对比较结果。"""
    group1: str
    group2: str
    statistic: float
    p_value_raw: float
    p_value_adjusted: float        # Bonferroni 校正后
    significant: bool              # α=0.05 校正后


@dataclass
class PosthocResult:
    """Dunn's 检验完整结果。"""
    variable: str
    kruskal_statistic: float
    kruskal_p: float
    n_comparisons: int
    alpha_adjusted: float          # 0.05 / n_comparisons
    pairs: list[PosthocPairResult]
    significant_pairs: list[PosthocPairResult]
    method: str = "dunn_bonferroni"

    def to_markdown(self) -> str:
        lines = [
            f"### {self.variable}",
            f"- Kruskal-Wallis: H={self.kruskal_statistic:.3f}, p={self.kruskal_p:.4f}",
            f"- 两两比较: {self.n_comparisons} 对（Bonferroni α={self.alpha_adjusted:.4f}）",
            "",
            "| 组1 | 组2 | Z统计量 | p (原始) | p (校正) | 显著 |",
            "|---|---|---|---|---|---|",
        ]
        for pair in self.pairs:
            sig = "✓" if pair.significant else ""
            lines.append(
                f"| {pair.group1} | {pair.group2} | "
                f"{pair.statistic:.3f} | {pair.p_value_raw:.4f} | "
                f"{pair.p_value_adjusted:.4f} | {sig} |"
            )
        return "\n".join(lines)


class DunnPosthoc:
    """
    Dunn's post-hoc 检验器。

    使用方法：
        analyzer = DunnPosthoc()
        results = analyzer.run(df, variables=["vo2_peak", "hr_peak"], group_col="group_code")
        report = generate_posthoc_report(results)
    """

    def run(
        self,
        df: pd.DataFrame,
        variables: list[str],
        group_col: str = "group_code",
        alpha: float = 0.05,
    ) -> dict[str, PosthocResult]:
        """
        对多个变量跑 Dunn's 检验。

        参数：
            df: 含变量列 + group_col 的 DataFrame
            variables: 要检验的连续变量列名列表
            group_col: 分组列名
            alpha: 显著性水平（Bonferroni 校正前）

        返回：{variable: PosthocResult}
        """
        results = {}
        groups = sorted(df[group_col].dropna().unique().tolist())

        for var in variables:
            if var not in df.columns:
                logger.warning("变量 %s 不存在，跳过", var)
                continue

            result = self._run_one(df, var, groups, group_col, alpha)
            if result is not None:
                results[var] = result

        return results

    def _run_one(
        self,
        df: pd.DataFrame,
        variable: str,
        groups: list[str],
        group_col: str,
        alpha: float,
    ) -> Optional[PosthocResult]:
        """对单个变量跑 Kruskal-Wallis + Dunn's 检验。"""
        # 提取各组数据
        group_data = {}
        for g in groups:
            vals = df.loc[df[group_col] == g, variable].dropna().values
            if len(vals) >= 3:
                group_data[g] = vals

        if len(group_data) < 2:
            logger.warning("变量 %s 有效组数 < 2，跳过", variable)
            return None

        # Kruskal-Wallis
        try:
            kw_stat, kw_p = scipy_stats.kruskal(*group_data.values())
        except Exception as e:
            logger.warning("KW检验失败 %s: %s", variable, e)
            return None

        # Dunn's 两两比较（手动实现）
        pairs_result = self._dunn_pairs(group_data, alpha)

        sig_pairs = [p for p in pairs_result if p.significant]

        return PosthocResult(
            variable=variable,
            kruskal_statistic=float(kw_stat),
            kruskal_p=float(kw_p),
            n_comparisons=len(pairs_result),
            alpha_adjusted=alpha / max(len(pairs_result), 1),
            pairs=pairs_result,
            significant_pairs=sig_pairs,
        )

    def _dunn_pairs(
        self,
        group_data: dict[str, np.ndarray],
        alpha: float,
    ) -> list[PosthocPairResult]:
        """
        手动 Dunn's 检验（Bonferroni 校正）。

        Dunn (1964) 方法：将所有数据合并排名，计算组间排名均值差，
        用 Z 统计量检验。
        """
        groups = list(group_data.keys())
        all_data = np.concatenate([group_data[g] for g in groups])
        all_groups = np.concatenate([[g] * len(group_data[g]) for g in groups])
        N = len(all_data)

        # 全局排名
        ranks = scipy_stats.rankdata(all_data)
        group_ranks = {g: ranks[all_groups == g] for g in groups}
        group_n = {g: len(v) for g, v in group_data.items()}

        # 修正系数（平均组）
        _, tie_counts = np.unique(all_data, return_counts=True)
        tie_correction = np.sum(tie_counts**3 - tie_counts) / (12 * (N - 1)) if N > 1 else 0
        se_base = np.sqrt((N * (N + 1) / 12 - tie_correction))

        pairs = list(itertools.combinations(groups, 2))
        n_comp = len(pairs)
        alpha_adj = alpha / n_comp if n_comp > 0 else alpha

        results = []
        for g1, g2 in pairs:
            r1_mean = np.mean(group_ranks[g1])
            r2_mean = np.mean(group_ranks[g2])
            n1, n2 = group_n[g1], group_n[g2]

            se = se_base * np.sqrt(1 / n1 + 1 / n2)
            if se == 0:
                z = 0.0
            else:
                z = (r1_mean - r2_mean) / se

            p_raw = 2 * (1 - scipy_stats.norm.cdf(abs(z)))
            p_adj = min(1.0, p_raw * n_comp)  # Bonferroni

            results.append(PosthocPairResult(
                group1=g1,
                group2=g2,
                statistic=float(z),
                p_value_raw=float(p_raw),
                p_value_adjusted=float(p_adj),
                significant=p_adj < alpha,
            ))

        return results


def generate_posthoc_report(
    results: dict[str, PosthocResult],
    output_path: str | Path = "reports/posthoc_report.md",
) -> str:
    """
    生成 Dunn's post-hoc 检验 Markdown 报告。

    参数：
        results: DunnPosthoc.run() 返回值
        output_path: 输出路径

    返回：报告文本
    """
    lines = [
        "# Post-hoc 两两比较报告（Dunn's 检验 + Bonferroni 校正）",
        "",
        f"> 共检验 {len(results)} 个变量",
        "",
    ]

    # 汇总：有显著差异的变量
    sig_vars = [v for v, r in results.items() if r.significant_pairs]
    lines.append(f"## 汇总：{len(sig_vars)}/{len(results)} 个变量有显著两两差异")
    lines.append("")
    if sig_vars:
        lines.append("| 变量 | 显著对数 | 示例显著对 |")
        lines.append("|---|---|---|")
        for var in sig_vars:
            r = results[var]
            ex = f"{r.significant_pairs[0].group1} vs {r.significant_pairs[0].group2}"
            lines.append(f"| {var} | {len(r.significant_pairs)} | {ex} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 各变量详情")
    lines.append("")

    for var, result in results.items():
        lines.append(result.to_markdown())
        lines.append("")

    report_text = "\n".join(lines)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    logger.info("Post-hoc 报告已保存: %s", output_path)

    return report_text
