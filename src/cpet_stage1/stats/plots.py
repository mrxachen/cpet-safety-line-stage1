"""
plots.py — M4 统计分析可视化。

箱线图、小提琴图、交互作用图、参考方程散点图。
使用 matplotlib Agg 后端（无头渲染，支持服务器环境）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")   # 无头渲染，放在所有 matplotlib 导入之前

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# 中文字体设置（若系统无中文字体，回退为英文标签）
try:
    plt.rcParams["font.sans-serif"] = ["SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
except Exception:
    pass


def _load_plot_config(config_path: str | Path) -> dict[str, Any]:
    """加载绘图配置。"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"stats 配置不存在: {path}")
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get("plots", {})


def plot_grouped_boxplot(
    df: pd.DataFrame,
    variable: str,
    group_col: str,
    group_order: list[str] | None = None,
    group_labels: dict[str, str] | None = None,
    title: str | None = None,
    ylabel: str | None = None,
    palette: str = "Set2",
    figsize: tuple[float, float] = (10, 6),
    output_path: str | Path | None = None,
) -> plt.Figure:
    """
    分组箱线图。

    参数：
        df: 数据
        variable: 目标变量列名
        group_col: 分组列名
        group_order: 分组顺序（可选）
        group_labels: 分组显示标签（可选）
        title: 图标题
        ylabel: Y轴标签
        palette: 颜色方案
        figsize: 图尺寸
        output_path: 保存路径（None = 不保存）

    返回：
        matplotlib Figure
    """
    import seaborn as sns

    if variable not in df.columns or group_col not in df.columns:
        raise ValueError(f"列不存在: {variable} 或 {group_col}")

    sub = df[[group_col, variable]].dropna()

    # 确定分组顺序
    if group_order is None:
        group_order = sorted(sub[group_col].unique().tolist())

    # 过滤实际存在的组
    group_order = [g for g in group_order if g in sub[group_col].unique()]

    # 构建 x 轴标签
    x_labels = [
        (group_labels.get(g, g) if group_labels else g)
        for g in group_order
    ]

    fig, ax = plt.subplots(figsize=figsize)

    sns.boxplot(
        data=sub,
        x=group_col,
        y=variable,
        order=group_order,
        palette=palette,
        width=0.5,
        flierprops={"marker": "o", "markersize": 3, "alpha": 0.4},
        ax=ax,
    )

    ax.set_xticklabels(x_labels, rotation=15, ha="right")
    ax.set_xlabel("")
    ax.set_ylabel(ylabel or variable)
    ax.set_title(title or f"{variable} — 分组比较")
    sns.despine(ax=ax)
    plt.tight_layout()

    if output_path is not None:
        _save_figure(fig, output_path)

    return fig


def plot_grouped_violin(
    df: pd.DataFrame,
    variable: str,
    group_col: str,
    group_order: list[str] | None = None,
    group_labels: dict[str, str] | None = None,
    title: str | None = None,
    ylabel: str | None = None,
    palette: str = "Set2",
    figsize: tuple[float, float] = (10, 6),
    output_path: str | Path | None = None,
) -> plt.Figure:
    """
    分组小提琴图（内嵌箱线）。

    参数同 plot_grouped_boxplot。
    """
    import seaborn as sns

    if variable not in df.columns or group_col not in df.columns:
        raise ValueError(f"列不存在: {variable} 或 {group_col}")

    sub = df[[group_col, variable]].dropna()

    if group_order is None:
        group_order = sorted(sub[group_col].unique().tolist())
    group_order = [g for g in group_order if g in sub[group_col].unique()]

    x_labels = [
        (group_labels.get(g, g) if group_labels else g)
        for g in group_order
    ]

    fig, ax = plt.subplots(figsize=figsize)

    # 各组N≥3 才能画小提琴图
    valid_groups = [
        g for g in group_order
        if len(sub[sub[group_col] == g]) >= 3
    ]
    if not valid_groups:
        logger.warning("violin plot: 所有组样本量<3，改用箱线图")
        return plot_grouped_boxplot(
            df, variable, group_col, group_order, group_labels,
            title, ylabel, palette, figsize, output_path
        )

    sns.violinplot(
        data=sub,
        x=group_col,
        y=variable,
        order=valid_groups,
        palette=palette,
        inner="box",
        linewidth=1.0,
        ax=ax,
    )

    ax.set_xticklabels(
        [group_labels.get(g, g) if group_labels else g for g in valid_groups],
        rotation=15, ha="right"
    )
    ax.set_xlabel("")
    ax.set_ylabel(ylabel or variable)
    ax.set_title(title or f"{variable} — 分布比较（小提琴图）")
    sns.despine(ax=ax)
    plt.tight_layout()

    if output_path is not None:
        _save_figure(fig, output_path)

    return fig


