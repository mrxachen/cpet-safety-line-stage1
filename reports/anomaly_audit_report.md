# Anomaly Audit Report (Stage 1B)

- 总样本数：3232
- 使用变量：['vo2_peak', 've_vco2_slope', 'oues', 'o2_pulse_peak', 'mets_peak', 'vt1_vo2']
- 参考子集样本量：897
- 异常阈值（chi2 P97.5）：3.801
- 标记异常样本数：654 (20.2%)

## anomaly_score 分布

- Mean ± std：15.719 ± 390.197
- Median：2.778
- P75/P90/P95：3.577 / 4.713 / 5.837
- P97.5（阈值对应）：7.873

## 定位说明

异常表型（anomaly_flag=True）样本建议：
- 人工复核原始记录，排查数据录入错误
- 检查设备校准（尤其是气体分析仪）
- 作为 Stage II 原始数据分析的优先抽样池
- **不用于 final_zone 定义**（仅作 QC/atypical flag）