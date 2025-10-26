"""
AI-powered filter engine using LLM.
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from src.models import Paper
from src.ai_abstract_filter import AIAbstractFilter
from src.llm_client import OllamaClient
from .engines import FilterEngine
from .config_loader import AIFilterConfig


logger = logging.getLogger(__name__)


class AIFilterEngine(FilterEngine):
    """
    AI-powered filtering engine using local Ollama LLM.
    
    Uses natural language understanding to make nuanced filtering decisions.
    """
    
    def __init__(self, config: Optional[AIFilterConfig] = None):
        """
        Initialize AI filter engine.
        
        Args:
            config: AIFilterConfig with model, ollama_url, filters, etc.
        """
        self.config = config or AIFilterConfig()
        
        # Initialize Ollama client
        cache_dir = Path("results/ai_cache") if self.config.cache_responses else None
        
        try:
            self.llm_client = OllamaClient(
                model=self.config.model,
                base_url=self.config.ollama_url,
                temperature=self.config.temperature,
                cache_dir=cache_dir,
                retry_attempts=self.config.retry_attempts
            )
            logger.info(f"Initialized Ollama client with model: {self.config.model}")
        except Exception as e:
            logger.error(f"Failed to initialize Ollama client: {e}")
            raise
        
        # Initialize AI filter
        self.filter = AIAbstractFilter(
            llm_client=self.llm_client,
            confidence_threshold=self.config.confidence_threshold,
            log_decisions=True,
            log_dir=Path("results")
        )
    
    def get_engine_name(self) -> str:
        """Return engine name"""
        return "ai"
    
    def filter_records(self, papers: List[Paper]) -> Dict[str, Any]:
        """
        Filter papers using AI analysis.
        
        Args:
            papers: List of Paper objects to filter
        
        Returns:
            Dictionary with:
                - 'kept': List of papers that passed filters
                - 'filtered': Dict mapping filter names to filtered papers
                - 'summary': Dict with statistics
                - 'manual_review': List of papers needing manual review
        """
        logger.info(f"Starting AI filtering with {len(papers)} papers")
        logger.info(f"Model: {self.config.model}")
        logger.info(f"Confidence threshold: {self.config.confidence_threshold}")
        
        # Apply AI filters
        results = self.filter.apply_all_filters(papers, self.config.filters)
        
        # Results already in correct format
        return results
