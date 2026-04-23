# Sensitivity Analysis Report (Stage 1B v2.7.0)

5 组敏感性分析，评估关键设计选择对结果稳健性的影响。

## Baseline（主要分析）

- 总样本量：3232
- 方向：**correct**
| Zone | N | % |
|---|---|---|
| green | 637 | 19.7% |
| yellow | 829 | 25.6% |
| red | 961 | 29.7% |
| yellow_gray | 805 | 24.9% |

## SA-1：Reference 设计敏感性

- 当前设计：不排除 test_result（v2.7.0 后）
- 先前设计：排除 test_result 阳性（v2.6.x 及之前）
- Strict reference N：N/A
- Zone 方向：**correct**

## SA-2：Phenotype Cut 敏感性

- current (P75/P90)：Low=0.688, High=0.875
- alternative (P80/P95)：Low=0.75, High=1.0

| Zone | P75/P90 (%) | P80/P95 (%) |
|---|---|---|
| green | 74.1% | 78.1% |
| yellow | 15.3% | 16.8% |
| red | 10.6% | 5.1% |

## SA-3：置信度阈值敏感性

- 当前阈值：0.8
- 先前阈值：0.75

| 阈值 | High% |
|---|---|
| high@0.7 | 71.4 |
| high@0.75 | 39.3 |
| high@0.8 | 33.0 |
| high@0.85 | 31.5 |
| high@0.80_both_domains | N/A（无样本有双域数据） |

- 双域均有非中性值样本：0
- 备注：v2.7.0 阈值从 0.75 升至 0.80，预期 high% 下降（从 74.2% 至 45-60%）

## SA-4：Red 语义拆分

- Red 总计：961
- red_override（instability severe 触发）：220 (22.9%)
- red_phenotype（表型负担 P90 触发）：741 (77.1%)

## SA-5：Outcome-Anchor 修复摘要

- 问题：solver=saga + l1_ratio=0.5 但无 penalty='elasticnet' → 实际为纯 L2
- 修复：添加 penalty='elasticnet' 参数
- 预期效果：calibration slope 预期从 -0.055 向 1.0 改善
- 备注：重跑 make stage1b 后，outcome_anchor_report.md 将包含新数值