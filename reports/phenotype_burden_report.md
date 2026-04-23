# Phenotype Burden Report (Stage 1B)

- 总样本数：3232
- 参考分位切点：low_cut=0.2500, high_cut=0.5000

## Zone 分布

| Zone | N | % |
|---|---|---|
| green | 999 | 30.9% |
| yellow | 873 | 27.0% |
| red | 1323 | 40.9% |
| missing/NaN | 37 | 1.1% |

## 变量 Burden 分布（全量均值 ± std）

| 变量 | 域 | 方向 | Burden 均值 | Burden std | 覆盖率 |
|---|---|---|---|---|---|
| vo2_peak | reserve | higher_better | 0.489 | 0.457 | 98.9% |
| vo2_peak_pct_pred | reserve | higher_better | 0.451 | 0.474 | 98.5% |
| vt1_vo2 | reserve | higher_better | 0.395 | 0.430 | 97.8% |
| o2_pulse_peak | reserve | higher_better | 0.374 | 0.438 | 98.8% |
| mets_peak | reserve | higher_better | 0.488 | 0.456 | 98.9% |
| ve_vco2_slope | ventilatory | higher_worse | 0.384 | 0.461 | 98.7% |
| oues | ventilatory | higher_better | 0.409 | 0.435 | 98.5% |

## P_lab 分布统计

- Mean ± std：0.4182 ± 0.3122
- Median：0.3750
- Min/Max：0.0000 / 1.0000
- P25/P75：0.1250 / 0.6875

## 构念效度（phenotype_zone vs test_result 阳性率）

| phenotype_zone | N | test_result 阳性率 |
|---|---|---|
| green | 999 | 15.5% |
| yellow | 873 | 14.5% |
| red | 1323 | 14.1% |