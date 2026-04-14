"""
paths.py — Project path resolution utilities.

Reads DATA_DIR, OUTPUT_DIR, REPORTS_DIR from environment variables
or falls back to relative defaults.
"""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def project_root() -> Path:
    return _PROJECT_ROOT


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", _PROJECT_ROOT / "data"))


def output_dir() -> Path:
    return Path(os.environ.get("OUTPUT_DIR", _PROJECT_ROOT / "outputs"))


def reports_dir() -> Path:
    return Path(os.environ.get("REPORTS_DIR", _PROJECT_ROOT / "reports"))


def configs_dir() -> Path:
    return _PROJECT_ROOT / "configs"
