"""
Base filter engine interface and factory.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
import logging

from src.models import Paper


logger = logging.getLogger(__name__)


class FilterEngine(ABC):
    """
    Abstract base class for filter engines.
    
    All filter engines must implement filter_records() with the same signature.
    """
    
    @abstractmethod
    def filter_records(self, papers: List[Paper]) -> Dict[str, Any]:
        """
        Filter papers and return results.
        
        Args:
            papers: List of Paper objects to filter
        
        Returns:
            Dictionary with:
                - 'kept': List of papers that passed filters
                - 'filtered': Dict mapping filter names to filtered papers
                - 'summary': Dict with statistics
                - 'manual_review': List of papers needing manual review (optional)
        """
        pass
    
    @abstractmethod
    def get_engine_name(self) -> str:
        """Return the name of this engine"""
        pass


def get_filter_engine(engine_type: str, config: Any = None) -> FilterEngine:
    """
    Factory function to get the appropriate filter engine.
    
    Args:
        engine_type: 'normal' or 'ai'
        config: Configuration object (NormalFilterConfig or AIFilterConfig)
    
    Returns:
        FilterEngine instance
    
    Raises:
        ValueError: If engine_type is not recognized
    """
    if engine_type == "normal":
        from .filter_normal import NormalFilterEngine
        return NormalFilterEngine(config)
    elif engine_type == "ai":
        from .filter_ai import AIFilterEngine
        return AIFilterEngine(config)
    else:
        raise ValueError(f"Unknown engine type: {engine_type}. Must be 'normal' or 'ai'")
