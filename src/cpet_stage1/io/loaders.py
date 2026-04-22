"""
loaders.py — 通用数据加载工具。

供下游模块（qc / cohort / features）使用，统一入口加载 staging/curated 数据。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# 默认文件路径（可通过环境变量或参数覆盖）
_DEFAULT_STAGING = "data/staging/cpet_staging_v1.parquet"
_DEFAULT_CURATED = "data/curated/cpet_curated_v1.parquet"
_DEFAULT_CONFIGS_DIR = "configs"


def load_staging(path: str | Path | None = None) -> pd.DataFrame:
    """
    加载 staging parquet，供下游 qc/cohort/features 使用。

    参数：
        path: parquet 文件路径。None 时按以下优先级查找：
              1. 环境变量 STAGING_PARQUET
              2. 默认路径 data/staging/cpet_staging_v1.parquet

    返回：
        pd.DataFrame

    抛出：
        FileNotFoundError: 文件不存在时
    """
    if path is None:
        path = os.environ.get("STAGING_PARQUET", _DEFAULT_STAGING)
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"staging parquet 不存在: {path}\n"
            "请先运行 'make ingest' 生成 staging 数据。"
        )

    df = pd.read_parquet(path)
    logger.info("加载 staging parquet: %s (%d 行 × %d 列)", path, len(df), len(df.columns))
    return df


def load_curated(path: str | Path | None = None) -> pd.DataFrame:
    """
    加载 curated parquet（QC 通过后的数据）。

    参数：
        path: parquet 文件路径。None 时按以下优先级查找：
              1. 环境变量 CURATED_PARQUET
              2. 默认路径 data/curated/cpet_curated_v1.parquet
    """
    if path is None:
        path = os.environ.get("CURATED_PARQUET", _DEFAULT_CURATED)
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"curated parquet 不存在: {path}\n"
            "请先运行 'make qc' 生成 curated 数据。"
        )

    df = pd.read_parquet(path)
    logger.info("加载 curated parquet: %s (%d 行 × %d 列)", path, len(df), len(df.columns))
    return df


def load_config(config_name: str, configs_dir: str | Path | None = None) -> dict[str, Any]:
    """
    从 configs/ 加载 YAML 配置文件。

    参数：
        config_name: 相对于 configs_dir 的文件名，可含子路径，例如：
                     "data/field_map_v2.yaml"、"paths.yaml"
        configs_dir: configs 根目录。None 时使用 CONFIGS_DIR 环境变量或 "configs/"

    返回：
        解析后的 dict
    """
    if configs_dir is None:
        configs_dir = os.environ.get("CONFIGS_DIR", _DEFAULT_CONFIGS_DIR)
    cfg_path = Path(configs_dir) / config_name

    if not cfg_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {cfg_path}")

    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    logger.debug("已加载配置: %s", cfg_path)
    return cfg or {}


def load_demo_csv(path: str | Path | None = None) -> pd.DataFrame:
    """
    加载演示/测试用 CSV 数据。

    参数：
        path: CSV 文件路径。None 时使用 data/demo/synthetic_cpet_stage1.csv
    """
    if path is None:
        path = "data/demo/synthetic_cpet_stage1.csv"
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"演示 CSV 不存在: {path}")

    df = pd.read_csv(path)
    logger.info("加载演示 CSV: %s (%d 行)", path, len(df))
    return df
