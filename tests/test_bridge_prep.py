"""
tests/test_bridge_prep.py — Bridge Prep 文档包生成测试。

覆盖范围：
- ProxyHypothesisBuilder.build() 基本功能
- build_proxy_hypothesis_table() 列完整性
- ProxyHypothesisBuilder.save() CSV 输出
- export_bridge_prep_package() 全部 5 个文件生成
- anchor_variable_dictionary_v1.md 内容验证
- bridge_sampling_priority_list_v1.md 内容验证
- bridge_question_list_v1.md 内容验证
- bridge_prep_package_manifest.json 结构验证
- 缺失 YAML 文件时不崩溃（降级）
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from cpet_stage1.bridge_prep.proxy_hypothesis import (
    ProxyHypothesisBuilder,
    build_proxy_hypothesis_table,
)
from cpet_stage1.bridge_prep.export_bridge_prep import export_bridge_prep_package

# ============================================================
# 配置路径
# ============================================================
ANCHOR_RULES = Path("configs/bridge/anchor_rules_v1.yaml")
HOME_PROXY_MAP = Path("configs/bridge/home_proxy_map_v0.yaml")
BRIDGE_SAMPLING = Path("configs/bridge/bridge_sampling_priority_v0.yaml")
QUESTION_LIST_SRC = Path("docs/bridge/bridge_question_list_v1.md")

_EXPECTED_COLUMNS = [
    "axis",
    "var_id",
    "canonical_field",
    "description",
    "unit",
    "priority",
    "clinical_meaning",
    "home_proxy_hypothesis",
]


# ============================================================
# ProxyHypothesisBuilder 测试
# ============================================================

class TestProxyHypothesisBuilder:
    def test_build_returns_dataframe(self):
        builder = ProxyHypothesisBuilder(ANCHOR_RULES, HOME_PROXY_MAP)
        df = builder.build()
        assert isinstance(df, pd.DataFrame)

    def test_build_nonempty(self):
        builder = ProxyHypothesisBuilder(ANCHOR_RULES, HOME_PROXY_MAP)
        df = builder.build()
        assert len(df) > 0

    def test_required_columns_present(self):
        df = build_proxy_hypothesis_table(ANCHOR_RULES, HOME_PROXY_MAP)
        for col in _EXPECTED_COLUMNS:
            assert col in df.columns, f"缺少列: {col}"

    def test_all_axes_covered(self):
        df = build_proxy_hypothesis_table(ANCHOR_RULES, HOME_PROXY_MAP)
        axes = set(df["axis"].unique())
        assert "R" in axes
        assert "T" in axes
        assert "I" in axes

    def test_priority_critical_present(self):
        df = build_proxy_hypothesis_table(ANCHOR_RULES, HOME_PROXY_MAP)
        priorities = set(df["priority"].unique())
        assert "critical" in priorities

    def test_save_creates_csv(self, tmp_path):
        builder = ProxyHypothesisBuilder(ANCHOR_RULES, HOME_PROXY_MAP)
        df = builder.build()
        out_path = tmp_path / "proxy_hypothesis.csv"
        saved_path = builder.save(df, out_path)
        assert saved_path == out_path
        assert out_path.exists()

    def test_saved_csv_readable(self, tmp_path):
        builder = ProxyHypothesisBuilder(ANCHOR_RULES, HOME_PROXY_MAP)
        df = builder.build()
        out_path = tmp_path / "proxy_hypothesis.csv"
        builder.save(df, out_path)
        df2 = pd.read_csv(out_path, encoding="utf-8-sig")
        assert len(df2) == len(df)

    def test_missing_anchor_rules_empty_df(self, tmp_path):
        fake_path = tmp_path / "nonexistent.yaml"
        df = build_proxy_hypothesis_table(fake_path, HOME_PROXY_MAP)
        assert isinstance(df, pd.DataFrame)
        # 无锚点规则 → 空表
        assert len(df) == 0

    def test_missing_proxy_map_still_builds(self, tmp_path):
        fake_path = tmp_path / "nonexistent.yaml"
        df = build_proxy_hypothesis_table(ANCHOR_RULES, fake_path)
        # proxy 字段为空但锚点变量仍存在
        assert len(df) > 0
        assert "var_id" in df.columns

    def test_canonical_fields_nonempty(self):
        df = build_proxy_hypothesis_table(ANCHOR_RULES, HOME_PROXY_MAP)
        n_empty = df["canonical_field"].isna().sum() + (df["canonical_field"] == "").sum()
        assert n_empty == 0, f"{n_empty} 行 canonical_field 为空"


# ============================================================
# export_bridge_prep_package 测试
# ============================================================

class TestExportBridgePrepPackage:
    def test_all_files_created(self, tmp_path):
        exported = export_bridge_prep_package(
            output_dir=tmp_path,
            anchor_rules_path=ANCHOR_RULES,
            bridge_sampling_path=BRIDGE_SAMPLING,
            home_proxy_map_path=HOME_PROXY_MAP,
            question_list_source=QUESTION_LIST_SRC,
        )
        assert "anchor_variable_dictionary" in exported
        assert "home_proxy_hypothesis_table" in exported
        assert "bridge_sampling_priority_list" in exported
        assert "bridge_question_list" in exported
        assert "bridge_prep_manifest" in exported

    def test_all_files_exist(self, tmp_path):
        exported = export_bridge_prep_package(
            output_dir=tmp_path,
            anchor_rules_path=ANCHOR_RULES,
            bridge_sampling_path=BRIDGE_SAMPLING,
            home_proxy_map_path=HOME_PROXY_MAP,
            question_list_source=QUESTION_LIST_SRC,
        )
        for name, path in exported.items():
            assert Path(path).exists(), f"{name} 文件不存在: {path}"

    def test_anchor_dictionary_contains_axes(self, tmp_path):
        exported = export_bridge_prep_package(
            output_dir=tmp_path,
            anchor_rules_path=ANCHOR_RULES,
            bridge_sampling_path=BRIDGE_SAMPLING,
            home_proxy_map_path=HOME_PROXY_MAP,
            question_list_source=QUESTION_LIST_SRC,
        )
        content = Path(exported["anchor_variable_dictionary"]).read_text(encoding="utf-8")
        assert "轴 R" in content or "axis_R" in content or "Reserve" in content
        assert "轴 T" in content or "Threshold" in content
        assert "轴 I" in content or "Instability" in content

    def test_proxy_table_is_valid_csv(self, tmp_path):
        exported = export_bridge_prep_package(
            output_dir=tmp_path,
            anchor_rules_path=ANCHOR_RULES,
            bridge_sampling_path=BRIDGE_SAMPLING,
            home_proxy_map_path=HOME_PROXY_MAP,
            question_list_source=QUESTION_LIST_SRC,
        )
        csv_path = exported["home_proxy_hypothesis_table"]
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        assert len(df) > 0
        assert "var_id" in df.columns

    def test_sampling_list_contains_tiers(self, tmp_path):
        exported = export_bridge_prep_package(
            output_dir=tmp_path,
            anchor_rules_path=ANCHOR_RULES,
            bridge_sampling_path=BRIDGE_SAMPLING,
            home_proxy_map_path=HOME_PROXY_MAP,
            question_list_source=QUESTION_LIST_SRC,
        )
        content = Path(exported["bridge_sampling_priority_list"]).read_text(encoding="utf-8")
        assert "Tier" in content or "tier" in content or "Critical" in content or "目标" in content

    def test_manifest_valid_json(self, tmp_path):
        exported = export_bridge_prep_package(
            output_dir=tmp_path,
            anchor_rules_path=ANCHOR_RULES,
            bridge_sampling_path=BRIDGE_SAMPLING,
            home_proxy_map_path=HOME_PROXY_MAP,
            question_list_source=QUESTION_LIST_SRC,
        )
        manifest_path = exported["bridge_prep_manifest"]
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        assert "package_name" in manifest
        assert "generated_at" in manifest
        assert "files" in manifest
        assert len(manifest["files"]) == len(exported) - 1  # manifest 不计入自身

    def test_manifest_files_paths_exist(self, tmp_path):
        exported = export_bridge_prep_package(
            output_dir=tmp_path,
            anchor_rules_path=ANCHOR_RULES,
            bridge_sampling_path=BRIDGE_SAMPLING,
            home_proxy_map_path=HOME_PROXY_MAP,
            question_list_source=QUESTION_LIST_SRC,
        )
        manifest_path = exported["bridge_prep_manifest"]
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        for file_type, file_path in manifest["files"].items():
            assert Path(file_path).exists(), f"manifest 中 {file_type} 文件不存在: {file_path}"

    def test_question_list_has_questions(self, tmp_path):
        exported = export_bridge_prep_package(
            output_dir=tmp_path,
            anchor_rules_path=ANCHOR_RULES,
            bridge_sampling_path=BRIDGE_SAMPLING,
            home_proxy_map_path=HOME_PROXY_MAP,
            question_list_source=QUESTION_LIST_SRC,
        )
        content = Path(exported["bridge_question_list"]).read_text(encoding="utf-8")
        assert "Q1" in content or "问题" in content or "talk test" in content.lower()

    def test_question_list_fallback_when_source_missing(self, tmp_path):
        """source 文件不存在时应生成默认内容而非报错。"""
        nonexistent = tmp_path / "nonexistent_questions.md"
        exported = export_bridge_prep_package(
            output_dir=tmp_path / "out",
            anchor_rules_path=ANCHOR_RULES,
            bridge_sampling_path=BRIDGE_SAMPLING,
            home_proxy_map_path=HOME_PROXY_MAP,
            question_list_source=nonexistent,
        )
        q_path = exported["bridge_question_list"]
        assert Path(q_path).exists()
        content = Path(q_path).read_text(encoding="utf-8")
        assert len(content) > 50  # 有实质内容

    def test_manifest_next_steps_present(self, tmp_path):
        exported = export_bridge_prep_package(
            output_dir=tmp_path,
            anchor_rules_path=ANCHOR_RULES,
            bridge_sampling_path=BRIDGE_SAMPLING,
            home_proxy_map_path=HOME_PROXY_MAP,
            question_list_source=QUESTION_LIST_SRC,
        )
        with open(exported["bridge_prep_manifest"], encoding="utf-8") as f:
            manifest = json.load(f)
        assert "next_steps" in manifest
        assert len(manifest["next_steps"]) > 0
