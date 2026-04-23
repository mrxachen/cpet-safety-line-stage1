# 05｜论文改写蓝图

目标：把论文从“想做预测模型但性能一般”改成“清楚界定方法学边界的安全表型原型”。

---

# 一、题目怎么改

## 当前题目问题
当前题目仍然把重点放在：
- R/T/I 三轴框架
- 数据驱动安全区
- 阈值校准

但没有充分体现：
- 不稳定覆盖规则与主体表型的分离
- 不确定性输出
- prototype 而不是 prediction tool

## 推荐题目 1（最稳）
**基于汇总级心肺运动试验的运动安全实验室表型原型构建：双锚点参考归一化、不稳定覆盖规则与不确定性输出**

## 推荐题目 2（更临床）
**老年心血管患者汇总级 CPET 运动安全表型原型：参考偏离分层、测试中不稳定覆盖与置信度评估**

## 推荐题目 3（英文可对照）
**A summary-level CPET laboratory prototype for exercise safety phenotyping in older cardiovascular patients: dual-anchor reference calibration, instability override, and uncertainty-aware stratification**

---

# 二、摘要应该怎么改

## 结构建议

### 背景
说明：
- CPET 在运动处方与安全评估中重要
- summary-level 数据条件下，传统直接预测安全区容易混合不同构念

### 目的
改成：
- 建立一个 summary-level CPET 的实验室安全表型原型
- 显式区分表型负担、不稳定信号与不确定性
- 用 `test_result` 做外部锚定验证

### 方法
重点写：
1. reference-normal subset
2. 中国/本地 dual-anchor reference
3. condition quantile models
4. phenotype burden score
5. instability override
6. confidence engine
7. outcome-anchor validation

### 结果
不要把 AUC 写成 headline。  
应该先写：
- 参考建模与分位框架可稳定建立
- final zone 在 `test_result` 上有方向性梯度
- high-confidence subset 呈现更清晰分层
- 仍有一定比例 indeterminate，提示 Stage II 需要原始数据

### 结论
结论不要说：
- “可直接临床应用”
- “可高精度预测”

而应说：
- “提供了一个可复现的 summary-level CPET 原型”
- “明确了 Stage I 的有效边界”
- “为 Stage II 原始数据整合提供了优先方向”

---

# 三、引言怎么重写

## 3.1 保留的内容
- CPET 在运动安全/处方中的重要性
- 老年心血管患者对安全边界评估的需求
- 中国本地参考值不足的问题

## 3.2 必须新增的内容
### 缺口 1
现有研究常将慢性运动能力下降与测试中即时危险信号混合解释。

### 缺口 2
summary-level CPET 缺少逐呼吸、ECG、症状与终止原因时，直接训练三分类安全标签容易出现循环依赖或构念漂移。

### 缺口 3
当前临床模型往往只给单一分类，而不显式处理不确定性。

## 3.3 研究目标句推荐
“本研究并不旨在开发一个可部署的临床预测器，而是旨在在 summary-level CPET 条件下构建一个可解释、可复现的实验室安全表型原型，并明确其可识别端点与不确定区。”

---

# 四、方法部分怎么改

## 推荐的新方法结构

### 2.1 Study design and data source
保留基本设计

### 2.2 Variable role assignment
新增：把变量分成 phenotype / instability / validation / excluded 四类

### 2.3 Reference-normal subset construction
新增 strict / wide 双版本定义

### 2.4 Dual-anchor reference calibration
- external Chinese references
- internal conditional quantiles

### 2.5 Phenotype burden construction
- variable burden conversion
- reserve domain
- ventilatory domain
- composite score
- phenotype cutpoints

### 2.6 Instability override
- severe / mild rules
- override logic

### 2.7 Confidence and indeterminate classification
- completeness
- effort adequacy
- anchor agreement
- validation agreement

### 2.8 Outcome-anchored validation model
- 明确是 validation，不是主标签生成

### 2.9 Anomaly audit
- 仅作 QC / atypical phenotype flag

### 2.10 Statistical analysis
- construct validity
- calibration / gradient
- sensitivity analyses
- subgroup analyses

---

# 五、结果部分怎么排

## 推荐的新结果顺序

### 3.1 Cohort and data completeness
先交代数据现实，不要一上来就讲模型

### 3.2 Reference subset and conditional reference framework
展示 reference 建模成功建立

