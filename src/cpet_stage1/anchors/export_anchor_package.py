"""
export_anchor_package.py — 锚点资产包导出器。

从 AnchorTableResult 导出：
- data/anchors/anchor_table.parquet
- data/anchors/anchor_coverage_report.md
- outputs/bridge_prep/anchor_package_v1/（JSON + CSV 格式，可选）
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from cpet_stage1.anchors.anchor_builder import AnchorTableResult

logger = logging.getLogger(__name__)

# 合约要求的最小锚点列集合
_ANCHOR_REQUIRED_COLS = [
    "reserve_axis",
    "threshold_axis",
    "instability_axis",
    "a_lab_vector",
    "s_lab_score",
    "z_lab_zone",
]


def export_anchor_package(
    result: AnchorTableResult,
    anchor_parquet_path: str | Path = "data/anchors/anchor_table.parquet",
    coverage_report_path: str | Path = "data/anchors/anchor_coverage_report.md",
    package_dir: str | Path | None = None,
) -> dict[str, Path]:
    """
    导出锚点资产包。

    参数：
        result:               AnchorTableResult
        anchor_parquet_path:  anchor_table.parquet 输出路径
        coverage_report_path: 覆盖率报告 Markdown 路径
        package_dir:          可选的 JSON/CSV 格式包目录

    返回：
        {文件类型: 路径} 字典
    """
    exported: dict[str, Path] = {}

    # 1. anchor_table.parquet
    result.to_parquet(anchor_parquet_path)
    exported["anchor_table"] = Path(anchor_parquet_path)

    # 2. 覆盖率报告
    cov_path = Path(coverage_report_path)
    cov_path.parent.mkdir(parents=True, exist_ok=True)
    cov_path.write_text(result.coverage_report(), encoding="utf-8")
    exported["coverage_report"] = cov_path
    logger.info("覆盖率报告已保存: %s", cov_path)

    # 3. 可选：package_dir 格式导出
    if package_dir is not None:
        pkg_path = Path(package_dir)
        pkg_path.mkdir(parents=True, exist_ok=True)

        # 3a. 摘要 JSON
        summary_data: dict = {
            "n_total": result.n_total,
            "n_per_zone": result.n_per_zone,
            "anchor_coverage": {k: bool(v) for k, v in result.anchor_coverage.items()},
            "available_anchor_cols": [k for k, v in result.anchor_coverage.items() if v],
            "missing_anchor_cols": [k for k, v in result.anchor_coverage.items() if not v],
        }
        summary_path = pkg_path / "anchor_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        exported["anchor_summary"] = summary_path

        # 3b. 关键列 CSV（便于人工查阅）
        preview_cols = [
            c for c in
            ["cpet_session_id", "subject_id", "cohort_2x2"]
            + _ANCHOR_REQUIRED_COLS
            if c in result.df.columns
        ]
        csv_path = pkg_path / "anchor_table_preview.csv"
        result.df[preview_cols].to_csv(csv_path, index=False)
        exported["anchor_csv"] = csv_path

        logger.info("锚点包已导出: %s (%d 个文件)", pkg_path, len(exported))

    return exported
