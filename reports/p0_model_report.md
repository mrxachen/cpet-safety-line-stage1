# P0 模型报告 — 运动前先验风险预测

> 生成日期：2026-04-15

## 1. 实验概述

### 任务定义
- **P0**：运动前先验风险预测（binary classification）
- **输入**：运动前字段（人口学 / 体征 / 病史 / 药物 / 协议）
- **输出**：运动安全事件概率（P0 阳性概率）
- **评估**：AUC-ROC, AUPRC, Brier Score

### 模型对比
- LASSO Logistic Regression（基线，可解释）
- XGBoost（主模型）
- 双版本：含 BP（with_bp）vs 不含 BP（no_bp）

## 2. LeakageGuard 验证

| 字段 | 排除理由 |
|---|---|
| `bp_peak_sys` | 同时出现在 P0 定义和可能特征集中，硬排除 |
| `arrhythmia_flag` | 字段不存在（inactive） |
| `test_terminated_early` | 字段不存在（inactive） |
| `st_depression_mm` | 字段不存在（inactive） |

✅ LeakageGuard 验证通过（所有训练样本）

## 3. 性能对比表

| 模型 | 变体 | AUC-ROC | AUPRC | Brier | CV_AUC(mean±std) |
|---|---|---|---|---|---|
| LASSO | with_bp | 0.5822 | 0.2828 | 0.1731 | 0.6231 ± 0.0281 |
| LASSO | no_bp | 0.5822 | 0.2828 | 0.1731 | 0.6231 ± 0.0281 |
| XGB | with_bp | 0.5609 | 0.2789 | 0.1834 | 0.6225 ± 0.0160 |
| XGB | no_bp | 0.5609 | 0.2789 | 0.1834 | 0.6225 ± 0.0160 |

## 4. 校准曲线与 DCA

校准曲线显示模型预测概率与实际阳性率的一致性。
DCA 展示在不同决策阈值下的净获益。

### LASSO (with_bp)

![ROC](reports/figures/m5/p0_roc_lasso_with_bp.png)
![Calibration](reports/figures/m5/p0_calibration_lasso_with_bp.png)
![DCA](reports/figures/m5/p0_dca_lasso_with_bp.png)

### LASSO (no_bp)

![ROC](reports/figures/m5/p0_roc_lasso_no_bp.png)
![Calibration](reports/figures/m5/p0_calibration_lasso_no_bp.png)
![DCA](reports/figures/m5/p0_dca_lasso_no_bp.png)

### XGB (with_bp)

![ROC](reports/figures/m5/p0_roc_xgb_with_bp.png)
![Calibration](reports/figures/m5/p0_calibration_xgb_with_bp.png)
![DCA](reports/figures/m5/p0_dca_xgb_with_bp.png)

### XGB (no_bp)

![ROC](reports/figures/m5/p0_roc_xgb_no_bp.png)
![Calibration](reports/figures/m5/p0_calibration_xgb_no_bp.png)
![DCA](reports/figures/m5/p0_dca_xgb_no_bp.png)


## 5. SHAP Top-10 特征解释

_SHAP 解释未运行，请执行 `make model-interpret` 后查看_

## 6. BP 双版本对比

对比含 BP（静息 SBP/DBP）和不含 BP 版本的性能差异，
用于量化静息 BP 字段在 EHT_ONLY 组缺失时的影响。

### LASSO

| 版本 | AUC-ROC | AUPRC | Brier |
|---|---|---|---|
| With BP | 0.5822 | 0.2828 | 0.1731 |
| No BP | 0.5822 | 0.2828 | 0.1731 |
| **Delta** | **+0.0000** | — | — |

→ BP 信息对 LASSO 的 AUC 贡献：0.0000

### XGB

| 版本 | AUC-ROC | AUPRC | Brier |
|---|---|---|---|
| With BP | 0.5609 | 0.2789 | 0.1834 |
| No BP | 0.5609 | 0.2789 | 0.1834 |
| **Delta** | **+0.0000** | — | — |

→ BP 信息对 XGB 的 AUC 贡献：0.0000


---
_报告由 ModelReportGenerator 自动生成_