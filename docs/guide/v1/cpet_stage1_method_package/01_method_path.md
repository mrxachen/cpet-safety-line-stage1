# 01｜完整方法路径

这份文档回答五个问题：

1. Stage I 到底要做成什么？
2. 从原始数据到最终区间，顺序怎么排？
3. 每一步用什么方法？
4. 每一步的输出文件是什么？
5. 什么地方最容易再次掉回旧坑？

---

# 一、先把研究问题改写正确

## 当前问题写法（不推荐）

“根据 summary-level CPET 指标，把患者分成 Green / Yellow / Red，并训练模型预测该分区。”

这个写法的问题是：
- 容易回到标签循环依赖
- 容易让读者以为你要做临床部署级预测器
- 容易把 `test_result`、规则阈值和参考偏离混成一个东西

## 推荐写法

“在 summary-level CPET 条件下，构建一个用于实验室解释的运动安全表型原型，其输出由表型负担、不稳定覆盖规则和不确定性三部分组成，并以 `test_result` 作为外部锚定进行构念验证。”

---

# 二、Stage I 的最终产品应该是什么

不是单一模型，不是单一标签，而是 5 个对象：

1. **reference package**  
   条件参考区间与 reference-normal subset 定义

2. **phenotype burden score (`P_lab`)**  
   表示“与正常参考的偏离程度”

3. **instability flags (`I_flag`)**  
   表示“测试过程中是否出现安全相关警报条件”

4. **final zone (`Z_final`)**  
   将 phenotype zone 与 instability override 合成后的最终区间

5. **confidence / indeterminate (`C_final`)**  
   明确告诉临床和研究者：哪些样本可高信度解释，哪些不能

---

# 三、从头到尾的推荐执行顺序

下面的顺序很重要。不要再像旧主线那样“先定标签，再找模型去学标签”。

## Step 0：冻结旧结果，建立基线版本

### 目标
保留当前仓库结果作为 legacy baseline，方便论文和补充材料对照。

### 需要做什么
- 冻结当前 `zone_engine_v2` 结果
- 冻结 `label_rules_v2/v3` 结果
- 冻结 Phase G 三个方法的现有输出
- 写入一个 `legacy_baseline_manifest.json`

### 输出
- `reports/legacy/*.md`
- `data/labels/legacy_*.parquet`
- `reports/legacy_manifest.json`

### 为什么必须先做
因为你后面所有新结果都需要一个清晰对照。否则论文会越来越难写。

---

## Step 1：重做数据字典与变量分层

### 目标
把所有字段分成“表型主体”“不稳定信号”“验证变量”“禁用变量”四类。

### 推荐分层

#### A. 表型主体变量（进入 phenotype score）
- `vo2_peak`
- `vo2_peak_pct_pred`（注意：只用于 phenotype，不再用于监督标签）
- `vt1_vo2` / `at_vo2`
- `o2_pulse_peak`
- `mets_peak`
- `ve_vco2_slope`
- `oues`
- `hr_peak_pct_pred`（如果可稳定推导）
- `hrr_1min`（如果有）

#### B. 不稳定覆盖变量（进入 override）
- `eih_status` / `eht_status`（以你仓库当前定义为准）
- `bp_peak_sys`
- `bp_peak_dia`（若可用）
- `o2_pulse_trajectory`
- `arrhythmia_flag`（未来字段）
- `st_depression_mm`（未来字段）
- `termination_reason`（未来字段）
- `test_terminated_early`（未来字段）

#### C. 验证变量（不直接定义 final zone）
- `test_result`
- cohort group
- 历史病史组别
- later follow-up outcome（Stage II/III 以后）

#### D. 明确禁用变量
- 医生已经写好的结论性字段
- 任何直接把 final zone 翻译出来的列
- 任何 after-the-fact 的人工标签副本

### 输出
- `docs/data_dictionary/stage1b_variable_roles.md`
- `configs/data/variable_roles_stage1b.yaml`

---

## Step 2：重建 reference-normal subset

### 目标
建立一个真正“可作参考”的院内子集，而不是简单拿 CTRL 全体当正常。

### 推荐原则

