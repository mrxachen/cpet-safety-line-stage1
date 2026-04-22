"""
logistic_eih.py — EIH 多因素 Logistic 回归分析模块。

目的：识别 EIH（运动性低氧血症）的独立预测因子。
候选预测因子：age, sex, vo2_peak, htn_history, bmi（派生）

提供：
- EIHLogisticAnalyzer.run(): 拟合单变量 + 多因素模型
- EIHLogisticResult: 包含 OR、95% CI、p 值表
- generate_eih_logistic_report(): 生成 Markdown 报告（含森林图数据）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

logger = logging.getLogger(__name__)

# 候选预测因子（运动前字段，无泄漏风险）
DEFAULT_PREDICTORS = [
    "age",
    "sex",         # 编码为 0/1（F=0, M=1）
    "vo2_peak",    # 注意：vo2_peak 是 CPET 结果；若仅用运动前字段，改用 bmi/htn_years
    "htn_history",
    "bmi",         # 派生字段（height_cm + weight_kg）
    "htn_years",   # 高血压病程（可选，完整度52.6%）
]

# 运动前专用预测因子（严格 P0 约束）
P0_ONLY_PREDICTORS = [
    "age",
    "sex",
    "htn_history",
    "bmi",
    "htn_years",
]


@dataclass
class ORResult:
    """单个变量的 OR 结果。"""
    variable: str
    or_value: float
    ci_lower: float
    ci_upper: float
    p_value: float
    n_events: int
    n_total: int
    model_type: str    # "univariable" 或 "multivariable"


@dataclass
class EIHLogisticResult:
    """EIH Logistic 回归完整结果。"""
    univariable: list[ORResult]
    multivariable: list[ORResult]
    n_total: int
    n_eih_positive: int
    eih_rate: float
    predictors_used: list[str]
    converged: bool

    def to_markdown(self) -> str:
        lines = [
            f"## EIH 预测因子 Logistic 回归分析",
            f"",
            f"- 样本量: N={self.n_total}",
            f"- EIH 阳性: {self.n_eih_positive} ({self.eih_rate:.1%})",
            f"- 预测因子: {', '.join(self.predictors_used)}",
            f"- 多因素模型收敛: {'✓' if self.converged else '✗'}",
            f"",
            f"### 单变量分析",
            f"",
            f"| 变量 | OR | 95% CI | P值 |",
            f"|---|---|---|---|",
        ]
        for r in self.univariable:
            p_str = f"{r.p_value:.4f}" if r.p_value >= 0.001 else "<0.001"
            lines.append(
                f"| {r.variable} | {r.or_value:.3f} | "
                f"{r.ci_lower:.3f}–{r.ci_upper:.3f} | {p_str} |"
            )
        lines += [
            f"",
            f"### 多因素分析",
            f"",
            f"| 变量 | aOR | 95% CI | P值 |",
            f"|---|---|---|---|",
        ]
        for r in self.multivariable:
            p_str = f"{r.p_value:.4f}" if r.p_value >= 0.001 else "<0.001"
            lines.append(
                f"| {r.variable} | {r.or_value:.3f} | "
                f"{r.ci_lower:.3f}–{r.ci_upper:.3f} | {p_str} |"
            )
        return "\n".join(lines)

    def to_forest_data(self) -> pd.DataFrame:
        """返回用于绘制森林图的 DataFrame（多因素结果）。"""
        rows = []
        for r in self.multivariable:
            rows.append({
                "variable": r.variable,
                "or": r.or_value,
                "ci_lower": r.ci_lower,
                "ci_upper": r.ci_upper,
                "p_value": r.p_value,
                "significant": r.p_value < 0.05,
            })
        return pd.DataFrame(rows)


class EIHLogisticAnalyzer:
    """
    EIH 多因素 Logistic 回归分析器。

    使用方法：
        analyzer = EIHLogisticAnalyzer()
        result = analyzer.run(df, outcome="eih_status",
                              predictors=["age","sex","vo2_peak","htn_history"])
        report = generate_eih_logistic_report(result)
    """

    def run(
        self,
        df: pd.DataFrame,
        outcome: str = "eih_status",
        predictors: Optional[list[str]] = None,
        use_p0_only: bool = False,
    ) -> EIHLogisticResult:
        """
        运行 EIH Logistic 回归。

        参数：
            df: 含 outcome 列 + 预测因子列的 DataFrame
            outcome: 结局变量列名（0/1）
            predictors: 预测因子列表（None 则使用默认）
            use_p0_only: True 则只用运动前字段（严格 P0 约束）

        返回：EIHLogisticResult
        """
        if predictors is None:
            predictors = P0_ONLY_PREDICTORS if use_p0_only else DEFAULT_PREDICTORS

        # 仅保留存在的列（bmi 可以派生，需特殊处理）
        available_preds = []
        for p in predictors:
            if p in df.columns:
                available_preds.append(p)
            elif p == "bmi" and "height_cm" in df.columns and "weight_kg" in df.columns:
                # bmi 可以派生
                available_preds.append(p)

        if outcome not in df.columns:
            raise ValueError(f"结局变量列 '{outcome}' 不存在")

        # 准备数据（含 bmi 派生）
        df_model = self._prepare_data(df, outcome, available_preds)
        y = df_model[outcome].astype(int).values
        n_total = len(y)
        n_pos = int(y.sum())

        univariable = self._run_univariable(df_model, y, available_preds)
        multivariable, converged = self._run_multivariable(df_model, y, available_preds)

        return EIHLogisticResult(
            univariable=univariable,
            multivariable=multivariable,
            n_total=n_total,
            n_eih_positive=n_pos,
            eih_rate=n_pos / n_total if n_total > 0 else 0.0,
            predictors_used=available_preds,
            converged=converged,
        )

    def _prepare_data(
        self,
        df: pd.DataFrame,
        outcome: str,
        predictors: list[str],
    ) -> pd.DataFrame:
        """准备建模数据：派生 BMI、编码 sex、填充缺失值。"""
        cols = [outcome] + predictors
        df_sub = df[[c for c in cols if c in df.columns]].copy()

        # 派生 BMI（如果 height_cm + weight_kg 存在但 bmi 不存在）
        if "bmi" in predictors and "bmi" not in df.columns:
            if "height_cm" in df.columns and "weight_kg" in df.columns:
                height_m = df["height_cm"] / 100.0
                df_sub["bmi"] = df["weight_kg"] / (height_m ** 2)
            else:
                df_sub["bmi"] = np.nan

        # 编码 sex（F=0, M=1）
        if "sex" in df_sub.columns:
            sex_col = df_sub["sex"]
            # 支持 object 和 Categorical 两种 dtype
            if sex_col.dtype == object or hasattr(sex_col, "cat"):
                df_sub["sex"] = (sex_col.astype(str).str.upper() == "M").astype(float)

        # 中位数填充缺失值（跳过分类列）
        for col in predictors:
            if col in df_sub.columns and df_sub[col].isnull().any():
                if hasattr(df_sub[col], "cat") or df_sub[col].dtype.name == "category":
                    continue  # 分类列不支持 median，跳过
                median_val = df_sub[col].median()
                df_sub[col] = df_sub[col].fillna(median_val)

        # 删除 outcome 缺失行
        df_sub = df_sub.dropna(subset=[outcome])
        return df_sub

    def _run_univariable(
        self,
        df: pd.DataFrame,
        y: np.ndarray,
        predictors: list[str],
    ) -> list[ORResult]:
        """单变量 Logistic 回归（逐个变量）。"""
        results = []
        for pred in predictors:
            if pred not in df.columns:
                continue
            x = df[pred].values.reshape(-1, 1)
            or_result = self._fit_logistic_one(x, y, pred, "univariable", df)
            if or_result is not None:
                results.append(or_result)
        return results

    def _run_multivariable(
        self,
        df: pd.DataFrame,
        y: np.ndarray,
        predictors: list[str],
    ) -> tuple[list[ORResult], bool]:
        """多因素 Logistic 回归（所有预测因子联合）。"""
        avail = [p for p in predictors if p in df.columns]
        if len(avail) < 2:
            return [], False

        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler

            X = df[avail].values
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            model = LogisticRegression(max_iter=1000, solver="lbfgs", random_state=42)
            model.fit(X_scaled, y)

            # 用 bootstrap 估计 95% CI（简化版：50次重采样）
            coefs_boot = self._bootstrap_coefs(X_scaled, y, n_boot=200)

            results = []
            for i, pred in enumerate(avail):
                coef = model.coef_[0][i]
                or_val = float(np.exp(coef))
                # CI from bootstrap
                boot_ors = np.exp(coefs_boot[:, i])
                ci_lo = float(np.percentile(boot_ors, 2.5))
                ci_hi = float(np.percentile(boot_ors, 97.5))
                # Wald p
                se = float(np.std(coefs_boot[:, i]))
                z = coef / se if se > 0 else 0.0
                p = float(2 * (1 - scipy_stats.norm.cdf(abs(z))))

                results.append(ORResult(
                    variable=pred,
                    or_value=or_val,
                    ci_lower=ci_lo,
                    ci_upper=ci_hi,
                    p_value=p,
                    n_events=int(y.sum()),
                    n_total=len(y),
                    model_type="multivariable",
                ))

            return results, True

        except Exception as e:
            logger.warning("多因素 Logistic 回归失败: %s", e)
            return [], False

    def _fit_logistic_one(
        self,
        X: np.ndarray,
        y: np.ndarray,
        var_name: str,
        model_type: str,
        df: pd.DataFrame,
    ) -> Optional[ORResult]:
        """拟合单变量 Logistic（仅用于单变量分析）。"""
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            model = LogisticRegression(max_iter=1000, solver="lbfgs", random_state=42)
            model.fit(X_scaled, y)

            coef = model.coef_[0][0]
            or_val = float(np.exp(coef))

            # Bootstrap CI
            boot_coefs = self._bootstrap_coefs(X_scaled, y, n_boot=200)
            boot_ors = np.exp(boot_coefs[:, 0])
            ci_lo = float(np.percentile(boot_ors, 2.5))
            ci_hi = float(np.percentile(boot_ors, 97.5))

            se = float(np.std(boot_coefs[:, 0]))
            z = coef / se if se > 0 else 0.0
            p = float(2 * (1 - scipy_stats.norm.cdf(abs(z))))

            return ORResult(
                variable=var_name,
                or_value=or_val,
                ci_lower=ci_lo,
                ci_upper=ci_hi,
                p_value=p,
                n_events=int(y.sum()),
                n_total=len(y),
                model_type=model_type,
            )
        except Exception as e:
            logger.warning("单变量回归失败 [%s]: %s", var_name, e)
            return None

    def _bootstrap_coefs(
        self,
        X: np.ndarray,
        y: np.ndarray,
        n_boot: int = 200,
    ) -> np.ndarray:
        """Bootstrap 重采样估计系数分布。"""
        from sklearn.linear_model import LogisticRegression

        n = len(y)
        n_feats = X.shape[1]
        coefs = np.zeros((n_boot, n_feats))

        model = LogisticRegression(max_iter=500, solver="lbfgs", random_state=42)

        rng = np.random.RandomState(42)
        for i in range(n_boot):
            idx = rng.choice(n, n, replace=True)
            X_b, y_b = X[idx], y[idx]
            # 确保两类都有样本
            if len(np.unique(y_b)) < 2:
                coefs[i] = model.coef_[0] if hasattr(model, "coef_") else np.zeros(n_feats)
                continue
            try:
                model.fit(X_b, y_b)
                coefs[i] = model.coef_[0]
            except Exception:
                coefs[i] = np.zeros(n_feats)

        return coefs


def generate_eih_logistic_report(
    result: EIHLogisticResult,
    output_path: str | Path = "reports/eih_logistic_report.md",
) -> str:
    """
    生成 EIH Logistic 回归 Markdown 报告。

    参数：
        result: EIHLogisticAnalyzer.run() 返回值
        output_path: 输出路径

    返回：报告文本
    """
    report_text = result.to_markdown()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    logger.info("EIH Logistic 回归报告已保存: %s", output_path)

    return report_text
