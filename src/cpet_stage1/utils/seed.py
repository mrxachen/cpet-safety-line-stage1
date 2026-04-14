"""
seed.py — Global random seed management for reproducibility.
"""

from __future__ import annotations

import os
import random

import numpy as np


def set_global_seed(seed: int | None = None) -> int:
    """Set random seed for Python, NumPy. Returns the seed used."""
    if seed is None:
        seed = int(os.environ.get("RANDOM_SEED", 42))
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
    except ImportError:
        pass
    return seed
