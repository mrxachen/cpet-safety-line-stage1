"""
proxy_hypothesis.py — 家庭代理假设表生成器。

从 anchor_rules_v1.yaml 和 home_proxy_map_v0.yaml 生成：
    home_proxy_hypothesis_table_v1.csv

状态：HYPOTHESIS — 待阶段 II/III 验证。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

logger = logging.getLogger(__name__)


def _load_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        logger.warning("YAML 文件不存在: %s，返回空字典", path)
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_proxy_hypothesis_table(
    anchor_rules_path: str | Path = "configs/bridge/anchor_rules_v1.yaml",
    home_proxy_map_path: str | Path = "configs/bridge/home_proxy_map_v0.yaml",
) -> pd.DataFrame:
    """
    构建家庭代理假设表。

    将 anchor_rules_v1.yaml 中的每个锚点变量，与 home_proxy_map_v0.yaml 中的
    家庭代理信号匹配，输出统一的 CSV 格式假设表。

    返回 DataFrame，列：
        axis, var_id, canonical_field, description, unit, priority,
        clinical_meaning, home_proxy_hypothesis, feasibility, evidence_level
    """
    anchor_cfg = _load_yaml(anchor_rules_path)
    proxy_map = _load_yaml(home_proxy_map_path)

    # 构建 proxy 反向查找：anchor_var_id → proxy info
    proxy_by_anchor: dict[str, dict] = {}
    for proxy_name, proxy_info in proxy_map.get("proxies", {}).items():
        anchor_id = proxy_info.get("maps_to_anchor", "")
        if anchor_id:
            proxy_by_anchor[anchor_id] = {
                "proxy_name": proxy_name,
                "feasibility": proxy_info.get("feasibility", ""),
                "evidence_level": proxy_info.get("evidence_level", ""),
                "measurement": proxy_info.get("measurement", ""),
                "equipment": proxy_info.get("equipment", ""),
            }

    rows = []
    for axis_key in ["axis_R", "axis_T", "axis_I"]:
        axis_cfg = anchor_cfg.get(axis_key, {})
        axis_label = axis_key.split("_")[1]  # R / T / I

        for var_id, var_info in axis_cfg.get("variables", {}).items():
            proxy_info = proxy_by_anchor.get(var_id, {})
            row = {
                "axis": axis_label,
                "var_id": var_id,
                "canonical_field": var_info.get("canonical_field", ""),
                "description": var_info.get("description", ""),
                "unit": var_info.get("unit", ""),
                "priority": var_info.get("priority", ""),
                "clinical_meaning": var_info.get("clinical_meaning", ""),
                "home_proxy_hypothesis": var_info.get("home_proxy_hypothesis", ""),
                "proxy_name": proxy_info.get("proxy_name", ""),
                "proxy_measurement": proxy_info.get("measurement", ""),
                "proxy_equipment": proxy_info.get("equipment", ""),
                "feasibility": proxy_info.get("feasibility", ""),
                "evidence_level": proxy_info.get("evidence_level", ""),
            }
            rows.append(row)

    df = pd.DataFrame(rows)
    logger.info("家庭代理假设表构建完成: %d 行", len(df))
    return df


class ProxyHypothesisBuilder:
    """家庭代理假设表构建器（封装接口）。"""

    def __init__(
        self,
        anchor_rules_path: str | Path = "configs/bridge/anchor_rules_v1.yaml",
        home_proxy_map_path: str | Path = "configs/bridge/home_proxy_map_v0.yaml",
    ) -> None:
        self._anchor_path = Path(anchor_rules_path)
        self._proxy_path = Path(home_proxy_map_path)

    def build(self) -> pd.DataFrame:
        return build_proxy_hypothesis_table(self._anchor_path, self._proxy_path)

    def save(self, df: pd.DataFrame, output_path: str | Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        logger.info(
            "home_proxy_hypothesis_table 已保存: %s (%d 行)",
            output_path,
            len(df),
        )
        return output_path