### 3.3 Phenotype burden score and zone distribution
展示新主体分数和区间分布

### 3.4 Instability override effects
说明有多少人因即时警报被升级

### 3.5 Confidence / indeterminate results
强调高置信度端点与不确定区

### 3.6 Construct validity against `test_result`
展示梯度：green < yellow < red

### 3.7 Sensitivity analyses
strict / wide, no-BP / full, cycle-only, sex/age strata

### 3.8 Legacy comparison
把旧的 R/T/I v2、rule labels、outcome-anchor-only 结果放在这里或补充

---

# 六、讨论怎么改

## 讨论第一段就要改
不要以“模型性能不高”为开头。  
改成：
- 我们的主要发现是 summary-level CPET 的安全解释应分为表型负担、测试中不稳定和不确定性三层。

## 主要发现建议写成 4 点

### 发现 1
单一监督标签不足以承载安全构念。

### 发现 2
双锚点参考和条件分位框架比单纯 OLS/单方程更适合 Stage I。

### 发现 3
即时不稳定信号应作为覆盖规则，而不应与慢性表型均值混合。

### 发现 4
不确定性并非失败，而是 Stage I 最关键的输出之一。

## 必须明确承认的局限
- summary-level 数据
- 缺失逐呼吸与 ECG
- 无随访结局
- `test_result` 仍是代理变量
- 单中心 derivation
- 部分关键字段缺失

## 未来方向要怎么写
不要只说“以后扩大样本量”。  
要具体说：
1. 引入 breath-by-breath 与 ECG
2. 将不确定区作为 Stage II 优先采样对象
3. 以真实临床随访或安全事件作为外部结果
4. 做多中心外部验证

---

# 七、结论怎么写

## 不推荐
“本模型具有良好临床应用前景，可用于老年高血压患者运动安全预测。”

## 推荐
“本研究建立了一个基于 summary-level CPET 的实验室安全表型原型。该原型以双锚点参考归一化的连续表型负担分数为主体，以测试中的不稳定信号作为覆盖规则，并显式输出置信度与不确定区。结果提示，在缺乏原始波形和随访结局的 Stage I 条件下，最有价值的产出不是高精度预测器，而是一个能够稳定识别高信度端点并保留不确定区的可复现方法学框架。”

---

# 八、补充材料怎么改

补充材料最适合放这些：

## S1
legacy P1 v2/v3 标签和 leakage 消融  
→ 作为“为什么旧路径不适合作为主结果”的证据

## S2
outcome-anchor 模型全部细节  
→ calibration, DCA, feature importance

## S3
alternative weighting / PCA / factor-loading  
→ 证明主公式稳健

## S4
Mahalanobis / anomaly 结果  
→ 说明它更适合 QC

## S5
strict vs wide / no-BP / cycle-only  
→ 稳健性分析

---

# 九、主文表图重排建议

## 主文保留
- 研究流程图
- reference 建模图
- final zone 结果表
- outcome gradient 图
- confidence 分布图

## 移出主文放补充
- 复杂 ML 对比表
- 过多的 SHAP 图
- Mahalanobis 全部细节
- 旧标签消融细节

---

# 十、投稿定位

## 最稳定位
- 方法学原型
- internal derivation
- uncertainty-aware stratification
- laboratory phenotype framework

## 不要自我定位为
- deployable clinical tool
- decision support model
- ready-to-use prediction system

## 稿件语气
要显得：
- 清醒
- 诚实
- 有方法学自觉
- 不夸大

---

# 十一、写给审稿人的核心防守句

### 防守句 1
“本研究并未将 summary-level CPET 误包装为高精度预测器，而是明确将其定位为实验室原型，用于定义可识别端点与不确定区。”

### 防守句 2
“我们将测试中的即时不稳定信号与慢性表型负担拆分建模，以避免构念混杂。”

### 防守句 3
“`test_result` 被用于外部锚定与构念验证，而非用于重新制造主标签。”

### 防守句 4
“显式保留 indeterminate 区是本研究的有意设计，而非分析失败。”

---

# 十二、最建议你直接替换掉的摘要结尾句

推荐最终一句：

“在 summary-level CPET 的信息边界内，运动安全分层更适合被表述为一个以表型负担为主体、以即时不稳定为覆盖、并显式呈现不确定性的实验室原型，而非一个追求单一高 AUC 的监督分类器。”
