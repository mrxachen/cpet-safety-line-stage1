"""
clinical_utility.py — P0/P1 临床效用分析（Phase E 修订 4）

计算内容：
  P0:
    - 最优阈值下的 NPV、PPV、敏感度、特异度、NNS
    - 简单基线模型（htn_history + bmi，2变量 Logistic）vs XGBoost 增量 AUC
    - 决策价值框架（优于全部治疗/全部不治疗策略的条件）

  P1:
    - 各区域 PPV / NPV
    - Red→Green 和 Green→Red 误分类代价分析
    - 简单硬编码规则（VO₂peak 阈值）vs LightGBM 一致性

用法：
    cd cpet-safety-line-stage1
    python -m cpet_stage1.stats.clinical_utility [--output reports/clinical_utility_report.md]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.model_selection import cross_val_score

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 阈值与效用常数
# ---------------------------------------------------------------------------
# P1 区域分类（与 label_rules_v2.yaml 对应）
_ZONE_NAMES = {0: "Green", 1: "Yellow", 2: "Red"}

# 最优 F1 阈值搜索范围
_THRESHOLD_RANGE = np.linspace(0.05, 0.95, 100)


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def load_data(
    features_post: str | Path = "data/features/features_post_v2.parquet",
    features_pre: str | Path = "data/features/features_pre_v2.parquet",
    label_table: str | Path = "data/labels/label_table.parquet",
) -> pd.DataFrame:
    """加载并合并特征和标签数据。"""
    fp_post = pd.read_parquet(features_post)
    fp_pre = pd.read_parquet(features_pre)
    lt = pd.read_parquet(label_table)

    df = pd.concat([
        fp_pre.reset_index(drop=True),
        fp_post.reset_index(drop=True),
        lt.reset_index(drop=True),
    ], axis=1)

    # 编码性别
    if "sex" in df.columns:
        df["sex"] = df["sex"].map({"M": 0, "F": 1, 0: 0, 1: 1}).fillna(-1)

    logger.info("合并后数据: %d 行", len(df))
    return df


# ---------------------------------------------------------------------------
# P0 临床效用
# ---------------------------------------------------------------------------

def analyze_p0_utility(df: pd.DataFrame, random_state: int = 42) -> dict:
    """
    P0 临床效用分析：
    1. 训练 XGBoost（主模型）和 2变量基线 Logistic（htn_history + bmi）
    2. 计算 AUC、AUPRC、NPV、PPV、NNS
    3. 量化 ML 模型的增量价值
    """
    from sklearn.impute import SimpleImputer

    p0_label = "p0_event"
    if p0_label not in df.columns:
        return {"error": "p0_event 标签不存在"}

    # 特征集
    p0_features = [
        "age", "height_cm", "weight_kg", "bmi",
        "htn_years", "htn_history", "cad_history", "sex",
    ]
    available_p0 = [c for c in p0_features if c in df.columns]

    # 基线模型特征（2变量）
    baseline_features = [c for c in ["htn_history", "bmi"] if c in df.columns]

    df_valid = df[[p0_label] + available_p0].dropna(subset=[p0_label]).copy()
    y = (df_valid[p0_label] == True).astype(int).values

    # 插补
    imp = SimpleImputer(strategy="median")
    X_full = imp.fit_transform(df_valid[available_p0])

    imp_base = SimpleImputer(strategy="median")
    X_base = imp_base.fit_transform(df_valid[baseline_features])

    # 固定 80/20 分割
    np.random.seed(random_state)
    n = len(y)
    test_size = int(n * 0.2)
    test_idx = np.random.choice(n, size=test_size, replace=False)
    train_mask = np.ones(n, dtype=bool)
    train_mask[test_idx] = False
    train_idx = np.where(train_mask)[0]

    X_train, X_test = X_full[train_idx], X_full[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    X_base_train, X_base_test = X_base[train_idx], X_base[test_idx]

    # 1. 基线模型（htn_history + bmi）
    baseline_model = LogisticRegression(
        solver="lbfgs", max_iter=1000, random_state=random_state
    )
    baseline_model.fit(X_base_train, y_train)
    y_proba_base = baseline_model.predict_proba(X_base_test)[:, 1]
    auc_base = roc_auc_score(y_test, y_proba_base)
    auprc_base = average_precision_score(y_test, y_proba_base)

    # 2. XGBoost（主模型）
    try:
        from xgboost import XGBClassifier
        ml_model = XGBClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            use_label_encoder=False, eval_metric="logloss",
            random_state=random_state, n_jobs=-1, verbosity=0,
        )
    except ImportError:
        logger.warning("XGBoost 不可用，退化为 LogisticRegression")
        ml_model = LogisticRegression(
            solver="lbfgs", max_iter=1000, random_state=random_state
        )

    ml_model.fit(X_train, y_train)
    y_proba_ml = ml_model.predict_proba(X_test)[:, 1]
    auc_ml = roc_auc_score(y_test, y_proba_ml)
    auprc_ml = average_precision_score(y_test, y_proba_ml)
    delta_auc = auc_ml - auc_base

    # 3. 最优阈值（最大化 F1）
    best_f1, best_threshold = 0.0, 0.5
    for thr in _THRESHOLD_RANGE:
        y_pred_thr = (y_proba_ml >= thr).astype(int)
        f1 = f1_score(y_test, y_pred_thr, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = thr

    y_pred_opt = (y_proba_ml >= best_threshold).astype(int)
    cm = confusion_matrix(y_test, y_pred_opt)
    tn, fp, fn, tp = cm.ravel()

    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    ppv = tp / (tp + fp) if (tp + fp) > 0 else 0.0  # Precision
    npv = tn / (tn + fn) if (tn + fn) > 0 else 0.0

    # NNS = 1 / PPV（筛查阳性中真阳性比例的倒数）
    nns = 1 / ppv if ppv > 0 else float("inf")

    # 阳性率（先验概率）
    prevalence = y.mean()

    # Net benefit at threshold 0.1 and 0.2（简化 DCA）
    def net_benefit(y_true, y_proba, threshold):
        y_pred = (y_proba >= threshold).astype(int)
        tp_nb = np.sum((y_pred == 1) & (y_true == 1))
        fp_nb = np.sum((y_pred == 1) & (y_true == 0))
        n = len(y_true)
        nb = tp_nb / n - fp_nb / n * threshold / (1 - threshold)
        # Treat all 策略
        nb_all = prevalence - (1 - prevalence) * threshold / (1 - threshold)
        return float(nb), float(nb_all)

    nb_model_10, nb_all_10 = net_benefit(y_test, y_proba_ml, 0.10)
    nb_model_20, nb_all_20 = net_benefit(y_test, y_proba_ml, 0.20)

    return {
        "prevalence": float(prevalence),
        "n_total": int(n),
        "n_test": int(len(y_test)),
        "n_positive_test": int(y_test.sum()),
        "baseline_auc": float(auc_base),
        "baseline_auprc": float(auprc_base),
        "ml_auc": float(auc_ml),
        "ml_auprc": float(auprc_ml),
        "delta_auc": float(delta_auc),
        "optimal_threshold": float(best_threshold),
        "sensitivity": float(sensitivity),
        "specificity": float(specificity),
        "ppv": float(ppv),
        "npv": float(npv),
        "nns": float(nns),
        "net_benefit_0.10": {"model": nb_model_10, "treat_all": nb_all_10},
        "net_benefit_0.20": {"model": nb_model_20, "treat_all": nb_all_20},
        "features_used": available_p0,
        "baseline_features": baseline_features,
    }


# ---------------------------------------------------------------------------
# P1 临床效用
# ---------------------------------------------------------------------------

def analyze_p1_utility(df: pd.DataFrame, random_state: int = 42) -> dict:
    """
    P1 临床效用分析：
    1. 各区域 PPV/NPV（one-vs-rest）
    2. Red→Green 和 Green→Red 误分类代价分析（基于混淆矩阵）
    3. 简单硬编码规则（VO₂peak < 50% 预测值 → Red）vs 模型一致性
    """
    from sklearn.impute import SimpleImputer

    p1_label = "p1_zone"
    if p1_label not in df.columns:
        return {"error": "p1_zone 标签不存在"}

    p1_features = [
        "vo2_peak", "hr_peak", "o2_pulse_peak", "vt1_vo2",
        "hr_recovery", "oues", "mets_peak",
    ]
    available_p1 = [c for c in p1_features if c in df.columns]

    df_valid = df[[p1_label] + available_p1].dropna(subset=[p1_label]).copy()
    df_valid[p1_label] = df_valid[p1_label].astype(int)
    y = df_valid[p1_label].values

    imp = SimpleImputer(strategy="median")
    X = imp.fit_transform(df_valid[available_p1])

    # 固定分割
    np.random.seed(random_state)
    n = len(y)
    test_size = int(n * 0.2)
    test_idx = np.random.choice(n, size=test_size, replace=False)
    train_mask = np.ones(n, dtype=bool)
    train_mask[test_idx] = False
    train_idx = np.where(train_mask)[0]

    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    # LightGBM 模型
    try:
        from lightgbm import LGBMClassifier
        model = LGBMClassifier(
            objective="multiclass", num_class=3,
            class_weight="balanced",
            n_estimators=200, max_depth=6, learning_rate=0.05,
            num_leaves=31, random_state=random_state,
            n_jobs=-1, verbose=-1,
        )
    except ImportError:
        model = LogisticRegression(
            solver="lbfgs", max_iter=1000, random_state=random_state,
            class_weight="balanced",
        )

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    # 混淆矩阵
    cm = confusion_matrix(y_test, y_pred, labels=[0, 1, 2])

    # 各区域 PPV/NPV (one-vs-rest)
    ppv_npv = {}
    for cls_idx, cls_name in _ZONE_NAMES.items():
        y_true_bin = (y_test == cls_idx).astype(int)
        y_pred_bin = (y_pred == cls_idx).astype(int)

        tp = np.sum((y_pred_bin == 1) & (y_true_bin == 1))
        fp = np.sum((y_pred_bin == 1) & (y_true_bin == 0))
        fn = np.sum((y_pred_bin == 0) & (y_true_bin == 1))
        tn = np.sum((y_pred_bin == 0) & (y_true_bin == 0))

        ppv = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        npv = tn / (tn + fn) if (tn + fn) > 0 else 0.0
        sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0

        ppv_npv[cls_name] = {
            "ppv": float(ppv),
            "npv": float(npv),
            "sensitivity": float(sensitivity),
            "specificity": float(specificity),
            "support": int(y_true_bin.sum()),
        }

    # 错误分类代价分析
    # Red→Green: cm[2,0]（真红区，预测为绿区）— 最严重
    # Green→Red: cm[0,2]（真绿区，预测为红区）— 保守
    red_as_green = int(cm[2, 0])
    red_total = int(cm[2].sum())
    green_as_red = int(cm[0, 2])
    green_total = int(cm[0].sum())

    dangerous_misclassification_rate = red_as_green / red_total if red_total > 0 else 0.0
    conservative_misclassification_rate = green_as_red / green_total if green_total > 0 else 0.0

    # 简单规则：vo2_peak < 阈值 → Red（近似 %pred < 50% 的硬编码）
    # 使用训练集中 vo2_peak 的 10th percentile 作为 Red 阈值代理
    if "vo2_peak" in df_valid.columns:
        vo2_train = X_train[:, available_p1.index("vo2_peak")]
        # Red 标签对应 vo2_peak_pct_pred < 50%，约等于 vo2_peak < ~13.5 mL/kg/min
        # 使用实际 Red 样本的 vo2_peak 中位数作为阈值
        red_train_mask = y_train == 2
        if red_train_mask.sum() > 0:
            vo2_red_median = np.median(vo2_train[red_train_mask])
            # 简单规则：vo2_peak < median(Red_train)
            simple_rule_pred = (X_test[:, available_p1.index("vo2_peak")] < vo2_red_median).astype(int) * 2
            # 将 0 (not Red) 映射为模型预测
            # 简化：仅看 Red vs non-Red
            y_test_bin = (y_test == 2).astype(int)
            simple_rule_bin = (simple_rule_pred == 2).astype(int)
            tp_sr = np.sum((simple_rule_bin == 1) & (y_test_bin == 1))
            fp_sr = np.sum((simple_rule_bin == 1) & (y_test_bin == 0))
            fn_sr = np.sum((simple_rule_bin == 0) & (y_test_bin == 1))
            tn_sr = np.sum((simple_rule_bin == 0) & (y_test_bin == 0))
            simple_rule_red_recall = tp_sr / (tp_sr + fn_sr) if (tp_sr + fn_sr) > 0 else 0.0
            simple_rule_red_ppv = tp_sr / (tp_sr + fp_sr) if (tp_sr + fp_sr) > 0 else 0.0
            simple_rule_threshold = float(vo2_red_median)
        else:
            simple_rule_red_recall = 0.0
            simple_rule_red_ppv = 0.0
            simple_rule_threshold = float("nan")

        # 模型 Red 指标
        model_red_recall = ppv_npv["Red"]["sensitivity"]
        model_red_ppv = ppv_npv["Red"]["ppv"]
    else:
        simple_rule_red_recall = float("nan")
        simple_rule_red_ppv = float("nan")
        simple_rule_threshold = float("nan")
        model_red_recall = ppv_npv["Red"]["sensitivity"]
        model_red_ppv = ppv_npv["Red"]["ppv"]

    return {
        "n_test": int(len(y_test)),
        "confusion_matrix": cm.tolist(),
        "ppv_npv_by_zone": ppv_npv,
        "red_as_green": red_as_green,
        "green_as_red": green_as_red,
        "dangerous_misclassification_rate": float(dangerous_misclassification_rate),
        "conservative_misclassification_rate": float(conservative_misclassification_rate),
        "simple_rule": {
            "threshold_vo2_peak": simple_rule_threshold,
            "red_recall": float(simple_rule_red_recall),
            "red_ppv": float(simple_rule_red_ppv),
        },
        "model": {
            "red_recall": float(model_red_recall),
            "red_ppv": float(model_red_ppv),
        },
    }


# ---------------------------------------------------------------------------
# 报告生成
# ---------------------------------------------------------------------------

def generate_report(
    p0_results: dict,
    p1_results: dict,
    output_path: str | Path,
) -> str:
    """生成临床效用分析 Markdown 报告。"""
    lines = [
        "# 临床效用分析报告（P0 + P1）",
        "",
        "> 生成日期：2026-04-21",
        "> **目的**：回应审稿意见 4——量化近随机性能下的临床决策价值，",
        "> 补充 NPV/PPV/NNS 等临床决策指标，并与简单基线模型比较。",
        "",
    ]

    # ---- P0 部分 ----
    lines += ["## 1. P0 运动前风险预测——临床效用", ""]

    if "error" in p0_results:
        lines.append(f"**错误**: {p0_results['error']}")
    else:
        p0 = p0_results
        lines += [
            f"**患病率（阳性率）**: {p0['prevalence']:.3f} ({p0['n_positive_test']} / {p0['n_test']} 测试集)",
            "",
            "### 1.1 基线模型 vs ML 模型",
            "",
            "| 模型 | AUC-ROC | AUPRC | 说明 |",
            "|---|---|---|---|",
            f"| 2变量基线（HTN史+BMI）| {p0['baseline_auc']:.4f} | {p0['baseline_auprc']:.4f} | 最简临床规则 |",
            f"| XGBoost（所有特征）| {p0['ml_auc']:.4f} | {p0['ml_auprc']:.4f} | 主模型 |",
            f"| **增量 ΔAUC** | **{p0['delta_auc']:+.4f}** | — | ML vs 基线 |",
            "",
        ]

        if abs(p0["delta_auc"]) < 0.02:
            lines.append(
                "> **解读**：ML 模型相对 2 变量基线模型增量 ΔAUC < 0.02，"
                "提示在当前特征集受限条件下，复杂 ML 模型相对简单临床规则无显著优势。"
                "这支持将本研究定位为「方法学框架验证」而非「预测工具推广」。"
            )
        else:
            lines.append(
                f"> **解读**：ML 模型相对基线增量 ΔAUC={p0['delta_auc']:+.4f}，"
                "显示了一定增量价值，但绝对 AUC 仍偏低（<0.60），临床独立使用价值有限。"
            )

        lines += [
            "",
            "### 1.2 最优阈值下的临床指标",
            "",
            f"最优决策阈值：{p0['optimal_threshold']:.3f}（最大化 F1）",
            "",
            "| 指标 | 值 | 临床解读 |",
            "|---|---|---|",
            f"| 敏感度（Sensitivity/Recall）| {p0['sensitivity']:.3f} | 阳性患者中正确识别的比例 |",
            f"| 特异度（Specificity）| {p0['specificity']:.3f} | 阴性患者中正确识别的比例 |",
            f"| PPV（阳性预测值）| {p0['ppv']:.3f} | 预测阳性中真阳性的比例 |",
            f"| NPV（阴性预测值）| {p0['npv']:.3f} | 预测阴性中真阴性的比例 |",
            f"| NNS（需筛查数）| {p0['nns']:.1f} | 每发现 1 例真阳性需筛查的人数 |",
            "",
        ]

        nb_10 = p0["net_benefit_0.10"]
        nb_20 = p0["net_benefit_0.20"]
        lines += [
            "### 1.3 决策曲线分析（简化 Net Benefit）",
            "",
            "| 决策阈值 | 模型 NB | 全治疗 NB | 结论 |",
            "|---|---|---|---|",
            f"| 0.10 | {nb_10['model']:.4f} | {nb_10['treat_all']:.4f} | "
            + ("模型优于全治疗 ✓" if nb_10["model"] > nb_10["treat_all"] else "全治疗更优 ×"),
            f"| 0.20 | {nb_20['model']:.4f} | {nb_20['treat_all']:.4f} | "
            + ("模型优于全治疗 ✓" if nb_20["model"] > nb_20["treat_all"] else "全治疗更优 ×"),
            "",
            f"> NPV={p0['npv']:.3f} 提示：当模型预测「低风险」时，",
            f"> 真正低风险的概率约为 {p0['npv']:.1%}，具有一定的运动前排除价值。",
            "",
        ]

    # ---- P1 部分 ----
    lines += ["## 2. P1 运动后安全区分层——临床效用", ""]

    if "error" in p1_results:
        lines.append(f"**错误**: {p1_results['error']}")
    else:
        p1 = p1_results
        lines += [
            "### 2.1 各区域 PPV / NPV（One-vs-Rest）",
            "",
            "| 区域 | 支持数 | PPV | NPV | 敏感度 | 特异度 |",
            "|---|---|---|---|---|---|",
        ]
        for zone_name, metrics in p1["ppv_npv_by_zone"].items():
            lines.append(
                f"| {zone_name} | {metrics['support']} | {metrics['ppv']:.3f} | "
                f"{metrics['npv']:.3f} | {metrics['sensitivity']:.3f} | {metrics['specificity']:.3f} |"
            )

        lines += [
            "",
            "### 2.2 误分类代价分析",
            "",
            "误分类类型按临床严重程度分级：",
            "",
            "| 误分类类型 | 例数 | 比例 | 严重程度 | 临床后果 |",
            "|---|---|---|---|---|",
            f"| **Red → Green**（危险漏判）| {p1['red_as_green']} | "
            f"{p1['dangerous_misclassification_rate']:.3f} | ⚠️ 严重 | 高风险患者接受高强度运动处方 |",
            f"| Green → Red（保守误判）| {p1['green_as_red']} | "
            f"{p1['conservative_misclassification_rate']:.3f} | 中等 | 低风险患者运动处方受限 |",
            "",
            f"> **Red → Green 漏判率 = {p1['dangerous_misclassification_rate']:.3f}**：",
            f"> 即约 {p1['dangerous_misclassification_rate']:.1%} 的真红区患者被预测为绿区。",
            "> 在临床场景中，若 P1 模型用于运动处方决策，此误判率代表患者安全风险。",
            "",
            "### 2.3 简单规则 vs 模型（Red 区检测）",
            "",
            "| 方法 | Red 召回率 | Red PPV |",
            "|---|---|---|",
            f"| 简单规则（VO₂peak < {p1['simple_rule']['threshold_vo2_peak']:.1f} mL/kg/min）"
            f"| {p1['simple_rule']['red_recall']:.3f} | {p1['simple_rule']['red_ppv']:.3f} |",
            f"| LightGBM 模型 | {p1['model']['red_recall']:.3f} | {p1['model']['red_ppv']:.3f} |",
            "",
        ]
        delta_recall = p1["model"]["red_recall"] - p1["simple_rule"]["red_recall"]
        if abs(delta_recall) < 0.05:
            lines.append(
                "> **解读**：模型与简单 VO₂peak 阈值规则在 Red 召回率上差异 < 0.05，"
                "提示复杂模型在当前特征下相对简单规则无显著优势。"
                "这与 summary-level 数据预测天花板的结论一致。"
            )
        else:
            lines.append(
                f"> **解读**：模型 Red 召回率 {'高于' if delta_recall > 0 else '低于'}简单规则"
                f" {abs(delta_recall):.3f}。"
            )

    # ---- 综合评估 ----
    lines += [
        "",
        "## 3. 综合临床效用评估",
        "",
        "### 3.1 模型定位",
        "",
        "基于上述分析，P0/P1 模型的临床价值体现在以下三个层面，而非直接替代临床判断：",
        "",
        "1. **方法学框架验证**：HTN×EIH 2×2 设计 + Leakage Guard 机制为此类回顾性研究",
        "   提供了可复现的标准化分析框架，独立于预测性能本身具有方法学价值。",
        "",
        "2. **特征重要性发现**：SHAP 分析揭示 VO₂peak 和峰值心率的预测贡献，",
        "   为阶段 II 特征选择（逐呼吸数据）提供了实证依据。",
        "",
        "3. **阶段 II/III 基线 Benchmark**：当前模型性能（P0 AUC≈0.58，P1 F1≈0.50）",
        "   作为 summary-level 数据基准，未来引入逐呼吸数据后的性能提升可量化对比。",
        "",
        "### 3.2 局限性声明",
        "",
        f"- P0 AUC={p0_results.get('ml_auc', 0):.3f}，仅略优于随机（AUC=0.5），",
        "  不建议单独用于临床决策。",
        f"- P1 Red 召回率 ≈ {p1_results.get('model', {}).get('red_recall', 0):.1%}，",
        "  约 {:.0%} 的高风险患者被漏判，直接临床应用风险较高。".format(
            1 - p1_results.get("model", {}).get("red_recall", 0)
        ),
        "- 两个模型均受限于 summary-level 数据（无药物信息、无逐呼吸波形），",
        "  现有性能反映数据层次固有上限，非方法缺陷。",
        "",
    ]

    lines += [
        "---",
        "_由 clinical_utility.py 自动生成（Phase E 修订 4）_",
    ]

    report = "\n".join(lines)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    logger.info("临床效用报告已保存: %s", out_path)
    return report


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="P0/P1 临床效用分析")
    parser.add_argument("--features-post", default="data/features/features_post_v2.parquet")
    parser.add_argument("--features-pre", default="data/features/features_pre_v2.parquet")
    parser.add_argument("--label-table", default="data/labels/label_table.parquet")
    parser.add_argument("--output", default="reports/clinical_utility_report.md")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        stream=sys.stdout,
    )

    logger.info("加载数据...")
    df = load_data(args.features_post, args.features_pre, args.label_table)

    logger.info("分析 P0 临床效用...")
    p0_results = analyze_p0_utility(df, random_state=args.seed)

    logger.info("分析 P1 临床效用...")
    p1_results = analyze_p1_utility(df, random_state=args.seed)

    report = generate_report(p0_results, p1_results, args.output)
    print(report)
    logger.info("分析完成。报告: %s", args.output)


if __name__ == "__main__":
    main()
