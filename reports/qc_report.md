# CPET Stage I — QC 报告

> 生成时间：2026-04-15 14:37
> 数据规模：3232 行

---

## 1. 全局概览

| 指标 | 数值 |
|---|---|
| 总行数 | 3232 |
| 拒绝行数（关键字段缺失 >50%） | 26 |
| 范围越界行数 | 58 |
| 逻辑违规行数 | 7 |
| 重复记录行数 | 0 |
| IQR 异常值行数 | 35 |
| 努力度充分行数 | 0 (0.0%) |

## 2. 分组概览

| 分组 | 行数 | 拒绝 | 范围违规 | 逻辑违规 | 异常值 | 努力度充分 |
|---|---|---|---|---|---|---|
| CTRL | 1858 | 0 | 31 | 2 | 21 | 0 |
| EHT_ONLY | 359 | 26 | 8 | 3 | 6 | 0 |
| HTN_HISTORY_NO_EHT | 738 | 0 | 14 | 2 | 5 | 0 |
| HTN_HISTORY_WITH_EHT | 277 | 0 | 5 | 0 | 3 | 0 |

## 3. 关键字段缺失率

| 字段 | CTRL | EHT_ONLY | HTN_HISTORY_NO_EHT | HTN_HISTORY_WITH_EHT | 全样本 |
|---|---|---|---|---|---|
| vo2_peak | 0.0% | 9.8% | 0.0% | 0.7% | 1.1% |
| hr_peak | 0.1% | 9.8% | 0.0% | 0.7% | 1.2% |
| vt1_vo2 | 0.7% | 10.9% | 2.0% | 2.2% | 2.2% |
| ve_vco2_slope | N/A | N/A | N/A | N/A | 1.3% |
| o2_pulse_peak | N/A | N/A | N/A | N/A | 1.2% |

## 4. 范围越界字段

| 字段（范围标志） | 越界行数 |
|---|---|
| range_exercise_frequency_per_week | 14 |
| range_hr_peak | 11 |
| range_mets_peak | 7 |
| range_protocol_ramp_watts | 6 |
| range_vt1_vo2_abs | 6 |
| range_ve_vco2_slope | 6 |
| range_vo2_peak | 3 |
| range_exercise_duration_min | 3 |
| range_quit_smoking_months | 1 |
| range_smoking_years | 1 |
| range_htn_years | 1 |
| range_smoking_daily_amount | 1 |

## 5. 逻辑一致性检查

| 规则 | 违规行数 |
|---|---|
| logic_vt1_abs_lt_peak_abs | 6 |
| logic_vt1_lt_peak | 2 |

## 6. 重复记录

未发现重复记录。

## 7. IQR 异常值

| 字段（异常值标志） | 异常行数 |
|---|---|
| outlier_vo2_peak | 12 |
| outlier_hr_peak | 11 |
| outlier_o2_pulse_peak | 10 |
| outlier_ve_vco2_slope | 7 |
| outlier_bp_peak_sys | 3 |

## 8. 努力度充分性（RER ≥ 1.05）

- 全样本努力度充分：**0 / 3232（0.0%）**

| 分组 | 行数 | 努力度充分 | 百分比 |
|---|---|---|---|
| CTRL | 1858 | 0 | 0.0% |
| EHT_ONLY | 359 | 0 | 0.0% |
| HTN_HISTORY_NO_EHT | 738 | 0 | 0.0% |
| HTN_HISTORY_WITH_EHT | 277 | 0 | 0.0% |

---

## 9. EHT_ONLY 组专项诊断（仅运动高血压）

> 此组为本研究核心暴露组，特殊关注其 CPET 安全指标分布。

**EHT_ONLY 组 n = 359**

### 9.1 关注字段描述统计

| 字段 | 非缺失数 | 均值 | 中位数 | P25 | P75 |
|---|---|---|---|---|---|
| bp_peak_sys | 229 | 216.62 | 212.00 | 200.00 | 223.00 |
| vo2_peak | 324 | 25.34 | 23.55 | 19.30 | 29.02 |
| hr_peak | 324 | 155.40 | 158.00 | 144.75 | 170.00 |
| ve_vco2_slope | 324 | 31.94 | 27.40 | 24.35 | 29.96 |
| o2_pulse_trajectory | 0 | — | — | — | — |

### 9.2 运动高血压相关标志


### 9.3 EHT_ONLY vs CTRL 关键指标对比

| 字段 | EHT_ONLY 中位数 | CTRL 中位数 |
|---|---|---|
| vo2_peak | 23.55 | 23.20 |
| hr_peak | 158.00 | 154.00 |
| ve_vco2_slope | 27.40 | 26.74 |

### 9.4 EHT_ONLY QC 摘要

- 总行数: 359
- 拒绝行数: 26
- 范围越界: 8
- 逻辑违规: 3
- 异常值: 6
- 努力度充分: 0

---

*本报告由 cpet_stage1 QC 管线自动生成。详细 flags 见 `data/curated/qc_flags.parquet`。*
