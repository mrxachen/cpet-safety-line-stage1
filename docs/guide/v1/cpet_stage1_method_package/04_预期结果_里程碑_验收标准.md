# 04｜预期结果、里程碑与验收标准

这份文档的目的，是把“什么叫成功”重新说清楚。

---

# 一、不要再追的不合理目标

下面这些目标，不应该继续作为 Stage I 主成功标准：

- outcome-anchor AUC 必须 > 0.70
- 三分类模型 F1 必须 > 0.70
- 一致性高信度必须 > 60%
- Mahalanobis 必须和 `test_result` 强相关
- OLS R² 必须大幅接近 0.70

这些目标本质上都假设：  
summary-level CPET + 缺少逐呼吸 + 缺少 ECG/终止原因/症状 + 无随访结局，仍然能做出部署级预测器。  
这是不现实的。

---

# 二、Stage I 真正应该达到的结果

## 成功标准 A：构念清晰
最终输出能把这三件事拆开：
1. 慢性表型负担
2. 测试中不稳定/警报
3. 不确定性

## 成功标准 B：结果可复现
同一批数据重复运行，最终 cutpoints、zone 分布和关键统计量稳定。

## 成功标准 C：方向有临床意义
`final_zone` 在 `test_result` 上能显示有方向性的梯度。

## 成功标准 D：能识别不确定区
不是所有人都必须明确分层，但必须能识别“不能高信度解释”的样本。

## 成功标准 E：论文可成立
即便预测性能一般，论文依然能作为“方法学原型”成立。

---

# 三、合理的结果预期区间

## 3.1 参考建模

### 你可以合理期待
- 条件分位模型运行稳定
- VO2peak 外部中国方程比欧美老方程偏差更小
- 内部条件分位能提供可解释的 q10/q25/q75/q90

### 不应强求
- 所有变量都有很高解释度
- 所有变量都能得到漂亮的线性方程

### 可以接受的现象
- CV R² 仍在 0.35~0.50 左右
- 某些变量分位模型只适合给 band，不适合给精确预测值

---

## 3.2 phenotype zone

### 你可以合理期待
- reference subset 里 green 占多数
- red 比例较低
- overall zone 分布不会极端失衡

### 建议目标
- strict reference 中 red 最好 < 10–15%
- wide reference 中 red 可略高，但不应过多

### 如果出现下面情况，说明要返工
- strict reference 中 red > 20%
- green 几乎消失
- zone 分布受单一变量完全支配

---

## 3.3 outcome validation

### 你可以合理期待
- green / yellow / red 的 `test_result` 阳性率呈递增
- 高置信度子集梯度更清晰

### 现实预期
在当前 summary-level 条件下，outcome model AUC 很可能仍只在：
- 0.55–0.65

### 这不算失败
只要：
- calibration 不离谱
- zone 梯度方向正确
- 高置信度子集更稳

就足够支撑 Stage I 结论。

---

## 3.4 confidence engine

### 最合理期待
- high confidence 子集可被识别
- medium / low / indeterminate 有清晰分层

### 推荐结果区间
- high confidence：30–50%
- medium：20–40%
- low/indeterminate：20–40%

### 为什么不再追 >60%
因为你现有数据结构本来就不支持那么高的确定性。

---

## 3.5 anomaly audit

### 合理期待
- 极端异常样本被识别
- 不要求和 `test_result` 强相关

### 推荐用途成功标准
- 能帮助排查数据问题
- 能圈出 atypical phenotype
- 能为 Stage II 选样提供名单

---

# 四、四个里程碑

## Milestone 1：reference system

### 完成定义
- strict / wide reference subset 定义完成
- 4–6 个核心变量的条件分位模型跑通
- 输出 q10/q25/q50/q75/q90

### 交付
- `reference_subset_stage1b.parquet`
- `reference_quantiles_stage1b.parquet`
- `stage1b_reference_report.md`

### 验收标准
- quantile 预测单调
- cycle / treadmill 分开处理
- reference 报告可解释

---

