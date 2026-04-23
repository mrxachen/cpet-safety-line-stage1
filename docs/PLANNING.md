# PLANNING.md — 项目代码规划文档

> 本文档是 `cpet-safety-line-stage1` 仓库的**代码开发总规划**，是所有开发工作的技术北极星。
> 最新修订：2026-04-23（v3.1.0，Stage 1B 全部完成 + 论文三轮修订完成）
> 对应原始规划文档：`Document/规划/v2/` 全套（文档1–4）

---

## 一、四阶段总路线

**核心目标**：根据人处于什么状态（状态参数），判断他会如何（结果）。

| 阶段 | 核心目标 | 状态参数 | 结果定义 | 侧重点 |
|---|---|---|---|---|
| **Stage I（本仓库）** | 建立 CPET 报告→安全区的有效建模方法学 | CPET 汇总指标 + 人口学 + 病史 | 三区间安全区（锚定于 test_result 临床结局）| **有效建模**（方法学创新）|
| Stage II | 引入完整 CPET 原始数据提升预测精度 | Stage I + 逐呼吸气体交换 + 12导 ECG 波形 | 同 Stage I（更精确的连续风险评分）| **预测精度** |
| Stage III | 迁移到日常可穿戴场景 | 可穿戴设备数据（HR/SpO₂/加速度/呼吸率）| 居家安全走廊 | **场景迁移**（新实验设计）|
| Stage IV | 静默验证与临床转化 | 上述全部 | 前瞻性验证 | **临床验证** |

**Stage I 一句话定位：**
> Stage 1 核心任务：从 CPET 报告数据中，建立科学有效且临床可解释的"状态→结局"映射方法学。不追求预测精度（那是 Stage 2），追求映射的有效性和可靠性。

---

## 二、阶段 I 边界

### 做什么（In Scope）

- 四组 summary-level CPET 数据的导入、QC、统一 schema
- `HTN history × EIH response` 2×2 队列注册
- reference-normal subset 构建
- **改进参考方程**（纳入 BMI，本地化中国老年高血压人群）
- **数据驱动安全区构建**（R/T/I 三轴 → S_lab → 参考分位切点）
- **结局锚定安全区**（直接以 test_result 为结局，全特征建模，消除循环依赖）
- **多变量异常评分**（Mahalanobis 距离，捕获多维偏离模式）
- **多定义一致性分析**（规则 vs 数据驱动 vs 结局锚定 → 一致性/不确定性量化）
- P0/P1 ML 模型（辅助验证：量化 summary-level 数据的预测天花板）
- 实验室锚点资产（R/T/I 三轴：A_lab、S_lab、Z_lab）
- 阶段 III 桥接准备包（anchor dict + proxy hypothesis + sampling priority + question list）
- 论文：数据驱动安全区方法学（核心）+ ML 辅助验证

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

## 六-B、方法学创新体系（Phase G 新增）

> Phase G 针对 Stage I 的根本问题（P1 循环依赖）提出三种互补方法，构成完整的"数据驱动安全区方法学"体系。

### 根本问题诊断

```
P1 zone = f(vo2_peak_pct_pred, ve_vco2_slope, eih_status)  ← 确定性规则
leakage_guard 排除这3个变量
ML 只能用间接特征预测 f(excluded_vars) ← 结构性不可学习
结果：P1 F1=0.47 < 2变量基线(HTN+BMI) AUC=0.611
```

### Method 1：结局锚定安全区（Outcome-Anchored Safety Zones）

**核心创新**：直接以 `test_result`（CPET 临床结局）为标签，全特征（含 vo2_peak_pct_pred、ve_vco2_slope）建模，消除循环依赖。

- 特征：全部 CPET 指标 + 人口学（~12-15 个）
- 标签：test_result 二分类（阳性+可疑阳性 vs 阴性）
- 模型：LightGBM + isotonic 校准（5折CV）
- 安全区切点：Youden's J + DCA net benefit 联合优化
- **预期 AUC > 0.65**（消除结构性不可学习问题后）
- 核心文件：`src/cpet_stage1/modeling/train_outcome.py`、`src/cpet_stage1/labels/outcome_zone.py`

