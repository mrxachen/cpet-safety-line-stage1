# Stage 1B 变量角色数据字典

> 版本：Stage 1B（2026-04-22）
> 配置文件：`configs/data/variable_roles_stage1b.yaml`

---

## 背景与设计原则

Stage 1B 的核心方法学转变是将变量分为**四类角色**，防止构念污染和标签泄漏：

| 角色 | 进入哪里 | 禁止进入哪里 |
|---|---|---|
| 表型主体（Phenotype） | burden 计算 → phenotype zone | 监督标签定义 |
| 不稳定信号（Instability） | override 规则 | burden 均值 |
| 验证变量（Validation） | 构念效度分析、confidence engine | zone 定义 |
| 禁用变量（Excluded） | 无 | 一切特征集 |

---

## A. 表型主体变量（Phenotype Variables）

### Reserve 域（心肺储备）

| 字段 | 中文含义 | 方向 | 必需 | 说明 |
|---|---|---|---|---|
| `vo2_peak` | 峰值摄氧量 (mL/kg/min) | 越高越好 | ✅ | 主锚点变量 |
| `vo2_peak_pct_pred` | VO2peak占预测值% | 越高越好 | — | 仅用于phenotype，不再定义监督标签 |
| `vt1_vo2` | 无氧阈时VO2 (mL/kg/min) | 越高越好 | — | VT1/AT表示储备深度 |
| `at_vo2` | AT时VO2备用字段 | 越高越好 | — | 与vt1_vo2二选一 |
| `o2_pulse_peak` | 峰值氧脉搏 (mL/beat) | 越高越好 | — | 反映每搏量×a-vO2差 |
| `mets_peak` | 峰值代谢当量 | 越高越好 | — | 功能活动当量 |
| `hrr_1min` | 1分钟心率恢复 | 越高越好 | — | 迷走神经功能代理 |

**Burden 转换规则（higher_better）**：
- `≥ q25` → burden = 0（正常）
- `q10 ≤ x < q25` → burden = 0.5（边界）
- `< q10` → burden = 1.0（异常）

**域内聚合**：取可用变量均值；至少需要 **2 个**变量，否则降置信度

### Ventilatory 域（通气效率）

| 字段 | 中文含义 | 方向 | 必需 | 说明 |
|---|---|---|---|---|
| `ve_vco2_slope` | 通气效率斜率 | 越高越差 | ✅ | 核心通气负担变量 |
| `oues` | 氧摄取效率平台 | 越高越好 | — | VE/VCO2 slope的补充 |

**Burden 转换规则（higher_worse，以ve_vco2_slope为例）**：
- `≤ q75` → burden = 0（正常）
- `q75 < x ≤ q90` → burden = 0.5（边界）
- `> q90` → burden = 1.0（异常）

**域内聚合**：取可用变量均值；至少需要 **1 个**变量，否则降置信度

---

## B. 不稳定覆盖变量（Instability Variables）

> 这些变量**不参与 burden 均值**，而是作为 Override 规则直接决定 zone 提升。

### Severe 规则（任一满足 → 强制 Red）

| 字段 | 触发条件 | 说明 |
|---|---|---|
| `eih_status` | `== True` | 运动诱发低氧；即刻覆盖 |
| `bp_peak_sys` | `> 220 mmHg` | 峰值收缩压极端升高 |
| `bp_peak_dia` | `> 110 mmHg` | 峰值舒张压升高（若有数据） |
| `o2_pulse_trajectory` | `in ["下降","晚期下降","运动终止前下降","持续平台","晚期平台"]` | O2脉搏轨迹异常 |

### Mild 规则（满足 → Green 升 Yellow，不降级 Red）

| 字段 | 触发条件 | 说明 |
|---|---|---|
| `bp_peak_sys` | `200 < x ≤ 220 mmHg` | 边界高血压反应 |
| `effort_adequacy` | `== "uncertain"` | 努力度不充分但未明确终止 |

**Override 逻辑**：
```
phenotype_zone (any) + severe → Red
phenotype_zone green + mild → Yellow
phenotype_zone yellow/red + mild → 保持不变（不降级）
```

---

## C. 验证变量（Validation Variables）

> 这些变量**不直接定义 final zone**，只用于构念效度分析和 confidence engine。

| 字段 | 角色 | 说明 |
|---|---|---|
| `test_result` | 外部锚定 | 运动试验临床结果；用于验证zone是否与结局同向 |
| `group_code` | 队列分层 | CTRL/HTN_HISTORY/EHT_ONLY 分层分析 |
| `diagnosis_htn` | 队列上下文 | 高血压病史 |
| `diagnosis_cad` | 队列上下文 | 冠心病病史 |
| `diagnosis_hf` | 队列上下文 | 心衰病史 |

---

## D. 明确禁用变量（Excluded Variables）

| 字段 | 禁用原因 |
|---|---|
| `zone_v2` / `zone_v3` | 旧标签直接副本，循环依赖 |
| `p1_zone` / `p0_zone` | P1/P0 监督标签，循环依赖 |
| `eih_status_raw` | 与 eih_status 高度共线且含结论性语义 |
| `concordance_zone` | Phase G 多定义投票派生标签，循环依赖 |

---

## E. 协变量（Reference Model Covariates）

用于建立条件分位参考模型（`reference_quantiles.py`）的调整变量：

| 字段 | 类型 | 说明 |
|---|---|---|
| `age` | 数值（样条） | 年龄；建议5结点自然样条 |
| `bmi` | 数值 | 体质指数 |
| `sex` | 类别 | 性别（OHE编码） |
| `protocol_mode` | 类别 | 测试模式（cycle/treadmill；OHE编码） |

---

## F. Stage 1B 产出列定义

最终每个受试者一行，包含以下列：

| 列名 | 类型 | 说明 |
|---|---|---|
| `reserve_burden` | float [0,1] | Reserve域平均burden |
| `vent_burden` | float [0,1] | Ventilatory域平均burden |
| `p_lab` | float [0,1] | 主体表型分数（0.5×reserve + 0.5×vent） |
| `phenotype_zone` | str | green/yellow/red（基于参考分位切点） |
| `instability_severe` | bool | 是否触发severe规则 |
| `instability_mild` | bool | 是否触发mild规则（非severe） |
| `final_zone_before_confidence` | str | override后zone（未经confidence处理） |
| `confidence_score` | float [0,1] | 置信度综合评分 |
| `confidence_label` | str | high/medium/low |
| `indeterminate_flag` | bool | True = 样本不应被高信度解释 |
| `final_zone` | str | 最终zone（含yellow_gray） |
| `outcome_risk_prob` | float | outcome模型预测概率（验证用） |
| `outcome_risk_tertile` | str | low/mid/high三分位（validation agreement用） |
| `anomaly_flag` | bool | Mahalanobis异常标记（QC用） |

---

## 与旧主线对比

| 方面 | Legacy（v2.2.0） | Stage 1B |
|---|---|---|
| 标签来源 | label_rules_v2/v3（deterministic rules on phenotype vars） | 参考分位 + override rules |
| test_result 角色 | 外部锚定（Phase G） | 外部锚定（同，但更明确） |
| ML任务 | 学习 P1 green/yellow/red → AUC/F1 | 验证器（outcome-anchor），非主产出 |
| 不确定性 | Phase G concordance（73.5%不确定） | confidence engine（显式indeterminate） |
| 主体负担 | R/T/I三轴（含instability均值） | Reserve/Ventilatory双域 + override分离 |
