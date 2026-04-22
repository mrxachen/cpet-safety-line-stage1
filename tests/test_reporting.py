"""
tests/test_reporting.py — M7 reporting 模块单元测试和集成测试。

使用临时文件系统，不依赖真实数据或已运行的管线。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 辅助：在临时目录中构造 mock reports/ 结构
# ---------------------------------------------------------------------------

def _make_reports_dir(tmp_path: Path, reports: list[str] | None = None) -> Path:
    """在 tmp_path/reports 中创建 mock 报告文件。"""
    rdir = tmp_path / "reports"
    rdir.mkdir()

    default_reports = [
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
    for name in (reports if reports is not None else default_reports):
        p = rdir / name
        if name.endswith(".md"):
            p.write_text(f"# {name}\n\n这是 {name} 的占位内容。\n", encoding="utf-8")
        else:
            p.write_text("col_a,col_b,col_c\n1,2,3\n", encoding="utf-8")

    return rdir


def _make_figure_dirs(rdir: Path, m4_count: int = 3, m5_count: int = 5) -> None:
    """在 reports/ 下创建 mock 图表文件。"""
    m4_dir = rdir / "figures" / "m4"
    m4_dir.mkdir(parents=True)
    for i in range(m4_count):
        (m4_dir / f"boxplot_{i}.png").write_bytes(b"PNG")

    m5_dir = rdir / "figures" / "m5"
    m5_dir.mkdir(parents=True)
    for i in range(m5_count):
        (m5_dir / f"p0_roc_{i}.png").write_bytes(b"PNG")


def _make_mock_p0_report(rdir: Path) -> None:
    """写入含 AUC 信息的 mock P0 报告。"""
    content = """# P0 模型报告

## 模型性能汇总

| 模型 | AUC-ROC | AUPRC |
|---|---|---|
| LASSO | 0.5821 | 0.3412 |
| XGBoost | 0.5614 | 0.3201 |
"""
    (rdir / "p0_model_report.md").write_text(content, encoding="utf-8")


def _make_mock_p1_report(rdir: Path) -> None:
    """写入含 F1 信息的 mock P1 报告。"""
    content = """# P1 模型报告

## 模型性能汇总

