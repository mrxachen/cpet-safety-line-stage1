# Post-hoc 两两比较报告（Dunn's 检验 + Bonferroni 校正）

> 共检验 11 个变量

## 汇总：10/11 个变量有显著两两差异

| 变量 | 显著对数 | 示例显著对 |
|---|---|---|
| height_cm | 3 | CTRL vs HTN_HISTORY_NO_EHT |
| weight_kg | 5 | CTRL vs EHT_ONLY |
| vo2_peak | 4 | CTRL vs HTN_HISTORY_NO_EHT |
| hr_peak | 5 | CTRL vs HTN_HISTORY_NO_EHT |
| o2_pulse_peak | 1 | CTRL vs EHT_ONLY |
| vt1_vo2 | 4 | CTRL vs HTN_HISTORY_NO_EHT |
| ve_vco2_slope | 2 | CTRL vs HTN_HISTORY_NO_EHT |
| vo2_peak_pct_pred | 3 | CTRL vs HTN_HISTORY_NO_EHT |
| hr_recovery | 4 | CTRL vs HTN_HISTORY_NO_EHT |
| mets_peak | 4 | CTRL vs HTN_HISTORY_NO_EHT |

---

## 各变量详情

### age
- Kruskal-Wallis: H=3.109, p=0.3751
- 两两比较: 6 对（Bonferroni α=0.0083）

| 组1 | 组2 | Z统计量 | p (原始) | p (校正) | 显著 |
|---|---|---|---|---|---|
| CTRL | EHT_ONLY | 0.333 | 0.7393 | 1.0000 |  |
| CTRL | HTN_HISTORY_NO_EHT | 0.827 | 0.4085 | 1.0000 |  |
| CTRL | HTN_HISTORY_WITH_EHT | 1.687 | 0.0916 | 0.5493 |  |
| EHT_ONLY | HTN_HISTORY_NO_EHT | 0.245 | 0.8066 | 1.0000 |  |
| EHT_ONLY | HTN_HISTORY_WITH_EHT | 1.093 | 0.2745 | 1.0000 |  |
| HTN_HISTORY_NO_EHT | HTN_HISTORY_WITH_EHT | 1.032 | 0.3022 | 1.0000 |  |

### height_cm
- Kruskal-Wallis: H=20.878, p=0.0001
- 两两比较: 6 对（Bonferroni α=0.0083）

| 组1 | 组2 | Z统计量 | p (原始) | p (校正) | 显著 |
|---|---|---|---|---|---|
| CTRL | EHT_ONLY | -2.506 | 0.0122 | 0.0732 |  |
| CTRL | HTN_HISTORY_NO_EHT | 2.639 | 0.0083 | 0.0500 | ✓ |
| CTRL | HTN_HISTORY_WITH_EHT | 2.182 | 0.0291 | 0.1748 |  |
| EHT_ONLY | HTN_HISTORY_NO_EHT | 3.995 | 0.0001 | 0.0004 | ✓ |
| EHT_ONLY | HTN_HISTORY_WITH_EHT | 3.562 | 0.0004 | 0.0022 | ✓ |
| HTN_HISTORY_NO_EHT | HTN_HISTORY_WITH_EHT | 0.366 | 0.7141 | 1.0000 |  |

### weight_kg
- Kruskal-Wallis: H=130.447, p=0.0000
- 两两比较: 6 对（Bonferroni α=0.0083）

| 组1 | 组2 | Z统计量 | p (原始) | p (校正) | 显著 |
|---|---|---|---|---|---|
| CTRL | EHT_ONLY | -5.382 | 0.0000 | 0.0000 | ✓ |
| CTRL | HTN_HISTORY_NO_EHT | -8.358 | 0.0000 | 0.0000 | ✓ |
| CTRL | HTN_HISTORY_WITH_EHT | -8.657 | 0.0000 | 0.0000 | ✓ |
| EHT_ONLY | HTN_HISTORY_NO_EHT | -0.634 | 0.5261 | 1.0000 |  |
| EHT_ONLY | HTN_HISTORY_WITH_EHT | -2.898 | 0.0038 | 0.0225 | ✓ |
| HTN_HISTORY_NO_EHT | HTN_HISTORY_WITH_EHT | -2.757 | 0.0058 | 0.0350 | ✓ |

