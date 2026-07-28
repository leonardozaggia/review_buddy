"""
Paper Downloader Module

Downloads PDFs for papers listed in a .bib or .ris file, prioritizing open access sources.
Supports fallback strategies and optional Sci-Hub integration.
"""
import os
import re
import logging
from typing import List, Optional
from pathlib import Path

# External dependencies: requests, unpaywall, bibtexparser, rispy
# Sci-Hub support: requires user opt-in and third-party library (e.g., sci-hub-py)

class DownloadError(Exception):
    pass

class PaperDownloader:
    # Realistic browser User-Agent reused across all requests
    USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    def __init__(self, output_dir: str, use_scihub: bool = False, unpaywall_email: Optional[str] = None,
                 use_zotero: bool = True, zotero_url: Optional[str] = None, max_workers: int = 4,
                 use_browser: bool = False):
        import threading
        import requests
        from requests.adapters import HTTPAdapter

        self.output_dir = Path(output_dir)
        self.use_scihub = use_scihub
        self.unpaywall_email = unpaywall_email
        self.max_workers = max(1, int(max_workers))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Dual-transport session: many publishers 403 a plain `requests` client
        # even for open-access content, and a browser-impersonating client gets
        # blocked by a *different* set of sites. This tries both. Sessions are
        # thread-local, so it is safe across the download workers.
        try:
            from .http_client import DualTransportSession, CURL_CFFI_AVAILABLE
        except ImportError:
            from http_client import DualTransportSession, CURL_CFFI_AVAILABLE
        self.session = DualTransportSession(self.USER_AGENT,
                                            pool_size=self.max_workers * 2)
        self.impersonating = CURL_CFFI_AVAILABLE

        # Guards shared mutable state (stats, failed_papers) during parallel runs
        self._lock = threading.Lock()

        # Real-browser fetcher (Firefox/Gecko) - the last-resort strategy for
        # Cloudflare-protected publishers that block every HTTP client
        # regardless of TLS fingerprint. Lazily started (see _get_browser()):
        # constructing a PaperDownloader should never eagerly launch a browser
        # process, only the first paper that actually falls through to this
        # strategy does. `None` = not yet attempted, `False` = tried and failed.
        self.use_browser = use_browser
        self._browser_fetcher = None
        self._browser_lock = threading.Lock()

        # Set up logger with better formatting
        self.logger = logging.getLogger("PaperDownloader")
        self.logger.setLevel(logging.INFO)
        
        # Remove any existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # File handler with detailed formatting
        handler = logging.FileHandler(self.output_dir / "download.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        self.logger.addHandler(handler)
        
        # Console handler for user feedback
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
        self.logger.addHandler(console)
        
        # Zotero translation server (primary PDF fetcher when available)
        self.zotero = None
        if use_zotero:
            try:
                from .zotero_client import ZoteroTranslationClient, DEFAULT_SERVER_URL
            except ImportError:
                from zotero_client import ZoteroTranslationClient, DEFAULT_SERVER_URL

            server_url = zotero_url or os.getenv("ZOTERO_TRANSLATION_SERVER") or DEFAULT_SERVER_URL
            # The client is always used: Zotero's open-access index works with no
            # local server. The server only adds the site-specific translator step.
            self.zotero = ZoteroTranslationClient(server_url, session=self.session)
            if self.zotero.is_available():
                self.logger.info(
                    f"Zotero resolver enabled (OA index + translation server at {server_url})")
            else:
                self.logger.warning(
                    f"Zotero translation server not reachable at {server_url} - using the OA index "
                    f"and citation_pdf_url only. Start it with: python scripts/setup_zotero.py")

        # Statistics
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'dois_found': 0,  # DOIs found via Crossref lookup
            'by_method': {
                'zotero': 0,
                'direct_pdf': 0,
                'arxiv': 0,
                'unpaywall': 0,
                'browser': 0,
                'scihub': 0
            },
            'time_by_method': {},  # method -> cumulative wall-clock seconds
        }

        # Track failed downloads
        self.failed_papers = []

    def download_from_bib(self, bib_file: str):
        import bibtexparser
        
        # Log session start with separator
        self.logger.info("="*80)
        self.logger.info(f"NEW DOWNLOAD SESSION STARTED")
        self.logger.info(f"Input file: {bib_file}")
        self.logger.info(f"Output directory: {self.output_dir}")
        self.logger.info(f"Unpaywall enabled: {bool(self.unpaywall_email)}")
        self.logger.info(f"Sci-Hub enabled: {self.use_scihub}")
        self.logger.info(f"Zotero translators: {'enabled (' + self.zotero.base_url + ')' if self.zotero else 'not available'}")
        self.logger.info("="*80)
        
        with open(bib_file, encoding="utf-8") as f:
            bib_db = bibtexparser.load(f)
        papers = bib_db.entries
        self.stats['total'] = len(papers)
        
        self.logger.info(f"Loaded {len(papers)} papers from {bib_file}")
        self.logger.info("")

        self._download_all(papers)

        # Log summary
        self._log_summary()
        self.close()

    def _download_all(self, papers: List[dict]):
        """
        Download all papers, in parallel when max_workers > 1.

        Each paper writes to a distinct destination file, so the only shared
        state is stats/failed_papers, which `_record_outcome` guards with a lock.
        """
        total = len(papers)
        if self.max_workers <= 1 or total <= 1:
            for i, entry in enumerate(papers, 1):
                self.logger.info(f"[{i}/{total}] " + "-"*60)
                self._download_paper(entry)
            return

        from concurrent.futures import ThreadPoolExecutor, as_completed

        self.logger.info(f"Downloading with {self.max_workers} parallel workers...")
        completed = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._download_paper, entry): entry for entry in papers}
            for future in as_completed(futures):
                completed += 1
                try:
                    future.result()
                except Exception as e:
                    # A worker crashing must not abort the whole run
                    self.logger.error(f"Worker error: {e}")
                    self._record_outcome(futures[future], 'failed')
                self.logger.info(f"[{completed}/{total}] complete")

    def download_from_ris(self, ris_file: str):
        import rispy
        
        # Log session start with separator
        self.logger.info("="*80)
        self.logger.info(f"NEW DOWNLOAD SESSION STARTED")
        self.logger.info(f"Input file: {ris_file}")
        self.logger.info(f"Output directory: {self.output_dir}")
        self.logger.info(f"Unpaywall enabled: {bool(self.unpaywall_email)}")
        self.logger.info(f"Sci-Hub enabled: {self.use_scihub}")
        self.logger.info(f"Zotero translators: {'enabled (' + self.zotero.base_url + ')' if self.zotero else 'not available'}")
        self.logger.info("="*80)
        
        with open(ris_file, encoding="utf-8") as f:
            entries = rispy.load(f)
        self.stats['total'] = len(entries)
        
        self.logger.info(f"Loaded {len(entries)} papers from {ris_file}")
        self.logger.info("")

        self._download_all(entries)

        # Log summary
        self._log_summary()
        self.close()

    def _lookup_doi_from_title(self, title: str) -> Optional[str]:
        """
        Look up DOI from paper title using Crossref API.
        
        Args:
            title: Paper title to search for
            
        Returns:
            DOI string if found, None otherwise
        """
        if not title or title == "Unknown":
            return None

        try:
            # Use Crossref API to search by title
            api_url = "https://api.crossref.org/works"
            params = self._crossref_params({
                'query.bibliographic': title,
                'rows': 1,
                'select': 'DOI,title,score'
            })

            r = self.session.get(api_url, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                items = data.get('message', {}).get('items', [])
                
                if items:
                    item = items[0]
                    # Check if the result is relevant (score > 50 indicates good match)
                    score = item.get('score', 0)
                    if score > 50:
                        doi = item.get('DOI')
                        returned_title = item.get('title', [''])[0]
                        
                        self.logger.info(f"  → Found DOI via Crossref: {doi}")
                        self.logger.debug(f"     Match score: {score}, Title: {returned_title[:60]}")
                        self.stats['dois_found'] += 1
                        return doi
                    else:
                        self.logger.debug(f"  → Crossref match score too low ({score}), skipping")
        except Exception as e:
            self.logger.debug(f"  → Crossref lookup error: {e}")
        
        return None

    def _record_outcome(self, entry: dict, outcome: str, elapsed: float = 0.0):
        """Thread-safely update statistics for one paper's download outcome.

        `outcome` is a by_method key on success, or 'skipped' / 'failed'.
        `elapsed` is wall-clock seconds spent on this paper, aggregated per
        method so the summary can report average time per strategy.
        """
        with self._lock:
            if outcome == 'skipped':
                self.stats['skipped'] += 1
            elif outcome == 'failed':
                self.stats['failed'] += 1
                self._store_failed_paper(entry)
            else:
                self.stats['success'] += 1
                self.stats['by_method'][outcome] = self.stats['by_method'].get(outcome, 0) + 1
                self.stats['time_by_method'][outcome] = \
                    self.stats['time_by_method'].get(outcome, 0.0) + elapsed

    def _download_paper(self, entry: dict):
        """Resolve and download one paper, recording the outcome in stats."""
        import time
        start = time.monotonic()
        outcome = self._resolve_and_download(entry)
        elapsed = time.monotonic() - start
        self._record_outcome(entry, outcome, elapsed)
        if outcome not in ('skipped', 'failed'):
            self.logger.info(f"  ⏱ {elapsed:.1f}s via {outcome}")
        return outcome

    def _resolve_and_download(self, entry: dict) -> str:
        """
        Attempt every strategy in priority order for a single paper.

        Returns the successful method name (a by_method key), 'skipped' if the
        PDF already exists, or 'failed' if no strategy worked. Does NOT mutate
        shared state, so it is safe to call from worker threads.
        """
        title = entry.get("title") or entry.get("TI") or "Unknown"
        doi = entry.get("doi") or entry.get("DO")
        url = entry.get("url") or entry.get("UR")
        arxiv_id = entry.get("arxiv_id")

        # Extract arXiv ID from URL if present (for @misc entries from arXiv)
        if not arxiv_id and url and "arxiv.org" in url.lower():
            # Handle both new-style (2101.00001) and old-style (math/0211159) IDs
            match = re.search(r'arxiv\.org/(?:abs|pdf)/([a-z\-]+/\d{7}|\d{4}\.\d{4,5})', url, re.IGNORECASE)
            if match:
                arxiv_id = match.group(1)

        # If no DOI, try to look it up via Crossref using the title
        if not doi and not arxiv_id and title != "Unknown":
            doi = self._lookup_doi_from_title(title)

        pdf_url = None
        paper_id = doi or arxiv_id or title or url
        safe_name = self._safe_filename(paper_id)
        dest_path = self.output_dir / f"{safe_name}.pdf"

        # Skip if already downloaded
        if dest_path.exists():
            self.logger.info(f"SKIP: {title[:80]}")
            self.logger.info(f"  → Already downloaded: {dest_path.name}")
            return 'skipped'

        self.logger.info(f"PROCESSING: {title[:80]}")
        if doi:
            self.logger.info(f"  DOI: {doi}")
        if arxiv_id:
            self.logger.info(f"  arXiv ID: {arxiv_id}")
        if url and not arxiv_id:
            self.logger.info(f"  URL: {url[:100]}")

        # 0. Zotero resolver chain (primary) - mirrors the desktop app's
        #    "Add by identifier" flow: doi -> url -> pmcid -> OA index, with the
        #    web translators extracting the PDF link from each landing page.
        if self.zotero and (doi or url or entry.get("pmcid")):
            self.logger.info(f"  → Trying Zotero resolver chain...")
            found_any = False
            for pdf_url, referer, method in self.zotero.iter_pdf_candidates(
                    doi=doi, url=url, pmcid=entry.get("pmcid")):
                found_any = True
                self.logger.info(f"  → [{method}] candidate: {pdf_url[:80]}")
                if self._download_pdf(pdf_url, dest_path, referer=referer):
                    self.logger.info(f"  ✓ SUCCESS via {method}")
                    return 'zotero'
            if not found_any:
                self.logger.info(f"  → Zotero: no candidates found, falling back")

        # 0.5. Fast path: known Cloudflare-protected publishers block every
        #    HTTP-based strategy below regardless of TLS fingerprint (measured:
        #    Elsevier 4/49, Wiley 0/9 - see docs/ZOTERO_HOW_IT_WORKS.md). Jump
        #    straight to the real-browser fetcher instead of burning time on
        #    attempts that are known to fail for these domains.
        if self.use_browser and url and self._is_browser_required_domain(url):
            self.logger.info(f"  → Known bot-protected publisher - trying browser fetcher directly...")
            browser = self._get_browser()
            if browser and browser.fetch_pdf(self._browser_target(doi, url), dest_path, referer=None):
                self.logger.info(f"  ✓ SUCCESS via browser (fast path)")
                return 'browser'

        # 1. Try direct PDF link
        if url and url.endswith(".pdf"):
            self.logger.info(f"  → Trying direct PDF link...")
            if self._download_pdf(url, dest_path):
                self.logger.info(f"  ✓ SUCCESS via direct PDF link")
                return 'direct_pdf'

        # 2. Try arXiv direct (check arXiv ID first, then DOI, then URL)
        if arxiv_id or (doi and "arxiv" in doi.lower()) or (url and "arxiv" in url.lower()):
            self.logger.info(f"  → Trying arXiv...")
            pdf_url = self._get_arxiv_pdf(entry)
            if pdf_url and self._download_pdf(pdf_url, dest_path):
                self.logger.info(f"  ✓ SUCCESS via arXiv")
                return 'arxiv'

        # 2.5. Try bioRxiv/medRxiv (common for biomedical preprints)
        if url and ("biorxiv.org" in url.lower() or "medrxiv.org" in url.lower()):
            self.logger.info(f"  → Trying bioRxiv/medRxiv...")
            pdf_url = self._get_biorxiv_pdf(url)
            if pdf_url and self._download_pdf(pdf_url, dest_path):
                self.logger.info(f"  ✓ SUCCESS via bioRxiv/medRxiv")
                return 'biorxiv'

        # 3. Try Unpaywall (open access)
        if doi and self.unpaywall_email:
            self.logger.info(f"  → Checking Unpaywall...")
            pdf_url = self._get_unpaywall_pdf(doi)
            if pdf_url:
                self.logger.info(f"  → Found OA version: {pdf_url[:80]}")
                if self._download_pdf(pdf_url, dest_path):
                    self.logger.info(f"  ✓ SUCCESS via Unpaywall")
                    return 'unpaywall'
            else:
                self.logger.info(f"  → No open access version found")
        elif doi and not self.unpaywall_email:
            self.logger.warning(f"  ⚠ Unpaywall email not set, skipping OA check")

        # 3.2. Try Crossref API for full-text links
        if doi:
            self.logger.info(f"  → Checking Crossref for full-text...")
            pdf_url = self._get_crossref_pdf(doi, title)
            if pdf_url:
                self.logger.info(f"  → Found via Crossref: {pdf_url[:80]}")
                if self._download_pdf(pdf_url, dest_path):
                    self.logger.info(f"  ✓ SUCCESS via Crossref")
                    return 'crossref'

        # 3.5. Try PubMed Central (if PMID or PMC ID available)
        pmid = entry.get("pmid") or entry.get("PMID")
        if pmid or (url and "pubmed.ncbi.nlm.nih.gov" in url):
            self.logger.info(f"  → Checking PubMed Central...")
            if not pmid and url:
                match = re.search(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d+)', url)
                if match:
                    pmid = match.group(1)

            if pmid:
                pdf_url = self._get_pmc_pdf(pmid)
                if pdf_url and self._download_pdf(pdf_url, dest_path):
                    self.logger.info(f"  ✓ SUCCESS via PubMed Central")
                    return 'pmc'

        # 4. Try common publisher patterns (MDPI, Frontiers, etc.)
        if url and doi:
            self.logger.info(f"  → Trying publisher-specific patterns...")
            pdf_url = self._get_publisher_pdf(url, doi)
            if pdf_url and self._download_pdf(pdf_url, dest_path):
                self.logger.info(f"  ✓ SUCCESS via publisher pattern")
                return 'publisher'

        # 4.6. Try scraping HTML page for PDF link
        if url:
            self.logger.info(f"  → Trying to scrape PDF link from page...")
            pdf_url = self._try_scrape_pdf_link(url)
            if pdf_url:
                self.logger.info(f"  → Found PDF link: {pdf_url[:80]}")
                if self._download_pdf(pdf_url, dest_path):
                    self.logger.info(f"  ✓ SUCCESS via HTML scraping")
                    return 'scraping'

        # 4.7. Last resort: real-browser fetcher (Firefox/Gecko). Slow, so it
        #    only runs here - after every cheaper HTTP-based strategy failed.
        #    (Skipped if the 0.5 fast path above already tried it for this URL.)
        if self.use_browser and (url or doi) and not (url and self._is_browser_required_domain(url)):
            target = self._browser_target(doi, url)
            self.logger.info(f"  → Trying real-browser fetcher (last resort): {target[:80]}")
            browser = self._get_browser()
            if browser:
                if browser.fetch_pdf(target, dest_path, referer=None):
                    self.logger.info(f"  ✓ SUCCESS via browser")
                    return 'browser'

        # 5. Fallback: Sci-Hub (if enabled)
        if self.use_scihub and doi:
            self.logger.info(f"  → Trying Sci-Hub...")
            pdf_path = self._get_scihub_pdf(doi, dest_path)
            if pdf_path and dest_path.exists():
                self.logger.info(f"  ✓ SUCCESS via Sci-Hub")
                return 'scihub'

        # 6. Nothing worked
        self.logger.error(f"  ✗ FAILED: Could not download from any source")
        if not doi and not arxiv_id:
            self.logger.error(f"  → No DOI or arXiv ID available")
        return 'failed'

    def _download_pdf(self, pdf_url: str, dest_path: Path, retry_count: int = 0, max_retries: int = 3,
                      referer: Optional[str] = None) -> bool:
        import requests
        import time

        try:
            self.logger.info(f"Downloading from: {pdf_url}")

            # Per-request headers (User-Agent comes from the shared session)
            headers = {
                'Accept': 'application/pdf,application/octet-stream,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'DNT': '1',
                'Upgrade-Insecure-Requests': '1',
                'Referer': referer or 'https://www.google.com/',
            }

            timeout = 15 if 'arxiv.org' in pdf_url.lower() else 30
            r = self.session.get(pdf_url, timeout=timeout, headers=headers,
                                 allow_redirects=True, stream=True)

            if r.status_code == 200:
                content_type = r.headers.get('content-type', '').lower()

                # Peek at the first bytes to confirm it's a PDF before saving
                chunks = r.iter_content(chunk_size=65536)
                try:
                    first = next(chunks)
                except StopIteration:
                    first = b''

                is_pdf = 'application/pdf' in content_type or first[:4] == b'%PDF'
                if is_pdf:
                    # Stream to disk in chunks instead of buffering the whole file
                    with open(dest_path, "wb") as f:
                        if first:
                            f.write(first)
                        for chunk in chunks:
                            if chunk:
                                f.write(chunk)
                    file_size = dest_path.stat().st_size
                    self.logger.info(f"Successfully saved PDF ({file_size} bytes)")

                    # Verify file is not corrupt (PDF should be > 5KB)
                    if file_size > 5000:
                        return True
                    else:
                        self.logger.warning(f"PDF file too small ({file_size} bytes), likely corrupt")
                        dest_path.unlink()
                        return False
                else:
                    self.logger.warning(f"Downloaded content is not a PDF (content-type: {content_type})")
            elif r.status_code == 403:
                self.logger.warning(f"HTTP 403 Forbidden - likely IP blocked or requires authentication")
            elif r.status_code == 429:
                # Too many requests - retry with backoff
                if retry_count < max_retries:
                    wait_time = min(2 ** retry_count, 10)  # Exponential backoff: 1, 2, 4, 8, 10 seconds
                    self.logger.warning(f"HTTP 429 Too Many Requests - retrying in {wait_time}s ({retry_count + 1}/{max_retries})")
                    time.sleep(wait_time)
                    return self._download_pdf(pdf_url, dest_path, retry_count + 1, max_retries, referer=referer)
                else:
                    self.logger.error(f"HTTP 429 - max retries exceeded")
            else:
                self.logger.warning(f"HTTP {r.status_code} for URL: {pdf_url}")
        except Exception as e:
            # Covers requests.* and curl_cffi.* transport errors alike
            name = type(e).__name__
            if "Timeout" in name:
                self.logger.warning(f"Request timeout - server took too long to respond")
            elif "Connection" in name:
                self.logger.warning(f"Connection error - check internet or server availability")
            else:
                self.logger.error(f"PDF download error: {pdf_url} - {e}")
        return False

    def _crossref_params(self, extra: Optional[dict] = None) -> dict:
        """Crossref query params including a mailto for the faster 'polite pool'."""
        params = dict(extra or {})
        if self.unpaywall_email:
            params['mailto'] = self.unpaywall_email
        return params

    def _get_unpaywall_pdf(self, doi: str) -> Optional[str]:
        api = f"https://api.unpaywall.org/v2/{doi}?email={self.unpaywall_email}"
        try:
            r = self.session.get(api, timeout=15)
            if r.status_code == 200:
                data = r.json()
                oa_location = data.get("best_oa_location")
                if oa_location and oa_location.get("url_for_pdf"):
                    return oa_location["url_for_pdf"]
        except Exception as e:
            self.logger.error(f"Unpaywall error for DOI {doi}: {e}")
        return None
    
    def _get_crossref_pdf(self, doi: str, title: str = "") -> Optional[str]:
        """
        Check Crossref API for full-text links and license information.
        Some publishers provide direct PDF links via Crossref.
        """
        try:
            # Query Crossref for this DOI
            api_url = f"https://api.crossref.org/works/{doi}"
            r = self.session.get(api_url, params=self._crossref_params(), timeout=10)
            
            if r.status_code == 200:
                data = r.json().get('message', {})
                
                # Check for link information
                links = data.get('link', [])
                for link in links:
                    if link.get('content-type') == 'application/pdf':
                        url = link.get('URL')
                        if url:
                            self.logger.info(f"  → Found Crossref PDF link: {url[:80]}")
                            return url
                
                # Check for resource links
                resource = data.get('resource', {})
                primary_url = resource.get('primary', {}).get('URL')
                if primary_url and '.pdf' in primary_url.lower():
                    self.logger.info(f"  → Found Crossref resource: {primary_url[:80]}")
                    return primary_url
                    
        except Exception as e:
            self.logger.debug(f"Crossref full-text lookup error for DOI {doi}: {e}")
        
        return None

    # New-style (2101.00001) or old-style (math/0211159, cond-mat/0211159) arXiv IDs
    _ARXIV_ID_RE = re.compile(r'([a-z\-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})(v\d+)?', re.IGNORECASE)

    def _get_arxiv_pdf(self, entry: dict) -> Optional[str]:
        arxiv_id = None

        # Check direct arXiv ID field
        if entry.get("arxiv_id"):
            arxiv_id = entry["arxiv_id"]
        # Check DOI for arXiv pattern (e.g. 10.48550/arXiv.2101.00001)
        elif entry.get("doi") and "arxiv" in entry["doi"].lower():
            m = self._ARXIV_ID_RE.search(entry["doi"])
            if m:
                arxiv_id = m.group(1)
        # Check URL for arXiv pattern
        elif entry.get("url") and "arxiv" in entry["url"].lower():
            m = self._ARXIV_ID_RE.search(entry["url"])
            if m:
                arxiv_id = m.group(1)

        if arxiv_id:
            # Strip a trailing version suffix (vN) only, preserving old-style IDs
            arxiv_id = re.sub(r'v\d+$', '', arxiv_id.strip())
            # /pdf/ serves the PDF directly; /abs/ is an HTML page and does NOT redirect
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
            self.logger.info(f"Constructed arXiv PDF URL: {pdf_url}")
            return pdf_url

        return None
    
    def _get_biorxiv_pdf(self, url: str) -> Optional[str]:
        """
        Construct PDF URL for bioRxiv/medRxiv preprints.
        bioRxiv and medRxiv have very predictable PDF URLs.
        """
        try:
            import re
            
            # bioRxiv/medRxiv URLs look like:
            # https://www.biorxiv.org/content/10.1101/2021.01.01.000001v1
            # https://www.medrxiv.org/content/10.1101/2021.01.01.000001v1
            
            # Extract DOI pattern
            match = re.search(r'/(10\.1101/[\d.]+)(v\d+)?', url)
            if match:
                doi_part = match.group(1)
                version = match.group(2) or 'v1'  # Default to v1 if no version
                
                # Determine if it's biorxiv or medrxiv
                if 'medrxiv' in url.lower():
                    base = 'https://www.medrxiv.org'
                else:
                    base = 'https://www.biorxiv.org'
                
                # Construct PDF URL
                pdf_url = f"{base}/content/{doi_part}{version}.full.pdf"
                self.logger.info(f"  → Constructed bioRxiv/medRxiv PDF URL: {pdf_url[:80]}")
                return pdf_url
                
        except Exception as e:
            self.logger.debug(f"bioRxiv/medRxiv URL construction error: {e}")
        
        return None
    
    def _get_pmc_pdf(self, pmid: str) -> Optional[str]:
        """
        Try to get a direct PDF link for a PMC article using its PMID.

        The old approach returned `/pmc/articles/{pmcid}/pdf/` (a directory URL
        that serves HTML, not a PDF) and NCBI blocks scripted access to article
        pages with HTTP 403 anyway. Instead we use the documented NCBI Open
        Access web service, which returns the real PDF href when the article is
        in the OA subset, then fall back to Europe PMC.

        Note: for reliable PMC downloads, run the Zotero translation server -
        its PMC translator resolves the exact PDF URL in a browser-like context.
        """
        from xml.etree import ElementTree as ET

        try:
            # Resolve PMID -> PMCID
            pmc_api = f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={pmid}&format=json"
            r = self.session.get(pmc_api, timeout=10)
            pmcid = None
            if r.status_code == 200:
                records = r.json().get('records', [])
                if records:
                    pmcid = records[0].get('pmcid')

            if not pmcid:
                self.logger.debug(f"  → No US PMC record, trying Europe PMC...")
                return self._get_europepmc_pdf(pmid)

            self.logger.info(f"  → Found PMC ID: {pmcid}")

            # Query the NCBI OA service for a direct PDF href
            oa_api = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}"
            r = self.session.get(oa_api, timeout=10)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                for link in root.findall('.//link'):
                    if link.get('format') == 'pdf' and link.get('href'):
                        # OA hrefs use ftp://; serve over https from the same host
                        href = link.get('href')
                        pdf_url = href.replace('ftp://ftp.ncbi.nlm.nih.gov', 'https://ftp.ncbi.nlm.nih.gov')
                        self.logger.info(f"  → PMC OA PDF: {pdf_url[:80]}")
                        return pdf_url

            # No direct OA PDF - try Europe PMC
            self.logger.debug(f"  → No OA PDF for {pmcid}, trying Europe PMC...")
            return self._get_europepmc_pdf(pmid)

        except Exception as e:
            self.logger.debug(f"PubMed Central error for PMID {pmid}: {e}")
            return self._get_europepmc_pdf(pmid)
    
    def _get_europepmc_pdf(self, pmid: str) -> Optional[str]:
        """
        Try to get PDF from Europe PubMed Central.
        Europe PMC often has papers not in US PMC.
        """
        try:
            # Check Europe PMC for full text availability
            api_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search"
            params = {
                'query': f'EXT_ID:{pmid}',
                'format': 'json',
                'resultType': 'core'
            }

            r = self.session.get(api_url, params=params, timeout=10)
            if r.status_code == 200:
                data = r.json()
                results = data.get('resultList', {}).get('result', [])
                
                if results:
                    result = results[0]
                    # Check if full text is available
                    has_pdf = result.get('hasPDF')
                    pmcid = result.get('pmcid')
                    
                    if has_pdf == 'Y' and pmcid:
                        # Construct Europe PMC PDF URL
                        pdf_url = f"https://europepmc.org/articles/{pmcid}?pdf=render"
                        self.logger.info(f"  → Found in Europe PMC: {pmcid}")
                        return pdf_url
                    else:
                        self.logger.debug(f"  → Paper in Europe PMC but no PDF available")
                        
        except Exception as e:
            self.logger.debug(f"Europe PMC error for PMID {pmid}: {e}")
        
        return None
    
    def _get_publisher_pdf(self, url: str, doi: str) -> Optional[str]:
        """
        Try to construct PDF URL from common publisher patterns.
        Many publishers have predictable PDF URL structures.
        """
        url_lower = url.lower()
        
        # MDPI (mdpi.com)
        if "mdpi.com" in url_lower:
            # Pattern: https://www.mdpi.com/XXXX/pdf
            if "/pdf" not in url_lower:
                pdf_url = url.rstrip('/') + '/pdf'
                self.logger.info(f"  → Trying MDPI pattern: {pdf_url[:80]}")
                return pdf_url
        
        # Frontiers (frontiersin.org)
        elif "frontiersin.org" in url_lower:
            # Pattern: add /pdf to the end
            if "/pdf" not in url_lower and "/full" in url_lower:
                pdf_url = url.replace('/full', '/pdf')
                self.logger.info(f"  → Trying Frontiers pattern: {pdf_url[:80]}")
                return pdf_url
        
        # Nature (nature.com)
        elif "nature.com" in url_lower:
            # Pattern: replace /articles/ with /articles/
            if ".pdf" not in url_lower:
                pdf_url = url.rstrip('/') + '.pdf'
                self.logger.info(f"  → Trying Nature pattern: {pdf_url[:80]}")
                return pdf_url
        
        # IEEE (ieeexplore.ieee.org)
        elif "ieeexplore.ieee.org" in url_lower:
            # Extract document ID and try to build PDF URL
            import re
            match = re.search(r'/document/(\d+)', url)
            if match:
                doc_id = match.group(1)
                pdf_url = f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={doc_id}"
                self.logger.info(f"  → Trying IEEE pattern: {pdf_url[:80]}")
                return pdf_url
        
        # ScienceDirect (sciencedirect.com)
        elif "sciencedirect.com" in url_lower:
            # Try to use DOI-based PDF access
            if doi:
                # Pattern: https://www.sciencedirect.com/science/article/pii/XXXXX/pdfft
                if "/pii/" in url_lower:
                    pdf_url = url.split('?')[0].rstrip('/') + '/pdfft?isDTMRedir=true&download=true'
                    self.logger.info(f"  → Trying ScienceDirect pattern: {pdf_url[:80]}")
                    return pdf_url
        
        # Springer (springer.com, link.springer.com)
        elif "springer.com" in url_lower:
            if "/chapter/" in url_lower or "/article/" in url_lower:
                # Try adding .pdf extension
                pdf_url = url.split('?')[0].rstrip('/') + '.pdf'
                self.logger.info(f"  → Trying Springer pattern: {pdf_url[:80]}")
                return pdf_url
        
        # PLOS (plos.org, plosone.org)
        elif "plos" in url_lower:
            # Pattern: replace /article/ with /article/file/
            if "/article/" in url_lower and "file" not in url_lower:
                pdf_url = url.replace('/article?', '/article/file?').replace('id=', 'id=') + '&type=printable'
                self.logger.info(f"  → Trying PLOS pattern: {pdf_url[:80]}")
                return pdf_url
        
        return None

    def _try_scrape_pdf_link(self, url: str) -> Optional[str]:
        """
        Try to scrape HTML page for PDF download link.
        Works for many open access repositories and publishers.
        Enhanced with more patterns and better error handling.
        """
        from bs4 import BeautifulSoup

        try:
            headers = {
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            r = self.session.get(url, timeout=15, headers=headers)
            if r.status_code != 200:
                return None
            
            soup = BeautifulSoup(r.content, 'html.parser')
            
            # Aggressively search for PDFs in different formats
            pdf_patterns = [
                # Direct PDF links
                {'name': 'a', 'href': lambda x: x and x.endswith('.pdf')},
                {'name': 'a', 'href': lambda x: x and '.pdf' in x.lower()},
                # Download buttons with "PDF", "download", "full text"
                {'name': 'a', 'string': lambda x: x and any(w in str(x).lower() for w in ['pdf', 'download', 'full text', 'full-text'])},
                {'name': 'button', 'string': lambda x: x and any(w in str(x).lower() for w in ['pdf', 'download', 'full text'])},
                {'name': 'a', 'class_': lambda x: x and any(c in str(x).lower() for c in ['pdf', 'download', 'fulltext'])},
                # Meta tags for PDF
                {'name': 'meta', 'attrs': {'name': 'citation_pdf_url'}},
                {'name': 'meta', 'attrs': {'property': 'og:pdf'}},
                # Publisher specific
                {'name': 'a', 'attrs': {'title': lambda x: x and 'PDF' in str(x)}},
                {'name': 'a', 'attrs': {'data-track-action': 'download pdf'}},
                {'name': 'a', 'attrs': {'href': lambda x: x and 'pdf' in x.lower() and 'download' in x.lower()}},
            ]
            
            for pattern in pdf_patterns:
                if 'attrs' in pattern and isinstance(pattern.get('attrs', {}), dict):
                    if any(callable(v) for v in pattern['attrs'].values()):
                        # Skip patterns with callables in attrs
                        continue
                    # Meta tag with simple attrs
                    if pattern['name'] == 'meta':
                        tag = soup.find(pattern['name'], attrs=pattern['attrs'])
                        if tag and tag.get('content'):
                            pdf_url = tag['content']
                            if pdf_url and not pdf_url.startswith('http'):
                                from urllib.parse import urljoin
                                pdf_url = urljoin(url, pdf_url)
                            return pdf_url
                else:
                    # Link patterns
                    tags = soup.find_all(pattern['name'], **{k: v for k, v in pattern.items() if k != 'name'})
                    for tag in tags:
                        href = tag.get('href')
                        if href:
                            if not href.startswith('http'):
                                from urllib.parse import urljoin
                                href = urljoin(url, href)
                            if '.pdf' in href.lower():
                                return href
            
            # Check JavaScript PDF links (common in modern sites)
            import re
            # Look for URLs in script tags
            js_pdf_patterns = [
                r'https?://[^"\'\s<>]+\.pdf',
                r'"url":\s*"([^"]+\.pdf[^"]*)"',
                r'pdfUrl["\']?\s*[:=]\s*["\']([^"\']+\.pdf[^"\']*)["\']',
            ]
            for pattern in js_pdf_patterns:
                matches = re.findall(pattern, r.text)
                if matches:
                    return matches[0]
            
            # Repository-specific patterns
            url_lower = url.lower()
            
            # ACM Digital Library: Construct PDF URL
            if 'dl.acm.org' in url_lower:
                match = re.search(r'/doi/(?:abs/)?(\d+\.\d+/\d+)', url)
                if match:
                    doi = match.group(1)
                    pdf_url = f"https://dl.acm.org/doi/pdf/{doi}"
                    return pdf_url
            
            # Springer: Try chapter PDF
            if 'link.springer.com/chapter/' in url_lower:
                if not url.endswith('/pdf'):
                    pdf_url = url.rstrip('/') + '.pdf'
                    return pdf_url
            
            # IEEE Xplore: Try PDF endpoint
            if 'ieeexplore.ieee.org' in url_lower:
                match = re.search(r'/document/(\d+)', url)
                if match:
                    doc_id = match.group(1)
                    pdf_url = f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={doc_id}"
                    return pdf_url
            
            # Institutional repositories
            if any(x in url_lower for x in ['repository', 'eprints', 'dspace', 'handle', 'ir.ucc']):
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    if any(x in href.lower() for x in ['download', 'bitstream', 'pdf', 'fulltext']):
                        if not href.startswith('http'):
                            from urllib.parse import urljoin
                            href = urljoin(url, href)
                        if '.pdf' in href.lower():
                            return href
                        
        except Exception as e:
            self.logger.debug(f"HTML scraping error for {url}: {e}")
        
        return None

    def _is_browser_required_domain(self, url: str) -> bool:
        """Whether `url` is a publisher known to block every HTTP strategy."""
        try:
            from .browser_fetcher import is_browser_required_domain
        except ImportError:
            from browser_fetcher import is_browser_required_domain
        return is_browser_required_domain(url)

    # Search sources hand us a record/landing URL on the DATABASE, not the
    # publisher - e.g. Scopus gives scopus.com/inward/record.uri and PubMed
    # gives pubmed.ncbi.nlm.nih.gov/<pmid>/. Those pages are login-walled and
    # have no PDF, so pointing the browser at them is futile. The DOI is the
    # authoritative route: https://doi.org/<DOI> redirects to the real
    # publisher article page (exactly what Zotero's `doi` resolver uses).
    _AGGREGATOR_HOSTS = (
        "scopus.com", "pubmed.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
        "semanticscholar.org", "webofscience.com", "lens.org",
        "europepmc.org", "dimensions.ai",
    )

    def _browser_target(self, doi, url):
        """Best URL to hand the browser: the DOI resolver when `url` is a
        database record page (or missing), otherwise the URL itself."""
        if doi and (not url or any(h in url.lower() for h in self._AGGREGATOR_HOSTS)):
            return f"https://doi.org/{doi}"
        return url or f"https://doi.org/{doi}"

    def _get_browser(self):
        """
        Lazily start the real-browser fetcher on first use.

        Returns None if unavailable (not installed, or failed to launch);
        `False` is cached internally so we don't retry launching for every
        paper in a run once it's known to be broken.
        """
        if not self.use_browser:
            return None
        with self._browser_lock:
            if self._browser_fetcher is None:
                try:
                    from .browser_fetcher import BrowserFetcher
                except ImportError:
                    from browser_fetcher import BrowserFetcher
                self.logger.info("Starting browser fetcher (Firefox) - first use may take a few seconds...")
                fetcher = BrowserFetcher()
                if fetcher.is_available():
                    self._browser_fetcher = fetcher
                    engine = "Camoufox (anti-detect)" if fetcher.using_camoufox else "stock Firefox"
                    self.logger.info(f"Browser fetcher ready [{engine}]")
                    if not fetcher.using_camoufox:
                        self.logger.warning(
                            "  Using stock Playwright Firefox - navigator.webdriver is visible and "
                            "Cloudflare-protected publishers will likely still challenge it. "
                            "Install camoufox for the fix: pip install camoufox[geoip] && python -m camoufox fetch"
                        )
                else:
                    self.logger.warning(
                        f"Browser fetcher unavailable ({fetcher._error}). "
                        f"Run: pip install playwright && playwright install firefox"
                    )
                    self._browser_fetcher = False
        return self._browser_fetcher or None

    def _get_scihub_pdf(self, doi: str, dest_path: Path) -> Optional[Path]:
        """
        Try to download from Sci-Hub using the scihub library.
        Note: The scihub library API varies. This tries multiple methods.
        """
        try:
            from scihub import SciHub
            sh = SciHub()
            
            # Try different API methods (library versions vary)
            try:
                # Method 1: fetch with destination parameter
                result = sh.fetch(doi, destination=str(dest_path.parent), path=dest_path.name)
            except TypeError:
                try:
                    # Method 2: fetch without path, then move file
                    result = sh.fetch(doi)
                    if result and 'pdf' in result:
                        pdf_path = result['pdf']
                        if os.path.exists(pdf_path):
                            import shutil
                            shutil.move(pdf_path, dest_path)
                            return dest_path
                except:
                    # Method 3: download method (older API)
                    result = sh.download(doi, destination=str(dest_path.parent))
            
            if dest_path.exists():
                return dest_path
            else:
                self.logger.warning(f"Sci-Hub fetch returned no result for: {doi}")
                
        except ImportError:
            self.logger.error("Sci-Hub library not installed. Install with: pip install scihub")
        except AttributeError as e:
            self.logger.error(f"Sci-Hub API error (library may have changed): {e}")
            self.logger.info("Try updating scihub library or using an alternative implementation")
        except Exception as e:
            self.logger.error(f"Sci-Hub error for DOI {doi}: {e}")
        
        return None

    def _safe_filename(self, name: str) -> str:
        """
        Build a filesystem-safe filename from an identifier.

        Truncating a long title to 80 chars can make two different papers map to
        the same name (the second is then wrongly skipped as "already
        downloaded"). Append a short hash of the full identifier so distinct
        papers never collide, while equal identifiers stay stable (idempotent
        skip-if-exists still works).
        """
        import hashlib

        cleaned = "".join(c if c.isalnum() else "_" for c in name)
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
        return f"{cleaned[:70]}_{digest}"
    
    def _store_failed_paper(self, entry: dict):
        """
        Convert bibtex entry to Paper object and store in failed_papers list.
        
        Args:
            entry: BibTeX entry dictionary
        """
        from datetime import date
        
        # Import Paper model (assuming it's in src.models)
        try:
            import sys
            from pathlib import Path
            # Add src to path if not already there
            src_path = Path(__file__).parent.parent
            if str(src_path) not in sys.path:
                sys.path.insert(0, str(src_path))
            from models import Paper
        except ImportError:
            self.logger.error("Failed to import Paper model - cannot store failed papers")
            return
        
        try:
            # Extract fields from bibtex entry
            title = entry.get("title") or entry.get("TI") or "Unknown"
            
            # Parse authors
            authors = []
            author_field = entry.get("author") or entry.get("AU") or ""
            if author_field:
                # Split by "and" for bibtex format
                authors = [a.strip() for a in author_field.split(" and ")]
            
            # Create Paper object
            paper = Paper(title=title)
            paper.authors = authors
            paper.abstract = entry.get("abstract") or entry.get("AB")
            paper.doi = entry.get("doi") or entry.get("DO")
            paper.pmid = entry.get("pmid") or entry.get("PMID")
            paper.arxiv_id = entry.get("arxiv_id")
            paper.journal = entry.get("journal") or entry.get("JO")
            paper.url = entry.get("url") or entry.get("UR")
            paper.volume = entry.get("volume")
            paper.issue = entry.get("number") or entry.get("issue")
            paper.pages = entry.get("pages")
            paper.publisher = entry.get("publisher")
            paper.issn = entry.get("issn")
            
            # Parse year to date
            year_str = entry.get("year")
            if year_str:
                try:
                    year = int(year_str)
                    paper.publication_date = date(year, 1, 1)
                except (ValueError, TypeError):
                    pass
            
            self.failed_papers.append(paper)
            
        except Exception as e:
            self.logger.error(f"Failed to store failed paper entry: {e}")
    
    def get_failed_papers(self):
        """
        Get list of papers that failed to download.
        
        Returns:
            List of Paper objects
        """
        return self.failed_papers
    
    def close(self):
        """
        Release resources held by this downloader (currently: the browser
        fetcher, if one was started). Safe to call even if never used.
        """
        if self._browser_fetcher:
            self._browser_fetcher.close()

    def _log_summary(self):
        """Log download session summary with statistics"""
        self.logger.info("")
        self.logger.info("="*80)
        self.logger.info("DOWNLOAD SESSION SUMMARY")
        self.logger.info("="*80)
        self.logger.info(f"Total papers: {self.stats['total']}")
        self.logger.info(f"Successfully downloaded: {self.stats['success']} ({self.stats['success']/max(self.stats['total'],1)*100:.1f}%)")
        self.logger.info(f"Already downloaded (skipped): {self.stats['skipped']}")
        self.logger.info(f"Failed to download: {self.stats['failed']} ({self.stats['failed']/max(self.stats['total'],1)*100:.1f}%)")
        if self.stats.get('dois_found', 0) > 0:
            self.logger.info(f"DOIs found via Crossref: {self.stats['dois_found']}")
        self.logger.info("")
        self.logger.info("Downloads by method (count, avg time/paper):")
        times = self.stats.get('time_by_method', {})
        for method, count in self.stats['by_method'].items():
            if count > 0:
                avg = times.get(method, 0.0) / count if count else 0.0
                self.logger.info(f"  {method.replace('_', ' ').title()}: {count}  (avg {avg:.1f}s)")
        self.logger.info("="*80)
        self.logger.info("")

# Example usage:
# downloader = PaperDownloader(output_dir="results/pdfs", use_scihub=True, unpaywall_email="your@email.com")
# downloader.download_from_bib("results/references.bib")
# downloader.download_from_ris("results/references.ris")
