"""
reference_quantiles.py
---------------------------------
Stage I-B 条件分位参考模型模板。

用途：
1. 在 reference subset 上拟合每个核心变量的 q10/q25/q50/q75/q90
2. 对全样本预测条件分位
3. 供 phenotype_engine 计算 burden

依赖：
- pandas
- numpy
- scikit-learn

注意：
- 这是模板，不是你仓库现成 API 的一比一替代品
- 真实集成时请接入你项目现有的路径管理、日志和 CLI
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import QuantileRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, SplineTransformer


DEFAULT_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)


@dataclass
class QuantileModelBundle:
    variable: str
    quantiles: tuple[float, ...]
    models: dict[float, Pipeline]
    feature_columns: list[str]
    numeric_columns: list[str]
    categorical_columns: list[str]

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """为输入数据预测所有分位。"""
        out = pd.DataFrame(index=df.index)
        X = df[self.feature_columns].copy()
        for q, model in self.models.items():
            out[f"{self.variable}_q{int(q * 100):02d}"] = model.predict(X)
        return out


def _make_preprocessor(
    numeric_columns: list[str],
    categorical_columns: list[str],
) -> ColumnTransformer:
    """构造 age spline + 数值补缺 + 类别编码 的预处理器。"""
    transformers = []

    if "age" in numeric_columns:
        age_pipe = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("spline", SplineTransformer(n_knots=5, degree=3, include_bias=False)),
            ]
        )
        transformers.append(("age", age_pipe, ["age"]))
        other_numeric = [c for c in numeric_columns if c != "age"]
    else:
        other_numeric = list(numeric_columns)

    if other_numeric:
        num_pipe = Pipeline(
            steps=[("imputer", SimpleImputer(strategy="median"))]
        )
        transformers.append(("num", num_pipe, other_numeric))

    if categorical_columns:
        cat_pipe = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]
        )
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
) -> QuantileModelBundle:
    """
    在 reference subset 上拟合某一变量的条件分位模型。

    Parameters
    ----------
    df_reference : pd.DataFrame
        参考子集
    variable : str
        目标变量
    numeric_columns : Iterable[str]
        数值协变量
    categorical_columns : Iterable[str]
        类别协变量
    quantiles : Iterable[float]
        需要拟合的分位
    alpha : float
        L1 惩罚参数。适度正则可提升稳定性
    """
    numeric_columns = [c for c in numeric_columns if c in df_reference.columns]
    categorical_columns = [c for c in categorical_columns if c in df_reference.columns]
    feature_columns = numeric_columns + categorical_columns

    if variable not in df_reference.columns:
        raise KeyError(f"{variable!r} not found in reference dataframe")

    work = df_reference.dropna(subset=[variable]).copy()
    if len(work) < 100:
        raise ValueError(
            f"Reference subset too small for {variable!r}: n={len(work)}. "
            "Consider widening reference criteria."
        )

    X = work[feature_columns]
    y = pd.to_numeric(work[variable], errors="coerce")
    valid = y.notna()
    X = X.loc[valid]
    y = y.loc[valid]

    preprocessor = _make_preprocessor(numeric_columns, categorical_columns)
    models: dict[float, Pipeline] = {}

    for q in quantiles:
        pipe = Pipeline(
            steps=[
                ("preprocessor", preprocessor),
                ("model", QuantileRegressor(quantile=q, alpha=alpha, solver="highs")),
            ]
        )
        pipe.fit(X, y)
        models[float(q)] = pipe

    return QuantileModelBundle(
        variable=variable,
        quantiles=tuple(float(q) for q in quantiles),
        models=models,
        feature_columns=feature_columns,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
    )


def predict_quantiles_for_variables(
    df: pd.DataFrame,
    bundles: dict[str, QuantileModelBundle],
) -> pd.DataFrame:
    """对多个变量一起预测条件分位。"""
    parts = []
    for variable, bundle in bundles.items():
        _ = variable  # 保留变量名供未来日志扩展
        parts.append(bundle.predict(df))
    if not parts:
        return pd.DataFrame(index=df.index)
    return pd.concat(parts, axis=1)


if __name__ == "__main__":
    # 示例：真实项目中请改成 CLI 入口
    print("This module is a template. Import and integrate into your project CLI.")
