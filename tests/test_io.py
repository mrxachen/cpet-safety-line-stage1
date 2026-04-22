"""
test_io.py — io 模块单元测试。

覆盖：
- field_map 加载与反向映射构建
- 列名映射（中文 → canonical）
- value_map 应用（男→M 等）
- 缺失值统一（"-"、"无"、"" → NaN）
- demo CSV 可通过 loaders.load_demo_csv()
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from cpet_stage1.io.excel_import import (
    ExcelImporter,
    _build_reverse_map,
    _build_value_maps,
    _flatten_schema,
    _load_yaml,
    compute_hash_registry,
)
from cpet_stage1.io.loaders import load_demo_csv

# ------------------------------------------------------------------ #
# 固定件（Fixtures）
# ------------------------------------------------------------------ #

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIELD_MAP_V2 = PROJECT_ROOT / "configs/data/field_map_v2.yaml"
SCHEMA_V2 = PROJECT_ROOT / "configs/data/schema_v2.yaml"
DEMO_CSV = PROJECT_ROOT / "data/demo/synthetic_cpet_stage1.csv"


@pytest.fixture(scope="module")
def field_map_raw():
    return _load_yaml(FIELD_MAP_V2)


@pytest.fixture(scope="module")
def schema_raw():
    return _load_yaml(SCHEMA_V2)


@pytest.fixture(scope="module")
def reverse_map(field_map_raw):
    return _build_reverse_map(field_map_raw)


@pytest.fixture(scope="module")
def value_maps(field_map_raw):
    return _build_value_maps(field_map_raw)


@pytest.fixture(scope="module")
def flat_schema(schema_raw):
    return _flatten_schema(schema_raw)


# ------------------------------------------------------------------ #
# 1. 配置文件加载测试
# ------------------------------------------------------------------ #

class TestFieldMapLoading:
    def test_field_map_v2_exists(self):
        assert FIELD_MAP_V2.exists(), f"field_map_v2.yaml 不存在: {FIELD_MAP_V2}"

    def test_field_map_v2_version(self, field_map_raw):
        assert field_map_raw.get("version") == "2.0"

    def test_reverse_map_not_empty(self, reverse_map):
        assert len(reverse_map) > 50, "反向映射应包含至少 50 个条目"

    def test_canonical_names_in_reverse_map(self, reverse_map):
        """canonical 名本身应包含在反向映射中。"""
        assert "vo2_peak" in reverse_map
        assert "hr_peak" in reverse_map
        assert "age" in reverse_map

    def test_chinese_aliases_in_reverse_map(self, reverse_map):
        """中文别名应在反向映射中。"""
        assert "最大值-VO2" in reverse_map, "最大值-VO2 应映射到 vo2_peak"
        assert reverse_map["最大值-VO2"] == "vo2_peak"

    def test_vo2_peak_abs_alias(self, reverse_map):
        """带 * 的 VO2 应映射到 vo2_peak_abs。"""
        assert "最大值-VO2*" in reverse_map
        assert reverse_map["最大值-VO2*"] == "vo2_peak_abs"

    def test_test_date_alias_DATE(self, reverse_map):
        """DATE 应映射到 test_date。"""
        assert "DATE" in reverse_map
        assert reverse_map["DATE"] == "test_date"

    def test_hr_peak_alias(self, reverse_map):
        assert "最大值-HR" in reverse_map
        assert reverse_map["最大值-HR"] == "hr_peak"


class TestValueMaps:
    def test_sex_value_map_exists(self, value_maps):
        assert "sex" in value_maps

    def test_sex_male_mapping(self, value_maps):
        assert value_maps["sex"]["男"] == "M"
        assert value_maps["sex"]["女"] == "F"

    def test_boolean_value_map(self, value_maps):
        """是/否 → 1/0 的映射应正确（排除有自定义映射的字段如 exercise_habit）。"""
        # 只检查标准二值字段（映射到 0/1 整数的）
        standard_binary_fields = [
            f for f, vm in value_maps.items()
            if "是" in vm and vm.get("是") in (0, 1)  # 仅检查映射到整数的字段
        ]
        assert len(standard_binary_fields) > 0, "至少应有一个标准二值字段"
        for field_name in standard_binary_fields:
            vm = value_maps[field_name]
            assert vm["是"] == 1, f"{field_name}: 是 应映射为 1"
            assert vm["否"] == 0, f"{field_name}: 否 应映射为 0"


class TestSchemaLoading:
    def test_schema_v2_exists(self):
        assert SCHEMA_V2.exists(), f"schema_v2.yaml 不存在: {SCHEMA_V2}"

    def test_schema_v2_version(self, schema_raw):
        assert schema_raw.get("version") == "2.0"

    def test_flat_schema_contains_key_fields(self, flat_schema):
        required = ["subject_id", "group_code", "age", "sex", "vo2_peak", "hr_peak"]
        for fld in required:
            assert fld in flat_schema, f"关键字段 {fld!r} 不在 schema 中"

    def test_flat_schema_vo2_peak_abs(self, flat_schema):
        assert "vo2_peak_abs" in flat_schema
        assert flat_schema["vo2_peak_abs"]["unit"] == "mL/min"

    def test_flat_schema_drug_fields(self, flat_schema):
        drug_fields = ["med_ccb", "med_acei", "med_betablocker", "med_statin"]
        for f in drug_fields:
            assert f in flat_schema, f"药物字段 {f!r} 缺失"
            assert flat_schema[f]["dtype"] == "category"


# ------------------------------------------------------------------ #
# 2. 列名映射测试
# ------------------------------------------------------------------ #

class TestColumnMapping:
    def _make_importer(self):
        return ExcelImporter(
            field_map_path=FIELD_MAP_V2,
            schema_path=SCHEMA_V2,
        )

    def test_importer_init(self):
        imp = self._make_importer()
        assert imp is not None

    def test_apply_column_mapping_basic(self):
        """最基础的列名映射测试。"""
        imp = self._make_importer()
        df = pd.DataFrame({
            "最大值-VO2": [18.5, 22.1],
            "最大值-HR": [148, 162],
            "年龄": [65, 72],
            "性别": ["男", "女"],
        })
        mapped = imp._apply_column_mapping(df, group_code="TEST")
        assert "vo2_peak" in mapped.columns, "最大值-VO2 应映射为 vo2_peak"
        assert "hr_peak" in mapped.columns
        assert "age" in mapped.columns
        assert "sex" in mapped.columns

    def test_apply_column_mapping_vo2_abs(self):
        """带 * 的列映射测试。"""
        imp = self._make_importer()
        df = pd.DataFrame({"最大值-VO2*": [1850, 2210]})
        mapped = imp._apply_column_mapping(df, "TEST")
        assert "vo2_peak_abs" in mapped.columns

    def test_apply_column_mapping_preserves_unmatched(self):
        """未映射列应保留在 DataFrame 中。"""
        imp = self._make_importer()
        df = pd.DataFrame({"未知列_xyz": [1, 2], "年龄": [65, 72]})
        mapped = imp._apply_column_mapping(df, "TEST")
        assert "age" in mapped.columns
        # 未匹配列不应被删除（仅记录）
        assert "未知列_xyz" in mapped.columns


# ------------------------------------------------------------------ #
# 3. 缺失值处理测试
# ------------------------------------------------------------------ #

class TestMissingNormalization:
    def _make_importer(self):
        return ExcelImporter(FIELD_MAP_V2, SCHEMA_V2)

    def test_dash_becomes_nan(self):
        imp = self._make_importer()
        df = pd.DataFrame({"vo2_peak": ["-", "18.5", "无", ""]})
        result = imp._normalize_missing(df)
        assert pd.isna(result.loc[0, "vo2_peak"])  # "-"
        assert pd.isna(result.loc[2, "vo2_peak"])  # "无"
        assert pd.isna(result.loc[3, "vo2_peak"])  # ""
        assert result.loc[1, "vo2_peak"] == "18.5"  # 有效值保留

    def test_nan_string_becomes_nan(self):
        imp = self._make_importer()
        df = pd.DataFrame({"age": ["nan", "65", "NaN", "N/A"]})
        result = imp._normalize_missing(df)
        assert pd.isna(result.loc[0, "age"])
        assert pd.isna(result.loc[2, "age"])
        assert pd.isna(result.loc[3, "age"])
        assert result.loc[1, "age"] == "65"


# ------------------------------------------------------------------ #
# 4. value_map 应用测试
# ------------------------------------------------------------------ #

class TestValueMapApplication:
    def _make_importer(self):
        return ExcelImporter(FIELD_MAP_V2, SCHEMA_V2)

    def test_sex_value_map_applied(self):
        imp = self._make_importer()
        df = pd.DataFrame({"sex": ["男", "女", np.nan]})
        result = imp._apply_value_maps(df)
        assert result.loc[0, "sex"] == "M"
        assert result.loc[1, "sex"] == "F"
        assert pd.isna(result.loc[2, "sex"])

    def test_boolean_field_value_map(self):
        imp = self._make_importer()
        df = pd.DataFrame({"med_statin": ["是", "否", "1", "0"]})
        result = imp._apply_value_maps(df)
        assert result.loc[0, "med_statin"] == 1
        assert result.loc[1, "med_statin"] == 0
        assert result.loc[2, "med_statin"] == 1
        assert result.loc[3, "med_statin"] == 0


# ------------------------------------------------------------------ #
# 5. 完整 pipeline 测试（基于合成数据）
# ------------------------------------------------------------------ #

class TestEndToEndWithDemoData:
    def test_load_demo_csv(self):
        if not DEMO_CSV.exists():
            pytest.skip("演示 CSV 不存在，跳过")
        df = load_demo_csv(DEMO_CSV)
        assert len(df) > 0
        assert "vo2_peak" in df.columns

    def test_importer_with_demo_like_data(self, tmp_path):
        """用接近真实格式的合成数据测试完整 import_file 流程。"""
        # 构造一个小型测试 Excel（用 pandas 写出后再读入）
        test_data = pd.DataFrame({
            "年龄": ["65", "72", "-"],
            "性别": ["男", "女", "男"],
            "最大值-VO2": ["18.5", "无", "22.1"],
            "最大值-HR": ["148", "162", "155"],
            "最大值-VO2*": ["1850", "1950", "-"],
            "β受体阻滞剂": ["是", "否", "1"],
        })
        excel_path = tmp_path / "test_group.xlsx"
        test_data.to_excel(excel_path, index=False)

        imp = ExcelImporter(FIELD_MAP_V2, SCHEMA_V2)
        result = imp.import_file(excel_path, group_code="TEST_GROUP")

        assert len(result) == 3
        assert "group_code" in result.columns
        assert result["group_code"].iloc[0] == "TEST_GROUP"
        assert "vo2_peak" in result.columns
        assert "hr_peak" in result.columns
        assert "vo2_peak_abs" in result.columns
        # 性别映射
        assert result["sex"].iloc[0] == "M"
        assert result["sex"].iloc[1] == "F"
        # 缺失值处理
        assert pd.isna(result["vo2_peak"].iloc[1])  # "无" → NaN
        assert pd.isna(result["age"].iloc[2])  # "-" → NaN
        # β受体阻滞剂 value_map（category dtype 统一转为 str）
        assert str(result["med_betablocker"].iloc[0]) == "1"
        assert str(result["med_betablocker"].iloc[1]) == "0"


# ------------------------------------------------------------------ #
# 6. hash registry 测试
# ------------------------------------------------------------------ #

class TestHashRegistry:
    def test_compute_hash_registry_empty(self):
        result = compute_hash_registry([])
        assert result == {}

    def test_compute_hash_registry_missing_file(self, tmp_path):
        result = compute_hash_registry([tmp_path / "nonexistent.xlsx"])
        assert result == {}

    def test_compute_hash_registry_real_file(self, tmp_path):
        f = tmp_path / "test.xlsx"
        f.write_bytes(b"test content 12345")
        result = compute_hash_registry([f])
        assert "test.xlsx" in result
        assert len(result["test.xlsx"]) == 64  # SHA256 hex 长度

    def test_compute_hash_registry_deterministic(self, tmp_path):
        f = tmp_path / "data.xlsx"
        f.write_bytes(b"reproducible content")
        r1 = compute_hash_registry([f])
        r2 = compute_hash_registry([f])
        assert r1 == r2
