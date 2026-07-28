"""
Zotero-style PDF finder.

This mirrors what the Zotero desktop app does when you paste DOIs into
"Add Item(s) by Identifier". Contrary to a common assumption, Zotero's
*translators* do not download the PDF from a DOI. The real flow is:

  1. identifier -> metadata        (a search translator: Crossref/DOI, PubMed, arXiv)
  2. metadata   -> file resolvers  (Zotero.Attachments.getFileResolvers)
  3. each resolver yields either a direct PDF `url` or a `pageURL`
  4. for a `pageURL`, Zotero fetches the page and runs the *web translators*
     on the resulting document to extract the PDF link
     (Zotero.Utilities.Internal.getFileFromDocument)

Resolver order in the app (chrome/content/zotero/xpcom/attachments.js):
    ['doi', 'url', 'oa', 'custom']
      doi  -> pageURL https://doi.org/<DOI>
      url  -> pageURL <item url>
      oa   -> pageURL https://pmc.ncbi.nlm.nih.gov/articles/<PMCID>/   (if PMCID)
      oa   -> POST https://services.zotero.org/oa/search {doi}
              -> [{url?, pageURL?, version}]  (Zotero's own OA index)

Step 4 is where translators come in, and the OA index in step 3 is what makes
the app find so many PDFs - it is a curated Unpaywall-derived service and is
*not* part of the translators repo at all.

This module reproduces that chain. The OA index works with no local server;
the translator step needs the vendored translation server (see
scripts/setup_zotero.py).
"""

import logging
from typing import Iterator, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

DEFAULT_SERVER_URL = "http://127.0.0.1:1969"

# Zotero's own open-access index (ZOTERO_CONFIG.SERVICES_URL + 'oa/search')
OA_SEARCH_URL = "https://services.zotero.org/oa/search"

# Content types Zotero accepts as a "file" (FIND_AVAILABLE_FILE_TYPES)
PDF_CONTENT_TYPES = ("application/pdf",)


