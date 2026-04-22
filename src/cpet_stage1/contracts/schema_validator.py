"""
schema_validator.py — 验证 staging DataFrame 是否符合 schema。

检查内容：
1. 必填列是否存在（required: true）
2. 数值字段类型是否可转换
3. category 字段是否在允许的 categories 范围内
4. range 约束（和 QC range_checks 独立，此处只验证 schema 定义的范围）

使用示例：
    from cpet_stage1.contracts.schema_validator import validate_staging
    result = validate_staging(df, "configs/data/schema_v2.yaml")
    if not result.passed:
        print(result.report())
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

logger = logging.getLogger(__name__)


def _load_yaml(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _flatten_schema(schema: dict) -> dict[str, dict]:
    """展平嵌套 schema 为 {field_name: spec}。"""
    flat: dict[str, dict] = {}
    skip_keys = {"version", "description"}
    for section_key, section_val in schema.items():
        if section_key in skip_keys:
            continue
        if not isinstance(section_val, dict):
            continue
        for field_name, field_spec in section_val.items():
            if isinstance(field_spec, dict):
                flat[field_name] = field_spec
    return flat


@dataclass
class ValidationResult:
    """schema 验证结果。"""

    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    field_stats: dict[str, dict] = field(default_factory=dict)

    def report(self) -> str:
        """生成文字报告。"""
        lines = ["=== Schema 验证报告 ==="]
        lines.append(f"结果: {'通过 ✅' if self.passed else '失败 ❌'}")
        if self.errors:
            lines.append(f"\n错误（{len(self.errors)} 项）:")
            for e in self.errors:
                lines.append(f"  ✗ {e}")
        if self.warnings:
            lines.append(f"\n警告（{len(self.warnings)} 项）:")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "field_stats": self.field_stats,
        }

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info("验证报告已保存: %s", path)


def validate_staging(
    df: pd.DataFrame,
    schema_path: str | Path,
    strict: bool = False,
) -> ValidationResult:
    """
    验证 staging DataFrame 是否符合 schema。

    参数：
        df:          待验证的 DataFrame
        schema_path: schema YAML 路径
        strict:      True 则 warning 也算 failed

    返回：
        ValidationResult
    """
    schema_path = Path(schema_path)
    schema_raw = _load_yaml(schema_path)
    flat_schema = _flatten_schema(schema_raw)

    errors: list[str] = []
    warnings: list[str] = []
    field_stats: dict[str, dict] = {}

    for field_name, spec in flat_schema.items():
        required = spec.get("required", False)
        dtype = spec.get("dtype", "string")
        categories = spec.get("categories")
        rng = spec.get("range")

        # 1. 必填字段存在性检查
        if field_name not in df.columns:
            if required:
                errors.append(f"必填字段缺失: {field_name!r}")
            else:
                warnings.append(f"可选字段缺失: {field_name!r}")
            field_stats[field_name] = {"status": "missing", "required": required}
            continue

        col = df[field_name]
        stats: dict = {"status": "ok", "dtype": dtype, "n_null": int(col.isna().sum())}

        # 2. 数值类型可转换性
        if dtype in ("float", "int"):
            numeric = pd.to_numeric(col, errors="coerce")
            n_bad = int((col.notna() & numeric.isna()).sum())
            if n_bad > 0:
                warnings.append(
                    f"字段 {field_name!r} (dtype={dtype}): {n_bad} 行无法转换为数值"
                )
                stats["n_non_numeric"] = n_bad

            # range 检查（schema 级别）
            if rng and len(rng) == 2:
                lo, hi = rng
                out = ((numeric < lo) | (numeric > hi)) & numeric.notna()
                n_out = int(out.sum())
                if n_out > 0:
                    warnings.append(
                        f"字段 {field_name!r}: {n_out} 行超出 schema 范围 [{lo}, {hi}]"
                    )
                    stats["n_out_of_range"] = n_out

        # 3. category 字段合法值检查
        if dtype == "category" and categories:
            allowed = {str(c) for c in categories}
            invalid = col.dropna().apply(lambda x: str(x) not in allowed)
            n_invalid = int(invalid.sum())
            if n_invalid > 0:
                warnings.append(
                    f"字段 {field_name!r}: {n_invalid} 行不在允许 categories 范围内 {categories}"
                )
                stats["n_invalid_category"] = n_invalid

        field_stats[field_name] = stats

    passed = len(errors) == 0 and (len(warnings) == 0 if strict else True)
    result = ValidationResult(
        passed=passed,
        errors=errors,
        warnings=warnings,
        field_stats=field_stats,
    )

    if passed:
        logger.info("Schema 验证通过 (strict=%s): 0 errors, %d warnings", strict, len(warnings))
    else:
        logger.warning(
            "Schema 验证失败: %d errors, %d warnings",
            len(errors), len(warnings),
        )
        for e in errors:
            logger.warning("  ERROR: %s", e)

    return result
