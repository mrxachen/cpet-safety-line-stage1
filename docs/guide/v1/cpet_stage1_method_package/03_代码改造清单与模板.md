# 03｜代码改造清单与模板

本文件告诉你：仓库里具体该怎么改。

---

# 一、总原则

不要在当前代码上“继续补补丁式救火”。  
建议采用：

- **冻结旧主线**
- **新增 Stage1B 主线**
- **保留旧结果用于对照和补充材料**

换句话说，不删历史；但主结果换轨。

---

# 二、建议的仓库调整策略

## 2.1 保留但降级为 legacy / audit

### 这些保留
- `configs/data/label_rules_v2.yaml`
- `configs/data/label_rules_v3.yaml`
- `src/cpet_stage1/labels/leakage_guard.py`
- `src/cpet_stage1/labels/zone_engine_v2.py`
- Phase G 相关报表

### 新定位
- 用作历史对照
- 用作补充材料
- 用作“负对照 / 方法学边界展示”
- 不再作为主结果生成器

---

## 2.2 新增的主线模块

建议新增：

```text
src/cpet_stage1/stats/reference_quantiles.py
src/cpet_stage1/anchors/phenotype_engine.py
src/cpet_stage1/anchors/instability_rules.py
src/cpet_stage1/anchors/confidence_engine.py
src/cpet_stage1/modeling/train_outcome_anchor.py
src/cpet_stage1/stats/anomaly_audit.py
src/cpet_stage1/reporting/stage1b_report.py
configs/data/zone_rules_stage1b.yaml
configs/data/variable_roles_stage1b.yaml
configs/data/reference_spec_stage1b.yaml
tests/stats/test_reference_quantiles.py
tests/anchors/test_phenotype_engine.py
tests/anchors/test_instability_rules.py
tests/anchors/test_confidence_engine.py
tests/reporting/test_stage1b_report.py
```

---

# 三、推荐的模块职责

## 3.1 `reference_quantiles.py`

### 职责
- 拟合条件分位模型
- 预测 q10/q25/q50/q75/q90
- 保存模型对象
- 为主体变量提供统一接口

### 必要函数
- `fit_quantile_bundle()`
- `predict_quantiles()`
- `save_bundle()`
- `load_bundle()`

### 关键输入
- reference subset
- variable list
- covariate spec

### 关键输出
- 每个变量的 quantile bundle
- 每位受试者的 predicted quantiles table

---

## 3.2 `phenotype_engine.py`

### 职责
- 根据 quantile predictions 计算单变量 burden
- 聚合 reserve / ventilatory 域
- 计算 `p_lab`
- 估计 phenotype cutpoints
- 生成 phenotype zone

### 必要函数
- `compute_variable_burden()`
- `aggregate_domain_scores()`
- `estimate_phenotype_cutpoints()`
- `assign_phenotype_zone()`
- `run_phenotype_engine()`

---

## 3.3 `instability_rules.py`

### 职责
- 读取 YAML 规则
- 计算 severe / mild instability
- 执行 override

### 必要函数
- `evaluate_rule()`
- `evaluate_instability()`
- `apply_override()`

---

## 3.4 `confidence_engine.py`

### 职责
- 计算 completeness
- 计算 effort adequacy
- 计算 anchor agreement
- 计算 validation agreement
- 生成 confidence 和 indeterminate

### 必要函数
- `compute_completeness_score()`
- `compute_anchor_agreement()`
- `compute_validation_agreement()`
- `compute_confidence()`
- `finalize_zone_with_uncertainty()`

---

## 3.5 `train_outcome_anchor.py`

### 职责
- 训练 outcome-anchor 验证模型
- 做 nested CV
- 导出 calibration / DCA / probability columns

### 必要函数
- `build_outcome_label()`
- `get_feature_matrix()`
- `fit_elastic_net()`
- `fit_lightgbm()`
- `evaluate_outcome_model()`

---

## 3.6 `anomaly_audit.py`

### 职责
- 基于 reference-normalized 主体变量做异常审计
- 输出 anomaly flag

### 必要函数
- `fit_robust_mahalanobis()`
- `score_anomaly()`
- `flag_extreme_cases()`

---

# 四、配置文件怎么设计

## 4.1 `variable_roles_stage1b.yaml`

需要定义：
- 哪些变量属于 reserve
- 哪些变量属于 ventilatory
- 哪些变量属于 instability
- 每个变量方向（higher_better / higher_worse）
- 每个变量是否 required
- 缺失策略

## 4.2 `reference_spec_stage1b.yaml`

需要定义：
- reference subset 生成规则
- strict / wide 两个版本
- 不同 protocol mode 的参考建模分支
- 参考模型 covariates

## 4.3 `zone_rules_stage1b.yaml`

需要定义：
- burden band 规则（q10/q25/q75/q90）
- severe instability 规则
- mild instability 规则
- confidence 权重
- indeterminate 阈值

---

# 五、推荐的 commit 顺序

## Commit 1：封版 legacy
```text
chore: freeze legacy zone and label outputs for stage1b comparison
```

