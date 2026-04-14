"""
Smoke tests — minimal checks that key modules import and basic utilities work.

These tests do NOT require real data. They verify the package structure is intact
and critical classes/functions are importable and behave as documented.
"""

from __future__ import annotations

import importlib

import pytest


# --------------- Import Smoke Tests ---------------

def test_package_importable():
    """cpet_stage1 package can be imported."""
    import cpet_stage1
    assert cpet_stage1.__version__ == "0.1.0"
    assert cpet_stage1.__stage__ == 1


def test_submodule_imports():
    """All declared submodules can be imported without error."""
    submodules = [
        "cpet_stage1.cli",
        "cpet_stage1.utils.paths",
        "cpet_stage1.utils.seed",
        "cpet_stage1.utils.logging",
        "cpet_stage1.labels.leakage_guard",
    ]
    for mod in submodules:
        importlib.import_module(mod)


# --------------- Utility Tests ---------------

def test_set_global_seed_returns_int():
    from cpet_stage1.utils.seed import set_global_seed
    seed = set_global_seed(42)
    assert seed == 42


def test_set_global_seed_env_default(monkeypatch):
    monkeypatch.setenv("RANDOM_SEED", "123")
    from cpet_stage1.utils import seed as seed_mod
    import importlib
    importlib.reload(seed_mod)
    result = seed_mod.set_global_seed()
    assert result == 123


def test_paths_return_path_objects():
    from pathlib import Path
    from cpet_stage1.utils.paths import project_root, configs_dir
    assert isinstance(project_root(), Path)
    assert isinstance(configs_dir(), Path)


# --------------- LeakageGuard Tests ---------------

def test_leakage_guard_filter_p0():
    import pandas as pd
    from cpet_stage1.labels.leakage_guard import LeakageGuard

    guard = LeakageGuard()
    df = pd.DataFrame({
        "age": [70],
        "vo2_peak": [18.0],
        "arrhythmia_flag": [True],    # should be removed
        "test_terminated_early": [False],  # should be removed
        "hr_peak": [145],
    })
    clean = guard.filter(df, task="p0")
    assert "arrhythmia_flag" not in clean.columns
    assert "test_terminated_early" not in clean.columns
    assert "age" in clean.columns
    assert "vo2_peak" in clean.columns


def test_leakage_guard_assert_no_leakage_passes():
    import pandas as pd
    from cpet_stage1.labels.leakage_guard import LeakageGuard

    guard = LeakageGuard()
    df = pd.DataFrame({"age": [70], "vo2_peak": [18.0], "hr_peak": [145]})
    guard.assert_no_leakage(df, task="p0")  # should not raise


def test_leakage_guard_assert_no_leakage_fails():
    import pandas as pd
    from cpet_stage1.labels.leakage_guard import LeakageGuard

    guard = LeakageGuard()
    df = pd.DataFrame({"age": [70], "arrhythmia_flag": [True]})
    with pytest.raises(AssertionError, match="leakage"):
        guard.assert_no_leakage(df, task="p0")


def test_leakage_guard_report():
    from cpet_stage1.labels.leakage_guard import LeakageGuard

    guard = LeakageGuard()
    report = guard.report()
    assert "p0_exclusions" in report
    assert "arrhythmia_flag" in report["p0_exclusions"]


# --------------- Demo Data Tests ---------------

def test_demo_csv_readable():
    """Synthetic demo data is present and has expected columns."""
    from pathlib import Path
    import csv

    demo_path = Path(__file__).parents[1] / "data" / "demo" / "synthetic_cpet_stage1.csv"
    assert demo_path.exists(), f"Demo CSV not found: {demo_path}"

    with open(demo_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) > 0, "Demo CSV is empty"
    required_cols = {"subject_id", "age", "sex", "vo2_peak", "p1_zone"}
    assert required_cols.issubset(set(rows[0].keys())), (
        f"Missing columns. Have: {set(rows[0].keys())}"
    )
