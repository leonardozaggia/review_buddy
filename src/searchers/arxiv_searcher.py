"""
arXiv searcher - Search for preprint papers on arXiv.org
Uses the free arXiv API (no key required).
"""

import requests
import logging
from typing import List, Optional
from datetime import datetime
import xml.etree.ElementTree as ET
import time

from ..models import Paper


logger = logging.getLogger(__name__)


class ArxivSearcher:
    """Search for papers in arXiv"""
    
    BASE_URL = "http://export.arxiv.org/api/query"
    
    def __init__(self, max_results: int = 1000, timeout: int = 30):
        """
        Initialize arXiv searcher.
        
        Args:
            max_results: Maximum number of results to fetch
            timeout: Request timeout in seconds
        """
        self.max_results = max_results
        self.timeout = timeout
        self.session = requests.Session()
    
    def search(self, query: str, year_from: Optional[int] = None, year_to: Optional[int] = None) -> List[Paper]:
        """
        Search arXiv for papers matching the query.
        
        Args:
            query: Search query (simple text search in all fields)
            year_from: Start year filter (applied to submission date)
            year_to: End year filter (applied to submission date)
        
        Returns:
            List of Paper objects
        """
        papers = []
        
        # arXiv API query format: search in all fields
        arxiv_query = f"all:{query}"
        
        logger.info(f"Searching arXiv with query: {arxiv_query}")
        
        # Fetch in batches
        start = 0
        batch_size = 100  # arXiv recommends max 100 per request
        
        while len(papers) < self.max_results:
            try:
                # Make request
                params = {
                    'search_query': arxiv_query,
                    'start': start,
                    'max_results': min(batch_size, self.max_results - len(papers)),
                    'sortBy': 'submittedDate',
                    'sortOrder': 'descending'
                }
                
                response = self.session.get(
                    self.BASE_URL,
                    params=params,
                    timeout=self.timeout
                )
                response.raise_for_status()
                
                # Parse XML response
                root = ET.fromstring(response.content)
                
                # Define namespace
                ns = {'atom': 'http://www.w3.org/2005/Atom',
                      'arxiv': 'http://arxiv.org/schemas/atom'}
                
                entries = root.findall('atom:entry', ns)
                
                if not entries:
                    break
                
                for entry in entries:
                    paper = self._parse_entry(entry, ns)
                    if paper:
                        # Apply year filter
                        if year_from or year_to:
                            if paper.publication_date:
                                year = paper.publication_date.year
                                if year_from and year < year_from:
                                    continue
                                if year_to and year > year_to:
                                    continue
                        
                        papers.append(paper)
                        
                        if len(papers) % 50 == 0:
                            logger.info(f"arXiv: Fetched {len(papers)}/{self.max_results} papers")
                
                # Check if we should continue
                if len(entries) < batch_size or len(papers) >= self.max_results:
                    break
                
                start += batch_size
                time.sleep(0.5)  # Be nice to arXiv API
                
            except Exception as e:
                logger.error(f"arXiv request failed: {e}")
                break
        
        logger.info(f"arXiv: Successfully retrieved {len(papers)} papers")
        return papers
    
    def _parse_entry(self, entry: ET.Element, ns: dict) -> Optional[Paper]:
        """
        Parse an arXiv entry into a Paper object.
        
        Args:
            entry: XML element for entry
            ns: XML namespace dict
        
        Returns:
            Paper object or None if parsing fails
        """
        try:
            # Title
            title_elem = entry.find('atom:title', ns)
            if title_elem is None or not title_elem.text:
                return None
            
            title = title_elem.text.strip().replace('\n', ' ')
            paper = Paper(title=title)
            paper.sources.add("arXiv")
            
            # Authors
            for author_elem in entry.findall('atom:author', ns):
                name_elem = author_elem.find('atom:name', ns)
                if name_elem is not None and name_elem.text:
                    paper.authors.append(name_elem.text.strip())
            
            # Abstract
            summary_elem = entry.find('atom:summary', ns)
            if summary_elem is not None and summary_elem.text:
                paper.abstract = summary_elem.text.strip().replace('\n', ' ')
            
            # arXiv ID
            id_elem = entry.find('atom:id', ns)
            if id_elem is not None and id_elem.text:
                arxiv_id = id_elem.text.split('/abs/')[-1]
                paper.arxiv_id = arxiv_id
                paper.url = f"https://arxiv.org/abs/{arxiv_id}"
                paper.pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            
            # DOI (if published)
            doi_elem = entry.find('arxiv:doi', ns)
            if doi_elem is not None and doi_elem.text:
                paper.doi = doi_elem.text.strip()
            
            # Publication/submission date
            published_elem = entry.find('atom:published', ns)
            if published_elem is not None and published_elem.text:
                try:
                    date_str = published_elem.text.split('T')[0]
                    paper.publication_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except:
                    pass
            
            # Journal reference (if published)
            journal_elem = entry.find('arxiv:journal_ref', ns)
            if journal_elem is not None and journal_elem.text:
                paper.journal = journal_elem.text.strip()
            
            # Categories as keywords
            for category_elem in entry.findall('atom:category', ns):
                term = category_elem.get('term')
                if term:
                    paper.keywords.add(term)
            
            return paper
            
        except Exception as e:
            logger.debug(f"Failed to parse arXiv entry: {e}")
            return None
