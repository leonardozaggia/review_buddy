"""
IEEE Xplore searcher - Search IEEE digital library.
Requires IEEE API key from: https://developer.ieee.org/
"""

import requests
import logging
from typing import List, Optional
from datetime import datetime

from ..models import Paper
from ..progress import create_progress_tracker


logger = logging.getLogger(__name__)


class IEEESearcher:
    """Search for papers in IEEE Xplore"""
    
    BASE_URL = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
    
    def __init__(self, api_key: str, max_results: int = 1000, timeout: int = 30):
        """
        Initialize IEEE searcher.
        
        Args:
            api_key: IEEE API key
            max_results: Maximum number of results to fetch
            timeout: Request timeout in seconds
        """
        if not api_key:
            raise ValueError("IEEE API key is required")
        
        self.api_key = api_key
        self.max_results = max_results
        self.timeout = timeout
        self.session = requests.Session()
    
    def search(self, query: str, year_from: Optional[int] = None, year_to: Optional[int] = None) -> List[Paper]:
        """
        Search IEEE Xplore for papers matching the query.
        
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
        
        logger.info(f"Searching IEEE Xplore with query: {normalized_query}")
        
        # Fetch in batches
        start = 1  # IEEE starts at 1, not 0
        batch_size = 200  # IEEE max per request
        progress = None
        
        while len(papers) < self.max_results:
            try:
                # Build parameters
                params = {
                    'apikey': self.api_key,
                    'querytext': normalized_query,
                    'max_records': min(batch_size, self.max_results - len(papers)),
                    'start_record': start,
                    'sort_order': 'desc',
                    'sort_field': 'publication_year'
                }
                
                # Add year filters
                if year_from:
                    params['start_year'] = year_from
                if year_to:
                    params['end_year'] = year_to
                
                response = self.session.get(
                    self.BASE_URL,
                    params=params,
                    timeout=self.timeout
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Check for errors
                if 'ERROR' in data:
                    logger.error(f"IEEE API error: {data['ERROR']}")
                    break
                
                total_records = int(data.get('total_records', 0))
                
                if start == 1:
                    logger.info(f"IEEE: Found {total_records} total results")
                    max_to_fetch = min(total_records, self.max_results)
                    progress = create_progress_tracker(max_to_fetch, "IEEE")
                
                articles = data.get('articles', [])
                
                if not articles:
                    break
                
                for article in articles:
                    paper = self._parse_article(article)
                    if paper:
                        papers.append(paper)
                        if progress:
                            progress.update(1)
                
                # Check if we should continue
                if len(articles) < batch_size or len(papers) >= self.max_results or len(papers) >= total_records:
                    break
                
                start += batch_size
                
            except Exception as e:
                logger.error(f"IEEE request failed: {e}")
                break
        
        if progress:
            progress.close()
        
        logger.info(f"IEEE: Successfully retrieved {len(papers)} papers")
        return papers
    
    def _parse_article(self, article: dict) -> Optional[Paper]:
        """
        Parse an IEEE article into a Paper object.
        
        Args:
            article: Article dictionary from IEEE API
        
        Returns:
            Paper object or None if parsing fails
        """
        try:
            # Title
            title = article.get('title')
            if not title:
                return None
            
            paper = Paper(title=title)
            paper.sources.add("IEEE")
            
            # Authors
            authors = article.get('authors', {}).get('authors', [])
            for author in authors:
                full_name = author.get('full_name')
                if full_name:
                    paper.authors.append(full_name)
            
            # Abstract
            paper.abstract = article.get('abstract')
            
            # DOI
            paper.doi = article.get('doi')
            
            # Publication info
            paper.journal = article.get('publication_title')
            paper.volume = article.get('volume')
            paper.issue = article.get('issue')
            
            # Pages
            start_page = article.get('start_page')
            end_page = article.get('end_page')
            if start_page and end_page:
                paper.pages = f"{start_page}-{end_page}"
            elif start_page:
                paper.pages = str(start_page)
            
            # Publication year
            pub_year = article.get('publication_year')
            if pub_year:
                try:
                    paper.publication_date = datetime(int(pub_year), 1, 1).date()
                except:
                    pass
            
            # Publisher
            paper.publisher = article.get('publisher', 'IEEE')
            
            # ISSN/ISBN
            paper.issn = article.get('issn')
            paper.isbn = article.get('isbn')
            
            # URL
            article_number = article.get('article_number')
            if article_number:
                paper.url = f"https://ieeexplore.ieee.org/document/{article_number}"
            
            # PDF URL
            pdf_url = article.get('pdf_url')
            if pdf_url:
                paper.pdf_url = pdf_url
            
            # Keywords/index terms
            index_terms = article.get('index_terms', {})
            
            # Author keywords
            author_terms = index_terms.get('author_terms', {}).get('terms', [])
            for term in author_terms:
                paper.keywords.add(term)
            
            # IEEE terms
            ieee_terms = index_terms.get('ieee_terms', {}).get('terms', [])
            for term in ieee_terms:
                paper.keywords.add(term)
            
            return paper
            
        except Exception as e:
            logger.debug(f"Failed to parse IEEE article: {e}")
            return None
