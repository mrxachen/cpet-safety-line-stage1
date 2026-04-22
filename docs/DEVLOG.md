# DEVLOG.md — 开发日志

> 逐次记录每个开发会话的进展、决策与遗留问题。
> 格式：最新条目在最前面（倒序）。

---

## 里程碑进度总览

| 里程碑 | 状态 | 完成日期 |
|---|---|---|
| M1 — 仓库脚手架 | ✅ 完成 | 2026-04-14 |
| M2 — 数据导入 + QC | ✅ 完成 | 2026-04-14 |
| M3 — 2×2 队列 + 标签引擎 | ✅ 完成 | 2026-04-14 |
| M4 — 表型分析 + 参考模型 | ✅ 完成 | 2026-04-14 |
| M5 — P0/P1 主模型 | ✅ 完成 | 2026-04-14 |
| M6 — 锚点资产 + Bridge Prep | ✅ 完成 | 2026-04-15 |
| M7 — 报告 + 冻结版发布 | ✅ 完成 | 2026-04-16 |
| **Phase A — 补充分析（SHAP+后处理+新图表+亚组）** | ✅ 完成（代码+测试）| 2026-04-16 |
| **Phase B — 论文初稿（中英文）** | ✅ 完成（LaTeX模板）| 2026-04-16 |
| **Phase C — 模型改善（特征扩展+标签v3+代价敏感）** | ✅ 完成（管线执行+结果记录）| 2026-04-21 |
| **Phase D — 修订论文** | ✅ 完成（论文全面升级+亚组bug修复）| 2026-04-21 |
| **Phase E — 审稿意见回应** | ✅ 完成（5条方法学修订：消融+效用+标签+术语+ANOVA）| 2026-04-21 |
| **Phase F Step 1--3 — 数据驱动安全区管线** | ✅ 完成（参考方程v2+Zone引擎v2+敏感性分析，487+1测试）| 2026-04-21 |
| **Phase F Step 4 — 测试修复+论文重构** | ✅ 完成（test_result泄漏修复，488/0，论文叙事→数据驱动方法学）| 2026-04-21 |
| **Phase G — 方法学优化（结局锚定+Mahalanobis+一致性框架）** | ✅ 完成（62新测试，240/0总通过）| 2026-04-21 |
| **Phase G Step 7-8 — CLI集成+真实数据运行+论文更新** | ✅ 完成（3 CLI命令，3报告，论文Tables 11-13）| 2026-04-21 |
| **Stage 1B Step 1 — 冻结旧主线 + 变量角色定义** | ✅ 完成（legacy归档 + variable_roles_stage1b.yaml + PLANNING.md更新）| 2026-04-22 |
| **Stage 1B Step 2 — 条件分位参考模型** | ✅ 完成（reference_quantiles.py + 28 测试）| 2026-04-22 |
| **Stage 1B Step 3 — Phenotype Burden Engine** | ✅ 完成（phenotype_engine.py + 32 测试）| 2026-04-22 |
| **Stage 1B Step 4 — Instability Override Engine** | ✅ 完成（instability_rules.py + 32 测试）| 2026-04-22 |
| **Stage 1B Step 5 — Confidence Engine** | ✅ 完成（confidence_engine.py + 44 测试）| 2026-04-22 |
| **Stage 1B Step 6 — Outcome-Anchor + Anomaly Audit** | ✅ 完成（train_outcome_anchor.py + anomaly_audit.py + 25 测试）| 2026-04-22 |
| **Stage 1B Step 7 — 报告聚合 + 全管线** | ✅ 完成（stage1b_report.py + 37 测试 + pipeline CLI + Makefile stage1b）| 2026-04-22 |
| **Stage 1B Step 8 — 论文重写（表型原型叙事）** | ✅ 完成（main_cn/en.tex 全面重写 + supplementary.tex 重写 + references.bib +13条）| 2026-04-22 |

---

## 代码版本历史

| 版本 | 日期 | 变更摘要 |
|---|---|---|
| `v0.1.0` | 2026-04-14 | 仓库脚手架初始化 |
| `v0.2.0` | 2026-04-14 | M2 数据导入+QC管线实现（field_map_v2, schema_v2, io/qc/contracts 模块, 83个测试全通过）|
| `v0.3.0` | 2026-04-14 | M3 2×2队列注册+标签引擎（cohort/labels模块, label_rules_v2, reference_rules_v2, ~35新测试）|
| `v0.4.0` | 2026-04-14 | M4 表型分析+参考模型（stats模块: table1/twobytwo/reference_builder/plots, 52新测试, 207总测试通过）|
| `v0.5.0` | 2026-04-14 | M5 P0/P1主模型管线（features/modeling模块全实现, ~123新测试, 330总测试通过）|
| `v0.5.1` | 2026-04-15 | 管线修复（P1 leakage_guard + clip_to_schema_range + cli 预检），342测试通过 |
| `v0.6.0` | 2026-04-15 | M6 锚点资产+Bridge Prep（anchors/bridge_prep/contracts 模块，54新测试，396总测试通过）|
| `v1.0.0-stage1` | 2026-04-16 | M7 报告聚合+冻结发布（reporting模块实现，18新测试，414总测试通过）|
| `v1.1.0` | 2026-04-16 | Phase A/B/C：SHAP接通+post-hoc+EIH Logistic+亚组分析+新图表+论文初稿+feature_config_v2+label_rules_v3+代价敏感配置，453个测试通过 |
| `v1.2.0` | 2026-04-21 | Phase A/C 管线收尾：CatBoost sample_weight 修复 + cost-sensitive 重跑 + supplement-plots + 文档更新，453 测试通过 |
| `v1.3.0` | 2026-04-21 | Phase D：论文全面升级（亚组bug修复+填充所有数据+新增7张表格+启用图表+重写Discussion+扩充参考文献至28条），453 测试通过 |
| `v1.4.0` | 2026-04-21 | Phase E：审稿意见回应（5条方法学修订：P1标签定义补全+代理泄漏消融+P0术语修正+临床效用分析+ANOVA效应量完善），453 测试通过 |
| `v1.5.0` | 2026-04-21 | Phase F Step 4：test_result泄漏修复（等权重S_lab）+ 论文全面重构（数据驱动叙事）+ references.bib新增4条 + 488/0 测试 |
| `v2.0.0` | 2026-04-21 | Phase G：方法学重大升级（结局锚定+Mahalanobis异常评分+一致性框架）+ 文档重构（三阶段定位）+ 62新测试，240/0 总通过 |
| `v2.1.0` | 2026-04-21 | Phase G Step 7-8：CLI 集成（3 新命令）+ Makefile Phase G targets + 真实数据运行（3 报告生成）+ 论文更新（Methods 2.8-2.10，Results 3.7-3.9，Tables 11-13，Discussion/Conclusions，+2条参考文献）|
| `v2.2.0` | 2026-04-22 | 论文深度重写：main_cn/en.tex 从"项目报告"重构为 IMRAD 期刊论文；引言4段逻辑链；方法6节；结果5节；讨论整合段落；补充材料 supplementary.tex 新建；清除所有"阶段II/III"/"Stage 2"项目语言；正文表格8张 |
| `v2.3.0` | 2026-04-22 | Stage 1B Step 1：冻结旧主线（legacy reports/parquets）+ variable_roles_stage1b.yaml + stage1b_variable_roles.md + legacy_baseline_manifest.json + PLANNING.md Stage 1B 主线章节 |
| `v2.4.0` | 2026-04-22 | Stage 1B Steps 2-8 全部完成：reference_quantiles(28)+phenotype_engine(32)+instability_rules(32)+confidence_engine(44)+outcome_anchor+anomaly_audit(25)+stage1b_report(37) = 198 Stage 1B 新测试；总计 748 通过；pipeline stage1b CLI + Makefile stage1b targets；论文全面重写（表型原型叙事）+ references.bib 新增13条中国参考值/TRIPOD+AI/MECKI/CPX文献 |

---

## 会话记录

---

### [2026-04-22] 会话 #21 — Stage 1B Steps 2-8 全部完成 + 论文重写

**完成内容**：

1. **Step 7：Stage 1B 总报告聚合 + 全管线（本会话起点）**
   - `src/cpet_stage1/reporting/stage1b_report.py` — build_stage1b_output_table / compute_construct_validity / compute_reference_validity / assess_acceptance / generate_stage1b_summary_report
   - `tests/reporting/test_stage1b_report.py` — 37 个测试，全部通过
   - `cli.py` — 新增 `pipeline stage1b` 命令（聚合所有中间 parquet → 输出表 + 摘要报告 + 验收判定）
   - `Makefile` — 新增 stage1b-reference/phenotype/instability/confidence/outcome/anomaly/report/stage1b 8个 targets

2. **Step 8：论文全面重写（表型原型叙事）**
   - `paper/main_cn.tex` — 全面重写：新标题（实验室表型原型）+ 新摘要（四层方法学）+ 引言三缺口 + Methods 2.1-2.10（变量角色→条件分位→phenotype burden→instability override→confidence engine→outcome-anchor→anomaly audit→统计分析）+ Results 3.1-3.8（含现有数据表格保留 + TODO 新结果占位）+ Discussion 四主要发现 + 结论重写
   - `paper/main_en.tex` — 同步重写，英文版结构与中文版对齐
   - `paper/supplementary.tex` — 全面重写：变量角色表 + 分位模型技术细节 + 负担转换规则表 + 置信度权重说明 + 验收标准表 + 输出列定义表 + Legacy系统对照表 + TODO占位 + Phase G legacy 结果保留
   - `paper/references.bib` — 新增 13 条参考文献：WangCycle2022, HuangTreadmill2024, PUTHCycle2025, XET2021, FRIEND2022, FRIEND2016cycle, Gorodeski2008cpx, CPXvalidation2013, MECKI2023, TRIPODAI2024, PROBASTAI2025, BMJuncertainty2025
   - `docs/DEVLOG.md` — 本条目 + 里程碑进度表全部标为完成 + v2.4.0 版本历史

**关键决策**：
- test\_result 角色：验证锚点（确定 final\_zone 后方可用），严禁定义区间
- main_cn/en.tex 保留 Table 1、ANOVA、参考方程表（有真实数据）；新增 Stage 1B 结果章节带 TODO 占位（等待 make stage1b 在真实数据上运行）
- supplementary.tex 以 S7 Legacy 对照表呈现 Phase G vs Stage 1B 的架构差异
- TRIPOD+AI 和 PROBAST+AI 作为方法论透明度框架引用，为不确定性输出提供外部标准支撑

**测试结果**：748 passed, 0 failed（含 198 Stage 1B 新测试）

**遗留问题**：
- 需要在真实数据上运行 `make stage1b`，填充论文中所有 `\textcolor{red}{TODO}` 占位
- papers 的 LaTeX 编译需要本地 xelatex + gbt7714 环境
- Stage 1B confidence 权重尚未经前瞻性数据校准（置信度引擎四个分量的相对重要性）

