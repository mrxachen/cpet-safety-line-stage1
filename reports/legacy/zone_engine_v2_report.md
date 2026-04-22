# Phase F Step 2 — 数据驱动安全区引擎报告（v2）

## 核心方法

1. **R/T/I 轴权重**：基于与 test_result 的 point-biserial 相关性确定
2. **Zone 切点**：Method A（结局锚定）— Youden's J 优化
3. **个性化**：HTN history × sex × age 组分层

## R/T/I 轴权重（数据驱动）

- **方法**：correlation
- **R轴（储备）权重**：0.314
- **T轴（阈值）权重**：0.314
- **I轴（不稳定性）权重**：0.371
- **各分量与结局的相关性**：
  - `i_risk`：r=+0.059
  - `t_risk`：r=-0.024
  - `r_risk`：r=+0.010

## 全局 Zone 切点

- **方法**：reference_percentile
- **Green/Yellow 界（低切点）**：24.17
  - 灵敏度：nan，特异度：nan
- **Yellow/Red 界（高切点）**：27.13
  - 灵敏度：0.312，特异度：0.854
  - Youden's J：0.167
  - Bootstrap 95% CI（高切点）：[7.28, 58.76]
- **阳性样本**：468/3188 (14.7%)

## 与文献切点的对比

| 指标 | 本数据驱动切点 | 文献先验（Weber-Janicki等）| 偏差 |
|---|---|---|---|
| VO₂peak %pred (green) | 86.0% | 文献: Green≥70%, Yellow 50-70%, Red<50% | — |
| VO₂peak %pred (yellow) | 72.0% | 文献: Green≥70%, Yellow 50-70%, Red<50% | — |
| VO₂peak %pred (red) | 69.0% | 文献: Green≥70%, Yellow 50-70%, Red<50% | — |

## Zone 分布（全局 + 分层）

**global**（N=3206）：
  - green: 1316 (41.0%)
  - yellow: 544 (17.0%)
  - red: 1346 (42.0%)

**group=CTRL**（N=1858）：
  - green: 962 (51.8%)
  - yellow: 350 (18.8%)
  - red: 546 (29.4%)

**group=HTN_HISTORY_NO_EHT**（N=738）：
  - green: 325 (44.0%)
  - yellow: 147 (19.9%)
  - red: 266 (36.0%)

**group=HTN_HISTORY_WITH_EHT**（N=277）：
  - green: 11 (4.0%)
  - yellow: 18 (6.5%)
  - red: 248 (89.5%)

**group=EHT_ONLY**（N=333）：
  - green: 18 (5.4%)
  - yellow: 29 (8.7%)
  - red: 286 (85.9%)

**sex=M**（N=1678）：
  - green: 741 (44.2%)
  - yellow: 295 (17.6%)
  - red: 642 (38.3%)

**sex=F**（N=1520）：
  - green: 575 (37.8%)
  - yellow: 248 (16.3%)
  - red: 697 (45.9%)

## 新旧 Zone 重分类矩阵（v1 P1 zone → v2 Z_lab_v2）

| 旧 P1 zone | green | red | yellow |
|---|---|---|---|
| green | 958 | 145 | 186 |
| red | 43 | 685 | 69 |
| yellow | 311 | 503 | 285 |

**一致率**：60.5%（对角线比例）

## 分层切点汇总

| 分层 | N阳性 | N总计 | 低切点 | 高切点 | Youden J | 方法 |
|---|---|---|---|---|---|---|
| htn_history=False | 295 | 2177 | 13.86 | 58.76 | 0.365 | youden |
| htn_history=True | 173 | 1011 | 23.03 | 10.60 | 0.173 | youden |
| sex=M | 253 | 1669 | 20.75 | 7.28 | 0.152 | youden |
| sex=F | 214 | 1511 | 16.32 | 55.46 | 0.460 | youden |
| age_group=age>=67 | 244 | 1688 | 15.15 | 57.28 | 0.256 | youden |
| age_group=age<67 | 224 | 1500 | 13.71 | 54.17 | 0.227 | youden |
| beta_blocker=bb_no | 444 | 2965 | 14.29 | 54.17 | 0.185 | youden |
| beta_blocker=bb_yes | 24 | 223 | 16.62 | 49.48 | 0.229 | youden |