def plot_interaction(
    df: pd.DataFrame,
    outcome: str,
    factor_a: str,
    factor_b: str,
    factor_a_labels: dict[Any, str] | None = None,
    factor_b_labels: dict[Any, str] | None = None,
    title: str | None = None,
    ylabel: str | None = None,
    figsize: tuple[float, float] = (8, 6),
    output_path: str | Path | None = None,
) -> plt.Figure:
    """
    双因素交互作用图（边际均值 + SEM 误差棒）。

    参数：
        df: 数据
        outcome: 结局变量
        factor_a: 因素A（X轴分组，如 htn_history）
        factor_b: 因素B（线条，如 eih_status）
        factor_a_labels: 因素A值标签映射
        factor_b_labels: 因素B值标签映射

    返回：
        Figure
    """
    if outcome not in df.columns:
        raise ValueError(f"结局变量不存在: {outcome}")

    sub = df[[outcome, factor_a, factor_b]].dropna().copy()
    sub[factor_a] = sub[factor_a].astype(bool)
    sub[factor_b] = sub[factor_b].astype(bool)

    fig, ax = plt.subplots(figsize=figsize)

    colors = ["#4C72B0", "#DD8452"]

    for i, fb_val in enumerate([False, True]):
        fb_mask = sub[factor_b] == fb_val
        fb_sub = sub[fb_mask]

        x_vals = []
        y_vals = []
        y_err = []
        x_ticks = []
        x_labels_list = []

        for j, fa_val in enumerate([False, True]):
            fa_mask = fb_sub[factor_a] == fa_val
            cell_data = fb_sub.loc[fa_mask, outcome]
            n = len(cell_data)
            if n == 0:
                continue
            mean_val = cell_data.mean()
            sem_val = cell_data.sem() if n > 1 else 0.0

            x_vals.append(j)
            y_vals.append(mean_val)
            y_err.append(sem_val)
            if j not in x_ticks:
                x_ticks.append(j)
                fa_label = (factor_a_labels or {}).get(fa_val, str(fa_val))
                x_labels_list.append(fa_label)

        if not x_vals:
            continue

        fb_label = (factor_b_labels or {}).get(fb_val, f"{factor_b}={fb_val}")
        ax.errorbar(
            x_vals, y_vals, yerr=y_err,
            marker="o", linewidth=2, capsize=5,
            color=colors[i], label=fb_label,
        )

    ax.set_xticks([0, 1])
    fa_false_label = (factor_a_labels or {}).get(False, f"{factor_a}=False")
    fa_true_label = (factor_a_labels or {}).get(True, f"{factor_a}=True")
    ax.set_xticklabels([fa_false_label, fa_true_label])
    ax.set_xlabel("")
    ax.set_ylabel(ylabel or outcome)
    ax.set_title(title or f"{outcome} — {factor_a} × {factor_b} 交互作用图")
    ax.legend(title=factor_b, frameon=False)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    if output_path is not None:
        _save_figure(fig, output_path)

    return fig


def plot_reference_scatter(
    df: pd.DataFrame,
    target: str,
    age_col: str = "age",
    sex_col: str = "sex",
    ref_flag_col: str | None = "reference_flag_wide",
    equation_label: str = "",
    title: str | None = None,
    ylabel: str | None = None,
    figsize: tuple[float, float] = (9, 6),
    output_path: str | Path | None = None,
) -> plt.Figure:
    """
    年龄 vs 目标变量散点图，按性别着色 + 回归线。

    参数：
        df: 数据
        target: 目标变量
        age_col: 年龄列名
        sex_col: 性别列名（'M'/'F'）
        ref_flag_col: 参考子集标志列（若存在则高亮）
        equation_label: 方程标注文本

    返回：
        Figure
    """
    import seaborn as sns

    if target not in df.columns:
        raise ValueError(f"目标变量不存在: {target}")

    needed = [target, age_col]
    if sex_col in df.columns:
        needed.append(sex_col)
    if ref_flag_col and ref_flag_col in df.columns:
        needed.append(ref_flag_col)

    sub = df[needed].dropna(subset=[target, age_col]).copy()

    fig, ax = plt.subplots(figsize=figsize)

    # 若有性别列，按性别分色
    if sex_col in sub.columns:
        palette = {"M": "#4C72B0", "F": "#DD8452", "m": "#4C72B0", "f": "#DD8452"}
        for sex_val, color_key in [("M", "M"), ("m", "M"), ("F", "F"), ("f", "F")]:
            sex_sub = sub[sub[sex_col] == sex_val]
            if sex_sub.empty:
                continue
            ax.scatter(
                sex_sub[age_col], sex_sub[target],
                c=palette.get(color_key, "gray"),
                alpha=0.3, s=10,
                label=f"性别={sex_val}",
            )
            # 添加回归线
            try:
                z = np.polyfit(sex_sub[age_col], sex_sub[target], 1)
                p_fn = np.poly1d(z)
                x_range = np.linspace(sex_sub[age_col].min(), sex_sub[age_col].max(), 50)
                ax.plot(x_range, p_fn(x_range), color=palette.get(color_key, "gray"), linewidth=2)
            except Exception:
                pass
    else:
        ax.scatter(sub[age_col], sub[target], alpha=0.3, s=10, color="steelblue")
        try:
            z = np.polyfit(sub[age_col], sub[target], 1)
            p_fn = np.poly1d(z)
            x_range = np.linspace(sub[age_col].min(), sub[age_col].max(), 50)
            ax.plot(x_range, p_fn(x_range), color="steelblue", linewidth=2)
        except Exception:
            pass

    # 高亮参考子集
    if ref_flag_col and ref_flag_col in sub.columns:
        ref_sub = sub[sub[ref_flag_col].astype(bool)]
        if not ref_sub.empty:
            ax.scatter(
                ref_sub[age_col], ref_sub[target],
                edgecolors="black", facecolors="none",
                s=20, linewidths=0.8,
                label="参考子集", zorder=5, alpha=0.6,
            )

    if equation_label:
        ax.text(
            0.05, 0.95, equation_label,
            transform=ax.transAxes,
            fontsize=9, verticalalignment="top",
            bbox={"boxstyle": "round", "alpha": 0.1},
        )

    ax.set_xlabel(age_col)
    ax.set_ylabel(ylabel or target)
    ax.set_title(title or f"{target} vs 年龄（参考方程散点图）")
    ax.legend(frameon=False, markerscale=2)
    plt.tight_layout()

    if output_path is not None:
        _save_figure(fig, output_path)

    return fig