#### 必需条件
- 无明显异常 `test_result`
- 无严重不稳定信号
- 努力度达到最低要求（当前可用 HR 代理；未来补 RER）
- 无明显数据质量问题
- 处于当前数据库中相对“低风险解释窗口”

#### 建议分成两个版本
- `reference_flag_strict`
- `reference_flag_wide`

### 为什么要双版本
因为 strict 太干净会导致样本量不足，wide 太松会污染正常参考。  
双版本让你可以做敏感性分析。

### 输出
- `data/cohort/reference_subset_stage1b.parquet`
- `reports/reference_subset_audit.md`

---

## Step 3：建立 dual-anchor reference system

这是整套方案最关键的一步。

## 3A. 外部锚点（external anchor）

### 目标
把 VO2peak 的解释锚定到中国更合适的人群参考，而不是仅依赖欧美公式。

### 推荐优先级
1. PUTH 2025 cycle equation
2. Wang 2022 中国社区成人 cycle 参考值
3. X-ET 2021 中国成人医院项目参考值
4. treadmill 数据仅用于 treadmill 子集 sanity check
5. FRIEND 作为国际对照，不作中国主锚点

### 原则
- cycle 数据只跟 cycle 参考比
- treadmill 数据只跟 treadmill 参考比
- 不要混用测试方式

## 3B. 内部锚点（internal anchor）

### 目标
在 `reference_flag_strict` 或 `reference_flag_wide` 上构建本实验室的条件参考区间。

### 为什么内部锚点仍然必要
因为外部公式主要能覆盖 VO2peak；你还有 OUES、VE/VCO2 slope、O2 pulse 等变量需要本地化解释。

---

## Step 4：参考建模方法——不用再只盯 OLS 均值

### 不推荐只做的事
- 单纯 OLS 平均预测 + R² 最大化
- 只用一个参考方程解释一切
- 把 R² 当 Stage I 成败标准

### 推荐做法
对每个核心变量建立**条件分位模型**，至少输出：
- q10
- q25
- q50
- q75
- q90

### 自变量建议
- age（建议样条）
- sex
- protocol_mode（cycle/treadmill）
- BMI
- 必要时加 age × sex

### 为什么选分位模型而不是只做 OLS
因为你后面真正需要的是：
- “这个人是否低于正常第 10 / 25 百分位”
- “这个人是否高于正常第 75 / 90 百分位”

而不是单纯“离均值差多少”。

### 输出
- `outputs/reference_models/*.joblib`
- `reports/reference_quantiles_report.md`
- `data/features/reference_quantiles_stage1b.parquet`

---

## Step 5：把变量转换成“方向一致的偏离负担”

### 目标
把不同量纲、不同方向的 CPET 指标统一成同一种语言。

### 核心思想
所有变量都转换成一个 0~1 的 **burden** 值：
- 0 = 更接近正常
- 1 = 明显偏离正常

### 推荐规则

#### 对“越高越好”的变量
如：
- VO2peak
- VT1 VO2
- O2 pulse peak
- OUES
- METs peak
- HRR（如果定义为恢复越高越好）

定义：
- 若值 ≥ q25：burden = 0
- 若 q10 ≤ 值 < q25：burden = 0.5
- 若值 < q10：burden = 1

#### 对“越高越差”的变量
如：
- VE/VCO2 slope
- peak SBP（只在 instability 中直接使用；若进入表型只做辅助）
- certain abnormal trajectory burden

定义：
- 若值 ≤ q75：burden = 0
- 若 q75 < 值 ≤ q90：burden = 0.5
- 若值 > q90：burden = 1

### 好处
- 很容易解释
- 对偏态分布更鲁棒
- 不需要假设完全正态
- 可以自然做缺失容忍

---

## Step 6：构建两个主体域，而不是三个同权轴

## 为什么改成两个主体域
原 R/T/I 的问题不在于“三轴”这个想法，而在于：
- R 和 T 更多是慢性能力/效率表型
- I 更像即时安全警报

所以我建议把主体改成两个域：

1. **Reserve burden（R-burden）**
2. **Ventilatory burden（V-burden）**

然后把 instability 从主体移出去，作为覆盖规则。

## Reserve burden 推荐变量
- VO2peak 或 VO2peak%pred
- VT1 VO2 / AT VO2
- O2 pulse peak
- METs peak 或 peak work
- 可选：HRR / HRpeak%pred

