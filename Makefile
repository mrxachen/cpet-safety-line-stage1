# =============================================================================
# cpet-safety-line-stage1 Makefile
# =============================================================================
.PHONY: help install lint test ingest qc cohort labels \
        stats stats-table1 stats-twobytwo stats-reference stats-plots stats-sensitivity \
        features anchors \
        model-p0 model-p1 model-evaluate model-interpret model-report model \
        model-outcome stats-anomaly stats-concordance phase-g \
        reports bridge-prep release clean

PYTHON  := python
CLI     := $(PYTHON) -m cpet_stage1.cli
PYTEST  := pytest

help:
	@echo "cpet-safety-line-stage1 — Available targets:"
	@echo ""
	@echo "  Setup"
	@echo "    install        Install package with dev dependencies"
	@echo "    lint           Run ruff lint + format check"
	@echo "    test           Run test suite"
	@echo ""
	@echo "  Pipeline"
	@echo "    ingest         Import raw Excel files → staging"
	@echo "    qc             Run quality control checks → reports/qc/"
	@echo "    cohort         Register cohort → data/contracts/"
	@echo "    labels         Generate P0/P1 labels → data/labels/"
	@echo "    features       Build feature matrices → data/features/"
	@echo "    anchors        Export anchor variable package → data/anchors/"
	@echo ""
	@echo "  M4 Stats"
	@echo "    stats-table1   Generate Table 1 baseline characteristics"
	@echo "    stats-twobytwo HTN x EIH two-way ANOVA effect analysis"
	@echo "    stats-reference Build reference-normal equations (%pred, z-score)"
	@echo "    stats-plots    Generate M4 figures (boxplot/violin/interaction)"
	@echo "    stats-sensitivity Protocol-stratified sensitivity analysis"
	@echo "    stats          Run all M4 stats steps"
	@echo ""
	@echo "  M5 Modeling"
	@echo "    model-p0       Train P0 baseline models (LASSO, XGBoost)"
	@echo "    model-p1       Train P1 zone prediction models (LightGBM, CatBoost)"
	@echo "    model-evaluate Evaluate trained models"
	@echo "    model-interpret Run SHAP interpretation"
	@echo "    model-report   Generate model reports"
	@echo "    model          Run full M5 pipeline (p0 + p1 + report)"
	@echo ""
	@echo "  Phase G (Method 1/2/3)"
	@echo "    model-outcome  Train outcome-anchored safety zone model (Method 1)"
	@echo "    stats-anomaly  Run Mahalanobis anomaly scoring (Method 2)"
	@echo "    stats-concordance Run multi-definition concordance analysis (Method 3)"
	@echo "    phase-g        Run all Phase G methods"
	@echo ""
	@echo "  Output"
	@echo "    reports        Generate summary figures and tables"
	@echo "    bridge-prep    Prepare Stage II bridge documents"
	@echo "    release        Package release snapshot"
	@echo ""
	@echo "  Utility"
	@echo "    clean          Remove generated outputs and caches"

# --------------- Setup ---------------
install:
	pip install -e ".[dev]"
	pre-commit install

lint:
	ruff check src tests
	ruff format --check src tests

test:
	$(PYTEST) tests/ -v --cov=cpet_stage1 --cov-report=term-missing

# --------------- Pipeline ---------------
ingest:
	$(CLI) ingest

qc:
	$(CLI) qc

cohort:
	$(CLI) cohort

labels:
	$(CLI) labels

# --------------- M4 Stats ---------------
stats-table1:
	$(CLI) stats table1

stats-twobytwo:
	$(CLI) stats twobytwo

stats-reference:
	$(CLI) stats reference

stats-plots:
	$(CLI) stats plots

stats-sensitivity:
	$(CLI) stats sensitivity

stats: stats-table1 stats-twobytwo stats-reference stats-plots stats-sensitivity

features:
	$(CLI) features

anchors:
	$(CLI) anchors

# --------------- M5 Modeling ---------------
model-p0:
	$(CLI) model p0

model-p1:
	$(CLI) model p1

model-evaluate:
	$(CLI) model evaluate

model-interpret:
	$(CLI) model interpret

model-report:
	$(CLI) model report

model: model-p0 model-p1 model-report

# --------------- Output ---------------
reports:
	$(CLI) reports

bridge-prep:
	$(CLI) bridge-prep

release:
	$(CLI) release

# --------------- Phase F (Stage 1 Iteration 2) ---------------
data-audit:
	$(CLI) stats data-audit

reference-v2:
	$(CLI) stats reference-v2

zone-v2:
	$(CLI) stats zone-v2

zone-sensitivity:
	$(CLI) stats zone-sensitivity

phase-f: data-audit reference-v2 zone-v2 zone-sensitivity

# --------------- Phase A (Post-M7) ---------------
shap:
	$(CLI) model interpret

posthoc:
	$(CLI) stats posthoc

eih-logistic:
	$(CLI) stats eih-logistic

supplement-plots:
	$(CLI) stats supplement-plots

subgroup:
	$(CLI) stats subgroup

phase-a: shap posthoc eih-logistic supplement-plots subgroup

# --------------- Phase C (Model Improvement) ---------------
labels-v3:
	$(CLI) labels --label-rules configs/data/label_rules_v3.yaml \
		--output-label data/labels/label_table_v3.parquet \
		--output-zone data/labels/zone_table_v3.parquet \
		--output-ref data/labels/reference_scores_v3.parquet

features-v2:
	$(CLI) features \
		--feature-config configs/features/feature_config_v2.yaml \
		--label-rules configs/data/label_rules_v2.yaml \
		--output-p0 data/features/features_pre_v2.parquet \
		--output-p1 data/features/features_post_v2.parquet

model-p0-v2:
	$(CLI) model p0 \
		--feature-config configs/features/feature_config_v2.yaml \
		--label-rules configs/data/label_rules_v2.yaml \
		--report-path reports/p0_model_report_v2.md

model-p1-v2:
	$(CLI) model p1 \
		--feature-config configs/features/feature_config_v2.yaml \
		--label-rules configs/data/label_rules_v3.yaml \
		--report-path reports/p1_model_report_v2.md

model-p1-v3-labels:
	$(CLI) model p1 \
		--feature-config configs/features/feature_config_v2.yaml \
		--label-rules configs/data/label_rules_v3.yaml \
		--label-col p1_zone_v3 \
		--report-path reports/p1_model_report_v3labels.md

# Phase C4: 代价敏感训练（Red 权重 4x）
model-p1-cost-sensitive:
	$(CLI) model p1 \
		--feature-config configs/features/feature_config_v2.yaml \
		--label-rules configs/data/label_rules_v3.yaml \
		--lgbm-config configs/model/p1_lgbm_cost_sensitive.yaml \
		--catboost-config configs/model/p1_catboost_cost_sensitive.yaml \
		--report-path reports/p1_model_report_cost_sensitive.md

phase-c: features-v2 model-p0-v2 model-p1-v2 model-p1-cost-sensitive

# --------------- Phase G (Method 1/2/3) ---------------
model-outcome:
	$(CLI) model outcome

stats-anomaly:
	$(CLI) stats anomaly

stats-concordance:
	$(CLI) stats concordance

phase-g: model-outcome stats-anomaly stats-concordance

# --------------- Utility ---------------
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."