### Method 2：多变量异常评分（Mahalanobis Distance Anomaly Scoring）

**核心创新**：计算患者在多变量 CPET 空间中相对参考人群的 Mahalanobis 距离，捕获变量间协方差信息。

- 参考子集：CTRL（reference_flag_wide=True）构建 μ 和 Σ
- 变量：5 个非泄漏 CPET 变量（vo2_peak, hr_peak, o2_pulse_peak, oues, mets_peak）
- D² 服从 χ²(k) 分布，提供自然概率解释
- 安全区：P75（Green/Yellow）和 P95（Yellow/Red）
- **预期 D² 与 test_result 相关 r > 0.10**（优于当前 r=0.059）
- 核心文件：`src/cpet_stage1/stats/anomaly_score.py`

### Method 3：多定义一致性框架（Concordance Ensemble）

**核心创新**：将多种安全区定义（规则式 + 数据驱动 + 结局锚定）的一致性/分歧量化为"信度"，不确定区域主动标记。

- 收集 K≥3 个定义的投票：P1 规则标签、Zone Engine v2、结局锚定模型、VO₂peak 阈值规则
- 输出：`zone_consensus`（多数票区）+ `zone_confidence`（一致性比例）
- 不确定类别：无定义 > 50% 投票或 Green/Red 同时出现
- **预期高信度子集 ≥ 55%**，自然引出 Stage 2 优先人群（不确定区）
- 核心文件：`src/cpet_stage1/labels/concordance_ensemble.py`

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
| stats | `src/.../stats/` | Table 1, 2×2 因子, reference builder, 可视化 | `reports/table1.md, twobytwo.md, figures/m4/*.png` |
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

### M2 — 数据导入与 QC 跑通（已完成 ✅）

**目标**：四组 Excel → `staging` → `curated`，并输出 QC 报告。

**完成标准：**
- [x] `make ingest` 成功：`data/staging/*.parquet` 生成
- [x] `make qc` 成功：输出 `qc_report.md`（含缺失率、范围、逻辑检查）
- [x] `仅运动 HTN` 组有单独 QC 诊断段落
- [x] 字段映射报告 `field_mapping_report.json` 生成
- [x] `data/manifests/hash_registry.json` 生成

**关键模块**：`io/loaders.py`, `io/excel_import.py`, `qc/rules.py`, `qc/validators.py`

**前置条件**：真实 Excel 数据文件就位（`DATA_DIR` 配置）

---

### M3 — 2×2 队列注册 + 标签引擎跑通（已完成 ✅）

**目标**：正式注册队列，生成 P0/P1 标签与实验室安全区。

**完成标准：**
- [x] `make cohort` 成功：`cohort_registry.parquet`（含 `cohort_2x2`, `reference_flag`）
- [x] reference-normal subset 生成（宽 + 严两版本）
- [x] `make labels` 成功：`label_table.parquet` + `zone_table.parquet`
- [x] `leakage_guard` 检查通过（报告写入实验记录）
- [x] 标签分布统计通过合理性检查（P0 阳性率 10–30%，红区占比 < 40%）

**关键模块**：`cohort/cohort_registry.py`, `cohort/reference_subset.py`, `labels/label_engine.py`, `labels/safety_zone.py`, `labels/leakage_guard.py`

---

### M4 — 表型分析与参考模型（已完成 ✅）

**目标**：输出 Table 1、2×2 因子分析，支撑论文 1。

**完成标准：**
- [x] Table 1 输出（四组，含 SD / IQR，`stats/table1.py`）
- [x] HTN × EIH 双因素效应分析（主效应 + 交互效应）
- [x] reference-normal 参考方程 / %pred / z-score 跑通
- [x] 关键指标分组差异图（箱线图 / 小提琴图）
- [x] 协议分层敏感性分析

**关键模块**：`stats/table1.py`, `stats/twobytwo.py`, `stats/reference_builder.py`, `stats/plots.py`

---

### M5 — P0/P1 主模型跑通（论文 2 核心）（已完成 ✅）

**目标**：完成基线 + 主模型训练、校准、SHAP 解释，支撑论文 2。

