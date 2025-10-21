"""
Paper searcher implementations for various academic databases
"""

from .scopus_searcher import ScopusSearcher
from .pubmed_searcher import PubMedSearcher
from .arxiv_searcher import ArxivSearcher
from .scholar_searcher import ScholarSearcher
from .ieee_searcher import IEEESearcher
from .paper_downloader import PaperDownloader

__all__ = [
    "ScopusSearcher",
    "PubMedSearcher",
    "ArxivSearcher",
    "ScholarSearcher",
    "IEEESearcher",
    "PaperDownloader",
]