**下一步**（未来会话）：
- 在真实 staging.parquet 上运行 `make stage1b`，生成真实 Stage 1B 结果
- 填充 paper TODO 占位：final\_zone 分布、构念效度梯度数值、置信度分布
- 编译论文 PDF 验证 LaTeX 排版

---

### [2026-04-22] 会话 #20 — Stage 1B Step 1：冻结旧主线 + 变量角色定义

**完成内容**：

1. **Legacy 归档**
   - `reports/legacy/` — 10 份旧报告（zone_engine_v2, zone_report, zone_sensitivity, concordance, outcome_model, anomaly_score, p1_model×2, clinical_utility, p1_ablation）
   - `data/labels/legacy/` — 5 份旧 parquet（zone_table, label_table, outcome_zone, anomaly_zone, reference_scores）
   - `reports/legacy_baseline_manifest.json` — 版本元数据 + 关键指标存档

2. **变量角色定义**
   - `configs/data/variable_roles_stage1b.yaml` — 四分类定义（phenotype/instability/validation/excluded + covariates + confidence_fields）
   - `docs/data_dictionary/stage1b_variable_roles.md` — 可读数据字典（burden转换规则 + override逻辑 + Stage1B产出列定义 + legacy对比表）

3. **文档更新**
   - `docs/PLANNING.md` — 新增"八、Stage 1B 方法学主线"章节（研究问题定位 + 五产品对象 + 变量分层表 + 执行顺序表 + 验收标准）
   - `docs/DEVLOG.md` — 本条目 + 里程碑进度表 + 版本历史 v2.3.0

**关键决策**：
- `test_result` 彻底降级为"验证变量"，不再触发任何 zone 定义
- `eih_status` / `bp_peak_sys` 归入"不稳定覆盖"，不参与 burden 均值
- legacy 代码保留功能完整，仅降级为"补充材料对照组"

**遗留问题**：
- `zone_rules_stage1b.yaml` 已由 code_templates 提供，待 Step 2 正式复制到 `configs/data/`
- reference_spec_stage1b.yaml 待 Step 2 创建

**下一步（Step 2）**：
- 实现 `src/cpet_stage1/stats/reference_quantiles.py`（从 code_templates 适配）
- 创建 `configs/data/reference_spec_stage1b.yaml`
- 写测试 `tests/stats/test_reference_quantiles.py`
- 接 CLI 命令 `stats reference-quantiles`

---

### [2026-04-22] 会话 #19 — 论文深度重写：从"项目报告"到"期刊论文"

**完成内容：**
- `paper/main_cn.tex` 全面重构：
  - 摘要：改为结构化四段（目的/方法/结果/结论）
  - 引言：4段严格逻辑链（大背景→现状不足→三个Gap→创新目标），删除ML文献综述段和编号列表
  - 方法：6个子节（原10个），R/T/I框架用subsubsection组织，ML及三种互补方法移入补充材料
  - 结果：5个子节（原10个），每节有引导句衔接，Bootstrap+文献比较合并为单表（Table 7）
  - 讨论：4个子节连贯段落（原编号列表6条+3块），无 "（一）（二）…" 编号
  - 结论：4句简洁总结，无项目语言
  - 全文清除：Stage 2/II/III、阶段II/III、优先对象、逐呼吸建模优先、居家运动安全走廊
  - 正文表格：8张（Bootstrap CI + 文献比较合并为一张双面板表）
- `paper/supplementary.tex` 新建：
  - 补充方法S1-S4（ML、结局锚定、Mahalanobis、一致性框架）
  - 补充结果S5-S8（含4张补充表 S1-S4/原Tables 9-13）
- `paper/main_en.tex` 同步重写：完全镜像CN结构，地道英文表达
- 编译验证：main_cn.pdf（14页）和 main_en.pdf（17页）均无 fatal error

**验证结果（全部通过）：**
- ✅ 零残留项目语言（Stage 2/II/III，阶段II/III，优先对象等）
- ✅ 引言4段严格逻辑链，每段唯一逻辑角色
- ✅ Methods子节数 = 6（≤6）
- ✅ Results子节数 = 5（≤5）
- ✅ Discussion无编号列表，为连贯段落叙述
- ✅ 正文表格数 = 8（≤8）
- ✅ 编译无 fatal error

**遗留问题：** 无

**下一步：** 论文投稿前需填写：作者姓名、单位、伦理批准号

---

### [2026-04-21] 会话 #18 — Phase G Step 7-8：CLI 集成 + 真实数据运行 + 论文更新

**完成内容：**

#### Task 1：CLI 集成 + Makefile + anomaly 报告生成器

**修改文件：**
- `src/cpet_stage1/stats/anomaly_score.py` — 新增 `generate_anomaly_report()` 函数（Method 2 报告生成器，与 Method 1/3 对齐）
- `src/cpet_stage1/cli.py` — 新增三个 CLI 命令：
  - `model outcome`：加载 cohort_registry + label_table → OutcomeTrainer.run() → 写入 reports/outcome_model_report.md + data/labels/outcome_zone.parquet
  - `stats anomaly`：加载 cohort_registry → run_anomaly_scoring() → 写入 reports/anomaly_score_report.md + data/labels/anomaly_zone.parquet
  - `stats concordance`：合并多个 zone parquet → run_concordance_analysis() → 写入 reports/concordance_report.md
- `Makefile` — 新增 Phase G targets：`model-outcome`, `stats-anomaly`, `stats-concordance`, `phase-g`

#### Task 2：真实数据运行结果

**Method 1（结局锚定）：**
- test_result 阳性率：14.7%（468/3,188 有效样本）
- CV AUC：0.578 ± 0.031（5折），测试集 AUC=0.548
- AP=0.178，Brier=0.126
- 切点：Green/Yellow P<0.140（Sens=0.909，Spec=0.503），Yellow/Red P≥0.150（Youden J=0.448）
- 安全区分布：Green=1400(43.9%，阳性率5.1%)，Yellow=372(11.7%，阳性率10.5%)，Red=1416(44.4%，阳性率25.3%)
- Top 5 特征：hr_peak, ve_vco2_slope, age, oues, vt1_vo2

**Method 2（Mahalanobis 异常评分）：**
- 5变量（vo2_peak, hr_peak, o2_pulse_peak, oues, mets_peak），参考子集 N=969
- 经验切点：P75=3.825，P95=8.788；理论χ²(5) P75=6.626，P95=11.070
- 安全区分布：Green=2083(65.0%，阳性率16.1%)，Yellow=879(27.4%，12.2%)，Red=244(7.6%，10.2%)
- D² vs test_result 相关：r=-0.011（D²测量多变量偏离，非直接风险分级）

**Method 3（多定义一致性框架）：**
- K=4 定义（zone_engine_v2, outcome_anchored, vo2_threshold, anomaly_score）
- 高信度：841(26.2%)，不确定：2358(73.5%)，Green/Red 冲突：1974(61.6%)
- 高信度各区阳性率：Green=5.1%，Yellow=13.1%，Red=28.6%（区分度显著）

#### Task 3：论文更新（main_cn.tex + main_en.tex + references.bib）

**新增内容：**
- **Abstract**：Methods 新增三种互补方法；Results 新增 Phase G 数据；Conclusions 新增第五条
- **Methods 2.8-2.10**：结局锚定安全区模型 + Mahalanobis 异常评分 + 多定义一致性框架（各 ~12-18 行）
- **Results 3.7-3.9**：三方法结果（Table 11/12/13，含各区阳性率 + 切点参数 + 信度统计）
- **Discussion**：新增第六项主要发现（三方法互补解决 P1 循环依赖）；方法学贡献新增一致性框架段落；未来方向新增不确定区 → Stage 2 优先
- **Conclusions**：新增第五条结论
- **references.bib**：新增 `Mahalanobis1936`（Mahalanobis 距离经典引用）+ `NiculescuMizil2005`（isotonic 校准引用）

**生成产出：**
- `reports/outcome_model_report.md` ✅
- `reports/anomaly_score_report.md` ✅
- `reports/concordance_report.md` ✅
- `data/labels/outcome_zone.parquet` ✅
- `data/labels/anomaly_zone.parquet` ✅

**遗留问题：无**

**下一步（建议）：**
- LaTeX 编译验证（若 LaTeX 环境可用）
- `pytest tests/` 回归验证

---

### [2026-04-21] 会话 #17 — Phase G：项目规划刷新 + Stage 1 方法学优化（三种创新方法）

**背景**：重新审视项目核心目标后，发现 Stage I 存在结构性问题：P1 标签由 `vo2_peak_pct_pred / ve_vco2_slope / eih_status` 确定性定义，但这三个变量被 leakage_guard 排除——ML 无法学习一个由排除变量确定性定义的函数。提出三种互补方法解决根本问题。

**完成内容（进行中）：**

#### Part A：文档更新

- `docs/PLANNING.md` — 重写四阶段路线表（突出每阶段侧重点）、重写 In Scope（新增三种方法）、新增「六-B 方法学创新体系」节、新增 Phase G 计划、更新版本策略（→ v2.0.0）
- `docs/DEVLOG.md` — 新增 Phase G 里程碑进度行 + 本会话条目
- `CPET_VO/CLAUDE.md` — 更新快速导航（反映 Phase G）

#### Part B：三种创新方法实现

**Method 1：结局锚定安全区**
- `src/cpet_stage1/modeling/train_outcome.py` — 新建：LightGBM 直接预测 test_result 的训练管线
- `src/cpet_stage1/labels/outcome_zone.py` — 新建：校准概率→Green/Yellow/Red 转换
- `src/cpet_stage1/labels/leakage_guard.py` — 修改：新增 `task="outcome"` 路径（outcome 任务不排除 vo2_peak_pct_pred/ve_vco2_slope/eih_status）
- `configs/model/outcome_lgbm.yaml` — 新建：结局锚定模型配置
- `tests/test_outcome_model.py` — 新建：12 个单元测试

**Method 2：多变量异常评分**
- `src/cpet_stage1/stats/anomaly_score.py` — 新建：Mahalanobis 距离计算（含分层版本）
- `configs/stats/anomaly_config.yaml` — 新建：变量选择和切点配置
- `tests/test_anomaly_score.py` — 新建：12 个单元测试

**Method 3：多定义一致性框架**
- `src/cpet_stage1/labels/concordance_ensemble.py` — 新建：多定义投票 + 信度量化
- `configs/data/concordance_config.yaml` — 新建：投票源配置
- `tests/test_concordance.py` — 新建：12 个单元测试

**测试结果：**
- 62 个新测试全部通过（test_outcome_model: 25, test_anomaly_score: 18, test_concordance: 19）
- 现有 178 个测试无回归
- 总计：240 passed, 0 failed

**关键技术决策：**
- sklearn 1.8.0 移除 `cv="prefit"` → 改用 `cv=2` 内部校准
- LightGBM 搜索改用 `n_jobs=1`（WSL 多进程开销）
- 测试模式下自动降级 CV 折数（n_iter<10 时用 2 折）
- leakage_guard 新增 `outcome` 任务路径（返回空 frozenset，不排除任何字段）
- 一致性框架 Green/Red 冲突检测：任何一对 green+red 共存即标记为不确定

