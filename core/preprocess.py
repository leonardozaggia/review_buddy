"""
Preprocessing utilities (currently minimal, placeholder for future features).
"""

import logging
from typing import List

from src.models import Paper


logger = logging.getLogger(__name__)


def preprocess_papers(papers: List[Paper]) -> List[Paper]:
    """
    Preprocess papers before filtering.
    
    Currently minimal - placeholder for future features like:
    - Text cleaning/normalization
    - Deduplication
    - Metadata enrichment
    
    Args:
        papers: List of Paper objects
    
    Returns:
        Preprocessed papers
    """
    logger.info(f"Preprocessing {len(papers)} papers")
    
    # Currently just pass through
    # Future: add text normalization, deduplication, etc.
    
    return papers
