"""
excel_import.py — 从 Excel 文件导入 CPET 数据到 staging parquet。

核心职责：
1. 读取 Excel 文件（中文列名）
2. 应用 field_map_v2.yaml 映射为英文 canonical 名
3. 应用 value_map（如 男→M，是→1）
4. 统一缺失值标记（"-"、"无"、"" → NaN）
5. 按 schema dtype 进行类型转换
6. 注入 group_code 列
7. 输出 staging parquet + field_mapping_report.json

使用示例：
    from cpet_stage1.io.excel_import import ExcelImporter
    importer = ExcelImporter(field_map_path="configs/data/field_map_v2.yaml",
                             schema_path="configs/data/schema_v2.yaml")
    df = importer.import_file("健康对照.xlsx", group_code="CTRL")
    importer.import_batch("data/manifests/batch_cpet_example_manifest.json")
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

# 统一识别为缺失的值（不区分大小写）
_MISSING_MARKERS: set[str] = {"-", "无", "nan", "none", "na", "n/a", "", " "}


def _load_yaml(path: str | Path) -> dict:
    """加载 YAML 配置文件。"""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _flatten_schema(schema: dict) -> dict[str, dict]:
    """
    将嵌套 schema 展平为 {canonical_name: field_spec} 字典。
    跳过顶层 'version' / 'description' 键。
    """
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


def _build_reverse_map(field_map: dict) -> dict[str, str]:
    """
    从 field_map YAML 构建反向映射：{中文列名 → canonical_name}。
    field_map 格式：
      canonical_name:
        aliases: [别名1, 别名2, ...]
        value_map: {...}   # 可选
    """
    reverse: dict[str, str] = {}
    skip_keys = {"version"}
    for canonical, spec in field_map.items():
        if canonical in skip_keys:
            continue
        if not isinstance(spec, dict):
            continue
        aliases = spec.get("aliases", [])
        for alias in aliases:
            alias_str = str(alias).strip()
            if alias_str:
                reverse[alias_str] = canonical
        # canonical 名本身也加入反向映射（大小写不变）
        reverse[canonical] = canonical
    return reverse


def _build_value_maps(field_map: dict) -> dict[str, dict]:
    """提取每个字段的 value_map：{canonical_name → {原始值 → 目标值}}。"""
    maps: dict[str, dict] = {}
    skip_keys = {"version"}
    for canonical, spec in field_map.items():
        if canonical in skip_keys:
            continue
        if not isinstance(spec, dict):
            continue
        vm = spec.get("value_map", {})
        if vm:
            maps[canonical] = {str(k): v for k, v in vm.items()}
    return maps


class FieldMappingReport:
    """字段映射统计报告。"""

    def __init__(self) -> None:
        self.mapped: list[dict] = []       # 成功映射
        self.unmapped: list[str] = []      # 原始列名未在 field_map 中找到
        self.missing_expected: list[str] = []  # field_map 有但数据中没有的关键字段

    def add_mapped(self, original: str, canonical: str, group: str) -> None:
        self.mapped.append({"original": original, "canonical": canonical, "group": group})

    def add_unmapped(self, col: str) -> None:
        if col not in self.unmapped:
            self.unmapped.append(col)

    def add_missing_expected(self, field: str) -> None:
        if field not in self.missing_expected:
            self.missing_expected.append(field)

    def to_dict(self) -> dict:
        return {
            "summary": {
                "mapped_count": len(self.mapped),
                "unmapped_count": len(self.unmapped),
                "missing_expected_count": len(self.missing_expected),
            },
            "mapped": self.mapped,
            "unmapped": self.unmapped,
            "missing_expected": self.missing_expected,
        }

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info("字段映射报告已保存: %s", path)


class ExcelImporter:
    """
    读取 Excel 文件，应用字段映射，输出 staging parquet。

    参数：
        field_map_path: field_map_v2.yaml 路径
        schema_path:    schema_v2.yaml 路径
    """

    def __init__(self, field_map_path: str | Path, schema_path: str | Path) -> None:
        self.field_map_path = Path(field_map_path)
        self.schema_path = Path(schema_path)

        # 加载配置
        raw_field_map = _load_yaml(self.field_map_path)
        schema = _load_yaml(self.schema_path)

        self._reverse_map: dict[str, str] = _build_reverse_map(raw_field_map)
        self._value_maps: dict[str, dict] = _build_value_maps(raw_field_map)
        self._flat_schema: dict[str, dict] = _flatten_schema(schema)
        self._report = FieldMappingReport()

        logger.info(
            "ExcelImporter 初始化完成 — field_map 含 %d 个别名映射，schema 含 %d 个字段",
            len(self._reverse_map),
            len(self._flat_schema),
        )

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def import_file(
        self,
        excel_path: str | Path,
        group_code: str,
        sheet_name: int | str = 0,
        header_row: int = 0,
    ) -> pd.DataFrame:
        """
        读取单个 Excel 文件并返回规范化 DataFrame。

        步骤：
        1. pd.read_excel
        2. 列名映射（中文 → canonical）
        3. value_map 应用
        4. 缺失值统一
        5. dtype 转换
        6. 注入 group_code
        """
        excel_path = Path(excel_path)
        logger.info("开始导入: %s (group=%s)", excel_path.name, group_code)

        # 1. 读取 Excel
        df = pd.read_excel(
            excel_path,
            sheet_name=sheet_name,
            header=header_row,
            dtype=str,        # 先全部读为字符串，后续手动转换类型
        )
        logger.info("读取完成: %d 行 × %d 列", len(df), len(df.columns))

        # 2. 列名映射
        df = self._apply_column_mapping(df, group_code)

        # 3. 缺失值统一（先于 value_map，避免 "-" 被误映射）
        df = self._normalize_missing(df)

        # 4. value_map 应用（如 男→M, 是→1）
        df = self._apply_value_maps(df)

        # 5. dtype 转换
        df = self._cast_dtypes(df)

        # 6. 注入 group_code
        df["group_code"] = group_code

        logger.info("导入完成: %d 行 × %d 列 (group=%s)", len(df), len(df.columns), group_code)
        return df

    def import_batch(
        self,
        manifest_path: str | Path,
        data_base_dir: str | Path | None = None,
        output_parquet: str | Path | None = None,
        report_path: str | Path | None = None,
    ) -> pd.DataFrame:
        """
        按 manifest.json 批量导入所有组，合并后返回 DataFrame。

        参数：
            manifest_path: manifest JSON 路径
            data_base_dir: Excel 文件所在目录（None 则使用 manifest 同级目录
                           或 EXTERNAL_DATA_DIR 环境变量）
            output_parquet: 输出 parquet 路径（None 则不写文件）
            report_path:    映射报告 JSON 路径（None 则不写文件）
        """
        manifest_path = Path(manifest_path)
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        # 确定数据文件根目录
        if data_base_dir is None:
            ext_dir = os.environ.get("EXTERNAL_DATA_DIR")
            if ext_dir:
                data_base_dir = Path(ext_dir) / "clinical_structured/BATCH_CPET_EXAMPLE/S01_GROUPED/raw"
            else:
                # 默认使用 manifest 文件同级目录
                data_base_dir = manifest_path.parent
        data_base_dir = Path(data_base_dir)

        group_file_map: dict[str, str] = manifest["group_file_map"]
        sheet_configs: dict[str, dict] = manifest.get("sheet_configs", {})

        all_dfs: list[pd.DataFrame] = []
        self._report = FieldMappingReport()  # 重置报告

        for group_code, filename in group_file_map.items():
            excel_path = data_base_dir / filename
            if not excel_path.exists():
                logger.warning("文件不存在，跳过: %s", excel_path)
                continue

            sheet_cfg = sheet_configs.get(group_code, {})
            sheet_name = sheet_cfg.get("sheet_name", 0)
            header_row = sheet_cfg.get("header_row", 0)

            df_group = self.import_file(
                excel_path=excel_path,
                group_code=group_code,
                sheet_name=sheet_name,
                header_row=header_row,
            )
            all_dfs.append(df_group)

        if not all_dfs:
            logger.error("未成功导入任何 Excel 文件，请检查 data_base_dir 和 manifest 配置")
            return pd.DataFrame()

        combined = pd.concat(all_dfs, ignore_index=True)
        logger.info(
            "批量导入完成: 共 %d 行 × %d 列，来自 %d 组",
            len(combined), len(combined.columns), len(all_dfs),
        )

        # 写出 parquet
        if output_parquet is not None:
            output_parquet = Path(output_parquet)
            output_parquet.parent.mkdir(parents=True, exist_ok=True)
            combined.to_parquet(output_parquet, index=False)
            logger.info("staging parquet 已写出: %s", output_parquet)

        # 写出映射报告
        if report_path is not None:
            self._report.save(report_path)

        return combined

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _apply_column_mapping(self, df: pd.DataFrame, group_code: str) -> pd.DataFrame:
        """将中文列名映射为 canonical 英文名，记录未匹配列。"""
        rename_map: dict[str, str] = {}
        for col in df.columns:
            col_str = str(col).strip()
            canonical = self._reverse_map.get(col_str)
            if canonical:
                rename_map[col] = canonical
                self._report.add_mapped(col_str, canonical, group_code)
            else:
                self._report.add_unmapped(col_str)
                logger.debug("未匹配列: %r (group=%s)", col_str, group_code)

        df = df.rename(columns=rename_map)
        # 删除未映射列（保留以便调试时查看可加参数控制）
        unmapped_in_df = [c for c in df.columns if c not in self._flat_schema and c != "group_code"]
        if unmapped_in_df:
            logger.debug("以下列未在 schema 中定义，将保留原始名: %s", unmapped_in_df[:10])
        return df

    def _normalize_missing(self, df: pd.DataFrame) -> pd.DataFrame:
        """将各种缺失值标记统一替换为 NaN。"""
        def _is_missing(val: Any) -> bool:
            if pd.isna(val):
                return True
            return str(val).strip().lower() in _MISSING_MARKERS

        return df.map(lambda x: float("nan") if _is_missing(x) else x)

    def _apply_value_maps(self, df: pd.DataFrame) -> pd.DataFrame:
        """对每个有 value_map 的字段应用值替换。"""
        for col, vm in self._value_maps.items():
            if col not in df.columns:
                continue
            df[col] = df[col].apply(
                lambda x, _vm=vm: _vm.get(str(x).strip(), x) if pd.notna(x) else x
            )
        return df

    def _cast_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """按 schema dtype 做类型转换，转换失败置为 NaN。"""
        for col, spec in self._flat_schema.items():
            if col not in df.columns:
                continue
            dtype = spec.get("dtype", "string")
            try:
                if dtype in ("float", "int"):
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                    if dtype == "int":
                        df[col] = df[col].astype("Int64")  # 可空整数
                elif dtype == "bool":
                    # 处理数值型布尔（0/1）和字符串
                    df[col] = df[col].map(
                        lambda x: (
                            None if pd.isna(x)
                            else bool(int(float(x))) if str(x).strip() in ("0", "1", "0.0", "1.0")
                            else bool(x)
                        )
                    )
                elif dtype == "category":
                    # 先统一转为 str（防止 value_map 部分映射后出现 int/str 混合类型）
                    df[col] = df[col].apply(
                        lambda x: str(x) if pd.notna(x) else x
                    ).astype("category")
                elif dtype == "date":
                    df[col] = pd.to_datetime(df[col], errors="coerce")
                # string: 保持原样（已为字符串）
            except Exception as exc:
                logger.warning("字段 %r dtype=%r 转换失败: %s", col, dtype, exc)

        return df

    def get_report(self) -> FieldMappingReport:
        """返回最近一次 import_batch 的映射报告。"""
        return self._report


def compute_hash_registry(file_paths: list[str | Path]) -> dict[str, str]:
    """
    计算源文件 SHA256 hash，生成可复现性清单。

    返回：{文件名 → sha256_hex}
    """
    registry: dict[str, str] = {}
    for fp in file_paths:
        fp = Path(fp)
        if not fp.exists():
            logger.warning("文件不存在，跳过 hash: %s", fp)
            continue
        sha256 = hashlib.sha256()
        with open(fp, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        registry[fp.name] = sha256.hexdigest()
        logger.debug("hash(%s) = %s", fp.name, sha256.hexdigest()[:16] + "...")
    return registry