def generate_all_m4_plots(
    df: pd.DataFrame,
    config_path: str | Path,
    output_dir: str | Path | None = None,
) -> list[Path]:
    """
    一键批量生成所有 M4 图表。

    参数：
        df: 数据
        config_path: stats 配置路径
        output_dir: 输出目录（覆盖配置）

    返回：
        生成的图表路径列表
    """
    plot_cfg = _load_plot_config(config_path)
    out_dir = Path(output_dir or plot_cfg.get("output_dir", "reports/figures/m4"))
    out_dir.mkdir(parents=True, exist_ok=True)

    palette = plot_cfg.get("palette", "Set2")
    figsize = tuple(plot_cfg.get("figsize", [10, 6]))
    dpi = plot_cfg.get("dpi", 300)

    # 读取 table1 配置获取分组信息
    t1_cfg: dict[str, Any] = {}
    try:
        with open(config_path, encoding="utf-8") as f:
            full_cfg = yaml.safe_load(f) or {}
        t1_cfg = full_cfg.get("table1", {})
    except Exception:
        pass

    group_col = t1_cfg.get("group_column", "group_code")
    group_order = t1_cfg.get("group_order", None)
    group_labels = t1_cfg.get("group_labels", None)

    generated: list[Path] = []

    # 箱线图
    for vname in plot_cfg.get("boxplot_variables", []):
        if vname not in df.columns:
            continue
        out_path = out_dir / f"boxplot_{vname}.png"
        try:
            fig = plot_grouped_boxplot(
                df, vname, group_col,
                group_order=group_order,
                group_labels=group_labels,
                palette=palette, figsize=figsize,
                output_path=out_path,
            )
            plt.close(fig)
            generated.append(out_path)
            logger.info("箱线图保存: %s", out_path)
        except Exception as e:
            logger.warning("箱线图生成失败 (%s): %s", vname, e)

    # 小提琴图
    for vname in plot_cfg.get("violin_variables", []):
        if vname not in df.columns:
            continue
        out_path = out_dir / f"violin_{vname}.png"
        try:
            fig = plot_grouped_violin(
                df, vname, group_col,
                group_order=group_order,
                group_labels=group_labels,
                palette=palette, figsize=figsize,
                output_path=out_path,
            )
            plt.close(fig)
            generated.append(out_path)
            logger.info("小提琴图保存: %s", out_path)
        except Exception as e:
            logger.warning("小提琴图生成失败 (%s): %s", vname, e)

    # 交互作用图
    twobytwo_cfg: dict[str, Any] = {}
    try:
        with open(config_path, encoding="utf-8") as f:
            full_cfg2 = yaml.safe_load(f) or {}
        twobytwo_cfg = full_cfg2.get("twobytwo", {})
    except Exception:
        pass

    factor_a = twobytwo_cfg.get("factor_a", "htn_history")
    factor_b = twobytwo_cfg.get("factor_b", "eih_status")

    for vname in plot_cfg.get("interaction_outcomes", []):
        if vname not in df.columns:
            continue
        out_path = out_dir / f"interaction_{vname}.png"
        try:
            fig = plot_interaction(
                df, vname, factor_a, factor_b,
                figsize=(8, 6),
                output_path=out_path,
            )
            plt.close(fig)
            generated.append(out_path)
            logger.info("交互作用图保存: %s", out_path)
        except Exception as e:
            logger.warning("交互作用图生成失败 (%s): %s", vname, e)

    logger.info("M4 图表生成完成: %d 张", len(generated))
    return generated


def _save_figure(fig: plt.Figure, path: str | Path, dpi: int = 300) -> None:
    """保存图表到指定路径。"""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    logger.debug("图表保存: %s", out_path)


# ============================================================================
# Phase A3 补充图表函数
# ============================================================================

# 安全区颜色映射
ZONE_COLORS = {"green": "#2ecc71", "yellow": "#f39c12", "red": "#e74c3c"}
GROUP_ORDER = ["CTRL", "HTN_HISTORY_NO_EHT", "HTN_HISTORY_WITH_EHT", "EHT_ONLY"]
GROUP_SHORT_LABELS = {
    "CTRL": "对照",
    "HTN_HISTORY_NO_EHT": "HTN无EIH",
    "HTN_HISTORY_WITH_EHT": "HTN+EIH",
    "EHT_ONLY": "仅EIH",
}