**完成标准：**
- [x] P0：LASSO 基线 + XGBoost 主模型（AUC、AUPRC、Brier score）
- [x] P1：Ordinal Logistic 基线 + LightGBM/CatBoost 主模型（F1_macro、kappa）
- [x] 含 BP / 不含 BP 双版本对照完成
- [x] 踏车主模型 + 全样本模型一致性分析完成
- [x] 校准曲线（isotonic）+ DCA 完成
- [x] SHAP global + 个体解释图
- [x] 测试集结果报告 `p0_model_report.md` + `p1_model_report.md` 生成

**关键模块**：`modeling/train_p0.py`, `modeling/train_p1.py`, `modeling/calibrate.py`, `modeling/evaluate.py`, `modeling/interpret.py`

---

### M6 — 锚点资产 + Bridge Prep 包跑通（已完成 ✅）

**目标**：固化阶段 I 对阶段 III 的上游输出。

**完成标准：**
- [x] `make anchors` 成功：`anchor_table.parquet`（含 `reserve_axis`, `threshold_axis`, `instability_axis`, `a_lab_vector`, `s_lab_score`, `z_lab_zone`）
- [x] `make bridge-prep` 成功：输出以下全部文件：
  - `anchor_variable_dictionary_v1.md`
  - `home_proxy_hypothesis_table_v1.csv`
  - `bridge_sampling_priority_list_v1.md`
  - `bridge_question_list_v1.md`
  - `bridge_prep_package_manifest.json`
- [x] `contract_snapshot.json` 生成并通过 `bridge_contract.py` 验证

**关键模块**：`anchors/anchor_builder.py`, `anchors/export_anchor_package.py`, `bridge_prep/proxy_hypothesis.py`, `bridge_prep/export_bridge_prep.py`, `contracts/bridge_contract.py`

---

### M7 — 报告 + 冻结版发布（v1.0.0-stage1）

**目标**：产出阶段 I 第一版论文复现实验包。

**完成标准：**
- [x] `make reports` 一键生成 Markdown 报告
- [x] `reports/release/` 有冻结结果（含模型指标、图表、config 快照）
- [x] README 可指导他人基于 synthetic demo 数据复现全流程
- [x] `bridge_prep_pkg_v1` 打包
- [x] 创建 Git tag `v1.0.0-stage1`（2026-04-16 已创建）

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

| 版本类型 | 当前 | 下一步 |
|---|---|---|
| 代码版本 | `v3.1.0`（论文三轮修订完成，784 测试通过）| 待定（前瞻性验证队列 / Stage II）|
| 论文状态 | `v3.1.0`（三份 PDF 编译完成，语言自然化完成）| 投稿准备（伦理批号填充 + 作者信息）|
| 数据快照 | N=3,232（4组 Excel，2015–2023）| 待扩充 |
| Stage 1B 管线 | `make stage1b` 全通过，验收 **Accept** | — |
| 数据契约 | `contract_v1`（schema 定义）| `contract_v2_bridge_ready`（Stage II 时启动）|
| 锚点/Bridge 准备包 | `anchor_pkg_v1`（M6 ✅）| Stage II 启动时更新 |

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

---

## 十五、Post-M7 论文准备与模型改善（2026-04-16 新增）

> 版本：v1.0.0-stage1（M1–M7 全部完成，414 测试，3206 条真实数据）
> 论文策略：合并为**一篇论文**（表型 + 模型），先按通用学术格式（中文 + 英文版）

### 数据现状关键发现（影响后续策略）

| 类别 | 状态 | 影响 |
|---|---|---|
| 药物列（30列）| **全部为0**，不可用 | P0 无法用药物特征 |
| 合并症（diabetes 等）| **全部为0**，不可用 | 组间差异分析受限 |
| hr_recovery | 97.8% 完整，与现有 P1 特征低相关（r<0.06）| ✅ P1 重要新特征 |
| oues | 99.3% 完整，独立信号（r<0.16）| ✅ P1 新特征 |
| mets_peak | 99.7% 完整，与 vo2_peak 相关仅 0.179 | ✅ P1 新特征 |
| ve_peak | 99.3% 完整，但与 vo2_peak 高相关（0.77）| ⚠ 慎用 |
| BMI | 缺失，但可从 height_cm + weight_kg 派生 | ✅ P0 新特征 |
| htn_years | 52.6% 完整 | ✅ P0 新特征（中位填充） |
| 静息 BP/HR/LVEF | 完全缺失 | ❌ P0 性能上限约束 |
| P1 zone 分布 | EIH+ 100% Red（结构性问题）| 需 label_rules_v3.yaml |

