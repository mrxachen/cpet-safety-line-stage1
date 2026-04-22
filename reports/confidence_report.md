# Confidence Engine Report (Stage 1B)

- 总样本数：3232
- High confidence：2397 (74.2%)
- Medium confidence：774 (23.9%)
- Low confidence：61 (1.9%)
- Indeterminate（低置信度覆盖为 yellow_gray）：60 (1.9%)

## final_zone 分布

| Zone | N | % |
|---|---|---|
| green | 807 | 25.0% |
| yellow | 933 | 28.9% |
| red | 1432 | 44.3% |
| yellow_gray | 60 | 1.9% |

## 置信度分数分布

- Mean ± std：0.747 ± 0.062
- Median：0.775
- P25/P75：0.700 / 0.775

## 高置信度样本中的 final_zone 梯度（对比低置信度）

| confidence_label | green% | yellow% | red% | indeterminate% |
|---|---|---|---|---|
| high | 29.7% | 31.2% | 39.2% | 0.0% |
| medium | 12.4% | 24.0% | 63.6% | 0.0% |
| low | 0.0% | 0.0% | 1.6% | 98.4% |

## 高置信度样本 final_zone vs test_result 阳性率

| Zone | N | test_result 阳性率 |
|---|---|---|
| green（高置信） | 711 | 14.5% |
| yellow（高置信） | 747 | 15.3% |
| red（高置信） | 939 | 14.9% |