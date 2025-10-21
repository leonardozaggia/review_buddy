"""
Configuration and API keys for paper searcher.
"""

import os
from typing import Optional


class Config:
    """Configuration for paper searching and downloading"""
    
    def __init__(
        self,
        scopus_api_key: Optional[str] = None,
        pubmed_email: Optional[str] = None,
        pubmed_api_key: Optional[str] = None,
        ieee_api_key: Optional[str] = None,
        use_scihub: bool = False,
        scihub_url: str = "https://sci-hub.se",
        max_results_per_source: int = 1000,
        timeout: int = 30,
    ):
        """
        Initialize configuration.
        
        Args:
            scopus_api_key: Elsevier/Scopus API key
            pubmed_email: Email for PubMed API (required by NCBI)
            pubmed_api_key: PubMed API key (optional, increases rate limits)
            ieee_api_key: IEEE Xplore API key
            use_scihub: Whether to use Sci-Hub as fallback for downloads
            scihub_url: Sci-Hub URL to use
            max_results_per_source: Maximum papers to fetch per database
            timeout: Request timeout in seconds
        """
        # Get from environment and strip quotes if present
        self.scopus_api_key = self._clean_value(scopus_api_key or os.getenv("SCOPUS_API_KEY"))
        self.pubmed_email = self._clean_value(pubmed_email or os.getenv("PUBMED_EMAIL"))
        self.pubmed_api_key = self._clean_value(pubmed_api_key or os.getenv("PUBMED_API_KEY"))
        self.ieee_api_key = self._clean_value(ieee_api_key or os.getenv("IEEE_API_KEY"))
        self.use_scihub = use_scihub
        self.scihub_url = scihub_url
        self.max_results_per_source = max_results_per_source
        self.timeout = timeout
    
    def _clean_value(self, value: Optional[str]) -> Optional[str]:
        """
        Clean configuration values by removing surrounding quotes.
        Environment variables sometimes include quotes when set.
        
        Args:
            value: String value to clean
            
        Returns:
            Cleaned string or None
        """
        if not value:
            return None
        
        value = value.strip()
        
        # Remove surrounding quotes (single or double)
        if len(value) >= 2:
            if (value[0] == '"' and value[-1] == '"') or \
               (value[0] == "'" and value[-1] == "'"):
                value = value[1:-1]
        
        return value if value else None
    
    def has_scopus_access(self) -> bool:
        """Check if Scopus API key is configured"""
        return bool(self.scopus_api_key)
    
    def has_pubmed_access(self) -> bool:
        """Check if PubMed email is configured"""
        return bool(self.pubmed_email)
    
    def has_arxiv_access(self) -> bool:
        """Check if arXiv access is available (always true, no key needed)"""
        return True
    
    def has_scholar_access(self) -> bool:
        """Check if Google Scholar access is available (always true, no key needed)"""
        return True
    
    def has_ieee_access(self) -> bool:
        """Check if IEEE API key is configured"""
        return bool(self.ieee_api_key)
