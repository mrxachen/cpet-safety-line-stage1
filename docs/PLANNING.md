# PLANNING.md — 项目代码规划文档

> 本文档是 `cpet-safety-line-stage1` 仓库的**代码开发总规划**，是所有开发工作的技术北极星。
> 最新修订：2026-04-14
> 对应原始规划文档：`Document/规划/v2/` 全套（文档1–4）

---

## 一、四阶段总路线

| 阶段 | 核心问题 | 数据主战场 | 代码/仓库 |
|---|---|---|---|
| **阶段 I（本仓库）** | 基于 summary-level 数据建立实验室安全线原型 | ~3232 条脱敏 CPET 汇总数据 | `cpet-safety-line-stage1`（主战场） |
| 阶段 II | 原始 ECG + 逐呼吸数据升级实验室时序能力 | 12导联 ECG（1000Hz）+ 逐呼吸气体交换 | 本仓库预留接口 / 后续扩展 |
| 阶段 III | 从 CPET 实验室安全线迁移至居家安全走廊 | 同步采集 + 短期家庭跟踪 | 本仓库输出 bridge prep 资产 |
| 阶段 IV | 静默验证与转化评估 | 医院静默运行 + 家庭试运行 | 后续转化仓库 |

**阶段 I 一句话定位：**
> 只正式求解实验室安全线原型（B_lab），但从第一天起就为家庭安全走廊（C_home）做好准备。

---

## 二、阶段 I 边界

### 做什么（In Scope）

- 四组 summary-level CPET 数据的导入、QC、统一 schema
- `HTN history × EIH response` 2×2 队列注册
- reference-normal subset 构建
- **P0**（运动前先验风险）与 **P1**（运动后后验分层）分时间轴模型
- 实验室绿 / 黄 / 红安全区原型（Z_lab）
- 实验室锚点资产（R/T/I 三轴：A_lab、S_lab、Z_lab）
- 阶段 III 桥接准备包（anchor dict + proxy hypothesis + sampling priority + question list）
- 论文 1（表型与双因素分析）和论文 2（P0/P1 分层模型）所需代码与图表

### 不做什么（Out of Scope）

- 原始 ECG / 逐呼吸波形的正式建模（仅预留接口 + 1–2 例链路打通）
- 家庭安全走廊（C_home）的正式建模与验证
- 实时推理服务、Web 前端、可穿戴端部署
- 大规模前瞻性临床试验

---

## 三、当前数据快照

| 组别 | N | 年龄中位 | 男性% | VO₂peak 中位 | AT-VO₂ 中位 | 阳性% |
|---|---|---|---|---|---|---|
| 对照 / 非高血压 | 1858 | 67 | 50.2 | 23.2 | 14.1 | 13.5 |
| 既往 HTN + 无运动 HTN | 738 | 67 | 57.7 | 19.2 | 12.2 | 16.1 |
| 既往 HTN + 运动 HTN | 277 | 67 | 50.9 | 20.1 | 12.3 | 19.5 |
| 仅运动 HTN | 359 | 68 | 49.9 | 23.6 | 14.2 | 12.3 |
| **合计** | **3232** | — | — | — | — | — |

**五个关键数据判断（影响建模策略）：**

1. **储备轴 ≠ 应激轴**：既往 HTN 无运动 HTN 组更像"慢性储备下降型"，仅运动 HTN 组更像"血流动力学异常反应型"，不能单轴合并。
2. **EIH 与峰值 BP 高度同源**：防泄漏是硬约束，leakage_guard 是方法学而非工程补丁。
3. **对照组不等于健康规范组**：必须先构建 reference-normal subset，不能直接用全部对照当参考。
4. **仅运动 HTN 组缺失更多**：含 BP / 不含 BP 双版本模型是必须的，不是可选项。
5. **原始数据极少（1–2 例）**：定义为"链路打通任务"，不正式训练多模态模型。

---

## 四、核心方法学原则

