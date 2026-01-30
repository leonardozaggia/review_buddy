"""
Paper Downloader Module

Downloads PDFs for papers listed in a .bib or .ris file, prioritizing open access sources.
Supports fallback strategies and optional Sci-Hub integration.
"""
import os
import logging
from typing import List, Optional
from pathlib import Path

# External dependencies: requests, unpaywall, bibtexparser, rispy
# Sci-Hub support: requires user opt-in and third-party library (e.g., sci-hub-py)

class DownloadError(Exception):
    pass

class PaperDownloader:
    def __init__(
        self, 
        output_dir: str, 
        use_scihub: bool = False, 
        unpaywall_email: Optional[str] = None,
        use_zotero: bool = True,
        zotero_server_url: Optional[str] = None,
        use_browser: bool = False,
        browser_headless: bool = True
    ):
        self.output_dir = Path(output_dir)
        self.use_scihub = use_scihub
        self.unpaywall_email = unpaywall_email
        self.use_zotero = use_zotero
        self.zotero_server_url = zotero_server_url or "http://localhost:1969"
        self.use_browser = use_browser
        self.browser_headless = browser_headless
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
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
        
        # Initialize Zotero Translation Client (if enabled)
        self.zotero_client = None
        if self.use_zotero:
            try:
                from .zotero_client import ZoteroTranslationClient
                self.zotero_client = ZoteroTranslationClient(
                    server_url=self.zotero_server_url,
                    timeout=30
                )
                if self.zotero_client.is_available():
                    self.logger.info(f"Zotero Translation Server available at {self.zotero_server_url}")
                else:
                    self.logger.warning(f"Zotero Translation Server not available at {self.zotero_server_url}")
                    self.logger.warning("  → Zotero will be skipped. To enable: docker run -d -p 1969:1969 zotero/translation-server")
            except ImportError as e:
                self.logger.warning(f"Failed to import Zotero client: {e}")
                self.zotero_client = None
        
        # Initialize Browser Downloader (if enabled)
        self.browser_downloader = None
        if self.use_browser:
            try:
                from .browser_downloader import BrowserDownloader
                self.browser_downloader = BrowserDownloader(
                    output_dir=str(self.output_dir),
                    headless=self.browser_headless
                )
                self.logger.info(f"Browser downloader enabled (headless={self.browser_headless})")
                self.logger.info(f"  → Session data: {self.browser_downloader.user_data_dir}")
            except ImportError as e:
                self.logger.warning(f"Failed to import browser downloader: {e}")
                self.logger.warning("  → Install playwright: pip install playwright && playwright install chromium")
                self.browser_downloader = None
        
        # Statistics
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'dois_found': 0,  # DOIs found via Crossref lookup
            'by_method': {
                'direct_pdf': 0,
                'zotero': 0,
                'arxiv': 0,
                'unpaywall': 0,
                'browser': 0,
                'scihub': 0
            }
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
        self.logger.info(f"Zotero enabled: {self.use_zotero and self.zotero_client is not None}")
        self.logger.info(f"Browser enabled: {self.use_browser and self.browser_downloader is not None}")
        self.logger.info(f"Unpaywall enabled: {bool(self.unpaywall_email)}")
        self.logger.info(f"Sci-Hub enabled: {self.use_scihub}")
        self.logger.info("="*80)
        
        with open(bib_file, encoding="utf-8") as f:
            bib_db = bibtexparser.load(f)
        papers = bib_db.entries
        self.stats['total'] = len(papers)
        
        self.logger.info(f"Loaded {len(papers)} papers from {bib_file}")
        self.logger.info("")
        
        for i, entry in enumerate(papers, 1):
            self.logger.info(f"[{i}/{len(papers)}] " + "-"*60)
            self._download_paper(entry)
        
        # Log summary
        self._log_summary()

    def download_from_ris(self, ris_file: str):
        import rispy
        
        # Log session start with separator
        self.logger.info("="*80)
        self.logger.info(f"NEW DOWNLOAD SESSION STARTED")
        self.logger.info(f"Input file: {ris_file}")
        self.logger.info(f"Output directory: {self.output_dir}")
        self.logger.info(f"Zotero enabled: {self.use_zotero and self.zotero_client is not None}")
        self.logger.info(f"Unpaywall enabled: {bool(self.unpaywall_email)}")
        self.logger.info(f"Sci-Hub enabled: {self.use_scihub}")
        self.logger.info("="*80)
        
        with open(ris_file, encoding="utf-8") as f:
            entries = rispy.load(f)
        self.stats['total'] = len(entries)
        
        self.logger.info(f"Loaded {len(entries)} papers from {ris_file}")
        self.logger.info("")
        
        for i, entry in enumerate(entries, 1):
            self.logger.info(f"[{i}/{len(entries)}] " + "-"*60)
            self._download_paper(entry)
        
        # Log summary
        self._log_summary()

    def _lookup_doi_from_title(self, title: str) -> Optional[str]:
        """
        Look up DOI from paper title using Crossref API.
        
        Args:
            title: Paper title to search for
            
        Returns:
            DOI string if found, None otherwise
        """
        import requests
        
        if not title or title == "Unknown":
            return None
        
        try:
            # Use Crossref API to search by title
            api_url = "https://api.crossref.org/works"
            params = {
                'query.bibliographic': title,
                'rows': 1,
                'select': 'DOI,title,score'
            }
            
            r = requests.get(api_url, params=params, timeout=10)
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

    def _download_paper(self, entry: dict):
        title = entry.get("title") or entry.get("TI") or "Unknown"
        doi = entry.get("doi") or entry.get("DO")
        url = entry.get("url") or entry.get("UR")
        arxiv_id = entry.get("arxiv_id")
        
        # Extract arXiv ID from URL if present (for @misc entries from arXiv)
        if not arxiv_id and url and "arxiv.org" in url.lower():
            # Extract arXiv ID from URL
            import re
            match = re.search(r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+)', url)
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
            self.stats['skipped'] += 1
            return
        
        self.logger.info(f"PROCESSING: {title[:80]}")
        if doi:
            self.logger.info(f"  DOI: {doi}")
        if arxiv_id:
            self.logger.info(f"  arXiv ID: {arxiv_id}")
        if url and not arxiv_id:
            self.logger.info(f"  URL: {url[:100]}")
        
        # 1. Try direct PDF link
        if url and url.endswith(".pdf"):
            self.logger.info(f"  → Trying direct PDF link...")
            pdf_url = url
            if self._download_pdf(pdf_url, dest_path):
                self.logger.info(f"  ✓ SUCCESS via direct PDF link")
                self.stats['success'] += 1
                self.stats['by_method']['direct_pdf'] += 1
                return
        
        # 1.5. Try Zotero Translation Server
        if self.use_zotero and self.zotero_client and self.zotero_client.is_available():
            self.logger.info(f"  → Trying Zotero Translation Server...")
            try:
                pdf_url = self._get_zotero_pdf(entry)
                if pdf_url:
                    self.logger.info(f"  → Found via Zotero: {pdf_url[:80]}")
                    # First try simple download (works for open access)
                    if self._download_pdf(pdf_url, dest_path):
                        self.logger.info(f"  ✓ SUCCESS via Zotero Translation Server")
                        self.stats['success'] += 1
                        self.stats['by_method']['zotero'] = self.stats['by_method'].get('zotero', 0) + 1
                        return
                    # If simple download fails but we have browser, try browser with Zotero URL
                    elif self.browser_downloader:
                        self.logger.info(f"  → Zotero URL found but needs auth, trying browser...")
                        try:
                            browser_pdf = self.browser_downloader.download_pdf(
                                pdf_url,
                                filename=dest_path.name,
                                doi=doi
                            )
                            if browser_pdf and browser_pdf.exists():
                                self.logger.info(f"  ✓ SUCCESS via Zotero + Browser")
                                self.stats['success'] += 1
                                self.stats['by_method']['zotero_browser'] = self.stats['by_method'].get('zotero_browser', 0) + 1
                                return
                        except Exception as be:
                            self.logger.debug(f"  → Zotero+Browser failed: {be}")
            except Exception as e:
                self.logger.debug(f"  → Zotero error: {e}")
        
        # 2. Try arXiv direct (check arXiv ID first, then DOI, then URL)
        if arxiv_id or (doi and "arxiv" in doi.lower()) or (url and "arxiv" in url.lower()):
            self.logger.info(f"  → Trying arXiv...")
            pdf_url = self._get_arxiv_pdf(entry)
            if pdf_url and self._download_pdf(pdf_url, dest_path):
                self.logger.info(f"  ✓ SUCCESS via arXiv")
                self.stats['success'] += 1
                self.stats['by_method']['arxiv'] += 1
                return
        
        # 2.5. Try bioRxiv/medRxiv (common for biomedical preprints)
        if url and ("biorxiv.org" in url.lower() or "medrxiv.org" in url.lower()):
            self.logger.info(f"  → Trying bioRxiv/medRxiv...")
            pdf_url = self._get_biorxiv_pdf(url)
            if pdf_url and self._download_pdf(pdf_url, dest_path):
                self.logger.info(f"  ✓ SUCCESS via bioRxiv/medRxiv")
                self.stats['success'] += 1
                self.stats['by_method']['biorxiv'] = self.stats['by_method'].get('biorxiv', 0) + 1
                return
        
        # 3. Try Unpaywall (open access)
        if doi and self.unpaywall_email:
            self.logger.info(f"  → Checking Unpaywall...")
            pdf_url = self._get_unpaywall_pdf(doi)
            if pdf_url:
                self.logger.info(f"  → Found OA version: {pdf_url[:80]}")
                if self._download_pdf(pdf_url, dest_path):
                    self.logger.info(f"  ✓ SUCCESS via Unpaywall")
                    self.stats['success'] += 1
                    self.stats['by_method']['unpaywall'] += 1
                    return
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
                    self.stats['success'] += 1
                    self.stats['by_method']['crossref'] = self.stats['by_method'].get('crossref', 0) + 1
                    return
        
        # 3.5. Try PubMed Central (if PMID or PMC ID available)
        pmid = entry.get("pmid") or entry.get("PMID")
        if pmid or (url and "pubmed.ncbi.nlm.nih.gov" in url):
            self.logger.info(f"  → Checking PubMed Central...")
            if not pmid and url:
                # Extract PMID from URL
                import re
                match = re.search(r'pubmed\.ncbi\.nlm\.nih\.gov/(\d+)', url)
                if match:
                    pmid = match.group(1)
            
            if pmid:
                pdf_url = self._get_pmc_pdf(pmid)
                if pdf_url and self._download_pdf(pdf_url, dest_path):
                    self.logger.info(f"  ✓ SUCCESS via PubMed Central")
                    self.stats['success'] += 1
                    self.stats['by_method']['pmc'] = self.stats['by_method'].get('pmc', 0) + 1
                    return
        
        # 4. Try common publisher patterns (MDPI, Frontiers, etc.)
        if url and doi:
            self.logger.info(f"  → Trying publisher-specific patterns...")
            pdf_url = self._get_publisher_pdf(url, doi)
            if pdf_url and self._download_pdf(pdf_url, dest_path):
                self.logger.info(f"  ✓ SUCCESS via publisher pattern")
                self.stats['success'] += 1
                self.stats['by_method']['publisher'] = self.stats['by_method'].get('publisher', 0) + 1
                return
        
        # 4.5. Try ResearchGate and Academia.edu (many authors upload there)
        if title and title != "Unknown":
            self.logger.info(f"  → Checking ResearchGate and Academia.edu...")
            pdf_url = self._get_academic_social_pdf(title, authors=entry.get("author", ""))
            if pdf_url:
                self.logger.info(f"  → Found on academic social network: {pdf_url[:80]}")
                if self._download_pdf(pdf_url, dest_path):
                    self.logger.info(f"  ✓ SUCCESS via ResearchGate/Academia.edu")
                    self.stats['success'] += 1
                    self.stats['by_method']['researchgate'] = self.stats['by_method'].get('researchgate', 0) + 1
                    return
        
        # 4.6. Try scraping HTML page for PDF link
        if url:
            self.logger.info(f"  → Trying to scrape PDF link from page...")
            pdf_url = self._try_scrape_pdf_link(url)
            if pdf_url:
                self.logger.info(f"  → Found PDF link: {pdf_url[:80]}")
                if self._download_pdf(pdf_url, dest_path):
                    self.logger.info(f"  ✓ SUCCESS via HTML scraping")
                    self.stats['success'] += 1
                    self.stats['by_method']['scraping'] = self.stats['by_method'].get('scraping', 0) + 1
                    return
        
        # 5. Browser-based download (uses real browser with saved sessions)
        if self.browser_downloader and (doi or url):
            self.logger.info(f"  → Trying browser-based download...")
            try:
                download_url = f"https://doi.org/{doi}" if doi else url
                pdf_path = self.browser_downloader.download_pdf(
                    download_url,
                    filename=dest_path.name,
                    doi=doi
                )
                if pdf_path and pdf_path.exists():
                    self.logger.info(f"  ✓ SUCCESS via browser download")
                    self.stats['success'] += 1
                    self.stats['by_method']['browser'] += 1
                    return
            except Exception as e:
                self.logger.debug(f"  → Browser download failed: {e}")
        
        # 6. Fallback: Sci-Hub (if enabled)
        if self.use_scihub and doi:
            self.logger.info(f"  → Trying Sci-Hub...")
            pdf_path = self._get_scihub_pdf(doi, dest_path)
            if pdf_path and dest_path.exists():
                self.logger.info(f"  ✓ SUCCESS via Sci-Hub")
                self.stats['success'] += 1
                self.stats['by_method']['scihub'] += 1
                return
        
        # 7. Log failure and store paper info
        self.logger.error(f"  ✗ FAILED: Could not download from any source")
        if not doi and not arxiv_id:
            self.logger.error(f"  → No DOI or arXiv ID available")
        self.stats['failed'] += 1
        
        # Store failed paper entry for later export
        self._store_failed_paper(entry)

    def _download_pdf(self, pdf_url: str, dest_path: Path, retry_count: int = 0, max_retries: int = 3) -> bool:
        import requests
        import time
        
        try:
            self.logger.info(f"Downloading from: {pdf_url}")
            
            # Comprehensive headers that mimic real browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/pdf,application/octet-stream,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Referer': 'https://www.google.com/',
            }
            
            # Special handling for arXiv
            if 'arxiv.org' in pdf_url.lower():
                # arXiv sometimes redirects, add timeout to avoid hangs
                r = requests.get(pdf_url, timeout=15, headers=headers, allow_redirects=True, stream=True)
            else:
                r = requests.get(pdf_url, timeout=30, headers=headers, allow_redirects=True, stream=True)
            
            if r.status_code == 200:
                content_type = r.headers.get('content-type', '').lower()
                
                # Verify it's actually a PDF
                if 'application/pdf' in content_type or (r.content and r.content[:4] == b'%PDF'):
                    with open(dest_path, "wb") as f:
                        f.write(r.content)
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
                    return self._download_pdf(pdf_url, dest_path, retry_count + 1, max_retries)
                else:
                    self.logger.error(f"HTTP 429 - max retries exceeded")
            else:
                self.logger.warning(f"HTTP {r.status_code} for URL: {pdf_url}")
        except requests.exceptions.Timeout:
            self.logger.warning(f"Request timeout - server took too long to respond")
        except requests.exceptions.ConnectionError:
            self.logger.warning(f"Connection error - check internet or server availability")
        except Exception as e:
            self.logger.error(f"PDF download error: {pdf_url} - {e}")
        return False

    def _get_unpaywall_pdf(self, doi: str) -> Optional[str]:
        import requests
        api = f"https://api.unpaywall.org/v2/{doi}?email={self.unpaywall_email}"
        try:
            r = requests.get(api, timeout=15)
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
        import requests
        try:
            # Query Crossref for this DOI
            api_url = f"https://api.crossref.org/works/{doi}"
            r = requests.get(api_url, timeout=10)
            
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

    def _get_academic_social_pdf(self, title: str, authors: str = "") -> Optional[str]:
        """
        Try to find paper on academic social networks like ResearchGate and Academia.edu.
        Many researchers upload their papers there for sharing.
        """
        import requests
        import re
        from urllib.parse import quote
        
        try:
            # Clean title for search
            search_title = title[:80].strip()
            search_query = quote(search_title)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # Try ResearchGate
            try:
                rg_url = f"https://www.researchgate.net/publication/search?q={search_query}"
                r = requests.get(rg_url, timeout=10, headers=headers)
                
                if r.status_code == 200 and 'researchgate.net' in r.url:
                    # Look for PDF download links
                    pdf_patterns = [
                        r'href=["\']([^"\']*(?:download|pdf)[^"\']*\.pdf[^"\']*)["\']',
                        r'"fullText"["\']?\s*:\s*"([^"]+\.pdf[^"]*)"',
                        r'data-ua-action-data="([^"]*\.pdf[^"]*)"'
                    ]
                    for pattern in pdf_patterns:
                        match = re.search(pattern, r.text)
                        if match:
                            pdf_url = match.group(1)
                            if not pdf_url.startswith('http'):
                                pdf_url = 'https://www.researchgate.net' + pdf_url
                            return pdf_url
            except Exception as e:
                self.logger.debug(f"ResearchGate search error: {e}")
            
        except Exception as e:
            self.logger.debug(f"Academic social network search error: {e}")
        
        return None
    
    def _get_arxiv_pdf(self, entry: dict) -> Optional[str]:
        arxiv_id = None
        
        # Check direct arXiv ID field
        if "arxiv_id" in entry and entry["arxiv_id"]:
            arxiv_id = entry["arxiv_id"]
        # Check DOI for arXiv pattern
        elif "doi" in entry and entry["doi"] and "arxiv" in entry["doi"].lower():
            if entry["doi"].startswith("10.48550/arXiv."):
                arxiv_id = entry["doi"].split("arXiv.")[-1]
            else:
                # Try to extract from DOI string
                parts = entry["doi"].split("/")
                for part in parts:
                    if part.replace(".", "").replace("v", "").isdigit():
                        arxiv_id = part
                        break
        # Check URL for arXiv pattern
        elif "url" in entry and entry["url"] and "arxiv" in entry["url"].lower():
            url = entry["url"]
            # Extract from URL like https://arxiv.org/abs/2101.00001
            if "/abs/" in url:
                arxiv_id = url.split("/abs/")[-1].split(".pdf")[0].split("v")[0]
            elif "/pdf/" in url:
                arxiv_id = url.split("/pdf/")[-1].split(".pdf")[0].split("v")[0]
        
        if arxiv_id:
            # Clean arXiv ID (remove version if present)
            arxiv_id = arxiv_id.split("v")[0].strip()
            # Use abstract endpoint which redirects to PDF - more reliable
            pdf_url = f"https://arxiv.org/abs/{arxiv_id}"
            self.logger.info(f"Constructed arXiv abstract URL (will redirect to PDF): {pdf_url}")
            return pdf_url
        
        return None
    
    def _get_zotero_pdf(self, entry: dict) -> Optional[str]:
        """
        Try to get PDF URL using Zotero Translation Server.
        
        The Zotero Translation Server can extract metadata and PDF links
        from DOIs, PMIDs, arXiv IDs, and URLs using its extensive library
        of translators.
        
        Note: The Translation Server primarily returns metadata, not PDFs.
        However, it can resolve identifiers to canonical publisher URLs
        which may help downstream download methods.
        
        Args:
            entry: BibTeX/RIS entry dictionary
            
        Returns:
            PDF URL if found, or canonical publisher URL to try, None otherwise
        """
        if not self.zotero_client:
            return None
        
        # Extract identifiers from entry
        doi = entry.get("doi") or entry.get("DO")
        pmid = entry.get("pmid") or entry.get("PMID")
        arxiv_id = entry.get("arxiv_id")
        url = entry.get("url") or entry.get("UR")
        
        try:
            metadata = None
            
            # Try DOI first (most reliable)
            if doi:
                self.logger.debug(f"  → Zotero: trying DOI {doi}")
                metadata = self.zotero_client.translate_identifier(doi, "doi")
            
            # Try PMID
            if not metadata and pmid:
                self.logger.debug(f"  → Zotero: trying PMID {pmid}")
                metadata = self.zotero_client.translate_identifier(pmid, "pmid")
            
            # Try arXiv ID
            if not metadata and arxiv_id:
                self.logger.debug(f"  → Zotero: trying arXiv {arxiv_id}")
                metadata = self.zotero_client.translate_identifier(arxiv_id, "arxiv")
            
            # Try URL to get canonical publisher URL
            if not metadata and url:
                self.logger.debug(f"  → Zotero: trying URL {url[:80]}")
                metadata = self.zotero_client.translate_url(url)
            
            # Extract PDF URL from metadata
            if metadata:
                # First try direct PDF attachment
                pdf_url = self.zotero_client.extract_pdf_url(metadata)
                if pdf_url:
                    return pdf_url
                
                # Get canonical URL from metadata - useful for resolving Scopus/proxy links
                canonical_url = metadata.get('url')
                if canonical_url and canonical_url != url:
                    # Try to construct PDF URL from canonical URL
                    pdf_url = self._construct_pdf_from_publisher_url(canonical_url)
                    if pdf_url:
                        self.logger.debug(f"  → Zotero: constructed PDF URL from canonical: {pdf_url[:60]}")
                        return pdf_url
                
                self.logger.debug(f"  → Zotero found metadata but no PDF URL")
            
        except Exception as e:
            self.logger.debug(f"  → Zotero error: {e}")
        
        return None
    
    def _construct_pdf_from_publisher_url(self, url: str) -> Optional[str]:
        """
        Try to construct a PDF URL from a publisher URL.
        
        Many publishers have predictable PDF URL patterns.
        
        Args:
            url: Publisher URL from Zotero metadata
            
        Returns:
            PDF URL if pattern matched, None otherwise
        """
        if not url:
            return None
        
        url_lower = url.lower()
        
        # Nature (nature.com)
        if 'nature.com/articles/' in url_lower:
            return url.replace('/articles/', '/articles/') + '.pdf'
        
        # Frontiers
        if 'frontiersin.org/articles/' in url_lower or 'frontiersin.org/journals/' in url_lower:
            if '/full' in url_lower:
                return url.replace('/full', '/pdf')
            return url + '/pdf'
        
        # MDPI
        if 'mdpi.com/' in url_lower and '/htm' not in url_lower:
            # https://www.mdpi.com/2079-9292/14/13/2667 -> https://www.mdpi.com/2079-9292/14/13/2667/pdf
            return url.rstrip('/') + '/pdf'
        
        # PLoS
        if 'plos' in url_lower and 'journal.p' in url_lower:
            # https://journals.plos.org/plosone/article?id=10.1371/... 
            if '?id=' in url:
                doi = url.split('?id=')[-1]
                return f"https://journals.plos.org/plosone/article/file?id={doi}&type=printable"
        
        # bioRxiv/medRxiv  
        if 'biorxiv.org' in url_lower or 'medrxiv.org' in url_lower:
            if '/content/' in url and not url.endswith('.pdf'):
                return url + '.full.pdf'
        
        # Wiley (for open access)
        if 'onlinelibrary.wiley.com/doi/' in url_lower:
            # Try pdfdirect pattern
            if '/full/' in url:
                return url.replace('/full/', '/pdfdirect/')
            elif '/abs/' in url:
                return url.replace('/abs/', '/pdfdirect/')
            else:
                return url.replace('/doi/', '/doi/pdfdirect/')
        
        # IOP Science
        if 'iopscience.iop.org/article/' in url_lower:
            if '/meta' in url:
                return url.replace('/meta', '/pdf')
            return url + '/pdf'
        
        # Springer/BMC (open access journals)
        if 'springeropen.com/articles/' in url_lower or 'biomedcentral.com/articles/' in url_lower:
            return url + '/fulltext.pdf' if not url.endswith('.pdf') else url
        
        # JNEUROSCI and similar
        if 'jneurosci.org' in url_lower:
            return url + '.full.pdf'
        
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
        Try to get PDF from PubMed Central using PMID.
        PMC provides free full-text access for many papers.
        Also tries Europe PMC as fallback.
        """
        import requests
        try:
            # First, check if paper is available in PMC
            pmc_api = f"https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={pmid}&format=json"
            r = requests.get(pmc_api, timeout=10)
            
            if r.status_code == 200:
                data = r.json()
                records = data.get('records', [])
                
                if records and len(records) > 0:
                    record = records[0]
                    pmcid = record.get('pmcid')
                    
                    if pmcid:
                        # Try to get PDF from PMC
                        pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
                        self.logger.info(f"  → Found PMC ID: {pmcid}")
                        return pdf_url
                    else:
                        self.logger.debug(f"  → Paper not available in US PMC, trying Europe PMC...")
                        # Try Europe PMC as fallback
                        return self._get_europepmc_pdf(pmid)
                else:
                    self.logger.debug(f"  → No US PMC record, trying Europe PMC...")
                    return self._get_europepmc_pdf(pmid)
                        
        except Exception as e:
            self.logger.debug(f"PubMed Central error for PMID {pmid}: {e}")
            # Try Europe PMC as fallback
            return self._get_europepmc_pdf(pmid)
        
        return None
    
    def _get_europepmc_pdf(self, pmid: str) -> Optional[str]:
        """
        Try to get PDF from Europe PubMed Central.
        Europe PMC often has papers not in US PMC.
        """
        import requests
        try:
            # Check Europe PMC for full text availability
            api_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search"
            params = {
                'query': f'EXT_ID:{pmid}',
                'format': 'json',
                'resultType': 'core'
            }
            
            r = requests.get(api_url, params=params, timeout=10)
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
        import requests
        from bs4 import BeautifulSoup
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            r = requests.get(url, timeout=15, headers=headers)
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
        return "".join(c if c.isalnum() else "_" for c in name)[:80]
    
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
        self.logger.info("Downloads by method:")
        for method, count in self.stats['by_method'].items():
            if count > 0:
                self.logger.info(f"  {method.replace('_', ' ').title()}: {count}")
        self.logger.info("="*80)
        self.logger.info("")

# Example usage:
# downloader = PaperDownloader(output_dir="results/pdfs", use_scihub=True, unpaywall_email="your@email.com")
# downloader.download_from_bib("results/references.bib")
# downloader.download_from_ris("results/references.ris")
