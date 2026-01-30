"""
Browser-Based PDF Downloader

Uses Playwright to download PDFs with a real browser, enabling:
- Persistent sessions (stay logged into institutional access)
- JavaScript execution
- Bot detection bypass
- Cookie persistence

This matches Zotero Desktop's PDF download capability.
"""
import logging
import os
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse


class BrowserDownloader:
    """
    Browser-based PDF downloader using Playwright.
    
    Uses a persistent browser context to maintain login sessions
    across downloads, enabling institutional access.
    """
    
    def __init__(
        self,
        output_dir: str = "downloads",
        headless: bool = True,
        user_data_dir: Optional[str] = None,
        timeout: int = 30000,
        browser_type: str = "firefox"  # "chromium" or "firefox"
    ):
        """
        Initialize the browser downloader.
        
        Args:
            output_dir: Directory to save downloaded PDFs
            headless: Run browser in headless mode (set False for debugging/login)
            user_data_dir: Directory to persist browser data (cookies, sessions)
                          If None, uses a default location in the project
            timeout: Page load timeout in milliseconds
            browser_type: Browser to use - "firefox" (recommended) or "chromium"
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.timeout = timeout
        self.browser_type = browser_type
        self.logger = logging.getLogger("BrowserDownloader")
        
        # Set up persistent browser data directory
        # Use the real browser session if available
        self._use_real_session = False
        if user_data_dir is None:
            real_browser_data = Path(__file__).parent.parent.parent / ".browser_data_real"
            if real_browser_data.exists():
                self.user_data_dir = real_browser_data
                self._use_real_session = True
                # Force chromium when using real Chrome session
                self.browser_type = "chromium"
                self.logger.info("Using real browser session data")
            else:
                self.user_data_dir = Path(__file__).parent.parent.parent / ".browser_data"
        else:
            self.user_data_dir = Path(user_data_dir)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        
        # Browser context (lazy initialization)
        self._playwright = None
        self._browser = None
        self._context = None
        
    def _try_connect_to_chrome(self) -> bool:
        """
        Try to connect to a running Chrome instance with debugging port.
        
        This allows using an authenticated Chrome session started with:
        chrome.exe --remote-debugging-port=9222 --user-data-dir=".browser_data_real"
        
        Returns:
            True if connected successfully, False otherwise
        """
        from playwright.sync_api import sync_playwright
        import socket
        
        # Check if Chrome is listening on debugging port
        debugging_port = 9222
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', debugging_port))
            sock.close()
            if result != 0:
                return False
        except Exception:
            return False
        
        try:
            self._playwright = sync_playwright().start()
            # Connect to running Chrome via CDP
            self._browser = self._playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{debugging_port}"
            )
            
            # Get the default context (the authenticated one)
            contexts = self._browser.contexts
            if contexts:
                self._context = contexts[0]
                self._use_real_session = True
                self.logger.info("Connected to running Chrome with authenticated session!")
                return True
            else:
                self.logger.warning("Connected to Chrome but no context found")
                self._browser.close()
                self._playwright.stop()
                self._browser = None
                self._playwright = None
                return False
                
        except Exception as e:
            self.logger.debug(f"Could not connect to Chrome: {e}")
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
            self._browser = None
            self._playwright = None
            return False
    
    def _ensure_browser(self):
        """Initialize browser if not already running."""
        if self._context is not None:
            return
        
        # First, try to connect to a running Chrome with debugging port
        # This enables using your authenticated session!
        if self._try_connect_to_chrome():
            return
        
        from playwright.sync_api import sync_playwright
        
        self._playwright = sync_playwright().start()
        
        # Choose browser type
        if self.browser_type == "firefox":
            browser_launcher = self._playwright.firefox
            # Firefox-specific options
            self._context = browser_launcher.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=self.headless,
                accept_downloads=True,
                viewport={'width': 1920, 'height': 1080},
                ignore_https_errors=True,
            )
        else:
            browser_launcher = self._playwright.chromium
            # Chromium with anti-detection
            self._context = browser_launcher.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=self.headless,
                accept_downloads=True,
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                ignore_https_errors=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ],
            )
            # Remove webdriver property for Chromium
            for page in self._context.pages:
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
        
        self.logger.info(f"Browser started ({self.browser_type}, headless={self.headless})")
        self.logger.info(f"Session data stored in: {self.user_data_dir}")
    
    def close(self):
        """Close the browser and clean up."""
        # If connected to real Chrome via CDP, just disconnect (don't close user's browser)
        if self._use_real_session and self._browser:
            # Just disconnect, don't close the user's Chrome
            self._context = None
            self._browser = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
            return
            
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def login_interactive(self, url: str = "https://www.google.com"):
        """
        Open a browser window for manual login.
        
        Use this to log into your institution's library portal.
        The session will be saved and reused for subsequent downloads.
        
        Args:
            url: URL to open for login (default: Google for general testing)
        """
        # Force non-headless for interactive login
        old_headless = self.headless
        self.headless = False
        
        # Close existing browser if any
        self.close()
        
        # Start fresh browser
        self._ensure_browser()
        
        page = self._context.new_page()
        
        # Anti-detection for Chromium only
        if self.browser_type == "chromium":
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
        
        page.goto(url, wait_until='domcontentloaded')
        
        print("\n" + "="*60)
        print("INTERACTIVE LOGIN SESSION")
        print("="*60)
        print(f"\nBrowser opened to: {url}")
        print("\nPlease log in to your institution's library portal.")
        print("Your session will be saved for future downloads.")
        print("\nWhen done, press Enter to continue...")
        input()
        
        page.close()
        self.close()
        
        # Restore headless mode
        self.headless = old_headless
        print("\nSession saved! You can now run downloads with institutional access.")

    def _get_downloads_folder(self) -> Path:
        """Get the user's Downloads folder."""
        import os
        # Windows: C:\Users\<user>\Downloads
        # macOS: /Users/<user>/Downloads  
        # Linux: /home/<user>/Downloads
        if os.name == 'nt':  # Windows
            return Path(os.path.expanduser('~')) / 'Downloads'
        else:
            return Path.home() / 'Downloads'
    
    def _wait_for_new_download(self, timeout: int = 30) -> Optional[Path]:
        """
        Wait for a new PDF to appear in Downloads folder.
        Used when connected via CDP where downloads go to user's Downloads.
        
        Returns:
            Path to the new PDF if found, None otherwise
        """
        downloads_dir = self._get_downloads_folder()
        
        # Get current files
        existing_files = set(downloads_dir.glob('*.pdf'))
        
        # Wait for new file
        start = time.time()
        while time.time() - start < timeout:
            current_files = set(downloads_dir.glob('*.pdf'))
            new_files = current_files - existing_files
            
            for new_file in new_files:
                # Check if it's a complete download (not .crdownload temp file)
                if new_file.exists() and new_file.stat().st_size > 5000:
                    # Wait a bit to ensure download is complete
                    time.sleep(1)
                    if new_file.exists() and new_file.stat().st_size > 5000:
                        return new_file
            
            time.sleep(0.5)
        
        return None
    
    def download_pdf(
        self,
        url: str,
        filename: Optional[str] = None,
        doi: Optional[str] = None
    ) -> Optional[Path]:
        """
        Download a PDF from a URL using the browser.
        
        Args:
            url: URL of the PDF or paper page
            filename: Optional filename for the PDF
            doi: DOI for constructing filename if not provided
            
        Returns:
            Path to downloaded PDF if successful, None otherwise
        """
        self._ensure_browser()
        
        # Generate filename if not provided
        if filename is None:
            if doi:
                filename = doi.replace("/", "_").replace(".", "_") + ".pdf"
            else:
                filename = urlparse(url).path.split("/")[-1]
                if not filename.endswith(".pdf"):
                    filename = f"paper_{int(time.time())}.pdf"
        
        dest_path = self.output_dir / filename
        
        # Skip if already exists
        if dest_path.exists() and dest_path.stat().st_size > 5000:
            self.logger.info(f"Already downloaded: {filename}")
            return dest_path
        
        page = self._context.new_page()
        
        try:
            self.logger.debug(f"Navigating to: {url[:80]}...")
            
            # Check if URL is a direct PDF link
            if url.lower().endswith('.pdf') or '/pdf' in url.lower():
                # Try to download directly
                result = self._download_direct_pdf(page, url, dest_path)
                if result:
                    return result
            
            # Handle DOI URLs - they redirect to publisher pages
            if 'doi.org/' in url:
                # DOI handling includes finding PDF on the publisher page
                return self._download_via_doi(page, url, dest_path, doi)
            
            # Navigate to page and look for PDF link
            return self._download_from_page(page, url, dest_path, doi)
                
        except Exception as e:
            self.logger.error(f"Browser download failed: {e}")
            return None
        finally:
            page.close()
    
    def _download_via_doi(self, page, url: str, dest_path: Path, doi: Optional[str] = None) -> Optional[Path]:
        """Follow DOI redirect and download PDF from publisher page."""
        try:
            # Navigate to DOI URL - it will redirect to publisher
            response = page.goto(url, timeout=self.timeout, wait_until='domcontentloaded')
            
            if not response:
                self.logger.warning("No response from DOI redirect")
                return None
            
            # Check for DOI not found
            if response.status == 404:
                self.logger.warning(f"DOI not found: {doi or url}")
                return None
            
            # Wait for redirects to complete - Elsevier often has multiple redirects
            page.wait_for_timeout(2000)
            
            # Wait for network to settle
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass  # Timeout okay, continue
            
            # Wait a bit more for any JavaScript redirects
            page.wait_for_timeout(1000)
            
            final_url = page.url
            self.logger.debug(f"DOI redirected to: {final_url[:60]}...")
            
            # Check if we're still on doi.org (no redirect happened)
            if 'doi.org' in final_url:
                self.logger.warning(f"DOI did not redirect: {doi or url}")
                return None
            
            # Handle linkinghub.elsevier.com redirects
            if 'linkinghub.elsevier.com' in final_url:
                # Wait for it to redirect to ScienceDirect
                page.wait_for_timeout(3000)
                final_url = page.url
                self.logger.debug(f"After linkinghub redirect: {final_url[:60]}...")
            
            # Check if we landed on a direct PDF or Chrome is showing PDF viewer
            content_type = response.headers.get('content-type', '') if response else ''
            is_pdf_url = final_url.lower().endswith('.pdf') or '/pdf' in final_url.lower()
            is_pdf_content = 'application/pdf' in content_type
            
            if is_pdf_url or is_pdf_content:
                # Try CDP JS fetch to download the PDF
                if self._use_real_session:
                    result = self._download_via_cdp(page, final_url, dest_path)
                    if result:
                        return result
            
            # For ScienceDirect, try to find and click the PDF download link
            if 'sciencedirect.com' in final_url:
                result = self._download_sciencedirect(page, dest_path)
                if result:
                    return result
            
            # For SAGE journals
            if 'sagepub.com' in final_url:
                result = self._download_sage(page, dest_path)
                if result:
                    return result
            
            # For IOP Science
            if 'iopscience.iop.org' in final_url:
                result = self._download_iop(page, dest_path)
                if result:
                    return result
            
            # For AIP Publishing (JASA, etc.) - uses Silverchair platform
            if 'pubs.aip.org' in final_url:
                result = self._download_aip(page, dest_path)
                if result:
                    return result
            
            # Look for PDF links on the publisher page
            return self._try_find_pdf_on_page(page, dest_path, doi)
            
        except Exception as e:
            self.logger.debug(f"DOI download failed: {e}")
            return None
    
    def _download_via_cdp(self, page, url: str, dest_path: Path) -> Optional[Path]:
        """
        Download PDF when connected via CDP to real Chrome.
        
        Uses JavaScript fetch with credentials to download the PDF,
        leveraging the browser's authenticated session.
        """
        import base64
        
        try:
            # Check if we're already on a page or need to navigate
            current_url = page.url
            if current_url != url and 'about:blank' not in current_url:
                # We're already on a page, try fetch from current context first
                pass
            else:
                # Navigate to the page to establish context
                try:
                    page.goto(url, timeout=self.timeout, wait_until='domcontentloaded')
                except Exception as e:
                    # Navigation might fail for PDF URLs, but context may still work
                    self.logger.debug(f"Navigation exception (continuing): {e}")
            
            time.sleep(1)
            
            # Use JavaScript fetch to download the PDF with credentials
            # This uses the browser's authenticated session!
            # We're more lenient with content-type since some servers misreport
            fetch_script = '''
            async (url) => {
                try {
                    const response = await fetch(url, { credentials: 'include' });
                    if (!response.ok) {
                        return { error: 'HTTP ' + response.status };
                    }
                    const arrayBuffer = await response.arrayBuffer();
                    const bytes = new Uint8Array(arrayBuffer);
                    
                    // Check if it's actually a PDF (starts with %PDF)
                    if (bytes.length < 5 || 
                        bytes[0] !== 0x25 || bytes[1] !== 0x50 || 
                        bytes[2] !== 0x44 || bytes[3] !== 0x46) {
                        // Not a PDF, check what we got
                        const text = new TextDecoder().decode(bytes.slice(0, 100));
                        return { error: 'Not a PDF, starts with: ' + text.substring(0, 50) };
                    }
                    
                    let binary = '';
                    for (let i = 0; i < bytes.length; i++) {
                        binary += String.fromCharCode(bytes[i]);
                    }
                    return { data: btoa(binary), size: bytes.length };
                } catch (e) {
                    return { error: e.message };
                }
            }
            '''
            
            self.logger.debug(f"Fetching PDF via JavaScript with credentials...")
            result = page.evaluate(fetch_script, url)
            
            if isinstance(result, dict):
                if 'error' in result:
                    self.logger.debug(f"JavaScript fetch failed: {result['error']}")
                    return None
                
                if 'data' in result:
                    pdf_bytes = base64.b64decode(result['data'])
                    
                    # Verify it's a PDF
                    if len(pdf_bytes) > 5000 and pdf_bytes[:4] == b'%PDF':
                        dest_path.write_bytes(pdf_bytes)
                        self.logger.info(f"Downloaded via CDP+JS: {dest_path.name} ({len(pdf_bytes)} bytes)")
                        return dest_path
                    else:
                        self.logger.debug(f"Fetched content is not a valid PDF")
            
            return None
            
        except Exception as e:
            self.logger.debug(f"CDP download failed: {e}")
            return None

    def _download_sciencedirect(self, page, dest_path: Path) -> Optional[Path]:
        """
        Download PDF from ScienceDirect (Elsevier).
        
        ScienceDirect uses AWS-signed URLs for PDFs and Cloudflare protection.
        The most reliable method is:
        1. Navigate to the article's pdfft URL
        2. Wait for redirect to pdf.sciencedirectassets.com
        3. Use CDP printToPDF to capture the rendered PDF
        """
        import base64
        
        try:
            self.logger.debug("Trying ScienceDirect download...")
            
            # Wait for page to fully load
            page.wait_for_timeout(2000)
            
            current_url = page.url
            
            # First, try to extract the article PII from the URL
            # URL format: https://www.sciencedirect.com/science/article/pii/S0278431925003866
            pii = None
            if '/pii/' in current_url:
                parts = current_url.split('/pii/')
                if len(parts) > 1:
                    pii = parts[1].split('/')[0].split('?')[0]
            
            if not pii:
                self.logger.debug("Could not extract PII from ScienceDirect URL")
                return None
            
            # Find and navigate to the pdfft link
            pdf_link = page.query_selector('a[href*="pdfft"]')
            if not pdf_link:
                # Try to construct the pdfft URL
                pdf_url = f"/science/article/pii/{pii}/pdfft"
            else:
                pdf_url = pdf_link.get_attribute('href')
            
            # Make full URL
            if pdf_url.startswith('/'):
                full_pdf_url = f"https://www.sciencedirect.com{pdf_url}"
            else:
                full_pdf_url = pdf_url
            
            self.logger.debug(f"Navigating to PDF viewer: {full_pdf_url[:70]}...")
            
            # Navigate to the PDF viewer
            try:
                page.goto(full_pdf_url, timeout=60000)
            except Exception as e:
                # Navigation might timeout but still redirect - check URL
                self.logger.debug(f"Navigation exception (checking URL): {e}")
            
            # Wait for redirect to pdf.sciencedirectassets.com
            for _ in range(10):  # Wait up to 10 seconds
                page.wait_for_timeout(1000)
                if 'pdf.sciencedirectassets.com' in page.url:
                    self.logger.debug("Redirected to PDF assets URL")
                    break
            
            if 'pdf.sciencedirectassets.com' not in page.url:
                self.logger.debug(f"Did not reach PDF assets URL, current: {page.url[:60]}")
                return None
            
            # Wait for PDF to fully load in Chrome's PDF viewer
            # This is crucial - the PDF needs time to render before printToPDF works
            self.logger.debug("Waiting for PDF to fully load...")
            page.wait_for_timeout(5000)
            
            # Now we're on the PDF page rendered by Chrome's built-in PDF viewer
            # Use CDP printToPDF to capture the rendered PDF
            if self._use_real_session:
                self.logger.debug("Using CDP printToPDF to capture PDF...")
                
                try:
                    cdp = self._context.new_cdp_session(page)
                    result = cdp.send('Page.printToPDF', {
                        'printBackground': True,
                        'preferCSSPageSize': True,
                        'scale': 1.0,
                    })
                    
                    if result and 'data' in result:
                        pdf_bytes = base64.b64decode(result['data'])
                        
                        # Verify it's a valid PDF
                        if len(pdf_bytes) > 5000 and pdf_bytes[:4] == b'%PDF':
                            dest_path.write_bytes(pdf_bytes)
                            self.logger.info(f"Downloaded via CDP printToPDF: {dest_path.name} ({len(pdf_bytes)} bytes)")
                            return dest_path
                        else:
                            self.logger.debug("printToPDF output is not a valid PDF")
                    else:
                        self.logger.debug(f"printToPDF returned no data: {result}")
                        
                except Exception as e:
                    self.logger.debug(f"CDP printToPDF failed: {e}")
            else:
                self.logger.debug("Not using real session - printToPDF approach requires CDP connection")
            
            return None
            
        except Exception as e:
            self.logger.debug(f"ScienceDirect download failed: {e}")
            return None
    
    def _download_sage(self, page, dest_path: Path) -> Optional[Path]:
        """
        Download PDF from SAGE journals.
        
        SAGE pages require navigating to the PDF URL, which opens in
        Chrome's PDF viewer. We use printToPDF to capture the rendered PDF.
        """
        import base64
        
        try:
            self.logger.debug("Trying SAGE download...")
            
            # Wait for page to load
            page.wait_for_timeout(2000)
            
            # Look for PDF link
            pdf_selectors = [
                'a[href*="/doi/pdf/"]',
                'a[href*="/doi/pdfdirect/"]',
                'a[href*="/doi/reader/"]',
            ]
            
            pdf_url = None
            for selector in pdf_selectors:
                try:
                    link = page.query_selector(selector)
                    if link:
                        href = link.get_attribute('href')
                        if href:
                            if href.startswith('/'):
                                pdf_url = f"https://journals.sagepub.com{href}"
                            elif href.startswith('http'):
                                pdf_url = href
                            self.logger.debug(f"Found SAGE PDF link: {pdf_url[:60]}...")
                            break
                except Exception:
                    continue
            
            if not pdf_url:
                # Construct from current URL
                current_url = page.url
                if '/doi/' in current_url and '/pdf/' not in current_url:
                    # https://journals.sagepub.com/doi/full/10.1177/XXX
                    # -> https://journals.sagepub.com/doi/pdf/10.1177/XXX
                    pdf_url = current_url.replace('/doi/full/', '/doi/pdf/').replace('/doi/abs/', '/doi/pdf/')
                    if '/doi/10.' in pdf_url:
                        pdf_url = pdf_url.replace('/doi/10.', '/doi/pdf/10.')
                    self.logger.debug(f"Constructed SAGE PDF URL: {pdf_url[:60]}...")
            
            if pdf_url and self._use_real_session:
                # Navigate to the PDF URL
                self.logger.debug(f"Navigating to SAGE PDF: {pdf_url[:60]}...")
                try:
                    page.goto(pdf_url, timeout=30000)
                except Exception:
                    pass  # Navigation might time out but page may still load
                
                # Wait for PDF to fully load in Chrome's PDF viewer
                self.logger.debug("Waiting for PDF to fully load...")
                page.wait_for_timeout(5000)
                
                final_url = page.url
                self.logger.debug(f"Final URL: {final_url[:60]}...")
                
                # If we're on a PDF page, use printToPDF
                if 'pdf' in final_url.lower():
                    self.logger.debug("Using CDP printToPDF for SAGE...")
                    
                    try:
                        cdp = self._context.new_cdp_session(page)
                        result = cdp.send('Page.printToPDF', {
                            'printBackground': True,
                            'preferCSSPageSize': True,
                            'scale': 1.0,
                        })
                        
                        if result and 'data' in result:
                            pdf_bytes = base64.b64decode(result['data'])
                            
                            # Verify it's a valid PDF
                            if len(pdf_bytes) > 5000 and pdf_bytes[:4] == b'%PDF':
                                dest_path.write_bytes(pdf_bytes)
                                self.logger.info(f"Downloaded SAGE via printToPDF: {dest_path.name} ({len(pdf_bytes)} bytes)")
                                return dest_path
                            else:
                                self.logger.debug("printToPDF output is not a valid PDF")
                    except Exception as e:
                        self.logger.debug(f"CDP printToPDF failed for SAGE: {e}")
            
            return None
            
        except Exception as e:
            self.logger.debug(f"SAGE download failed: {e}")
            return None

    def _download_iop(self, page, dest_path: Path) -> Optional[Path]:
        """
        Download PDF from IOP Science journals.
        
        IOP Science pages require navigating to the PDF URL, which opens in
        Chrome's PDF viewer. We use printToPDF to capture the rendered PDF.
        """
        import base64
        
        try:
            self.logger.debug("Trying IOP Science download...")
            
            # Wait for page to load
            page.wait_for_timeout(2000)
            
            current_url = page.url
            
            # Construct PDF URL from article URL
            # https://iopscience.iop.org/article/10.1088/XXX -> /article/10.1088/XXX/pdf
            if '/article/' in current_url and not current_url.endswith('/pdf'):
                pdf_url = current_url.rstrip('/') + '/pdf'
            else:
                # Look for PDF link
                link = page.query_selector('a[href*="/pdf"]')
                if link:
                    href = link.get_attribute('href')
                    if href.startswith('/'):
                        pdf_url = f"https://iopscience.iop.org{href}"
                    else:
                        pdf_url = href
                else:
                    self.logger.debug("No IOP PDF link found")
                    return None
            
            self.logger.debug(f"Navigating to IOP PDF: {pdf_url[:60]}...")
            
            try:
                page.goto(pdf_url, timeout=30000)
            except Exception:
                pass  # Navigation might time out but page may still load
            
            # Wait for PDF to fully load in Chrome's PDF viewer
            self.logger.debug("Waiting for PDF to fully load...")
            page.wait_for_timeout(5000)
            
            final_url = page.url
            self.logger.debug(f"Final URL: {final_url[:60]}...")
            
            # Use printToPDF
            if self._use_real_session and 'pdf' in final_url.lower():
                self.logger.debug("Using CDP printToPDF for IOP...")
                
                try:
                    cdp = self._context.new_cdp_session(page)
                    result = cdp.send('Page.printToPDF', {
                        'printBackground': True,
                        'preferCSSPageSize': True,
                        'scale': 1.0,
                    })
                    
                    if result and 'data' in result:
                        pdf_bytes = base64.b64decode(result['data'])
                        
                        # Verify it's a valid PDF
                        if len(pdf_bytes) > 5000 and pdf_bytes[:4] == b'%PDF':
                            dest_path.write_bytes(pdf_bytes)
                            self.logger.info(f"Downloaded IOP via printToPDF: {dest_path.name} ({len(pdf_bytes)} bytes)")
                            return dest_path
                        else:
                            self.logger.debug("printToPDF output is not a valid PDF")
                except Exception as e:
                    self.logger.debug(f"CDP printToPDF failed for IOP: {e}")
            
            return None
            
        except Exception as e:
            self.logger.debug(f"IOP Science download failed: {e}")
            return None

    def _download_aip(self, page, dest_path: Path) -> Optional[Path]:
        """
        Download PDF from AIP Publishing (JASA, etc.).
        
        AIP uses Silverchair platform. PDFs are accessible via article-pdf URLs
        which redirect to watermark.silverchair.com for authenticated users.
        We use printToPDF to capture the rendered PDF.
        """
        import base64
        
        try:
            self.logger.debug("Trying AIP download...")
            
            # Wait for page to load
            page.wait_for_timeout(2000)
            
            # Look for PDF link on the page
            pdf_link = page.query_selector('a[href*="/article-pdf/"]')
            if not pdf_link:
                self.logger.debug("No AIP PDF link found")
                return None
            
            href = pdf_link.get_attribute('href')
            if href.startswith('/'):
                pdf_url = f"https://pubs.aip.org{href}"
            else:
                pdf_url = href
            
            self.logger.debug(f"Navigating to AIP PDF: {pdf_url[:60]}...")
            
            try:
                page.goto(pdf_url, timeout=60000)
            except Exception:
                pass  # Navigation might time out but page may still load
            
            # Wait for redirect to Silverchair and PDF to load
            self.logger.debug("Waiting for PDF to fully load...")
            page.wait_for_timeout(5000)
            
            final_url = page.url
            self.logger.debug(f"Final URL: {final_url[:60]}...")
            
            # Use printToPDF if we're on a PDF page
            if self._use_real_session and ('silverchair' in final_url.lower() or 'pdf' in final_url.lower()):
                self.logger.debug("Using CDP printToPDF for AIP...")
                
                try:
                    cdp = self._context.new_cdp_session(page)
                    result = cdp.send('Page.printToPDF', {
                        'printBackground': True,
                        'preferCSSPageSize': True,
                        'scale': 1.0,
                    })
                    
                    if result and 'data' in result:
                        pdf_bytes = base64.b64decode(result['data'])
                        
                        # Verify it's a valid PDF
                        if len(pdf_bytes) > 5000 and pdf_bytes[:4] == b'%PDF':
                            dest_path.write_bytes(pdf_bytes)
                            self.logger.info(f"Downloaded AIP via printToPDF: {dest_path.name} ({len(pdf_bytes)} bytes)")
                            return dest_path
                        else:
                            self.logger.debug("printToPDF output is not a valid PDF")
                except Exception as e:
                    self.logger.debug(f"CDP printToPDF failed for AIP: {e}")
            
            return None
            
        except Exception as e:
            self.logger.debug(f"AIP download failed: {e}")
            return None

    def _download_direct_pdf(self, page, url: str, dest_path: Path) -> Optional[Path]:
        """Download a direct PDF link."""
        
        # When connected via CDP, downloads go to user's Downloads folder
        # We need to watch for new files there instead of using Playwright's download handling
        if self._use_real_session:
            return self._download_via_cdp(page, url, dest_path)
        
        try:
            # Use expect_event with JavaScript navigation to avoid "Download is starting" exception
            # page.goto() throws an error when the URL triggers a download
            # page.evaluate() triggers the download via JavaScript and captures the download event
            with page.expect_event('download', timeout=self.timeout) as download_info:
                # Trigger download via JavaScript navigation (avoids Playwright exception)
                page.evaluate(f'window.location.href = "{url}"')
            
            download = download_info.value
            download.save_as(dest_path)
            
            # Verify it's a valid PDF
            if dest_path.exists() and dest_path.stat().st_size > 5000:
                self.logger.info(f"Downloaded: {dest_path.name} ({dest_path.stat().st_size} bytes)")
                return dest_path
            else:
                self.logger.warning(f"Downloaded file too small or missing")
                return None
                
        except Exception as e:
            # If download didn't trigger, the URL might not be a direct PDF
            # Try navigating normally to check
            self.logger.debug(f"Direct download failed, trying page load: {e}")
            
            try:
                # Create a new page to avoid state issues
                new_page = self._context.new_page()
                try:
                    response = new_page.goto(url, timeout=self.timeout, wait_until='domcontentloaded')
                    
                    if response and response.status == 200:
                        content_type = response.headers.get('content-type', '')
                        
                        if 'application/pdf' in content_type:
                            content = response.body()
                            if content and content[:4] == b'%PDF':
                                dest_path.write_bytes(content)
                                self.logger.info(f"Downloaded: {dest_path.name} ({len(content)} bytes)")
                                return dest_path
                        
                        # Check if we landed on a paywall/login page
                        if 'text/html' in content_type:
                            self.logger.debug("Got HTML instead of PDF - may need login or page has PDF links")
                            return self._try_find_pdf_on_page(new_page, dest_path)
                            
                    elif response and response.status == 403:
                        self.logger.warning("HTTP 403 - Access denied")
                        return None
                finally:
                    new_page.close()
                    
            except Exception as e2:
                self.logger.debug(f"Page load also failed: {e2}")
                return None
        
        return None
    
    def _download_from_page(self, page, url: str, dest_path: Path, doi: Optional[str] = None) -> Optional[Path]:
        """Navigate to a paper page and find/download the PDF."""
        try:
            # Use domcontentloaded instead of networkidle to avoid timeouts
            response = page.goto(url, timeout=self.timeout, wait_until='domcontentloaded')
            
            if not response:
                self.logger.warning("No response from page")
                return None
            
            # Wait a bit for dynamic content but don't block
            try:
                page.wait_for_load_state('networkidle', timeout=5000)
            except Exception:
                pass  # Timeout is okay, we'll try to find PDF anyway
            
            # Check for publisher-specific handlers FIRST
            current_url = page.url
            
            # ScienceDirect (Elsevier) - use specialized handler
            if 'sciencedirect.com' in current_url:
                result = self._download_sciencedirect(page, dest_path)
                if result:
                    return result
            
            # SAGE journals
            if 'sagepub.com' in current_url:
                result = self._download_sage(page, dest_path)
                if result:
                    return result
            
            # IOP Science journals
            if 'iopscience.iop.org' in current_url:
                result = self._download_iop(page, dest_path)
                if result:
                    return result
            
            # AIP Publishing (JASA, etc.)
            if 'pubs.aip.org' in current_url:
                result = self._download_aip(page, dest_path)
                if result:
                    return result
            
            # Try to find PDF link on the page
            return self._try_find_pdf_on_page(page, dest_path, doi)
            
        except Exception as e:
            self.logger.error(f"Failed to load page: {e}")
            return None
    
    def _try_find_pdf_on_page(self, page, dest_path: Path, doi: Optional[str] = None) -> Optional[Path]:
        """Find and click PDF download link on the page."""
        
        page_host = urlparse(page.url).netloc
        # Extract base domain (e.g., frontiersin.org from www.frontiersin.org)
        page_domain = '.'.join(page_host.split('.')[-2:]) if '.' in page_host else page_host
        
        # Publisher-specific selectors (prioritized)
        pdf_selectors = [
            # Frontiers
            'a.download-files-pdf',
            'a[data-testid="download-pdf"]',
            'a.ArticlePdf',
            
            # Nature/Springer
            'a[data-track-action="download pdf"]',
            'a.c-pdf-download__link',
            
            # PLOS
            'a#downloadPdf',
            'a[data-doi]:has-text("PDF")',
            
            # Wiley
            'a.pdf-download',
            
            # Elsevier/ScienceDirect
            'a.pdf-download-btn-link',
            'a[id*="pdfLink"]',
            
            # PeerJ
            'a.pdf-button',
            'a[href*="/article/"][href$="/pdf"]',
            
            # Generic but specific to current domain
            'a.download-pdf',
            '.pdf-download',
            '#pdfLink',
            
            # Download buttons
            'a:has-text("Download PDF")',
            'button:has-text("Download PDF")',
            
            # More generic but still likely main PDF
            'a[href*="/pdf/"]',
            'a[href*="pdf?"]',
            'a[href$=".pdf"]',
        ]
        
        for selector in pdf_selectors:
            try:
                links = page.query_selector_all(selector)
                for link in links:
                    href = link.get_attribute('href')
                    if href:
                        # Skip obviously external links (different base domain)
                        if href.startswith('http'):
                            link_host = urlparse(href).netloc
                            link_domain = '.'.join(link_host.split('.')[-2:]) if '.' in link_host else link_host
                            # Allow same base domain (e.g., cdn.frontiersin.org for frontiersin.org)
                            if link_domain and link_domain != page_domain:
                                self.logger.debug(f"Skipping external link: {href[:60]}...")
                                continue
                        
                        self.logger.debug(f"Found PDF link: {href[:60]}...")
                        
                        # Handle relative URLs
                        if href.startswith('/'):
                            base_url = f"{page.url.split('//')[0]}//{page.url.split('//')[1].split('/')[0]}"
                            href = base_url + href
                        
                        # Try to download via click
                        try:
                            # For CDP mode, watch Downloads folder
                            if self._use_real_session:
                                downloads_dir = self._get_downloads_folder()
                                existing_files = set(downloads_dir.glob('*.pdf'))
                                link.click()
                                time.sleep(3)  # Wait for download to start
                                
                                # Check for new file
                                for _ in range(30):
                                    current_files = set(downloads_dir.glob('*.pdf'))
                                    new_files = current_files - existing_files
                                    for new_file in new_files:
                                        if new_file.exists() and new_file.stat().st_size > 5000:
                                            time.sleep(1)
                                            if new_file.stat().st_size > 5000:
                                                import shutil
                                                shutil.move(str(new_file), str(dest_path))
                                                self.logger.info(f"Downloaded via CDP click: {dest_path.name}")
                                                return dest_path
                                    time.sleep(1)
                            else:
                                with page.expect_event('download', timeout=self.timeout) as download_info:
                                    link.click()
                                
                                download = download_info.value
                                download.save_as(dest_path)
                                
                                if dest_path.exists() and dest_path.stat().st_size > 5000:
                                    self.logger.info(f"Downloaded via click: {dest_path.name}")
                                    return dest_path
                        except Exception:
                            # Click didn't trigger download, try navigating via JavaScript
                            try:
                                with page.expect_event('download', timeout=self.timeout) as download_info:
                                    page.evaluate(f'window.location.href = "{href}"')
                                
                                download = download_info.value
                                download.save_as(dest_path)
                                
                                if dest_path.exists() and dest_path.stat().st_size > 5000:
                                    self.logger.info(f"Downloaded via JS navigation: {dest_path.name}")
                                    return dest_path
                            except Exception:
                                # Try opening in new page and reading content
                                new_page = self._context.new_page()
                                try:
                                    response = new_page.goto(href, timeout=self.timeout, wait_until='domcontentloaded')
                                    if response and 'application/pdf' in response.headers.get('content-type', ''):
                                        content = response.body()
                                        if content and content[:4] == b'%PDF':
                                            dest_path.write_bytes(content)
                                            self.logger.info(f"Downloaded via content read: {dest_path.name}")
                                            return dest_path
                                finally:
                                    new_page.close()
                                
            except Exception as e:
                self.logger.debug(f"Selector {selector} failed: {e}")
                continue
        
        self.logger.debug("No PDF link found on page")
        return None
    
    def download_batch(
        self,
        entries: List[Dict[str, Any]],
        delay: float = 2.0
    ) -> Dict[str, Any]:
        """
        Download PDFs for multiple papers.
        
        Args:
            entries: List of paper entries with 'doi', 'url', 'title' fields
            delay: Delay between downloads in seconds (be polite to servers)
            
        Returns:
            Dictionary with statistics and results
        """
        results = {
            'total': len(entries),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'downloaded_files': []
        }
        
        for i, entry in enumerate(entries, 1):
            doi = entry.get('doi') or entry.get('DOI')
            url = entry.get('url') or entry.get('URL')
            title = entry.get('title', 'Unknown')[:50]
            
            self.logger.info(f"[{i}/{len(entries)}] {title}...")
            
            if not doi and not url:
                self.logger.warning("  No DOI or URL available")
                results['failed'] += 1
                continue
            
            # Try DOI first
            pdf_path = None
            if doi:
                # Construct publisher URL from DOI
                doi_url = f"https://doi.org/{doi}"
                pdf_path = self.download_pdf(doi_url, doi=doi)
            
            # Try URL if DOI failed
            if not pdf_path and url:
                pdf_path = self.download_pdf(url, doi=doi)
            
            if pdf_path:
                results['success'] += 1
                results['downloaded_files'].append(str(pdf_path))
            else:
                results['failed'] += 1
            
            # Polite delay
            if i < len(entries):
                time.sleep(delay)
        
        return results


def interactive_login():
    """
    Standalone function to open browser for interactive login.
    Run this to log into your institution before downloading.
    """
    print("\n" + "="*60)
    print("REVIEW BUDDY - INSTITUTIONAL LOGIN")
    print("="*60)
    print("\nThis will open a browser where you can log into your")
    print("institution's library portal (e.g., university login).")
    print("\nYour session will be saved for future PDF downloads.")
    
    url = input("\nEnter the login URL (or press Enter for Google Scholar): ").strip()
    if not url:
        url = "https://scholar.google.com"
    
    downloader = BrowserDownloader(headless=False)
    downloader.login_interactive(url)


if __name__ == "__main__":
    # Run interactive login when called directly
    interactive_login()
