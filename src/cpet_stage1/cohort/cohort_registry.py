"""
cohort_registry.py — 2×2 队列注册模块。

功能：
    从 curated DataFrame（含 group_code 列）注册 HTN × EIH 2×2 队列，
    推导 htn_history / eih_status，生成 cohort_2x2 标签和 cpet_session_id。

group_code 映射：
    CTRL                  → htn=False, eih=False → "HTN-/EIH-"
    EHT_ONLY              → htn=False, eih=True  → "HTN-/EIH+"
    HTN_HISTORY_NO_EHT    → htn=True,  eih=False → "HTN+/EIH-"
    HTN_HISTORY_WITH_EHT  → htn=True,  eih=True  → "HTN+/EIH+"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# group_code → (htn_history, eih_status, cohort_2x2)
_GROUP_CODE_MAP: dict[str, tuple[bool, bool, str]] = {
    "CTRL": (False, False, "HTN-/EIH-"),
    "EHT_ONLY": (False, True, "HTN-/EIH+"),
    "HTN_HISTORY_NO_EHT": (True, False, "HTN+/EIH-"),
    "HTN_HISTORY_WITH_EHT": (True, True, "HTN+/EIH+"),
}


@dataclass
class CohortRegistryResult:
    """队列注册结果。"""

    df: pd.DataFrame                    # 带新列的 DataFrame
    cohort_counts: dict[str, int]       # 各象限样本量
    unknown_group_codes: list[str]      # 未识别的 group_code
    n_total: int = field(init=False)

    def __post_init__(self) -> None:
        self.n_total = len(self.df)

    def summary(self) -> str:
        """返回可读摘要字符串。"""
        lines = [
            f"CohortRegistry: {self.n_total} 行",
            "  2×2 队列分布：",
        ]
        for quad, cnt in sorted(self.cohort_counts.items()):
            lines.append(f"    {quad}: {cnt}")
        if self.unknown_group_codes:
            lines.append(f"  未识别 group_code: {self.unknown_group_codes}")
        return "\n".join(lines)


class CohortRegistry:
    """
    从 curated DataFrame 注册 2×2 队列。

    使用方法：
        registry = CohortRegistry()
        result = registry.register(df)
        df_out = result.df
    """

    def __init__(self) -> None:
        self._group_map = _GROUP_CODE_MAP

    def _derive_cohort_fields(self, group_code: str) -> tuple[bool | None, bool | None, str | None]:
        """
        从单个 group_code 推导 (htn_history, eih_status, cohort_2x2)。
        未识别的 group_code 返回 (None, None, None)。
        """
        mapping = self._group_map.get(group_code)
        if mapping is None:
            return None, None, None
        htn, eih, quad = mapping
        return htn, eih, quad

    def register(self, df: pd.DataFrame) -> CohortRegistryResult:
        """
        注册队列，添加以下列到 DataFrame（返回副本）：
        - htn_history: bool（从 group_code 推导，覆盖原有值）
        - eih_status: bool（从 group_code 推导，覆盖原有值）
        - cohort_2x2: str（"HTN-/EIH-" / "HTN-/EIH+" / "HTN+/EIH-" / "HTN+/EIH+"）
        - cpet_session_id: str（本阶段 1:1，等于 subject_id；若 subject_id 不存在则用行索引）

        参数：
            df: curated DataFrame，必须含 group_code 列

        返回：
            CohortRegistryResult
        """
        if "group_code" not in df.columns:
            raise ValueError("DataFrame 缺少 'group_code' 列，无法注册队列")

        result_df = df.copy()

        # 推导三个新列
        derived = result_df["group_code"].apply(self._derive_cohort_fields)
        result_df["htn_history"] = derived.apply(lambda x: x[0])
        result_df["eih_status"] = derived.apply(lambda x: x[1])
        result_df["cohort_2x2"] = derived.apply(lambda x: x[2])

        # 记录未识别 group_code
        unknown_mask = result_df["htn_history"].isna()
        unknown_codes: list[str] = []
        if unknown_mask.any():
            unknown_codes = result_df.loc[unknown_mask, "group_code"].unique().tolist()
            logger.warning(
                "CohortRegistry: %d 行包含未识别 group_code: %s",
                unknown_mask.sum(),
                unknown_codes,
            )

        # 生成 cpet_session_id（阶段 I：1:1 对应 subject_id）
        if "subject_id" in result_df.columns:
            result_df["cpet_session_id"] = result_df["subject_id"].astype(str)
        else:
            # 用行索引生成
            result_df["cpet_session_id"] = [
                f"SESSION_{i:06d}" for i in range(len(result_df))
            ]
            logger.warning(
                "CohortRegistry: subject_id 列不存在，使用行索引生成 cpet_session_id"
            )

        # 统计各象限样本量
        cohort_counts: dict[str, int] = (
            result_df["cohort_2x2"]
            .value_counts()
            .to_dict()
        )

        logger.info(
            "CohortRegistry 完成: %d 行，四象限: %s",
            len(result_df),
            cohort_counts,
        )

        return CohortRegistryResult(
            df=result_df,
            cohort_counts=cohort_counts,
            unknown_group_codes=unknown_codes,
        )

    def save(self, result: CohortRegistryResult, output_path: str | Path) -> Path:
        """
        将注册结果保存为 parquet。

        返回保存路径。
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.df.to_parquet(output_path, index=False)
        logger.info("CohortRegistry 保存: %s (%d 行)", output_path, len(result.df))
        return output_path