### 论文定位

**合并一篇论文**，核心叙事：
1. **前半部分（表型分析）**：扎实的临床发现（2×2 ANOVA 效应量大，可发表）
2. **后半部分（ML 建模）**：方法学探索 + 诚实报告 + leakage guard 方法学贡献
3. **弱模型性能**：定位为 "summary-level CPET 数据的预测天花板"，强调阶段 II 必要性

**论文标题**：
- 中文：老年高血压人群心肺运动试验安全分区特征研究——基于 HTN×EIH 2×2 设计的表型分析与机器学习分层模型（N=3,206）
- 英文：Safety Zone Characterization in Elderly Hypertensive Patients Using Cardiopulmonary Exercise Testing: A 2×2 HTN×EIH Phenotypic and Machine Learning Classification Study (N=3,206)

### Phase A：补充分析（目标 → v1.1.0）

#### A1. SHAP 解释（当前为占位符）
- 修改 CLI `model interpret` 接通 `src/cpet_stage1/modeling/interpret.py`
- 在 interpret 命令中重新训练（数据小，几秒），对 trained model 跑 SHAP
- 产出：`reports/figures/m5/shap_summary_p0_xgb.png`, `shap_summary_p1_lgbm.png` 等 6-8 张
- 涉及：`modeling/interpret.py`，`cli.py`

#### A2. 补充统计分析
| 分析 | 目的 | 新文件 |
|---|---|---|
| Dunn's post-hoc 两两比较 | KW 检验 omnibus 后各组差异 | `stats/posthoc.py` |
| EIH 多因素 Logistic 回归 | 独立预测因子（age/sex/VO2peak/HTN→EIH）| `stats/logistic_eih.py` |
| P1 zone 按队列分层性能 | EIH- 子群 P1 性能（应优于整体）| 扩展模型评估 |
| 数据缺失模式图 | 展示字段缺失程度 | 扩展 `stats/plots.py` |

#### A3. 补充图表（目标新增 ≥8 张）
| 图表 | 类型 | 用途 |
|---|---|---|
| SHAP summary (P0 + P1) | 蜂群图/条形图 | 特征重要性 |
| Zone 分布堆叠柱状图（by 2×2 cohort）| 堆叠柱状图 | EIH+ 全红关键发现 |
| 缺失数据热力图 | 矩阵热力图 | 方法学展示 |
| EIH Logistic 回归森林图 | 森林图 | OR 值可视化 |
| P0 trigger Venn/UpSet | 集合图 | 三种触发条件重叠 |
| 特征相关热力图 | Heatmap | 特征关系 |
| P1 按 EIH+/EIH- 分层性能 | 对比柱状图 | 分层分析 |
| 安全区概念示意图 | R/T/I 框架图 | 论文核心概念 |

#### A4. 亚组分析
- 性别分层：男/女分别跑 Table 1 + zone 分布
- 年龄分层：按中位年龄（67岁）分层
- Beta-blocker 亚组：❌ 不可行（全为0）
- effort_adequate 分层：分层 P1 性能

### Phase B：写论文初稿（→ v1.1.0）

