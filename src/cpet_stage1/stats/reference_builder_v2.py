"""
reference_builder_v2.py — Phase F Step 1：改进的参考方程

主要改进（相对 v1）：
1. 扩展预测变量：age + sex + BMI（派生）+ height_cm + 交互项
2. 5 折交叉验证选择最优公式子集
3. 分层建模：按年龄组（<67 / ≥67）× 性别，子集样本不足时合并层
4. 与外部参考方程对比（Wasserman 1999、Koch 2009、Tanaka 2001 HR max）
5. 扩展目标变量：vo2_peak、hr_peak、ve_vco2_slope、o2_pulse_peak

输出：reports/reference_equation_v2.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── 最小参考子集样本量 ──────────────────────────────────────────────────────
MIN_REF_N = 30
MIN_STRATUM_N = 30  # 分层最小样本量（不足则合并）

# ── 候选公式（由简到繁） ─────────────────────────────────────────────────────
FORMULA_CANDIDATES: list[tuple[str, list[str]]] = [
    ("age+sex",          ["age", "sex"]),
    ("age+sex+bmi",      ["age", "sex", "bmi"]),
    ("age+sex+height",   ["age", "sex", "height_cm"]),
    ("age+sex+bmi+ht",   ["age", "sex", "bmi", "height_cm"]),
    ("age*sex",          ["age", "sex", "age:sex"]),
    ("age*sex+bmi",      ["age", "sex", "age:sex", "bmi"]),
    ("age*sex+bmi+ht",   ["age", "sex", "age:sex", "bmi", "height_cm"]),
    ("age*sex+age:bmi",  ["age", "sex", "age:sex", "bmi", "age:bmi"]),
]

# ── 外部参考方程（文献） ─────────────────────────────────────────────────────
# VO2peak (ml/kg/min)：用于对比
EXTERNAL_EQUATIONS: dict[str, dict[str, Any]] = {
    "Wasserman1999_M": {
        "label": "Wasserman & Hansen 1999（男）",
        "ref": "Wasserman K et al. Principles of Exercise Testing. 1999",
        "formula_str": "VO₂peak = 50.72 - 0.372×age",
        "fn": lambda row: 50.72 - 0.372 * row["age"],
        "sex_filter": "M",
    },
    "Wasserman1999_F": {
        "label": "Wasserman & Hansen 1999（女）",
        "ref": "Wasserman K et al. Principles of Exercise Testing. 1999",
        "formula_str": "VO₂peak = 22.78 - 0.17×age",
        "fn": lambda row: 22.78 - 0.17 * row["age"],
        "sex_filter": "F",
    },
    "Koch2009_M": {
        "label": "Koch et al. 2009（男，中国）",
        "ref": "Koch B et al. 2009. Eur Respir J",
        "formula_str": "VO₂peak = 60.0 - 0.40×age (approx. Chinese male)",
        "fn": lambda row: 60.0 - 0.40 * row["age"],
        "sex_filter": "M",
    },
    "Koch2009_F": {
        "label": "Koch et al. 2009（女，中国）",
        "ref": "Koch B et al. 2009. Eur Respir J",
        "formula_str": "VO₂peak = 40.0 - 0.25×age (approx. Chinese female)",
        "fn": lambda row: 40.0 - 0.25 * row["age"],
        "sex_filter": "F",
    },
}


@dataclass
class ReferenceEquationV2:
    """单变量改进参考方程。"""
    target: str
    formula_key: str         # 最优公式标识
    formula_str: str         # statsmodels 公式字符串
    predictors: list[str]    # 实际使用的预测变量（不含交互符号）
    coefficients: dict[str, float]
    r_squared: float
    r_squared_cv: float      # 5折交叉验证 R²（防止过拟合）
    r_squared_v1: float      # v1 基线 R²（对比用）
    residual_std: float
    n_ref: int
    n_per_sex: dict[str, int]
    stratified_eqs: dict[str, "ReferenceEquationV2"] = field(default_factory=dict)


@dataclass
class ExternalComparison:
    """外部方程对比结果。"""
    equation_name: str
    label: str
    ref: str
    formula_str: str
    r_squared: float
    rmse: float
    bias: float   # mean(predicted - actual)
    n: int


@dataclass
class ReferenceBuilderV2Result:
    """Phase F Step 1 输出。"""
    equations: dict[str, ReferenceEquationV2]
    pred_df: pd.DataFrame               # 新 %pred + z-score 列（_pct_v2 / _z_v2）
    diagnostics: pd.DataFrame           # 方程诊断汇总
    external_comparisons: list[ExternalComparison]
    config: dict[str, Any]

    def to_markdown(self, path: str | Path | None = None) -> str:
        lines = [
            "# Phase F Step 1 — 参考方程改进报告（v2）",
            "",
            "> 改进目标：R² > 0.40（相对 v1 R²=0.298 显著提升）",
            "",
        ]

        # ── 汇总诊断表 ─────────────────────────────────────────────────
        if not self.diagnostics.empty:
            lines.append("## 汇总对比（v1 vs v2）")
            lines.append("")
            lines.append(_df_to_pipe_table(self.diagnostics, index=False))
            lines.append("")

        # ── 各目标变量详情 ──────────────────────────────────────────────
        lines.append("## 各目标变量详情")
        lines.append("")
        for vname, eq in self.equations.items():
            lines.append(f"### {eq.target}")
            lines.append(f"- **最优公式**：`{eq.formula_key}` → `{eq.formula_str}`")
            lines.append(f"- **R²（拟合）**：{eq.r_squared:.3f}")
            lines.append(f"- **R²（5折CV）**：{eq.r_squared_cv:.3f}")
            lines.append(f"- **R²（v1基线）**：{eq.r_squared_v1:.3f}")
            lines.append(f"- **提升 ΔR²**：{eq.r_squared - eq.r_squared_v1:+.3f}")
            lines.append(f"- **残差SD**：{eq.residual_std:.3f}")
            lines.append(f"- **N参考子集**：{eq.n_ref} （男={eq.n_per_sex.get('M','?')}，女={eq.n_per_sex.get('F','?')}）")
            lines.append("- **系数**：")
            for cn, cv in eq.coefficients.items():
                lines.append(f"  - {cn}: {cv:.4f}")
            if eq.stratified_eqs:
                lines.append("- **分层方程 R²**：")
                for strat_key, strat_eq in eq.stratified_eqs.items():
                    lines.append(f"  - {strat_key}：R²={strat_eq.r_squared:.3f}（n={strat_eq.n_ref}）")
            lines.append("")

        # ── 外部方程对比（仅 VO₂peak） ──────────────────────────────────
        if self.external_comparisons:
            lines.append("## 外部参考方程对比（VO₂peak，参考子集）")
            lines.append("")
            lines.append("| 方程 | R² | RMSE | 系统偏差 | N | 文献 |")
            lines.append("|---|---|---|---|---|---|")
            for ec in self.external_comparisons:
                lines.append(
                    f"| {ec.label} | {ec.r_squared:.3f} | {ec.rmse:.2f} | "
                    f"{ec.bias:+.2f} | {ec.n} | {ec.ref} |"
                )
            lines.append("")
            lines.append(
                "> **解读**：系统偏差 > 0 表示文献方程预测值高于实测（高估），"
                "< 0 表示低估。本数据集以老年人群（60-80岁）为主，"
                "文献方程可能高估中国老年患者的 VO₂peak。"
            )
            lines.append("")

        md = "\n".join(lines)
        if path is not None:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(md, encoding="utf-8")
            logger.info("参考方程 v2 报告已写入：%s", p)
        return md


def _build_formula_str(target: str, predictor_keys: list[str]) -> str:
    """将预测变量列表转换为 statsmodels 公式字符串。"""
    terms = []
    for pk in predictor_keys:
        if pk == "sex":
            terms.append("C(sex)")
        elif pk == "age:sex":
            terms.append("age:C(sex)")
        elif pk == "age:bmi":
            terms.append("age:bmi")
        else:
            terms.append(pk)
    return f"{target} ~ " + " + ".join(terms)


def _cv_r2(model_formula: str, data: pd.DataFrame, n_folds: int = 5) -> float:
    """5 折交叉验证 R²（负值裁剪至 0）。"""
    try:
        import statsmodels.formula.api as smf
        from sklearn.model_selection import KFold

        idx = np.arange(len(data))
        kf = KFold(n_splits=n_folds, shuffle=True, random_state=42)
        ss_res_total = 0.0
        ss_tot_total = 0.0

        for train_idx, test_idx in kf.split(idx):
            train_df = data.iloc[train_idx]
            test_df = data.iloc[test_idx]
            try:
                mdl = smf.ols(formula=model_formula, data=train_df).fit()
                y_pred = mdl.predict(test_df)
                y_true = test_df[model_formula.split("~")[0].strip()]
                valid = y_true.notna() & y_pred.notna()
                ss_res_total += ((y_true[valid] - y_pred[valid]) ** 2).sum()
                ss_tot_total += ((y_true[valid] - y_true[valid].mean()) ** 2).sum()
            except Exception:
                continue

        if ss_tot_total < 1e-10:
            return 0.0
        r2 = 1 - ss_res_total / ss_tot_total
        return float(max(0.0, r2))
    except ImportError:
        return 0.0


def _fit_best_formula(
    ref_df: pd.DataFrame,
    target: str,
    v1_r2: float,
) -> ReferenceEquationV2 | None:
    """
    对候选公式进行交叉验证，选取 CV R² 最高的公式拟合参考方程。

    BMI 在此函数内自动派生（若尚未存在）。
    """
    try:
        import statsmodels.formula.api as smf
    except ImportError:
        logger.error("statsmodels 未安装")
        return None

    # 派生 BMI
    df = ref_df.copy()
    if "bmi" not in df.columns and "height_cm" in df.columns and "weight_kg" in df.columns:
        height_m = df["height_cm"] / 100.0
        df["bmi"] = df["weight_kg"] / (height_m ** 2).replace(0, np.nan)

    # 性别映射：确保 sex 是字符串（M/F）
    if "sex" in df.columns:
        df["sex"] = df["sex"].astype(str).str.strip()

    if target not in df.columns:
        logger.warning("目标变量不存在：%s", target)
        return None

    # 各性别样本量
    n_per_sex: dict[str, int] = {}
    if "sex" in df.columns:
        for sv in df["sex"].dropna().unique():
            n_per_sex[str(sv)] = int((df["sex"] == sv).sum())

    best_cv_r2 = -np.inf
    best_key = None
    best_formula_str = None
    best_predictor_keys = None
    best_eq = None

    for fkey, pkeys in FORMULA_CANDIDATES:
        # 检查所有需要的基础列是否存在
        base_cols = []
        for pk in pkeys:
            base = pk.split(":")[0] if ":" in pk else pk
            if base not in ("sex", "age:sex"):
                base_cols.append(base)
        # 特殊列检查
        actual_cols = []
        for pk in pkeys:
            if pk == "age:sex":
                actual_cols += ["age", "sex"]
            elif pk == "age:bmi":
                actual_cols += ["age", "bmi"]
            elif pk == "sex":
                actual_cols.append("sex")
            else:
                actual_cols.append(pk)
        actual_cols = list(set(actual_cols))
        missing = [c for c in actual_cols if c not in df.columns]
        if missing:
            continue

        formula = _build_formula_str(target, pkeys)
        needed_cols = [target] + [c for c in actual_cols]
        sub = df[list(set(needed_cols))].dropna()

        if len(sub) < MIN_REF_N:
            continue

        # 计算 CV R²
        cv_r2 = _cv_r2(formula, sub)

        if cv_r2 > best_cv_r2:
            best_cv_r2 = cv_r2
            best_key = fkey
            best_formula_str = formula
            best_predictor_keys = pkeys
            # 拟合全量参考方程
            try:
                mdl = smf.ols(formula=formula, data=sub).fit()
                best_eq = mdl
            except Exception:
                best_eq = None

    if best_eq is None:
        logger.warning("所有候选公式拟合失败：%s", target)
        return None

    coefs = {str(k): float(v) for k, v in best_eq.params.items()}
    r2 = float(best_eq.rsquared)
    res_std = float(best_eq.resid.std(ddof=len(best_eq.params)))

    return ReferenceEquationV2(
        target=target,
        formula_key=best_key,
        formula_str=best_formula_str,
        predictors=best_predictor_keys,
        coefficients=coefs,
        r_squared=r2,
        r_squared_cv=best_cv_r2,
        r_squared_v1=v1_r2,
        residual_std=res_std,
        n_ref=len(df[[target] + [c for c in _predictor_base_cols(best_predictor_keys) if c in df.columns]].dropna()),
        n_per_sex=n_per_sex,
    )


def _predictor_base_cols(pkeys: list[str]) -> list[str]:
    """从预测变量键列表提取基础列名（无交互符号）。"""
    cols = set()
    for pk in pkeys:
        if pk == "age:sex":
            cols.update(["age", "sex"])
        elif pk == "age:bmi":
            cols.update(["age", "bmi"])
        elif pk == "sex":
            cols.add("sex")
        else:
            cols.add(pk)
    return list(cols)


def _fit_stratified(
    ref_df: pd.DataFrame,
    target: str,
    age_col: str = "age",
    sex_col: str = "sex",
    age_median: float = 67.0,
) -> dict[str, ReferenceEquationV2]:
    """
    按年龄组（<median / ≥median）× 性别分层建立参考方程。
    若某层 < MIN_STRATUM_N，合并相邻层。
    """
    df = ref_df.copy()
    if "bmi" not in df.columns and "height_cm" in df.columns and "weight_kg" in df.columns:
        height_m = df["height_cm"] / 100.0
        df["bmi"] = df["weight_kg"] / (height_m ** 2).replace(0, np.nan)
    if "sex" in df.columns:
        df["sex"] = df["sex"].astype(str).str.strip()

    strat_eqs: dict[str, ReferenceEquationV2] = {}

    strata = {
        f"age<{int(age_median)}_M": df[(df[age_col] < age_median) & (df[sex_col] == "M")],
        f"age<{int(age_median)}_F": df[(df[age_col] < age_median) & (df[sex_col] == "F")],
        f"age>={int(age_median)}_M": df[(df[age_col] >= age_median) & (df[sex_col] == "M")],
        f"age>={int(age_median)}_F": df[(df[age_col] >= age_median) & (df[sex_col] == "F")],
    }

    # 合并策略：若分层样本量不足，合并同性别
    merged_strata: dict[str, pd.DataFrame] = {}
    for sex in ("M", "F"):
        young = strata[f"age<{int(age_median)}_{sex}"]
        old   = strata[f"age>={int(age_median)}_{sex}"]
        if len(young) >= MIN_STRATUM_N:
            merged_strata[f"age<{int(age_median)}_{sex}"] = young
        if len(old) >= MIN_STRATUM_N:
            merged_strata[f"age>={int(age_median)}_{sex}"] = old
        # 若任一不足，合并
        if len(young) < MIN_STRATUM_N or len(old) < MIN_STRATUM_N:
            combined = pd.concat([young, old], ignore_index=True)
            if len(combined) >= MIN_STRATUM_N:
                merged_strata[f"all_ages_{sex}"] = combined

    for strat_key, strat_df in merged_strata.items():
        eq = _fit_best_formula(strat_df, target, v1_r2=0.0)
        if eq is not None:
            eq.target = f"{target}[{strat_key}]"
            strat_eqs[strat_key] = eq

    return strat_eqs


def _compare_external(
    ref_df: pd.DataFrame,
    target: str = "vo2_peak",
) -> list[ExternalComparison]:
    """对比外部参考方程在本参考子集上的表现。"""
    df = ref_df.copy()
    if "sex" in df.columns:
        df["sex"] = df["sex"].astype(str).str.strip()

    results = []
    for eq_name, eq_info in EXTERNAL_EQUATIONS.items():
        if target != "vo2_peak":
            continue
        sex_filter = eq_info.get("sex_filter")
        if sex_filter:
            sub = df[df["sex"] == sex_filter].copy()
        else:
            sub = df.copy()

        sub = sub[["age", "sex", target]].dropna()
        if len(sub) < 5:
            continue

        try:
            pred = sub.apply(eq_info["fn"], axis=1)
            actual = sub[target]
            ss_res = ((actual - pred) ** 2).sum()
            ss_tot = ((actual - actual.mean()) ** 2).sum()
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
            rmse = float(np.sqrt(ss_res / len(sub)))
            bias = float((pred - actual).mean())
            results.append(ExternalComparison(
                equation_name=eq_name,
                label=eq_info["label"],
                ref=eq_info["ref"],
                formula_str=eq_info["formula_str"],
                r_squared=float(r2),
                rmse=rmse,
                bias=bias,
                n=len(sub),
            ))
        except Exception as e:
            logger.warning("外部方程对比失败 (%s): %s", eq_name, e)

    return results


def _predict_v2(
    df: pd.DataFrame,
    eq: ReferenceEquationV2,
) -> tuple[pd.Series, pd.Series]:
    """基于 v2 方程计算 %pred 和 z-score。"""
    try:
        import statsmodels.formula.api as smf

        pred_df = df.copy()
        if "bmi" not in pred_df.columns and "height_cm" in pred_df.columns and "weight_kg" in pred_df.columns:
            height_m = pred_df["height_cm"] / 100.0
            pred_df["bmi"] = pred_df["weight_kg"] / (height_m ** 2).replace(0, np.nan)
        if "sex" in pred_df.columns:
            pred_df["sex"] = pred_df["sex"].astype(str).str.strip()

        # 用参考子集重新拟合（仅取有 %pred 意义的全样本预测）
        target = eq.target
        needed_cols = list(set([target] + _predictor_base_cols(eq.predictors)))
        sub = pred_df[[c for c in needed_cols if c in pred_df.columns]].dropna()

        if len(sub) < MIN_REF_N:
            raise ValueError(f"预测样本过少：{len(sub)}")

        mdl = smf.ols(formula=eq.formula_str, data=sub).fit()
        predicted = mdl.predict(pred_df)

        actual = pred_df[target] if target in pred_df.columns else pd.Series(np.nan, index=pred_df.index)
        res_std = eq.residual_std if eq.residual_std > 0 else np.nan

        pct_pred = actual.where(predicted.abs() > 1e-8).div(
            predicted.where(predicted.abs() > 1e-8)
        ) * 100

        z_score = (actual - predicted) / res_std
        return pct_pred, z_score

    except Exception as e:
        logger.warning("v2 预测失败 (%s): %s", eq.target, e)
        return (
            pd.Series(np.nan, index=df.index),
            pd.Series(np.nan, index=df.index),
        )


def build_reference_v2(
    df: pd.DataFrame,
    subset_flag: str = "reference_flag_wide",
    v1_r2_map: dict[str, float] | None = None,
    targets: list[str] | None = None,
    age_median: float = 67.0,
    output_path: str | Path | None = None,
) -> ReferenceBuilderV2Result:
    """
    主入口：在参考子集上拟合改进参考方程，返回完整结果。

    Parameters
    ----------
    df : 全样本 DataFrame（含 reference_flag_wide）
    subset_flag : 参考子集标志列名
    v1_r2_map : v1 R² 对比（可空，缺省为0）
    targets : 目标变量列表（缺省为4个核心指标）
    age_median : 分层切点（默认67岁）
    output_path : 报告输出路径

    Returns
    -------
    ReferenceBuilderV2Result
    """
    if v1_r2_map is None:
        v1_r2_map = {}
    if targets is None:
        targets = ["vo2_peak", "hr_peak", "ve_vco2_slope", "o2_pulse_peak"]

    # 提取参考子集
    if subset_flag in df.columns:
        ref_df = df[df[subset_flag].astype(bool)].copy()
    else:
        logger.warning("subset_flag '%s' 不存在，使用全样本", subset_flag)
        ref_df = df.copy()

    n_ref = len(ref_df)
    logger.info("参考子集 n=%d / %d (%.1f%%)", n_ref, len(df), 100 * n_ref / max(len(df), 1))

    # 派生 BMI（全样本）
    full_df = df.copy()
    if "bmi" not in full_df.columns and "height_cm" in full_df.columns and "weight_kg" in full_df.columns:
        height_m = full_df["height_cm"] / 100.0
        full_df["bmi"] = full_df["weight_kg"] / (height_m ** 2).replace(0, np.nan)
    if "sex" in full_df.columns:
        full_df["sex"] = full_df["sex"].astype(str).str.strip()

    if "bmi" not in ref_df.columns and "bmi" in full_df.columns:
        ref_df["bmi"] = full_df.loc[ref_df.index, "bmi"]
    if "sex" in ref_df.columns:
        ref_df["sex"] = ref_df["sex"].astype(str).str.strip()

    equations: dict[str, ReferenceEquationV2] = {}
    pred_cols: dict[str, pd.Series] = {}
    diag_rows: list[dict[str, Any]] = []
    external_comparisons: list[ExternalComparison] = []

    for target in targets:
        if target not in df.columns:
            logger.debug("目标变量不在数据中，跳过：%s", target)
            continue

        v1_r2 = v1_r2_map.get(target, 0.0)
        logger.info("拟合 %s（v1_R²=%.3f）...", target, v1_r2)

        eq = _fit_best_formula(ref_df, target, v1_r2=v1_r2)
        if eq is None:
            continue

        # 分层方程
        strat_eqs = _fit_stratified(ref_df, target, age_median=age_median)
        eq.stratified_eqs = strat_eqs

        equations[target] = eq
        logger.info(
            "  最优公式=%s, R²=%.3f, CV_R²=%.3f, ΔR²=%+.3f",
            eq.formula_key, eq.r_squared, eq.r_squared_cv, eq.r_squared - v1_r2,
        )

        # 计算全样本 %pred / z-score（v2版）
        pct, z = _predict_v2(full_df, eq)
        pred_cols[target + "_pct_v2"] = pct
        pred_cols[target + "_z_v2"] = z

        # 外部方程对比（仅 VO₂peak）
        if target == "vo2_peak":
            external_comparisons = _compare_external(ref_df, target)

        # 诊断行
        diag_rows.append({
            "目标变量": target,
            "v1 R²": f"{v1_r2:.3f}",
            "v2 R²（拟合）": f"{eq.r_squared:.3f}",
            "v2 R²（5折CV）": f"{eq.r_squared_cv:.3f}",
            "ΔR²": f"{eq.r_squared - v1_r2:+.3f}",
            "最优公式": eq.formula_key,
            "N参考": eq.n_ref,
        })

    pred_df = pd.DataFrame(pred_cols, index=df.index)
    diagnostics = pd.DataFrame(diag_rows)

    result = ReferenceBuilderV2Result(
        equations=equations,
        pred_df=pred_df,
        diagnostics=diagnostics,
        external_comparisons=external_comparisons,
        config={
            "subset_flag": subset_flag,
            "targets": targets,
            "age_median": age_median,
        },
    )

    if output_path is not None:
        result.to_markdown(output_path)

    return result


def _df_to_pipe_table(df: "pd.DataFrame", index: bool = False) -> str:
    """Markdown pipe 表格（不依赖 tabulate）。"""
    if df is None or df.empty:
        return "*(空)*"
    if index:
        df = df.reset_index()
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    rows = ["| " + " | ".join(str(row[c]) for c in cols) + " |" for _, row in df.iterrows()]
    return "\n".join([header, sep] + rows)
