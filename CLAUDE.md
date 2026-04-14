# CLAUDE.md — cpet-safety-line-stage1

> Claude Code 项目指令文件。在此目录下启动的所有会话自动加载。

## 项目定位

**阶段 I**：基于 ~3232 条脱敏 CPET 汇总数据，构建老年心血管患者运动安全线实验室原型（B_lab），同时输出阶段 III 家庭桥接资产。详见 `docs/PLANNING.md`。

---

## 开发工作流规则

### 会话开始时（必须执行）

1. **读取** `docs/PLANNING.md` — 了解当前里程碑、边界约束和实施顺序
2. **读取** `docs/DEVLOG.md` — 了解已完成内容、遗留问题和下一步任务
3. 在 DEVLOG.md 的里程碑进度表中确认当前处于哪个里程碑

### 会话进行中

- 严格按照 PLANNING.md 中的里程碑顺序推进，不跳步
- 遇到边界问题（数据泄漏、标签设计）须对照 `configs/data/` 中的规则文件
- 任何架构决策须创建或更新 `docs/decisions/ADR-xxx-*.md`

### 会话结束时（任何代码变更后必须执行）

更新 `docs/DEVLOG.md`，包括：

1. 新增会话条目（格式：`### [YYYY-MM-DD] 会话 #N — 标题`）
2. 记录本次完成内容、关键决策、遗留问题、下一步
3. 更新里程碑进度表（状态 + 完成日期）
4. 更新代码版本历史（若有版本 bump）

---

## 代码规范

| 规范 | 要求 |
|---|---|
| 注释语言 | 中文注释，英文变量名（snake_case） |
| 配置 | 规则外置 YAML（`configs/`），不在代码中硬编码阈值 |
| 数据泄漏 | `leakage_guard` 是方法学约束，**不可跳过或绕过** |
| 真实数据 | 真实患者数据**不入 Git**（见 `docs/decisions/ADR-005-data-not-in-git.md`） |
| Python | 3.11+，见 `docs/decisions/ADR-006-python-version.md` |
| 测试 | 新功能须附 `tests/` 单元测试或集成测试 |

---

## Git 规范

- **Commit 格式**：`feat/fix/docs/test/refactor/chore: 描述`（Conventional Commits）
- **分支命名**：功能 `feat/xxx`，修复 `fix/xxx`
- **主干保护**：不直接 push `main`；通过 `dev` 分支 PR 合并
- **禁止提交**：真实数据文件、`.env` 文件、含密钥的配置

---

## 关键文件索引

| 文件 | 用途 |
|---|---|
| `docs/PLANNING.md` | 项目总规划（四阶段路线 + 里程碑 + 建模架构） |
| `docs/DEVLOG.md` | 开发日志（会话记录 + 里程碑进度 + 版本历史） |
| `configs/data/schema_v1.yaml` | 字段 schema |
| `configs/data/label_rules_v1.yaml` | P0/P1 标签规则 + leakage guard 配置 |
| `configs/data/qc_rules_v1.yaml` | QC 规则 |
| `src/cpet_stage1/labels/leakage_guard.py` | 泄漏防护实现 |
| `docs/decisions/` | 架构决策记录（ADR） |
| `docs/protocol/stage1_scope.md` | 阶段 I 范围声明 |
