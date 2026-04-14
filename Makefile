# =============================================================================
# cpet-safety-line-stage1 Makefile
# =============================================================================
.PHONY: help install lint test ingest qc cohort labels features anchors \
        model-p0 model-p1 reports bridge-prep release clean

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
	@echo "  Modeling"
	@echo "    model-p0       Train P0 baseline models (LASSO, XGBoost)"
	@echo "    model-p1       Train P1 zone prediction models (LightGBM, CatBoost)"
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

features:
	$(CLI) features

anchors:
	$(CLI) anchors

# --------------- Modeling ---------------
model-p0:
	$(CLI) model p0

model-p1:
	$(CLI) model p1

# --------------- Output ---------------
reports:
	$(CLI) reports

bridge-prep:
	$(CLI) bridge-prep

release:
	$(CLI) release

# --------------- Utility ---------------
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."
