"""
Background Engine - Modular Background Generation System

A flexible, component-based system for generating backgrounds with
configurable layout, spacing, and components.
"""

from .config import BackgroundConfig
from .layout import LayoutEngine, LayoutComponent, ComponentLayout
from .generators.unified import UnifiedBackgroundGenerator

__all__ = [
    'BackgroundConfig',
    'LayoutEngine', 
    'LayoutComponent',
    'ComponentLayout',
    'UnifiedBackgroundGenerator'
]