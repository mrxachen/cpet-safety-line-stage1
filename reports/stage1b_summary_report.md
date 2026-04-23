# Stage 1B Summary Report

- 总样本数：3232
- 输出列：['reserve_burden', 'vent_burden', 'p_lab', 'phenotype_zone', 'instability_severe', 'instability_mild', 'final_zone_before_confidence', 'confidence_score', 'confidence_label', 'indeterminate_flag', 'final_zone', 'outcome_risk_prob', 'anomaly_flag']

## final_zone 分布

| Zone | N | % |
|---|---|---|
| green | 637 | 19.7% |
| yellow | 829 | 25.6% |
| red | 961 | 29.7% |
| yellow_gray | 805 | 24.9% |

## 置信度分布

| Label | N | % |
|---|---|---|
| high | 1065 | 33.0% |
| medium | 1331 | 41.2% |
| low | 836 | 25.9% |
| indeterminate | 805 | 24.9% |

## 构念效度（final_zone vs test_result）

- 方向：**correct**
- 单调梯度：✅
- green 阳性率：14.0%
- yellow 阳性率：15.1%
- red 阳性率：18.0%

## 参考子集合理性

- 参考子集 N：903
- green%：69.2%
- red%：10.2%
- 参考合理：✅

## Red 区来源拆分（red_source）

| 来源 | N | % |
|---|---|---|
| red_override | 220 | 6.8% |
| red_phenotype | 741 | 22.9% |

## 验收判定：**Accept**

- release_status：**Accept**
- 原因：所有验收标准满足

## Outcome Risk 分布

- Mean prob：0.145
- Median prob：0.142