#### 论文结构
```
1. 引言（1.5页）：背景→CPET现状→研究目的
2. 方法（4-5页）：
   2.1 研究人群与设计（单中心回顾性，2×2，N=3206）
   2.2 CPET 测试方案与变量定义
   2.3 质量控制管线（5层QC + leakage guard）
   2.4 安全区定义（P0先验+P1后验+R/T/I锚点）
   2.5 统计分析（Table1+2×2ANOVA+参考方程+post-hoc）
   2.6 机器学习模型（P0: LASSO+XGB; P1: OrdLogistic+LightGBM+CatBoost）
3. 结果（4-5页）：
   3.1 基线特征（Table 1）
   3.2 HTN×EIH 交互效应（Table 2=ANOVA，Figure 1=交互图）
   3.3 参考方程（Table 3，Figure 2=散点图）
   3.4 安全区分布（Figure 3=堆叠柱状图，P0 trigger 分析）
   3.5 P0 预测（Table 4，Figure 4=ROC+SHAP）
   3.6 P1 分类（Table 5，Figure 5=混淆矩阵+SHAP）
4. 讨论（3-4页）：主要发现→文献对比→Leakage Guard方法学→临床意义→局限性→未来方向
5. 结论
补充材料：数据字典、QC报告、参考方程系数、泄漏保护列表
```

#### LaTeX 实现
- 中文版：`paper/main_cn.tex`（ctexart + gbt7714）
- 英文版：`paper/main_en.tex`（article + numeric style）
- 复用 `review_article/` gbt7714 本地编译方案
- 图表：从 `reports/figures/` 复制至 `paper/figures/`

### Phase C：模型改善（→ v1.2.0）

#### C1. P0 特征扩展（6→8）
| 新特征 | 来源 | 完整度 |
|---|---|---|
| bmi（派生）| height_cm + weight_kg | 99.6% |
| htn_years | 直接可用 | 52.6%（中位填充）|

#### C2. P1 特征扩展（4→7，重点）
| 新特征 | 完整度 | 相关性 |
|---|---|---|
| hr_recovery | 97.8% | r<0.06（自主神经功能）|
| oues | 99.3% | r<0.16（独立信号）|
| mets_peak | 99.7% | r=0.18 vs vo2_peak |

**预期**：F1_macro 0.47 → 0.52-0.58

#### C3. P1 标签规则调整（核心）
**问题**：EIH+ 患者 100% Red（EIH-Red 公理），但 eih_status 被 leakage_guard 排除，模型无法学习

**方案 A（推荐）**：创建 `label_rules_v3.yaml`，P1 zone 移除 EIH 条件，纯基于心肺储备指标
- 预期 Red 占比从 24.9% 降至约 8-12%
- 模型真正学到心肺储备模式

**方案 B**：保留当前标签，在论文中报告 EIH+/EIH- 分层性能

**执行**：两者都做，在论文中对比呈现

#### C4. 代价敏感训练
- 增大 Red 类权重（3-5倍），提升 Red 召回率（当前仅 26%）
- 修改 `configs/model/p1_lgbm.yaml` + `p1_catboost.yaml`

#### C5. 参考方程 z-score 作为特征（保守策略）
- 仅用 hr_peak_zpred 和 o2_pulse_peak_zpred（非泄漏字段的 z-score）
- 涉及文件：`configs/features/feature_config_v1.yaml` → `feature_config_v2.yaml`

### Phase A/C 执行结果（2026-04-21 实际跑出）

#### 产出清单

- `reports/p0_model_report_v2.md` — P0 v2（feature_config_v2 + label_rules_v3），AUC=0.582
- `reports/p1_model_report_v2.md` — P1 v2（7特征），LightGBM F1=0.4646，CatBoost F1=0.4651
- `reports/p1_model_report_cost_sensitive.md` — P1 代价敏感版（class_weight Red=4×）
- SHAP 图：`reports/figures/shap/`（16 张，P0/P1 各 8 张）
- 补充图表：`reports/figures/supplement/`（4 张）
  - `zone_distribution_stacked_z_lab_zone.png`
  - `missing_data_heatmap.png`
  - `eih_logistic_forest.png`
  - `safety_zone_concept.png`

#### v1（标准版）→ v2（扩展特征）指标对比

| 模型 | v1 F1_macro | v2 F1_macro | 提升 |
|---|---|---|---|
| P0 LightGBM | AUC=0.582 | AUC=0.582 | — |
| P1 LightGBM | 0.4646 | 0.4646 | 特征受限无变化 |
| P1 CatBoost | 0.4651 | 0.4651 | — |

#### 代价敏感版对比（v2 基线 vs cost-sensitive）