| 模型 | F1_macro | kappa_weighted |
|---|---|---|
| LightGBM | 0.4731 | 0.3812 |
| CatBoost | 0.4651 | 0.3720 |
"""
    (rdir / "p1_model_report.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# TestReportAggregator
# ---------------------------------------------------------------------------

class TestReportAggregator:
    def test_scan_finds_all_reports(self, tmp_path):
        """scan() 正确找到所有预期报告。"""
        from cpet_stage1.reporting import ReportAggregator

        rdir = _make_reports_dir(tmp_path)
        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        assert len(manifest.found_reports) == 9
        assert len(manifest.missing_reports) == 0
        assert manifest.is_complete

    def test_scan_detects_missing_reports(self, tmp_path):
        """scan() 正确检测缺失报告。"""
        from cpet_stage1.reporting import ReportAggregator

        # 只创建部分报告
        rdir = _make_reports_dir(tmp_path, reports=["qc_report.md", "table1.md"])
        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        assert len(manifest.found_reports) == 2
        assert len(manifest.missing_reports) == 7
        assert not manifest.is_complete

    def test_scan_counts_figures(self, tmp_path):
        """scan() 正确统计图表数量。"""
        from cpet_stage1.reporting import ReportAggregator

        rdir = _make_reports_dir(tmp_path)
        _make_figure_dirs(rdir, m4_count=4, m5_count=6)

        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        assert manifest.total_figures == 10
        assert len(manifest.figure_dirs.get("figures/m4", [])) == 4
        assert len(manifest.figure_dirs.get("figures/m5", [])) == 6

    def test_scan_empty_figure_dirs(self, tmp_path):
        """无图表目录时 total_figures 为 0。"""
        from cpet_stage1.reporting import ReportAggregator

        rdir = _make_reports_dir(tmp_path)
        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        assert manifest.total_figures == 0

    def test_generate_summary_creates_file(self, tmp_path):
        """generate_summary() 创建输出文件。"""
        from cpet_stage1.reporting import ReportAggregator

        rdir = _make_reports_dir(tmp_path)
        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        out = tmp_path / "summary.md"
        result_path = aggregator.generate_summary(manifest, output_path=out)

        assert result_path == out
        assert out.exists()
        assert out.stat().st_size > 0

    def test_generate_summary_has_toc(self, tmp_path):
        """summary 文件包含目录（TOC）。"""
        from cpet_stage1.reporting import ReportAggregator

        rdir = _make_reports_dir(tmp_path)
        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()
        out = tmp_path / "summary.md"
        aggregator.generate_summary(manifest, output_path=out)

        content = out.read_text(encoding="utf-8")
        assert "## 目录" in content
        assert "报告完整性" in content
        assert "图表清单" in content

    def test_generate_summary_lists_missing(self, tmp_path):
        """summary 包含缺失报告的提示。"""
        from cpet_stage1.reporting import ReportAggregator

        rdir = _make_reports_dir(tmp_path, reports=["qc_report.md"])
        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()
        out = tmp_path / "summary.md"
        aggregator.generate_summary(manifest, output_path=out)

        content = out.read_text(encoding="utf-8")
        assert "缺失" in content or "❌" in content

    def test_manifest_has_scan_time(self, tmp_path):
        """manifest 包含扫描时间戳。"""
        from cpet_stage1.reporting import ReportAggregator

        rdir = _make_reports_dir(tmp_path)
        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        assert manifest.scan_time != ""
        assert "2026" in manifest.scan_time or "2025" in manifest.scan_time


# ---------------------------------------------------------------------------
# TestReleasePackager
# ---------------------------------------------------------------------------

class TestReleasePackager:
    def test_package_creates_release_dir(self, tmp_path):
        """package() 创建 release 目录。"""
        from cpet_stage1.reporting import ReportAggregator, ReleasePackager

        rdir = _make_reports_dir(tmp_path)
        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        rel_dir = tmp_path / "release"
        packager = ReleasePackager(version="v1.0.0-stage1")
        result = packager.package(manifest, release_dir=rel_dir, include_bridge_prep=False)

        assert rel_dir.exists()
        assert result.release_dir == rel_dir

    def test_package_copies_reports(self, tmp_path):
        """package() 将报告文件复制到 release 目录。"""
        from cpet_stage1.reporting import ReportAggregator, ReleasePackager

        rdir = _make_reports_dir(tmp_path)
        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        rel_dir = tmp_path / "release"
        packager = ReleasePackager(version="v1.0.0-stage1")
        result = packager.package(manifest, release_dir=rel_dir, include_bridge_prep=False)

        # 应至少有一个 .md 文件
        md_files = list(rel_dir.glob("*.md"))
        assert len(md_files) > 0
        assert "qc_report.md" in [f.name for f in md_files]

    def test_package_copies_figures(self, tmp_path):
        """package() 将图表复制到 release/figures/ 下。"""
        from cpet_stage1.reporting import ReportAggregator, ReleasePackager

        rdir = _make_reports_dir(tmp_path)
        _make_figure_dirs(rdir, m4_count=2, m5_count=3)

        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        rel_dir = tmp_path / "release"
        packager = ReleasePackager(version="v1.0.0-stage1")
        packager.package(manifest, release_dir=rel_dir, include_bridge_prep=False)

        fig_files = list((rel_dir / "figures").rglob("*.png"))
        assert len(fig_files) == 5  # 2 + 3

    def test_package_snapshots_configs(self, tmp_path):
        """package() 在 config_snapshot/ 中创建 YAML 快照。"""
        from cpet_stage1.reporting import ReportAggregator, ReleasePackager

        rdir = _make_reports_dir(tmp_path)
        # 创建 mock configs
        cfg_root = tmp_path / "configs"
        cfg_root.mkdir()
        (cfg_root / "base.yaml").write_text("key: value\n")
        (cfg_root / "data").mkdir()
        (cfg_root / "data" / "schema_v2.yaml").write_text("fields: []\n")

        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        rel_dir = tmp_path / "release"
        packager = ReleasePackager(version="v1.0.0-stage1")
        packager.package(manifest, release_dir=rel_dir, include_bridge_prep=False)

        snapshot_dir = rel_dir / "config_snapshot"
        assert snapshot_dir.exists()
        yaml_files = list(snapshot_dir.rglob("*.yaml"))
        assert len(yaml_files) == 2

    def test_package_writes_metrics_json(self, tmp_path):
        """package() 生成 metrics_summary.json。"""
        from cpet_stage1.reporting import ReportAggregator, ReleasePackager

        rdir = _make_reports_dir(tmp_path)
        _make_mock_p0_report(rdir)
        _make_mock_p1_report(rdir)

        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        rel_dir = tmp_path / "release"
        packager = ReleasePackager(version="v1.0.0-stage1")
        packager.package(manifest, release_dir=rel_dir, include_bridge_prep=False)

        metrics_path = rel_dir / "metrics_summary.json"
        assert metrics_path.exists()
        data = json.loads(metrics_path.read_text())
        assert "p0" in data or "p1" in data

    def test_package_writes_manifest_json(self, tmp_path):
        """package() 生成包含版本号的 release_manifest.json。"""
        from cpet_stage1.reporting import ReportAggregator, ReleasePackager

        rdir = _make_reports_dir(tmp_path)
        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        rel_dir = tmp_path / "release"
        packager = ReleasePackager(version="v1.0.0-stage1")
        result = packager.package(manifest, release_dir=rel_dir, include_bridge_prep=False)

        assert result.manifest_path is not None
        assert result.manifest_path.exists()
        data = json.loads(result.manifest_path.read_text())
        assert data["version"] == "v1.0.0-stage1"
        assert "files" in data
        assert "package_time" in data

    def test_package_bridge_prep_copied(self, tmp_path):
        """include_bridge_prep=True 时复制 bridge_prep 目录。"""
        from cpet_stage1.reporting import ReportAggregator, ReleasePackager

        rdir = _make_reports_dir(tmp_path)
        # 创建 mock bridge_prep
        bp_src = tmp_path / "outputs" / "bridge_prep"
        bp_src.mkdir(parents=True)
        (bp_src / "anchor_dict.json").write_text('{"key": "val"}')
        (bp_src / "manifest.json").write_text('{}')

        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        rel_dir = tmp_path / "release"
        packager = ReleasePackager(version="v1.0.0-stage1")
        packager.package(
            manifest,
            release_dir=rel_dir,
            include_bridge_prep=True,
            bridge_prep_dir=bp_src,
        )

        assert (rel_dir / "bridge_prep").exists()
        assert (rel_dir / "bridge_prep" / "anchor_dict.json").exists()

    def test_package_no_bridge_prep(self, tmp_path):
        """include_bridge_prep=False 时不复制 bridge_prep。"""
        from cpet_stage1.reporting import ReportAggregator, ReleasePackager

        rdir = _make_reports_dir(tmp_path)
        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()

        rel_dir = tmp_path / "release"
        packager = ReleasePackager(version="v1.0.0-stage1")
        packager.package(manifest, release_dir=rel_dir, include_bridge_prep=False)

        assert not (rel_dir / "bridge_prep").exists()


# ---------------------------------------------------------------------------
# 集成测试
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_aggregator_to_release_end_to_end(self, tmp_path):
        """aggregator → release 端到端集成流程。"""
        from cpet_stage1.reporting import ReportAggregator, ReleasePackager

        rdir = _make_reports_dir(tmp_path)
        _make_figure_dirs(rdir, m4_count=2, m5_count=3)
        _make_mock_p0_report(rdir)
        _make_mock_p1_report(rdir)

        # Step 1: aggregate
        aggregator = ReportAggregator(reports_dir=rdir)
        manifest = aggregator.scan()
        summary_path = rdir / "summary_report.md"
        aggregator.generate_summary(manifest, output_path=summary_path)

        assert summary_path.exists()

        # Step 2: release
        rel_dir = tmp_path / "release"
        packager = ReleasePackager(version="v1.0.0-stage1")
        result = packager.package(manifest, release_dir=rel_dir, include_bridge_prep=False)

        assert result.file_count > 0
        assert result.manifest_path.exists()

        # 验证 manifest JSON 结构
        data = json.loads(result.manifest_path.read_text())
        assert data["version"] == "v1.0.0-stage1"
        assert len(data["files"]) > 0

    def test_reporting_imports(self):
        """所有 reporting 导出均可正常导入。"""
        from cpet_stage1.reporting import (
            ReportAggregator,
            ReportManifest,
            ReleasePackager,
            ReleaseResult,
        )
        assert ReportAggregator is not None
        assert ReportManifest is not None
        assert ReleasePackager is not None
        assert ReleaseResult is not None