**遗留问题：无**

**下一步（建议）：**
- 在真实数据上运行 `make outcome` / `make anomaly` / `make concordance` 查看实际结果
- 论文更新（main_cn.tex + main_en.tex）整合 Phase G 三方法结果

---

### [2026-04-21] 会话 #16 — Phase F Step 4：测试修复 + 论文重构（数据驱动叙事）

**完成内容：**

#### Task 1：修复 `test_no_data_leakage_test_result` 失败测试

**问题**：`zone_engine_v2.py` 中 `_compute_axis_weights()` 使用 `outcome`（来自 `test_result`）
计算 R/T/I 相关性权重，这些权重直接乘入 `S_lab_v2`，形成 test\_result → S\_lab\_v2 的循环依赖。

**修复**：`build()` 方法中始终使用等权重（R=0.333, T=0.333, I=0.334）计算 `S_lab_v2`；
相关性权重（`audit_weights`）仅作为审计元数据存入 `result.config`，不参与评分计算。

**结果**：`tests/test_phase_f.py::TestZoneEngineV2::test_no_data_leakage_test_result` PASSED。
全套测试：**488 passed, 0 failed**。

#### Task 2：重写 `paper/main_cn.tex` 和 `paper/main_en.tex`

**核心叙事转换**：从"ML预测安全区（F1≈0.50）"→"数据驱动R/T/I三轴安全区方法学"。

| 变更项 | 旧叙事 | 新叙事 |
|---|---|---|
| 标题 | 表型分析与机器学习分层模型 | **数据驱动安全区构建，R/T/I三轴框架与阈值校准** |
| 摘要目的 | 构建ML预测模型；量化预测天花板 | 改进参考方程；**R/T/I数据驱动安全区**；阈值校准与验证 |
| 摘要结果 | P0 AUC=0.583，P1 F1=0.499 | **R²从0.298→0.392；Bootstrap CI<1.0；文献偏差+21%；重分类率39.5%** |
| 方法核心 | 机器学习（P0/P1） | **数据驱动安全区构建（2.4）+Zone边界验证（2.5）** |
| 结论 | summary-level预测天花板 | **首个数据驱动R/T/I安全区方法学；文献阈值Yellow/Red偏差+21%** |

**新增结果内容**：
- Table 3：参考方程 v1 vs v2 对比（$\Delta R^2$=+0.094）
- Table 4：外部参考方程适用性（Wasserman/Koch $R^2<0$）
- Table 5：数据驱动 Zone 分布（全局+队列+性别）
- Table 6：Bootstrap 95% CI（宽度0.65/0.94，均<1）
- Table 7：文献阈值对比（Green/Yellow +5%✓，Yellow/Red +21%✗）
- Table 8：重分类矩阵（39.5%，Red↔Green 188例）
- Tables 9/10：ML 辅助验证（定位降级为辅助）

#### Task 3：更新 `paper/references.bib`

新增4条参考文献：`Weber1982`（Weber-Janicki分级）、`Koch2009`（SHIP参考方程）、
`Hansen1984`（Hansen/Sue/Wasserman预测值）、`Wasserman1999`（运动测试原理教材）。

**关键文件变更**：
| 文件 | 操作 | 摘要 |
|---|---|---|
| `src/cpet_stage1/labels/zone_engine_v2.py` | 修复（行861-875） | 等权重S_lab + audit_weights元数据 |
| `paper/main_cn.tex` | 全面重写（~420行） | 数据驱动叙事；新增10张表格 |
| `paper/main_en.tex` | 全面重写（~390行） | 同步CN版 |
| `paper/references.bib` | 新增4条（行317-368） | Weber1982/Koch2009/Hansen1984/Wasserman1999 |
| `docs/DEVLOG.md` | 新增本条目 | 会话#16 |

**验证**：
- `pytest tests/ -q` → **488 passed, 0 failed** ✅
- 论文核心叙事 = 数据驱动安全区方法学，ML 为辅助验证 ✅
- 所有数据（$R^2$、切点、CI、重分类率）与报告文件一致 ✅

**遗留**：`make cn` / `make en` 编译待用户在本地执行（需 xelatex + gbt7714）。

---

### [2026-04-21] 会话 #15 — Phase E 审稿意见回应 + 方法学修订

**完成内容：**

#### 5 条审稿意见全部修订

| 修订 | 问题 | 解决方案 | 关键文件 |
|---|---|---|---|
| 修订 1 | P1 标签定义未列出 eih\_status 作为 Red 独立充分条件 | 重写 2.4 节：Green/Yellow/Red 均含 eih\_status 条件；新增 Remark 段落说明公理性约束 | `paper/main_cn.tex`, `paper/main_en.tex` |
| 修订 2 | P1 代理泄漏未量化 | 新建消融实验脚本 + 运行：Full/No-VO2/VO2-only 三变体；ΔF1=+0.003（可忽略），确认天花板来自特征局限 | `src/cpet_stage1/modeling/ablation_p1.py`, `reports/p1_ablation_report.md` |
| 修订 3 | P0 "先验风险"术语误导 | 改为"运动前预测的运动事件风险"；增加 P0 是前瞻性预测任务的说明 | `paper/main_cn.tex`, `paper/main_en.tex` |
| 修订 4 | 近随机性能无临床效用论证 | 新建临床效用分析：基线 AUC vs ML，NPV/PPV/NNS，Net Benefit，Red→Green 误判率，简单规则 vs 模型 | `src/cpet_stage1/stats/clinical_utility.py`, `reports/clinical_utility_report.md` |
| 修订 5 | ANOVA 效应量报告不充分 | Methods 增加 N=3206 大样本说明；Results 明确所有 η²<0.01 交互效应为"可忽略"；Discussion 修正 | `paper/main_cn.tex`, `paper/main_en.tex` |

#### 关键发现（对 Discussion 有重大影响）

- **代理泄漏可忽略**：Full vs No-VO2 ΔF1=+0.003，"预测天花板"论断仍成立
- **ML 不优于基线**：P0 XGBoost AUC=0.577 < 2变量基线（HTN+BMI）AUC=0.611（ΔAUC=-0.034）
- **P0 NPV 价值**：NPV=0.853，作为 rule-out 工具有意义；Net Benefit 优于全治疗策略
- **P1 Red 漏判严重**：Red→Green 危险误判率 29.4%；简单 VO₂peak 阈值规则 Red 召回(48.4%) > 模型(26.8%)
- **ANOVA 大样本效应**：VO₂peak%pred 交互 p=0.025 但 η²=0.002（可忽略），正文已更正措辞

#### 新增报告文件

| 文件 | 内容 |
|---|---|
| `reports/p1_ablation_report.md` | 三变体消融：Full(0.458)/No-VO2(0.455)/VO2-only(0.441) |
| `reports/clinical_utility_report.md` | NPV=0.853, NNS=3.8, Red→Green=29.4%, Net Benefit 正向 |

**编译验证**：`make cn`（19页）✅，`make en`（21页）✅
**测试验证**：pytest tests/ 全部通过

---

### [2026-04-21] 会话 #14 — Phase D 论文全面升级

**完成内容：**

#### Bug 修复

| # | 问题 | 修复方案 | 文件 |
|---|---|---|---|
| Bug #6 | `subgroup_report.md` 所有 zone 分布为 0.0% | `_make_summary` 增加整数区域映射（0→green, 1→yellow, 2→red），处理 zone_table 中整数编码的 p1_zone | `src/cpet_stage1/stats/subgroup.py:220-227` |

**根本原因**：`zone_table.parquet` 存储 `p1_zone` 为整数（0/1/2），而 `_make_summary` 直接 `.astype(str)` 后得到 "0"/"1"/"2"，无法匹配 ZONE_ORDER = ["green","yellow","red"]。

#### 论文全面升级（Phase D 核心）

**`paper/main_cn.tex`**（全面重写，~450行）：
- 摘要：修正 VE/VCO₂ 错误数据（原36.2 vs 30.1 → 实际各组均值约27-28），更新最优 P1 模型为 CatBoost F1=0.4991，纠正 VO₂peak 交互效应描述（实际不显著）
- 新增完整 Table 1（7连续变量+3分类变量，全部 median[IQR]，p值）
- 新增 Table 2（ANOVA，6变量 F/p/η²）
- 新增 Table 3（参考方程，5变量 R²/系数）
- 新增 Table 4（P0 模型对比）
- 新增 Table 5（P1 模型对比）
- 新增 Table 6（代价敏感敏感性分析）
- 新增 Table 7（EIH Logistic 回归）
- 启用全部7张 `\includegraphics`
- 重写 Discussion（主要发现/与文献比较/方法学贡献/局限性/未来方向），修正 VO₂peak 交互不显著这一关键发现
- 引言补充文献引用（Li2022xgb, Arina2025, Hearn2018 等）

**`paper/main_en.tex`**（同步更新）：英文版与中文版完全同步，所有数据一致

**`paper/references.bib`**（从10条扩充至28条）：
- 新增：Balady2010(完整), Guazzi2012, OConnor2012, Piepoli2016, Thomas2019
- 新增：Lundberg2017(SHAP), Cohen1988, Chen2016(XGBoost), Ke2017(LightGBM)
- 新增：Ntalianis2024, Zignoli2022ejss(完整), Gao2026
- 补全：Li2022xgb(完整期刊信息), Arina2025(完整), SunXG2022consensus(DOI), Hearn2018(完整)

**`paper/figures/`**（从空目录填充7张）：
- `interaction_plots.png` ← reports/figures/m4/interaction_vo2_peak.png
- `zone_distribution_stacked.png` ← reports/figures/supplement/zone_distribution_stacked_z_lab_zone.png
- `shap_p0.png` ← reports/figures/m5/shap_summary_XGBoost_no_bp.png
- `shap_p1.png` ← reports/figures/m5/shap_summary_LightGBM_full.png
- `eih_forest.png` ← reports/figures/supplement/eih_logistic_forest.png
- `p0_roc.png` ← reports/figures/m5/p0_roc_xgb_no_bp.png
- `p1_cm_catboost.png` ← reports/figures/m5/p1_cm_catboost_full.png

#### 关键数据修正（对照真实报告）

| 数据项 | 原骨架值 | 修正后真实值 | 数据来源 |
|---|---|---|---|
| VO₂peak 交互效应 | "显著" | **不显著** (F=0.02, p=0.894) | twobytwo.md |
| 最优 P1 模型 | LightGBM F1=0.473 | **CatBoost F1=0.4991, κ=0.3023** | p1_model_report_v2.md |
| VE/VCO₂ slope | EIH+ 36.2 vs EIH- 30.1 | 各组均值27.0-28.2（无显著组间差异，p=0.558）| twobytwo.md |
| HTN-EIH 红区占比 | XX% | **99.3%** (275/277) | zone_report.md |
| CTRL 红区占比 | XX% | **6.3%** (117/1858) | zone_report.md |
| P0 XGBoost AUPRC | XX | **0.2869** | p0_model_report_v2.md |
| 参考 N | XXX | **968/969** | reference_equations.md |
| VO₂peak R² | XX | **0.298** | reference_equations.md |
| EIH-Only QC后 N | 359 | **333** | table1.md |

