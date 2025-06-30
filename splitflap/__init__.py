"""
Splitflap Clock System for HSG Canvas
Provides real-time animated splitflap clock background
"""

from .digit import SplitflapDigit
from .clock import SplitflapClock
from .renderer import SplitflapRenderer

__all__ = ['SplitflapDigit', 'SplitflapClock', 'SplitflapRenderer']