"""
Scopus searcher - Simple and reliable paper fetching from Scopus database.
"""

import requests
import logging
from typing import List, Optional
from datetime import datetime

from ..models import Paper
from ..progress import create_progress_tracker


logger = logging.getLogger(__name__)


def _wrapped_in_parens(query: str) -> bool:
    """
    True only if a single pair of parentheses encloses the entire query.

    `(A OR B)` qualifies; `(A) AND (B)` does not, even though it also starts
    with '(' and ends with ')'. Parentheses inside quoted phrases are ignored.
    """
    if not (query.startswith("(") and query.endswith(")")):
        return False

    depth = 0
    in_quotes = False
    last = len(query) - 1
    for i, char in enumerate(query):
        if char == '"':
            in_quotes = not in_quotes
        elif in_quotes:
            continue
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and i < last:
                return False  # the opening paren closed early: not a wrapper
            if depth < 0:
                return False  # unbalanced
    return depth == 0


class ScopusSearcher:
    """Search for papers in Scopus database"""
    
    BASE_URL = "https://api.elsevier.com/content/search/scopus"
    ABSTRACT_URL = "https://api.elsevier.com/content/abstract/scopus_id"

    # Elsevier serves at most 5000 records per query: any request with
    # start >= 5000 returns HTTP 400 "Exceeds the number of search results",
    # no matter what max_results is set to. Reaching further needs the query
    # split into smaller slices (e.g. one publication year at a time).
    MAX_RETRIEVABLE = 5000

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

        When the result set exceeds the API's per-query ceiling the search is
        automatically split into one-year slices, so a broad query still returns
        everything rather than silently stopping at the first 5000.

        Args:
            query: Search query (will be wrapped in TITLE-ABS-KEY())
            year_from: Start year filter
            year_to: End year filter

        Returns:
            List of Paper objects
        """
        base_query = self._build_query(query)
        logger.info(f"Searching Scopus with query: "
                    f"{base_query}{self._year_clause(year_from, year_to)}")

        total = self._count_results(base_query, year_from, year_to)
        if total is None:
            return []
        logger.info(f"Scopus: Found {total} total results")

        windows = self._plan_windows(total, year_from, year_to)

        target = min(total, self.max_results)
        progress = create_progress_tracker(target, "Scopus") if target else None

        papers: List[Paper] = []
        try:
            for window_from, window_to in windows:
                if len(papers) >= self.max_results:
                    break
                papers.extend(self._fetch_window(
                    base_query, window_from, window_to,
                    limit=self.max_results - len(papers),
                    progress=progress,
                    announce=len(windows) > 1,
                ))
        finally:
            if progress:
                progress.close()

        logger.info(f"Scopus: Successfully retrieved {len(papers)} papers")
        return papers

    def _build_query(self, query: str) -> str:
        """Wrap the user's query in Scopus syntax. No year clause — see _year_clause."""
        # Normalize query - remove newlines and extra whitespace
        # This is crucial for queries read from .txt files
        normalized_query = ' '.join(query.split())

        # Check if query already contains field codes (TITLE-ABS-KEY, TITLE, etc.)
        upper_query = normalized_query.upper()
        has_field_codes = any(code in upper_query for code in ['TITLE-ABS-KEY', 'TITLE(', 'ABS(', 'KEY(', 'AUTH(', 'AFFIL('])

        if has_field_codes:
            # Query already has field codes, use as-is
            scopus_query = normalized_query
        else:
            # Simple boolean query without field codes: scope the WHOLE query to
            # title/abstract/keywords. Redundant outer parentheses are dropped
            # only when they genuinely wrap everything — "(A) AND (B)" also
            # starts with '(' and ends with ')', but stripping those leaves
            # "TITLE-ABS-KEY(A) AND (B)", where B escapes the field restriction
            # and is matched against every Scopus field including references and
            # affiliations. On a real three-group query that inflated the result
            # set more than tenfold (544 -> 5751).
            stripped_query = normalized_query.strip()
            if _wrapped_in_parens(stripped_query):
                stripped_query = stripped_query[1:-1].strip()
            scopus_query = f"TITLE-ABS-KEY({stripped_query})"

        # Fix Scopus-specific syntax issues
        # In Scopus, standalone NOT should be AND NOT
        scopus_query = scopus_query.replace(' NOT (', ' AND NOT (')
        scopus_query = scopus_query.replace(' not (', ' AND NOT (')
        return scopus_query

    @staticmethod
    def _year_clause(year_from: Optional[int], year_to: Optional[int]) -> str:
        """The PUBYEAR restriction for one window (empty when unbounded)."""
        clause = ""
        if year_from:
            clause += f" AND PUBYEAR > {year_from - 1}"
        if year_to:
            clause += f" AND PUBYEAR < {year_to + 1}"
        return clause

    def _request(self, query: str, start: int, count: int) -> dict:
        """One search request. Raises on transport/HTTP errors."""
        params = {
            "apiKey": self.api_key,
            "query": query,
            "start": start,
            "count": count,
            "sort": "coverDate",
            "view": "COMPLETE",  # Request complete view to get more fields
        }
        response = self.session.get(
            self.BASE_URL,
            params=params,
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json().get("search-results", {})

    def _count_results(self, base_query: str, year_from: Optional[int],
                       year_to: Optional[int]) -> Optional[int]:
        """Total matches for a window, or None if the request failed."""
        try:
            results = self._request(base_query + self._year_clause(year_from, year_to), 0, 1)
            return int(results.get("opensearch:totalResults", 0))
        except requests.RequestException as e:
            logger.error(f"Scopus request failed: {e}")
            return None
        except (ValueError, TypeError) as e:
            logger.error(f"Scopus returned an unreadable result count: {e}")
            return None

    def _plan_windows(self, total: int, year_from: Optional[int],
                      year_to: Optional[int]) -> List[tuple]:
        """
        Split the search into windows that each fit under the API ceiling.

        Elsevier serves at most MAX_RETRIEVABLE records per *query*, so the only
        way to reach a bigger result set is to issue several narrower queries.
        Publication year is the natural axis: the slices are disjoint, so they
        cannot return the same paper twice.
        """
        if total <= self.MAX_RETRIEVABLE:
            return [(year_from, year_to)]

        last_year = year_to or datetime.now().year
        if not year_from or last_year < year_from:
            logger.warning(
                f"Scopus: {total} matches exceed the {self.MAX_RETRIEVABLE}-record ceiling, "
                f"and without a start year the search cannot be split automatically. Only the "
                f"first {self.MAX_RETRIEVABLE} are reachable — set search.year_from in "
                f"config.yaml to enable year-by-year slicing."
            )
            return [(year_from, year_to)]

        if last_year == year_from:
            # A single year already over the ceiling: PUBYEAR is the only axis
            # we can slice on, so there is nothing finer to cut it into.
            logger.warning(
                f"Scopus: {total} matches in {year_from} alone exceed the "
                f"{self.MAX_RETRIEVABLE}-record ceiling, and a one-year search cannot be split "
                f"any further. {total - self.MAX_RETRIEVABLE} records are unreachable — narrow "
                f"the query to recover them."
            )
            return [(year_from, year_to)]

        # The final window keeps the caller's upper bound, so an open-ended
        # search still picks up records dated beyond the current year (Scopus
        # carries in-press articles with next year's cover date).
        windows = [(y, y) for y in range(year_from, last_year)]
        windows.append((last_year, year_to))

        logger.info(
            f"Scopus: {total} matches exceed the {self.MAX_RETRIEVABLE}-record per-query "
            f"ceiling — splitting into {len(windows)} one-year searches "
            f"({year_from}–{year_to or 'present'}) to retrieve all of them."
        )
        return windows

    def _fetch_window(self, base_query: str, year_from: Optional[int], year_to: Optional[int],
                      limit: int, progress=None, announce: bool = False) -> List[Paper]:
        """Page through a single year window, up to `limit` papers."""
        query = base_query + self._year_clause(year_from, year_to)
        label = str(year_from) if year_from and year_from == year_to else \
            f"{year_from or 'any'}-{year_to or 'present'}"

        papers: List[Paper] = []
        window_total = None
        start = 0
        page = 25  # Results per page

        while len(papers) < limit and start < self.MAX_RETRIEVABLE:
            page_size = min(page, limit - len(papers), self.MAX_RETRIEVABLE - start)
            try:
                results = self._request(query, start, page_size)
            except requests.RequestException as e:
                resp = getattr(e, "response", None)
                if resp is not None and resp.status_code == 400 and "Exceeds the number" in resp.text:
                    logger.warning(
                        f"Scopus [{label}]: hit the {self.MAX_RETRIEVABLE}-record ceiling "
                        f"(kept {len(papers)} papers)."
                    )
                else:
                    logger.error(f"Scopus request failed: {e}")
                break
            except Exception as e:
                logger.error(f"Scopus parsing error: {e}")
                break

            if window_total is None:
                try:
                    window_total = int(results.get("opensearch:totalResults", 0))
                except (TypeError, ValueError):
                    window_total = 0
                if announce:
                    logger.info(f"Scopus [{label}]: {window_total} matches")
                if window_total > self.MAX_RETRIEVABLE:
                    logger.warning(
                        f"Scopus [{label}]: {window_total} matches in this single year still "
                        f"exceed the {self.MAX_RETRIEVABLE}-record ceiling, so "
                        f"{window_total - self.MAX_RETRIEVABLE} of them cannot be retrieved. "
                        f"Narrow the query to recover them."
                    )

            entries = results.get("entry", [])
            if not entries:
                break

            for entry in entries:
                paper = self._parse_entry(entry)
                if paper:
                    papers.append(paper)
                    if progress:
                        progress.update(1)

            if len(papers) >= window_total:
                break
            start += page_size

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
            
            # Authors - the COMPLETE view returns a full `author` array; the
            # `dc:creator` field only holds the first author. Prefer the array.
            authors = entry.get("author")
            if isinstance(authors, list) and authors:
                for a in authors:
                    given = a.get("given-name")
                    surname = a.get("surname")
                    if given and surname:
                        paper.authors.append(f"{given} {surname}")
                    elif a.get("authname"):
                        paper.authors.append(a["authname"])
            if not paper.authors:
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