## Milestone 2：phenotype engine

### 完成定义
- Reserve burden
- Ventilatory burden
- `p_lab`
- phenotype zone

### 交付
- `phenotype_stage1b.parquet`
- `phenotype_cutpoints.json`
- `stage1b_phenotype_report.md`

### 验收标准
- 域内 burden 逻辑正确
- strict reference 中 green 为主
- no single variable dominance

---

## Milestone 3：override + confidence

### 完成定义
- severe / mild instability
- final zone before confidence
- confidence score
- indeterminate output

### 交付
- `instability_stage1b.parquet`
- `confidence_stage1b.parquet`
- `final_zone_stage1b.parquet`

### 验收标准
- severe 一定 red
- low confidence 不再被硬判 green/red
- final output 列完整

---

## Milestone 4：validation + manuscript

### 完成定义
- outcome-anchor validation
- anomaly audit
- paper rewrite
- release artifacts

### 交付
- `outcome_anchor_predictions.parquet`
- `anomaly_flags_stage1b.parquet`
- `stage1b_summary_report.md`
- 新版主文与补充材料

### 验收标准
- `test_result` 梯度方向正确
- 主文叙事不再围绕失败的 ML
- supplement 中 legacy 对照齐全

---

# 五、接受/警告/失败三色标准

## 5.1 接受（Accept）
满足大部分如下条件：
- reference 模型稳定
- phenotype zone 可解释
- final zone 对 `test_result` 有单调梯度
- high confidence 子集存在且更稳
- 论文能以 prototype 逻辑完整讲通

## 5.2 警告（Warn）
出现以下情况之一，但可修：
- reference subset 定义过窄导致样本量太小
- confidence engine 把太多人送入 indeterminate
- no-BP 与 full 版本差异过大
- 某个关键变量分位模型极不稳定

## 5.3 失败（Fail）
出现以下情况应返工：
- reference 中 red 大量出现
- final zone 与 `test_result` 完全无方向性关系
- instability override 形同虚设
- confidence 计算几乎全靠一个分量决定
- 论文仍只能讲“ML 不行”

---

# 六、结果呈现时最应该展示的表与图

## 主文表格

### Table 1
按 final zone 分组的 cohort baseline

### Table 2
参考建模摘要（变量、协变量、分位效果、模式）

### Table 3
phenotype 变量和 burden 规则

### Table 4
final zone 与 `test_result` 梯度

### Table 5
不同 confidence 层级的结果

### Table 6
敏感性分析（strict/wide, full/no-BP, cycle-only）

## 主文图

### Figure 1
研究流程图：summary-level → reference → phenotype → override → confidence

### Figure 2
关键变量在 reference subset 的条件分位示意

### Figure 3
各 cohort 的 phenotype score 分布

### Figure 4
final zone 的 `test_result` 阳性率梯度

### Figure 5
confidence 分布与 indeterminate 比例

---

# 七、你应该怎么向导师或审稿人解释“结果一般但研究仍成立”

推荐说法：

1. 我们明确证明了 summary-level CPET 的能力边界  
2. 我们避免了循环依赖标签继续误导结果  
3. 我们把安全构念拆成表型、警报与不确定性三层  
4. 我们得到的是一个可冻结的 Stage I 原型  
5. 我们因此能为 Stage II 提供更清晰的数据需求和抽样优先级

---

# 八、最稳的 headline result 是什么

不是：
- AUC = x.xx

而是：

- 基于双锚点参考和不稳定覆盖规则的 summary-level CPET 原型可稳定识别高信度低风险与高风险端点，同时显式保留不确定区，避免将即时安全信号与慢性表型负担混为一谈。

---

# 九、你最后应当愿意接受的结果范围

如果最后得到的是：

- outcome AUC 只有 0.58
- high confidence 只有 35%
- indeterminate 还有 30%
- 但 final zone 在 `test_result` 上有清晰梯度
- strict / wide / no-BP 分析方向一致
- 论文叙事完整

那么这已经是一个合格且有价值的 Stage I 成果。