## Commit 2：变量角色与参考配置
```text
feat: add stage1b variable role and reference specs
```

## Commit 3：reference quantiles
```text
feat: implement conditional quantile reference builder for stage1b
```

## Commit 4：phenotype engine
```text
feat: implement phenotype burden engine with dual-domain scoring
```

## Commit 5：instability rules
```text
feat: add instability override engine for stage1b
```

## Commit 6：confidence engine
```text
feat: implement uncertainty-aware confidence engine
```

## Commit 7：outcome anchor validation
```text
feat: add outcome-anchor validator for stage1b
```

## Commit 8：reporting
```text
feat: add stage1b reporting and release artifacts
```

## Commit 9：paper sync
```text
docs: rewrite manuscript for stage1b phenotype prototype narrative
```

---

# 六、CLI / Makefile 应该怎么加

## 建议 CLI 命令

```text
cpet-stage1 stats reference-quantiles
cpet-stage1 anchors phenotype
cpet-stage1 anchors instability
cpet-stage1 anchors confidence
cpet-stage1 model outcome-anchor
cpet-stage1 stats anomaly-audit
cpet-stage1 reports stage1b
cpet-stage1 pipeline stage1b
```

## Makefile 建议新增

```make
reference-quantiles:
\tpython -m cpet_stage1.cli stats reference-quantiles

phenotype:
\tpython -m cpet_stage1.cli anchors phenotype

instability:
\tpython -m cpet_stage1.cli anchors instability

confidence:
\tpython -m cpet_stage1.cli anchors confidence

outcome-anchor:
\tpython -m cpet_stage1.cli model outcome-anchor

anomaly-audit:
\tpython -m cpet_stage1.cli stats anomaly-audit

stage1b:
\tpython -m cpet_stage1.cli pipeline stage1b
```

---

# 七、需要修改而不是新增的老文件

## 7.1 `README.md`
更新项目定位：
- 从 prediction 改成 prototype
- 从 3-class ML 改成 phenotype + override + uncertainty

## 7.2 `docs/PLANNING.md`
新增一节：
- Stage I-B 方法主线
- 明确 legacy 与 main path

## 7.3 `docs/DEVLOG.md`
记录：
- freeze 旧主线
- 新模块上线
- 论文换轨原因

## 7.4 `src/cpet_stage1/reporting/`
加入 Stage1B 总报告聚合

---

# 八、测试怎么写

## 8.1 reference quantiles 测试
要测：
- 输入小样本时是否报错合理
- cycle / treadmill 是否能分支
- 预测 quantiles 是否单调（q10 <= q25 <= ... <= q90）

## 8.2 phenotype engine 测试
要测：
- higher_better 与 higher_worse 方向是否正确
- burden 取值是否只在 {0, 0.5, 1}
- 域内缺失处理是否正确
- cutpoint 与 zone 分配是否稳定

## 8.3 instability 测试
要测：
- severe 触发后一定 red
- mild 只会升级，不会降级
- 缺失值不误报 severe

## 8.4 confidence 测试
要测：
- completeness 计算
- anchor agreement 计算
- validation agreement 缺失时是否走中性分
- low confidence 是否触发 indeterminate

## 8.5 end-to-end 测试
要测：
- 最终输出列完整
- 全流程命令可跑通
- reports 可生成

---

# 九、最推荐的目录输出

```text
data/
  cohort/reference_subset_stage1b.parquet
  features/reference_quantiles_stage1b.parquet
  anchors/phenotype_stage1b.parquet
  anchors/instability_stage1b.parquet
  anchors/confidence_stage1b.parquet
  labels/final_zone_stage1b.parquet
  labels/outcome_anchor_predictions.parquet
  labels/anomaly_flags_stage1b.parquet

outputs/
  reference_models/
  outcome_anchor/
  anomaly/

reports/
  stage1b_reference_report.md
  stage1b_phenotype_report.md
  stage1b_validation_report.md
  stage1b_summary_report.md
```

---

# 十、你应该如何处理旧的 `zone_engine_v2.py`

## 不建议
直接在 `zone_engine_v2.py` 里继续大改，把所有新逻辑塞进去。

## 建议
- 保留 `zone_engine_v2.py` 为 legacy engine
- 新建 `phenotype_engine.py`
- 在总报告中并列展示：
  - legacy v2
  - stage1b new engine

### 原因
这样：
- 补充材料更好写
- 回溯更清楚
- 不会出现“一个文件里同时写两套互相矛盾的方法”的情况

---

# 十一、实际开始编码的最小可行路径（MVP）

如果你不想一下子改很多，最小可行版是：

## Phase 1
- reference subset
- condition quantiles for 4–6 core vars
- phenotype score
- phenotype zone

## Phase 2
- instability override
- confidence engine

## Phase 3
- outcome-anchor validation
- anomaly audit
- report aggregation
- paper rewrite

只要 Phase 1 做好，项目叙事已经会明显改善。

---

# 十二、你最需要记住的一句工程原则

> 旧主线的对象是“标签”；新主线的对象是“构念”。

这一句会决定你后面所有代码是不是又掉回原来的坑。
