# Phenotype Burden Report (Stage 1B)

- 总样本数：3232
- 参考分位切点：low_cut=0.2500, high_cut=0.5000

## Zone 分布

| Zone | N | % |
|---|---|---|
| green | 992 | 30.7% |
| yellow | 877 | 27.1% |
| red | 1326 | 41.0% |
| missing/NaN | 37 | 1.1% |

## 变量 Burden 分布（全量均值 ± std）

| 变量 | 域 | 方向 | Burden 均值 | Burden std | 覆盖率 |
|---|---|---|---|---|---|
| vo2_peak | reserve | higher_better | 0.491 | 0.457 | 98.9% |
| vo2_peak_pct_pred | reserve | higher_better | 0.451 | 0.472 | 98.5% |
| vt1_vo2 | reserve | higher_better | 0.403 | 0.436 | 97.8% |
| o2_pulse_peak | reserve | higher_better | 0.375 | 0.438 | 98.8% |
| mets_peak | reserve | higher_better | 0.493 | 0.457 | 98.9% |
| ve_vco2_slope | ventilatory | higher_worse | 0.385 | 0.462 | 98.7% |
| oues | ventilatory | higher_better | 0.410 | 0.437 | 98.5% |

## P_lab 分布统计

- Mean ± std：0.4202 ± 0.3133
- Median：0.3750
- Min/Max：0.0000 / 1.0000
- P25/P75：0.1250 / 0.7000

## 构念效度（phenotype_zone vs test_result 阳性率）

| phenotype_zone | N | test_result 阳性率 |
|---|---|---|
| green | 992 | 15.2% |
| yellow | 877 | 14.8% |
| red | 1326 | 14.1% |