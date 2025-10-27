"""
AI-powered abstract filtering for papers.

Uses LLM to analyze abstracts and make filtering decisions based on
natural language understanding rather than keyword matching.
"""

import logging
from typing import List, Dict, Set
from pathlib import Path
import json
from datetime import datetime

from .models import Paper
from .llm_client import OllamaClient


logger = logging.getLogger(__name__)


class AIAbstractFilter:
    """
    AI-powered filter for papers based on abstract content.
    
    Uses LLM to understand context and make nuanced filtering decisions.
    Papers flagged for manual review are kept but marked separately.
    """
    
    def __init__(
        self, 
        llm_client: OllamaClient,
        confidence_threshold: float = 0.5,
        log_decisions: bool = True,
        log_dir: Path = None
    ):
        """
        Initialize AI-powered filter.
        
        Args:
            llm_client: Ollama client for local model inference
            confidence_threshold: Minimum confidence for filtering (0.0-1.0)
            log_decisions: Whether to log all decisions to JSON
            log_dir: Directory for decision logs (default: results/)
        """
        self.llm_client = llm_client
        self.confidence_threshold = confidence_threshold
        self.log_decisions = log_decisions
        self.log_dir = log_dir or Path("results")
        
        # Storage for detailed decisions
        self.decision_log = []
        
        # Stats tracking
        self.papers_processed = 0
        self.papers_flagged_manual_review = 0
        
        logger.info(f"AI filter initialized with confidence threshold: {confidence_threshold}")
    
    def filter_no_abstract(self, papers: List[Paper]) -> tuple[List[Paper], List[Paper]]:
        """
        Filter out papers without abstracts.
        Same as keyword-based version - no AI needed.
        
        Args:
            papers: List of papers to filter
        
        Returns:
            Tuple of (papers_with_abstract, papers_without_abstract)
        """
        with_abstract = []
        without_abstract = []
        
        for paper in papers:
            if paper.abstract and paper.abstract.strip():
                with_abstract.append(paper)
            else:
                without_abstract.append(paper)
        
        logger.info(f"Abstract filter: {len(with_abstract)} papers with abstract, "
                   f"{len(without_abstract)} without")
        
        return with_abstract, without_abstract
    
    def filter_by_ai(
        self, 
        papers: List[Paper], 
        filters_config: Dict[str, Dict]
    ) -> Dict:
        """
        Apply AI-based filtering to papers.
        
        Args:
            papers: List of papers to filter
            filters_config: Dict mapping filter names to config dicts with 'prompt'
        
        Returns:
            Dict with:
                - 'kept': List of papers that passed all filters
                - 'filtered': Dict mapping filter names to filtered papers
                - 'manual_review': List of papers flagged for manual review
                - 'decisions': List of detailed decision records
        """
        # Prepare filter questions
        filter_questions = {
            name: config['prompt'] 
            for name, config in filters_config.items()
        }
        
        kept_papers = []
        filtered_papers = {name: [] for name in filter_questions.keys()}
        manual_review_papers = []
        
        # Track which papers we've already added to manual review
        papers_needing_manual_review = set()
        
        logger.info(f"\nProcessing {len(papers)} papers with AI filters...")
        logger.info(f"Filters: {', '.join(filter_questions.keys())}")
        
        for i, paper in enumerate(papers, 1):
            if i % 10 == 0:
                logger.info(f"Progress: {i}/{len(papers)} papers processed")
            
            # Skip papers without abstracts
            if not paper.abstract or not paper.abstract.strip():
                kept_papers.append(paper)
                logger.debug(f"Skipping AI filter (no abstract): {paper.title[:50]}")
                continue
            
            # Call LLM to check all filters
            result = self.llm_client.check_paper(paper, filter_questions)
            
            self.papers_processed += 1
            
            # Check if API failed
            if not result['success']:
                # API failure - keep but flag for manual review
                kept_papers.append(paper)
                if id(paper) not in papers_needing_manual_review:
                    manual_review_papers.append(paper)
                    papers_needing_manual_review.add(id(paper))
                    self.papers_flagged_manual_review += 1
                logger.warning(f"API failure, manual review needed: {paper.title[:50]}")
                continue  # Skip to next paper
            
            # Check each filter
            should_filter = False
            filter_reasons = []
            needs_manual_review = result['manual_review']
            
            for filter_name, filter_result in result['filters'].items():
                if filter_result['should_filter']:
                    confidence = filter_result['confidence']
                    
                    # Only filter if confidence meets threshold
                    if confidence >= self.confidence_threshold:
                        filtered_papers[filter_name].append(paper)
                        should_filter = True
                        filter_reasons.append({
                            'filter': filter_name,
                            'confidence': confidence,
                            'reason': filter_result['reason']
                        })
                        logger.debug(f"Filtered by {filter_name} (conf={confidence:.2f}): "
                                   f"{paper.title[:50]}")
                    else:
                        # Low confidence - flag for manual review
                        needs_manual_review = True
                        logger.info(f"Low confidence for {filter_name} (conf={confidence:.2f}), "
                                  f"flagging for review: {paper.title[:50]}")
            
            # Keep paper if not filtered by any filter
            if not should_filter:
                kept_papers.append(paper)
                
                # Add to manual review if flagged (only once per paper)
                if needs_manual_review and id(paper) not in papers_needing_manual_review:
                    manual_review_papers.append(paper)
                    papers_needing_manual_review.add(id(paper))
                    self.papers_flagged_manual_review += 1
            
            # Log decision
            decision = {
                'title': paper.title,
                'doi': paper.doi,
                'filtered': should_filter,
                'filter_reasons': filter_reasons,
                'manual_review': needs_manual_review,
                'api_success': result['success'],
                'all_filter_results': result['filters']
            }
            
            self.decision_log.append(decision)
        
        logger.info(f"\nAI filtering complete:")
        logger.info(f"  Papers processed: {self.papers_processed}")
        logger.info(f"  Papers kept: {len(kept_papers)}")
        logger.info(f"  Papers flagged for manual review: {len(manual_review_papers)}")
        
        return {
            'kept': kept_papers,
            'filtered': filtered_papers,
            'manual_review': manual_review_papers,
            'decisions': self.decision_log
        }
    
    def apply_all_filters(
        self,
        papers: List[Paper],
        filters_config: Dict[str, Dict]
    ) -> Dict:
        """
        Apply all AI filters to papers.
        
        Args:
            papers: List of papers to filter
            filters_config: Dict mapping filter names to config with 'enabled' and 'prompt'
        
        Returns:
            Dictionary with:
                - 'kept': List of papers that passed all filters
                - 'filtered': Dictionary mapping filter names to filtered papers
                - 'manual_review': List of papers flagged for manual review
                - 'summary': Dictionary with counts
                - 'decisions': Detailed decision log
        """
        logger.info(f"Starting AI filtering with {len(papers)} papers")
        
        # First filter out papers without abstracts
        current_papers, no_abstract = self.filter_no_abstract(papers)
        
        # Get enabled filters only
        enabled_filters = {
            name: config 
            for name, config in filters_config.items() 
            if config.get('enabled', True)
        }
        
        if not enabled_filters:
            logger.warning("No AI filters enabled!")
            return {
                'kept': current_papers,
                'filtered': {'no_abstract': no_abstract},
                'manual_review': [],
                'summary': {
                    'initial_count': len(papers),
                    'final_count': len(current_papers),
                    'total_filtered': len(no_abstract),
                    'manual_review_count': 0,
                    'filtered_by_category': {'no_abstract': len(no_abstract)}
                },
                'decisions': []
            }
        
        # Apply AI filters
        ai_results = self.filter_by_ai(current_papers, enabled_filters)
        
        # Combine results
        all_filtered = {'no_abstract': no_abstract}
        all_filtered.update(ai_results['filtered'])
        
        # Remove duplicates from filtered counts
        unique_filtered_count = len(papers) - len(ai_results['kept'])
        
        # Create summary
        summary = {
            'initial_count': len(papers),
            'final_count': len(ai_results['kept']),
            'total_filtered': unique_filtered_count,
            'manual_review_count': len(ai_results['manual_review']),
            'filtered_by_category': {
                name: len(papers_list) 
                for name, papers_list in all_filtered.items()
            },
            'api_stats': self.llm_client.get_usage_stats()
        }
        
        # Save decision log if enabled
        if self.log_decisions:
            self._save_decision_log(ai_results['decisions'], summary)
        
        logger.info(f"\nFiltering complete: {len(ai_results['kept'])}/{len(papers)} papers kept "
                   f"({unique_filtered_count} filtered)")
        
        return {
            'kept': ai_results['kept'],
            'filtered': all_filtered,
            'manual_review': ai_results['manual_review'],
            'summary': summary,
            'decisions': ai_results['decisions']
        }
    
    def _save_decision_log(self, decisions: List[Dict], summary: Dict):
        """Save detailed decision log to JSON file."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.log_dir / f"ai_filtering_log_{timestamp}.json"
        
        log_data = {
            'timestamp': timestamp,
            'summary': summary,
            'decisions': decisions
        }
        
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Decision log saved to: {log_file}")
        except Exception as e:
            logger.error(f"Failed to save decision log: {e}")
