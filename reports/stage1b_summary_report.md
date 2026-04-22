# Stage 1B Summary Report

- 总样本数：3232
- 输出列：['reserve_burden', 'vent_burden', 'p_lab', 'phenotype_zone', 'instability_severe', 'instability_mild', 'final_zone_before_confidence', 'confidence_score', 'confidence_label', 'indeterminate_flag', 'final_zone', 'outcome_risk_prob', 'anomaly_flag']

## final_zone 分布

| Zone | N | % |
|---|---|---|
| green | 807 | 25.0% |
| yellow | 933 | 28.9% |
| red | 1432 | 44.3% |
| yellow_gray | 60 | 1.9% |

## 置信度分布

| Label | N | % |
|---|---|---|
| high | 2397 | 74.2% |
| medium | 774 | 23.9% |
| low | 61 | 1.9% |
| indeterminate | 60 | 1.9% |

## 构念效度（final_zone vs test_result）

- 方向：**non-monotone**
- 单调梯度：❌
- green 阳性率：14.1%
- yellow 阳性率：15.2%
- red 阳性率：14.7%

## 参考子集合理性

- 参考子集 N：855
- green%：68.8%
- red%：10.2%
- 参考合理：✅

## 验收判定：**Warn**

- 原因：final_zone vs test_result 单调梯度不完整

## Outcome Risk 分布

- Mean prob：0.145
- Median prob：0.142