| # | 原则 | 工程落点 |
|---|---|---|
| P1 | 先注册队列，再建模 | `cohort_registry.py` 先跑 |
| P2 | 先 reference subset，再标准化 | `reference_subset.py` 产出 %pred / z-score |
| P3 | 先分时间轴，再谈风险 | P0 特征集 ≠ P1 特征集，代码层硬隔离 |
| P4 | leakage guard 是正式方法学 | `leakage_guard.py` + 实验报告必须记录通过与否 |
| P5 | 分组 QC，拒绝"统一清洗幻想" | `qc/` 对每组独立输出缺失率和协议诊断 |
| P6 | bridge-aware 但 scope-controlled | `bridge_prep/` 输出资产，不训练桥接模型 |

---

## 五、系统架构：八层数据流

```
医院 Excel 导出
    ↓ make ingest
  data/raw/              ← 原始导入，永不覆盖
    ↓ io/ + field_map
  data/staging/          ← 字段映射 + 类型修正
    ↓ qc/
  data/curated/          ← QC 通过的建模底表
    ↓ cohort/ + labels/
  data/labels/           ← 2×2 注册 + proxy 标签 + 安全区 (Z_lab)
  data/contracts/        ← 跨场景主键合约
    ↓ features/
  data/features/         ← P0 特征表 (features_pre) + P1 特征表 (features_post)
    ↓ anchors/
  data/anchors/          ← A_lab 向量 + S_lab 分数 + Z_lab 区 (R/T/I 三轴)
    ↓ modeling/
  outputs/               ← 模型 + 评估 + SHAP
    ↓ reporting/ + bridge_prep/
  reports/               ← Markdown 报告 + 论文图表
  outputs/bridge_prep/   ← 桥接准备包 (anchor dict + proxy table + ...)
```

---

## 六、模型体系

### P0：运动前先验风险模型

**目的**：预测"上机前"可能出现的异常应激/低储备风险，用于运动前评估。

| 要素 | 说明 |
|---|---|
| 输入特征 | 人口学、体型、病史、药物、行为生活方式、协议信息 |
| 禁止输入 | 峰值 SBP/DBP、peak VO₂、运动试验结果、任何测试后字段 |
| 候选模型 | LASSO Logistic（基线）、XGBoost（主模型） |
| 配置文件 | `configs/model/p0_lasso.yaml`, `configs/model/p0_xgb.yaml` |
| 核心模块 | `src/cpet_stage1/modeling/train_p0.py` |

### P1：运动后后验分层模型

**目的**：基于 CPET 测试全结果做实验室安全区分层，输出绿/黄/红区。

| 要素 | 说明 |
|---|---|
| 输入特征 | VO₂@AT、peak VO₂、%pred VO₂、OUES、VE/VCO₂ slope、HRR、O₂脉搏轨迹、运动耐量 |
| 输出 | 三分类有序（green=0 / yellow=1 / red=2）+ 各类别概率 |
| 候选模型 | Ordinal Logistic（基线）、LightGBM（主）、CatBoost（对照） |
| 配置文件 | `configs/model/p1_logit.yaml`, `configs/model/p1_lgbm.yaml`, `configs/model/p1_catboost.yaml` |
| 核心模块 | `src/cpet_stage1/modeling/train_p1.py` |

### 实验室锚点资产（三轴）

| 轴 | 含义 | 关键变量 | 工程对象 |
|---|---|---|---|
| **R（Reserve）** | 还能承受多大运动量？ | VO₂peak %pred, O₂脉搏, VT1/VO₂peak% | `reserve_axis` |
| **T（Threshold）** | 是否接近不该继续加量的区域？ | HR@VT1, HR@RCP, VT1_load_W | `threshold_axis` |
| **I（Instability）** | 是否出现危险模式？ | EIH flag, BP 异常, arrhythmia, VE/VCO₂ slope | `instability_axis` |

组合向量：`A_lab = (R, T, I)`  →  综合风险分数：`S_lab`  →  安全区：`Z_lab ∈ {green, yellow, red}`

