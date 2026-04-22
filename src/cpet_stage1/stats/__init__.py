"""stats package — M4 统计分析模块。"""

from cpet_stage1.stats.reference_builder import ReferenceBuilder, ReferenceBuilderResult
from cpet_stage1.stats.table1 import Table1Builder, Table1Result, build_stratified_table1
from cpet_stage1.stats.twobytwo import TwoByTwoAnalyzer, TwoByTwoResult
from cpet_stage1.stats.posthoc import DunnPosthoc, PosthocResult, generate_posthoc_report
from cpet_stage1.stats.logistic_eih import (
    EIHLogisticAnalyzer,
    EIHLogisticResult,
    generate_eih_logistic_report,
)
from cpet_stage1.stats.subgroup import (
    SubgroupAnalyzer,
    SubgroupResult,
    generate_subgroup_report,
)

__all__ = [
    "Table1Builder",
    "Table1Result",
    "build_stratified_table1",
    "TwoByTwoAnalyzer",
    "TwoByTwoResult",
    "ReferenceBuilder",
    "ReferenceBuilderResult",
    "DunnPosthoc",
    "PosthocResult",
    "generate_posthoc_report",
    "EIHLogisticAnalyzer",
    "EIHLogisticResult",
    "generate_eih_logistic_report",
    "SubgroupAnalyzer",
    "SubgroupResult",
    "generate_subgroup_report",
]
