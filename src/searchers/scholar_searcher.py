"""
Google Scholar searcher - Using scholarly library for academic paper search.
Note: Google Scholar doesn't have an official API, so this uses web scraping.
Be respectful with rate limits.
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..models import Paper


logger = logging.getLogger(__name__)


class ScholarSearcher:
    """Search for papers in Google Scholar"""
    
    def __init__(self, max_results: int = 1000, timeout: int = 30,
                 overall_timeout: int = 60):
        """
        Initialize Google Scholar searcher.

        Args:
            max_results: Maximum number of results to fetch
            timeout: Per-request timeout in seconds
            overall_timeout: Hard cap (seconds) on the whole Scholar search. The
                `scholarly` library gives NO way to time out its blocking calls,
                and Google Scholar frequently blocks automated queries by simply
                hanging (or serving a CAPTCHA it silently retries). Without this
                cap a single blocked Scholar request would stall the entire
                fetch step forever. When hit, we return whatever was collected
                so far and let the other sources proceed.
        """
        self.max_results = max_results
        self.timeout = timeout
        self.overall_timeout = overall_timeout

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
        Search Google Scholar with a hard overall timeout.

        `scholarly` provides no timeout and blocks uninterruptibly (thread and
        even multiprocessing timeouts fail to stop it on Windows - verified).
        The reliable fix is to run it as a plain SUBPROCESS and enforce the
        deadline with subprocess.run(timeout=...), whose kill uses a real
        TerminateProcess. Returns whatever the subprocess produced (usually
        empty when Google is blocking automated access).
        """
        import subprocess
        import tempfile
        import os

        normalized_query = ' '.join(query.split())
        logger.info(f"Searching Google Scholar with query: {normalized_query}")
        if year_from or year_to:
            logger.info(f"Google Scholar: year range {year_from or 'any'} to {year_to or 'any'}")

        script = Path(__file__).resolve().parent.parent.parent / "scripts" / "scholar_fetch.py"
        fd, out_file = tempfile.mkstemp(suffix=".json", prefix="scholar_")
        os.close(fd)
        args = [sys.executable, str(script), out_file, str(self.max_results),
                str(year_from) if year_from else "-",
                str(year_to) if year_to else "-",
                normalized_query]

        raw = []
        try:
            # No stdout/stderr pipes: scholarly may spawn grandchildren that
            # would keep a captured pipe open past the child's death and hang
            # us. We read results from `out_file` instead.
            subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=self.overall_timeout)
        except subprocess.TimeoutExpired:
            logger.warning(
                f"Google Scholar timed out after {self.overall_timeout}s - Google is "
                f"almost certainly blocking automated access (CAPTCHA/rate limit). "
                f"Skipping Scholar. Tip: remove 'scholar' from config.yaml sources, or use a proxy."
            )
        except Exception as e:
            logger.error(f"Google Scholar search failed: {e}")
        finally:
            try:
                with open(out_file, encoding="utf-8") as f:
                    raw = json.loads(f.read() or "[]")
            except (FileNotFoundError, ValueError):
                raw = []
            try:
                os.remove(out_file)
            except OSError:
                pass

        papers = [p for p in (self._paper_from_dict(d) for d in raw) if p]
        logger.info(f"Google Scholar: Successfully retrieved {len(papers)} papers")
        return papers

    def _paper_from_dict(self, d: dict) -> Optional[Paper]:
        """Build a Paper from the JSON dict emitted by scripts/scholar_fetch.py."""
        try:
            title = d.get("title")
            if not title:
                return None
            paper = Paper(title=title)
            paper.sources.add("Google Scholar")
            paper.authors = d.get("authors") or []
            paper.abstract = d.get("abstract")
            paper.journal = d.get("journal")
            paper.url = d.get("url")
            paper.doi = d.get("doi")
            if d.get("year"):
                try:
                    paper.publication_date = datetime(int(d["year"]), 1, 1).date()
                except (ValueError, TypeError):
                    pass
            if d.get("citations") is not None:
                try:
                    paper.citations = int(d["citations"])
                except (ValueError, TypeError):
                    pass
            return paper
        except Exception as e:
            logger.debug(f"Failed to build Scholar paper: {e}")
            return None

    def _parse_result(self, result: dict) -> Optional[Paper]:
        """
        Parse a raw scholarly result dict into a Paper (used by the subprocess
        helper's fallback path and kept for compatibility).
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