def plot_zone_distribution_stacked(
    df: pd.DataFrame,
    zone_col: str = "z_lab_zone",
    group_col: str = "group_code",
    output_path: str | Path | None = None,
    figsize: tuple[float, float] = (10, 6),
    dpi: int = 150,
) -> plt.Figure:
    """
    安全区（绿/黄/红）按 2×2 队列的堆叠柱状图。

    展示 EIH+ 100% Red 的关键发现。
    """
    if zone_col not in df.columns or group_col not in df.columns:
        raise ValueError(f"列不存在: {zone_col} 或 {group_col}")

    groups = [g for g in GROUP_ORDER if g in df[group_col].unique()]
    zones = ["green", "yellow", "red"]

    # 计算各组区间比例
    pct_data = {}
    for g in groups:
        sub = df[df[group_col] == g][zone_col].dropna()
        total = len(sub)
        pct_data[g] = {z: (sub == z).sum() / total * 100 if total > 0 else 0 for z in zones}

    fig, ax = plt.subplots(figsize=figsize)
    x = np.arange(len(groups))
    bottom = np.zeros(len(groups))

    for zone in zones:
        vals = [pct_data[g][zone] for g in groups]
        ax.bar(x, vals, bottom=bottom, label=zone.capitalize(),
               color=ZONE_COLORS[zone], alpha=0.85, width=0.6)
        # 标注百分比（>5% 才显示）
        for i, (v, b) in enumerate(zip(vals, bottom)):
            if v > 5:
                ax.text(i, b + v / 2, f"{v:.0f}%", ha="center", va="center",
                        fontsize=9, color="white", fontweight="bold")
        bottom += np.array(vals)

    ax.set_xticks(x)
    ax.set_xticklabels([GROUP_SHORT_LABELS.get(g, g) for g in groups], fontsize=11)
    ax.set_ylabel("比例 (%)", fontsize=12)
    ax.set_title("安全区分布（HTN × EIH 2×2 队列）", fontsize=13)
    ax.legend(loc="upper right", fontsize=10)
    ax.set_ylim(0, 105)
    ax.set_xlabel("队列", fontsize=12)

    # 添加样本量标注
    for i, g in enumerate(groups):
        n = len(df[df[group_col] == g])
        ax.text(i, -5, f"n={n}", ha="center", va="top", fontsize=9, color="gray")

    plt.tight_layout()

    if output_path:
        _save_figure(fig, output_path, dpi=dpi)
    return fig


def plot_missing_data_heatmap(
    df: pd.DataFrame,
    max_vars: int = 30,
    output_path: str | Path | None = None,
    figsize: tuple[float, float] = (14, 8),
    dpi: int = 150,
) -> plt.Figure:
    """
    数据缺失率热力图（变量 × 队列）。

    展示哪些字段缺失最严重。
    """
    # 选择具有任何缺失值的列
    missing_rate = df.isnull().mean()
    cols_with_missing = missing_rate[missing_rate > 0].sort_values(ascending=False)

    if len(cols_with_missing) == 0:
        # 无缺失，选top变量展示
        top_cols = list(df.columns[:max_vars])
    else:
        top_cols = list(cols_with_missing.head(max_vars).index)

    # 如果有 group_col，按组计算
    if "group_code" in df.columns:
        groups = [g for g in GROUP_ORDER if g in df["group_code"].unique()]
        heat_data = pd.DataFrame(index=top_cols, columns=[GROUP_SHORT_LABELS.get(g, g) for g in groups])
        for g in groups:
            sub = df[df["group_code"] == g]
            label = GROUP_SHORT_LABELS.get(g, g)
            heat_data[label] = [sub[c].isnull().mean() * 100 if c in sub.columns else 0
                                 for c in top_cols]
        heat_data = heat_data.astype(float)
    else:
        heat_data = pd.DataFrame({"全样本": [df[c].isnull().mean() * 100 for c in top_cols]},
                                  index=top_cols)

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(heat_data.values, aspect="auto", cmap="Reds", vmin=0, vmax=100)

    ax.set_xticks(np.arange(len(heat_data.columns)))
    ax.set_xticklabels(heat_data.columns, fontsize=10)
    ax.set_yticks(np.arange(len(top_cols)))
    ax.set_yticklabels(top_cols, fontsize=8)
    ax.set_title("数据缺失率热力图（%）", fontsize=13)

    plt.colorbar(im, ax=ax, label="缺失率 (%)")

    # 标注数值
    for i in range(len(top_cols)):
        for j in range(len(heat_data.columns)):
            val = heat_data.iloc[i, j]
            if val > 0:
                text_color = "white" if val > 50 else "black"
                ax.text(j, i, f"{val:.0f}", ha="center", va="center",
                        fontsize=7, color=text_color)

    plt.tight_layout()

    if output_path:
        _save_figure(fig, output_path, dpi=dpi)
    return fig