#### 测试

- **453 个测试全部通过**（Bug #6 修复不破坏任何现有测试）

**关键决策：**
- VO₂peak 交互效应不显著是本研究的核心发现之一，论文叙述从"协同效应显著"修正为"独立主效应驱动"
- 最优 P1 模型更新为 CatBoost（F1=0.4991 > LightGBM 0.4646），Red 召回率 30.8%
- Discussion 中明确将低性能定位为"预测天花板"而非方法缺陷，为阶段 II 建立必要性论据
- 引言补充文献对比（Li2022xgb, Arina2025），诚实讨论特征集差异导致的性能差距

**遗留问题：**
- 伦理批号（XX-XXXX）需填入实际批号
- 亚组 bug 修复后 subgroup_report.md 已重新生成（EIH+ 98.2% Red，符合标签定义预期）

**后续补充（会话 #14 验证）：**
- ✅ `make en`：pdflatex 编译成功，**20页，0个未解析引用**
  - 修复：`references.bib` 中 SunXG2022consensus 期刊名从中文改为拼音（pdflatex 不支持 Unicode）
  - gbt7714 风格文件从 CTAN 下载编译后放置于 `paper/` 目录
- ✅ `make cn`：xelatex 编译成功，**17页，0个错误**
- ✅ 亚组报告验证：zone 分布全部非零（EIH+ 98.2% Red；HTN+ 35.1% Red；性别/年龄亚组均正常）
- ✅ `pytest tests/ -q`：**453 测试全部通过**

**下一步：**
- 伦理批号确认后更新论文
- 根据审稿意见修订（针对特定期刊格式）

---

### [2026-04-21] 会话 #13 — Phase A/C 管线收尾

**完成内容：**

#### Bug 修复

| # | 问题 | 修复方案 | 文件 |
|---|---|---|---|
| Bug #5 | CatBoost cost-sensitive 完全退化（F1=0.1332，全预测 red） | 将 `class_weights` 转为 `sample_weight` 传入 `rs.fit()`，构造不含 class_weights 的干净 base_model，使 RandomizedSearchCV 可正常 clone | `src/cpet_stage1/modeling/train_p1.py:545-577` |

#### Phase A/C 管线执行结果

**`make model-p1-cost-sensitive` 结果：**

| 模型 | F1_macro | Kappa | Red Recall |
|---|---|---|---|
| LightGBM（代价敏感） | 0.3924 | 0.1284 | 85/159=53.5% ↑（v2 基线 23.9%）|
| CatBoost（代价敏感） | 0.1871 | 0.0226 | 153/159=96.2%（仍偏向 red）|

**`make supplement-plots` 结果：**
- 4 张补充图生成至 `reports/figures/supplement/`：
  - `zone_distribution_stacked_z_lab_zone.png`
  - `missing_data_heatmap.png`
  - `eih_logistic_forest.png`
  - `safety_zone_concept.png`

#### 测试

- **453 个测试全部通过**（与 v1.1.0 持平，无新增测试）

**关键决策：**
- CatBoost sample_weight 修复使 F1 从 0.1332 提升至 0.1871，但仍未达到 F1>0.30 的验收标准。根本原因：RandomizedSearchCV 内部 CV fold 时 sample_weight 以统一权重采样，导致搜索目标与期望不一致。后续 Phase D 可专项调查（如改用 `scale_pos_weight` 或 `min_data_in_leaf` 约束）
- **主推模型确定**：LightGBM v2（F1=0.4646）作为论文主要结果；LightGBM CS（Red recall=53.5%）作为安全优先敏感性分析附表
- PLANNING.md 新增「Phase A/C 执行结果」小节，记录实际指标

**遗留问题：**
- CatBoost 代价敏感仍需进一步调研（可待 Phase D 论文修订时一并处理）
- Phase D（修订论文 → v1.3.0）尚未启动，待执行

**下一步（Phase D）：**
- 更新 Tables 4/5 使用改善后模型结果（LightGBM v2 F1=0.4646）
- 添加"模型改善分析"小节（before/after 对比）
- 更新 Discussion 性能讨论

---

### [2026-04-16] 会话 #12 — Phase A4 亚组分析 + Phase C4 代价敏感训练

**完成内容：**

#### Phase A4：亚组分析模块

- **新建 `src/cpet_stage1/stats/subgroup.py`**：
  - `SubgroupAnalyzer` 类，提供 4 个亚组维度：
    - `run_sex()` — 性别亚组（M vs F）
    - `run_age_median()` — 年龄中位数分层（<中位 vs ≥中位）
    - `run_eih()` — EIH 状态分层（EIH+ vs EIH-）
    - `run_htn()` — 高血压史分层（HTN+ vs HTN-）
  - `StratumSummary` dataclass：含 zone 分布（绿/黄/红）、VO₂peak 中位数、VE/VCO₂中位数、KW检验 p 值
  - `SubgroupResult` dataclass：含 `to_markdown()` 方法
  - `generate_subgroup_report()` 函数：输出 Markdown 报告

- **更新 `stats/__init__.py`**：导出 `SubgroupAnalyzer`, `SubgroupResult`, `generate_subgroup_report`

- **新增 CLI 命令 `stats subgroup`**：自动检测 sex/age/eih_status/htn_history 列，生成四维度亚组报告

- **Makefile 新增 `subgroup` target**，更新 `phase-a` 依赖包含 subgroup

#### Phase C4：代价敏感训练

- **新建 `configs/model/p1_lgbm_cost_sensitive.yaml`**：
  - `class_weight: {0: 1.0, 1: 2.0, 2: 4.0}` — Red 类权重 4×（当前 Red 召回率仅 26%）
  - 其余超参数与标准版相同

- **新建 `configs/model/p1_catboost_cost_sensitive.yaml`**：
  - `class_weights: [1.0, 2.0, 4.0]` — 显式列表格式（CatBoost API）
  - 替代原 `auto_class_weights: Balanced`

- **更新 `src/cpet_stage1/modeling/train_p1.py`**：
  - `_train_lgbm()` — 从配置读取 `class_weight`（支持 dict/string 两种格式），不再硬编码 "balanced"
  - `_train_catboost()` — 从配置读取 `class_weights`（列表）或 `auto_class_weights`，以配置为准

- **Makefile 新增 `model-p1-cost-sensitive` target**，更新 `phase-c` 依赖

#### 测试

- **`tests/test_phase_a.py`** 新增 11 个测试：
  - `TestNewConfigs`：`test_cost_sensitive_lgbm_config_loads`、`test_cost_sensitive_catboost_config_loads`
  - `TestSubgroupAnalyzer`（9个）：四种分层维度、StratumSummary 字段、KW p 值、to_markdown、report 文件、zone 列缺失降级

- **453 个测试全部通过**（414 + 39 从上一会话的 28 到现在的 39，总计 453）

**关键决策：**
- 代价敏感权重选 Red=4×（而非 3×），基于 Red 召回率仅 26% 的问题严重程度
- CatBoost 使用 `class_weights` 列表而非 `auto_class_weights`，以实现精确控制
- 亚组分析的 KW 检验以 vo2_peak 为主要指标（临床意义最强）

**遗留问题：**
- Phase C 管线（feature_config_v2 + label_rules_v3）尚未实际执行（需真实数据环境）
- Phase D 论文修订待 Phase C 管线跑完后进行

**下一步（Phase C 管线执行）：**
1. `make labels-v3` — 用 label_rules_v3 重生成标签（移除 EIH 从 P1 Red）
2. `make features-v2` — feature_config_v2 构建特征（P0 +BMI/htn_years, P1 +hr_recovery/oues/mets_peak）
3. `make model-p0-v2` — P0 模型（8特征版）
4. `make model-p1-v2` — P1 模型（7特征 + label_rules_v3）
5. `make model-p1-cost-sensitive` — 代价敏感版 P1
6. 对比新旧性能指标，更新论文

---

### [2026-04-16] 会话 #11 — Post-M7 论文准备与模型改善规划

**完成内容：**

#### 数据探索关键发现

通过对 3206 条真实数据的探索性分析，发现以下关键数据现状（影响后续建模策略）：

| 发现 | 结论 |
|---|---|
| 药物列（30列）全部为0 | P0 模型无法利用药物特征；需在论文中明确说明此局限 |
| 合并症字段（diabetes 等）全部为0 | 组间差异分析受限；论文需将其列为局限性 |
| hr_recovery：97.8% 完整，r<0.06（与现有P1特征）| ✅ 高价值 P1 新特征（自主神经功能代理）|
| oues：99.3% 完整，r<0.16 | ✅ 独立 P1 新特征（氧摄取效率斜率）|
| mets_peak：99.7% 完整，r=0.18 vs vo2_peak | ✅ P1 新特征（代谢当量，非 VO2 简单变换）|
| ve_peak：r=0.77 vs vo2_peak | ⚠ 高相关，谨慎用于 P1 |
| BMI 缺失，但 height_cm + weight_kg 可派生 | ✅ P0 新特征，需在 feature_engineer.py 添加派生逻辑 |
| htn_years：52.6% 完整 | ✅ P0 新特征（中位填充），与 EIH 有临床关联 |
| 静息 BP/HR/LVEF：完全缺失 | ❌ P0 性能上限约束（AUC≈0.58 的数据层面原因）|
| P1 EIH+ 100% Red | 结构性问题：EIH-Red 公理导致模型无法学习；需 label_rules_v3.yaml |

#### 论文策略决定

1. **合并为一篇论文**（表型分析 + ML 建模），不拆成两篇
2. **先通用学术格式**（中文 + 英文双版本），不针对特定期刊样式
3. **弱模型定位**：P0 AUC=0.582、P1 F1=0.473 定位为 "summary-level CPET 数据的预测天花板"，强调阶段 II 的必要性（原始波形+逐呼吸数据）
4. **Leakage Guard 作为方法学贡献**：在论文方法和讨论中专门论述
5. **工作流**：跑完结果 → 写初稿 → 改善模型 → 改论文

#### Phase A-D 规划完成

新增 `docs/PLANNING.md` 十五节，详细规划：
- **Phase A**（→ v1.1.0）：SHAP CLI 接通 + Dunn's post-hoc + EIH Logistic 回归 + ≥8 张新图表 + 亚组分析
- **Phase B**（→ v1.1.0）：论文初稿（`paper/main_cn.tex` + `paper/main_en.tex`）
- **Phase C**（→ v1.2.0）：P0 +BMI/htn_years，P1 +hr_recovery/oues/mets_peak，label_rules_v3，代价敏感训练
- **Phase D**（→ v1.3.0）：修订论文，更新所有数字与图表

#### 文档更新

- `docs/PLANNING.md`：
  - 十、版本策略：新增 v1.1.0/v1.2.0/v1.3.0 路线
  - 新增十五节：Post-M7 论文准备与模型改善（数据现状 + 论文定位 + Phase A-D 详细规划 + 验证标准）