class ZoteroTranslationClient:
    """Client for the Zotero translation-server HTTP API + Zotero's OA index."""

    def __init__(self, base_url: str = DEFAULT_SERVER_URL, timeout: int = 60,
                 session: Optional[requests.Session] = None):
        """
        Args:
            base_url: Base URL of the translation server
            timeout: Request timeout in seconds (translation fetches and parses
                     the target page, so it can be slow)
            session: Optional shared requests.Session (connection reuse)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self._available: Optional[bool] = None

    # ------------------------------------------------------------------
    # Translation server
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Check whether the translation server is reachable (cached)."""
        if self._available is None:
            try:
                # Any HTTP response (even 404) means the server is up
                self.session.get(f"{self.base_url}/", timeout=3)
                self._available = True
            except requests.RequestException:
                self._available = False
        return self._available

    def translate_url(self, url: str) -> List[dict]:
        """
        Translate a web page URL into Zotero items.

        Returns a list of Zotero item dicts (empty if translation failed).
        Requires the review_buddy attachments patch for `attachments` to be
        populated - see vendor/patches/expose-attachments.patch.
        """
        try:
            r = self.session.post(
                f"{self.base_url}/web",
                data=url.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
                timeout=self.timeout,
            )

            # 300 = multiple items on the page; pick the first and re-post
            if r.status_code == 300:
                data = r.json()
                items = data.get("items", {})
                if items:
                    first_key = next(iter(items))
                    data["items"] = {first_key: items[first_key]}
                    r = self.session.post(f"{self.base_url}/web", json=data,
                                          timeout=self.timeout)

            if r.status_code == 200:
                result = r.json()
                if isinstance(result, list):
                    return result

            logger.debug(f"Zotero translation failed ({r.status_code}) for: {url}")

        except requests.RequestException as e:
            logger.debug(f"Zotero translation error for {url}: {e}")
        except ValueError as e:
            logger.debug(f"Zotero returned invalid JSON for {url}: {e}")

        return []

    def pdf_from_page(self, page_url: str) -> Optional[str]:
        """
        Run the web translators on `page_url` and return a PDF attachment URL.

        This is the equivalent of Zotero's getFileFromDocument().
        """
        for item in self.translate_url(page_url):
            for attachment in item.get("attachments") or []:
                if attachment.get("mimeType") in PDF_CONTENT_TYPES and attachment.get("url"):
                    return attachment["url"]
        return None

    # ------------------------------------------------------------------
    # Zotero's open-access index
    # ------------------------------------------------------------------

    def open_access_locations(self, doi: str) -> List[dict]:
        """
        Query Zotero's OA index for a DOI.

        Returns a list of {url?, pageURL?, version} dicts. Works without the
        local translation server.
        """
        if not doi:
            return []
        try:
            r = self.session.post(OA_SEARCH_URL, json={"doi": doi}, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    return data
            else:
                logger.debug(f"Zotero OA lookup returned {r.status_code} for {doi}")
        except (requests.RequestException, ValueError) as e:
            logger.debug(f"Zotero OA lookup error for {doi}: {e}")
        return []

    # ------------------------------------------------------------------
    # Resolver chain (mirrors Zotero.Attachments.getFileResolvers)
    # ------------------------------------------------------------------

    def file_resolvers(self, doi: Optional[str] = None, url: Optional[str] = None,
                       pmcid: Optional[str] = None) -> List[dict]:
        """
        Build the ordered resolver list, same order as the Zotero app:
        doi -> url -> pmcid -> open-access index.

        Each resolver is {'url': ...} and/or {'pageURL': ...} plus 'method'.
        """
        resolvers: List[dict] = []

        if doi:
            resolvers.append({"pageURL": f"https://doi.org/{doi}", "method": "zotero:doi"})
        if url:
            resolvers.append({"pageURL": url, "method": "zotero:url"})
        if pmcid:
            resolvers.append({
                "pageURL": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
                "method": "zotero:pmc",
            })
        for loc in self.open_access_locations(doi) if doi else []:
            resolvers.append({
                "url": loc.get("url"),
                "pageURL": loc.get("pageURL"),
                "method": "zotero:oa",
                "version": loc.get("version"),
            })

        return resolvers

    def iter_pdf_candidates(self, doi: Optional[str] = None, url: Optional[str] = None,
                            pmcid: Optional[str] = None) -> Iterator[Tuple[str, str, str]]:
        """
        Yield (pdf_url, referer, method) candidates in Zotero's resolver order.

        For a resolver with a direct `url`, that URL is yielded as-is. For a
        `pageURL`, the page is inspected: a citation_pdf_url meta tag is used
        when present (cheap, and what Zotero's Embedded Metadata translator
        reads), otherwise the page is handed to the translation server so the
        site-specific translator can find the link.

        The caller is responsible for verifying/downloading each candidate.
        """
        seen = set()

        for resolver in self.file_resolvers(doi=doi, url=url, pmcid=pmcid):
            method = resolver["method"]

            direct = resolver.get("url")
            if direct and direct not in seen:
                seen.add(direct)
                yield direct, resolver.get("pageURL") or "", method

            page_url = resolver.get("pageURL")
            if not page_url or page_url in seen:
                continue
            seen.add(page_url)

            # 1) Cheap path: fetch the page once and read citation_pdf_url.
            #    Also catches the "DOI resolves straight to a PDF" case.
            resolved_url = page_url
            try:
                r = self.session.get(page_url, timeout=30, allow_redirects=True, stream=True)
                resolved_url = r.url
                ctype = r.headers.get("content-type", "").lower()
                if any(t in ctype for t in PDF_CONTENT_TYPES):
                    r.close()
                    if resolved_url not in seen:
                        seen.add(resolved_url)
                        yield resolved_url, page_url, method + ":direct"
                    continue
                # Read enough of the head to find the meta tag, then stop.
                # iter_content works for both requests and curl_cffi sessions.
                body = b""
                for chunk in r.iter_content(chunk_size=32768):
                    body += chunk
                    if len(body) >= 400_000:
                        break
                r.close()
                meta_pdf = _citation_pdf_url(body, resolved_url)
                if meta_pdf and meta_pdf not in seen:
                    seen.add(meta_pdf)
                    yield meta_pdf, resolved_url, method + ":meta"
            except Exception as e:
                logger.debug(f"Zotero resolver fetch failed for {page_url}: {e}")

            # 2) Translator path: let the site-specific translator find the PDF
            if self.is_available():
                translated = self.pdf_from_page(resolved_url)
                if translated and translated not in seen:
                    seen.add(translated)
                    yield translated, resolved_url, method + ":translator"

    # ------------------------------------------------------------------
    # Backwards-compatible helper
    # ------------------------------------------------------------------

    def get_pdf_url(self, doi: Optional[str] = None,
                    url: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """Return the first (pdf_url, page_url) candidate, or (None, None)."""
        for pdf_url, referer, _method in self.iter_pdf_candidates(doi=doi, url=url):
            return pdf_url, referer
        return None, None


def _citation_pdf_url(html_bytes: bytes, base_url: str) -> Optional[str]:
    """Extract a citation_pdf_url meta tag from raw HTML."""
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin

        soup = BeautifulSoup(html_bytes, "html.parser")
        for attrs in ({"name": "citation_pdf_url"}, {"property": "citation_pdf_url"}):
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                return urljoin(base_url, tag["content"])
    except Exception as e:
        logger.debug(f"citation_pdf_url parse error: {e}")
    return None
