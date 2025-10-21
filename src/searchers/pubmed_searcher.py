"""
PubMed searcher - Free access to biomedical literature via NCBI E-utilities.
"""

import requests
import logging
import time
from typing import List, Optional
from datetime import datetime
from xml.etree import ElementTree as ET

from ..models import Paper


logger = logging.getLogger(__name__)


class PubMedSearcher:
    """Search for papers in PubMed/MEDLINE database"""
    
    SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    
    def __init__(self, email: str, api_key: Optional[str] = None, max_results: int = 1000, timeout: int = 30):
        """
        Initialize PubMed searcher.
        
        Args:
            email: Your email (required by NCBI)
            api_key: PubMed API key (optional, increases rate limits)
            max_results: Maximum number of results to fetch
            timeout: Request timeout in seconds
        """
        if not email:
            raise ValueError("Email is required for PubMed API (NCBI policy)")
        
        self.email = email
        self.api_key = api_key
        self.max_results = max_results
        self.timeout = timeout
        self.session = requests.Session()
        
        # Rate limiting: 3 requests/sec without key, 10 with key
        self.delay = 0.1 if api_key else 0.34
    
    def search(self, query: str, year_from: Optional[int] = None, year_to: Optional[int] = None) -> List[Paper]:
        """
        Search PubMed for papers matching the query.
        
        Args:
            query: Search query (PubMed query syntax)
            year_from: Start year filter
            year_to: End year filter
        
        Returns:
            List of Paper objects
        """
        papers = []
        
        # Build query with date filters
        pubmed_query = query
        if year_from or year_to:
            date_from = f"{year_from or 1900}/01/01"
            date_to = f"{year_to or datetime.now().year}/12/31"
            pubmed_query += f" AND ({date_from}:{date_to}[pdat])"
        
        logger.info(f"Searching PubMed with query: {pubmed_query}")
        
        # Step 1: Search to get PMIDs
        pmids = self._search_pmids(pubmed_query)
        
        if not pmids:
            logger.info("PubMed: No results found")
            return papers
        
        logger.info(f"PubMed: Found {len(pmids)} results, fetching details...")
        
        # Step 2: Fetch details in batches
        batch_size = 100
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i + batch_size]
            batch_papers = self._fetch_details(batch)
            papers.extend(batch_papers)
            
            logger.info(f"PubMed: Fetched {len(papers)}/{len(pmids)} papers")
            time.sleep(self.delay)  # Rate limiting
        
        logger.info(f"PubMed: Successfully retrieved {len(papers)} papers")
        return papers
    
    def _search_pmids(self, query: str) -> List[str]:
        """
        Search PubMed and get list of PMIDs.
        
        Args:
            query: PubMed query string
        
        Returns:
            List of PubMed IDs
        """
        try:
            params = {
                "db": "pubmed",
                "term": query,
                "retmax": self.max_results,
                "retmode": "json",
                "email": self.email,
            }
            
            if self.api_key:
                params["api_key"] = self.api_key
            
            response = self.session.get(
                self.SEARCH_URL,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            pmids = data.get("esearchresult", {}).get("idlist", [])
            
            return pmids
            
        except Exception as e:
            logger.error(f"PubMed search failed: {e}")
            return []
    
    def _fetch_details(self, pmids: List[str]) -> List[Paper]:
        """
        Fetch full details for a list of PMIDs.
        
        Args:
            pmids: List of PubMed IDs
        
        Returns:
            List of Paper objects
        """
        papers = []
        
        try:
            params = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "xml",
                "email": self.email,
            }
            
            if self.api_key:
                params["api_key"] = self.api_key
            
            response = self.session.get(
                self.FETCH_URL,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            # Parse XML
            root = ET.fromstring(response.content)
            
            for article in root.findall(".//PubmedArticle"):
                paper = self._parse_article(article)
                if paper:
                    papers.append(paper)
            
        except Exception as e:
            logger.error(f"PubMed fetch failed: {e}")
        
        return papers
    
    def _parse_article(self, article: ET.Element) -> Optional[Paper]:
        """
        Parse a PubMed article XML element into a Paper object.
        
        Args:
            article: XML element for article
        
        Returns:
            Paper object or None if parsing fails
        """
        try:
            # Get article element
            medline_citation = article.find(".//MedlineCitation")
            if medline_citation is None:
                return None
            
            article_elem = medline_citation.find(".//Article")
            if article_elem is None:
                return None
            
            # Title
            title_elem = article_elem.find(".//ArticleTitle")
            if title_elem is None or not title_elem.text:
                return None
            
            title = title_elem.text.strip()
            paper = Paper(title=title)
            paper.sources.add("PubMed")
            
            # PMID
            pmid_elem = medline_citation.find(".//PMID")
            if pmid_elem is not None and pmid_elem.text:
                paper.pmid = pmid_elem.text.strip()
            
            # Authors
            authors_list = article_elem.find(".//AuthorList")
            if authors_list is not None:
                for author in authors_list.findall(".//Author"):
                    last_name = author.find(".//LastName")
                    fore_name = author.find(".//ForeName")
                    if last_name is not None and last_name.text:
                        name = last_name.text
                        if fore_name is not None and fore_name.text:
                            name = f"{fore_name.text} {name}"
                        paper.authors.append(name.strip())
            
            # Abstract
            abstract_elem = article_elem.find(".//Abstract/AbstractText")
            if abstract_elem is not None and abstract_elem.text:
                paper.abstract = abstract_elem.text.strip()
            
            # Journal
            journal_elem = article_elem.find(".//Journal")
            if journal_elem is not None:
                journal_title = journal_elem.find(".//Title")
                if journal_title is not None and journal_title.text:
                    paper.journal = journal_title.text.strip()
                
                # ISSN
                issn_elem = journal_elem.find(".//ISSN")
                if issn_elem is not None and issn_elem.text:
                    paper.issn = issn_elem.text.strip()
                
                # Volume, Issue
                journal_issue = journal_elem.find(".//JournalIssue")
                if journal_issue is not None:
                    volume_elem = journal_issue.find(".//Volume")
                    if volume_elem is not None and volume_elem.text:
                        paper.volume = volume_elem.text.strip()
                    
                    issue_elem = journal_issue.find(".//Issue")
                    if issue_elem is not None and issue_elem.text:
                        paper.issue = issue_elem.text.strip()
            
            # Pages
            pagination = article_elem.find(".//Pagination/MedlinePgn")
            if pagination is not None and pagination.text:
                paper.pages = pagination.text.strip()
            
            # Publication date
            pub_date = article_elem.find(".//Journal/JournalIssue/PubDate")
            if pub_date is not None:
                year_elem = pub_date.find(".//Year")
                month_elem = pub_date.find(".//Month")
                day_elem = pub_date.find(".//Day")
                
                if year_elem is not None and year_elem.text:
                    year = int(year_elem.text)
                    month = 1
                    day = 1
                    
                    if month_elem is not None and month_elem.text:
                        try:
                            month = int(month_elem.text)
                        except:
                            # Month might be name like "Jan"
                            month_map = {
                                "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
                                "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
                                "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
                            }
                            month = month_map.get(month_elem.text[:3], 1)
                    
                    if day_elem is not None and day_elem.text:
                        try:
                            day = int(day_elem.text)
                        except:
                            pass
                    
                    try:
                        paper.publication_date = datetime(year, month, day).date()
                    except:
                        pass
            
            # DOI
            article_ids = article.find(".//PubmedData/ArticleIdList")
            if article_ids is not None:
                for article_id in article_ids.findall(".//ArticleId"):
                    if article_id.get("IdType") == "doi" and article_id.text:
                        paper.doi = article_id.text.strip()
                        break
            
            # Keywords
            keywords_list = medline_citation.find(".//KeywordList")
            if keywords_list is not None:
                for keyword in keywords_list.findall(".//Keyword"):
                    if keyword.text:
                        paper.keywords.add(keyword.text.strip())
            
            # URL
            if paper.pmid:
                paper.url = f"https://pubmed.ncbi.nlm.nih.gov/{paper.pmid}/"
            
            return paper
            
        except Exception as e:
            logger.debug(f"Failed to parse PubMed article: {e}")
            return None
