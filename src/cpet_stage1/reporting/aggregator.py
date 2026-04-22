"""
reporting.aggregator — 扫描已有报告并生成聚合摘要。

纯文件系统操作，不重跑模型或统计。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


# 预期报告列表（M2–M6 产出）
_EXPECTED_REPORTS = [
    "qc_report.md",
    "zone_report.md",
    "table1.md",
    "table1.csv",
    "twobytwo.md",
    "reference_equations.md",
    "sensitivity_protocol.md",
    "p0_model_report.md",
    "p1_model_report.md",
]

_EXPECTED_FIGURE_DIRS = ["figures/m4", "figures/m5"]


@dataclass
class ReportManifest:
    """扫描结果数据类。"""

    reports_dir: Path
    found_reports: List[Path] = field(default_factory=list)
    missing_reports: List[str] = field(default_factory=list)
    figure_dirs: dict = field(default_factory=dict)  # dir_name -> list of paths
    total_figures: int = 0
    scan_time: str = ""

    @property
    def is_complete(self) -> bool:
        return len(self.missing_reports) == 0


class ReportAggregator:
    """扫描 reports/ 目录，验证报告完整性，生成聚合摘要。"""

    def __init__(self, reports_dir: str | Path = "reports") -> None:
        self.reports_dir = Path(reports_dir)

    def scan(self) -> ReportManifest:
        """扫描 reports/ 目录，返回 ReportManifest。"""
        manifest = ReportManifest(
            reports_dir=self.reports_dir,
            scan_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # 检查预期报告是否存在
        for name in _EXPECTED_REPORTS:
            p = self.reports_dir / name
            if p.exists():
                manifest.found_reports.append(p)
            else:
                manifest.missing_reports.append(name)

        # 扫描图表目录
        total = 0
        for dir_name in _EXPECTED_FIGURE_DIRS:
            fig_dir = self.reports_dir / dir_name
            if fig_dir.exists():
                figs = list(fig_dir.glob("*.png")) + list(fig_dir.glob("*.svg"))
                manifest.figure_dirs[dir_name] = figs
                total += len(figs)
            else:
                manifest.figure_dirs[dir_name] = []

        manifest.total_figures = total
        return manifest

    def generate_summary(
        self,
        manifest: ReportManifest,
        output_path: str | Path = "reports/summary_report.md",
    ) -> Path:
        """生成聚合摘要 Markdown 文件。"""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        lines: List[str] = []
        lines.append("# Stage I 报告聚合摘要")
        lines.append("")
        lines.append(f"> 生成时间：{manifest.scan_time}")
        lines.append("")

        # 目录（TOC）
        lines.append("## 目录")
        lines.append("")
        lines.append("1. [报告完整性检查](#1-报告完整性检查)")
        lines.append("2. [各报告摘要](#2-各报告摘要)")
        lines.append("3. [图表清单](#3-图表清单)")
        lines.append("4. [数据产出清单](#4-数据产出清单)")
        lines.append("")

        # 1. 报告完整性
        lines.append("## 1. 报告完整性检查")
        lines.append("")
        status = "✅ 全部报告存在" if manifest.is_complete else f"⚠️ 缺失 {len(manifest.missing_reports)} 个报告"
        lines.append(f"**状态**：{status}")
        lines.append("")
        lines.append(f"| 报告文件 | 状态 |")
        lines.append(f"|---|---|")
        for name in _EXPECTED_REPORTS:
            p = manifest.reports_dir / name
            icon = "✅" if p.exists() else "❌"
            lines.append(f"| `{name}` | {icon} |")
        lines.append("")

        if manifest.missing_reports:
            lines.append(f"**缺失报告**：")
            for m in manifest.missing_reports:
                lines.append(f"- `{m}`")
            lines.append("")

        # 2. 各报告摘要
        lines.append("## 2. 各报告摘要")
        lines.append("")
        for rp in manifest.found_reports:
            lines.append(f"### {rp.name}")
            lines.append("")
            lines.append(f"**路径**：`{rp}`")
            lines.append(f"**大小**：{rp.stat().st_size:,} 字节")
            lines.append("")
            # 读取前几行作为摘要
            try:
                content = rp.read_text(encoding="utf-8", errors="replace")
                preview = _extract_preview(content, rp.suffix)
                if preview:
                    lines.append(f"**摘要**：{preview}")
                    lines.append("")
            except Exception:
                pass

        # 3. 图表清单
        lines.append("## 3. 图表清单")
        lines.append("")
        lines.append(f"**共计**：{manifest.total_figures} 张")
        lines.append("")
        for dir_name, figs in manifest.figure_dirs.items():
            lines.append(f"### {dir_name}（{len(figs)} 张）")
            lines.append("")
            if figs:
                for fig in sorted(figs):
                    lines.append(f"- `{fig.name}`")
            else:
                lines.append("_(目录不存在或无图表)_")
            lines.append("")

        # 4. 数据产出清单
        lines.append("## 4. 数据产出清单")
        lines.append("")
        data_root = manifest.reports_dir.parent / "data"
        _append_data_inventory(lines, data_root)

        out.write_text("\n".join(lines), encoding="utf-8")
        return out


def _extract_preview(content: str, suffix: str) -> Optional[str]:
    """从报告内容中提取第一行非空标题或说明作为摘要。"""
    if suffix == ".md":
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith(">"):
                return line[:120]
        # 返回第一个二级标题
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("## "):
                return f"含章节：{line[3:]}"
    elif suffix == ".csv":
        first_line = content.split("\n")[0].strip()
        cols = first_line.split(",")
        return f"{len(cols)} 列：{', '.join(cols[:5])}{'...' if len(cols) > 5 else ''}"
    return None


def _append_data_inventory(lines: List[str], data_root: Path) -> None:
    """列举 data/ 下的 parquet 和 JSON 文件。"""
    if not data_root.exists():
        lines.append("_(data/ 目录不存在)_")
        lines.append("")
        return

    lines.append(f"| 文件 | 大小 |")
    lines.append(f"|---|---|")

    for suffix in ["**/*.parquet", "**/*.json"]:
        for fp in sorted(data_root.glob(suffix)):
            # 排除 manifests 下的大型原始文件
            rel = fp.relative_to(data_root.parent)
            size_kb = fp.stat().st_size / 1024
            lines.append(f"| `{rel}` | {size_kb:.1f} KB |")
    lines.append("")
