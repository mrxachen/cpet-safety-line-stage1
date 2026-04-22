"""
reference_builder.py — 参考正常方程构建与 %pred / z-score 计算。

基于 reference_flag_wide 标记的参考子集拟合 OLS：
    target ~ age + C(sex) + age:C(sex)

输出：
- 各目标变量的参考方程（系数、R²、残差标准差）
- 全样本 %pred 和 z-score 列
- 诊断报告
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
class ReferenceEquation:
    """单变量参考方程信息。"""

    target: str
    formula: str
    coefficients: dict[str, float]   # 系数字典（截距 + 各预测变量）
    r_squared: float
    residual_std: float              # 残差标准差（用于z-score）
    n_ref: int                       # 参考子集样本量
    n_per_sex: dict[str, int]        # 各性别样本量
    used_interaction: bool


@dataclass
class ReferenceBuilderResult:
    """参考方程构建结果。"""

    equations: dict[str, ReferenceEquation]   # {target_name: equation}
    pred_df: pd.DataFrame                      # 含 %pred + z-score 的列
    diagnostics: pd.DataFrame                  # 方程诊断表
    config: dict[str, Any]

    def to_markdown(self, path: str | Path | None = None) -> str:
        """输出参考方程诊断报告（Markdown）。"""
        lines = ["# 参考正常方程诊断报告", ""]

        for vname, eq in self.equations.items():
            lines.append(f"## {eq.target}")
            lines.append(f"- 公式：`{eq.formula}`")
            lines.append(f"- N(参考子集)：{eq.n_ref}（男={eq.n_per_sex.get('M', '?')}，女={eq.n_per_sex.get('F', '?')}）")
            lines.append(f"- R²：{eq.r_squared:.3f}")
            lines.append(f"- 残差SD：{eq.residual_std:.3f}")
            lines.append(f"- 含交互项：{'是' if eq.used_interaction else '否（样本不足，退化）'}")
            lines.append("- 系数：")
            for coef_name, coef_val in eq.coefficients.items():
                lines.append(f"  - {coef_name}: {coef_val:.4f}")
            lines.append("")

        # 汇总诊断表
        if not self.diagnostics.empty:
            lines.append("## 汇总诊断表")
            lines.append("")
            lines.append(_df_to_pipe_table(self.diagnostics, index=False))

        md_str = "\n".join(lines)
        if path is not None:
            out_path = Path(path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md_str, encoding="utf-8")
            logger.info("参考方程报告保存: %s", out_path)

        return md_str


class ReferenceBuilder:
    """
    参考正常方程构建器。

    使用方法：
        builder = ReferenceBuilder("configs/stats/table1_config.yaml")
        result = builder.build(df)
        result.to_markdown("reports/reference_equations.md")
    """

    def __init__(self, config_path: str | Path) -> None:
        self._config_path = Path(config_path)
        self._cfg = self._load_config(self._config_path)
        self._ref_cfg = self._cfg.get("reference", {})

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(f"stats 配置不存在: {path}")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _fit_equation(
        self,
        ref_df: pd.DataFrame,
        target: str,
        predictors: list[str],
        use_interaction: bool,
    ) -> ReferenceEquation | None:
        """
        拟合 OLS 参考方程。

        公式：target ~ age + C(sex) + age:C(sex)  （含交互）
              或    target ~ age + C(sex)           （无交互）

        参数：
            ref_df: 参考子集
            target: 目标变量
            predictors: 预测变量列表（age, sex）
            use_interaction: 是否含交互项

        返回：
            ReferenceEquation 或 None（拟合失败）
        """
        try:
            import statsmodels.formula.api as smf
        except ImportError:
            logger.error("statsmodels 未安装，无法拟合参考方程")
            return None

        sub = ref_df[[target] + predictors].dropna().copy()
        n = len(sub)

        if n < 10:
            logger.warning("参考子集过小（n=%d），跳过 %s", n, target)
            return None

        # 各性别样本量
        sex_col = next((p for p in predictors if "sex" in p.lower()), "sex")
        n_per_sex: dict[str, int] = {}
        if sex_col in sub.columns:
            for sv in sub[sex_col].unique():
                n_per_sex[str(sv)] = int((sub[sex_col] == sv).sum())

        # 最小样本量检查
        min_per_sex = self._ref_cfg.get("min_per_sex", 20)
        can_interact = use_interaction and all(
            v >= min_per_sex for v in n_per_sex.values()
        )
        if use_interaction and not can_interact:
            logger.warning(
                "%s: 某性别参考子集 < %d，退化为无交互模型（n_per_sex=%s）",
                target, min_per_sex, n_per_sex,
            )

        # 构建 formula
        age_col = next((p for p in predictors if "age" in p.lower()), "age")
        if sex_col in sub.columns:
            if can_interact:
                formula = f"{target} ~ {age_col} + C({sex_col}) + {age_col}:C({sex_col})"
            else:
                formula = f"{target} ~ {age_col} + C({sex_col})"
        else:
            formula = f"{target} ~ {age_col}"

        try:
            model = smf.ols(formula=formula, data=sub).fit()
        except Exception as e:
            logger.warning("OLS 拟合失败 (%s): %s", target, e)
            return None

        # 提取系数
        coefs = {str(k): float(v) for k, v in model.params.items()}
        r2 = float(model.rsquared)
        res_std = float(model.resid.std(ddof=len(model.params)))

        return ReferenceEquation(
            target=target,
            formula=formula,
            coefficients=coefs,
            r_squared=r2,
            residual_std=res_std,
            n_ref=n,
            n_per_sex=n_per_sex,
            used_interaction=can_interact,
        )

    def _predict_and_score(
        self,
        df: pd.DataFrame,
        equation: ReferenceEquation,
        predictors: list[str],
    ) -> tuple[pd.Series, pd.Series]:
        """
        基于参考方程计算 %pred 和 z-score。

        %pred = 100 × actual / predicted
        z-score = (actual - predicted) / residual_std

        参数：
            df: 全样本 DataFrame
            equation: 参考方程
            predictors: 预测变量列表

        返回：
            (pct_pred, z_score) — 均含 NaN（缺失行）
        """
        target = equation.target
        if target not in df.columns:
            return pd.Series(float("nan"), index=df.index), pd.Series(float("nan"), index=df.index)

        # 手动计算预测值（避免 statsmodels predict 的依赖性）
        try:
            import statsmodels.formula.api as smf

            # 构建预测子集（含 predictor 列）
            needed = [target] + predictors
            pred_sub = df[[c for c in needed if c in df.columns]].copy()

            model_fit = smf.ols(
                formula=equation.formula,
                data=pred_sub.dropna(),
            ).fit()

            # 对全行预测（缺失行自动为 NaN）
            predicted = model_fit.predict(pred_sub)
        except Exception as e:
            logger.warning("预测失败 (%s): %s", target, e)
            predicted = pd.Series(float("nan"), index=df.index)

        actual = df[target]
        res_std = equation.residual_std if equation.residual_std > 0 else float("nan")

        # %pred（预测值为0或负时为 NaN）
        pct_pred = actual.where(predicted.abs() > 1e-8).div(
            predicted.where(predicted.abs() > 1e-8)
        ) * 100

        # z-score
        z_score = (actual - predicted) / res_std

        return pct_pred, z_score

    def build(self, df: pd.DataFrame) -> ReferenceBuilderResult:
        """
        构建所有目标变量的参考方程，并输出 %pred / z-score。

        参数：
            df: 含 reference_flag_wide、age、sex 及目标变量的 DataFrame

        返回：
            ReferenceBuilderResult
        """
        subset_flag = self._ref_cfg.get("subset_flag", "reference_flag_wide")
        predictors = self._ref_cfg.get("predictors", ["age", "sex"])
        use_interaction = self._ref_cfg.get("interaction", True)
        targets_cfg = self._ref_cfg.get("target_variables", [])
        pct_suffix = self._ref_cfg.get("pct_pred_suffix", "_pct_ref")
        z_suffix = self._ref_cfg.get("z_score_suffix", "_z_ref")

        # 提取参考子集
        if subset_flag in df.columns:
            ref_df = df[df[subset_flag].astype(bool)].copy()
        else:
            logger.warning("reference_flag 列不存在 (%s)，使用全部数据作参考", subset_flag)
            ref_df = df.copy()

        logger.info("参考子集: n=%d / %d (%.1f%%)", len(ref_df), len(df), 100 * len(ref_df) / max(len(df), 1))

        equations: dict[str, ReferenceEquation] = {}
        pred_cols: dict[str, pd.Series] = {}
        diag_rows: list[dict[str, Any]] = []

        for tgt_cfg in targets_cfg:
            vname = tgt_cfg["name"]
            vlabel = tgt_cfg.get("label", vname)

            if vname not in df.columns:
                logger.debug("目标变量不存在，跳过: %s", vname)
                continue

            eq = self._fit_equation(ref_df, vname, predictors, use_interaction)
            if eq is None:
                continue

            equations[vname] = eq

            # 计算 %pred 和 z-score
            pct_pred, z_score = self._predict_and_score(df, eq, predictors)
            pred_cols[vname + pct_suffix] = pct_pred
            pred_cols[vname + z_suffix] = z_score

            # 诊断行
            diag_rows.append({
                "变量": vlabel,
                "N参考": eq.n_ref,
                "公式": eq.formula,
                "R²": f"{eq.r_squared:.3f}",
                "残差SD": f"{eq.residual_std:.3f}",
                "含交互": "是" if eq.used_interaction else "否",
            })

            logger.info(
                "参考方程 %s: R²=%.3f, res_std=%.3f, n=%d",
                vname, eq.r_squared, eq.residual_std, eq.n_ref,
            )

        # 汇总输出 DataFrame
        pred_df = pd.DataFrame(pred_cols, index=df.index)
        diagnostics = pd.DataFrame(diag_rows)

        return ReferenceBuilderResult(
            equations=equations,
            pred_df=pred_df,
            diagnostics=diagnostics,
            config=self._ref_cfg,
        )


def _df_to_pipe_table(df: "pd.DataFrame", index: bool = False) -> str:
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