| 模型 | 标准版 F1 | 代价敏感版 F1 | Red Recall 标准 | Red Recall CS |
|---|---|---|---|---|
| LightGBM | 0.4646 | 0.3924 | 38/159=23.9% | 85/159=53.5% |
| CatBoost | 0.4651 | 0.1871 | — | 153/159=96.2%（退化为全 red）|

#### 结论

- **LightGBM 代价敏感**成功：牺牲 F1_macro (-0.07) 换取 Red recall 提升 (+29.6%)，符合临床安全优先原则
- **CatBoost 代价敏感**仍有问题：sample_weight 修复使 RandomizedSearchCV 可运行（F1 从 0.1332→0.1871），但模型仍偏向预测 red；根本原因是 CatBoost 的 sample_weight CV 行为与 class_weights 参数存在差异，待 Phase D 专项调查
- **主推模型**：LightGBM v2（F1=0.4646）用于论文报告；LightGBM CS 版（Red recall=53.5%）作为安全优先敏感性分析

### Phase D：修订论文（→ v1.3.0）✅ 完成（2026-04-21）

**完成内容：**
- `paper/main_cn.tex` 全面重写：填充所有 XX 占位符，新增 7 张表格，启用 7 张图表，重写 Discussion
- `paper/main_en.tex` 同步更新：英文版与中文版完全一致
- `paper/references.bib` 从 10 条扩充至 28 条
- `paper/figures/` 填充 7 张图表
- `src/cpet_stage1/stats/subgroup.py` 修复亚组 zone 分布 0.0% bug（整数→字符串映射）
- **关键修正**：VO₂peak 交互效应不显著（F=0.02, p=0.894）；最优 P1 模型为 CatBoost F1=0.4991
- 453 测试通过

### 实施顺序

```
Step 1（Phase A）：SHAP CLI接通 + post-hoc + EIH Logistic + 新图表 + 亚组分析
Step 2（Phase B）：paper/ 目录 + LaTeX 模板 + 论文初稿（中英）
Step 3（Phase C）：feature_config_v2 + label_rules_v3 + BMI派生 + 重跑管线 + 代价敏感
Step 4（Phase D）：修订论文 + 最终校对
```

### 验证标准

| 阶段 | 验收条件 |
|---|---|
| Phase A | SHAP 图存在 + post-hoc 报告生成 + 新增图表 ≥ 8 张 |
| Phase B | `paper/main_cn.tex` + `paper/main_en.tex` 可编译 |
| Phase C | P1 F1_macro ≥ 0.52（7特征版本）+ 新旧对比表存在 |
| Phase D | 论文中所有数字与最终模型结果一致 |

---

### Phase G：方法学优化（→ v2.0.0）

> 针对 Stage I 根本问题（P1 循环依赖）的三种创新方法，构成"数据驱动安全区方法学"体系。

#### Method 1：结局锚定安全区

**目标**：以 `test_result` 为结局直接建模，消除 P1 循环依赖。

| 文件 | 操作 |
|---|---|
| `src/cpet_stage1/modeling/train_outcome.py` | 新建：LightGBM 结局锚定训练管线 |
| `src/cpet_stage1/labels/outcome_zone.py` | 新建：概率→安全区转换 |
| `src/cpet_stage1/labels/leakage_guard.py` | 修改：新增 `task="outcome"` 路径 |
| `configs/model/outcome_lgbm.yaml` | 新建：结局锚定模型配置 |
| `tests/test_outcome_model.py` | 新建：单元测试 |

**验收**：结局锚定 AUC > 0.65（test_result 预测，消除循环依赖后）

#### Method 2：多变量异常评分

**目标**：Mahalanobis 距离捕获多维协方差偏离，D² 与 test_result 相关 r > 0.10。

| 文件 | 操作 |
|---|---|
| `src/cpet_stage1/stats/anomaly_score.py` | 新建：Mahalanobis 距离计算 |
| `configs/stats/anomaly_config.yaml` | 新建：变量选择和分层配置 |
| `tests/test_anomaly_score.py` | 新建：单元测试 |

**验收**：D² 与 test_result 相关 r > 0.10，参考子集内 P75/P95 切点计算正确

#### Method 3：多定义一致性框架