### vo2_peak
- Kruskal-Wallis: H=287.284, p=0.0000
- 两两比较: 6 对（Bonferroni α=0.0083）

| 组1 | 组2 | Z统计量 | p (原始) | p (校正) | 显著 |
|---|---|---|---|---|---|
| CTRL | EHT_ONLY | -0.441 | 0.6595 | 1.0000 |  |
| CTRL | HTN_HISTORY_NO_EHT | 15.344 | 0.0000 | 0.0000 | ✓ |
| CTRL | HTN_HISTORY_WITH_EHT | 8.618 | 0.0000 | 0.0000 | ✓ |
| EHT_ONLY | HTN_HISTORY_NO_EHT | 10.407 | 0.0000 | 0.0000 | ✓ |
| EHT_ONLY | HTN_HISTORY_WITH_EHT | 7.110 | 0.0000 | 0.0000 | ✓ |
| HTN_HISTORY_NO_EHT | HTN_HISTORY_WITH_EHT | -1.570 | 0.1165 | 0.6989 |  |

### hr_peak
- Kruskal-Wallis: H=438.957, p=0.0000
- 两两比较: 6 对（Bonferroni α=0.0083）

| 组1 | 组2 | Z统计量 | p (原始) | p (校正) | 显著 |
|---|---|---|---|---|---|
| CTRL | EHT_ONLY | -2.618 | 0.0089 | 0.0531 |  |
| CTRL | HTN_HISTORY_NO_EHT | 19.517 | 0.0000 | 0.0000 | ✓ |
| CTRL | HTN_HISTORY_WITH_EHT | 6.447 | 0.0000 | 0.0000 | ✓ |
| EHT_ONLY | HTN_HISTORY_NO_EHT | 15.108 | 0.0000 | 0.0000 | ✓ |
| EHT_ONLY | HTN_HISTORY_WITH_EHT | 7.004 | 0.0000 | 0.0000 | ✓ |
| HTN_HISTORY_NO_EHT | HTN_HISTORY_WITH_EHT | -6.104 | 0.0000 | 0.0000 | ✓ |

### o2_pulse_peak
- Kruskal-Wallis: H=8.522, p=0.0364
- 两两比较: 6 对（Bonferroni α=0.0083）

| 组1 | 组2 | Z统计量 | p (原始) | p (校正) | 显著 |
|---|---|---|---|---|---|
| CTRL | EHT_ONLY | -2.917 | 0.0035 | 0.0212 | ✓ |
| CTRL | HTN_HISTORY_NO_EHT | -0.677 | 0.4983 | 1.0000 |  |
| CTRL | HTN_HISTORY_WITH_EHT | -0.352 | 0.7252 | 1.0000 |  |
| EHT_ONLY | HTN_HISTORY_NO_EHT | 2.197 | 0.0280 | 0.1682 |  |
| EHT_ONLY | HTN_HISTORY_WITH_EHT | 1.872 | 0.0613 | 0.3676 |  |
| HTN_HISTORY_NO_EHT | HTN_HISTORY_WITH_EHT | 0.096 | 0.9235 | 1.0000 |  |

### vt1_vo2
- Kruskal-Wallis: H=163.894, p=0.0000
- 两两比较: 6 对（Bonferroni α=0.0083）

| 组1 | 组2 | Z统计量 | p (原始) | p (校正) | 显著 |
|---|---|---|---|---|---|
| CTRL | EHT_ONLY | -0.611 | 0.5412 | 1.0000 |  |
| CTRL | HTN_HISTORY_NO_EHT | 11.245 | 0.0000 | 0.0000 | ✓ |
| CTRL | HTN_HISTORY_WITH_EHT | 7.061 | 0.0000 | 0.0000 | ✓ |
| EHT_ONLY | HTN_HISTORY_NO_EHT | 7.899 | 0.0000 | 0.0000 | ✓ |
| EHT_ONLY | HTN_HISTORY_WITH_EHT | 6.013 | 0.0000 | 0.0000 | ✓ |
| HTN_HISTORY_NO_EHT | HTN_HISTORY_WITH_EHT | -0.477 | 0.6331 | 1.0000 |  |

