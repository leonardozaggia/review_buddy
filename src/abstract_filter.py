"""
Abstract-based filtering for papers.
Rule-based filters to exclude unwanted papers based on abstract content.
"""

import logging
from typing import List, Set
from .models import Paper


logger = logging.getLogger(__name__)


class AbstractFilter:
    """
    Generic filter for papers based on abstract content and metadata.
    
    This class provides generic filtering capabilities. Domain-specific filters
    (epilepsy, BCI, etc.) should be defined as custom filters in the main script.
    """
    
    def __init__(self):
        """Initialize the filter"""
        self.langdetect_available = False
        try:
            import langdetect
            self.langdetect = langdetect
            self.langdetect_available = True
            logger.info("Language detection enabled")
        except ImportError:
            logger.warning("langdetect not installed - language filtering will be skipped")
        
        # Dictionary to store custom filters
        self.custom_filters = {}
        
        # Store empirical indicators for non_empirical filter
        self.empirical_indicators = {
            'participants', 'subjects', 'patients', 'cohort', 'sample size',
            'recruited', 'enrollment', 'n =', 'n=', 'dataset', 'data collection',
            'measured', 'recorded', 'assessed', 'evaluated', 'trial'
        }
    
    
    def add_custom_filter(self, filter_name: str, keywords: List[str]):
        """
        Add a custom keyword-based filter.
        
        Args:
            filter_name: Name for the custom filter
            keywords: List of keywords to filter out
        """
        self.custom_filters[filter_name] = set(keywords)
    
    def filter_no_abstract(self, papers: List[Paper]) -> tuple[List[Paper], List[Paper]]:
        """
        Filter out papers without abstracts.
        
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
    
    def filter_non_english(self, papers: List[Paper]) -> tuple[List[Paper], List[Paper]]:
        """
        Filter out non-English papers using language detection.
        
        Args:
            papers: List of papers to filter
        
        Returns:
            Tuple of (english_papers, non_english_papers)
        """
        if not self.langdetect_available:
            logger.warning("Skipping language filter - langdetect not available")
            return papers, []
        
        english = []
        non_english = []
        
        for paper in papers:
            # Need abstract or title for language detection
            text = paper.abstract if paper.abstract else paper.title
            
            if not text or not text.strip():
                # No text to detect, assume English (will be filtered by no_abstract)
                english.append(paper)
                continue
            
            try:
                # Detect language
                lang = self.langdetect.detect(text)
                
                if lang == 'en':
                    english.append(paper)
                else:
                    non_english.append(paper)
                    logger.debug(f"Non-English ({lang}): {paper.title[:50]}...")
                    
            except Exception as e:
                # If detection fails, assume English
                logger.debug(f"Language detection failed for: {paper.title[:50]}... - {e}")
                english.append(paper)
        
        logger.info(f"Language filter: {len(english)} English papers, "
                   f"{len(non_english)} non-English")
        
        return english, non_english
    
    def filter_by_keywords(
        self, 
        papers: List[Paper], 
        exclude_keywords: Set[str],
        filter_name: str = "keyword"
    ) -> tuple[List[Paper], List[Paper]]:
        """
        Filter out papers containing specific keywords in title or abstract.
        Uses whole-word matching to avoid false positives from substrings.
        
        Args:
            papers: List of papers to filter
            exclude_keywords: Set of keywords to exclude (case-insensitive)
            filter_name: Name for logging purposes
        
        Returns:
            Tuple of (kept_papers, filtered_papers)
        """
        import re
        
        kept = []
        filtered = []
        
        for paper in papers:
            # Combine title and abstract for searching
            text = f"{paper.title} {paper.abstract or ''}".lower()
            
            # Check if any exclude keyword is present (using word boundaries)
            found_keywords = []
            for kw in exclude_keywords:
                kw_lower = kw.lower()
                # Use word boundaries to match whole words only
                # This prevents "rodent" from matching in "corrected for"
                pattern = r'\b' + re.escape(kw_lower) + r'\b'
                if re.search(pattern, text):
                    found_keywords.append(kw)
                    break  # Only need to find one match
            
            if found_keywords:
                filtered.append(paper)
                logger.debug(f"{filter_name} filter matched '{found_keywords[0]}': "
                           f"{paper.title[:50]}...")
            else:
                kept.append(paper)
        
        logger.info(f"{filter_name} filter: {len(kept)} papers kept, "
                   f"{len(filtered)} filtered out")
        
        return kept, filtered
    
    def filter_non_empirical(self, papers: List[Paper], review_keywords: Set[str]) -> tuple[List[Paper], List[Paper]]:
        """
        Filter out non-empirical papers (reviews, methods papers without data).
        Uses keyword-based detection with empirical indicators to reduce false positives.
        Uses whole-word matching to avoid false positives from substrings.
        
        Args:
            papers: List of papers to filter
            review_keywords: Set of keywords that identify review papers
        
        Returns:
            Tuple of (empirical_papers, non_empirical_papers)
        """
        import re
        
        empirical = []
        non_empirical = []
        
        for paper in papers:
            text = f"{paper.title} {paper.abstract or ''}".lower()
            
            # Check for review keywords using word boundaries
            found_review_keywords = []
            for kw in review_keywords:
                kw_lower = kw.lower()
                pattern = r'\b' + re.escape(kw_lower) + r'\b'
                if re.search(pattern, text):
                    found_review_keywords.append(kw)
                    break
            
            if found_review_keywords:
                # Found review keywords, but check for empirical indicators
                empirical_indicators_found = []
                for kw in self.empirical_indicators:
                    kw_lower = kw.lower()
                    pattern = r'\b' + re.escape(kw_lower) + r'\b'
                    if re.search(pattern, text):
                        empirical_indicators_found.append(kw)
                        break
                
                if empirical_indicators_found:
                    # Has both review keywords and empirical indicators
                    # This might be a systematic review WITH meta-analysis of data
                    # Or a methods paper WITH validation
                    # Keep it for now (conservative approach)
                    empirical.append(paper)
                    logger.debug(f"Non-empirical filter: Kept despite review keywords "
                               f"(has empirical indicators): {paper.title[:50]}...")
                else:
                    # Pure review/methods paper
                    non_empirical.append(paper)
                    logger.debug(f"Non-empirical filter matched '{found_review_keywords[0]}': "
                               f"{paper.title[:50]}...")
            else:
                empirical.append(paper)
        
        logger.info(f"Non-empirical filter: {len(empirical)} empirical papers, "
                   f"{len(non_empirical)} non-empirical")
        
        return empirical, non_empirical
    
    def apply_all_filters(
        self,
        papers: List[Paper],
        filters_to_apply: List[str] = None
    ) -> dict:
        """
        Apply all or selected filters to papers.
        
        Args:
            papers: List of papers to filter
            filters_to_apply: List of filter names to apply. If None, applies all.
                             Options: 'no_abstract', 'non_english', 'epilepsy', 'bci',
                                     'non_human', 'non_empirical'
        
        Returns:
            Dictionary with:
                - 'kept': List of papers that passed all filters
                - 'filtered': Dictionary mapping filter names to filtered papers
                - 'summary': Dictionary with counts
        """
        if filters_to_apply is None:
            filters_to_apply = [
                'no_abstract', 'non_english', 'epilepsy', 'bci', 
                'non_human', 'non_empirical'
            ]
        
        current_papers = papers
        filtered_papers = {}
        
        logger.info(f"Starting with {len(current_papers)} papers")
        
        # Apply filters in sequence
        for filter_name in filters_to_apply:
            if filter_name == 'no_abstract':
                current_papers, removed = self.filter_no_abstract(current_papers)
            elif filter_name == 'non_english':
                current_papers, removed = self.filter_non_english(current_papers)
            elif filter_name == 'non_empirical':
                # Non-empirical filter requires review keywords
                if 'non_empirical' in self.custom_filters:
                    current_papers, removed = self.filter_non_empirical(
                        current_papers, 
                        self.custom_filters['non_empirical']
                    )
                else:
                    logger.warning("Non-empirical filter requested but keywords not provided")
                    removed = []
            elif filter_name in self.custom_filters:
                # Apply custom filter
                current_papers, removed = self.filter_by_keywords(
                    current_papers, 
                    self.custom_filters[filter_name], 
                    f"Custom: {filter_name}"
                )
            else:
                logger.warning(f"Unknown filter: {filter_name}")
                continue
            
            filtered_papers[filter_name] = removed
        
        # Create summary
        summary = {
            'initial_count': len(papers),
            'final_count': len(current_papers),
            'total_filtered': len(papers) - len(current_papers),
            'filtered_by_category': {
                name: len(papers) for name, papers in filtered_papers.items()
            }
        }
        
        logger.info(f"Filtering complete: {len(current_papers)}/{len(papers)} papers kept "
                   f"({summary['total_filtered']} filtered)")
        
        return {
            'kept': current_papers,
            'filtered': filtered_papers,
            'summary': summary
        }