## Ventilatory burden 推荐变量
- VE/VCO2 slope
- OUES
- 可选：PETCO2 / VE/VCO2 at AT（如果未来有）

### 域内聚合
每个域对可用 burden 变量取平均值。

### 缺失规则
- Reserve 域至少需要 2 个变量
- Ventilatory 域至少需要 1 个变量
- 不满足则降置信度，不直接硬判为正常

### 输出
- `reserve_burden`
- `vent_burden`

---

## Step 7：构建 phenotype score（主体分数）

### 主体分数定义
`P_lab = 0.5 * reserve_burden + 0.5 * vent_burden`

### 为什么此处可以 0.5 / 0.5
因为两个主体域语义接近，都是“慢性表型负担”；与此前把 instability 一起平均不同。

### 还要做的敏感性分析
- 0.6 / 0.4
- 0.4 / 0.6
- PCA/factor-loading 权重（只做补充分析，不作主分析）

### 输出
- `p_lab_continuous`

---

## Step 8：用 reference subset 的 composite 分布定义 phenotype zone

### 推荐主方法
在 `reference_flag_strict` 子集上看 `p_lab_continuous` 的分布：
- `< P75` → phenotype green
- `P75 ~ P90` → phenotype yellow
- `> P90` → phenotype red

### 为什么这是合理主线
因为这一步回答的是：
> “这名受试者相对参考正常人群偏离到什么程度？”

这和 `test_result` 是不同构念，但构念清晰。

### 需要同时做的验证
在全样本中检验 phenotype zone 与 `test_result` 的梯度关系。

### 输出
- `phenotype_zone`
- `phenotype_cutpoints.json`

---

## Step 9：构建 instability override

### 目标
把真正的即时安全信号单独处理，而不是被均值稀释。

## 9A. severe instability
满足任一条件就触发 severe：
- `eih_status == True`（按你仓库现有 EIH/EHT 定义）
- `bp_peak_sys > 220`
- `bp_peak_dia > 110`（若有）
- 高危 O2 pulse trajectory
- future: arrhythmia / ischemia / early termination

## 9B. mild instability
满足任一条件触发 mild：
- `200 < bp_peak_sys <= 220`
- 努力度不充分但不是明确无效
- 边界型异常 trajectory
- 关键安全变量缺失（作为 mild 或 confidence penalty，二选一，建议后者）

## 9C. override 规则
- phenotype green + severe → red
- phenotype yellow + severe → red
- phenotype green + mild → yellow
- phenotype red 不因 mild 被降级
- 任何 severe 都不允许被 outcome model 拉回 green

### 输出
- `instability_severe`
- `instability_mild`
- `final_zone_before_confidence`

---

## Step 10：构建 confidence engine

这是当前项目最应该认真做的地方。

### 为什么必须做
因为你自己的 Phase G 已经证明：
- 多定义一致性不高
- 很大比例样本不确定
- summary-level 数据先天信息不足

所以不确定性不是“丢人的结果”，而是 Stage I 的核心输出之一。

## 推荐置信度四要素

### A. completeness
核心变量覆盖率：
- Reserve 域变量是否足够
- Ventilatory 域变量是否足够
- BP / instability 信息是否完整

### B. effort adequacy
- 当前用 HR 代理
- 未来补 RER 后升级
- effort 不足不必剔除，但要降 confidence

### C. anchor agreement
- 外部 VO2peak 参考解释 vs 内部分位解释是否一致
- 若一致：高分
- 若相邻：中分
- 若冲突：低分

### D. validation agreement
- `test_result` 风险分位（来自 outcome model）与 final zone 是否同向
- 这里只作置信度加权，不反向定义最终 zone

## 置信度评分
推荐：
`confidence = 0.40*completeness + 0.15*effort + 0.20*anchor_agreement + 0.25*validation_agreement`

## 置信度分层
- ≥ 0.75：high
- 0.60–0.75：medium
- < 0.60：low

## 最终处理
- severe instability 一律保留红色，但置信度可标为 low / medium
- 若无 severe，且 confidence < 0.60，则输出 `yellow_gray` 或 `indeterminate`