---

## 七、核心模块职责表

| 模块 | 文件路径 | 职责 | 主要输出 |
|---|---|---|---|
| io | `src/.../io/` | Excel 读入、字段映射、staging 生成 | `staging/*.parquet` |
| qc | `src/.../qc/` | 范围/逻辑/缺失/协议检查 | `qc_report.md`, `qc_flags.parquet` |
| contracts | `src/.../contracts/` | 跨场景主键定义与验证 | `contract_snapshot.json` |
| cohort | `src/.../cohort/` | 2×2 注册 + reference subset | `cohort_registry.parquet`, `reference_subset.parquet` |
| labels | `src/.../labels/` | P0/P1 标签生成 + leakage guard | `label_table.parquet`, `zone_table.parquet` |
| features | `src/.../features/` | P0/P1 特征工程 + 标准化 + 插补 | `features_pre.parquet`, `features_post.parquet` |
| anchors | `src/.../anchors/` | R/T/I 三轴构建 + 锚点包导出 | `anchor_table.parquet`, `anchor_package_v1/` |
| stats | `src/.../stats/` | Table 1, 2×2 因子, reference builder | 统计表 + 图表 |
| modeling | `src/.../modeling/` | P0/P1/多任务训练 + 校准 + 评估 + SHAP | 模型文件 + `metrics.json` + SHAP图 |
| bridge_prep | `src/.../bridge_prep/` | 代理假设 + 采样优先级 + 问题清单导出 | bridge prep 包 |
| interfaces | `src/.../interfaces/` | 阶段 II/III 外部数据 schema（仅定义） | ECG/呼吸/传感器 schema |
| reporting | `src/.../reporting/` | 论文图表 + Markdown 报告 | `reports/release/` |
| utils | `src/.../utils/` | 路径、随机种子、日志 | — |

---

## 八、七个里程碑

### M1 — 仓库脚手架（已完成 ✅）

**完成标准：**
- [x] 完整目录结构
- [x] `pyproject.toml` + `Makefile` + `.gitignore` + `.pre-commit-config.yaml`
- [x] 所有 YAML 配置文件（schema, field_map, qc_rules, label_rules, anchor_rules…）
- [x] `src/cpet_stage1/` 包骨架 + CLI 骨架
- [x] `leakage_guard.py` 核心模块
- [x] `tests/test_smoke_pipeline.py` smoke tests
- [x] `data/demo/synthetic_cpet_stage1.csv` 合成数据
- [x] GitHub 私有仓库 + `main`/`dev` 分支

---

### M2 — 数据导入与 QC 跑通

**目标**：四组 Excel → `staging` → `curated`，并输出 QC 报告。

**完成标准：**
- [ ] `make ingest` 成功：`data/staging/*.parquet` 生成
- [ ] `make qc` 成功：输出 `qc_report.md`（含缺失率、范围、逻辑检查）
- [ ] `仅运动 HTN` 组有单独 QC 诊断段落
- [ ] 字段映射报告 `field_mapping_report.json` 生成
- [ ] `data/manifests/hash_registry.json` 生成

**关键模块**：`io/loaders.py`, `io/excel_import.py`, `qc/rules.py`, `qc/validators.py`

**前置条件**：真实 Excel 数据文件就位（`DATA_DIR` 配置）

---

### M3 — 2×2 队列注册 + 标签引擎跑通

**目标**：正式注册队列，生成 P0/P1 标签与实验室安全区。

**完成标准：**
- [ ] `make cohort` 成功：`cohort_registry.parquet`（含 `cohort_2x2`, `reference_flag`）
- [ ] reference-normal subset 生成（宽 + 严两版本）
- [ ] `make labels` 成功：`label_table.parquet` + `zone_table.parquet`
- [ ] `leakage_guard` 检查通过（报告写入实验记录）
- [ ] 标签分布统计通过合理性检查（P0 阳性率 10–30%，红区占比 < 40%）

