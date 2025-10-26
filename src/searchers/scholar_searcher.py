"""
Google Scholar searcher - Using scholarly library for academic paper search.
Note: Google Scholar doesn't have an official API, so this uses web scraping.
Be respectful with rate limits.
"""

import logging
from typing import List, Optional
from datetime import datetime
import time

from ..models import Paper


logger = logging.getLogger(__name__)


class ScholarSearcher:
    """Search for papers in Google Scholar"""
    
    def __init__(self, max_results: int = 1000, timeout: int = 30):
        """
        Initialize Google Scholar searcher.
        
        Args:
            max_results: Maximum number of results to fetch
            timeout: Request timeout in seconds
        """
        self.max_results = max_results
        self.timeout = timeout
        
        # Lazy import scholarly to avoid dependency if not used
        try:
            from scholarly import scholarly
            self.scholarly = scholarly
        except ImportError:
            raise ImportError(
                "scholarly library is required for Google Scholar search. "
                "Install with: pip install scholarly"
            )
    
    def search(self, query: str, year_from: Optional[int] = None, year_to: Optional[int] = None) -> List[Paper]:
        """
        Search Google Scholar for papers matching the query.
        
        Args:
            query: Search query
            year_from: Start year filter
            year_to: End year filter
        
        Returns:
            List of Paper objects
        """
        papers = []
        
        # Normalize query - remove newlines and extra whitespace
        # This is crucial for queries read from .txt files
        normalized_query = ' '.join(query.split())
        
        # Build query with year filters
        scholar_query = normalized_query
        if year_from or year_to:
            year_from_str = str(year_from or 1900)
            year_to_str = str(year_to or datetime.now().year)
            scholar_query += f" after:{year_from_str} before:{year_to_str}"
        
        logger.info(f"Searching Google Scholar with query: {scholar_query}")
        
        # Note: Google Scholar doesn't provide total result count upfront
        # We'll just report progress as we fetch
        
        try:
            # Search with scholarly
            search_results = self.scholarly.search_pubs(scholar_query)
            
            count = 0
            for result in search_results:
                if count >= self.max_results:
                    break
                
                try:
                    paper = self._parse_result(result)
                    if paper:
                        papers.append(paper)
                        count += 1
                        
                        if count % 10 == 0:
                            logger.info(f"Google Scholar: Fetched {count} papers so far...")
                    
                    # Be nice to Google - add small delay
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.debug(f"Failed to parse Google Scholar result: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Google Scholar search failed: {e}")
        
        logger.info(f"Google Scholar: Successfully retrieved {len(papers)} papers")
        return papers
    
    def _parse_result(self, result: dict) -> Optional[Paper]:
        """
        Parse a Google Scholar result into a Paper object.
        
        Args:
            result: Result dictionary from scholarly
        
        Returns:
            Paper object or None if parsing fails
        """
        try:
            # Get basic info - scholarly returns dict with 'bib' key
            bib = result.get('bib', {})
            
            title = bib.get('title')
            if not title:
                return None
            
            paper = Paper(title=title)
            paper.sources.add("Google Scholar")
            
            # Authors
            authors = bib.get('author', [])
            if isinstance(authors, list):
                paper.authors = authors
            elif isinstance(authors, str):
                paper.authors = [authors]
            
            # Abstract
            paper.abstract = bib.get('abstract')
            
            # Publication info
            paper.journal = bib.get('venue')
            
            # Publication year
            pub_year = bib.get('pub_year')
            if pub_year:
                try:
                    paper.publication_date = datetime(int(pub_year), 1, 1).date()
                except:
                    pass
            
            # Citations
            num_citations = result.get('num_citations')
            if num_citations:
                try:
                    paper.citations = int(num_citations)
                except:
                    pass
            
            # URL
            pub_url = result.get('pub_url') or result.get('eprint_url')
            if pub_url:
                paper.url = pub_url
            
            # DOI (if available in URL)
            if paper.url and 'doi.org' in paper.url:
                doi_parts = paper.url.split('doi.org/')
                if len(doi_parts) > 1:
                    paper.doi = doi_parts[1].split('?')[0]  # Remove query params
            
            return paper
            
        except Exception as e:
            logger.debug(f"Failed to parse Google Scholar result: {e}")
            return None
