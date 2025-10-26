"""
Review Buddy - Core Module

Refactored core functionality for paper search, filtering, and downloading.
"""

__version__ = "2.0.0"

from .config_loader import PipelineConfig, load_config
from .engines import get_filter_engine, FilterEngine
from .io import load_papers, save_papers
from .filter_normal import NormalFilterEngine
from .filter_ai import AIFilterEngine

__all__ = [
    "PipelineConfig",
    "load_config",
    "get_filter_engine",
    "FilterEngine",
    "load_papers",
    "save_papers",
    "NormalFilterEngine",
    "AIFilterEngine",
]