**关键模块**：`cohort/cohort_registry.py`, `cohort/reference_subset.py`, `labels/label_engine.py`, `labels/safety_zone.py`, `labels/leakage_guard.py`

---

### M4 — 表型分析与参考模型（论文 1 核心）

**目标**：输出 Table 1、2×2 因子分析，支撑论文 1。

**完成标准：**
- [ ] Table 1 输出（四组，含 SD / IQR，`stats/table1.py`）
- [ ] HTN × EIH 双因素效应分析（主效应 + 交互效应）
- [ ] reference-normal 参考方程 / %pred / z-score 跑通
- [ ] 关键指标分组差异图（箱线图 / 小提琴图）
- [ ] 协议分层敏感性分析

**关键模块**：`stats/table1.py`, `stats/twobytwo.py`, `stats/reference_builder.py`

---

### M5 — P0/P1 主模型跑通（论文 2 核心）

**目标**：完成基线 + 主模型训练、校准、SHAP 解释，支撑论文 2。

**完成标准：**
- [ ] P0：LASSO 基线 + XGBoost 主模型（AUC、AUPRC、Brier score）
- [ ] P1：Ordinal Logistic 基线 + LightGBM/CatBoost 主模型（F1_macro、kappa）
- [ ] 含 BP / 不含 BP 双版本对照完成
- [ ] 踏车主模型 + 全样本模型一致性分析完成
- [ ] 校准曲线（isotonic）+ DCA 完成
- [ ] SHAP global + 个体解释图
- [ ] 测试集结果报告 `p0_model_report.md` + `p1_model_report.md` 生成

**关键模块**：`modeling/train_p0.py`, `modeling/train_p1.py`, `modeling/calibrate.py`, `modeling/evaluate.py`, `modeling/interpret.py`

---

### M6 — 锚点资产 + Bridge Prep 包跑通

**目标**：固化阶段 I 对阶段 III 的上游输出。

**完成标准：**
- [ ] `make anchors` 成功：`anchor_table.parquet`（含 `reserve_axis`, `threshold_axis`, `instability_axis`, `a_lab_vector`, `s_lab_score`, `z_lab_zone`）
- [ ] `make bridge-prep` 成功：输出以下全部文件：
  - `anchor_variable_dictionary_v1.md`
  - `home_proxy_hypothesis_table_v1.csv`
  - `bridge_sampling_priority_list_v1.md`
  - `bridge_question_list_v1.md`
  - `bridge_prep_package_manifest.json`
- [ ] `contract_snapshot.json` 生成并通过 `bridge_contract.py` 验证

**关键模块**：`anchors/anchor_builder.py`, `anchors/export_anchor_package.py`, `bridge_prep/proxy_hypothesis.py`, `bridge_prep/export_bridge_prep.py`, `contracts/bridge_contract.py`

---

### M7 — 报告 + 冻结版发布（v1.0.0-stage1）

**目标**：产出阶段 I 第一版论文复现实验包。

**完成标准：**
- [ ] `make reports` 一键生成 Markdown 报告
- [ ] `reports/release/` 有冻结结果（含模型指标、图表、config 快照）
- [ ] README 可指导他人基于 synthetic demo 数据复现全流程
- [ ] `bridge_prep_pkg_v1` 打包
- [ ] 创建 Git tag `v1.0.0-stage1`

---

## 九、推荐实施顺序（8 步）

按下面顺序实施，确保研究对象先定义稳再建模：

```
Step 1: io → qc → contracts → cohort_registry
Step 2: reference_subset → label_engine → leakage_guard
Step 3: feature_pre → feature_post → splits
Step 4: reference_builder → table1 → twobytwo
Step 5: train_p0 → train_p1 → evaluate → interpret
Step 6: anchor_builder → export_anchor_package
Step 7: proxy_hypothesis → sampling_priority → export_bridge_prep
Step 8: risk_reporter → export_md → release
```

---

## 十、版本策略

