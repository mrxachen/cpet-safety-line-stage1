# P1 模型报告 — 运动后安全区分层

> 生成日期：2026-04-15

## 1. 实验概述

### 任务定义
- **P1**：运动后安全区分层（3-class ordinal: green=0 / yellow=1 / red=2）
- **输入**：CPET 运动结果（peak VO₂ / threshold / VE/VCO₂ / EIH 等）
- **输出**：安全区分类（green / yellow / red）+ 各区概率
- **评估**：F1_macro, Cohen's kappa（weighted）

### 模型对比
- Ordinal Logistic（基线，可解释）
- LightGBM（主模型）
- CatBoost（对照）
- 双样本：全样本（full）vs 踏车协议（cycle_only）

## 2. 性能对比表

| 模型 | 样本 | F1_macro | Kappa | Accuracy | CV_F1(mean±std) |
|---|---|---|---|---|---|
| ordinal_logistic | full | 0.3860 | 0.2220 | 0.5039 | 0.3885 ± 0.0168 |
| ordinal_logistic | cycle_only | 0.3860 | 0.2220 | 0.5039 | 0.3885 ± 0.0168 |
| lgbm | full | 0.4731 | 0.2733 | 0.5086 | 0.4450 ± 0.0108 |
| lgbm | cycle_only | 0.4731 | 0.2733 | 0.5086 | 0.4450 ± 0.0108 |
| catboost | full | 0.4648 | 0.2640 | 0.5024 | 0.4562 ± 0.0110 |
| catboost | cycle_only | 0.4648 | 0.2640 | 0.5024 | 0.4562 ± 0.0110 |

## 3. 混淆矩阵

### ordinal_logistic (full)

![Confusion Matrix](reports/figures/m5/p1_cm_ordinal_logistic_full.png)

```
Predicted: green  yellow  red
True green: [187, 69, 2]
True yellow: [85, 133, 2]
True red: [57, 101, 1]
```

### ordinal_logistic (cycle_only)

![Confusion Matrix](reports/figures/m5/p1_cm_ordinal_logistic_cycle_only.png)

```
Predicted: green  yellow  red
True green: [187, 69, 2]
True yellow: [85, 133, 2]
True red: [57, 101, 1]
```

### lgbm (full)

![Confusion Matrix](reports/figures/m5/p1_cm_lgbm_full.png)

```
Predicted: green  yellow  red
True green: [173, 69, 16]
True yellow: [69, 110, 41]
True red: [50, 68, 41]
```

### lgbm (cycle_only)

![Confusion Matrix](reports/figures/m5/p1_cm_lgbm_cycle_only.png)

```
Predicted: green  yellow  red
True green: [173, 69, 16]
True yellow: [69, 110, 41]
True red: [50, 68, 41]
```

### catboost (full)

![Confusion Matrix](reports/figures/m5/p1_cm_catboost_full.png)

```
Predicted: green  yellow  red
True green: [167, 79, 12]
True yellow: [64, 116, 40]
True red: [50, 72, 37]
```

### catboost (cycle_only)

![Confusion Matrix](reports/figures/m5/p1_cm_catboost_cycle_only.png)

```
Predicted: green  yellow  red
True green: [167, 79, 12]
True yellow: [64, 116, 40]
True red: [50, 72, 37]
```


## 4. SHAP 特征解释

_SHAP 解释未运行，请执行 `make model-interpret` 后查看_

## 5. 踏车协议一致性分析

对比全样本与踏车协议子集模型的 F1_macro / kappa 差异，
验证模型在不同运动协议下的稳健性。

| 模型 | full F1 | cycle F1 | Δ F1 | full κ | cycle κ | Δ κ |
|---|---|---|---|---|---|---|
| ordinal_logistic | 0.3860 | 0.3860 | +0.0000 | 0.2220 | 0.2220 | +0.0000 |

![Cycle Consistency](reports/figures/m5/p1_cycle_consistency_ordinal_logistic.png)

| lgbm | 0.4731 | 0.4731 | +0.0000 | 0.2733 | 0.2733 | +0.0000 |

![Cycle Consistency](reports/figures/m5/p1_cycle_consistency_lgbm.png)

| catboost | 0.4648 | 0.4648 | +0.0000 | 0.2640 | 0.2640 | +0.0000 |

![Cycle Consistency](reports/figures/m5/p1_cycle_consistency_catboost.png)


---
_报告由 ModelReportGenerator 自动生成_