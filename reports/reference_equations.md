# 参考正常方程诊断报告

## vo2_peak
- 公式：`vo2_peak ~ age + C(sex) + age:C(sex)`
- N(参考子集)：968（男=479，女=489）
- R²：0.298
- 残差SD：6.331
- 含交互项：是
- 系数：
  - Intercept: 29.3758
  - C(sex)[T.M]: -4.0638
  - age: -0.0917
  - age:C(sex)[T.M]: 0.1828

## vo2_peak_pct_pred
- 公式：`vo2_peak_pct_pred ~ age + C(sex) + age:C(sex)`
- N(参考子集)：969（男=480，女=489）
- R²：0.013
- 残差SD：14.026
- 含交互项：是
- 系数：
  - Intercept: 116.9084
  - C(sex)[T.M]: -26.8596
  - age: -0.4469
  - age:C(sex)[T.M]: 0.3983

## hr_peak
- 公式：`hr_peak ~ age + C(sex) + age:C(sex)`
- N(参考子集)：966（男=478，女=488）
- R²：0.082
- 残差SD：17.494
- 含交互项：是
- 系数：
  - Intercept: 134.4765
  - C(sex)[T.M]: -6.7860
  - age: 0.2571
  - age:C(sex)[T.M]: 0.2476

## ve_vco2_slope
- 公式：`ve_vco2_slope ~ age + C(sex) + age:C(sex)`
- N(参考子集)：969（男=480，女=489）
- R²：0.040
- 残差SD：2.737
- 含交互项：是
- 系数：
  - Intercept: 30.5249
  - C(sex)[T.M]: -0.1173
  - age: -0.0673
  - age:C(sex)[T.M]: -0.0113

## o2_pulse_peak
- 公式：`o2_pulse_peak ~ age + C(sex) + age:C(sex)`
- N(参考子集)：968（男=479，女=489）
- R²：0.489
- 残差SD：2.632
- 含交互项：是
- 系数：
  - Intercept: 11.3719
  - C(sex)[T.M]: 1.1430
  - age: -0.0323
  - age:C(sex)[T.M]: 0.0596

## 汇总诊断表

| 变量 | N参考 | 公式 | R² | 残差SD | 含交互 |
|---|---|---|---|---|---|
| VO₂peak（mL/kg/min） | 968 | vo2_peak ~ age + C(sex) + age:C(sex) | 0.298 | 6.331 | 是 |
| VO₂peak%pred | 969 | vo2_peak_pct_pred ~ age + C(sex) + age:C(sex) | 0.013 | 14.026 | 是 |
| 峰值心率（bpm） | 966 | hr_peak ~ age + C(sex) + age:C(sex) | 0.082 | 17.494 | 是 |
| VE/VCO₂斜率 | 969 | ve_vco2_slope ~ age + C(sex) + age:C(sex) | 0.040 | 2.737 | 是 |
| O₂脉搏峰值（mL/beat） | 968 | o2_pulse_peak ~ age + C(sex) + age:C(sex) | 0.489 | 2.632 | 是 |