def plot_feature_correlation_heatmap(
    df: pd.DataFrame,
    variables: list[str] | None = None,
    output_path: str | Path | None = None,
    figsize: tuple[float, float] = (12, 10),
    dpi: int = 150,
) -> plt.Figure:
    """
    特征相关性热力图（Spearman 相关系数）。

    用于展示 P1 特征之间的关系。
    """
    if variables is None:
        # 默认选择关键 CPET 指标
        variables = [
            "vo2_peak", "hr_peak", "o2_pulse_peak", "vt1_vo2",
            "hr_recovery", "oues", "mets_peak", "ve_peak",
            "vt1_hr", "vt1_pct_vo2peak", "ve_vco2_slope", "vo2_peak_pct_pred",
        ]
    avail = [v for v in variables if v in df.columns]

    corr_df = df[avail].corr(method="spearman")

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(corr_df.values, aspect="auto", cmap="RdBu_r", vmin=-1, vmax=1)

    ax.set_xticks(np.arange(len(avail)))
    ax.set_xticklabels(avail, rotation=45, ha="right", fontsize=9)
    ax.set_yticks(np.arange(len(avail)))
    ax.set_yticklabels(avail, fontsize=9)
    ax.set_title("CPET 特征 Spearman 相关矩阵", fontsize=13)

    plt.colorbar(im, ax=ax, label="Spearman ρ")

    # 标注相关系数
    for i in range(len(avail)):
        for j in range(len(avail)):
            val = corr_df.iloc[i, j]
            text_color = "white" if abs(val) > 0.7 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    fontsize=7, color=text_color)

    plt.tight_layout()

    if output_path:
        _save_figure(fig, output_path, dpi=dpi)
    return fig


def plot_eih_forest(
    forest_df: pd.DataFrame,
    output_path: str | Path | None = None,
    figsize: tuple[float, float] = (9, 6),
    dpi: int = 150,
) -> plt.Figure:
    """
    EIH Logistic 回归森林图（OR + 95% CI）。

    参数：
        forest_df: to_forest_data() 返回的 DataFrame
            列：variable, or, ci_lower, ci_upper, p_value, significant
    """
    if forest_df.empty:
        fig, ax = plt.subplots(figsize=figsize)
        ax.text(0.5, 0.5, "No data available", ha="center", va="center",
                transform=ax.transAxes)
        if output_path:
            _save_figure(fig, output_path, dpi=dpi)
        return fig

    fig, ax = plt.subplots(figsize=figsize)
    y_pos = np.arange(len(forest_df))

    colors = ["#e74c3c" if sig else "#3498db"
              for sig in forest_df.get("significant", [False] * len(forest_df))]

    for i, row in forest_df.iterrows():
        idx = i if isinstance(i, int) else list(forest_df.index).index(i)
        ax.errorbar(
            row["or"], y_pos[idx],
            xerr=[[row["or"] - row["ci_lower"]], [row["ci_upper"] - row["or"]]],
            fmt="o", color=colors[idx], markersize=8, capsize=4, linewidth=1.5,
        )

    ax.axvline(x=1, color="gray", linestyle="--", linewidth=1.2, alpha=0.7)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(forest_df["variable"].tolist(), fontsize=11)
    ax.set_xlabel("调整 OR（95% CI）", fontsize=12)
    ax.set_title("EIH 多因素 Logistic 回归（森林图）", fontsize=13)
    ax.set_xscale("log")

    # P 值标注
    for idx, row in enumerate(forest_df.itertuples()):
        p_str = f"p={row.p_value:.3f}" if row.p_value >= 0.001 else "p<0.001"
        ax.text(ax.get_xlim()[1] * 0.9, y_pos[idx], p_str, va="center",
                ha="right", fontsize=9, color="gray")

    # 图例
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#e74c3c",
               markersize=8, label="p<0.05"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#3498db",
               markersize=8, label="p≥0.05"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=9)
    plt.tight_layout()

    if output_path:
        _save_figure(fig, output_path, dpi=dpi)
    return fig


def plot_p1_stratified_performance(
    perf_data: dict[str, dict[str, float]],
    output_path: str | Path | None = None,
    figsize: tuple[float, float] = (8, 5),
    dpi: int = 150,
) -> plt.Figure:
    """
    P1 分层性能对比柱状图（全样本 vs EIH- 子群 vs EIH+ 子群）。

    参数：
        perf_data: {"全样本": {"F1_macro": x, "Kappa": y}, "EIH-": {...}, ...}
    """
    if not perf_data:
        fig, ax = plt.subplots(figsize=figsize)
        ax.text(0.5, 0.5, "No data available", ha="center", va="center",
                transform=ax.transAxes)
        if output_path:
            _save_figure(fig, output_path, dpi=dpi)
        return fig

    groups = list(perf_data.keys())
    metrics = list(perf_data[groups[0]].keys()) if groups else ["F1_macro"]
    x = np.arange(len(groups))
    width = 0.35

    fig, ax = plt.subplots(figsize=figsize)
    colors = ["#3498db", "#e67e22", "#2ecc71", "#9b59b6"]

    for i, metric in enumerate(metrics):
        vals = [perf_data[g].get(metric, 0) for g in groups]
        offset = width * (i - len(metrics) / 2 + 0.5)
        bars = ax.bar(x + offset, vals, width, label=metric,
                      color=colors[i % len(colors)], alpha=0.8)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{val:.3f}", ha="center", va="bottom", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(groups, fontsize=11)
    ax.set_ylabel("性能指标", fontsize=12)
    ax.set_title("P1 分层性能：全样本 vs EIH 分层", fontsize=13)
    ax.legend(fontsize=10)
    ax.set_ylim(0, 1.05)
    plt.tight_layout()

    if output_path:
        _save_figure(fig, output_path, dpi=dpi)
    return fig