### ve_vco2_slope
- Kruskal-Wallis: H=41.131, p=0.0000
- 两两比较: 6 对（Bonferroni α=0.0083）

| 组1 | 组2 | Z统计量 | p (原始) | p (校正) | 显著 |
|---|---|---|---|---|---|
| CTRL | EHT_ONLY | -2.006 | 0.0449 | 0.2692 |  |
| CTRL | HTN_HISTORY_NO_EHT | -6.152 | 0.0000 | 0.0000 | ✓ |
| CTRL | HTN_HISTORY_WITH_EHT | -2.860 | 0.0042 | 0.0254 | ✓ |
| EHT_ONLY | HTN_HISTORY_NO_EHT | -2.201 | 0.0277 | 0.1665 |  |
| EHT_ONLY | HTN_HISTORY_WITH_EHT | -0.776 | 0.4379 | 1.0000 |  |
| HTN_HISTORY_NO_EHT | HTN_HISTORY_WITH_EHT | 1.180 | 0.2381 | 1.0000 |  |

### vo2_peak_pct_pred
- Kruskal-Wallis: H=44.927, p=0.0000
- 两两比较: 6 对（Bonferroni α=0.0083）

| 组1 | 组2 | Z统计量 | p (原始) | p (校正) | 显著 |
|---|---|---|---|---|---|
| CTRL | EHT_ONLY | -2.368 | 0.0179 | 0.1074 |  |
| CTRL | HTN_HISTORY_NO_EHT | 5.026 | 0.0000 | 0.0000 | ✓ |
| CTRL | HTN_HISTORY_WITH_EHT | -2.084 | 0.0372 | 0.2230 |  |
| EHT_ONLY | HTN_HISTORY_NO_EHT | 5.421 | 0.0000 | 0.0000 | ✓ |
| EHT_ONLY | HTN_HISTORY_WITH_EHT | 0.096 | 0.9235 | 1.0000 |  |
| HTN_HISTORY_NO_EHT | HTN_HISTORY_WITH_EHT | -5.002 | 0.0000 | 0.0000 | ✓ |

### hr_recovery
- Kruskal-Wallis: H=90.427, p=0.0000
- 两两比较: 6 对（Bonferroni α=0.0083）

| 组1 | 组2 | Z统计量 | p (原始) | p (校正) | 显著 |
|---|---|---|---|---|---|
| CTRL | EHT_ONLY | -0.897 | 0.3699 | 1.0000 |  |
| CTRL | HTN_HISTORY_NO_EHT | 8.831 | 0.0000 | 0.0000 | ✓ |
| CTRL | HTN_HISTORY_WITH_EHT | 3.527 | 0.0004 | 0.0025 | ✓ |
| EHT_ONLY | HTN_HISTORY_NO_EHT | 6.588 | 0.0000 | 0.0000 | ✓ |
| EHT_ONLY | HTN_HISTORY_WITH_EHT | 3.443 | 0.0006 | 0.0034 | ✓ |
| HTN_HISTORY_NO_EHT | HTN_HISTORY_WITH_EHT | -2.197 | 0.0280 | 0.1681 |  |

### mets_peak
- Kruskal-Wallis: H=280.987, p=0.0000
- 两两比较: 6 对（Bonferroni α=0.0083）

| 组1 | 组2 | Z统计量 | p (原始) | p (校正) | 显著 |
|---|---|---|---|---|---|
| CTRL | EHT_ONLY | -0.685 | 0.4934 | 1.0000 |  |
| CTRL | HTN_HISTORY_NO_EHT | 15.105 | 0.0000 | 0.0000 | ✓ |
| CTRL | HTN_HISTORY_WITH_EHT | 8.506 | 0.0000 | 0.0000 | ✓ |
| EHT_ONLY | HTN_HISTORY_NO_EHT | 10.481 | 0.0000 | 0.0000 | ✓ |
| EHT_ONLY | HTN_HISTORY_WITH_EHT | 7.206 | 0.0000 | 0.0000 | ✓ |
| HTN_HISTORY_NO_EHT | HTN_HISTORY_WITH_EHT | -1.524 | 0.1275 | 0.7652 |  |