**目标**：量化多定义间一致性，标记不确定区域，高信度子集 ≥ 55%。

| 文件 | 操作 |
|---|---|
| `src/cpet_stage1/labels/concordance_ensemble.py` | 新建：一致性投票框架 |
| `configs/data/concordance_config.yaml` | 新建：投票源配置 |
| `tests/test_concordance.py` | 新建：单元测试 |

**验收**：高信度子集 ≥ 55%，不确定区 test_result 阳性率介于 Green/Red 之间

#### Phase G 实施顺序

```
Step 1-3: 更新 PLANNING.md / DEVLOG.md / CLAUDE.md（文档）
Step 4:   Method 1 — 结局锚定安全区（最高优先，解决根本问题）
Step 5:   Method 2 — Mahalanobis 异常评分（增强 R/T/I 框架）
Step 6:   Method 3 — 一致性框架（整合所有定义）
Step 7:   pytest tests/ -q（全部通过，预期 520+）
Step 8:   更新 DEVLOG.md 会话结束条目
```

#### Phase G 验证标准

| 方法 | 验收条件 |
|---|---|
| Method 1 | AUC > 0.65（test_result 预测），leakage_guard outcome 路径通过 |
| Method 2 | D² vs test_result r > 0.10，P75/P95 切点合理 |
| Method 3 | 高信度子集 ≥ 55%，区内 test_result 阳性率 Green < Yellow < Red |
| 全部 | pytest 全通过（预期 520+），论文叙事更新 |

---

## 八、Stage 1B 方法学主线（v2.3.0 →）

> **启动日期**：2026-04-22
> **核心转变**：从"预测 Green/Yellow/Red 的模型"→"基于 summary-level CPET 的实验室安全表型原型"
> **旧主线状态**：冻结为 legacy（`reports/legacy/`，`data/labels/legacy/`）

### Stage 1B 研究问题定位

> "在 summary-level CPET 条件下，构建一个用于实验室解释的运动安全表型原型，其输出由表型负担、不稳定覆盖规则和不确定性三部分组成，并以 `test_result` 作为外部锚定进行结构效度验证。"

### Stage 1B 五个产品对象

1. **Reference package** — 条件参考区间与 reference-normal subset
2. **Phenotype burden score (`P_lab`)** — 与正常参考的偏离程度
3. **Instability flags (`I_flag`)** — 测试过程中的安全相关警报条件
4. **Final zone (`Z_final`)** — phenotype zone + instability override 合成
5. **Confidence / indeterminate (`C_final`)** — 哪些样本可高信度解释，哪些不能

### Stage 1B 变量分层（详见 `configs/data/variable_roles_stage1b.yaml`）

| 类别 | 进入哪里 | 禁止进入哪里 |
|---|---|---|
| 表型主体（Phenotype） | burden 计算 → phenotype zone | 监督标签定义 |
| 不稳定信号（Instability） | override 规则 | burden 均值 |
| 验证变量（Validation） | 结构效度分析、confidence engine | zone 定义 |
| 禁用变量（Excluded） | 无 | 一切特征集 |

### Stage 1B 执行顺序

| 步骤 | 内容 | 输出文件 | 状态 |
|---|---|---|---|
| Step 1 | 冻结旧主线 + 变量角色定义 | `reports/legacy/`, `variable_roles_stage1b.yaml` | ✅ v2.3.0 |
| Step 2 | 条件分位参考建模 | `reference_quantiles.py`, `reference_spec_stage1b.yaml` | ✅ v2.4.0 |
| Step 3 | Phenotype Burden Engine | `phenotype_engine.py` | ✅ v2.4.0 |
| Step 4 | Instability Override Engine | `instability_rules.py` | ✅ v2.4.0 |
| Step 5 | Confidence Engine | `confidence_engine.py` | ✅ v2.4.0 |
| Step 6 | Outcome-Anchor 验证 + Anomaly Audit | `train_outcome_anchor.py`, `anomaly_audit.py` | ✅ v2.4.0 |
| Step 7 | Stage1B 报告聚合 + 全管线集成 | `stage1b_report.py`, pipeline CLI | ✅ v2.4.0 |
| Step 8 | 论文重写（表型原型叙事） | `main_cn.tex`, `main_en.tex` | ✅ v2.4.0 |

