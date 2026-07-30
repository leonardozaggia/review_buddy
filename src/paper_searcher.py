"""
Main paper searcher - coordinates all search sources and provides unified interface.
"""

import logging
import re
from typing import List, Dict, Optional, Set
from datetime import datetime, date
from pathlib import Path

from .models import Paper, normalize_title, normalize_doi
from .config import Config
from .searchers.scopus_searcher import ScopusSearcher
from .searchers.pubmed_searcher import PubMedSearcher
from .searchers.arxiv_searcher import ArxivSearcher
from .searchers.ieee_searcher import IEEESearcher


logger = logging.getLogger(__name__)


# Scopus-only query syntax. Every source is sent the SAME query string, and
# only Scopus parses these. Nowhere else treats them as an error:
#   - PubMed turns TITLE-ABS-KEY into an ordinary search term and ANDs it in
#     ('"TITLE-ABS-KEY"[Title/Abstract] AND (...)'), so nothing matches and it
#     returns 0 with HTTP 200, no error and no warning.
#   - arXiv returns unrelated papers instead.
# Both outcomes are indistinguishable from "this database has nothing on your
# topic", which is why they need calling out before the search runs.
_SCOPUS_FIELD_CODES = ("TITLE(", "ABS(", "KEY(", "AUTH(", "AFFIL(",
                       "SRCTITLE(", "DOCTYPE(", "PUBYEAR")
_SCOPUS_PROXIMITY = re.compile(r"\b(?:W|PRE)/\d+\b", re.IGNORECASE)
_SHORT_WILDCARD = re.compile(r"\b\w{1,3}\*")

# Sources that receive the query verbatim and cannot parse Scopus syntax.
_NON_SCOPUS_SOURCES = ("pubmed", "arxiv", "scholar", "ieee")


def scopus_only_constructs(query: str) -> List[str]:
    """Return the Scopus-specific constructs found in `query`, if any."""
    found = []
    upper = query.upper()

    if "TITLE-ABS-KEY(" in upper:
        found.append("TITLE-ABS-KEY(...)")
        upper = upper.replace("TITLE-ABS-KEY(", " ")  # contains "KEY(" as a substring

    for code in _SCOPUS_FIELD_CODES:
        if code in upper:
            found.append(f"{code}...)" if code.endswith("(") else code)

    if _SCOPUS_PROXIMITY.search(query):
        found.append("proximity operator (W/n or PRE/n)")
    if _SHORT_WILDCARD.search(query):
        found.append("wildcard with under 4 leading characters (PubMed ignores these)")

    return found


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
        self.papers: Dict[str, Paper] = {}  # Deduplicated papers by normalized title
        self._doi_index: Dict[str, str] = {}  # normalized DOI -> title key
    
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
        self._doi_index = {}

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

        offenders = scopus_only_constructs(query)
        affected = [s for s in sources if str(s).lower() in _NON_SCOPUS_SOURCES]
        if offenders and affected:
            logger.warning(
                "Query contains Scopus-only syntax: %s. Scopus honours it, but %s "
                "receive the same string verbatim and will return 0 or unrelated results — "
                "neither API reports this as an error, so it looks like the database simply "
                "has nothing. For a multi-source search use plain boolean syntax: quoted "
                "phrases, AND / OR / NOT, and parentheses.",
                ", ".join(offenders), " and ".join(affected),
            )

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
        
        papers_list = list(self.papers.values())

        # Enforce year filter robustly across all sources (post-hoc safety net)
        if year_from or year_to:
            filtered = []
            filtered_out_count = 0
            no_date_count = 0
            
            for p in papers_list:
                pd = getattr(p, "publication_date", None)
                if pd and isinstance(pd, date):
                    y = pd.year
                    if year_from and y < year_from:
                        logger.debug(f"Post-filter: Removed (too old): {y} < {year_from} | {p.title[:80]}")
                        filtered_out_count += 1
                        continue
                    if year_to and y > year_to:
                        logger.debug(f"Post-filter: Removed (too new): {y} > {year_to} | {p.title[:80]}")
                        filtered_out_count += 1
                        continue
                    filtered.append(p)
                else:
                    # No parsed date: drop by default to make year filter strict.
                    logger.debug(f"Post-filter: Removed (no date): {p.title[:80]}")
                    no_date_count += 1
                    continue

            logger.info(f"Post-filter year validation: {len(filtered)} papers in range {year_from or 'any'} to {year_to or 'any'}")
            if filtered_out_count > 0:
                logger.info(f"Post-filter: Removed {filtered_out_count} papers outside year range")
            if no_date_count > 0:
                logger.info(f"Post-filter: Removed {no_date_count} papers with no publication date")
            papers_list = filtered
        else:
            logger.info(f"No year filtering applied")

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
                timeout=self.config.timeout,
                field=getattr(self.config, "pubmed_field", "tiab"),
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
                timeout=self.config.timeout,
                overall_timeout=45,  # hard cap: Google Scholar hangs when blocked
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

        Duplicate detection:
        1. Same DOI (normalized) - catches same paper with differing titles
        2. Same normalized title (punctuation/case-insensitive) - catches e.g.
           PubMed's trailing period vs Scopus's bare title

        Merge priority:
        1. Prefer PubMed papers (higher download success rate)
        2. If neither or both are PubMed, prefer more recent publication
        3. Merge missing fields from other paper

        Args:
            papers: List of papers to add
        """
        for paper in papers:
            key = self._find_existing_key(paper)

            if key is not None:
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

                # Surviving paper may have gained a DOI through the merge
                self._register_doi(key, self.papers[key])
            else:
                # Add new paper
                key = normalize_title(paper.title)
                self.papers[key] = paper
                self._register_doi(key, paper)

    def _find_existing_key(self, paper: Paper) -> Optional[str]:
        """Find the key of an already-stored duplicate of this paper, if any."""
        if paper.doi:
            doi = normalize_doi(paper.doi)
            if doi in self._doi_index:
                return self._doi_index[doi]

        key = normalize_title(paper.title)
        if key in self.papers:
            return key

        return None

    def _register_doi(self, key: str, paper: Paper):
        """Register a paper's DOI in the DOI index."""
        if paper.doi:
            self._doi_index[normalize_doi(paper.doi)] = key
    
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