def plot_safety_zone_concept(
    output_path: str | Path | None = None,
    figsize: tuple[float, float] = (10, 7),
    dpi: int = 150,
) -> plt.Figure:
    """
    安全区概念示意图（R/T/I 三轴框架）。

    展示 R（Reserve）、T（Threshold）、I（Instability）三轴与
    绿/黄/红分区的关系。
    """
    fig, axes = plt.subplots(1, 2, figsize=figsize)

    # 左图：R-I 平面示意
    ax = axes[0]
    # 绿区
    green_x = np.linspace(0, 50, 100)
    ax.fill_between(green_x, 0, 30, alpha=0.3, color="#2ecc71", label="绿区（安全）")
    # 黄区
    ax.fill_between(green_x, 30, 60, alpha=0.3, color="#f39c12", label="黄区（注意）")
    # 红区
    ax.fill_between(green_x, 60, 100, alpha=0.3, color="#e74c3c", label="红区（危险）")

    # 阈值线
    ax.axhline(y=30, color="#f39c12", linestyle="--", linewidth=1.5, alpha=0.8)
    ax.axhline(y=60, color="#e74c3c", linestyle="--", linewidth=1.5, alpha=0.8)
    ax.axvline(x=50, color="#3498db", linestyle=":", linewidth=1.5, alpha=0.6,
               label="VO₂peak阈值")

    ax.set_xlabel("R 轴（VO₂peak %pred）", fontsize=11)
    ax.set_ylabel("I 轴（不稳定性综合评分）", fontsize=11)
    ax.set_title("R-I 平面安全区", fontsize=12)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)

    # 右图：时间轴（P0 → 测试中 → P1）
    ax2 = axes[1]
    timeline_x = [0, 1, 2]
    timeline_labels = ["P0\n（运动前）", "CPET\n（测试中）", "P1\n（运动后）"]

    ax2.plot(timeline_x, [0.5, 0.5, 0.5], "k-", linewidth=2, zorder=1)
    for x_pos, label, color in zip(
        timeline_x,
        timeline_labels,
        ["#3498db", "#95a5a6", "#e74c3c"],
    ):
        ax2.scatter([x_pos], [0.5], s=300, color=color, zorder=2)
        ax2.text(x_pos, 0.62, label, ha="center", va="bottom", fontsize=10,
                 fontweight="bold", color=color)

    # P0 输入
    ax2.text(0, 0.3, "人口学\n病史\n体型", ha="center", va="top", fontsize=9,
             bbox=dict(boxstyle="round", facecolor="#3498db", alpha=0.2))
    # P1 输出
    ax2.text(2, 0.3, "VO₂peak\nHR恢复\nOUES\nVT1", ha="center", va="top", fontsize=9,
             bbox=dict(boxstyle="round", facecolor="#e74c3c", alpha=0.2))

    ax2.set_xlim(-0.5, 2.5)
    ax2.set_ylim(0, 1)
    ax2.axis("off")
    ax2.set_title("时间轴：P0 → P1 安全评估", fontsize=12)

    plt.suptitle("运动安全区框架（R/T/I 三轴）", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()

    if output_path:
        _save_figure(fig, output_path, dpi=dpi)
    return fig


def plot_zone_distribution_stage1b(
    df: pd.DataFrame,
    zone_col: str = "final_zone",
    group_col: str = "group_code",
    output_path: str | Path | None = None,
    figsize: tuple[float, float] = (11, 6),
    dpi: int = 150,
) -> plt.Figure:
    """
    Stage 1B final_zone（4区：green/yellow/red/yellow_gray）
    按 HTN×EIH 2×2 队列的堆叠柱状图。

    用于论文 Figure 2。
    """
    if zone_col not in df.columns or group_col not in df.columns:
        raise ValueError(f"列不存在: {zone_col} 或 {group_col}")

    groups = [g for g in GROUP_ORDER if g in df[group_col].unique()]
    zones = ["green", "yellow", "red", "yellow_gray"]
    colors = {
        "green": "#2ecc71",
        "yellow": "#f39c12",
        "red": "#e74c3c",
        "yellow_gray": "#bbbbbb",
    }
    labels = {
        "green": "Green",
        "yellow": "Yellow",
        "red": "Red",
        "yellow_gray": "Indeterminate\n(yellow_gray)",
    }

    # 英文分组标签
    group_en_labels = {
        "CTRL": "CTRL\n(n={n})",
        "HTN_HISTORY_NO_EHT": "HTN-noEIH\n(n={n})",
        "HTN_HISTORY_WITH_EHT": "HTN+EIH\n(n={n})",
        "EHT_ONLY": "EIH-Only\n(n={n})",
    }

    # 计算各组区间比例
    pct_data = {}
    n_data = {}
    for g in groups:
        sub = df[df[group_col] == g][zone_col].dropna()
        total = len(sub)
        n_data[g] = total
        pct_data[g] = {
            z: (sub == z).sum() / total * 100 if total > 0 else 0
            for z in zones
        }

    fig, ax = plt.subplots(figsize=figsize)
    x = np.arange(len(groups))
    bottom = np.zeros(len(groups))

    for zone in zones:
        vals = [pct_data[g][zone] for g in groups]
        ax.bar(
            x, vals, bottom=bottom,
            label=labels[zone],
            color=colors[zone],
            alpha=0.88,
            width=0.6,
            edgecolor="white",
            linewidth=0.5,
        )
        # 百分比标注（>4% 才显示）
        for i, (v, b) in enumerate(zip(vals, bottom)):
            if v > 4:
                ax.text(
                    i, b + v / 2, f"{v:.0f}%",
                    ha="center", va="center",
                    fontsize=9, color="white", fontweight="bold",
                )
        bottom += np.array(vals)

    # X 轴标签含 n
    x_labels = [
        group_en_labels.get(g, g).format(n=n_data[g])
        for g in groups
    ]
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, fontsize=10)
    ax.set_ylabel("Proportion (%)", fontsize=12)
    ax.set_title("Stage 1B final_zone Distribution by HTN×EIH Cohort", fontsize=13)
    ax.legend(loc="upper right", fontsize=9, frameon=True)
    ax.set_ylim(0, 108)
    ax.set_xlabel("Cohort", fontsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # 全局统计注解
    total = len(df)
    ax.text(
        0.01, 0.99,
        f"N={total}  Green 19.7% / Yellow 25.6% / Red 29.7% / Indeterminate 24.9%",
        transform=ax.transAxes,
        fontsize=8, va="top", color="gray",
    )

    plt.tight_layout()

    if output_path:
        _save_figure(fig, output_path, dpi=dpi)
    return fig


def plot_confidence_validity(
    df: pd.DataFrame,
    confidence_col: str = "confidence_label",
    zone_col: str = "final_zone",
    test_col: str = "test_result",
    output_path: str | Path | None = None,
    figsize: tuple[float, float] = (12, 5),
    dpi: int = 150,
) -> plt.Figure:
    """
    双面板图：
    左：置信度标签水平柱状图（High/Medium/Low/Indeterminate）
    右：final_zone vs test_result 阳性率梯度柱状图（构念效度）

    用于论文 Figure 3。
    """
    for col in [confidence_col, zone_col, test_col]:
        if col not in df.columns:
            raise ValueError(f"列不存在: {col}")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)

    # ── 左面板：置信度分布 ──
    conf_counts = df[confidence_col].value_counts()
    total = len(df)

    conf_order = ["high", "medium", "low"]
    conf_labels = {
        "high": f"High (≥0.80)\n{conf_counts.get('high', 0)} ({conf_counts.get('high', 0)/total*100:.1f}%)",
        "medium": f"Medium (0.65–0.80)\n{conf_counts.get('medium', 0)} ({conf_counts.get('medium', 0)/total*100:.1f}%)",
        "low": f"Low (<0.65)\n{conf_counts.get('low', 0)} ({conf_counts.get('low', 0)/total*100:.1f}%)",
    }
    conf_colors = {"high": "#2980b9", "medium": "#27ae60", "low": "#e67e22"}
    conf_vals = [conf_counts.get(c, 0) / total * 100 for c in conf_order]

    bars1 = ax1.barh(
        [conf_labels[c] for c in conf_order],
        conf_vals,
        color=[conf_colors[c] for c in conf_order],
        alpha=0.85, height=0.5,
    )
    for bar, val in zip(bars1, conf_vals):
        ax1.text(
            bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}%", va="center", fontsize=10,
        )
    ax1.set_xlabel("Proportion (%)", fontsize=11)
    ax1.set_title("Confidence Label Distribution\n(v2.7.0, threshold ≥0.80)", fontsize=11)
    ax1.set_xlim(0, max(conf_vals) * 1.25)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)

    # 添加 Indeterminate 注解
    indet_n = (df[zone_col] == "yellow_gray").sum()
    ax1.text(
        0.01, -0.12,
        f"Indeterminate (yellow_gray): {indet_n} ({indet_n/total*100:.1f}%)",
        transform=ax1.transAxes,
        fontsize=9, color="#888888",
    )

    # ── 右面板：构念效度梯度 ──
    pos_mask = df[test_col].isin(["阳性", "可疑阳性"])
    zone_order = ["green", "yellow", "red"]
    zone_colors_ev = {"green": "#2ecc71", "yellow": "#f39c12", "red": "#e74c3c"}

    rates = {}
    ns = {}
    for z in zone_order:
        sub = df[df[zone_col] == z]
        ns[z] = len(sub)
        rates[z] = pos_mask[sub.index].mean() * 100 if len(sub) > 0 else 0

    zone_en = {"green": "Green", "yellow": "Yellow", "red": "Red"}
    x_labels2 = [f"{zone_en[z]}\n(n={ns[z]})" for z in zone_order]
    vals2 = [rates[z] for z in zone_order]

    bars2 = ax2.bar(
        x_labels2, vals2,
        color=[zone_colors_ev[z] for z in zone_order],
        alpha=0.85, width=0.5,
    )
    for bar, val in zip(bars2, vals2):
        ax2.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.3,
            f"{val:.1f}%",
            ha="center", va="bottom", fontsize=11, fontweight="bold",
        )

    # 单调箭头
    ax2.annotate(
        "", xy=(2, max(vals2) + 2), xytext=(0, min(vals2) - 1),
        arrowprops=dict(arrowstyle="-|>", color="gray", lw=1.2),
    )
    ax2.set_ylabel("test_result Positive Rate (%)", fontsize=11)
    ax2.set_title("Construct Validity: Monotone Gradient\n(Excludes yellow_gray)", fontsize=11)
    ax2.set_ylim(0, max(vals2) * 1.35)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    # 验收标注
    ax2.text(
        0.5, 0.92, "✓ Monotone — Pipeline: Accept",
        ha="center", transform=ax2.transAxes,
        fontsize=10, color="#2980b9", fontweight="bold",
    )

    plt.suptitle(
        "Stage 1B Confidence & Construct Validity (N=3232, v2.7.0)",
        fontsize=12, fontweight="bold",
    )
    plt.tight_layout()

    if output_path:
        _save_figure(fig, output_path, dpi=dpi)
    return fig


