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
    ABSTRACT_URL = "https://api.elsevier.com/content/abstract/scopus_id"
    
    def __init__(self, api_key: str, max_results: int = 1000, timeout: int = 30, fetch_abstracts: bool = True):
        """
        Initialize Scopus searcher.
        
        Args:
            api_key: Scopus/Elsevier API key
            max_results: Maximum number of results to fetch
            timeout: Request timeout in seconds
            fetch_abstracts: Whether to fetch abstracts (requires additional API calls)
        """
        if not api_key:
            raise ValueError("Scopus API key is required")
        
        self.api_key = api_key
        self.max_results = max_results
        self.timeout = timeout
        self.fetch_abstracts = fetch_abstracts
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
        
        # Normalize query - remove newlines and extra whitespace
        # This is crucial for queries read from .txt files
        normalized_query = ' '.join(query.split())
        
        # Build query for Scopus
        # Check if query already contains field codes (TITLE-ABS-KEY, TITLE, etc.)
        upper_query = normalized_query.upper()
        has_field_codes = any(code in upper_query for code in ['TITLE-ABS-KEY', 'TITLE(', 'ABS(', 'KEY(', 'AUTH(', 'AFFIL('])
        
        if has_field_codes:
            # Query already has field codes, use as-is
            scopus_query = normalized_query
        else:
            # Simple boolean query without field codes
            # Remove outer parentheses if the query is wrapped in them
            stripped_query = normalized_query.strip()
            if stripped_query.startswith('(') and stripped_query.endswith(')'):
                # Check if these are the outer wrapping parentheses
                # by ensuring they match and aren't part of the query structure
                inner_query = stripped_query[1:-1].strip()
                scopus_query = f"TITLE-ABS-KEY({inner_query})"
            else:
                scopus_query = f"TITLE-ABS-KEY({normalized_query})"
        
        # Fix Scopus-specific syntax issues
        # In Scopus, standalone NOT should be AND NOT
        # Replace " NOT (" with " AND NOT (" to fix boolean logic
        scopus_query = scopus_query.replace(' NOT (', ' AND NOT (')
        scopus_query = scopus_query.replace(' not (', ' AND NOT (')
        
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
                    "view": "COMPLETE",  # Request complete view to get more fields
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
            
            # Abstract (may be available in COMPLETE view)
            abstract = entry.get("dc:description")
            if abstract:
                paper.abstract = abstract
            
            # Extract Scopus ID for potential abstract fetching
            scopus_id = entry.get("dc:identifier")
            if scopus_id:
                # Format is "SCOPUS_ID:123456789"
                scopus_id = scopus_id.replace("SCOPUS_ID:", "")
            
            # Fetch abstract if not available and fetching is enabled
            if not paper.abstract and self.fetch_abstracts and scopus_id:
                self._fetch_abstract(paper, scopus_id)
            
            return paper
            
        except Exception as e:
            logger.debug(f"Failed to parse Scopus entry: {e}")
            return None
    
    def _fetch_abstract(self, paper: Paper, scopus_id: str):
        """
        Fetch abstract using the Scopus Abstract Retrieval API.
        
        Args:
            paper: Paper object to add abstract to
            scopus_id: Scopus ID of the paper
        """
        try:
            url = f"{self.ABSTRACT_URL}/{scopus_id}"
            params = {
                "apiKey": self.api_key,
                "view": "FULL",
            }
            headers = {"Accept": "application/json"}
            
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Navigate to abstract in response
                coredata = data.get("abstracts-retrieval-response", {}).get("coredata", {})
                abstract = coredata.get("dc:description")
                
                if abstract:
                    paper.abstract = abstract
                    logger.debug(f"Fetched abstract for: {paper.title[:50]}...")
                    
            elif response.status_code == 404:
                logger.debug(f"No abstract available for Scopus ID: {scopus_id}")
            else:
                logger.debug(f"Abstract fetch failed with status {response.status_code} for: {scopus_id}")
                
        except Exception as e:
            logger.debug(f"Failed to fetch abstract for Scopus ID {scopus_id}: {e}")
