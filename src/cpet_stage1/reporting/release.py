"""
reporting.release — 打包冻结发布包到 reports/release/。

纯文件系统操作（复制 + JSON 序列化），不重跑模型。
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .aggregator import ReportManifest


@dataclass
class ReleaseResult:
    """发布打包结果数据类。"""

    release_dir: Path
    version: str
    files_copied: List[str] = field(default_factory=list)
    manifest_path: Optional[Path] = None
    metrics: dict = field(default_factory=dict)
    package_time: str = ""

    @property
    def file_count(self) -> int:
        return len(self.files_copied)


class ReleasePackager:
    """将 reports/ 内容打包为冻结发布包。"""

    def __init__(self, version: str = "v1.0.0-stage1") -> None:
        self.version = version

    def package(
        self,
        manifest: ReportManifest,
        release_dir: str | Path = "reports/release",
        include_bridge_prep: bool = True,
        bridge_prep_dir: str | Path = "outputs/bridge_prep",
    ) -> ReleaseResult:
        """执行打包流程，返回 ReleaseResult。"""
        rdir = Path(release_dir)
        rdir.mkdir(parents=True, exist_ok=True)

        result = ReleaseResult(
            release_dir=rdir,
            version=self.version,
            package_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        # 1. 复制 Markdown/CSV 报告
        self._copy_reports(manifest, rdir, result)

        # 2. 复制图表
        self._copy_figures(manifest, rdir, result)

        # 3. 快照 YAML 配置
        configs_root = manifest.reports_dir.parent / "configs"
        self._snapshot_configs(configs_root, rdir, result)

        # 4. 解析指标 → metrics_summary.json
        self._write_metrics(manifest, rdir, result)

        # 5. 可选：复制 bridge_prep
        if include_bridge_prep:
            bp_src = Path(bridge_prep_dir)
            if bp_src.exists():
                bp_dst = rdir / "bridge_prep"
                if bp_dst.exists():
                    shutil.rmtree(bp_dst)
                shutil.copytree(str(bp_src), str(bp_dst))
                for fp in bp_dst.rglob("*"):
                    if fp.is_file():
                        result.files_copied.append(str(fp.relative_to(rdir)))

        # 6. 生成 release_manifest.json
        manifest_path = rdir / "release_manifest.json"
        self._write_manifest(result, manifest_path)
        result.manifest_path = manifest_path

        return result

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _copy_reports(
        self, manifest: ReportManifest, rdir: Path, result: ReleaseResult
    ) -> None:
        """复制所有找到的 Markdown/CSV 报告。"""
        for rp in manifest.found_reports:
            dst = rdir / rp.name
            shutil.copy2(str(rp), str(dst))
            result.files_copied.append(rp.name)

        # 也复制 summary_report.md（如已生成）
        summary = manifest.reports_dir / "summary_report.md"
        if summary.exists():
            dst = rdir / "summary_report.md"
            shutil.copy2(str(summary), str(dst))
            if "summary_report.md" not in result.files_copied:
                result.files_copied.append("summary_report.md")

    def _copy_figures(
        self, manifest: ReportManifest, rdir: Path, result: ReleaseResult
    ) -> None:
        """复制所有图表到 figures/ 子目录，保留 m4/m5 结构。"""
        for dir_name, figs in manifest.figure_dirs.items():
            if not figs:
                continue
            dst_dir = rdir / "figures" / Path(dir_name).name
            dst_dir.mkdir(parents=True, exist_ok=True)
            for fig in figs:
                dst = dst_dir / fig.name
                shutil.copy2(str(fig), str(dst))
                result.files_copied.append(f"figures/{Path(dir_name).name}/{fig.name}")

    def _snapshot_configs(
        self, configs_root: Path, rdir: Path, result: ReleaseResult
    ) -> None:
        """快照全部 YAML 配置文件，保留目录结构。"""
        if not configs_root.exists():
            return
        snapshot_dir = rdir / "config_snapshot"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        for yaml_file in sorted(configs_root.rglob("*.yaml")):
            rel = yaml_file.relative_to(configs_root)
            dst = snapshot_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(yaml_file), str(dst))
            result.files_copied.append(f"config_snapshot/{rel}")

    def _write_metrics(
        self, manifest: ReportManifest, rdir: Path, result: ReleaseResult
    ) -> None:
        """从 p0/p1 报告解析关键指标，写入 metrics_summary.json。"""
        metrics: Dict[str, dict] = {}

        for rp in manifest.found_reports:
            if rp.name == "p0_model_report.md":
                metrics["p0"] = _parse_model_metrics(rp, task="p0")
            elif rp.name == "p1_model_report.md":
                metrics["p1"] = _parse_model_metrics(rp, task="p1")

        result.metrics = metrics
        out_path = rdir / "metrics_summary.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
        result.files_copied.append("metrics_summary.json")

    def _write_manifest(self, result: ReleaseResult, out_path: Path) -> None:
        """生成 release_manifest.json。"""
        manifest_data = {
            "version": result.version,
            "package_time": result.package_time,
            "file_count": result.file_count,
            "files": sorted(result.files_copied),
            "metrics": result.metrics,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, ensure_ascii=False, indent=2)
        result.files_copied.append("release_manifest.json")


# ------------------------------------------------------------------
# 指标解析工具函数
# ------------------------------------------------------------------

def _parse_model_metrics(report_path: Path, task: str) -> dict:
    """从 Markdown 报告表格中用正则提取 AUC/F1 等关键指标。"""
    try:
        content = report_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}

    metrics: dict = {}

    if task == "p0":
        # 匹配 AUC-ROC 数值（如 0.5821）
        auc_matches = re.findall(r"AUC[_\-]?ROC\s*[|:]\s*([\d.]+)", content, re.IGNORECASE)
        if not auc_matches:
            auc_matches = re.findall(r"\|\s*([\d.]{4,6})\s*\|.*auc", content, re.IGNORECASE)
        if auc_matches:
            metrics["best_auc_roc"] = float(auc_matches[0])

        # AUPRC
        auprc_matches = re.findall(r"AUPRC\s*[|:]\s*([\d.]+)", content, re.IGNORECASE)
        if auprc_matches:
            metrics["best_auprc"] = float(auprc_matches[0])

        # 从表格行提取：寻找数字行
        table_rows = re.findall(r"\|\s*(\w[\w_\s]*)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|", content)
        for row in table_rows:
            name, v1, v2 = row
            name = name.strip().lower().replace(" ", "_")
            if "lasso" in name or "xgb" in name or "lgbm" in name or "catboost" in name:
                try:
                    metrics[f"{name}_auc"] = float(v1)
                except ValueError:
                    pass

    elif task == "p1":
        # 匹配 F1 macro
        f1_matches = re.findall(r"F1[_\-]?macro\s*[|:]\s*([\d.]+)", content, re.IGNORECASE)
        if not f1_matches:
            f1_matches = re.findall(r"f1_macro\s*\|\s*([\d.]+)", content, re.IGNORECASE)
        if f1_matches:
            metrics["best_f1_macro"] = float(f1_matches[0])

        # kappa
        kappa_matches = re.findall(r"kappa[_\w]*\s*[|:]\s*([\d.]+)", content, re.IGNORECASE)
        if kappa_matches:
            metrics["best_kappa_weighted"] = float(kappa_matches[0])

        # 从表格行提取
        table_rows = re.findall(r"\|\s*(\w[\w_\s]*)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|", content)
        for row in table_rows:
            name, v1, v2 = row
            name = name.strip().lower().replace(" ", "_")
            if "lgbm" in name or "catboost" in name or "ordinal" in name:
                try:
                    metrics[f"{name}_f1"] = float(v1)
                except ValueError:
                    pass

    return metrics
