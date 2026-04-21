# P1 代理泄漏消融实验报告

> 生成日期：2026-04-21
> **目的**：量化 `vo2_peak` 通过 `vo2_peak_pct_pred = vo2_peak / predicted_peak × 100` 
> 对 P1 预测性能的代理泄漏贡献。
> 由于 leakage_guard 排除了 `vo2_peak_pct_pred`，但保留了 `vo2_peak`（绝对值），
> 树模型可部分重建标签边界阈值信息。

## 1. 实验设计

| 变体 | 特征集 | 说明 |
|---|---|---|
| Full | vo2_peak + hr_peak + o2_pulse_peak + vt1_vo2 + hr_recovery + oues + mets_peak | 当前默认 |
| No-VO2 | hr_peak + o2_pulse_peak + vt1_vo2 + hr_recovery + oues + mets_peak | 排除 vo2_peak |
| VO2-only | vo2_peak + age + sex | 代理泄漏上界 |

**分类器**：LightGBM（multiclass, class_weight=balanced）
**分割**：固定 80/20 训练/测试集，5 折交叉验证

## 2. 性能对比表

| 变体 | F1_macro | κ (weighted) | Accuracy | CV-F1 (mean±std) | Green召回 | Yellow召回 | Red召回 |
|---|---|---|---|---|---|---|---|
| **Full** | 0.4584 | 0.2368 | 0.4945 | 0.4513±0.0162 | 0.630 | 0.481 | 0.268 |
| **No-VO2** | 0.4554 | 0.2433 | 0.4914 | 0.4553±0.0148 | 0.627 | 0.481 | 0.261 |
| **VO2-only** | 0.4413 | 0.2001 | 0.4788 | 0.4614±0.0148 | 0.612 | 0.476 | 0.242 |

> **Full → No-VO2 Delta**: ΔF1=+0.0030, Δκ=-0.0065, ΔRed召回=+0.007
> **VO2-only vs Full Delta**: ΔF1=-0.0172

## 3. 各类别 F1 详情

| 变体 | Green F1 | Yellow F1 | Red F1 |
|---|---|---|---|
| Full | 0.6248 | 0.4566 | 0.2939 |
| No-VO2 | 0.6360 | 0.4505 | 0.2797 |
| VO2-only | 0.6036 | 0.4531 | 0.2671 |

## 4. 混淆矩阵

### Full
```
Predicted:    Green  Yellow  Red
True Green:     174      63   39
True Yellow:     62     100   46
True Red:        45      67   41
```

### No-VO2
```
Predicted:    Green  Yellow  Red
True Green:     173      63   40
True Yellow:     55     100   53
True Red:        40      73   40
```

### VO2-only
```
Predicted:    Green  Yellow  Red
True Green:     169      67   40
True Yellow:     62      99   47
True Red:        53      63   37
```

## 5. 代理泄漏解读

Full 与 No-VO2 变体 F1 差异 <0.03，提示 **代理泄漏贡献有限**。vo2_peak 绝对值在当前数据集中对 P1 区间边界的代理能力不强，可能因参考方程 R²=0.298（年龄/性别解释力低）导致 vo2_peak → %pred 的重建精度不足。

VO2-only（代理泄漏上界）F1=0.4413，代表仅通过 vo2_peak+age+sex 重建 %pred 阈值所能达到的性能上界。

**临床意义**：Red 类召回率是安全线预测的核心指标。
Full 模型 Red 召回=0.268，No-VO2 模型 Red 召回=0.261。
两者差异反映了 vo2_peak 对高风险患者识别的边际贡献。

**结论**：论文 Discussion 中将 P1 F1≈0.50 定位为 'summary-level 预测天花板' 的论断，
在量化代理泄漏贡献后仍然成立
——实际天花板来自特征集固有局限，而非泄漏驱动。

---
_由 ablation_p1.py 自动生成（Phase E 修订 2）_