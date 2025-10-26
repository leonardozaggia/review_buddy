"""
Normal (keyword-based) filter engine.
"""

import logging
from typing import List, Dict, Any, Optional

from src.models import Paper
from src.abstract_filter import AbstractFilter
from .engines import FilterEngine
from .config_loader import NormalFilterConfig


logger = logging.getLogger(__name__)


class NormalFilterEngine(FilterEngine):
    """
    Keyword-based filtering engine.
    
    Uses rule-based filters to exclude papers based on keywords in title/abstract.
    """
    
    def __init__(self, config: Optional[NormalFilterConfig] = None):
        """
        Initialize normal filter engine.
        
        Args:
            config: NormalFilterConfig with enabled_filters and keywords
        """
        self.config = config or NormalFilterConfig()
        self.filter = AbstractFilter()
        
        # Register custom keyword filters
        for filter_name, keywords in self.config.keywords.items():
            self.filter.add_custom_filter(filter_name, keywords)
            logger.info(f"Registered filter '{filter_name}' with {len(keywords)} keywords")
    
    def get_engine_name(self) -> str:
        """Return engine name"""
        return "normal"
    
    def filter_records(self, papers: List[Paper]) -> Dict[str, Any]:
        """
        Filter papers using keyword-based rules.
        
        Args:
            papers: List of Paper objects to filter
        
        Returns:
            Dictionary with:
                - 'kept': List of papers that passed filters
                - 'filtered': Dict mapping filter names to filtered papers
                - 'summary': Dict with statistics
        """
        logger.info(f"Starting normal filtering with {len(papers)} papers")
        logger.info(f"Filters to apply: {', '.join(self.config.enabled_filters)}")
        
        # Apply filters
        results = self.filter.apply_all_filters(
            papers, 
            filters_to_apply=self.config.enabled_filters
        )
        
        # Results already in correct format
        return results


def create_default_keywords() -> Dict[str, List[str]]:
    """
    Create default keyword filters.
    
    Returns:
        Dictionary mapping filter names to keyword lists
    """
    return {
        'epilepsy': [
            'epileptic spike', 'epileptic spikes', 'interictal spike', 'ictal spike',
            'spike detection', 'epileptiform', 'seizure spike', 'spike-wave',
            'paroxysmal spike', 'sharp wave', 'spike discharge'
        ],
        'bci': [
            'brain-computer interface', 'brain computer interface', 'bci',
            'brain-machine interface', 'brain machine interface', 'bmi',
            'neural interface', 'thought control', 'mind control',
            'p300 speller', 'motor imagery bci', 'steady-state visual'
        ],
        'non_human': [
            'rat', 'rats', 'mouse', 'mice', 'murine', 'rodent', 'rodents',
            'monkey', 'monkeys', 'primate', 'primates', 'macaque', 'macaques',
            'pig', 'pigs', 'porcine', 'sheep', 'ovine', 'rabbit', 'rabbits',
            'cat', 'cats', 'feline', 'dog', 'dogs', 'canine',
            'zebrafish', 'drosophila', 'c. elegans', 'caenorhabditis',
            'in vitro', 'in-vitro', 'cell culture', 'cell line', 'cultured cells',
            'animal model', 'animal study', 'animal experiment',
            'non-human', 'non human', 'nonhuman'
        ],
        'non_empirical': [
            'systematic review', 'meta-analysis', 'meta analysis', 'literature review',
            'scoping review', 'narrative review', 'review article', 'state of the art',
            'state-of-the-art review', 'survey paper', 'comprehensive review'
        ],
    }
