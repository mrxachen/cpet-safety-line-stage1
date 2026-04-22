"""
calibrate.py — M5 模型校准模块。

提供两种校准方法：
1. Isotonic 回归校准（IsotonicBinaryCalibrator，prefit 模式）— P0 二分类
2. Temperature Scaling（单标量 T）— P1 多分类

设计：
- calibrate_binary: 使用 IsotonicRegression / sigmoid 对已训练模型做校准
- TemperatureScaler: 自实现温度缩放，fit 学习最优 T，transform 输出校准后概率

注意：sklearn 1.8+ 移除了 CalibratedClassifierCV(cv="prefit")，
      本模块改用手动实现的 IsotonicBinaryCalibrator。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger(__name__)


class IsotonicBinaryCalibrator:
    """
    二分类 Isotonic Regression 校准器（手动 prefit 实现）。

    将已训练模型的预测概率进行 isotonic 校准。
    兼容 sklearn 1.8+（避免已弃用的 cv="prefit"）。

    提供 predict_proba / predict 接口（sklearn 兼容）。
    """

    def __init__(self, base_model: Any, method: str = "isotonic") -> None:
        self.base_model = base_model
        self.method = method
        self._calibrator: Optional[Any] = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "IsotonicBinaryCalibrator":
        """在校准集上 fit 校准器。"""
        proba = self.base_model.predict_proba(X)[:, 1]
        if self.method == "isotonic":
            self._calibrator = IsotonicRegression(out_of_bounds="clip")
            self._calibrator.fit(proba.reshape(-1, 1).ravel(), y)
        elif self.method == "sigmoid":
            # Platt scaling（logistic 回归在预测概率上）
            self._calibrator = LogisticRegression(C=1e5, max_iter=500)
            self._calibrator.fit(proba.reshape(-1, 1), y)
        else:
            raise ValueError(f"未知校准方法: {self.method}")
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """返回校准后概率 (n, 2)。"""
        proba = self.base_model.predict_proba(X)[:, 1]
        if self._calibrator is None:
            cal_proba = proba
        elif self.method == "isotonic":
            cal_proba = self._calibrator.predict(proba)
        else:  # sigmoid
            cal_proba = self._calibrator.predict_proba(proba.reshape(-1, 1))[:, 1]
        return np.column_stack([1 - cal_proba, cal_proba])

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.argmax(self.predict_proba(X), axis=1)


def calibrate_binary(
    model: Any,
    X_cal: np.ndarray,
    y_cal: np.ndarray,
    method: str = "isotonic",
) -> IsotonicBinaryCalibrator:
    """
    对二分类模型做 isotonic/sigmoid 校准。

    参数：
        model: 已训练的分类器（需有 predict_proba）
        X_cal: 校准集特征
        y_cal: 校准集标签（0/1）
        method: "isotonic" 或 "sigmoid"

    返回：
        IsotonicBinaryCalibrator 实例（已 fit）
    """
    cal_model = IsotonicBinaryCalibrator(base_model=model, method=method)
    cal_model.fit(X_cal, y_cal)
    logger.info("calibrate_binary [%s]: 校准完成，校准集大小=%d", method, len(y_cal))
    return cal_model


class TemperatureScaler:
    """
    温度缩放（Temperature Scaling）校准器。

    用于多分类模型（P1: 3 类）的概率校准。
    学习单标量 T，使得 softmax(logits/T) 最小化 NLL（负对数似然）。

    在 logits 不可用时（如 sklearn 树模型），直接对概率做 softmax(log(p)/T) 变换。

    使用方法：
        ts = TemperatureScaler()
        ts.fit(proba_cal, y_cal)       # proba: (n, n_classes)
        proba_cal_cal = ts.transform(proba_test)
    """

    def __init__(
        self,
        bounds: tuple[float, float] = (0.1, 10.0),
        n_classes: int = 3,
    ) -> None:
        self._bounds = bounds
        self._n_classes = n_classes
        self.temperature_: Optional[float] = None

    def fit(self, proba: np.ndarray, y: np.ndarray) -> "TemperatureScaler":
        """
        在校准集上学习最优温度 T。

        参数：
            proba: 模型输出概率矩阵 (n, n_classes)
            y: 真实标签 (n,)，整数 0..n_classes-1

        返回：
            self
        """
        proba = np.clip(proba, 1e-10, 1.0)
        logits = np.log(proba)  # 对数概率作为伪 logits

        def nll(t: float) -> float:
            """计算给定温度 T 下的负对数似然。"""
            scaled_logits = logits / t
            # 数值稳定 softmax
            shifted = scaled_logits - scaled_logits.max(axis=1, keepdims=True)
            log_proba = shifted - np.log(np.exp(shifted).sum(axis=1, keepdims=True))
            return -log_proba[np.arange(len(y)), y.astype(int)].mean()

        result = minimize_scalar(nll, bounds=self._bounds, method="bounded")
        self.temperature_ = float(result.x)
        logger.info(
            "TemperatureScaler: 最优 T=%.4f, NLL 改善=%.4f→%.4f",
            self.temperature_,
            nll(1.0),
            result.fun,
        )
        return self

    def transform(self, proba: np.ndarray) -> np.ndarray:
        """
        用拟合的温度 T 对概率做缩放。

        参数：
            proba: 模型输出概率 (n, n_classes)

        返回：
            校准后概率 (n, n_classes)
        """
        if self.temperature_ is None:
            raise RuntimeError("TemperatureScaler 尚未 fit，请先调用 fit()")
        proba = np.clip(proba, 1e-10, 1.0)
        logits = np.log(proba) / self.temperature_
        shifted = logits - logits.max(axis=1, keepdims=True)
        exp_logits = np.exp(shifted)
        return exp_logits / exp_logits.sum(axis=1, keepdims=True)

    def fit_transform(self, proba: np.ndarray, y: np.ndarray) -> np.ndarray:
        """在校准集上 fit 并立即 transform。"""
        return self.fit(proba, y).transform(proba)
