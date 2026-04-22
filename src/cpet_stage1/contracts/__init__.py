"""contracts package — Schema 验证与数据契约模块。"""

from cpet_stage1.contracts.schema_validator import ValidationResult, validate_staging
from cpet_stage1.contracts.bridge_contract import BridgeContractValidator, BridgeContractResult

__all__ = [
    "validate_staging",
    "ValidationResult",
    "BridgeContractValidator",
    "BridgeContractResult",
]