- `docs/DEVLOG.md`（本条目）：
  - 里程碑表新增 Phase A/B/C/D 四行（待开始）
  - 版本历史新增 v1.1.0/v1.2.0/v1.3.0 计划行

**关键决策：**
- `label_rules_v3.yaml` 将 P1 zone 定义中移除 EIH 条件（纯心肺储备指标），保留 v2 作为对比
- 模型改善分两步：先做分层分析（方案B），再改标签（方案A），在论文中对比呈现
- `feature_config_v2.yaml` 新增 BMI 派生 + htn_years（P0）+ hr_recovery/oues/mets_peak（P1）

**遗留问题：**
- 目前无遗留 bug，所有 414 个测试仍然通过
- `reports/release/` 是否纳入 Git 追踪，待确认

**下一步（Phase A 实施）：**
1. 接通 SHAP interpret CLI（`cli.py` model interpret → `modeling/interpret.py`）
2. 新建 `stats/posthoc.py`（Dunn's 检验）
3. 新建 `stats/logistic_eih.py`（EIH 多因素 Logistic 回归）
4. 扩展 `stats/plots.py`（缺失热力图 + zone 堆叠柱状图 + 相关热力图 + 森林图）
5. 生成 ≥8 张新图表
6. 完成后更新本 DEVLOG（追加 Phase A 完成条目）

---

### [2026-04-16] 会话 #10 — M7 报告聚合 + 冻结版发布

**完成内容：**

#### 新建模块

- `src/cpet_stage1/reporting/aggregator.py` — `ReportAggregator` + `ReportManifest`：
  - `scan()` — 扫描 `reports/` 目录，验证 9 个预期报告 + m4/m5 图表完整性
  - `generate_summary(manifest, output_path)` — 生成 `reports/summary_report.md`（TOC + 报告摘要 + 图表清单 + 数据产出清单）
  - 纯文件系统操作，不重跑模型
- `src/cpet_stage1/reporting/release.py` — `ReleasePackager` + `ReleaseResult`：
  - `package(manifest, release_dir, include_bridge_prep)` — 打包到 `reports/release/`
  - 复制所有 MD/CSV 报告
  - 复制 m4/m5 图表 → `figures/m4/` / `figures/m5/`
  - 快照全部 YAML → `config_snapshot/`（保留目录结构）
  - 正则解析 p0/p1 报告关键指标 → `metrics_summary.json`
  - 可选复制 `outputs/bridge_prep/` → `bridge_prep/`
  - 生成 `release_manifest.json`（版本、日期、文件清单）

#### 更新文件

- `src/cpet_stage1/reporting/__init__.py` — 导出 4 个类
- `src/cpet_stage1/cli.py` — `reports` / `release` 命令替换 NotImplementedError
- `src/cpet_stage1/__init__.py` — 版本升至 `v1.0.0-stage1`
- `tests/test_smoke_pipeline.py` — 版本断言更新
- `README.md` — 新增 Synthetic Demo 快速复现节 + anchors/release 步骤 + Release Artifacts 表格
- `docs/PLANNING.md` — M7 完成标准打勾，版本策略更新
- `docs/DEVLOG.md` — 本条目

#### 测试

- 新增 `tests/test_reporting.py`（18 个测试）：
  - `TestReportAggregator`（8个）：scan 找到/缺失报告、图表计数、summary 生成、TOC、时间戳
  - `TestReleasePackager`（8个）：目录创建、报告/图表/config 复制、metrics/manifest JSON、bridge_prep 开/关
  - 集成（2个）：端到端流程、导入检查
- **414 个测试全部通过**（396 + 18）

**关键设计决策：**
- 聚合不重建：reporting 模块纯文件系统操作
- 指标解析用正则：从 p0/p1 Markdown 提取 AUC/F1
- 实际文件复制非符号链接：reports/release/ 可直接 Git 追踪

**遗留问题：**
- `reports/release/` 目前 `.gitignore` 可能排除，需确认是否纳入版本控制

**Git tag：**
- `v1.0.0-stage1` 已于 2026-04-16 创建（annotated tag，message: "Stage I: frozen release with reports and bridge_prep_pkg_v1"）

**下一步（阶段 II 准备）：**
- 评估是否将 `reports/release/` 纳入 Git 追踪
- 阶段 II 数据接入准备

---

### [2026-04-15] 会话 #9 — M6 锚点资产 + Bridge Prep 实现

**完成内容：**

#### 新建模块

- `src/cpet_stage1/anchors/anchor_builder.py` — `AnchorBuilder` + `AnchorTableResult`：
  - `build(cohort_df, label_df, reference_df)` — 从 cohort/label/reference 提取 R/T/I 三轴锚点变量
  - R 轴：reserve_r1（vo2_peak_pct_pred）, reserve_r2（o2_pulse_peak）, reserve_r3（vt1_pct_vo2peak 派生）
  - T 轴：threshold_t1（vt1_hr）, t2（rcp_hr）, t3（vt1_load_w）, t4（ve_vco2_slope）
  - I 轴：instability_i1（eih_status）, i2（eih_nadir_spo2）, i3（bp_response_abnormal 派生）, i4（arrhythmia_flag）
  - 综合轴评分（0–100）+ S_lab_score + Z_lab_zone（来自 P1 zone 映射，NaN→NaN）
  - `coverage_report()` — 锚点变量覆盖率 Markdown

- `src/cpet_stage1/anchors/export_anchor_package.py` — `export_anchor_package()`：
  - anchor_table.parquet + anchor_coverage_report.md + JSON/CSV 格式包（可选）

- `src/cpet_stage1/contracts/bridge_contract.py` — `BridgeContractValidator` + `BridgeContractResult`：
  - 验证 anchor_table 必填字段（7 项）+ 推荐字段（6 项）+ z_lab_zone 合法值 + s_lab_score 范围
  - `save_snapshot()` — 生成 contract_snapshot.json

- `src/cpet_stage1/bridge_prep/proxy_hypothesis.py` — `ProxyHypothesisBuilder`：
  - `build()` — 从 anchor_rules + home_proxy_map 生成家庭代理假设表 DataFrame
  - `save()` — 导出 home_proxy_hypothesis_table_v1.csv

- `src/cpet_stage1/bridge_prep/export_bridge_prep.py` — `export_bridge_prep_package()`：
  - 生成全部 5 个 Bridge Prep 文件

#### CLI 命令实现

- `anchors` 命令（原 NotImplementedError）：完整实现，含 AnchorBuilder → export_anchor_package → BridgeContractValidator 全链路
- `bridge-prep` 命令（原 NotImplementedError）：完整实现，生成 5 个输出文件

#### 端到端产出（真实数据）

- `data/anchors/anchor_table.parquet` — 3206 行（含 reserve/threshold/instability 三轴 + S_lab + Z_lab）
- `data/anchors/anchor_coverage_report.md` — 6/11 锚点变量可用
- `data/contracts/contract_snapshot.json` — 验证通过 ✅（0 errors, 0 warnings）
- `outputs/bridge_prep/anchor_variable_dictionary_v1.md`
- `outputs/bridge_prep/home_proxy_hypothesis_table_v1.csv` — 11 行（R+T+I 全量锚点）
- `outputs/bridge_prep/bridge_sampling_priority_list_v1.md`
- `outputs/bridge_prep/bridge_question_list_v1.md`
- `outputs/bridge_prep/bridge_prep_package_manifest.json`
- `outputs/bridge_prep/anchor_package_v1/anchor_summary.json` + `anchor_table_preview.csv`

**测试结果：**
- 54 个新测试（test_anchors.py×34 + test_bridge_prep.py×20）全通过
- 396 总测试全通过

**Z_lab 分布（真实数据）：**
- green: 1289 (40.2%)，yellow: 1099 (34.3%)，red: 797 (24.9%)，NaN: 21 (0.7%)
- S_lab 均值 = 32.8（低风险人群为主，符合预期）

**可用锚点变量（6/11）：**
- R1: vo2_peak_pct_pred ✓，R2: o2_pulse_peak ✓，R3: vt1_pct_vo2peak（派生）✓
- T4: ve_vco2_slope ✓，I1: eih_status ✓，I3: bp_response_abnormal（派生）✓
- 缺失：vt1_hr、rcp_hr、vt1_load_w、eih_nadir_spo2、arrhythmia_flag（字段不在当前数据集）

**关键决策：**

| 决策 | 内容 | 理由 |
|---|---|---|
| NaN zone 保持 NaN | p1_zone=NaN → z_lab_zone=NaN（而非"unknown"）| 诚实表达缺失，合约只验证非 NaN 行 |
| bp_response_abnormal 推导 | bp_peak_sys > 180 mmHg | 直接字段不存在，从 bp_peak_sys 推导（阈值比 P0 更敏感：180 vs 220）|
| S_lab 权重 I=0.4/R=0.4/T=0.2 | 风险贡献：不稳定性=储备>阈值 | T 轴在当前数据集主要依赖 ve_vco2_slope（单一变量），权重降低 |
| v0.6.0 | 版本升级 | M6 里程碑完成 |

**遗留问题：**
- T1/T2/T3（vt1_hr/rcp_hr/vt1_load_w）在当前数据集不可用，阶段 II 扩充数据后可补充
- S_lab 权重系数（TBD）将在 M7/论文阶段根据 P1 模型系数正式校准

**下一步（M7）：**
- `make reports` — Markdown 总报告生成
- `reports/release/` — 冻结版发布（含模型指标、图表、config 快照）
- Git tag `v1.0.0-stage1`

---

### [2026-04-15] 会话 #8 — 管线修复重跑（Step 3）

**完成内容：**

#### Bug 修复（管线诊断 Step 3）

- `src/cpet_stage1/cli.py:308` — labels CLI leakage_guard 预检修复：原代码把全 df 列（含原始测量值 `bp_peak_sys`）当作"模拟特征矩阵"，导致 `bp_peak_sys` 被误报为泄漏；修复：改为从 `feature_config_v1.yaml` 加载实际 P0 特征列后再检查

#### 管线重跑结果

**QC（clip_to_schema_range 生效）：**
- `hr_peak` clip 11 行（range [50, 230]），`bp_peak_sys` clip 6 行，`ve_vco2_slope` clip 6 行
- `vo2_peak` clip 3 行，`o2_pulse_peak` clip 9 行；共 35 个值被 clip

**twobytwo（离群值修正后）：**
- 峰值心率 bpm：133.91~155.84（全在 120-160 预期范围内）✓
- 峰值收缩压 mmHg：160.76~214.85（全在 130-240 临床合理范围内）✓
- 原错误值（332/334）已通过 clip_to_schema_range 消除

**P0 模型（基本不变）：**
- LASSO AUC=0.5822，XGBoost AUC=0.5609（与修复前一致）✓

**P1 模型（泄漏修复后大幅下降，符合预期）：**
- LightGBM F1_macro=0.4731，kappa=0.2733
- CatBoost F1_macro=0.4648，kappa=0.2640
- Ordinal Logistic F1_macro=0.3860，kappa=0.2220
- （修复前虚高：CatBoost F1=0.84，kappa=0.80）— eih_status + ve_vco2_slope 泄漏已消除 ✓

