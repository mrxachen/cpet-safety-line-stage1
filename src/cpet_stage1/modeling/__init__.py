"""modeling package — M5 模型训练、校准、评估、解释。"""

from cpet_stage1.modeling.calibrate import TemperatureScaler, calibrate_binary
from cpet_stage1.modeling.evaluate import EvaluationResult, ModelEvaluator
from cpet_stage1.modeling.interpret import InterpretResult, SHAPInterpreter
from cpet_stage1.modeling.train_p0 import P0ModelResult, P0Trainer
from cpet_stage1.modeling.train_p1 import P1ModelResult, P1Trainer

__all__ = [
    "TemperatureScaler",
    "calibrate_binary",
    "EvaluationResult",
    "ModelEvaluator",
    "InterpretResult",
    "SHAPInterpreter",
    "P0ModelResult",
    "P0Trainer",
    "P1ModelResult",
    "P1Trainer",
]
