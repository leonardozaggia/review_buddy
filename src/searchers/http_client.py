"""
Dual-transport HTTP client.

Publishers increasingly gate content on *how the client looks*, not on whether
you have access. Two transports fail on disjoint sets of sites:

  * `requests`   - plain Python TLS fingerprint. Blocked by MDPI, PMC, Springer.
  * `curl_cffi`  - impersonates Chrome's TLS/JA3 fingerprint. Gets through those,
                   but SAGE (journals.sagepub.com) specifically blocks it.

Measured on a 123-paper corpus: curl_cffi alone cut HTTP 403s from 37 to 17 but
lost 5 SAGE papers that plain requests retrieved. Neither transport dominates,
so this client tries one and automatically retries the other when the response
looks like a bot-block. The union beats either alone.

Sessions are thread-local: curl_cffi wraps libcurl handles that are not safe to
share across threads, and the downloader runs several workers.
"""

import logging
import threading
import time
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Statuses meaning "we don't like your client" -> worth retrying on the other
# transport (a different TLS fingerprint may be accepted).
BLOCK_STATUSES = (403, 406, 429)

# Statuses that mean "you are going too fast" -> worth waiting longer.
# NOTE: 403 is deliberately NOT here. A Cloudflare bot-block is permanent for
# this client, so backing off just serialises the run behind a wall of 30s
# sleeps (measured: 49 Elsevier papers all 403, run never finished).
THROTTLE_PENALTY_STATUSES = (429, 503)

# Minimum gap between requests to the same host. Zotero does the same thing
# (see beforeRequest/afterRequest in attachments.js): without it, a parallel
# downloader trips publisher rate limits and earns an IP block that persists
# for hours - which looks exactly like "the tool can't download this paper".
DEFAULT_DOMAIN_DELAY = 1.0
MAX_DOMAIN_BACKOFF = 30.0


# Infrastructure APIs built for volume - throttling these only wastes time
# (doi.org in particular is hit once per paper).
THROTTLE_EXEMPT_HOSTS = frozenset({
    "doi.org", "dx.doi.org",
    "api.crossref.org",
    "api.unpaywall.org",
    "services.zotero.org",
    "eutils.ncbi.nlm.nih.gov",
    "www.ebi.ac.uk",
    "127.0.0.1", "localhost",
})


class DomainThrottle:
    """Per-host request spacing with exponential backoff on block responses."""

    def __init__(self, base_delay: float = DEFAULT_DOMAIN_DELAY):
        self.base_delay = base_delay
        self._next_allowed = {}   # host -> monotonic timestamp
        self._backoff = {}        # host -> current extra delay
        self._lock = threading.Lock()

    @staticmethod
    def host_of(url: str) -> str:
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""

    def wait(self, url: str):
        host = self.host_of(url)
        if not host or host.split(":")[0] in THROTTLE_EXEMPT_HOSTS:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                ready_at = self._next_allowed.get(host, 0.0)
                if now >= ready_at:
                    delay = self.base_delay + self._backoff.get(host, 0.0)
                    self._next_allowed[host] = now + delay
                    return
                sleep_for = ready_at - now
            time.sleep(min(sleep_for, MAX_DOMAIN_BACKOFF))

    def penalise(self, url: str):
        """Register a block response - back off harder for this host."""
        host = self.host_of(url)
        if not host:
            return
        with self._lock:
            current = self._backoff.get(host, 0.0)
            self._backoff[host] = min(max(current * 2, 2.0), MAX_DOMAIN_BACKOFF)
            logger.debug(f"Backing off {host} to +{self._backoff[host]}s")

    def reward(self, url: str):
        """A success decays the backoff for this host."""
        host = self.host_of(url)
        if not host:
            return
        with self._lock:
            if host in self._backoff:
                self._backoff[host] /= 2
                if self._backoff[host] < 0.5:
                    del self._backoff[host]

try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on install
    curl_requests = None
    CURL_CFFI_AVAILABLE = False


class DualTransportSession:
    """
    A requests-like session that transparently retries with a second transport.

    Exposes the subset of the requests API the downloader uses: `get`, `post`,
    `headers`. Response objects from both libraries support `.status_code`,
    `.headers`, `.url`, `.iter_content()` and `.close()`.
    """

    def __init__(self, user_agent: str, pool_size: int = 8,
                 impersonate: str = "chrome", domain_delay: float = DEFAULT_DOMAIN_DELAY):
        self.user_agent = user_agent
        self.pool_size = pool_size
        self.impersonate = impersonate
        self.headers = {"User-Agent": user_agent}
        self.throttle = DomainThrottle(domain_delay)
        self._local = threading.local()

    # -- transports ----------------------------------------------------

    @property
    def _requests_session(self) -> requests.Session:
        s = getattr(self._local, "req", None)
        if s is None:
            from requests.adapters import HTTPAdapter
            s = requests.Session()
            s.headers.update({"User-Agent": self.user_agent})
            adapter = HTTPAdapter(pool_connections=self.pool_size,
                                  pool_maxsize=self.pool_size)
            s.mount("https://", adapter)
            s.mount("http://", adapter)
            self._local.req = s
        return s

    @property
    def _curl_session(self):
        if not CURL_CFFI_AVAILABLE:
            return None
        s = getattr(self._local, "curl", None)
        if s is None:
            # Don't override User-Agent here: curl_cffi sets one that matches
            # the impersonated TLS fingerprint, and a mismatch is itself a
            # bot-detection signal.
            s = curl_requests.Session(impersonate=self.impersonate)
            self._local.curl = s
        return s

    # -- API -----------------------------------------------------------

    def get(self, url: str, **kwargs):
        """
        GET with automatic transport fallback.

        Tries curl_cffi first (it unblocks more sites), and retries with
        requests when the response looks like a block or the transport errors.
        """
        kwargs.setdefault("allow_redirects", True)
        primary, secondary = self._curl_session, self._requests_session

        self.throttle.wait(url)
        if primary is None:
            r = secondary.get(url, **kwargs)
            (self.throttle.penalise if r.status_code in THROTTLE_PENALTY_STATUSES
             else self.throttle.reward)(url)
            return r

        try:
            r = primary.get(url, **kwargs)
            if r.status_code not in BLOCK_STATUSES:
                self.throttle.reward(url)
                return r
            logger.debug(f"curl_cffi got {r.status_code} for {url} - retrying with requests")
            try:
                r.close()
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"curl_cffi transport error for {url} ({e}) - retrying with requests")

        # curl_cffi accepts some kwargs requests doesn't and vice versa
        kwargs.pop("impersonate", None)
        self.throttle.wait(url)
        r = secondary.get(url, **kwargs)
        (self.throttle.penalise if r.status_code in THROTTLE_PENALTY_STATUSES
         else self.throttle.reward)(url)
        return r

    def post(self, url: str, **kwargs):
        """POST always uses requests - API endpoints don't bot-block."""
        return self._requests_session.post(url, **kwargs)

    def close(self):
        for attr in ("req", "curl"):
            s = getattr(self._local, attr, None)
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass
