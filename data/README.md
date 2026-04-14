# Data Directory

## 重要：数据保密声明

**本目录下除 `demo/` 外的所有数据文件均不纳入版本控制（.gitignore）。**

真实患者数据存放于受保护的本地路径，通过 `DATA_DIR` 环境变量配置访问。

---

## 数据分层架构

```
data/
├── raw/          # 原始导入数据（Excel → Parquet，不修改）
├── staging/      # 清洗中间层（字段映射、类型转换）
├── curated/      # 质控通过的标准数据集
├── features/     # 特征工程输出（训练/验证/测试矩阵）
├── labels/       # P0/P1 标签（由 label_engine 生成）
├── anchors/      # 锚点变量包（供阶段 II 桥接）
├── contracts/    # 受试者/会话 ID 合约
├── manifests/    # 数据清单（catalog.csv, hash_registry.json）
└── demo/         # 合成演示数据（唯一纳入版本控制的数据）
```

## 数据流

```
Excel (raw) → staging → curated → features + labels → modeling
                                                     ↓
                                              anchors (Stage II bridge)
```

## 分层说明

| 层 | 内容 | 来源 |
|---|---|---|
| raw | 从 DATA_DIR 导入的原始 Parquet | `make ingest` |
| staging | 字段映射后数据 | `make ingest` |
| curated | QC 通过的完整记录 | `make qc` |
| features | 标准化特征矩阵 (X_train, X_test) | `make features` |
| labels | P0/P1 标签向量 (y_train, y_test) | `make labels` |
| anchors | 锚点包 (R/T/I 三轴) | `make anchors` |
| contracts | 受试者 ID 注册表 | `make cohort` |

## 版本控制（manifests/）

- `dataset_catalog.csv` — 数据集注册表（版本、来源、记录数）
- `hash_registry.json` — 文件 SHA256 哈希（数据完整性验证）
- `snapshot_notes.md` — 快照备注（纳入版本控制）