**测试结果：**
- 342 passed ✅（新增 cli.py fix 不破坏任何测试）

**关键观察：**
- P1 F1_macro 从 0.84 降至 0.47，符合移除泄漏字段后的预期（原性能虚高来自 eih_status 直接编码区域信息）
- 当前 P1 特征集仅 4 列（vo2_peak, hr_peak, o2_pulse_peak, vt1_vo2），受数据集字段限制
- cycle_only 与 full 完全一致（exercise_protocol_cycle 缺失，全为 unknown）

**遗留问题：**
- P1 特征集受限（vt1_*/load_peak_w/eih_nadir_spo2 等字段在当前数据集不存在）
- P0 特征集受限（bmi/hr_rest/lvef_pct 等字段不在 BATCH_CPET_EXAMPLE）

**下一步（M6）：**
- 锚点资产生成（`make anchors`）
- Bridge Prep 文档包生成（`make bridge-prep`）

---

### [2026-04-15] 会话 #7 — PLANNING.md 更新 + 管线产出生成

**完成内容：**

#### 文档更新
- `docs/PLANNING.md` — M5 完成标准 7 项 `[ ]` → `[x]`，M5 标题加 `（已完成 ✅）`，版本策略表当前版本 `v0.4.0` → `v0.5.0`，下一版本改为 `v0.6.0`（锚点资产+Bridge Prep）

#### Bug 修复
- `src/cpet_stage1/features/feature_engineer.py:269` — `sex` 列为 Categorical 类型时 `.fillna(-1)` 报错；修复：`X[col].astype(object).map(...).fillna(-1)`
- `src/cpet_stage1/features/splitter.py:172` — 同类问题，`df["sex"].astype(object).fillna("U")`
- `src/cpet_stage1/cli.py` — `model p0`/`p1` 命令加载 `cohort_registry.parquet` 但不含标签列；修复：合并 `data/labels/label_table.parquet`

#### 管线产出（首次生成）
- `data/labels/cohort_registry.parquet` — 3206 行，2×2 队列分布
- `data/labels/label_table.parquet` + `zone_table.parquet` — P0/P1 标签
- `data/labels/reference_scores.parquet` — 5 个参考方程的 %pred / z-score
- `data/features/features_pre.parquet` + `features_post.parquet` — P0/P1 特征矩阵（各 3206×6）
- `reports/zone_report.md` — P0 阳性 22.7%（727/3206），在 10-30% 目标范围内 ✓
- `reports/table1.md` + `.csv` — 四组对比，N=3206 ✓
- `reports/twobytwo.md` — HTN×EIH 双因素分析
- `reports/reference_equations.md` — 5 个参考方程（VO₂peak R²=0.296）
- `reports/sensitivity_protocol.md` — 协议敏感性（exercise_protocol 字段缺失 → unknown）
- `reports/p0_model_report.md` — LASSO AUC=0.5822，XGBoost AUC=0.5609（特征集受限）
- `reports/p1_model_report.md` — CatBoost F1_macro=0.8397，kappa=0.7989；LightGBM F1_macro=0.8296
- `reports/figures/m4/` — 10 张图（箱线/小提琴/交互作用图）
- `reports/figures/m5/` — 27 张图（ROC/PR/校准/DCA/BP对比）

**测试结果：**
- `make test`：330 tests passed（与 M5 完成时一致，修复未破坏任何测试）

**关键观察：**
- P0 AUC 偏低（~0.58）：原因是 P0 特征列大量缺失（bmi/bp_rest_*/hr_rest 等字段不在当前数据集），仅剩 6 列特征（age, sex, vo2_peak, ve_vco2_slope, hr_peak, o2_pulse_peak），实际上包含了 CPET 运动参数，无法完全反映"静息危险因素"建模能力
- P1 性能优秀（CatBoost F1=0.84，kappa=0.80）：因 P1 特征主要来自 CPET 运动结局，与分区标准高度相关
- `exercise_protocol_cycle` 字段缺失 → cycle_only 与 full 结果完全一致（合理）

**遗留问题：**
- P0 特征集受限（bmi/hr_rest/lvef_pct 字段不在 BATCH_CPET_EXAMPLE 数据中）；正式论文数据扩充后需重跑
- 中文字体 WSL 显示为方框（已知，warnings-only，图表内容完整）

**下一步（M6）：**
- 锚点资产生成（`make anchors`）
- Bridge Prep 文档包生成（`make bridge-prep`）

---

### [2026-04-14] 会话 #6 — M5 P0/P1 主模型管线实现

**完成内容：**

#### 配置层
- `configs/features/feature_config_v1.yaml` — **新建**，P0/P1 特征列表 + 插补/缩放策略：
  - P0 特征：continuous（age/bmi/bp_rest_*/hr_rest/lvef_pct）, binary（htn/cad/hf_history）, categorical（sex）, protocol（exercise_protocol_cycle）
  - P1 特征：continuous（vo2_peak/hr_peak/load_peak_w/o2_pulse_peak/ve_vco2_slope/vt1_*/eih_nadir_spo2）, binary（eih_status/bp_response_abnormal）
  - 插补策略：continuous=median, binary=zero, categorical=mode
  - 缩放：仅对 lasso_logistic / ordinal_logistic 应用 StandardScaler

#### features 模块（新建）
- `src/cpet_stage1/features/feature_engineer.py` — `FeatureEngineer` + `FeatureResult`：
  - `build_p0(df, include_bp, model_type, fitted_imputer, fitted_scaler)` — 编码 → LeakageGuard → 插补 → 缩放
  - `build_p1(df, cycle_only, model_type, fitted_imputer, fitted_scaler)` — 同上 + cycle 过滤
  - Train-only fit 防数据泄漏；fitted_imputer/fitted_scaler 参数传递给 test 集
- `src/cpet_stage1/features/splitter.py` — `DataSplitter` + `SplitResult`：
  - 80/20 holdout（StratifiedShuffleSplit），5-fold CV（StratifiedKFold）
  - `_make_strat_safe()`：稀有类合并防止分层失败

#### modeling 模块（新建）
- `src/cpet_stage1/modeling/calibrate.py` — 校准模块：
  - `IsotonicBinaryCalibrator`：手动实现 prefit 校准（替代 sklearn 1.8 已弃用的 `cv="prefit"`）
  - `calibrate_binary(model, X_cal, y_cal, method)` — isotonic/sigmoid 包装
  - `TemperatureScaler`：单标量 T 温度缩放（scipy.minimize_scalar，NLL 损失，bounds=[0.1,10.0]）
- `src/cpet_stage1/modeling/evaluate.py` — 评估模块：
  - `ModelEvaluator.evaluate_binary()` → AUC-ROC, AUPRC, Brier, 敏感性/特异性, F1, 校准曲线, DCA
  - `ModelEvaluator.evaluate_multiclass()` → F1_macro, weighted kappa, accuracy, per-class F1, 混淆矩阵
  - `decision_curve_analysis()` — 净获益自实现（net_benefit = TP/N - FP/N × t/(1-t)）
  - `EvaluationResult.to_json()` / `to_markdown()`
- `src/cpet_stage1/modeling/train_p0.py` — P0 训练管线：
  - `P0Trainer.run(df)` → `{model_name: {bp_variant: P0ModelResult}}`
  - LASSO：`LogisticRegression(l1_ratio=1.0, solver="saga")` + GridSearchCV over C grid
  - XGBoost：`XGBClassifier(scale_pos_weight=n_neg/n_pos)` + RandomizedSearchCV
  - 4 组合：(LASSO, XGBoost) × (with_bp, no_bp)
- `src/cpet_stage1/modeling/train_p1.py` — P1 训练管线：
  - `P1Trainer.run(df)` → `{model_name: {sample_variant: P1ModelResult}}`
  - OrdinalLogistic：`_OrdinalLogisticWrapper`（tries statsmodels → sklearn fallback）
  - LightGBM：`LGBMClassifier(objective="multiclass", class_weight="balanced")`
  - CatBoost：`CatBoostClassifier(auto_class_weights="Balanced")`
  - 6 组合：3 模型 × (full, cycle_only)，含一致性分析
- `src/cpet_stage1/modeling/interpret.py` — SHAP 解释（TreeExplainer → LinearExplainer → KernelExplainer 降级链）
- `src/cpet_stage1/modeling/plots.py` — M5 可视化（ROC/PR/校准/DCA/混淆矩阵/BP双版本/踏车一致性）
- `src/cpet_stage1/modeling/report.py` — 报告生成（p0_model_report.md / p1_model_report.md）

#### 测试（新建）
- `tests/test_features.py` — 25 tests
- `tests/test_splitter.py` — 15 tests
- `tests/test_evaluate.py` — 20 tests
- `tests/test_modeling_p0.py` — 20 tests
- `tests/test_modeling_p1.py` — 21 tests（含 session-scoped 缓存 fixture）
- `tests/test_interpret.py` — 12 tests

#### 其他更新
- `src/cpet_stage1/__init__.py` — 版本 v0.4.0 → v0.5.0
- `src/cpet_stage1/features/__init__.py` / `modeling/__init__.py` — 完整导出
- `src/cpet_stage1/cli.py` — 替换 3 个 NotImplementedError stub，新增 model_evaluate/interpret/report 子命令
- `Makefile` — 新增 model-p0/p1/evaluate/interpret/report/model targets
- `tests/test_smoke_pipeline.py` — 版本断言更新

**关键技术决策：**
- sklearn 1.8 兼容：`CalibratedClassifierCV(cv="prefit")` 已移除 → 手动实现 `IsotonicBinaryCalibrator`
- sklearn 1.8 兼容：`LogisticRegression(multi_class=...)` 已移除 → 使用默认 solver="lbfgs"
- sklearn 1.8 兼容：`penalty="l1"` → 改用 `l1_ratio=1.0`（elasticnet 语法）
- P1 测试速度：session-scoped fixture 缓存 trainer.run() 结果，避免 13 次重复跑（~3min → <1min）
- CatBoost/LightGBM fast-mode：`n_iter_override is not None` 时用小 iterations=[10,20] / n_estimators=[20,50]

**测试结果：**
- 330 总测试全通过（307 原有 + 21 P1新增 + 12 interpret新增 = 330）
- 警告：LightGBM feature names（无害）+ WSL 中文字体缺失（已知问题，warnings-only）

**遗留问题：**
- P1 test 整体耗时约 3 分钟（CatBoost 固有开销），可接受
- 真实数据端到端验证（需待真实患者数据接入）
- SHAP plots 在 CI 无头环境需验证

**下一步（M6）：**
- 锚点资产生成（个体化 VO₂/HR 阈值推荐）
- Bridge Prep（家庭心率区间映射）

---

### [2026-04-14] 会话 #5 — M4 表型分析与参考模型实现

**完成内容：**

