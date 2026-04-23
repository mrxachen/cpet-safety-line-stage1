# CPET Stage I 方法学执行包（先看这个）

这是一套给 `cpet-safety-line-stage1` 用的“可直接照着做”的执行包，不是原则清单，也不是泛泛而谈的审稿意见。

## 你会拿到什么

1. `01_完整方法路径.md`  
   从研究问题重定义，到数据清洗、参考建模、分区、验证、发布，一步一步写清楚。

2. `02_算法设计与判定流程.md`  
   把最终建议的算法拆成可以编码的规则、公式、伪代码和决策树。

3. `03_代码改造清单与模板.md`  
   告诉你仓库里哪些文件该保留、哪些该冻结、哪些该新增，以及建议的 commit 顺序。

4. `04_预期结果_里程碑_验收标准.md`  
   给出合理的结果预期，不再追求不现实的 AUC 目标，而是给出“做到什么算成功”。

5. `05_论文改写蓝图.md`  
   对标题、摘要、方法、结果、讨论、补充材料逐节改写。

6. `06_参考文献与引用建议.md`  
   把你真正该补的文献按“放在论文哪里”整理好。

7. `code_templates/`  
   放了可直接作为起点的 Python/YAML 模板。

8. `MASTER_总手册.docx`  
   把上面核心内容合并成一个适合打印、批注、发给导师/合作者的 Word 文档。

---

## 我建议你先接受的总定位

请先把项目定位从：

> “预测 Green / Yellow / Red 的模型”

改成：

> “基于 summary-level CPET 的实验室安全表型原型（laboratory phenotype prototype）”

更具体地说，Stage I 的主产品不应该是一个三分类预测器，而应该是一个三层输出：

- **层 1：表型负担分数（continuous phenotype burden）**
- **层 2：不稳定/硬停止覆盖规则（instability override）**
- **层 3：置信度/不确定性（confidence / indeterminate zone）**

这样你就不再需要把“慢性能力差”和“测试中出现危险信号”硬塞进一个同权平均模型里。

---

## 为什么这套方案比当前主线更稳

当前仓库最核心的问题，不是“模型不够复杂”，而是“安全”被同时定义成了三件事：

1. 规则标签（`label_rules_v2/v3`）
2. 相对 reference-normal subset 的偏离（`zone_engine_v2`）
3. `test_result` 代理的临床结局

这三者不是一回事，所以一致性差是正常结果。

本执行包的核心改法是：

- **把“表型”和“警报条件”拆开**
- **把 `test_result` 从主标签降级为外部锚定/验证变量**
- **把不确定性变成主输出，而不是副产物**

---

## 最推荐的阅读顺序

### 第一步：看方法主线
先读 `01_完整方法路径.md`

### 第二步：看算法怎么落地
再读 `02_算法设计与判定流程.md`

### 第三步：开始改仓库
按 `03_代码改造清单与模板.md` 操作

### 第四步：判断有没有跑偏
对照 `04_预期结果_里程碑_验收标准.md`

### 第五步：同步改论文
最后按 `05_论文改写蓝图.md`

---

## 建议你马上做的第一批动作（不需要再想）

### A. 立刻冻结旧主线
把以下内容标为 legacy / audit，不再当主方法：
- `label_rules_v2` / `label_rules_v3` 生成的 P1 三分类
- “用 ML 预测 P1” 这条主线
- 把 Mahalanobis 当成主风险分层器
- 把 outcome-anchor AUC > 0.70 当硬目标

### B. 立刻启动新主线
改成：

1. dual-anchor 参考建模  
2. phenotype burden 分数  
3. instability override  
4. confidence engine  
5. `test_result` 仅作外部验证/辅助置信度  
6. anomaly score 仅作 QC / atypical phenotype flag

### C. 论文同步降调
主文不再说：
- “预测工具”
- “临床可部署”
- “高精度风险模型”

改说：
- “方法学框架原型”
- “internal derivation”
- “laboratory prototype”
- “uncertainty-aware stratification”

---

## 你最后应该得到的不是这些

不要再以这些作为成功定义：

- P1 三分类 F1 必须 > 0.70
- Outcome-anchor AUC 必须 > 0.70
- 一致性高信度必须 > 60%
- Mahalanobis 必须和 `test_result` 强相关

这些目标在 summary-level、缺少随访、缺少 ECG/症状/终止原因的 Stage I 下，本来就不稳。

---

## 你最后应该得到的是这些

更合理的成功定义是：

- 形成一个 **可解释、可复现、可冻结** 的 Stage I 原型
- reference-normal 子集在新规则下大多数位于 Green / Yellow
- final zone 在 `test_result` 上呈现 **有方向性的梯度**
- 高置信度子集能够被识别出来
- 不确定子集能够被明确圈出来，作为 Stage II 优先对象
- 论文叙事从“模型不够准”转成“方法学边界被精确定义”

---

## 一句话结论

你最该做的，不是继续救 P1 模型；而是把整个项目改造成一个：

> **以中国参考值为外锚、以 reference subset 为内锚、以表型负担为主体、以不稳定规则为覆盖、以不确定性为显式输出的 summary-level CPET 实验室原型。**
