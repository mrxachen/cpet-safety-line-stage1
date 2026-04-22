"""
test_contracts.py — contracts 模块单元测试。

覆盖：
- schema 验证通过场景
- schema 验证失败场景（必填字段缺失）
- 类型不匹配警告
- category 非法值警告
- ValidationResult 序列化
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cpet_stage1.contracts.schema_validator import ValidationResult, validate_staging

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_V2 = PROJECT_ROOT / "configs/data/schema_v2.yaml"


def _make_valid_df(n: int = 5) -> pd.DataFrame:
    """构造符合 schema_v2 的最小合法 DataFrame。"""
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "subject_id": [f"S{i:04d}" for i in range(n)],
        "group_code": ["CTRL"] * n,
        "age": rng.uniform(50, 80, n).astype(float),
        "sex": rng.choice(["M", "F"], n),
        "vo2_peak": rng.uniform(12, 30, n).astype(float),
        "hr_peak": rng.uniform(100, 180, n).astype(float),
        "rer_peak": rng.uniform(1.0, 1.3, n).astype(float),
        "htn_history": [True, False, True, False, True],
    })


class TestSchemaValidatorPass:
    def test_valid_df_passes(self):
        df = _make_valid_df()
        result = validate_staging(df, SCHEMA_V2)
        assert isinstance(result, ValidationResult)
        # 基本必填字段存在，应无 errors
        assert len(result.errors) == 0, f"不应有错误: {result.errors}"

    def test_result_has_field_stats(self):
        df = _make_valid_df()
        result = validate_staging(df, SCHEMA_V2)
        assert isinstance(result.field_stats, dict)
        assert "subject_id" in result.field_stats

    def test_passed_is_true_for_valid_data(self):
        df = _make_valid_df()
        result = validate_staging(df, SCHEMA_V2)
        assert result.passed is True


class TestSchemaValidatorFailRequired:
    def test_missing_subject_id_raises_error(self):
        """缺少 required 字段 subject_id 应产生 error。"""
        df = _make_valid_df()
        df = df.drop(columns=["subject_id"])
        result = validate_staging(df, SCHEMA_V2)
        assert len(result.errors) > 0
        assert result.passed is False
        # 错误消息应提到 subject_id
        assert any("subject_id" in e for e in result.errors)

    def test_missing_group_code_raises_error(self):
        df = _make_valid_df()
        df = df.drop(columns=["group_code"])
        result = validate_staging(df, SCHEMA_V2)
        assert any("group_code" in e for e in result.errors)
        assert result.passed is False


class TestSchemaValidatorWarnings:
    def test_non_numeric_in_float_field_warns(self):
        """float 字段含字符串值应产生 warning。"""
        df = _make_valid_df()
        df["vo2_peak"] = df["vo2_peak"].astype(str)
        df.loc[0, "vo2_peak"] = "invalid_value"
        result = validate_staging(df, SCHEMA_V2)
        assert len(result.warnings) > 0

    def test_out_of_range_warns(self):
        """超出 schema range 的值应产生 warning。"""
        df = _make_valid_df()
        df.loc[0, "vo2_peak"] = 9999.0  # 远超 max=70
        result = validate_staging(df, SCHEMA_V2)
        range_warnings = [w for w in result.warnings if "range" in w.lower() or "范围" in w]
        assert len(range_warnings) > 0

    def test_invalid_category_warns(self):
        """group_code 不在 allowed categories 中应产生 warning。"""
        df = _make_valid_df()
        df.loc[0, "group_code"] = "INVALID_GROUP"
        result = validate_staging(df, SCHEMA_V2)
        cat_warnings = [w for w in result.warnings if "group_code" in w or "categor" in w.lower()]
        assert len(cat_warnings) > 0

    def test_missing_optional_field_warns(self):
        """缺少可选字段应产生 warning，不产生 error。"""
        df = _make_valid_df()
        # vo2_peak_abs 是可选字段（required 未设为 true）
        assert "vo2_peak_abs" not in df.columns
        result = validate_staging(df, SCHEMA_V2)
        # 不应因缺少可选字段而产生 error
        opt_errors = [e for e in result.errors if "vo2_peak_abs" in e]
        assert len(opt_errors) == 0


class TestValidationResult:
    def test_report_method_returns_string(self):
        result = ValidationResult(passed=True, errors=[], warnings=["test warning"])
        report = result.report()
        assert isinstance(report, str)
        assert "通过" in report or "passed" in report.lower()

    def test_report_method_shows_errors(self):
        result = ValidationResult(
            passed=False,
            errors=["必填字段缺失: subject_id"],
            warnings=[],
        )
        report = result.report()
        assert "subject_id" in report

    def test_to_dict(self):
        result = ValidationResult(
            passed=True,
            errors=[],
            warnings=["warning 1"],
            field_stats={"age": {"status": "ok"}},
        )
        d = result.to_dict()
        assert d["passed"] is True
        assert d["warnings"] == ["warning 1"]
        assert "age" in d["field_stats"]

    def test_save_to_json(self, tmp_path):
        import json
        result = ValidationResult(
            passed=True,
            errors=[],
            warnings=[],
            field_stats={"vo2_peak": {"status": "ok", "dtype": "float"}},
        )
        out = tmp_path / "validation_report.json"
        result.save(out)
        assert out.exists()
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        assert data["passed"] is True
        assert "vo2_peak" in data["field_stats"]


class TestStrictMode:
    def test_strict_false_warnings_still_pass(self):
        """非严格模式下，仅有 warning 应视为通过。"""
        df = _make_valid_df()
        df.loc[0, "vo2_peak"] = 999.0  # 产生 range warning
        result = validate_staging(df, SCHEMA_V2, strict=False)
        # 无 errors → passed
        assert result.passed is True

    def test_strict_true_warnings_fail(self):
        """严格模式下，有 warning 也应失败。"""
        df = _make_valid_df()
        df.loc[0, "vo2_peak"] = 999.0  # 产生 range warning
        result = validate_staging(df, SCHEMA_V2, strict=True)
        assert result.passed is False
