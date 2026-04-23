# Stratified Validation Report (Stage 1B)

5 组分层验证，剥离表型层/覆盖层/置信度层对构念效度的贡献。


### Group 1：表型负担层（全量 phenotype_zone）

_表型负担层（phenotype_zone，全量）_

- 分析样本量：3232
- 方向：**reversed**，单调梯度：❌

| Zone | N | test_result 阳性率 |
|---|---|---|
| green | 999 | 15.5% |
| yellow | 873 | 14.5% |
| red | 1323 | 14.1% |

### Group 2：Instability 覆盖层（severe 有无对比）

_Instability 覆盖层（severe vs non-severe）_

| 子组 | N | test_result 阳性率 |
|---|---|---|
| Severe instability | 220 | 20.0% |
| Non-severe | 3012 | 14.1% |

- 方向：**correct**

### Group 3：最终分区（final_zone，主要报告）

_最终分区（final_zone，含 instability 覆盖）_

- 分析样本量：3232
- 方向：**correct**，单调梯度：✅

| Zone | N | test_result 阳性率 |
|---|---|---|
| green | 637 | 14.0% |
| yellow | 829 | 15.1% |
| red | 961 | 18.0% |

### Group 4：高置信度子集

_高置信度子集（n=1065）_

- 分析样本量：1065
- 方向：**correct**，单调梯度：✅

| Zone | N | test_result 阳性率 |
|---|---|---|
| green | 332 | 13.0% |
| yellow | 276 | 14.9% |
| red | 457 | 19.9% |

### Group 5：纯表型层（去掉 severe override）

_纯表型层（去掉 severe override，n=3012）_

- 分析样本量：3012
- 方向：**reversed**，单调梯度：❌

| Zone | N | test_result 阳性率 |
|---|---|---|
| green | 935 | 15.6% |
| yellow | 814 | 13.6% |
| red | 1226 | 13.6% |

## 汇总对比

| 分析层 | 样本量 | 方向 | 单调 |
|---|---|---|---|
| 表型层（全量） | 3232 | reversed | ❌ |
| 最终分区（整体） | 3232 | correct | ✅ |
| 高置信度子集 | 1065 | correct | ✅ |
| 纯表型层（无override） | 3012 | reversed | ❌ |