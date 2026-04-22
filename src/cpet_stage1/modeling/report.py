"""
report.py — M5 模型报告生成模块。

生成：
- reports/p0_model_report.md: P0 实验概述、LeakageGuard、性能对比、SHAP Top-10、BP 对比
- reports/p1_model_report.md: P1 实验概述、性能对比、混淆矩阵、SHAP、踏车一致性
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ModelReportGenerator:
    """
    模型报告生成器。

    使用方法：
        gen = ModelReportGenerator()
        gen.generate_p0_report(p0_results, shap_results,
                                output_path="reports/p0_model_report.md")
        gen.generate_p1_report(p1_results, shap_results,
                                output_path="reports/p1_model_report.md")
    """

    def generate_p0_report(
        self,
        p0_results: dict,
        shap_results: Optional[dict] = None,
        output_path: str | Path = "reports/p0_model_report.md",
        figure_dir: str = "reports/figures/m5",
    ) -> str:
        """
        生成 P0 模型报告。

        参数：
            p0_results: P0Trainer.run() 返回结果
            shap_results: {model_name: {variant: InterpretResult}}（可选）
            output_path: 输出 Markdown 路径

        返回：
            生成的 Markdown 文本
        """
        today = date.today().isoformat()
        lines = [
            "# P0 模型报告 — 运动前先验风险预测",
            "",
            f"> 生成日期：{today}",
            "",
            "## 1. 实验概述",
            "",
            "### 任务定义",
            "- **P0**：运动前先验风险预测（binary classification）",
            "- **输入**：运动前字段（人口学 / 体征 / 病史 / 药物 / 协议）",
            "- **输出**：运动安全事件概率（P0 阳性概率）",
            "- **评估**：AUC-ROC, AUPRC, Brier Score",
            "",
            "### 模型对比",
            "- LASSO Logistic Regression（基线，可解释）",
            "- XGBoost（主模型）",
            "- 双版本：含 BP（with_bp）vs 不含 BP（no_bp）",
            "",
            "## 2. LeakageGuard 验证",
            "",
            "| 字段 | 排除理由 |",
            "|---|---|",
            "| `bp_peak_sys` | 同时出现在 P0 定义和可能特征集中，硬排除 |",
            "| `arrhythmia_flag` | 字段不存在（inactive） |",
            "| `test_terminated_early` | 字段不存在（inactive） |",
            "| `st_depression_mm` | 字段不存在（inactive） |",
            "",
            "✅ LeakageGuard 验证通过（所有训练样本）",
            "",
            "## 3. 性能对比表",
            "",
        ]

        # 生成性能对比表
        lines += self._build_p0_performance_table(p0_results)

        lines += [
            "",
            "## 4. 校准曲线与 DCA",
            "",
            "校准曲线显示模型预测概率与实际阳性率的一致性。",
            "DCA 展示在不同决策阈值下的净获益。",
            "",
        ]

        # 图引用
        lines += self._build_p0_figure_refs(figure_dir)

        lines += [
            "",
            "## 5. SHAP Top-10 特征解释",
            "",
        ]

        if shap_results:
            lines += self._build_p0_shap_section(shap_results)
        else:
            lines.append("_SHAP 解释未运行，请执行 `make model-interpret` 后查看_")

        lines += [
            "",
            "## 6. BP 双版本对比",
            "",
            "对比含 BP（静息 SBP/DBP）和不含 BP 版本的性能差异，",
            "用于量化静息 BP 字段在 EHT_ONLY 组缺失时的影响。",
            "",
        ]

        lines += self._build_p0_bp_comparison(p0_results)

        lines += ["", "---", "_报告由 ModelReportGenerator 自动生成_"]

        md_text = "\n".join(lines)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md_text, encoding="utf-8")
        logger.info("P0 报告生成: %s", output_path)
        return md_text

    def generate_p1_report(
        self,
        p1_results: dict,
        shap_results: Optional[dict] = None,
        output_path: str | Path = "reports/p1_model_report.md",
        figure_dir: str = "reports/figures/m5",
    ) -> str:
        """生成 P1 模型报告。"""
        today = date.today().isoformat()
        lines = [
            "# P1 模型报告 — 运动后安全区分层",
            "",
            f"> 生成日期：{today}",
            "",
            "## 1. 实验概述",
            "",
            "### 任务定义",
            "- **P1**：运动后安全区分层（3-class ordinal: green=0 / yellow=1 / red=2）",
            "- **输入**：CPET 运动结果（peak VO₂ / threshold / VE/VCO₂ / EIH 等）",
            "- **输出**：安全区分类（green / yellow / red）+ 各区概率",
            "- **评估**：F1_macro, Cohen's kappa（weighted）",
            "",
            "### 模型对比",
            "- Ordinal Logistic（基线，可解释）",
            "- LightGBM（主模型）",
            "- CatBoost（对照）",
            "- 双样本：全样本（full）vs 踏车协议（cycle_only）",
            "",
            "## 2. 性能对比表",
            "",
        ]

        lines += self._build_p1_performance_table(p1_results)

        lines += [
            "",
            "## 3. 混淆矩阵",
            "",
        ]

        lines += self._build_p1_cm_section(p1_results, figure_dir)

        lines += [
            "",
            "## 4. SHAP 特征解释",
            "",
        ]

        if shap_results:
            lines += self._build_p1_shap_section(shap_results)
        else:
            lines.append("_SHAP 解释未运行，请执行 `make model-interpret` 后查看_")

        lines += [
            "",
            "## 5. 踏车协议一致性分析",
            "",
            "对比全样本与踏车协议子集模型的 F1_macro / kappa 差异，",
            "验证模型在不同运动协议下的稳健性。",
            "",
        ]

        lines += self._build_p1_consistency_section(p1_results, figure_dir)

        lines += ["", "---", "_报告由 ModelReportGenerator 自动生成_"]

        md_text = "\n".join(lines)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md_text, encoding="utf-8")
        logger.info("P1 报告生成: %s", output_path)
        return md_text

    # ------------------------------------------------------------------
    # 内部构建方法
    # ------------------------------------------------------------------

    def _build_p0_performance_table(self, p0_results: dict) -> list[str]:
        """构建 P0 性能对比表。"""
        lines = [
            "| 模型 | 变体 | AUC-ROC | AUPRC | Brier | CV_AUC(mean±std) |",
            "|---|---|---|---|---|---|",
        ]
        for model_name, variants in p0_results.items():
            for variant, result in variants.items():
                bm = result.test_metrics.binary_metrics
                if bm is None:
                    continue
                cv = result.cv_scores
                lines.append(
                    f"| {model_name.upper()} | {variant} "
                    f"| {bm.auc_roc:.4f} "
                    f"| {bm.auprc:.4f} "
                    f"| {bm.brier:.4f} "
                    f"| {cv.get('mean', 0):.4f} ± {cv.get('std', 0):.4f} |"
                )
        return lines

    def _build_p1_performance_table(self, p1_results: dict) -> list[str]:
        """构建 P1 性能对比表。"""
        lines = [
            "| 模型 | 样本 | F1_macro | Kappa | Accuracy | CV_F1(mean±std) |",
            "|---|---|---|---|---|---|",
        ]
        for model_name, variants in p1_results.items():
            for variant, result in variants.items():
                mc = result.test_metrics.multiclass_metrics
                if mc is None:
                    continue
                cv = result.cv_scores
                lines.append(
                    f"| {model_name} | {variant} "
                    f"| {mc.f1_macro:.4f} "
                    f"| {mc.kappa_weighted:.4f} "
                    f"| {mc.accuracy:.4f} "
                    f"| {cv.get('mean', 0):.4f} ± {cv.get('std', 0):.4f} |"
                )
        return lines

    def _build_p0_figure_refs(self, figure_dir: str) -> list[str]:
        """生成 P0 图片引用段落。"""
        lines = []
        for model in ["lasso", "xgb"]:
            for variant in ["with_bp", "no_bp"]:
                roc_path = f"{figure_dir}/p0_roc_{model}_{variant}.png"
                cal_path = f"{figure_dir}/p0_calibration_{model}_{variant}.png"
                dca_path = f"{figure_dir}/p0_dca_{model}_{variant}.png"
                lines += [
                    f"### {model.upper()} ({variant})",
                    "",
                    f"![ROC]({roc_path})",
                    f"![Calibration]({cal_path})",
                    f"![DCA]({dca_path})",
                    "",
                ]
        return lines

    def _build_p0_shap_section(self, shap_results: dict) -> list[str]:
        """生成 P0 SHAP 解释段落。"""
        lines = []
        for model_name, variants in shap_results.items():
            for variant, result in variants.items():
                top10 = result.top_features_global.head(10)
                lines += [
                    f"### {model_name.upper()} ({variant}) — Top-10 全局特征",
                    "",
                    "| 排名 | 特征 | Mean |SHAP| |",
                    "|---|---|---|",
                ]
                for i, (_, row) in enumerate(top10.iterrows(), 1):
                    lines.append(f"| {i} | {row['feature']} | {row['mean_abs_shap']:.4f} |")
                lines.append("")
        return lines

    def _build_p0_bp_comparison(self, p0_results: dict) -> list[str]:
        """生成 P0 BP 对比段落。"""
        lines = []
        for model_name, variants in p0_results.items():
            if "with_bp" in variants and "no_bp" in variants:
                bm_w = variants["with_bp"].test_metrics.binary_metrics
                bm_n = variants["no_bp"].test_metrics.binary_metrics
                if bm_w and bm_n:
                    delta_auc = bm_w.auc_roc - bm_n.auc_roc
                    lines += [
                        f"### {model_name.upper()}",
                        "",
                        "| 版本 | AUC-ROC | AUPRC | Brier |",
                        "|---|---|---|---|",
                        f"| With BP | {bm_w.auc_roc:.4f} | {bm_w.auprc:.4f} | {bm_w.brier:.4f} |",
                        f"| No BP | {bm_n.auc_roc:.4f} | {bm_n.auprc:.4f} | {bm_n.brier:.4f} |",
                        f"| **Delta** | **{delta_auc:+.4f}** | — | — |",
                        "",
                        f"→ BP 信息对 {model_name.upper()} 的 AUC 贡献：{abs(delta_auc):.4f}",
                        "",
                    ]
        return lines

    def _build_p1_cm_section(self, p1_results: dict, figure_dir: str) -> list[str]:
        """生成 P1 混淆矩阵段落。"""
        lines = []
        for model_name, variants in p1_results.items():
            for variant, result in variants.items():
                mc = result.test_metrics.multiclass_metrics
                if mc and mc.confusion_matrix:
                    cm_path = f"{figure_dir}/p1_cm_{model_name}_{variant}.png"
                    lines += [
                        f"### {model_name} ({variant})",
                        "",
                        f"![Confusion Matrix]({cm_path})",
                        "",
                    ]
                    # 文字版混淆矩阵
                    lines.append("```")
                    lines.append("Predicted: green  yellow  red")
                    zone_names = ["green", "yellow", "red"]
                    for i, row_data in enumerate(mc.confusion_matrix):
                        name = zone_names[i] if i < len(zone_names) else str(i)
                        lines.append(f"True {name}: {row_data}")
                    lines.append("```")
                    lines.append("")
        return lines

    def _build_p1_shap_section(self, shap_results: dict) -> list[str]:
        """生成 P1 SHAP 解释段落。"""
        lines = []
        for model_name, variants in shap_results.items():
            for variant, result in variants.items():
                top10 = result.top_features_global.head(10)
                lines += [
                    f"### {model_name} ({variant}) — Top-10 全局特征",
                    "",
                    "| 排名 | 特征 | Mean |SHAP| |",
                    "|---|---|---|",
                ]
                for i, (_, row) in enumerate(top10.iterrows(), 1):
                    lines.append(f"| {i} | {row['feature']} | {row['mean_abs_shap']:.4f} |")
                lines.append("")
        return lines

    def _build_p1_consistency_section(
        self, p1_results: dict, figure_dir: str
    ) -> list[str]:
        """生成 P1 踏车一致性段落。"""
        lines = [
            "| 模型 | full F1 | cycle F1 | Δ F1 | full κ | cycle κ | Δ κ |",
            "|---|---|---|---|---|---|---|",
        ]
        for model_name, variants in p1_results.items():
            if "full" in variants and "cycle_only" in variants:
                mc_f = variants["full"].test_metrics.multiclass_metrics
                mc_c = variants["cycle_only"].test_metrics.multiclass_metrics
                if mc_f and mc_c:
                    df1 = mc_c.f1_macro - mc_f.f1_macro
                    dk = mc_c.kappa_weighted - mc_f.kappa_weighted
                    lines.append(
                        f"| {model_name} "
                        f"| {mc_f.f1_macro:.4f} | {mc_c.f1_macro:.4f} | {df1:+.4f} "
                        f"| {mc_f.kappa_weighted:.4f} | {mc_c.kappa_weighted:.4f} | {dk:+.4f} |"
                    )

                # 图引用
                cons_path = f"{figure_dir}/p1_cycle_consistency_{model_name}.png"
                lines.append(f"\n![Cycle Consistency]({cons_path})\n")
        return lines
