"""
twobytwo.py — HTN × EIH 双因素效应分析。

使用 statsmodels Type II SS ANOVA：
- 主效应 A（htn_history）
- 主效应 B（eih_status）
- 交互效应 A×B
- 偏 eta² 效应量
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)


@dataclass
class TwoByTwoResult:
    """双因素分析结果。"""

    anova_table: pd.DataFrame           # 汇总 ANOVA 表（多变量 × 效应）
    descriptive: pd.DataFrame           # 各 cell 描述统计（均值±SD）
    n_per_cell: pd.DataFrame            # 各 cell 有效N
    config: dict[str, Any]

    def to_markdown(self, path: str | Path | None = None) -> str:
        """输出 Markdown 格式。"""
        lines = ["# HTN × EIH 双因素效应分析", ""]
        lines.append("## ANOVA 结果表")
        lines.append("")
        lines.append(_df_to_pipe_table(self.anova_table, index=False))
        lines.append("")
        lines.append("## 各 cell 描述统计（均值 ± SD）")
        lines.append("")
        lines.append(_df_to_pipe_table(self.descriptive, index=True))
        lines.append("")
        lines.append("## 各 cell 有效 N")
        lines.append("")
        lines.append(_df_to_pipe_table(self.n_per_cell, index=True))
        lines.append("")
        lines.append("*偏η²：small≥0.01，medium≥0.06，large≥0.14（Cohen 1988）*")

        md_str = "\n".join(lines)
        if path is not None:
            out_path = Path(path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md_str, encoding="utf-8")
            logger.info("TwoByTwo Markdown 保存: %s", out_path)

        return md_str


def _interpret_eta2(eta2: float) -> str:
    """解读效应量大小（Cohen 1988）。"""
    if np.isnan(eta2):
        return "—"
    if eta2 >= 0.14:
        return "large"
    if eta2 >= 0.06:
        return "medium"
    if eta2 >= 0.01:
        return "small"
    return "negligible"


def _format_pvalue(p: float) -> str:
    """格式化P值。"""
    if np.isnan(p):
        return "—"
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


class TwoByTwoAnalyzer:
    """
    HTN × EIH 双因素效应分析器。

    使用方法：
        analyzer = TwoByTwoAnalyzer("configs/stats/table1_config.yaml")
        result = analyzer.run(df)
        result.to_markdown("reports/twobytwo.md")
    """

    def __init__(self, config_path: str | Path) -> None:
        self._config_path = Path(config_path)
        self._cfg = self._load_config(self._config_path)
        self._t2_cfg = self._cfg.get("twobytwo", {})

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"stats 配置不存在: {path}")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @staticmethod
    def _compute_partial_eta_squared(ss_effect: float, ss_error: float) -> float:
        """
        偏 eta² = SS_effect / (SS_effect + SS_error)。

        若分母为0或无效，返回 nan。
        """
        denom = ss_effect + ss_error
        if denom <= 0 or np.isnan(denom):
            return float("nan")
        return float(ss_effect / denom)

    def _run_anova_2way(
        self,
        df: pd.DataFrame,
        outcome: str,
        factor_a: str,
        factor_b: str,
    ) -> dict[str, float]:
        """
        运行 Two-way ANOVA（Type II SS）。

        参数：
            df: 数据
            outcome: 结局变量列名
            factor_a: 因素A列名（htn_history）
            factor_b: 因素B列名（eih_status）

        返回：
            dict 含 F_A, p_A, F_B, p_B, F_AB, p_AB, eta2_A, eta2_B, eta2_AB, n_valid
        """
        try:
            import statsmodels.formula.api as smf
            from statsmodels.stats.anova import anova_lm
        except ImportError:
            logger.error("statsmodels 未安装，无法运行 ANOVA")
            return _empty_anova_result()

        # 准备子集（列表删除法处理缺失）
        needed = [outcome, factor_a, factor_b]
        sub = df[needed].dropna().copy()
        n_valid = len(sub)

        if n_valid < 10:
            logger.warning("ANOVA: %s 有效N过少（%d），跳过", outcome, n_valid)
            return _empty_anova_result(n_valid=n_valid)

        # 转为 bool → str 以便 statsmodels 识别分类因素
        sub[factor_a] = sub[factor_a].astype(bool).astype(str)
        sub[factor_b] = sub[factor_b].astype(bool).astype(str)

        formula = f"{outcome} ~ C({factor_a}) + C({factor_b}) + C({factor_a}):C({factor_b})"

        try:
            model = smf.ols(formula=formula, data=sub).fit()
            anova_tab = anova_lm(model, typ=2)
        except Exception as e:
            logger.warning("ANOVA 模型拟合失败 (%s): %s", outcome, e)
            return _empty_anova_result(n_valid=n_valid)

        # 提取结果（statsmodels Type II 表：index 为效应名）
        ss_res = float(anova_tab.loc["Residual", "sum_sq"])

        # 因素A
        a_key = _find_anova_key(anova_tab.index, factor_a, is_interaction=False)
        F_A, p_A, eta2_A = _extract_effect(anova_tab, a_key, ss_res, self)

        # 因素B
        b_key = _find_anova_key(anova_tab.index, factor_b, is_interaction=False)
        F_B, p_B, eta2_B = _extract_effect(anova_tab, b_key, ss_res, self)

        # 交互效应
        ab_key = _find_anova_key(anova_tab.index, factor_a, is_interaction=True, factor_b=factor_b)
        F_AB, p_AB, eta2_AB = _extract_effect(anova_tab, ab_key, ss_res, self)

        return {
            "n_valid": n_valid,
            "F_A": F_A, "p_A": p_A, "eta2_A": eta2_A,
            "F_B": F_B, "p_B": p_B, "eta2_B": eta2_B,
            "F_AB": F_AB, "p_AB": p_AB, "eta2_AB": eta2_AB,
        }

    def run(self, df: pd.DataFrame) -> TwoByTwoResult:
        """
        对所有结局变量运行双因素 ANOVA，返回 TwoByTwoResult。

        参数：
            df: 含 htn_history / eih_status 及结局变量的 DataFrame

        返回：
            TwoByTwoResult
        """
        factor_a = self._t2_cfg.get("factor_a", "htn_history")
        factor_b = self._t2_cfg.get("factor_b", "eih_status")
        outcomes_cfg = self._t2_cfg.get("outcomes", [])
        thresholds = self._t2_cfg.get("effect_size_thresholds", {})

        rows: list[dict[str, Any]] = []
        desc_rows: list[dict[str, Any]] = []
        n_rows: list[dict[str, Any]] = []

        for oc_cfg in outcomes_cfg:
            vname = oc_cfg["name"]
            vlabel = oc_cfg.get("label", vname)

            if vname not in df.columns:
                logger.debug("结局变量不存在，跳过: %s", vname)
                continue

            # 描述统计（各 cell 均值±SD）
            _compute_descriptive(df, vname, factor_a, factor_b, vlabel, desc_rows, n_rows)

            # ANOVA
            res = self._run_anova_2way(df, vname, factor_a, factor_b)

            rows.append({
                "变量": vlabel,
                "N有效": res["n_valid"],
                # 因素A
                f"F({factor_a})": f"{res['F_A']:.2f}" if not np.isnan(res["F_A"]) else "—",
                f"p({factor_a})": _format_pvalue(res["p_A"]),
                f"η²({factor_a})": f"{res['eta2_A']:.3f}" if not np.isnan(res["eta2_A"]) else "—",
                f"效应({factor_a})": _interpret_eta2(res["eta2_A"]),
                # 因素B
                f"F({factor_b})": f"{res['F_B']:.2f}" if not np.isnan(res["F_B"]) else "—",
                f"p({factor_b})": _format_pvalue(res["p_B"]),
                f"η²({factor_b})": f"{res['eta2_B']:.3f}" if not np.isnan(res["eta2_B"]) else "—",
                f"效应({factor_b})": _interpret_eta2(res["eta2_B"]),
                # 交互效应
                "F(A×B)": f"{res['F_AB']:.2f}" if not np.isnan(res["F_AB"]) else "—",
                "p(A×B)": _format_pvalue(res["p_AB"]),
                "η²(A×B)": f"{res['eta2_AB']:.3f}" if not np.isnan(res["eta2_AB"]) else "—",
                "效应(A×B)": _interpret_eta2(res["eta2_AB"]),
            })

        anova_table = pd.DataFrame(rows)

        # 构建描述统计透视表
        if desc_rows:
            desc_df = pd.DataFrame(desc_rows)
        else:
            desc_df = pd.DataFrame()

        if n_rows:
            n_df = pd.DataFrame(n_rows)
        else:
            n_df = pd.DataFrame()

        logger.info("TwoByTwo 分析完成: %d 个结局变量", len(rows))

        return TwoByTwoResult(
            anova_table=anova_table,
            descriptive=desc_df,
            n_per_cell=n_df,
            config=self._t2_cfg,
        )


# ============================================================
# 辅助函数
# ============================================================

def _empty_anova_result(n_valid: int = 0) -> dict[str, float]:
    """返回全NaN的ANOVA结果占位dict。"""
    return {
        "n_valid": n_valid,
        "F_A": float("nan"), "p_A": float("nan"), "eta2_A": float("nan"),
        "F_B": float("nan"), "p_B": float("nan"), "eta2_B": float("nan"),
        "F_AB": float("nan"), "p_AB": float("nan"), "eta2_AB": float("nan"),
    }


def _find_anova_key(index: pd.Index, factor: str, is_interaction: bool, factor_b: str = "") -> str:
    """
    在 statsmodels ANOVA 表 index 中定位效应行键。

    statsmodels 生成的键格式类似 "C(htn_history)" 或 "C(htn_history):C(eih_status)"
    """
    for key in index:
        key_str = str(key)
        if is_interaction:
            # 交互效应：含两个因素名且含 ":"
            if ":" in key_str and factor in key_str and factor_b in key_str:
                return key_str
        else:
            # 主效应：含因素名且不含 ":"（或仅含本因素）
            if factor in key_str and ":" not in key_str:
                return key_str
    return ""


def _extract_effect(
    anova_tab: "pd.DataFrame",
    key: str,
    ss_res: float,
    analyzer: TwoByTwoAnalyzer,
) -> tuple[float, float, float]:
    """提取F、p、eta²。"""
    if not key or key not in anova_tab.index:
        return float("nan"), float("nan"), float("nan")

    row = anova_tab.loc[key]
    F = float(row.get("F", float("nan")))
    p = float(row.get("PR(>F)", float("nan")))
    ss_eff = float(row.get("sum_sq", float("nan")))
    eta2 = analyzer._compute_partial_eta_squared(ss_eff, ss_res)

    return F, p, eta2


def _df_to_pipe_table(df: pd.DataFrame, index: bool = False) -> str:
    """将 DataFrame 转换为 Markdown pipe 表格（不依赖 tabulate）。"""
    if df is None or df.empty:
        return "*(空)*"
    if index:
        df = df.reset_index()
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    rows = []
    for _, row in df.iterrows():
        rows.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join([header, sep] + rows)


def _compute_descriptive(
    df: pd.DataFrame,
    vname: str,
    factor_a: str,
    factor_b: str,
    vlabel: str,
    desc_rows: list,
    n_rows: list,
) -> None:
    """计算各 2×2 cell 的描述统计（均值±SD、有效N）。"""
    for fa_val in [True, False]:
        for fb_val in [True, False]:
            try:
                fa_mask = df[factor_a].astype(bool) == fa_val if factor_a in df.columns \
                    else pd.Series(True, index=df.index)
                fb_mask = df[factor_b].astype(bool) == fb_val if factor_b in df.columns \
                    else pd.Series(True, index=df.index)
                cell_data = df.loc[fa_mask & fb_mask, vname].dropna()
                n = len(cell_data)
                mean_val = cell_data.mean() if n > 0 else float("nan")
                std_val = cell_data.std(ddof=1) if n > 1 else float("nan")
                cell_label = f"{factor_a}={'T' if fa_val else 'F'},{factor_b}={'T' if fb_val else 'F'}"

                desc_rows.append({
                    "变量": vlabel,
                    "Cell": cell_label,
                    "均值±SD": f"{mean_val:.2f}±{std_val:.2f}" if not np.isnan(mean_val) else "—",
                })
                n_rows.append({
                    "变量": vlabel,
                    "Cell": cell_label,
                    "N有效": n,
                })
            except Exception:
                pass
