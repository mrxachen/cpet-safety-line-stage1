"""
reference_quantiles.py — Stage 1B 条件分位参考模型。

职责：
1. 在 reference subset 上拟合每个核心变量的 q10/q25/q50/q75/q90
2. 对全样本预测条件分位（作为 burden 判定基准）
3. 保存/加载模型 bundle（joblib）
4. 生成参考分位报告

适配说明：
    模板来源：docs/guide/cpet_stage1_method_package/code_templates/reference_quantiles.py
    在模板基础上增加：
    - 配置文件驱动（reference_spec_stage1b.yaml）
    - 单调性修正（确保 q10 ≤ q25 ≤ q50 ≤ q75 ≤ q90）
    - 报告生成
    - 与 cohort reference_subset 的接口
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import QuantileRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, SplineTransformer

logger = logging.getLogger(__name__)

DEFAULT_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)
_QUANTILE_COLS = ["q10", "q25", "q50", "q75", "q90"]


@dataclass
class QuantileModelBundle:
    """单变量条件分位模型集合。"""
    variable: str
    quantiles: tuple[float, ...]
    models: dict[float, Pipeline]
    feature_columns: list[str]
    numeric_columns: list[str]
    categorical_columns: list[str]
    n_reference: int = 0
    reference_version: str = "stage1b"

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """为输入数据预测所有分位，并强制单调排列。"""
        out = pd.DataFrame(index=df.index)
        X = df[self.feature_columns].copy()
        raw_cols: list[str] = []

        for q, model in sorted(self.models.items()):
            col = f"{self.variable}_q{int(q * 100):02d}"
            out[col] = model.predict(X)
            raw_cols.append(col)

        # 强制单调：逐行排序后重写
        if len(raw_cols) > 1:
            sorted_vals = np.sort(out[raw_cols].values, axis=1)
            for idx, col in enumerate(raw_cols):
                out[col] = sorted_vals[:, idx]

        return out


@dataclass
class QuantileBundleSet:
    """多变量分位 bundle 集合。"""
    bundles: dict[str, QuantileModelBundle] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """对所有变量批量预测分位。"""
        parts: list[pd.DataFrame] = []
        for bundle in self.bundles.values():
            parts.append(bundle.predict(df))
        if not parts:
            return pd.DataFrame(index=df.index)
        return pd.concat(parts, axis=1)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("Saved QuantileBundleSet to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "QuantileBundleSet":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Bundle set not found: {path}")
        obj = joblib.load(path)
        logger.info("Loaded QuantileBundleSet from %s", path)
        return obj


def _make_preprocessor(
    numeric_columns: list[str],
    categorical_columns: list[str],
    age_spline_knots: int = 5,
) -> ColumnTransformer:
    """构造预处理器：age 样条 + 数值补缺 + 类别 OHE。"""
    transformers = []

    if "age" in numeric_columns:
        age_pipe = Pipeline(steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("spline", SplineTransformer(
                n_knots=age_spline_knots, degree=3, include_bias=False
            )),
        ])
        transformers.append(("age_spline", age_pipe, ["age"]))
        other_numeric = [c for c in numeric_columns if c != "age"]
    else:
        other_numeric = list(numeric_columns)

    if other_numeric:
        num_pipe = Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))])
        transformers.append(("num", num_pipe, other_numeric))

    if categorical_columns:
        cat_pipe = Pipeline(steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ])
        transformers.append(("cat", cat_pipe, categorical_columns))

    return ColumnTransformer(transformers=transformers, remainder="drop")


def fit_quantile_bundle(
    df_reference: pd.DataFrame,
    variable: str,
    *,
    numeric_columns: Iterable[str] = ("age", "bmi"),
    categorical_columns: Iterable[str] = ("sex", "protocol_mode"),
    quantiles: Iterable[float] = DEFAULT_QUANTILES,
    alpha: float = 0.001,
    age_spline_knots: int = 5,
    min_reference_n: int = 100,
) -> QuantileModelBundle:
    """
    在 reference subset 上拟合某一变量的条件分位模型。

    Parameters
    ----------
    df_reference : 参考子集（应已过滤为 reference_flag_strict 或 wide）
    variable : 目标变量名
    numeric_columns : 数值协变量
    categorical_columns : 类别协变量
    quantiles : 需要拟合的分位（默认 0.10/0.25/0.50/0.75/0.90）
    alpha : L1 惩罚（正则化稳定性）
    age_spline_knots : age 样条结点数
    min_reference_n : 参考子集最小样本量要求
    """
    numeric_columns = [c for c in numeric_columns if c in df_reference.columns]
    categorical_columns = [c for c in categorical_columns if c in df_reference.columns]
    feature_columns = numeric_columns + categorical_columns

    if variable not in df_reference.columns:
        raise KeyError(f"{variable!r} not found in reference dataframe (columns: {list(df_reference.columns)[:10]})")

    work = df_reference.dropna(subset=[variable]).copy()
    if len(work) < min_reference_n:
        raise ValueError(
            f"Reference subset too small for {variable!r}: n={len(work)} < min={min_reference_n}. "
            "Consider widening reference criteria."
        )

    X = work[feature_columns]
    y = pd.to_numeric(work[variable], errors="coerce")
    valid = y.notna()
    X = X.loc[valid]
    y = y.loc[valid]

    preprocessor = _make_preprocessor(
        numeric_columns, categorical_columns, age_spline_knots=age_spline_knots
    )
    models: dict[float, Pipeline] = {}

    for q in sorted(quantiles):
        pipe = Pipeline(steps=[
            ("preprocessor", preprocessor),
            ("model", QuantileRegressor(quantile=float(q), alpha=alpha, solver="highs")),
        ])
        pipe.fit(X, y)
        models[float(q)] = pipe

    return QuantileModelBundle(
        variable=variable,
        quantiles=tuple(sorted(float(q) for q in quantiles)),
        models=models,
        feature_columns=feature_columns,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        n_reference=len(y),
    )


def fit_bundle_set(
    df_reference: pd.DataFrame,
    variables: list[str],
    *,
    numeric_columns: Iterable[str] = ("age", "bmi"),
    categorical_columns: Iterable[str] = ("sex", "protocol_mode"),
    quantiles: Iterable[float] = DEFAULT_QUANTILES,
    alpha: float = 0.001,
    age_spline_knots: int = 5,
    min_reference_n: int = 100,
    skip_missing: bool = True,
) -> QuantileBundleSet:
    """
    对多个变量批量拟合 bundle set。

    skip_missing=True 时，若变量在 df_reference 中不存在则跳过并记录警告，
    而不是抛出异常。
    """
    bundles: dict[str, QuantileModelBundle] = {}

    for var in variables:
        if var not in df_reference.columns:
            if skip_missing:
                logger.warning("Variable %r not in reference df, skipping", var)
                continue
            raise KeyError(f"{var!r} not found in reference dataframe")

        n_valid = df_reference[var].notna().sum()
        if n_valid < min_reference_n:
            logger.warning(
                "Variable %r has only %d non-null values in reference (< %d), skipping",
                var, n_valid, min_reference_n,
            )
            continue

        try:
            bundle = fit_quantile_bundle(
                df_reference,
                var,
                numeric_columns=numeric_columns,
                categorical_columns=categorical_columns,
                quantiles=quantiles,
                alpha=alpha,
                age_spline_knots=age_spline_knots,
                min_reference_n=min_reference_n,
            )
            bundles[var] = bundle
            logger.info("Fitted quantile bundle for %r (n=%d)", var, bundle.n_reference)
        except Exception as exc:
            logger.warning("Failed to fit %r: %s", var, exc)

    bset = QuantileBundleSet(
        bundles=bundles,
        metadata={
            "n_variables": len(bundles),
            "n_reference": len(df_reference),
            "variables": list(bundles.keys()),
            "quantiles": sorted(float(q) for q in quantiles),
        },
    )
    return bset


def load_reference_spec(spec_path: str | Path) -> dict:
    """加载 reference_spec_stage1b.yaml。"""
    path = Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(f"Reference spec not found: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_reference_subset_stage1b(
    df: pd.DataFrame,
    spec: dict,
) -> pd.DataFrame:
    """
    根据 reference_spec_stage1b 中的规则过滤参考子集。
    返回含 reference_flag_wide / reference_flag_strict 列的 df。
    """
    df = df.copy()
    wide_cfg = spec.get("reference_subset", {}).get("wide", {})
    strict_cfg = spec.get("reference_subset", {}).get("strict", {})

    wide_mask = pd.Series(True, index=df.index)

    # 组别限制
    if "allowed_groups" in wide_cfg:
        if "group_code" in df.columns:
            wide_mask &= df["group_code"].isin(wide_cfg["allowed_groups"])

    # test_result 限制
    if "exclude_test_result" in wide_cfg:
        excl = wide_cfg["exclude_test_result"]
        if "test_result" in df.columns:
            wide_mask &= ~df["test_result"].isin(excl)

    # VO2peak 下界
    if "vo2_peak_pct_pred_min" in wide_cfg:
        if "vo2_peak_pct_pred" in df.columns:
            wide_mask &= (
                df["vo2_peak_pct_pred"].isna() |
                (pd.to_numeric(df["vo2_peak_pct_pred"], errors="coerce") >= wide_cfg["vo2_peak_pct_pred_min"])
            )

    # VE/VCO2 slope 上界
    if "ve_vco2_slope_max" in wide_cfg:
        if "ve_vco2_slope" in df.columns:
            wide_mask &= (
                df["ve_vco2_slope"].isna() |
                (pd.to_numeric(df["ve_vco2_slope"], errors="coerce") <= wide_cfg["ve_vco2_slope_max"])
            )

    # eih_status
    if wide_cfg.get("exclude_eih", False):
        if "eih_status" in df.columns:
            wide_mask &= ~(df["eih_status"].astype(str).str.lower().isin(["true", "1"]))

    # bp_peak_sys 上界
    if "bp_peak_sys_max" in wide_cfg:
        if "bp_peak_sys" in df.columns:
            wide_mask &= (
                df["bp_peak_sys"].isna() |
                (pd.to_numeric(df["bp_peak_sys"], errors="coerce") <= wide_cfg["bp_peak_sys_max"])
            )

    # 年龄范围
    if "age_range" in wide_cfg:
        lo, hi = wide_cfg["age_range"]
        if "age" in df.columns:
            age_num = pd.to_numeric(df["age"], errors="coerce")
            wide_mask &= (age_num >= lo) & (age_num <= hi)

    df["reference_flag_wide"] = wide_mask.astype(bool)

    # strict：在 wide 基础上加 HR 代理努力度
    strict_mask = wide_mask.copy()
    if strict_cfg.get("hr_effort_proxy", False):
        if "hr_peak_pct_pred" in df.columns:
            hr_pct = pd.to_numeric(df["hr_peak_pct_pred"], errors="coerce")
            hr_ok = hr_pct >= strict_cfg.get("hr_peak_pct_pred_min", 85.0)
            strict_mask &= hr_ok.fillna(False)
        elif "hr_peak" in df.columns and "age" in df.columns:
            # 用 (220 - age) 代理
            age_num = pd.to_numeric(df["age"], errors="coerce")
            hr_num = pd.to_numeric(df["hr_peak"], errors="coerce")
            max_hr = 220.0 - age_num
            hr_pct = hr_num / max_hr * 100.0
            hr_ok = hr_pct >= strict_cfg.get("hr_peak_pct_pred_min", 85.0)
            strict_mask &= hr_ok.fillna(False)

    df["reference_flag_strict"] = strict_mask.astype(bool)

    n_wide = df["reference_flag_wide"].sum()
    n_strict = df["reference_flag_strict"].sum()
    logger.info(
        "Reference subset: wide=%d (%.1f%%), strict=%d (%.1f%%)",
        n_wide, 100 * n_wide / len(df),
        n_strict, 100 * n_strict / len(df),
    )

    return df


def generate_reference_quantiles_report(
    bundle_set: QuantileBundleSet,
    df_full: pd.DataFrame,
    *,
    reference_mask: pd.Series,
    output_path: str | Path | None = None,
) -> str:
    """生成参考分位报告（Markdown）。"""
    lines: list[str] = [
        "# Reference Quantiles Report (Stage 1B)\n",
        f"- 参考子集样本量：{reference_mask.sum()}",
        f"- 全量样本数：{len(df_full)}",
        f"- 已拟合变量：{len(bundle_set.bundles)}\n",
    ]

    lines.append("## 各变量参考分位统计（reference subset 上的实际分位）\n")
    lines.append("| 变量 | N | q10 | q25 | q50 | q75 | q90 |")
    lines.append("|---|---|---|---|---|---|---|")

    for var, bundle in bundle_set.bundles.items():
        if var not in df_full.columns:
            continue
        ref_vals = pd.to_numeric(df_full.loc[reference_mask, var], errors="coerce").dropna()
        if len(ref_vals) < 5:
            continue
        q10, q25, q50, q75, q90 = np.percentile(ref_vals, [10, 25, 50, 75, 90])
        lines.append(
            f"| {var} | {len(ref_vals)} "
            f"| {q10:.2f} | {q25:.2f} | {q50:.2f} | {q75:.2f} | {q90:.2f} |"
        )

    lines.append("\n## 模型单调性验证（全量预测）\n")
    preds = bundle_set.predict(df_full)

    lines.append("| 变量 | 单调违反行数 |")
    lines.append("|---|---|")

    for var in bundle_set.bundles:
        q_cols = [f"{var}_q{p}" for p in [10, 25, 50, 75, 90] if f"{var}_q{p}" in preds.columns]
        if len(q_cols) < 2:
            continue
        sub = preds[q_cols].dropna()
        violations = int((np.diff(sub.values, axis=1) < 0).any(axis=1).sum())
        lines.append(f"| {var} | {violations} |")

    lines.append("\n## 数据覆盖率（全量 non-null%）\n")
    lines.append("| 变量 | 全量非空% | 参考子集非空% |")
    lines.append("|---|---|---|")

    for var in bundle_set.bundles:
        if var not in df_full.columns:
            continue
        full_pct = 100 * df_full[var].notna().mean()
        ref_pct = 100 * df_full.loc[reference_mask, var].notna().mean()
        lines.append(f"| {var} | {full_pct:.1f}% | {ref_pct:.1f}% |")

    report = "\n".join(lines)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report, encoding="utf-8")
        logger.info("Reference quantiles report saved to %s", output_path)

    return report
