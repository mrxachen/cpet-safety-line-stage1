# 结局锚定安全区模型报告（Method 1 / Phase G）

## 方法概述

直接以 `test_result`（CPET 临床结局）为标签，全特征建模，消除 P1 循环依赖。

## 模型性能

| 指标 | 值 |
|---|---|
| CV AUC (5折) | 0.578 ± 0.031 |
| 测试集 AUC | 0.548 |
| 测试集 AP | 0.178 |
| 测试集 Brier | 0.126 |
| 阳性率 | 14.7% |
| 训练集 N | 2550 |
| 测试集 N | 638 |

## 安全区切点

| 参数 | 值 |
|---|---|
| Green/Yellow 界 | P < 0.140 |
| Yellow/Red 界 | P ≥ 0.150 |
| 方法 | sensitivity_constrained_youden |
| Green/Yellow 处敏感度 | 0.909 |
| Green/Yellow 处特异度 | 0.503 |
| Youden J (Yellow/Red) | 0.448 |

## 安全区分布

- **Green**: 1400 (43.9%), 阳性率 5.1%
- **Yellow**: 372 (11.7%), 阳性率 10.5%
- **Red**: 1416 (44.4%), 阳性率 25.3%

## 特征重要性（Top 10）

| 特征 | 重要性 |
|---|---|
| hr_peak | 96 |
| ve_vco2_slope | 95 |
| age | 78 |
| oues | 67 |
| vt1_vo2 | 63 |
| bmi | 55 |
| vo2_peak_pct_pred | 45 |
| o2_pulse_peak | 42 |
| htn_history | 32 |
| mets_peak | 25 |