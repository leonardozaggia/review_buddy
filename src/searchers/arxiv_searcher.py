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
from ..progress import create_progress_tracker


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
        
        # Normalize query - remove newlines and extra whitespace
        # This is crucial for queries read from .txt files
        normalized_query = ' '.join(query.split())
        
        # arXiv doesn't support wildcards (*), so remove them
        # Replace common patterns like "Electroencephalogra*" with just "Electroencephalogr"
        arxiv_safe_query = normalized_query.replace('*', '')
        
        # arXiv also has issues with "NOT" - it uses "ANDNOT" instead
        # Convert " NOT " to " ANDNOT "
        arxiv_safe_query = arxiv_safe_query.replace(' NOT ', ' ANDNOT ')
        
        # arXiv API query format: search in all fields
        arxiv_query = f"all:{arxiv_safe_query}"
        
        # Add date filtering to the query if year range is specified
        # arXiv uses submittedDate with format [YYYYMMDDTTTT TO YYYYMMDDTTTT]
        if year_from or year_to:
            from_date = f"{year_from or 1900}01010000"
            to_date = f"{year_to or 2099}12312359"
            arxiv_query += f" AND submittedDate:[{from_date} TO {to_date}]"
            logger.debug(f"arXiv: Added date filter to query: submittedDate:[{from_date} TO {to_date}]")
        
        logger.info(f"Searching arXiv with query: {arxiv_query[:200]}...")  # Truncate for readability
        
        # Determine sort order based on year filter
        # If filtering by year_from, sort ascending (oldest first) to hit the range faster
        # Otherwise sort descending (newest first) for most recent results
        if year_from:
            sort_order = 'ascending'
            logger.debug(f"arXiv: Using ascending sort to reach year_from={year_from}")
        else:
            sort_order = 'descending'
        
        # Fetch in batches
        start = 0
        batch_size = 100  # arXiv recommends max 100 per request
        progress = None
        
        while len(papers) < self.max_results:
            try:
                # Make request
                params = {
                    'search_query': arxiv_query,
                    'start': start,
                    'max_results': min(batch_size, self.max_results - len(papers)),
                    'sortBy': 'submittedDate',
                    'sortOrder': sort_order
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
                
                # Initialize progress bar on first batch
                if progress is None and entries:
                    # Get total results from opensearch:totalResults
                    total_results_elem = root.find('opensearch:totalResults', 
                                                  {'opensearch': 'http://a9.com/-/spec/opensearch/1.1/'})
                    if total_results_elem is not None and total_results_elem.text:
                        total_results = int(total_results_elem.text)
                        max_to_fetch = min(total_results, self.max_results)
                        progress = create_progress_tracker(max_to_fetch, "arXiv")
                
                filtered_out_count = 0
                fetched_count = 0
                papers_too_new = 0  # Track if we've exceeded year_to
                
                for entry in entries:
                    paper = self._parse_entry(entry, ns)
                    if paper:
                        fetched_count += 1
                        # Apply year filter
                        if year_from or year_to:
                            if paper.publication_date:
                                year = paper.publication_date.year
                                if year_from and year < year_from:
                                    logger.debug(f"arXiv: Filtered out (too old): {year} < {year_from} | {paper.title[:80]}")
                                    filtered_out_count += 1
                                    continue
                                if year_to and year > year_to:
                                    logger.debug(f"arXiv: Filtered out (too new): {year} > {year_to} | {paper.title[:80]}")
                                    filtered_out_count += 1
                                    papers_too_new += 1
                                    continue
                            else:
                                logger.debug(f"arXiv: Filtered out (no date): {paper.title[:80]}")
                                filtered_out_count += 1
                                continue
                        
                        papers.append(paper)
                        if progress:
                            progress.update(1)
                
                if filtered_out_count > 0:
                    logger.info(f"arXiv batch: fetched {fetched_count}, accepted {fetched_count - filtered_out_count}, filtered out {filtered_out_count}")
                
                # If we're getting too many papers beyond year_to and sorting ascending, we can stop
                # This happens when sorting ascending and we've moved past the desired range
                if year_to and sort_order == 'descending' and papers_too_new > batch_size * 0.8:
                    logger.info(f"arXiv: Stopping early - most papers now exceed year_to={year_to}")
                    break
                
                # Check if we should continue
                if len(entries) < batch_size or len(papers) >= self.max_results:
                    break
                
                start += batch_size
                time.sleep(0.5)  # Be nice to arXiv API
                
            except Exception as e:
                logger.error(f"arXiv request failed: {e}")
                import traceback
                logger.debug(f"arXiv error traceback: {traceback.format_exc()}")
                break
        
        if progress:
            progress.close()
        
        logger.info(f"arXiv: Successfully retrieved {len(papers)} papers")
        if year_from or year_to:
            logger.info(f"arXiv: Year filter applied - range: {year_from or 'any'} to {year_to or 'any'}")
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
