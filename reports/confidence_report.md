# Confidence Engine Report (Stage 1B)

- 总样本数：3232
- High confidence：1065 (33.0%)
- Medium confidence：1331 (41.2%)
- Low confidence：836 (25.9%)
- Indeterminate（低置信度覆盖为 yellow_gray）：805 (24.9%)

## final_zone 分布

| Zone | N | % |
|---|---|---|
| green | 637 | 19.7% |
| yellow | 829 | 25.6% |
| red | 961 | 29.7% |
| yellow_gray | 805 | 24.9% |

## 置信度分数分布

- Mean ± std：0.731 ± 0.128
- Median：0.725
- P25/P75：0.625 / 0.875

## 高置信度样本中的 final_zone 梯度（对比低置信度）

| confidence_label | green% | yellow% | red% | indeterminate% |
|---|---|---|---|---|
| high | 31.2% | 25.9% | 42.9% | 0.0% |
| medium | 22.9% | 41.5% | 35.5% | 0.0% |
| low | 0.0% | 0.0% | 3.7% | 96.3% |

## 高置信度样本 final_zone vs test_result 阳性率

| Zone | N | test_result 阳性率 |
|---|---|---|
| green（高置信） | 332 | 13.0% |
| yellow（高置信） | 276 | 14.9% |
| red（高置信） | 457 | 19.9% |