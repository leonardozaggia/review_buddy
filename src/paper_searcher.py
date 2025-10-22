"""
Main paper searcher - coordinates all search sources and provides unified interface.
"""

import logging
from typing import List, Dict, Optional, Set
from pathlib import Path

from .models import Paper
from .config import Config
from .searchers.scopus_searcher import ScopusSearcher
from .searchers.pubmed_searcher import PubMedSearcher
from .searchers.arxiv_searcher import ArxivSearcher
from .searchers.ieee_searcher import IEEESearcher


logger = logging.getLogger(__name__)


class PaperSearcher:
    """
    Main paper searcher that coordinates multiple sources.
    Simple, reliable, and comprehensive.
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the paper searcher.
        
        Args:
            config: Configuration object (creates default if None)
        """
        self.config = config or Config()
        self.papers: Dict[str, Paper] = {}  # Deduplicated papers by title
    
    def search_all(
        self,
        query: str,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        sources: Optional[List[str]] = None
    ) -> List[Paper]:
        """
        Search all available sources for papers.
        
        Args:
            query: Search query
            year_from: Start year filter
            year_to: End year filter
            sources: List of sources to search (None = all available)
                     Options: ['scopus', 'pubmed', 'scholar']
        
        Returns:
            Deduplicated list of Paper objects
        """
        self.papers = {}  # Reset
        
        # Determine which sources to use
        if sources is None:
            sources = []
            if self.config.has_scopus_access():
                sources.append('scopus')
            if self.config.has_pubmed_access():
                sources.append('pubmed')
            if self.config.has_arxiv_access():
                sources.append('arxiv')
            if self.config.has_scholar_access():
                sources.append('scholar')
            if self.config.has_ieee_access():
                sources.append('ieee')
        
        logger.info(f"Searching sources: {sources}")
        logger.info(f"Query: {query}")
        
        # Search each source
        if 'scopus' in sources and self.config.has_scopus_access():
            self._search_scopus(query, year_from, year_to)
        
        if 'pubmed' in sources and self.config.has_pubmed_access():
            self._search_pubmed(query, year_from, year_to)
        
        if 'arxiv' in sources and self.config.has_arxiv_access():
            self._search_arxiv(query, year_from, year_to)
        
        if 'scholar' in sources and self.config.has_scholar_access():
            self._search_scholar(query, year_from, year_to)
        
        if 'ieee' in sources and self.config.has_ieee_access():
            self._search_ieee(query, year_from, year_to)
        
        # Convert to list
        papers_list = list(self.papers.values())
        
        logger.info(f"\nTotal unique papers found: {len(papers_list)}")
        return papers_list
    
    def _search_scopus(self, query: str, year_from: Optional[int], year_to: Optional[int]):
        """Search Scopus and add results"""
        try:
            logger.info("\n" + "="*60)
            logger.info("Searching Scopus...")
            logger.info("="*60)
            
            searcher = ScopusSearcher(
                api_key=self.config.scopus_api_key,
                max_results=self.config.max_results_per_source,
                timeout=self.config.timeout
            )
            
            papers = searcher.search(query, year_from, year_to)
            self._add_papers(papers)
            
            logger.info(f"Scopus: Added {len(papers)} papers")
            
        except Exception as e:
            logger.error(f"Scopus search failed: {e}")
    
    def _search_pubmed(self, query: str, year_from: Optional[int], year_to: Optional[int]):
        """Search PubMed and add results"""
        try:
            logger.info("\n" + "="*60)
            logger.info("Searching PubMed...")
            logger.info("="*60)
            
            searcher = PubMedSearcher(
                email=self.config.pubmed_email,
                api_key=self.config.pubmed_api_key,
                max_results=self.config.max_results_per_source,
                timeout=self.config.timeout
            )
            
            papers = searcher.search(query, year_from, year_to)
            self._add_papers(papers)
            
            logger.info(f"PubMed: Added {len(papers)} papers")
            
        except Exception as e:
            logger.error(f"PubMed search failed: {e}")
    
    def _search_arxiv(self, query: str, year_from: Optional[int], year_to: Optional[int]):
        """Search arXiv and add results"""
        try:
            logger.info("\n" + "="*60)
            logger.info("Searching arXiv...")
            logger.info("="*60)
            
            searcher = ArxivSearcher(
                max_results=self.config.max_results_per_source,
                timeout=self.config.timeout
            )
            
            papers = searcher.search(query, year_from, year_to)
            self._add_papers(papers)
            
            logger.info(f"arXiv: Added {len(papers)} papers")
            
        except Exception as e:
            logger.error(f"arXiv search failed: {e}")
    
    def _search_scholar(self, query: str, year_from: Optional[int], year_to: Optional[int]):
        """Search Google Scholar and add results"""
        try:
            logger.info("\n" + "="*60)
            logger.info("Searching Google Scholar...")
            logger.info("="*60)
            
            # Lazy import to avoid requiring scholarly if not used
            from .searchers.scholar_searcher import ScholarSearcher
            
            searcher = ScholarSearcher(
                max_results=self.config.max_results_per_source,
                timeout=self.config.timeout
            )
            
            papers = searcher.search(query, year_from, year_to)
            self._add_papers(papers)
            
            logger.info(f"Google Scholar: Added {len(papers)} papers")
            
        except ImportError:
            logger.error("Google Scholar search requires 'scholarly' library. Install with: pip install scholarly")
        except Exception as e:
            logger.error(f"Google Scholar search failed: {e}")
    
    def _search_ieee(self, query: str, year_from: Optional[int], year_to: Optional[int]):
        """Search IEEE Xplore and add results"""
        try:
            logger.info("\n" + "="*60)
            logger.info("Searching IEEE Xplore...")
            logger.info("="*60)
            
            searcher = IEEESearcher(
                api_key=self.config.ieee_api_key,
                max_results=self.config.max_results_per_source,
                timeout=self.config.timeout
            )
            
            papers = searcher.search(query, year_from, year_to)
            self._add_papers(papers)
            
            logger.info(f"IEEE: Added {len(papers)} papers")
            
        except Exception as e:
            logger.error(f"IEEE search failed: {e}")
    
    def _add_papers(self, papers: List[Paper]):
        """
        Add papers to collection, deduplicating and merging data.
        
        Deduplication priority:
        1. Prefer PubMed papers (higher download success rate)
        2. If neither or both are PubMed, prefer more recent publication
        3. Merge missing fields from other paper
        
        Args:
            papers: List of papers to add
        """
        for paper in papers:
            key = paper.title.lower().strip()
            
            if key in self.papers:
                existing = self.papers[key]
                new = paper
                
                # Determine which paper to keep as primary
                should_replace = self._should_replace_paper(existing, new)
                
                if should_replace:
                    # Keep new paper as primary, merge existing data into it
                    new.merge_with(existing)
                    self.papers[key] = new
                else:
                    # Keep existing paper as primary, merge new data into it
                    existing.merge_with(new)
            else:
                # Add new paper
                self.papers[key] = paper
    
    def _should_replace_paper(self, existing: Paper, new: Paper) -> bool:
        """
        Determine if new paper should replace existing paper as the primary entry.
        
        Priority logic:
        1. PubMed papers are preferred (better download success)
        2. If PubMed status is the same, prefer more recent publication
        3. If dates are equal/unknown, keep existing
        
        Args:
            existing: Currently stored paper
            new: New paper being added
        
        Returns:
            True if new paper should replace existing, False otherwise
        """
        existing_is_pubmed = "PubMed" in existing.sources
        new_is_pubmed = "PubMed" in new.sources
        
        # Priority 1: Prefer PubMed
        if new_is_pubmed and not existing_is_pubmed:
            return True
        if existing_is_pubmed and not new_is_pubmed:
            return False
        
        # Priority 2: Prefer more recent publication
        if new.publication_date and existing.publication_date:
            return new.publication_date > existing.publication_date
        
        # If only one has a date, prefer the one with a date
        if new.publication_date and not existing.publication_date:
            return True
        if existing.publication_date and not new.publication_date:
            return False
        
        # Default: keep existing
        return False
    
    def generate_bibliography(
        self,
        papers: Optional[List[Paper]] = None,
        format: str = "bibtex",
        output_file: Optional[str] = None
    ) -> str:
        """
        Generate bibliography from papers.
        
        Args:
            papers: List of papers (uses all if None)
            format: Bibliography format ('bibtex' or 'ris')
            output_file: File to write to (optional)
        
        Returns:
            Bibliography string
        """
        if papers is None:
            papers = list(self.papers.values())
        
        if format.lower() == "bibtex":
            bib_text = self._generate_bibtex(papers)
        elif format.lower() == "ris":
            bib_text = self._generate_ris(papers)
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        # Write to file if specified
        if output_file:
            Path(output_file).write_text(bib_text, encoding='utf-8')
            logger.info(f"Bibliography written to: {output_file}")
        
        return bib_text
    
    def _generate_bibtex(self, papers: List[Paper]) -> str:
        """Generate BibTeX bibliography"""
        entries = []
        
        # Track cite keys to avoid duplicates
        used_keys: Set[str] = set()
        
        for paper in papers:
            # Generate unique cite key
            if paper.authors and paper.publication_date:
                base_key = f"{paper.authors[0].split()[-1]}_{paper.publication_date.year}"
            else:
                base_key = "Unknown"
            
            cite_key = base_key
            counter = 1
            while cite_key in used_keys:
                cite_key = f"{base_key}_{counter}"
                counter += 1
            
            used_keys.add(cite_key)
            entries.append(paper.to_bibtex_entry(cite_key))
        
        return "\n\n".join(entries)
    
    def _generate_ris(self, papers: List[Paper]) -> str:
        """Generate RIS bibliography"""
        entries = []
        
        for paper in papers:
            lines = ["TY  - JOUR"]  # Journal article
            
            if paper.title:
                lines.append(f"TI  - {paper.title}")
            
            for author in paper.authors:
                lines.append(f"AU  - {author}")
            
            if paper.journal:
                lines.append(f"JO  - {paper.journal}")
            
            if paper.publication_date:
                lines.append(f"PY  - {paper.publication_date.year}")
            
            if paper.volume:
                lines.append(f"VL  - {paper.volume}")
            
            if paper.issue:
                lines.append(f"IS  - {paper.issue}")
            
            if paper.pages:
                lines.append(f"SP  - {paper.pages}")
            
            if paper.doi:
                lines.append(f"DO  - {paper.doi}")
            
            if paper.abstract:
                lines.append(f"AB  - {paper.abstract}")
            
            if paper.url:
                lines.append(f"UR  - {paper.url}")
            
            lines.append("ER  - ")
            entries.append("\n".join(lines))
        
        return "\n\n".join(entries)
    
    def export_to_csv(self, papers: Optional[List[Paper]] = None, output_file: str = "papers.csv"):
        """
        Export papers to CSV format.
        
        Args:
            papers: List of papers (uses all if None)
            output_file: Output CSV file path
        """
        import csv
        
        if papers is None:
            papers = list(self.papers.values())
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'Title', 'Authors', 'Journal', 'Year', 'DOI', 'PMID',
                'Citations', 'URL', 'Sources', 'Keywords'
            ])
            
            # Data
            for paper in papers:
                writer.writerow([
                    paper.title,
                    '; '.join(paper.authors),
                    paper.journal or '',
                    paper.publication_date.year if paper.publication_date else '',
                    paper.doi or '',
                    paper.pmid or '',
                    paper.citations or '',
                    paper.url or '',
                    ', '.join(paper.sources),
                    '; '.join(paper.keywords)
                ])
        
        logger.info(f"Papers exported to: {output_file}")
