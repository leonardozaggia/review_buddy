"""
Scopus searcher - Simple and reliable paper fetching from Scopus database.
"""

import requests
import logging
from typing import List, Optional
from datetime import datetime

from ..models import Paper


logger = logging.getLogger(__name__)


class ScopusSearcher:
    """Search for papers in Scopus database"""
    
    BASE_URL = "https://api.elsevier.com/content/search/scopus"
    
    def __init__(self, api_key: str, max_results: int = 1000, timeout: int = 30):
        """
        Initialize Scopus searcher.
        
        Args:
            api_key: Scopus/Elsevier API key
            max_results: Maximum number of results to fetch
            timeout: Request timeout in seconds
        """
        if not api_key:
            raise ValueError("Scopus API key is required")
        
        self.api_key = api_key
        self.max_results = max_results
        self.timeout = timeout
        self.session = requests.Session()
    
    def search(self, query: str, year_from: Optional[int] = None, year_to: Optional[int] = None) -> List[Paper]:
        """
        Search Scopus for papers matching the query.
        
        Args:
            query: Search query (will be wrapped in TITLE-ABS-KEY())
            year_from: Start year filter
            year_to: End year filter
        
        Returns:
            List of Paper objects
        """
        papers = []
        
        # Build query
        scopus_query = f"TITLE-ABS-KEY({query})"
        
        if year_from:
            scopus_query += f" AND PUBYEAR > {year_from - 1}"
        if year_to:
            scopus_query += f" AND PUBYEAR < {year_to + 1}"
        
        logger.info(f"Searching Scopus with query: {scopus_query}")
        
        # Start fetching
        start = 0
        count = 25  # Results per page
        total_fetched = 0
        
        while total_fetched < self.max_results:
            try:
                # Make request
                params = {
                    "apiKey": self.api_key,
                    "query": scopus_query,
                    "start": start,
                    "count": count,
                    "sort": "coverDate",
                }
                
                headers = {"Accept": "application/json"}
                
                response = self.session.get(
                    self.BASE_URL,
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )
                
                response.raise_for_status()
                data = response.json()
                
                # Parse results
                search_results = data.get("search-results", {})
                total_results = int(search_results.get("opensearch:totalResults", 0))
                
                if start == 0:
                    logger.info(f"Scopus: Found {total_results} total results")
                
                entries = search_results.get("entry", [])
                
                if not entries:
                    break
                
                for entry in entries:
                    paper = self._parse_entry(entry)
                    if paper:
                        papers.append(paper)
                        total_fetched += 1
                
                logger.info(f"Scopus: Fetched {total_fetched}/{min(total_results, self.max_results)} papers")
                
                # Check if we should continue
                if total_fetched >= total_results or total_fetched >= self.max_results:
                    break
                
                # Move to next page
                start += count
                
            except requests.RequestException as e:
                logger.error(f"Scopus request failed: {e}")
                break
            except Exception as e:
                logger.error(f"Scopus parsing error: {e}")
                break
        
        logger.info(f"Scopus: Successfully retrieved {len(papers)} papers")
        return papers
    
    def _parse_entry(self, entry: dict) -> Optional[Paper]:
        """
        Parse a Scopus entry into a Paper object.
        
        Args:
            entry: Scopus API entry dictionary
        
        Returns:
            Paper object or None if parsing fails
        """
        try:
            # Required fields
            title = entry.get("dc:title")
            if not title:
                return None
            
            # Create paper
            paper = Paper(title=title)
            paper.sources.add("Scopus")
            
            # Authors
            creator = entry.get("dc:creator")
            if creator:
                paper.authors.append(creator)
            
            # DOI
            paper.doi = entry.get("prism:doi")
            
            # Publication date
            cover_date = entry.get("prism:coverDate")
            if cover_date:
                try:
                    paper.publication_date = datetime.strptime(cover_date, "%Y-%m-%d").date()
                except:
                    pass
            
            # Journal/publication info
            paper.journal = entry.get("prism:publicationName")
            paper.volume = entry.get("prism:volume")
            paper.issue = entry.get("prism:issueIdentifier")
            paper.pages = entry.get("prism:pageRange")
            paper.issn = entry.get("prism:issn")
            
            # Citations
            cited_by = entry.get("citedby-count")
            if cited_by:
                try:
                    paper.citations = int(cited_by)
                except:
                    pass
            
            # URL
            for link in entry.get("link", []):
                if link.get("@ref") == "scopus":
                    paper.url = link.get("@href")
                    break
            
            # Get more details if we have a Scopus link
            if paper.url:
                self._enrich_paper(paper)
            
            return paper
            
        except Exception as e:
            logger.debug(f"Failed to parse Scopus entry: {e}")
            return None
    
    def _enrich_paper(self, paper: Paper):
        """
        Fetch additional details from Scopus paper page.
        This is best-effort - if it fails, we still have the basic data.
        
        Args:
            paper: Paper object to enrich
        """
        try:
            # We could scrape the paper page here for abstract, keywords, etc.
            # For now, keeping it simple - the API gives us most of what we need
            pass
        except Exception as e:
            logger.debug(f"Failed to enrich paper from Scopus: {e}")