### 输出
- `confidence_score`
- `confidence_label`
- `indeterminate_flag`
- `final_zone`

---

## Step 11：把 outcome-anchor model 降级为“验证器”，不是“主标签制造器”

### 当前问题
你原来把它当作 Phase G 的补救主线，希望 AUC > 0.70。  
这个期待不适合当前数据现实。

### 新定位
它的作用变成三件事：

1. 检验 final zone 是否与临床结局代理同向
2. 提供 validation_agreement 给 confidence engine
3. 作为补充材料里的辅助模型，而不是主结果

### 推荐模型
- 主：elastic net logistic
- 辅：LightGBM / XGBoost
- 不建议只留 boosting，不留透明模型

### 推荐评估
- AUC
- AUPRC
- Brier score
- calibration intercept / slope
- calibration plot
- decision curve
- decile risk plot

### 现实预期
AUC 可能仍然只有 0.55~0.65。  
这不代表主方法失败，只代表 `test_result` 包含 summary-level 之外的信息。

### 输出
- `outcome_risk_prob`
- `outcome_risk_decile`
- `reports/outcome_validation_report.md`

---

## Step 12：异常评分只做 QC / atypical phenotype flag

### 推荐改法
不要再把 Mahalanobis 当主风险器，而是：
- 用 robust Mahalanobis
- 用在 reference-normalized 核心变量上
- 只标记极端偏离样本

### 作用
- 发现异常输入
- 发现不典型表型
- 作为 Stage II 重点样本池

### 输出
- `anomaly_score`
- `anomaly_flag`
- `reports/anomaly_audit.md`

---

## Step 13：形成最终的四层结果表

最终每个受试者一行，至少应有这些列：

- `reserve_burden`
- `vent_burden`
- `p_lab_continuous`
- `phenotype_zone`
- `instability_mild`
- `instability_severe`
- `final_zone_before_confidence`
- `confidence_score`
- `confidence_label`
- `indeterminate_flag`
- `final_zone`
- `outcome_risk_prob`
- `anomaly_flag`

### 这样做的最大价值
同一个受试者，你不再只能给一个“红黄绿”答案，而是能说清：
- 他为什么被分到这个区
- 是因为慢性表型差，还是因为测试中出现警报
- 这次判断有多稳
- 是否需要 Stage II 原始数据补充

---

# 四、统计验证顺序

## 1. 描述性与构念效度
看 final zone 是否与以下方向一致：
- VO2peak：green > yellow > red
- VE/VCO2 slope：green < yellow < red
- OUES：green > yellow > red
- `test_result` 阳性率：green < yellow < red

## 2. 参考合理性
在 strict reference 子集中：
- red 比例应该很低
- green 应占多数
- 若 red 很高，说明参考集污染或阈值建模有问题

## 3. 分层稳健性
检查：
- sex
- age group
- protocol mode
- no-BP version vs full version
- strict vs wide reference

## 4. 不确定性分析
报告：
- high / medium / low confidence 分布
- indeterminate 比例
- 高置信度样本中的梯度是否更清楚

## 5. 辅助验证
- outcome model calibration
- anomaly flag 分布
- 与 legacy v2/v3 对比

---

# 五、你最容易再次犯的错

## 错 1：又想把 `test_result` 拿回来做主切点
不要这样做。  
可以验证，不要主导定义。

## 错 2：又把 EIH/EHT 当成监督标签的一部分
EIH/EHT 更适合作为 override 规则，而不是让 ML 去“学会”它。

## 错 3：又把 Mahalanobis 当风险评分
它是偏离量，不是风险方向。

## 错 4：又想证明 Stage I 能做出高精度预测器
Stage I 的贡献不是高精度，而是构念拆分和方法学封版。

## 错 5：又试图让所有人都被明确分成绿黄红
不需要。  
不确定区本来就是你现在最有价值的发现之一。

---

# 六、最终一句话方法摘要（建议写进论文）

“我们将 summary-level CPET 的 Stage I 输出重新定义为：以中国/本地双锚点参考校准的连续表型负担分数为主体，以测试中的不稳定信号作为覆盖规则，并显式输出置信度与不确定区；`test_result` 仅用于外部锚定与构念验证，而不再作为主标签生成机制。”
