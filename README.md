# cpet-safety-line-stage1

**CPET-Based Exercise Safety-Line Prediction for Older Adults with Cardiovascular Disease**
**基于CPET的老年心血管疾病人群运动安全线预测 — 阶段 I**

> 主动健康：让患者在精准监测下敢于运动，而不是因恐惧而躺平。

---

## 项目简介

本仓库为四阶段纵向研究的**阶段 I（回顾性建模）**代码库。研究对象为老年高血压、冠心病、心力衰竭患者，核心目标是从心肺运动试验（CPET）summary 级别数据中，提取可以描述个体"运动安全线"的关键变量，并建立初步的统计/机器学习预测模型。

### 四阶段路线图

```
Stage I  ──► Stage II ──► Stage III ──► Stage IV
回顾性建模   前瞻性队列   家庭桥接验证   穿戴设备闭环
(本仓库)    (院内CPET)   (6MWT/家用HR)   (实时安全警报)
```

### 阶段 I 边界（Scope）

| 在范围内 (In Scope) | 不在范围内 (Out of Scope) |
|---|---|
| 历史 CPET summary 数据清洗与建库 | 逐次呼吸原始波形分析 |
| 统计描述 (Table 1) | 前瞻性数据收集 |
| P0 安全事件预测（历史事件代理标签） | 家庭穿戴设备接入 |
| P1 运动分区预测（VT/RCP zone） | 实时推理部署 |
| 锚点变量包导出（供阶段 II 桥接） | 临床决策支持系统 |
| Bridge 准备文档（问卷、假设列表） | — |

---

## 数据保密声明

本仓库**不包含任何真实患者数据**。

- `data/raw/`, `data/staging/`, `data/curated/` 等目录已在 `.gitignore` 中排除
- 仅 `data/demo/` 中的**合成数据**（synthetic data）会被纳入版本控制
- 所有真实数据存放于本地受保护路径，需通过 `DATA_DIR` 环境变量配置访问

---

## 快速开始

### 环境要求
- Python >= 3.11
- uv (推荐) 或 pip

### 安装

```bash
# 克隆仓库
git clone https://github.com/mrxachen/cpet-safety-line-stage1.git
cd cpet-safety-line-stage1

# 复制并配置环境变量
cp .env.example .env
# 编辑 .env 填写 DATA_DIR 等路径

# 安装依赖（uv 推荐）
make install
# 或: pip install -e ".[dev]"
```

### 基本工作流

```bash
make ingest        # 数据导入（需配置 DATA_DIR）
make qc            # 数据质控报告
make cohort        # 队列注册
make labels        # 标签生成（P0/P1）
make features      # 特征工程
make model-p0      # P0 基线模型（安全事件预测）
make model-p1      # P1 分区模型（VT/RCP zone）
make reports       # 生成报告
make bridge-prep   # 阶段 II 桥接准备包
```

---

## 目录结构

```
cpet-safety-line-stage1/
├── configs/           # YAML 配置（schema, field_map, qc_rules, model_params…）
├── data/              # 数据层（raw/staging/curated/features/labels/anchors）
│   └── demo/          # 合成演示数据（唯一纳入版本控制的数据）
├── docs/              # 文档（protocol, data_dictionary, bridge, ADR decisions）
├── notebooks/         # 探索性 Jupyter Notebooks (00~07 + 99_sandbox)
├── src/cpet_stage1/   # 核心 Python 包
│   ├── io/            # 数据读取与 Excel 导入
│   ├── qc/            # 质控规则与验证
│   ├── contracts/     # ID 合约与 session 管理
│   ├── cohort/        # 队列注册
│   ├── labels/        # 标签引擎（P0/P1/proxy）
│   ├── features/      # 特征工程与标准化
│   ├── anchors/       # 锚点变量包构建
│   ├── stats/         # 统计描述（Table 1, 2×2 等）
│   ├── modeling/      # 模型训练、评估、校准、解释
│   ├── bridge_prep/   # 阶段 II 桥接准备
│   ├── interfaces/    # 外部数据接口 schema（ECG/呼吸/传感器）
│   ├── reporting/     # 图表与报告生成
│   └── utils/         # 工具函数（logging, paths, seed）
├── tests/             # 自动化测试
├── outputs/           # 运行输出（不入版本控制）
└── reports/           # 生成的报告（release/ 版本快照入版本控制）
```

---

## 文档索引

| 文档 | 路径 |
|---|---|
| 阶段 I 范围定义 | `docs/protocol/stage1_scope.md` |
| 端点定义 | `docs/protocol/endpoint_definitions.md` |
| 数据请求清单 | `docs/protocol/data_request_checklist.md` |
| 数据字典 | `docs/data_dictionary/` |
| 锚点变量字典 | `docs/bridge/anchor_variable_dictionary_v1.md` |
| 家庭代理假设表 | `docs/bridge/home_proxy_hypothesis_table_v1.md` |
| 架构决策记录 | `docs/decisions/` |

---

## 贡献与开发

```bash
# 安装 pre-commit hooks
pre-commit install

# 运行测试
make test

# 代码风格检查
make lint
```

---

## 许可证

Apache License 2.0 — 见 [LICENSE](LICENSE)

---

*Stage I · 回顾性建模 · 2025–2026*