| 版本类型 | 当前 | 下一版本 |
|---|---|---|
| 代码版本 | `v0.1.0`（脚手架） | `v0.2.0`（QC + cohort 跑通） |
| 数据快照 | 待冻结 | `dataset_snapshot_2026-05-xx_v1` |
| 实验版本 | — | `exp_paper1_2x2_v1` |
| 数据契约 | `contract_v1`（schema 定义）| `contract_v2_bridge_ready`（M6后） |
| 锚点/Bridge 准备包 | — | `anchor_pkg_v1`（M6） |

---

## 十一、数据契约（跨场景主键）

一旦进入 `contract_v1`，以下字段命名**不得随意修改**（需升级版本号）：

```
subject_id           # 人级别唯一ID
cpet_session_id      # 单次 CPET 总结报告 ID（本阶段主键）
raw_session_id       # 原始波形 ID（阶段 II 预留）
bridge_session_id    # 桥接采集任务 ID（阶段 III 预留）
home_task_id         # 家庭任务 ID（阶段 IV 预留）
reserve_axis         # R 轴（锚点）
threshold_axis       # T 轴（锚点）
instability_axis     # I 轴（锚点）
s_lab_score          # 综合风险分数
z_lab_zone           # 绿/黄/红安全区
```

---

## 十二、测试策略

### 优先覆盖的 6 个模块
1. `label_engine` — 规则错误影响所有下游
2. `leakage_guard` — 方法学核心
3. `feature_pre` / `feature_post` — 特征隔离正确性
4. `splits` — 防止 subject 泄漏到不同 fold
5. `anchor_builder` — 锚点输出正确性
6. `bridge_contract` / `bridge_schema` — 跨阶段接口兼容性

### 回归测试基准
以 `data/demo/synthetic_cpet_stage1.csv`（20 条合成数据）作为回归基准，每次提交后验证：
- 标签分布不意外漂移
- 特征列数不意外变化
- leakage guard 不被绕过
- 锚点字段不缺失

---

## 十三、常见工程陷阱（提醒）

| 陷阱 | 后果 | 避免方式 |
|---|---|---|
| 只把仓库当模型脚本集合 | 无法复现，规则散落 | 所有规则外置 YAML，CLI 化 |
| Notebook 偷偷承载主逻辑 | 难以测试和审计 | Notebook 只用于探索和图表草稿 |
| 忽视 leakage_guard | 指标虚高，论文可信度下降 | 每次实验报告必须写 leakage_guard 结果 |
| Bridge prep 变成 bridge modeling | 主任务失控 | `bridge_prep/` 只输出文档和数据资产 |
| 没有跨场景主键 | 阶段 III 全面返工 | contract_v1 提前冻结 |
| 只输出分类结果，不输出锚点资产 | 阶段 III 失去方向 | M6 作为正式里程碑 |
| 真实数据进 GitHub | 合规风险 | `.gitignore` 已排除所有数据目录 |

---

## 十四、文档索引

| 文档 | 路径 | 说明 |
|---|---|---|
| 阶段 I 边界定义 | `docs/protocol/stage1_scope.md` | 纳排标准、终点、里程碑 |
| 端点定义 | `docs/protocol/endpoint_definitions.md` | P0/P1 正式定义 |
| 数据请求清单 | `docs/protocol/data_request_checklist.md` | 向医院申请数据的字段清单 |
| 锚点变量字典 | `docs/bridge/anchor_variable_dictionary_v1.md` | R/T/I 三轴变量 |
| 代理假设表 | `docs/bridge/home_proxy_hypothesis_table_v1.md` | 家庭代理信号假设（待验证） |
| 桥接问题清单 | `docs/bridge/bridge_question_list_v1.md` | 阶段 III 先回答什么 |
| ADR 001–006 | `docs/decisions/` | 六条架构决策记录 |
| **本规划文档** | `docs/PLANNING.md` | 代码开发总规划（本文件） |
| **开发日志** | `docs/DEVLOG.md` | 逐次进展记录 |