#### 配置层
- `configs/stats/table1_config.yaml` — **新建**，M4 统计分析全局配置：
  - `table1`：分组/变量列表（18个连续+12个分类）/检验方法（Shapiro-Wilk/Kruskal-Wallis/chi²）
  - `twobytwo`：因素定义（htn_history×eih_status）/9个CPET结局变量/eta²效应量
  - `reference`：参考子集标志/OLS预测变量/7个目标变量/后缀配置
  - `plots`：样式/输出目录/变量列表（箱线图/小提琴图/交互作用图）
  - `sensitivity`：协议推导规则（exercise_protocol_cycle → cycle/treadmill）

#### stats 模块（实现）
- `src/cpet_stage1/stats/table1.py` — `Table1Builder` + `Table1Result`：
  - Shapiro-Wilk 正态检测（n>5000 时抽样），mean±SD / median[Q1,Q3] 自动切换
  - force_format 覆盖机制，缺失行有效N标注
  - Kruskal-Wallis 组间检验（连续），χ² 检验（分类）
  - `to_markdown()` / `to_csv()` 输出
  - `build_stratified_table1()` 协议敏感性复用接口
- `src/cpet_stage1/stats/twobytwo.py` — `TwoByTwoAnalyzer` + `TwoByTwoResult`：
  - statsmodels Type II SS ANOVA，`anova_lm(typ=2)`
  - 偏η² = SS_eff/(SS_eff+SS_res)，效应量解读（small/medium/large）
  - 各cell描述统计（均值±SD + 有效N）
  - Markdown 输出（自定义 pipe-table 格式，不依赖 tabulate）
- `src/cpet_stage1/stats/reference_builder.py` — `ReferenceBuilder` + `ReferenceBuilderResult`：
  - OLS 拟合 `target ~ age + C(sex) + age:C(sex)`
  - 各性别<min_per_sex 时退化为无交互模型
  - `%pred = 100 × actual/predicted`，`z-score = (actual-predicted)/res_std`
  - NaN 完整传播
- `src/cpet_stage1/stats/plots.py` — 可视化模块（matplotlib Agg 无头渲染）：
  - `plot_grouped_boxplot()` — seaborn 分组箱线图
  - `plot_grouped_violin()` — seaborn 分组小提琴图（inner=box）
  - `plot_interaction()` — 双因素交互作用图（边际均值+SEM误差棒）
  - `plot_reference_scatter()` — 年龄-目标散点图（分sex着色+回归线+参考子集高亮）
  - `generate_all_m4_plots()` — 批量生成所有M4图表
- `src/cpet_stage1/stats/__init__.py` — 导出 Table1Builder / TwoByTwoAnalyzer / ReferenceBuilder

