"""
Zotero Translation Server Client

Client for communicating with a local Zotero Translation Server instance.
The server provides metadata extraction and PDF discovery from URLs, DOIs, PMIDs, and arXiv IDs.

Installation:
    Docker: docker run -d -p 1969:1969 zotero/translation-server
    See docs/ZOTERO_SETUP.md for detailed instructions.
"""
import logging
import time
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

import requests


class ZoteroTranslationClient:
    """
    Client for Zotero Translation Server.
    
    The Zotero Translation Server is a Node.js service that runs locally
    and provides API endpoints to extract metadata and attachments from
    URLs, DOIs, PMIDs, ISBNs, and arXiv IDs.
    
    Default endpoint: http://localhost:1969
    
    Attributes:
        server_url: Base URL of the Zotero Translation Server
        timeout: Request timeout in seconds
        logger: Logger instance for this client
    """
    
    def __init__(self, server_url: str = "http://localhost:1969", timeout: int = 30):
        """
        Initialize the Zotero Translation Client.
        
        Args:
            server_url: Base URL of the Zotero Translation Server (default: http://localhost:1969)
            timeout: Request timeout in seconds (default: 30)
        """
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        self.logger = logging.getLogger("ZoteroClient")
        self._available = None  # Cache availability check
        self._last_availability_check = 0
        self._availability_cache_ttl = 60  # Re-check every 60 seconds
        
        # Retry configuration
        self.max_retries = 3
        self.base_delay = 1  # Base delay for exponential backoff
    
    def is_available(self) -> bool:
        """
        Check if the Zotero Translation Server is running and responsive.
        
        Caches the result for 60 seconds to avoid repeated checks.
        
        Returns:
            True if the server is available, False otherwise
        """
        current_time = time.time()
        
        # Use cached result if still valid
        if (self._available is not None and 
            current_time - self._last_availability_check < self._availability_cache_ttl):
            return self._available
        
        try:
            # Simple health check - just try to connect
            # The server doesn't have a dedicated health endpoint,
            # so we make a simple request to the root
            response = requests.get(
                self.server_url,
                timeout=5
            )
            # Server returns 400 for GET to root, but that means it's running
            self._available = response.status_code in [200, 400, 404, 405]
            
        except requests.exceptions.ConnectionError:
            self.logger.debug(f"Zotero Translation Server not available at {self.server_url}")
            self._available = False
        except requests.exceptions.Timeout:
            self.logger.debug(f"Zotero Translation Server timeout at {self.server_url}")
            self._available = False
        except Exception as e:
            self.logger.debug(f"Zotero Translation Server check failed: {e}")
            self._available = False
        
        self._last_availability_check = current_time
        return self._available
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        retry_count: int = 0
    ) -> Optional[requests.Response]:
        """
        Make an HTTP request with retry logic and error handling.
        
        Args:
            method: HTTP method ('GET', 'POST', etc.)
            endpoint: API endpoint (will be appended to server_url)
            data: Request body data (for POST requests)
            headers: Additional headers
            retry_count: Current retry attempt (for internal use)
            
        Returns:
            Response object if successful, None otherwise
        """
        url = f"{self.server_url}{endpoint}"
        
        default_headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        if headers:
            default_headers.update(headers)
        
        try:
            if method.upper() == 'POST':
                # Check if we should send as plain text or JSON
                if default_headers.get('Content-Type') == 'text/plain':
                    response = requests.post(
                        url,
                        data=data,
                        headers=default_headers,
                        timeout=self.timeout
                    )
                else:
                    response = requests.post(
                        url,
                        json=data,
                        headers=default_headers,
                        timeout=self.timeout
                    )
            else:
                response = requests.get(
                    url,
                    headers=default_headers,
                    timeout=self.timeout
                )
            
            # Handle rate limiting
            if response.status_code == 429:
                if retry_count < self.max_retries:
                    wait_time = min(self.base_delay * (2 ** retry_count), 10)
                    self.logger.debug(f"Rate limited, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    return self._make_request(method, endpoint, data, headers, retry_count + 1)
                else:
                    self.logger.warning("Rate limit exceeded, max retries reached")
                    return None
            
            return response
            
        except requests.exceptions.ConnectionError:
            self.logger.debug(f"Connection error to Zotero server: {url}")
            self._available = False
            return None
        except requests.exceptions.Timeout:
            self.logger.debug(f"Request timeout to Zotero server: {url}")
            if retry_count < self.max_retries:
                wait_time = min(self.base_delay * (2 ** retry_count), 10)
                self.logger.debug(f"Timeout, retrying in {wait_time}s...")
                time.sleep(wait_time)
                return self._make_request(method, endpoint, data, headers, retry_count + 1)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error in Zotero request: {e}")
            return None
    
    def translate_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract metadata from a URL using Zotero translators.
        
        Args:
            url: The URL to translate (e.g., a paper landing page)
            
        Returns:
            Dictionary with metadata if successful, None otherwise.
            The dictionary contains fields like 'title', 'creators', 'DOI',
            'abstractNote', 'attachments', etc.
        """
        # Validate URL format
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                self.logger.debug(f"Invalid URL format: {url}")
                return None
        except Exception:
            self.logger.debug(f"URL parsing failed: {url}")
            return None
        
        self.logger.debug(f"Translating URL: {url[:80]}...")
        
        response = self._make_request(
            'POST',
            '/web',
            data={'url': url, 'session': 'review_buddy'}
        )
        
        if response is None:
            return None
        
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    self.logger.debug(f"Successfully translated URL, got {len(data)} item(s)")
                    return data[0]  # Return first item
                else:
                    self.logger.debug("Zotero returned empty response for URL")
                    return None
            except ValueError as e:
                self.logger.debug(f"Invalid JSON response from Zotero: {e}")
                return None
        elif response.status_code == 300:
            # Multiple choices - Zotero needs more info
            self.logger.debug("Zotero returned multiple choices, using first result")
            try:
                data = response.json()
                if isinstance(data, dict) and 'items' in data:
                    # Return first item from choices
                    items = list(data['items'].values())
                    if items:
                        return items[0]
            except ValueError:
                pass
            return None
        elif response.status_code == 501:
            self.logger.debug("No translator available for this URL")
            return None
        else:
            self.logger.debug(f"Zotero URL translation failed: HTTP {response.status_code}")
            return None
    
    def translate_identifier(
        self, 
        identifier: str, 
        identifier_type: str = "auto"
    ) -> Optional[Dict[str, Any]]:
        """
        Extract metadata from a DOI, PMID, ISBN, or arXiv ID.
        
        Args:
            identifier: The identifier value (e.g., "10.1234/example", "12345678", "2101.00001")
            identifier_type: Type of identifier - "doi", "pmid", "arxiv", "isbn", or "auto"
                           If "auto", the type will be detected automatically.
            
        Returns:
            Dictionary with metadata if successful, None otherwise.
        """
        if not identifier:
            return None
        
        identifier = str(identifier).strip()
        
        # Auto-detect identifier type
        if identifier_type == "auto":
            identifier_type = self._detect_identifier_type(identifier)
            self.logger.debug(f"Auto-detected identifier type: {identifier_type}")
        
        self.logger.debug(f"Translating {identifier_type}: {identifier}")
        
        # Build the search query based on identifier type
        # Zotero's /search endpoint accepts different identifier formats
        if identifier_type == "doi":
            # DOI - send directly
            search_text = identifier if identifier.startswith("10.") else f"10.{identifier}"
        elif identifier_type == "pmid":
            # PMID - just the number
            search_text = identifier.replace("PMID:", "").replace("pmid:", "").strip()
        elif identifier_type == "arxiv":
            # arXiv ID
            search_text = identifier.replace("arXiv:", "").replace("arxiv:", "").strip()
        elif identifier_type == "isbn":
            # ISBN - just the number
            search_text = identifier.replace("-", "").replace(" ", "")
        else:
            search_text = identifier
        
        response = self._make_request(
            'POST',
            '/search',
            data=search_text,
            headers={'Content-Type': 'text/plain'}
        )
        
        if response is None:
            return None
        
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    self.logger.debug(f"Successfully translated {identifier_type}")
                    return data[0]
                else:
                    self.logger.debug(f"Zotero returned empty response for {identifier_type}")
                    return None
            except ValueError as e:
                self.logger.debug(f"Invalid JSON response from Zotero: {e}")
                return None
        elif response.status_code == 501:
            self.logger.debug(f"No translator available for {identifier_type}: {identifier}")
            return None
        else:
            self.logger.debug(f"Zotero identifier translation failed: HTTP {response.status_code}")
            return None
    
    def _detect_identifier_type(self, identifier: str) -> str:
        """
        Detect the type of identifier based on its format.
        
        Args:
            identifier: The identifier string
            
        Returns:
            Detected type: "doi", "pmid", "arxiv", "isbn", or "unknown"
        """
        identifier = identifier.strip()
        
        # DOI detection
        if identifier.startswith("10.") or identifier.lower().startswith("doi:"):
            return "doi"
        
        # PMID detection (all digits, 1-8 characters typically)
        if identifier.lower().startswith("pmid:"):
            return "pmid"
        if identifier.isdigit() and len(identifier) <= 10:
            return "pmid"
        
        # arXiv detection
        if identifier.lower().startswith("arxiv:"):
            return "arxiv"
        # New format: YYMM.NNNNN
        import re
        if re.match(r'^\d{4}\.\d{4,5}(v\d+)?$', identifier):
            return "arxiv"
        # Old format: subject-class/YYMMNNN
        if re.match(r'^[a-z-]+/\d{7}$', identifier, re.IGNORECASE):
            return "arxiv"
        
        # ISBN detection (10 or 13 digits, may have hyphens)
        isbn_clean = identifier.replace("-", "").replace(" ", "")
        if isbn_clean.isdigit() and len(isbn_clean) in [10, 13]:
            return "isbn"
        if re.match(r'^[\dX]{10}$|^\d{13}$', isbn_clean, re.IGNORECASE):
            return "isbn"
        
        return "unknown"
    
    def extract_pdf_url(self, metadata: Dict[str, Any]) -> Optional[str]:
        """
        Extract PDF URL from Zotero metadata.
        
        Zotero translators may include PDF attachments in the metadata.
        This method extracts the URL of the first PDF attachment found.
        
        Args:
            metadata: Metadata dictionary from translate_url or translate_identifier
            
        Returns:
            PDF URL if found, None otherwise
        """
        if not metadata:
            return None
        
        # Check attachments array
        attachments = metadata.get('attachments', [])
        
        for attachment in attachments:
            # Check for PDF mime type
            mime_type = attachment.get('mimeType', '').lower()
            if mime_type == 'application/pdf':
                url = attachment.get('url')
                if url:
                    self.logger.debug(f"Found PDF attachment: {url[:80]}...")
                    return url
            
            # Some translators use 'contentType' instead of 'mimeType'
            content_type = attachment.get('contentType', '').lower()
            if content_type == 'application/pdf':
                url = attachment.get('url')
                if url:
                    self.logger.debug(f"Found PDF attachment: {url[:80]}...")
                    return url
            
            # Check title for PDF indication
            title = attachment.get('title', '').lower()
            if 'pdf' in title or 'full text' in title:
                url = attachment.get('url')
                if url and '.pdf' in url.lower():
                    self.logger.debug(f"Found PDF by title: {url[:80]}...")
                    return url
        
        # Check for direct PDF link in the metadata itself
        # Some Zotero items have a direct 'url' field pointing to PDF
        url = metadata.get('url', '')
        if url and url.lower().endswith('.pdf'):
            self.logger.debug(f"Found direct PDF URL: {url[:80]}...")
            return url
        
        # Check for pdfUrl field (some translators use this)
        pdf_url = metadata.get('pdfUrl')
        if pdf_url:
            self.logger.debug(f"Found pdfUrl field: {pdf_url[:80]}...")
            return pdf_url
        
        return None
    
    def batch_translate(self, items: List[str]) -> List[Dict[str, Any]]:
        """
        Process multiple identifiers or URLs.
        
        Note: Zotero Translation Server doesn't have a native batch endpoint,
        so this processes items sequentially with a small delay to avoid
        overwhelming the server.
        
        Args:
            items: List of URLs or identifiers to translate
            
        Returns:
            List of metadata dictionaries (may include None for failed items)
        """
        results = []
        
        for i, item in enumerate(items):
            self.logger.debug(f"Batch processing item {i+1}/{len(items)}: {item[:50]}...")
            
            # Detect if it's a URL or identifier
            if item.startswith('http://') or item.startswith('https://'):
                metadata = self.translate_url(item)
            else:
                metadata = self.translate_identifier(item)
            
            results.append(metadata)
            
            # Small delay between requests to be respectful
            if i < len(items) - 1:
                time.sleep(0.5)
        
        return results
    
    def get_metadata_summary(self, metadata: Dict[str, Any]) -> str:
        """
        Get a human-readable summary of metadata for logging.
        
        Args:
            metadata: Metadata dictionary from translation
            
        Returns:
            Summary string with title, DOI, and attachment count
        """
        if not metadata:
            return "No metadata"
        
        title = metadata.get('title', 'Unknown title')[:60]
        doi = metadata.get('DOI', 'No DOI')
        attachments = len(metadata.get('attachments', []))
        
        return f"'{title}' | DOI: {doi} | Attachments: {attachments}"


# Example usage
if __name__ == "__main__":
    # Set up logging for testing
    logging.basicConfig(level=logging.DEBUG)
    
    client = ZoteroTranslationClient()
    
    if client.is_available():
        print("✓ Zotero Translation Server is running")
        
        # Test DOI translation
        metadata = client.translate_identifier("10.1371/journal.pone.0123456", "doi")
        if metadata:
            print(f"✓ DOI translation: {client.get_metadata_summary(metadata)}")
            pdf_url = client.extract_pdf_url(metadata)
            if pdf_url:
                print(f"  PDF URL: {pdf_url[:80]}")
        
        # Test URL translation
        metadata = client.translate_url("https://arxiv.org/abs/2101.00001")
        if metadata:
            print(f"✓ URL translation: {client.get_metadata_summary(metadata)}")
    else:
        print("✗ Zotero Translation Server is not available")
        print(f"  Expected at: {client.server_url}")
        print("  To start: docker run -d -p 1969:1969 zotero/translation-server")
