# DEVLOG.md — 开发日志

> 逐次记录每个开发会话的进展、决策与遗留问题。
> 格式：最新条目在最前面（倒序）。

---

## 里程碑进度总览

| 里程碑 | 状态 | 完成日期 |
|---|---|---|
| M1 — 仓库脚手架 | ✅ 完成 | 2026-04-14 |
| M2 — 数据导入 + QC | 🔲 待开始 | — |
| M3 — 2×2 队列 + 标签引擎 | 🔲 待开始 | — |
| M4 — 表型分析 + 参考模型 | 🔲 待开始 | — |
| M5 — P0/P1 主模型 | 🔲 待开始 | — |
| M6 — 锚点资产 + Bridge Prep | 🔲 待开始 | — |
| M7 — 报告 + 冻结版发布 | 🔲 待开始 | — |

---

## 代码版本历史

| 版本 | 日期 | 变更摘要 |
|---|---|---|
| `v0.1.0` | 2026-04-14 | 仓库脚手架初始化 |

---

## 会话记录

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