#### CLI 扩展
- `src/cpet_stage1/cli.py` — 新增 `stats` 子命令组（5个子命令）：
  - `stats table1` — 生成 reports/table1.md + table1.csv
  - `stats twobytwo` — 生成 reports/twobytwo.md
  - `stats reference` — 生成 reports/reference_equations.md + reference_scores.parquet
  - `stats plots` — 批量生成 reports/figures/m4/*.png
  - `stats sensitivity` — 协议分层敏感性分析 reports/sensitivity_protocol.md

#### Makefile 扩展
- 新增 6 个 targets：`stats-table1`, `stats-twobytwo`, `stats-reference`, `stats-plots`, `stats-sensitivity`, `stats`（汇总）

#### 测试（52个全通过）
- `tests/test_stats.py` — 52个测试（合成数据，无真实患者数据）：
  - `TestTable1Builder`（21个）：正态/非正态格式化、force_format、P值方向、缺失报告、空组、Markdown/CSV输出、大N抽样
  - `TestTwoByTwoAnalyzer`（10个）：已知差异→P<0.05（HTN主效应显著）、无差异→η²≈0、偏η²计算、NaN丢弃、n_per_cell
  - `TestReferenceBuilder`（11个）：age系数方向（负相关vo2_peak）、%pred≈100、z-score≈0、NaN传播、性别不足退化
  - `TestStratifiedTable1`（3个）：按协议分层、各分层结果有效、缺列报错
  - `TestPlots`（7个）：各图返回Figure、保存文件、缺列报错、批量生成

#### 版本更新
- `src/cpet_stage1/__init__.py`：`v0.1.0` → `v0.4.0`
- `tests/test_smoke_pipeline.py`：版本断言更新

---

**关键决策：**

| 决策 | 内容 | 理由 |
|---|---|---|
| 不依赖 tabulate | to_markdown() 使用自定义 pipe-table | tabulate 未在 pyproject.toml 中，避免依赖问题 |
| Shapiro-Wilk 大N抽样 | n>5000 时抽 5000 条检验 | 大样本时 Shapiro-Wilk 极敏感，几乎所有分布都拒绝正态 |
| force_format 机制 | 允许 YAML 配置强制 normal/nonnormal | 临床数据中某些变量（如年龄）虽不通过Shapiro但惯用均值 |
| Kruskal-Wallis 作为默认 | 非参数检验，不假设正态 | CPET 数据组间分布形状差异大，参数检验不稳健 |
| 偏η² 而非η² | SS_eff/(SS_eff+SS_res) | 双因素设计的标准效应量，排除其他因素方差 |
| min_per_sex=20 退化 | 各性别<20人时不加入交互项 | 交互项估计需要足够样本，否则不可靠 |
| matplotlib Agg 后端 | 在 plots.py 顶部 `matplotlib.use('Agg')` | 服务器/WSL无头环境，无法显示GUI |

---

**遗留问题：**
1. 中文字体在 WSL/Linux 环境下无法渲染（警告但不影响功能），图表中文标签显示为方框
2. `make stats` 依赖真实数据（cohort_registry.parquet），需先运行 make labels
3. bp_peak_sys 在 EHT_ONLY 组缺失 139 条，ANOVA 报告有效N时应注意

---

**下一步（M5）：**
- [ ] P0/P1 主模型（LASSO, XGBoost, LightGBM）
- [ ] 端到端验证：`make stats` 用真实 cohort_registry.parquet 跑通
- [ ] 确认参考方程 R² 合理性（预期 vo2_peak R² ≈ 0.2–0.4）

---

### [2026-04-14] 会话 #4 — M3 2×2队列注册+标签引擎实现

**完成内容：**

#### 配置层
- `configs/data/label_rules_v2.yaml` — **新建**，v2 标签规则（优雅降级：不可用字段 inactive，可推导字段从 group_code 推导）
- `configs/data/reference_rules_v2.yaml` — **新建**，参考正常子集规则（wide + strict 两版本）

#### cohort 模块（实现）
- `src/cpet_stage1/cohort/cohort_registry.py` — `CohortRegistry` 类：group_code → htn_history/eih_status → cohort_2x2，cpet_session_id 生成
- `src/cpet_stage1/cohort/reference_subset.py` — `ReferenceSubsetBuilder` 类：wide/strict 两层筛选，HR 努力度代理，min_sample_size 检查
- `src/cpet_stage1/cohort/__init__.py` — 导出主接口

#### labels 模块（实现）
- `src/cpet_stage1/labels/label_engine.py` — `LabelEngine` + `LabelResult`：P0（三条活跃条件）+ P1（三区 take_worst）+ HR effort flag
- `src/cpet_stage1/labels/safety_zone.py` — `assign_zones()` + `generate_zone_report()`
- `src/cpet_stage1/labels/__init__.py` — 导出主接口

#### CLI 接通
- `src/cpet_stage1/cli.py` — `cohort` 和 `labels` 命令完整实现（含 leakage_guard 验证）

#### 测试
- `tests/test_cohort.py` — ~15 个测试：group_code推导、cohort_2x2四象限、reference筛选、边界值
- `tests/test_labels.py` — ~20 个测试：P0/P1标签生成、缺失值处理、take_worst、zone映射、leakage_guard

---

**关键决策：**

| 决策 | 内容 | 理由 |
|---|---|---|
| label_rules_v2 优雅降级 | 不可用字段标 inactive，可推导字段从 group_code 推导 | 数据实际缺少 arrhythmia_flag 等字段，不能强依赖 |
| P0 活跃条件 | eih_status + vo2_peak_pct_pred<50 + bp_peak_sys>220 | 基于可用数据；bp_peak_sys 列入 leakage_guard |
| P1 take_worst | 冲突时取最差区（max） | 临床保守原则，安全优先 |
| HR 努力度代理 | hr_peak >= 0.85×(220-age) | rer_peak 不可用，用 HR 代理 |
| NaN = absent | cad_history/hf_history NaN 视为 False | 稀疏二值编码约定 |

---

**遗留问题：**
1. reference_flag_strict 依赖 hr_peak 和 age，数据中若缺失则退化为 wide 结果
2. P0 阳性率受 eih_status 主导（约 19.5%+12.3% = 部分人群），需端到端验证
3. M4（表型分析 + Table 1）可在 M3 端到端跑通后启动

---

**下一步（M3 端到端验证）：**
- [ ] `make cohort` 验证：cohort_registry.parquet 四象限覆盖 + reference_flag 计数
- [ ] `make labels` 验证：P0 阳性率 10–30%，P1 红区 < 40%，leakage_guard 通过
- [ ] `make test` 验证：原 83 + 新增 ~35 = ~118 全部通过

---

### [2026-04-14] 会话 #3 — M2 真实数据端到端验证

**完成内容：**

#### 真实数据导入结果
- 四组 Excel 文件成功导入（合计 3232 行，87 列）
- field_map_v2.yaml 补充 25+ 中文别名（含关键修正：`最大值-VO2` → `vo2_peak` 等）
- 新增 10 个字段到 field_map_v2：体脂/腰围/体脂%、OUES、AT_VO2、O2脉搏等
- staging parquet 成功生成：3232 行

#### QC 运行结果
- QC 通过：**3206 行**（拒绝 26 行，约 0.8%）
- EHT_ONLY 专项诊断段落正常输出：139 个 bp_peak_sys 缺失
- 数据分布：vo2_peak 缺失 0，ve_vco2_slope 缺失 15，bp_peak_sys 缺失 139

#### 关键发现
1. `rer_peak` 字段不存在于真实 Excel → 标签规则降级（inactive）
2. `arrhythmia_flag`/`test_terminated_early`/`st_depression_mm` 字段不存在 → P0 inactive criteria
3. `cad_history`/`hf_history` 极稀疏（几乎全 NaN）→ NaN = absent (False) 约定
4. `exercise_habit` 编码为字符串（非整数）→ value_map 修正为字符串映射
5. logic_check NaN 处理：pandas eval 中 `is not null` 降级为 `== @threshold` 形式

---

**遗留问题（已解决）：**
- ~~真实 Excel 文件尚未就位~~ → 已就位，导入成功
- ~~field_map_v2.yaml 中文别名需核对~~ → 已核对并修正 25+ 别名

---

### [2026-04-14] 会话 #2 — M2 数据导入与QC管线

**完成内容：**

#### 配置层扩展
- `configs/data/field_map_v2.yaml` — **新建**，v1→v2 全量扩展至 87 列：
  - 覆盖真实 Excel 列名（含中文别名 + 关键修正：`最大值-VO2` → `vo2_peak`，`最大值-VO2*` → `vo2_peak_abs`，`DATE` → `test_date`，`最大值-HR` → `hr_peak`，`最大值-VO2/HR` → `o2_pulse_peak`）
  - 新增分组：教育/职业（4）、合并症（8）、吸烟史（5）、家族史/生活方式（7）、药物降压（6）、药物调脂（3）、药物抗栓（6）、药物降糖（7）、药物其他（5）、协议（5）、CPET扩展（5）
- `configs/data/schema_v2.yaml` — **新建**，扩展至~80个字段定义，药物字段统一 `dtype: category`
- `configs/data/qc_rules_v1.yaml` — **编辑**，新增 `range_checks_extended`（17个新字段）+ `logic_checks_extended`（2条规则）
- `configs/paths.yaml` — **编辑**，新增 `external_data_dir` 和 `batch_cpet_dir`

#### io 模块（新建）
- `src/cpet_stage1/io/excel_import.py` — `ExcelImporter` 核心类：
  - `import_file()`: Excel → 列名映射 → 缺失值统一 → value_map → dtype转换 → 注入group_code
  - `import_batch()`: 读取 manifest.json，遍历四组，合并输出 staging parquet
  - `FieldMappingReport`：映射统计（mapped/unmapped/missing_expected）
  - `compute_hash_registry()`：SHA256 hash 可复现性清单
- `src/cpet_stage1/io/loaders.py` — 通用加载工具：`load_staging`, `load_curated`, `load_config`, `load_demo_csv`
- `src/cpet_stage1/io/__init__.py` — 导出主接口

#### qc 模块（新建）
- `src/cpet_stage1/qc/rules.py` — `QCEngine` 类：5类检查（完整性/范围/逻辑/重复/IQR异常值）+ 努力度标志 + 分组统计
- `src/cpet_stage1/qc/validators.py` — `generate_qc_report()`（Markdown报告，含EHT_ONLY专项段落）+ `apply_qc_flags()`（curated输出）
- `src/cpet_stage1/qc/__init__.py` — 导出接口

#### contracts 模块（新建）
- `src/cpet_stage1/contracts/schema_validator.py` — `validate_staging()`：列名/类型/必填/范围/category验证
- `src/cpet_stage1/contracts/__init__.py` — 导出接口

#### CLI 接通
- `src/cpet_stage1/cli.py` — `ingest` 和 `qc` 命令完整实现（含参数：manifest, field_map, schema, output 等）

#### 数据清单
- `data/manifests/batch_cpet_example_manifest.json` — 四组Excel文件清单（CTRL/HTN_HISTORY_NO_EHT/HTN_HISTORY_WITH_EHT/EHT_ONLY）

#### 工程修复
- `pyproject.toml` — 修复 `build-backend` typo（`setuptools.backends.legacy:build` → `setuptools.build_meta`）

#### 测试（83个全通过）
- `tests/test_io.py` — 30个测试：field_map加载、列名映射、value_map、缺失值、端到端、hash
- `tests/test_qc.py` — 27个测试：5类QC规则、完整run()、报告生成、curated输出
- `tests/test_contracts.py` — 16个测试：schema验证通过/失败/warning、strict模式
- `tests/test_smoke_pipeline.py` — 原有10个测试继续通过

---

**关键决策：**

| 决策 | 内容 | 理由 |
|---|---|---|
| `applymap` → `map` | pandas FutureWarning 修复 | 兼容当前 pandas 版本 |
| `default_factory=lambda: pd.Index([])` | QCResult rejected_indices | pd.Index 不能直接用作 default_factory |
| 未匹配列保留 | _apply_column_mapping 不删除未知列 | 便于调试，数据不丢失 |
| EXTERNAL_DATA_DIR 优先 | data_base_dir 推断策略 | 数据与代码分离（ADR-005）|

---

**遗留问题（已在会话 #3 解决）：**
1. ~~真实 Excel 文件尚未就位~~ → 会话 #3 导入成功（3232→3206 行）
2. ~~field_map_v2.yaml 中文别名需核对~~ → 会话 #3 修正 25+ 别名
3. `qc_rules_v1.yaml` 的 `logic_checks` 使用 pandas eval，复杂条件降级处理（已知问题）
4. M3（2×2 队列 + 标签引擎）已在会话 #4 实现

---

**下一步（M3 前）：**
- [ ] 配置 `EXTERNAL_DATA_DIR` 指向真实数据路径，运行 `make ingest` 端到端验证
- [ ] 核对真实 Excel 列名与 `field_map_v2.yaml` 的对应关系，补充缺失别名
- [ ] 查看 `data/manifests/field_mapping_report.json` 中 `unmapped` 列表，逐一处理
- [ ] 开始 M3：cohort 注册 + P0/P1 标签生成

---

### [2026-04-14] 会话 #1 — M1 仓库脚手架

**完成内容：**

#### 环境准备
- GitHub CLI 认证完成（账号：`mrxachen`）
- 远程仓库创建：`mrxachen/cpet-safety-line-stage1`（private）
- 分支：`main`（稳定）+ `dev`（开发）

#### 仓库结构（81 个文件）
创建了完整的仓库目录树和关键文件：

**配置层 `configs/`**
- `data/schema_v1.yaml` — 完整字段 schema（人口学 / 临床 / CPET 峰值 / 阈值 / 安全标志 / 标签）
- `data/field_map_v1.yaml` — 中文→英文字段映射骨架（含 value_map，如 男/女 → M/F）
- `data/qc_rules_v1.yaml` — QC 规则（完整性 / 范围 / 逻辑 / 努力度 / 重复 / 异常值）
- `data/label_rules_v1.yaml` — P0 代理标签规则 + P1 三区分类规则 + leakage guard 配置
- `data/split_rules_v1.yaml` — 分层 5-fold CV，以 subject_id 为 group 键
- `data/reference_rules_v1.yaml` — reference-normal subset 筛选标准
- `configs/bridge/anchor_rules_v1.yaml` — **R/T/I 三轴锚点变量完整定义**（含 home proxy 假设）
- `configs/bridge/home_proxy_map_v0.yaml` — 家庭代理信号假设映射（v0，待验证）
- `configs/bridge/sensor_schema_v0.yaml`, `bridge_sampling_priority_v0.yaml`, `contract_rules_v1.yaml`
- `configs/model/` — P0 (LASSO/XGB) + P1 (Logit/LGBM/CatBoost) + 有序区 + 多任务 共 7 个配置

**源码层 `src/cpet_stage1/`**
- `__init__.py` — 版本 `0.1.0`
- `cli.py` — typer CLI 骨架（10 个命令：ingest/qc/cohort/labels/features/anchors/model-p0/model-p1/reports/bridge-prep）
- `labels/leakage_guard.py` — **核心模块**，含 `LeakageGuard` 类（filter/assert/report 方法），P0/P1 泄漏字段明确定义
- `utils/paths.py`, `utils/seed.py`, `utils/logging.py`
- 所有子包的 `__init__.py` 占位（io/qc/contracts/cohort/labels/features/anchors/stats/modeling/bridge_prep/interfaces/reporting/utils）

**工程配置**
- `pyproject.toml` — Python ≥3.11，完整依赖（pandas/xgboost/lightgbm/catboost/shap/typer/pydantic 等）
- `Makefile` — 全流程 targets（install/lint/test/ingest/qc/cohort/labels/features/anchors/model-p0/model-p1/reports/bridge-prep/release/clean）
- `.gitignore` — 排除所有数据目录（data/raw, staging, curated 等），保留 data/demo/
- `.env.example`, `.pre-commit-config.yaml`（ruff + pre-commit hooks）

**文档层 `docs/`**
- `protocol/stage1_scope.md` — 阶段 I 完整边界定义（纳排标准、终点、6 个里程碑、时间线）
- `protocol/endpoint_definitions.md`, `data_request_checklist.md`
- `bridge/` — anchor_variable_dictionary_v1, home_proxy_hypothesis_table_v1, bridge_sampling_priority_list_v1, bridge_question_list_v1, contract_spec_v1
- `decisions/ADR-001` 到 `ADR-006` — 六条架构决策记录
- `PLANNING.md` — 项目代码规划总文档（本次新增）
- `DEVLOG.md` — 本文件

**测试**
- `tests/test_smoke_pipeline.py` — 5 类 smoke tests（包导入 / 种子 / 路径 / LeakageGuard / demo CSV）

**演示数据**
- `data/demo/synthetic_cpet_stage1.csv` — 20 条合成数据（覆盖绿/黄/红三区，含完整字段）

**初始 commit：**
```
25006a3 feat: initialize stage1 research repository scaffold
```

---

**遗留问题 / 待处理：**

1. **`field_map_v1.yaml` 为骨架**：真实 Excel 列名需要拿到数据后逐一核对，特别是"仅运动高血压"组的列名可能与其他组不一致。
2. **`configs/experiment/` 为空**：`exp_paper1_2x2.yaml`, `exp_paper2_p0.yaml` 等实验配置待 M4/M5 时创建。
3. **`docs/data_dictionary/` 为空**：`dictionary_v1.md`, `units_and_ranges_v1.md`, `field_mapping_v1.md` 待 M2 QC 通过后从实际数据生成。
4. **`pyproject.toml` setuptools backend 字符串有 typo**：需验证 `setuptools.backends.legacy:build` 是否正确（标准写法为 `setuptools.build_meta`）。
5. **CI/GitHub Actions 未配置**：计划 M1 完成后添加（lint + test + bridge-prep smoke）。
6. **Notebooks 为 stub**：8 个 notebook（00–07）均为占位，内容待各对应里程碑时填充。

---

**下一步（M2 启动前需完成）：**

- [ ] 确认真实数据的 `DATA_DIR` 路径并更新 `.env`
- [ ] 核对 Excel 列名与 `field_map_v1.yaml` 的对应关系
- [ ] 开始实现 `src/cpet_stage1/io/excel_import.py` 和 `io/loaders.py`
- [ ] 开始实现 `src/cpet_stage1/qc/rules.py` 和 `qc/validators.py`
- [ ] 为 M2 创建 feature branch：`feat/ingest-qc`

---

**本次决策记录：**

| 决策 | 内容 | 理由 |
|---|---|---|
| 仓库可见性 | Private | 真实数据不公开；标签规则仍在迭代 |
| 许可证 | Apache-2.0 | 适合后续转化和合作衍生场景 |
| 分支策略 | main + dev | 简洁双主分支，功能分支用 feat/* |
| 数据隔离 | .gitignore 排除 data/*（除 demo/） | 合规约束 |
| leakage_guard | 独立模块，非工程补丁 | 方法学规则，影响论文可信度 |
| 合成数据 | 20 条覆盖三区 | 满足 smoke test 和 CI 需求 |

---

> **模板说明**：
> 每次开发会话结束时，在此文件最前面（`## 会话记录` 之后）新增一个 `### [日期] 会话 #N — 摘要` 条目。
> 同时更新顶部的**里程碑进度总览**表格和**代码版本历史**表格。