### Stage 1B 新增核心模块

```
src/cpet_stage1/stats/reference_quantiles.py     — 条件分位参考建模
src/cpet_stage1/anchors/phenotype_engine.py      — 表型负担引擎
src/cpet_stage1/anchors/instability_rules.py     — 不稳定覆盖规则
src/cpet_stage1/anchors/confidence_engine.py     — 置信度引擎
src/cpet_stage1/modeling/train_outcome_anchor.py — outcome-anchor 验证模型
src/cpet_stage1/stats/anomaly_audit.py           — 异常表型审计
src/cpet_stage1/reporting/stage1b_report.py      — 聚合报告
configs/data/variable_roles_stage1b.yaml         — 变量角色定义
configs/data/reference_spec_stage1b.yaml         — 参考子集规格
configs/data/zone_rules_stage1b.yaml             — Zone规则（已从模板复制）
```

### Stage 1B 验收标准

| 验收层级 | 条件 |
|---|---|
| **Accept** | reference 稳定 + phenotype zone 可解释 + final zone 对 test_result 有单调梯度 + high confidence 存在且更稳 |
| **Warn** | reference 过窄 / confidence 过多 indeterminate / no-BP 差异过大 |
| **Fail** | reference 中 red 大量出现 / final zone 与 test_result 无方向性 / confidence 全靠一个分量 |

### Stage 1B 实际运行结果（v2.7.0，2026-04-22）

**验收判定：Accept**

| 指标 | 值 | 验收标准 |
|---|---|---|
| 严格参考子集 N | 903（27.9%）| — |
| 参考子集低危比例 | 69.2% | >50% ✅ |
| 参考子集高危比例 | 10.2% | <15% ✅ |
| 结构效度梯度 | Green 14.0% < Yellow 15.1% < Red 18.0%（Cochran-Armitage p=0.025）| 严格单调 ✅ |
| 高置信度比例 | 33.0% | ≥10% ✅ |
| 不确定层 | 24.9%（805例）| 方法学合理 |
| Outcome-Anchor 验证 AUC | CV 0.564±0.016，Test 0.608 | 处于信息量合理范围 ✅ |

---

## 十六、论文投稿准备状态（v3.1.0）

> 更新日期：2026-04-23

### 当前状态

| 文件 | 版本 | 状态 |
|---|---|---|
| `paper/main_cn.tex` | v3.1.0 | ✅ 可编译（18页）；术语全清；语言自然化完成 |
| `paper/main_en.tex` | v3.1.0 | ✅ 可编译（21页）；术语全清；语言自然化完成 |
| `paper/supplementary.tex` | v3.1.0 | ✅ 可编译（7页）；内容完整 |
| `paper/references.bib` | — | ✅ ~125条，去重，格式正确 |

### 三轮修订历史

| 轮次 | 版本 | 重点 |
|---|---|---|
| Round 1 | v2.9.0 | 消除开发术语（Stage 1B/pipeline/final_zone 等 ~130处），重写为学术 IMRAD 格式 |
| Round 2 | v3.0.0 | 评审专家视角精确修复（EIH→EHT 全文替换；N=359修正；Cochran-Armitage p=0.025；η²_p规范化等 ~95处）|
| Round 3 | v3.1.0 | 语言自然化（消除机器翻译痕迹：汇总级→汇总指标；构念污染/效度→概念混淆/结构效度；临床结局代理→替代指标；显式→明确等 ~60处）|

### 投稿前剩余 TODO

| 项目 | 说明 |
|---|---|
| 伦理批号 | `\textcolor{red}{TODO: 填写批准号}` 需替换为真实批号 |
| 作者信息 | `\textcolor{red}{TODO: 作者姓名}` 和 `\textcolor{red}{TODO: 单位名称}` 需填充 |
| 目标期刊 | 根据目标期刊要求调整格式（字数限制、摘要字数、参考文献格式）|
| 图片分辨率 | 投稿时检查 `paper/figures/` 中图片 DPI 是否满足期刊要求（通常 ≥300 dpi）|