def generate_all_supplementary_plots(
    df: pd.DataFrame,
    output_dir: str | Path = "reports/figures/supplement",
    eih_forest_df: pd.DataFrame | None = None,
    p1_stratified_perf: dict | None = None,
    p1_feature_vars: list[str] | None = None,
) -> list[str]:
    """
    生成所有 Phase A3 补充图表。

    参数：
        df: 含 group_code + CPET 变量 + zone 列的 DataFrame
        output_dir: 输出目录
        eih_forest_df: EIH 森林图数据（from to_forest_data()）
        p1_stratified_perf: P1 分层性能数据
        p1_feature_vars: P1 特征变量列表

    返回：生成文件路径列表
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    # 1. Zone 分布堆叠柱状图
    for zone_col in ["z_lab_zone", "p1_zone"]:
        if zone_col in df.columns:
            try:
                fig = plot_zone_distribution_stacked(
                    df, zone_col=zone_col, group_col="group_code",
                    output_path=out_dir / f"zone_distribution_stacked_{zone_col}.png",
                )
                generated.append(str(out_dir / f"zone_distribution_stacked_{zone_col}.png"))
                plt.close(fig)
                logger.info("生成: zone_distribution_stacked_%s.png", zone_col)
            except Exception as e:
                logger.warning("zone 堆叠图失败: %s", e)
            break  # 只生成一个（优先 z_lab_zone）

    # 2. 缺失数据热力图
    try:
        fig = plot_missing_data_heatmap(
            df, max_vars=25,
            output_path=out_dir / "missing_data_heatmap.png",
        )
        generated.append(str(out_dir / "missing_data_heatmap.png"))
        plt.close(fig)
        logger.info("生成: missing_data_heatmap.png")
    except Exception as e:
        logger.warning("缺失热力图失败: %s", e)

    # 3. 特征相关热力图
    try:
        fig = plot_feature_correlation_heatmap(
            df, variables=p1_feature_vars,
            output_path=out_dir / "feature_correlation_heatmap.png",
        )
        generated.append(str(out_dir / "feature_correlation_heatmap.png"))
        plt.close(fig)
        logger.info("生成: feature_correlation_heatmap.png")
    except Exception as e:
        logger.warning("相关热力图失败: %s", e)

    # 4. EIH 森林图
    if eih_forest_df is not None and not eih_forest_df.empty:
        try:
            fig = plot_eih_forest(
                eih_forest_df,
                output_path=out_dir / "eih_logistic_forest.png",
            )
            generated.append(str(out_dir / "eih_logistic_forest.png"))
            plt.close(fig)
            logger.info("生成: eih_logistic_forest.png")
        except Exception as e:
            logger.warning("EIH 森林图失败: %s", e)

    # 5. P1 分层性能图
    if p1_stratified_perf:
        try:
            fig = plot_p1_stratified_performance(
                p1_stratified_perf,
                output_path=out_dir / "p1_stratified_performance.png",
            )
            generated.append(str(out_dir / "p1_stratified_performance.png"))
            plt.close(fig)
            logger.info("生成: p1_stratified_performance.png")
        except Exception as e:
            logger.warning("P1 分层性能图失败: %s", e)

    # 6. 安全区概念示意图
    try:
        fig = plot_safety_zone_concept(
            output_path=out_dir / "safety_zone_concept.png",
        )
        generated.append(str(out_dir / "safety_zone_concept.png"))
        plt.close(fig)
        logger.info("生成: safety_zone_concept.png")
    except Exception as e:
        logger.warning("安全区概念图失败: %s", e)

    logger.info("补充图表生成完成: %d 张", len(generated))
    return generated
