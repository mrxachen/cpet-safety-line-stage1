# 02｜算法设计与判定流程

这份文档只干一件事：把推荐方法写成可以编码的算法。

---

# 一、最终算法总览

## 输入
- demographics：age, sex, BMI, protocol_mode
- CPET summary：VO2peak, VT1 VO2, VE/VCO2 slope, OUES, O2 pulse peak, METs peak, HR indices
- instability signals：EIH/EHT, peak BP, O2 pulse trajectory, future ECG/termination fields
- validation only：test_result

## 中间层
1. 条件参考分位（q10/q25/q50/q75/q90）
2. 单变量 burden
3. Reserve burden
4. Ventilatory burden
5. phenotype score
6. phenotype zone
7. instability override
8. confidence score

## 输出
- final_zone
- confidence_label
- indeterminate_flag
- outcome_risk_prob（辅助）
- anomaly_flag（辅助）

---

# 二、核心算法设计

## 2.1 变量域定义

### Reserve 域
用于表示“运动储备/能力不足”

推荐字段：
- `vo2_peak` 或 `vo2_peak_pct_pred`
- `vt1_vo2` / `at_vo2`
- `o2_pulse_peak`
- `mets_peak`
- optional: `hrr_1min`
- optional: `hr_peak_pct_pred`

### Ventilatory 域
用于表示“通气效率/整合效率异常”

推荐字段：
- `ve_vco2_slope`
- `oues`
- optional: `petco2_at`
- optional: `ventilatory_reserve`

### Instability 域（不参与主体平均）
用于表示“测试中警报/不稳定”

推荐字段：
- `eih_status` / `eht_status`
- `bp_peak_sys`
- `bp_peak_dia`
- `o2_pulse_trajectory`
- optional future: `arrhythmia_flag`
- optional future: `st_depression_mm`
- optional future: `termination_reason`

---

## 2.2 条件参考分位建模

### 目标
对每个核心变量拟合条件分位：
- q10
- q25
- q50
- q75
- q90

### 特征
- age（样条）
- sex
- protocol_mode
- BMI
- 可选：age × sex

### 推荐算法
- `sklearn.QuantileRegressor`
- 配合 `SplineTransformer` 处理 age
- categorical 用 `OneHotEncoder`

### 为什么不是 OLS
因为你后面真正用的是“低于第 10/25 百分位”或“高于第 75/90 百分位”的判定。

---

# 三、单变量 burden 变换

## 3.1 高值更好（higher_better）
例如：
- VO2peak
- VT1 VO2
- O2 pulse peak
- OUES
- METs peak
- HRR

### 规则
- 若 `x >= q25` → burden = 0.0
- 若 `q10 <= x < q25` → burden = 0.5
- 若 `x < q10` → burden = 1.0

## 3.2 高值更差（higher_worse）
例如：
- VE/VCO2 slope
- 某些压力或不稳定连续量（如果进入主体）

### 规则
- 若 `x <= q75` → burden = 0.0
- 若 `q75 < x <= q90` → burden = 0.5
- 若 `x > q90` → burden = 1.0

## 3.3 缺失值
- 不把缺失硬编码成 0
- 不做简单均值填补后直接评分
- 缺失只在域内平均时跳过，但要单独影响 confidence

---

# 四、域内聚合

## 4.1 Reserve burden

令 Reserve 域可用 burden 集合为：
`R = {r1, r2, ..., rk}`

若 `k >= 2`：
`reserve_burden = mean(R)`

否则：
- 仍可计算，但标记 `reserve_domain_insufficient = True`
- 或者直接设为缺失，推荐后者更稳

## 4.2 Ventilatory burden

令 Ventilatory 域可用 burden 集合为：
`V = {v1, v2, ..., vm}`

若 `m >= 1`：
`vent_burden = mean(V)`

否则：
- 设为缺失
- 提高不确定性

---

# 五、主体 phenotype score

## 主公式
`p_lab = 0.5 * reserve_burden + 0.5 * vent_burden`

## 为什么此处允许 0.5 / 0.5
因为两个域都在描述“慢性表型偏离”，语义同层。

## 不要做的事
- 不要把 instability 也一起平均进去
- 不要用 `test_result` 学出来的权重定义主公式
- 不要把 `test_result` 的相关性拿来直接赋权

## 敏感性分析
补充材料中可加：
- `0.6 / 0.4`
- `0.4 / 0.6`
- PCA / factor loading 权重版

但主分析仍建议 0.5 / 0.5。

---

# 六、phenotype zone 切点

## 主切法
在 `reference_flag_strict` 子集上，查看 `p_lab` 的分布：

- `< P75` → phenotype green
- `P75 ~ P90` → phenotype yellow
- `> P90` → phenotype red

## 解释
这一步表示的是：
- green：仍处于参考正常波动内
- yellow：高于正常中上分位，需要关注
- red：显著高于正常尾部

## 备注
这一步不需要用 `test_result` 做切点。  
因为它回答的是“偏离正常的程度”，不是“医生报告阳性概率”。

---

# 七、instability override

## 7.1 severe flag

推荐 severe 规则（满足任一即可）：

### Rule S1
`eih_status == True`

### Rule S2
`bp_peak_sys > 220`

### Rule S3
`bp_peak_dia > 110`（若字段可用）

### Rule S4
`o2_pulse_trajectory in {"下降","晚期下降","运动终止前下降","持续平台"}`

### Rule S5（未来）
明确 arrhythmia / ischemia / early termination

## 7.2 mild flag

推荐 mild 规则（满足任一即可）：

### Rule M1
`200 < bp_peak_sys <= 220`

### Rule M2
`bp_peak_dia` 边界升高

