# Outcome-Anchor Validation Report (Stage 1B)

- 模型类型：elastic_net
- 训练集：2585，测试集：647
- 阳性率：14.5%

## 性能指标

| 指标 | 值 |
|---|---|
| CV AUC (mean ± std) | 0.564 ± 0.016 |
| Test AUC | 0.608 |
| Test AUPRC | 0.203 |
| Brier Score | 0.125 |
| Calibration intercept | -1.870 |
| Calibration slope | -0.055 |

## 说明

本模型定位为**验证器**，而非主标签制造器。
AUC 预期范围：0.55-0.65（summary-level CPET 本身信息限制）。
- AUC > 0.65：提示 outcome model 有额外信息，可作为 confidence engine 补充
- AUC < 0.55：final zone 与 test_result 关系弱，需关注数据质量

## 风险分位分布

- low: 1077 (33.3%)
- mid: 1078 (33.4%)
- high: 1077 (33.3%)