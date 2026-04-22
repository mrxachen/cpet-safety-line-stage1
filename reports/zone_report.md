# 标签分布报告

## P0 运动安全事件代理

- 总样本量: 3206
- P0 阳性: 727 (22.7%)

### P0 触发器分布

| 触发器 | 阳性数 | 占比 |
|---|---|---|
| EIH（运动高血压） | 610 | 19.0% |
| VO2peak < 50%pred | 133 | 4.1% |
| BP峰值 > 220 mmHg | 146 | 4.6% |

## P1 实验室安全区

| 区域 | 样本量 | 占比 |
|---|---|---|
| 🟢 Green | 1289 | 40.2% |
| 🟡 Yellow | 1099 | 34.3% |
| 🔴 Red | 797 | 24.9% |
| NaN（全缺失）| 21 | 0.7% |

### P1 分区按队列分布

- **HTN+/EIH+** (N=277): green=0, yellow=0, red=275
- **HTN+/EIH-** (N=738): green=299, yellow=353, red=81
- **HTN-/EIH+** (N=333): green=0, yellow=0, red=324
- **HTN-/EIH-** (N=1858): green=990, yellow=746, red=117

## HR 努力度代理

- HR 充足（>= 85% HRmax_pred）: 2520 (78.6%)

## Inactive 规则（数据不可用）

- P0/arrhythmia_flag: 字段不存在于当前数据集
- P0/test_terminated_early: 字段不存在于当前数据集
- P0/st_depression_mm: 字段不存在于当前数据集
- P1/rer_peak: 字段不存在于当前数据集
- P1/nyha_class: 字段不存在于当前数据集