### Rule M3
`effort_adequacy == uncertain`

### Rule M4
边界型 O2 pulse 异常

## 7.3 override 逻辑

```text
if severe_flag:
    final_zone_before_confidence = "red"
elif mild_flag and phenotype_zone == "green":
    final_zone_before_confidence = "yellow"
else:
    final_zone_before_confidence = phenotype_zone
```

### 重要原则
- severe flag 只允许升级，不允许降级
- instability 是透明规则，不走监督学习

---

# 八、confidence engine

## 8.1 四个分量

### completeness
`n_core_available / n_core_required`

推荐 required：
- Reserve 至少 2 项
- Ventilatory 至少 1 项
- instability 关键字段至少 1 项（BP 或 EIH）

### effort_score
- adequate = 1.0
- uncertain = 0.5
- inadequate = 0.0

### anchor_agreement
比较：
- 外部中国 VO2peak 参考分级
- 内部参考分级

评分：
- same = 1.0
- adjacent = 0.5
- discordant = 0.0

### validation_agreement
比较：
- final_zone_before_confidence
- outcome model risk tertile

评分：
- same direction = 1.0
- adjacent = 0.5
- opposite = 0.0
- 若 outcome model 不可用 = 0.5（中性）

## 8.2 总分公式
`confidence = 0.40*completeness + 0.15*effort + 0.20*anchor_agreement + 0.25*validation_agreement`

## 8.3 置信度标签
- `>= 0.75` → high
- `0.60–0.75` → medium
- `< 0.60` → low

## 8.4 不确定输出
推荐规则：

```text
if severe_flag:
    final_zone = "red"
    indeterminate = False
elif confidence < 0.60:
    final_zone = "yellow_gray"
    indeterminate = True
else:
    final_zone = final_zone_before_confidence
    indeterminate = False
```

### 说明
这里的思想是：
- 危险信号不能被“低置信度”冲掉
- 但没有危险信号时，低置信度不应该硬判成绿或红

---

# 九、outcome-anchor model

## 推荐用途
只做验证器，不做主定义器。

## 标签
`test_result_bin = 1` if `test_result in {"阳性","可疑阳性"}` else 0

## 特征
- demographics
- history
- core summary-level CPET
- 不使用明显的文本解释字段或人工结论副本

## 主模型
- elastic net logistic（主）
- LightGBM（辅）

## 评估
- nested CV
- AUC
- AUPRC
- Brier
- calibration intercept / slope
- calibration curve
- DCA

## 输出
- `outcome_risk_prob`
- `outcome_risk_tertile`

## 不要做的事
- 不要用 outcome model 的最优 Youden 切点直接定义 final zone
- 不要再把 outcome model 写成主方法

---

# 十、anomaly score

## 推荐定位
QC / atypical phenotype flag

## 推荐变量
用 reference-normalized 主体变量，不包含最终判定列。

## 方法
- robust Mahalanobis
- 或 isolation forest（补充）

## 输出
- `anomaly_score`
- `anomaly_flag`

## 用法
- 标记异常点
- 人工复核
- Stage II 优先抽样

---

# 十一、伪代码总流程

```python
# 1. 读入数据
df = load_curated_table()

# 2. 生成 reference subset
ref_df = build_reference_subset(df)

# 3. 拟合条件分位模型
ref_models = fit_reference_quantiles(
    df=ref_df,
    variables=core_reference_variables,
    covariates=["age", "sex", "protocol_mode", "bmi"],
)

# 4. 预测每位受试者的 q10/q25/q50/q75/q90
quantiles = predict_reference_quantiles(ref_models, df)

# 5. 计算单变量 burden
burden_df = compute_variable_burdens(df, quantiles, variable_specs)

# 6. 计算两个主体域
domain_df = aggregate_domains(burden_df)

# 7. 计算主体分数
domain_df["p_lab"] = 0.5 * domain_df["reserve_burden"] + 0.5 * domain_df["vent_burden"]

# 8. 用 reference subset 上 p_lab 的 P75/P90 得 phenotype zone
cutpoints = estimate_phenotype_cutpoints(domain_df.loc[ref_df.index, "p_lab"])
domain_df["phenotype_zone"] = assign_zone(domain_df["p_lab"], cutpoints)

# 9. instability override
instability_df = evaluate_instability_rules(df, rules_cfg)
zone_df = apply_override(domain_df["phenotype_zone"], instability_df)

# 10. outcome model（验证器）
outcome_pred = train_and_predict_outcome_model(df)

# 11. confidence
confidence_df = compute_confidence(
    df=df,
    burden_df=burden_df,
    zone_df=zone_df,
    outcome_pred=outcome_pred,
)

# 12. final zone
final_df = finalize_zone(zone_df, confidence_df)

# 13. anomaly flag
anomaly_df = run_anomaly_audit(burden_df)

# 14. 合并输出
result = combine_all_outputs(df, burden_df, domain_df, instability_df, confidence_df, anomaly_df)
```

---

# 十二、最推荐的最终输出列

```text
patient_id
reserve_burden
vent_burden
p_lab
phenotype_zone
instability_mild
instability_severe
final_zone_before_confidence
confidence_score
confidence_label
indeterminate_flag
final_zone
outcome_risk_prob
outcome_risk_tertile
anomaly_score
anomaly_flag
```

---

# 十三、你在论文里如何解释这个算法

最简洁的解释是：

1. 先根据 reference subset 建立条件参考分位  
2. 再把多个 summary-level 指标转成方向一致的表型负担  
3. 再组合成连续表型分数  
4. 再用测试中的警报条件覆盖  
5. 最后显式输出置信度和不确定区

这样叙事非常稳，也很符合当前数据实际。
