"""
table1.py — Table 1 基线特征表生成器。

自动正态检测（Shapiro-Wilk），按正态/非正态格式化：
- 正态：mean ± SD
- 非正态：median [Q1, Q3]
分类变量：n (%)
组间检验：Kruskal-Wallis / chi-square
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)


@dataclass
class Table1Result:
    """Table 1 生成结果。"""

    table: pd.DataFrame         # 主表（变量 × 统计值+P值）
    config: dict[str, Any]      # 使用的配置
    group_n: dict[str, int]     # 各组有效N
    normality_flags: dict[str, bool]   # 各连续变量正态性判断

    def to_markdown(self, path: str | Path | None = None) -> str:
        """输出 Markdown 格式表格。"""
        lines = ["# Table 1：基线特征", ""]

        # 组标题行
        group_cols = [c for c in self.table.columns if c not in ("Variable", "P value")]
        header = "| 变量 | " + " | ".join(group_cols) + " | P值 |"
        separator = "|---|" + "---|" * len(group_cols) + "---|"
        lines.append(header)
        lines.append(separator)

        for _, row in self.table.iterrows():
            var = str(row.get("Variable", ""))
            p_val = str(row.get("P value", ""))
            group_vals = " | ".join(str(row.get(c, "")) for c in group_cols)
            lines.append(f"| {var} | {group_vals} | {p_val} |")

        lines.append("")
        # 注脚
        lines.append("*连续变量：正态分布 mean±SD，非正态 median[Q1,Q3]；分类变量：n(%)。*")
        lines.append("*组间比较：连续变量 Kruskal-Wallis；分类变量 χ² 检验。*")

        md_str = "\n".join(lines)
        if path is not None:
            out_path = Path(path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md_str, encoding="utf-8")
            logger.info("Table 1 Markdown 保存: %s", out_path)

        return md_str

    def to_csv(self, path: str | Path) -> None:
        """输出 CSV 格式表格。"""
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        self.table.to_csv(out_path, index=False, encoding="utf-8-sig")
        logger.info("Table 1 CSV 保存: %s", out_path)


class Table1Builder:
    """
    从 DataFrame 生成 Table 1 基线特征表。

    使用方法：
        builder = Table1Builder("configs/stats/table1_config.yaml")
        result = builder.build(df)
        result.to_markdown("reports/table1.md")
    """

    def __init__(self, config_path: str | Path) -> None:
        self._config_path = Path(config_path)
        self._cfg = self._load_config(self._config_path)
        self._t1_cfg = self._cfg.get("table1", {})

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"stats 配置不存在: {path}")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _test_normality(self, series: pd.Series) -> bool:
        """
        Shapiro-Wilk 正态性检验。

        - n<=4：返回 True（无法检验，默认正态）
        - n>5000：随机抽样 5000 条后检验
        返回：True = 正态，False = 非正态
        """
        s = series.dropna()
        n = len(s)
        if n <= 4:
            return True

        alpha = self._t1_cfg.get("tests", {}).get("normality", {}).get("alpha", 0.05)
        max_n = self._t1_cfg.get("tests", {}).get("normality", {}).get("max_n_for_exact", 5000)
        sample_n = self._t1_cfg.get("tests", {}).get("normality", {}).get("sample_n", 5000)

        if n > max_n:
            s = s.sample(n=sample_n, random_state=42)

        try:
            _, p_value = scipy_stats.shapiro(s)
            return bool(p_value >= alpha)
        except Exception:
            logger.warning("Shapiro-Wilk 失败，默认非正态")
            return False

    @staticmethod
    def _format_continuous(series: pd.Series, is_normal: bool) -> str:
        """
        格式化连续变量统计值。

        - 正态：mean ± SD（保留1位小数）
        - 非正态：median [Q1, Q3]（保留1位小数）
        """
        s = series.dropna()
        n = len(s)
        if n == 0:
            return "—"

        if is_normal:
            return f"{s.mean():.1f} ± {s.std(ddof=1):.1f}"
        else:
            q1 = s.quantile(0.25)
            q3 = s.quantile(0.75)
            return f"{s.median():.1f} [{q1:.1f}, {q3:.1f}]"

    @staticmethod
    def _format_categorical(series: pd.Series, positive_value: Any) -> str:
        """格式化分类变量：n (%)。"""
        s = series.dropna()
        n_total = len(s)
        if n_total == 0:
            return "—"

        # 统一类型比较
        try:
            if isinstance(positive_value, bool):
                # 处理 bool 列（包括 object 列中存储 True/False 字符串的情况）
                n_pos = int((s == positive_value).sum())
            else:
                n_pos = int((s.astype(str) == str(positive_value)).sum())
        except Exception:
            n_pos = 0

        pct = 100 * n_pos / n_total if n_total > 0 else 0
        return f"{n_pos} ({pct:.1f}%)"

    @staticmethod
    def _test_continuous_across_groups(
        groups: dict[str, pd.Series]
    ) -> tuple[float, str]:
        """
        Kruskal-Wallis 检验。

        返回：(p_value, formatted_p_string)
        """
        arrays = [s.dropna().values for s in groups.values()]
        # 过滤掉空组
        arrays = [a for a in arrays if len(a) > 0]
        if len(arrays) < 2:
            return float("nan"), "—"

        try:
            _, p = scipy_stats.kruskal(*arrays)
            return float(p), _format_pvalue(p)
        except Exception as e:
            logger.warning("Kruskal-Wallis 失败: %s", e)
            return float("nan"), "—"

    @staticmethod
    def _test_categorical_across_groups(
        contingency: pd.DataFrame,
    ) -> tuple[float, str]:
        """
        chi-square 检验。

        参数：contingency 是 pd.crosstab 结果
        返回：(p_value, formatted_p_string)
        """
        try:
            _, p, _, _ = scipy_stats.chi2_contingency(contingency.values)
            return float(p), _format_pvalue(p)
        except Exception as e:
            logger.warning("chi2_contingency 失败: %s", e)
            return float("nan"), "—"

    def build(
        self,
        df: pd.DataFrame,
        group_column: str | None = None,
    ) -> Table1Result:
        """
        构建 Table 1。

        参数：
            df: 含所有分析字段的 DataFrame
            group_column: 分组列名（覆盖配置）

        返回：
            Table1Result
        """
        grp_col = group_column or self._t1_cfg.get("group_column", "group_code")
        group_order = self._t1_cfg.get("group_order", [])
        group_labels = self._t1_cfg.get("group_labels", {})
        cont_vars = self._t1_cfg.get("continuous_variables", [])
        cat_vars = self._t1_cfg.get("categorical_variables", [])

        # 构建有效的分组顺序（仅保留 df 中实际存在的组）
        if grp_col in df.columns:
            actual_groups = df[grp_col].dropna().unique().tolist()
            ordered_groups = [g for g in group_order if g in actual_groups]
            # 追加未在 group_order 中的组
            for g in sorted(actual_groups):
                if g not in ordered_groups:
                    ordered_groups.append(g)
        else:
            ordered_groups = []
            logger.warning("分组列不存在: %s，生成单组表格", grp_col)

        # 各组 N
        group_n: dict[str, int] = {}
        if grp_col in df.columns:
            for g in ordered_groups:
                group_n[g] = int((df[grp_col] == g).sum())
        else:
            group_n["All"] = len(df)

        # 列名（使用中文标签或原始分组名）
        col_names = {
            g: group_labels.get(g, g) + f"\n(n={group_n.get(g, 0)})"
            for g in ordered_groups
        }

        rows: list[dict[str, str]] = []
        normality_flags: dict[str, bool] = {}

        # ---- 连续变量 ----
        for var_cfg in cont_vars:
            vname = var_cfg["name"]
            vlabel = var_cfg.get("label", vname)
            force_format = var_cfg.get("force_format", None)  # "normal" / "nonnormal"

            if vname not in df.columns:
                logger.debug("连续变量列不存在，跳过: %s", vname)
                continue

            # 正态性检验
            if force_format == "normal":
                is_normal = True
            elif force_format == "nonnormal":
                is_normal = False
            else:
                is_normal = self._test_normality(df[vname])

            normality_flags[vname] = is_normal

            row: dict[str, str] = {"Variable": vlabel}

            if ordered_groups and grp_col in df.columns:
                groups_series: dict[str, pd.Series] = {}
                for g in ordered_groups:
                    mask = df[grp_col] == g
                    groups_series[g] = df.loc[mask, vname]
                    col_key = col_names[g]
                    # 格式化并附有效N
                    s = df.loc[mask, vname]
                    n_valid = int(s.notna().sum())
                    row[col_key] = self._format_continuous(s, is_normal)
                    # 若有缺失，补注有效N
                    if n_valid < len(s):
                        row[col_key] += f" [n={n_valid}]"

                # 组间检验
                _, p_str = self._test_continuous_across_groups(groups_series)
                row["P value"] = p_str
            else:
                row["All"] = self._format_continuous(df[vname], is_normal)
                row["P value"] = "—"

            # 格式标注
            fmt_note = " (mean±SD)" if is_normal else " (median[IQR])"
            row["Variable"] = vlabel + fmt_note

            rows.append(row)

        # ---- 分类变量 ----
        for var_cfg in cat_vars:
            vname = var_cfg["name"]
            vlabel = var_cfg.get("label", vname)
            pos_val = var_cfg.get("positive_value", True)

            if vname not in df.columns:
                logger.debug("分类变量列不存在，跳过: %s", vname)
                continue

            row = {"Variable": vlabel}

            if ordered_groups and grp_col in df.columns:
                # 构建列联表
                try:
                    cross = pd.crosstab(df[grp_col], df[vname])
                    _, p_str = self._test_categorical_across_groups(cross)
                except Exception:
                    p_str = "—"

                for g in ordered_groups:
                    mask = df[grp_col] == g
                    col_key = col_names[g]
                    row[col_key] = self._format_categorical(df.loc[mask, vname], pos_val)

                row["P value"] = p_str
            else:
                row["All"] = self._format_categorical(df[vname], pos_val)
                row["P value"] = "—"

            rows.append(row)

        # 构建 DataFrame
        all_cols = ["Variable"] + list(col_names.values()) + ["P value"]
        if not ordered_groups:
            all_cols = ["Variable", "All", "P value"]

        table = pd.DataFrame(rows)
        # 按列顺序整理
        present_cols = [c for c in all_cols if c in table.columns]
        table = table[present_cols].fillna("—")

        logger.info(
            "Table 1 构建完成: %d 行变量，%d 分组",
            len(rows), len(ordered_groups),
        )

        return Table1Result(
            table=table,
            config=self._t1_cfg,
            group_n=group_n,
            normality_flags=normality_flags,
        )


def build_stratified_table1(
    builder: Table1Builder,
    df: pd.DataFrame,
    stratify_col: str,
) -> dict[str, Table1Result]:
    """
    按分层列（如协议类型）分别构建 Table 1。

    用于协议敏感性分析。

    参数：
        builder: Table1Builder 实例
        df: 数据
        stratify_col: 分层列名

    返回：
        dict{stratum_value: Table1Result}
    """
    if stratify_col not in df.columns:
        raise ValueError(f"分层列不存在: {stratify_col}")

    results: dict[str, Table1Result] = {}
    for stratum in sorted(df[stratify_col].dropna().unique()):
        sub = df[df[stratify_col] == stratum].copy()
        logger.info("敏感性分析 - 协议: %s，n=%d", stratum, len(sub))
        results[str(stratum)] = builder.build(sub)

    return results


def _format_pvalue(p: float) -> str:
    """格式化P值：<0.001 / <0.01 / 精确值（3位有效数字）。"""
    if np.isnan(p):
        return "—"
    if p < 0.001:
        return "<0.001"
    if p < 0.01:
        return f"{p:.3f}"
    return f"{p:.3f}"
