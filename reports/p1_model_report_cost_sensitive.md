# P1 模型报告 — 运动后安全区分层

> 生成日期：2026-04-21

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
| ordinal_logistic | full | 0.3857 | 0.2250 | 0.5039 | 0.3925 ± 0.0132 |
| ordinal_logistic | cycle_only | 0.3857 | 0.2250 | 0.5039 | 0.3925 ± 0.0132 |
| lgbm | full | 0.3924 | 0.1284 | 0.3909 | 0.3949 ± 0.0196 |
| lgbm | cycle_only | 0.3924 | 0.1284 | 0.3909 | 0.3949 ± 0.0196 |
| catboost | full | 0.1871 | 0.0226 | 0.2716 | 0.2903 ± 0.0258 |
| catboost | cycle_only | 0.1871 | 0.0226 | 0.2716 | 0.2903 ± 0.0258 |

## 3. 混淆矩阵

### ordinal_logistic (full)

![Confusion Matrix](reports/figures/m5/p1_cm_ordinal_logistic_full.png)

```
Predicted: green  yellow  red
True green: [187, 68, 3]
True yellow: [87, 133, 0]
True red: [54, 104, 1]
```

### ordinal_logistic (cycle_only)

![Confusion Matrix](reports/figures/m5/p1_cm_ordinal_logistic_cycle_only.png)

```
Predicted: green  yellow  red
True green: [187, 68, 3]
True yellow: [87, 133, 0]
True red: [54, 104, 1]
```

### lgbm (full)

![Confusion Matrix](reports/figures/m5/p1_cm_lgbm_full.png)

```
Predicted: green  yellow  red
True green: [80, 72, 106]
True yellow: [23, 84, 113]
True red: [23, 51, 85]
```

### lgbm (cycle_only)

![Confusion Matrix](reports/figures/m5/p1_cm_lgbm_cycle_only.png)

```
Predicted: green  yellow  red
True green: [80, 72, 106]
True yellow: [23, 84, 113]
True red: [23, 51, 85]
```

### catboost (full)

![Confusion Matrix](reports/figures/m5/p1_cm_catboost_full.png)

```
Predicted: green  yellow  red
True green: [7, 16, 235]
True yellow: [1, 13, 206]
True red: [1, 5, 153]
```

### catboost (cycle_only)

![Confusion Matrix](reports/figures/m5/p1_cm_catboost_cycle_only.png)

```
Predicted: green  yellow  red
True green: [7, 16, 235]
True yellow: [1, 13, 206]
True red: [1, 5, 153]
```


## 4. SHAP 特征解释

_SHAP 解释未运行，请执行 `make model-interpret` 后查看_

## 5. 踏车协议一致性分析

对比全样本与踏车协议子集模型的 F1_macro / kappa 差异，
验证模型在不同运动协议下的稳健性。

| 模型 | full F1 | cycle F1 | Δ F1 | full κ | cycle κ | Δ κ |
|---|---|---|---|---|---|---|
| ordinal_logistic | 0.3857 | 0.3857 | +0.0000 | 0.2250 | 0.2250 | +0.0000 |

![Cycle Consistency](reports/figures/m5/p1_cycle_consistency_ordinal_logistic.png)

| lgbm | 0.3924 | 0.3924 | +0.0000 | 0.1284 | 0.1284 | +0.0000 |

![Cycle Consistency](reports/figures/m5/p1_cycle_consistency_lgbm.png)

| catboost | 0.1871 | 0.1871 | +0.0000 | 0.0226 | 0.0226 | +0.0000 |

![Cycle Consistency](reports/figures/m5/p1_cycle_consistency_catboost.png)


---
_报告由 ModelReportGenerator 自动生成_