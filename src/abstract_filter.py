"""
Abstract-based filtering for papers.
Rule-based filters to exclude unwanted papers based on abstract content.
"""

import logging
from typing import List, Set
from .models import Paper


logger = logging.getLogger(__name__)


class AbstractFilter:
    """Filter papers based on abstract content and metadata"""
    
    # Keywords for identifying epileptic spike papers
    EPILEPSY_KEYWORDS = {
        'epileptic spike', 'epileptic spikes', 'interictal spike', 'ictal spike',
        'spike detection', 'epileptiform', 'seizure spike', 'spike-wave',
        'paroxysmal spike', 'sharp wave', 'spike discharge'
    }
    
    # Keywords for identifying BCI papers
    BCI_KEYWORDS = {
        'brain-computer interface', 'brain computer interface', 'bci',
        'brain-machine interface', 'brain machine interface', 'bmi',
        'neural interface', 'thought control', 'mind control',
        'p300 speller', 'motor imagery bci', 'steady-state visual'
    }
    
    # Keywords for identifying non-human studies
    NON_HUMAN_KEYWORDS = {
        # Animals
        'rat', 'rats', 'mouse', 'mice', 'murine', 'rodent', 'rodents',
        'monkey', 'monkeys', 'primate', 'primates', 'macaque', 'macaques',
        'pig', 'pigs', 'porcine', 'sheep', 'ovine', 'rabbit', 'rabbits',
        'cat', 'cats', 'feline', 'dog', 'dogs', 'canine',
        'zebrafish', 'drosophila', 'c. elegans', 'caenorhabditis',
        # Non-human contexts
        'in vitro', 'in-vitro', 'cell culture', 'cell line', 'cultured cells',
        'animal model', 'animal study', 'animal experiment',
        'non-human', 'non human', 'nonhuman'
    }
    
    # Keywords for identifying review papers
    REVIEW_KEYWORDS = {
        'systematic review', 'meta-analysis', 'meta analysis', 'literature review',
        'scoping review', 'narrative review', 'review article', 'state of the art',
        'state-of-the-art review', 'survey paper', 'comprehensive review'
    }
    
    # Indicators that a paper might be empirical (reduce false positives for reviews)
    EMPIRICAL_INDICATORS = {
        'participants', 'subjects', 'patients', 'cohort', 'sample size',
        'recruited', 'enrollment', 'n =', 'n=', 'dataset', 'data collection',
        'measured', 'recorded', 'assessed', 'evaluated', 'trial'
    }
    
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
        
        Args:
            papers: List of papers to filter
            exclude_keywords: Set of keywords to exclude (case-insensitive)
            filter_name: Name for logging purposes
        
        Returns:
            Tuple of (kept_papers, filtered_papers)
        """
        kept = []
        filtered = []
        
        for paper in papers:
            # Combine title and abstract for searching
            text = f"{paper.title} {paper.abstract or ''}".lower()
            
            # Check if any exclude keyword is present
            found_keywords = [kw for kw in exclude_keywords if kw.lower() in text]
            
            if found_keywords:
                filtered.append(paper)
                logger.debug(f"{filter_name} filter matched '{found_keywords[0]}': "
                           f"{paper.title[:50]}...")
            else:
                kept.append(paper)
        
        logger.info(f"{filter_name} filter: {len(kept)} papers kept, "
                   f"{len(filtered)} filtered out")
        
        return kept, filtered
    
    def filter_epilepsy(self, papers: List[Paper]) -> tuple[List[Paper], List[Paper]]:
        """
        Filter out papers related to epileptic spikes.
        
        Args:
            papers: List of papers to filter
        
        Returns:
            Tuple of (non_epilepsy_papers, epilepsy_papers)
        """
        return self.filter_by_keywords(papers, self.EPILEPSY_KEYWORDS, "Epilepsy")
    
    def filter_bci(self, papers: List[Paper]) -> tuple[List[Paper], List[Paper]]:
        """
        Filter out papers related to brain-computer interfaces.
        
        Args:
            papers: List of papers to filter
        
        Returns:
            Tuple of (non_bci_papers, bci_papers)
        """
        return self.filter_by_keywords(papers, self.BCI_KEYWORDS, "BCI")
    
    def filter_non_human(self, papers: List[Paper]) -> tuple[List[Paper], List[Paper]]:
        """
        Filter out papers with non-human participants.
        Uses keyword-based detection.
        
        Args:
            papers: List of papers to filter
        
        Returns:
            Tuple of (human_papers, non_human_papers)
        """
        return self.filter_by_keywords(papers, self.NON_HUMAN_KEYWORDS, "Non-human")
    
    def filter_non_empirical(self, papers: List[Paper]) -> tuple[List[Paper], List[Paper]]:
        """
        Filter out non-empirical papers (reviews, methods papers without data).
        Uses keyword-based detection with empirical indicators to reduce false positives.
        
        Args:
            papers: List of papers to filter
        
        Returns:
            Tuple of (empirical_papers, non_empirical_papers)
        """
        empirical = []
        non_empirical = []
        
        for paper in papers:
            text = f"{paper.title} {paper.abstract or ''}".lower()
            
            # Check for review keywords
            review_keywords = [kw for kw in self.REVIEW_KEYWORDS if kw.lower() in text]
            
            if review_keywords:
                # Found review keywords, but check for empirical indicators
                empirical_indicators = [kw for kw in self.EMPIRICAL_INDICATORS 
                                       if kw.lower() in text]
                
                if empirical_indicators:
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
                    logger.debug(f"Non-empirical filter matched '{review_keywords[0]}': "
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
            elif filter_name == 'epilepsy':
                current_papers, removed = self.filter_epilepsy(current_papers)
            elif filter_name == 'bci':
                current_papers, removed = self.filter_bci(current_papers)
            elif filter_name == 'non_human':
                current_papers, removed = self.filter_non_human(current_papers)
            elif filter_name == 'non_empirical':
                current_papers, removed = self.filter_non_empirical(current_papers)
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
