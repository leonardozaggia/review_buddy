"""
Review Buddy - Academic Paper Search and Download Tool
"""

__version__ = "1.0.0"

from .models import Paper
from .config import Config
from .paper_searcher import PaperSearcher

__all__ = ["Paper", "Config", "PaperSearcher"]