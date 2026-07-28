"""
Real-browser PDF fetcher (Camoufox: a patched, anti-detect Firefox/Gecko) —
the last mile to close the gap with the Zotero desktop app.

Why this exists: the resolver chain in zotero_client.py and the dual-transport
client in http_client.py reproduce everything Zotero does at the HTTP level.
Measured against 123 real papers, that closed most of the gap — except for
Cloudflare-protected publishers (ScienceDirect, Wiley, MDPI), where Elsevier
alone accounted for 45 of 75 remaining failures.

## Why a plain browser isn't enough

A real Gecko engine (stock Playwright Firefox) was tried first and still got
Cloudflare's interactive "prove you're human" challenge on Elsevier/Wiley. The
reason is structural, not a matter of engine choice: WebDriver-based automation
(Playwright, Selenium, Puppeteer — all of them) sets `navigator.webdriver =
true` by protocol design, because that flag is literally how a remote client
tells the browser "let me control you". Cloudflare checks it directly. Zotero
doesn't trigger this because it isn't "automating" a browser via a remote
protocol at all — it embeds Gecko as a library directly in its own application
code (the historical XULRunner architecture), so there is no separate
automation layer to announce itself.

Camoufox is a patched Firefox build built specifically to remove that tell (and
other fingerprinting surfaces — canvas, WebGL, fonts, screen/window noise)
while still exposing a standard Playwright `BrowserContext`/`Page` API, so the
rest of this module's Playwright code is unchanged. Verified directly:

    stock Playwright Firefox:  navigator.webdriver -> True
    Camoufox:                  navigator.webdriver -> False

This closes the *fingerprint* gap. It does NOT bypass IP-reputation-based
blocking — if this exact IP has recently sent a flood of automated requests to
a domain (e.g. from running the benchmark scripts repeatedly), Cloudflare can
still challenge it regardless of browser authenticity, and that requires either
waiting it out or solving the challenge once by hand via
`scripts/browser_login.py` (headed) so the resulting `cf_clearance` cookie
carries over to headless runs through the persistent profile.

This is intentionally the LAST strategy in the fallback chain: launching and
driving a browser is far slower than an HTTP request, so it should only run for
papers everything else already failed on.

Threading model: Playwright's sync API must be driven from a single thread. The
downloader runs several worker threads, so this class owns ONE dedicated
background thread that holds the browser/context, and exposes a thread-safe
`fetch_pdf()` that any worker can call; requests are serialized through a queue.
Serializing is also the safer choice here: one browser action at a time looks
far less like an attack than N parallel tabs hammering the same publisher.
"""

import logging
import queue
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_PROFILE_DIR = Path(".browser_profile")

# Publisher domains empirically found to block every HTTP-based strategy via
# Cloudflare (see docs/ZOTERO_HOW_IT_WORKS.md for the measured breakdown).
# When a paper's URL matches one of these, the downloader can skip straight to
# the browser fetcher instead of wasting time on doomed HTTP attempts.
KNOWN_BROWSER_REQUIRED_DOMAINS = (
    "sciencedirect.com",
    "onlinelibrary.wiley.com",
    "mdpi.com",
)

# Link/button text and selectors publishers commonly use for the PDF download
# action, tried in order when no citation_pdf_url meta tag is found or when
# navigating straight to it doesn't work (some sites gate the PDF behind a
# genuine click rather than a fetchable URL).
_DOWNLOAD_SELECTORS = [
    'a[href$=".pdf"]',
    'meta[name="citation_pdf_url"]',
    'a:has-text("View PDF")',
    'a:has-text("Download PDF")',
    'a:has-text("PDF")',
    'a[data-track-action="download pdf"]',
    'a[title*="PDF" i]',
]


class BrowserFetcher:
    """Drives a persistent, real Firefox instance to fetch PDFs."""

    def __init__(self, profile_dir: Path = DEFAULT_PROFILE_DIR, headless: bool = True,
                 nav_timeout_ms: int = 45000):
        self.profile_dir = Path(profile_dir)
        self.headless = headless
        self.nav_timeout_ms = nav_timeout_ms

        self._tasks: "queue.Queue" = queue.Queue()
        self._ready = threading.Event()
        self._available = False
        self._error: Optional[str] = None
        self._closed = False
        self.using_camoufox: Optional[bool] = None  # set once _run() picks an engine

        # Origins whose Cloudflare challenge we've already cleared this session.
        # This is the whole "why Zotero is fast" trick: warm up a hard publisher
        # ONCE (the homepage visit banks a cf_clearance cookie in the persistent
        # context), then every later paper on that domain loads its article
        # directly with no challenge and no per-paper warm-up dance. Only ever
        # touched from the single browser thread, so it needs no lock.
        self._warmed_origins: set = set()

        self._thread = threading.Thread(target=self._run, name="BrowserFetcher", daemon=True)
        self._thread.start()
        # A healthy launch is ~4-12s. If it doesn't signal ready in time, the
        # most common cause by far is a LOCKED PROFILE - another Camoufox/Firefox
        # process is already using `.browser_profile` (e.g. a browser_login.py
        # window left open, or leftover processes from a crashed run). A Firefox
        # profile can only be opened by one process at a time, so the launch
        # blocks. Surface that clearly instead of a silent "unavailable (None)".
        if not self._ready.wait(timeout=45) and self._error is None:
            lock = self.profile_dir / "parent.lock"
            hint = ""
            if lock.exists():
                hint = (f" The profile at {self.profile_dir} looks locked "
                        f"({lock.name} present) - close any other Camoufox/Firefox "
                        f"window using it (e.g. a browser_login.py session), or kill "
                        f"stray 'camoufox' processes, then retry.")
            self._error = f"Browser launch timed out after 45s.{hint}"

    # -- lifecycle (runs entirely inside the dedicated thread) ---------

    def _run(self):
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        camoufox_available = False
        try:
            from camoufox.sync_api import Camoufox
            camoufox_available = True
        except ImportError:
            pass

        if camoufox_available:
            # Preferred path: Camoufox patches out navigator.webdriver and other
            # automation tells that Cloudflare checks directly. Verified: stock
            # Playwright Firefox reports navigator.webdriver == True; Camoufox
            # reports False. See module docstring for why that matters here.
            try:
                with Camoufox(persistent_context=True, user_data_dir=str(self.profile_dir),
                             headless=self.headless, humanize=True,
                             accept_downloads=True) as context:
                    self.using_camoufox = True
                    self._serve(context)
                return
            except Exception as e:
                self._error = f"Camoufox failed to launch ({e}). Try: python -m camoufox fetch"
                self._ready.set()
                return

        # Fallback: stock Playwright Firefox. Still a real Gecko engine, but
        # exposes navigator.webdriver=True, so it will likely still be
        # challenged by Cloudflare-protected publishers (Elsevier, Wiley).
        # Install camoufox to fix this: pip install camoufox[geoip] && python -m camoufox fetch
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self._error = (
                "Neither camoufox nor playwright installed. Run: "
                "pip install camoufox[geoip] && python -m camoufox fetch"
            )
            self._ready.set()
            return

        try:
            with sync_playwright() as p:
                try:
                    context = p.firefox.launch_persistent_context(
                        str(self.profile_dir),
                        headless=self.headless,
                        accept_downloads=True,
                    )
                except Exception as e:
                    self._error = (
                        f"Failed to launch Firefox ({e}). "
                        f"Run: playwright install firefox"
                    )
                    self._ready.set()
                    return

                self.using_camoufox = False
                try:
                    self._serve(context)
                finally:
                    # sync_playwright()'s own `with` block does not auto-close
                    # contexts it launched (unlike Camoufox's), so this path
                    # must close it explicitly.
                    context.close()
        except Exception as e:
            self._error = str(e)
            self._ready.set()

    def _serve(self, context):
        """Mark ready and process fetch requests until close() is called.

        Runs entirely on the dedicated browser thread, for both the Camoufox
        and stock-Playwright launch paths (both hand it a real Playwright
        BrowserContext).
        """
        context.set_default_timeout(self.nav_timeout_ms)
        self._context = context
        self._available = True
        self._ready.set()

        while True:
            item = self._tasks.get()
            if item is None:
                break
            fn, args, kwargs, result_box, done = item
            try:
                result_box["value"] = fn(*args, **kwargs)
            except Exception as e:
                result_box["error"] = e
            finally:
                done.set()

        # NOTE: closing `context` is the caller's responsibility, not this
        # method's - the Camoufox `with` block auto-closes its context on
        # exit, and double-closing raises. Only the plain-Playwright fallback
        # path (whose `with sync_playwright()` does NOT auto-close contexts)
        # needs an explicit close, which it does itself after this returns.

    def is_available(self) -> bool:
        return self._available

    def close(self):
        if self._available and not self._closed:
            self._closed = True
            self._tasks.put(None)
            self._thread.join(timeout=15)

    # -- thread-safe call bridge ----------------------------------------

    def _call(self, fn, *args, timeout: float = 90, **kwargs):
        """Run `fn` on the browser thread and block for its result."""
        if not self._available:
            raise RuntimeError(self._error or "Browser fetcher not available")
        result_box = {}
        done = threading.Event()
        self._tasks.put((fn, args, kwargs, result_box, done))
        if not done.wait(timeout=timeout):
            raise TimeoutError(f"Browser task timed out after {timeout}s")
        if "error" in result_box:
            raise result_box["error"]
        return result_box.get("value")

    # -- public API -------------------------------------------------------

    def fetch_pdf(self, url: str, dest_path: Path, referer: Optional[str] = None) -> bool:
        """
        Navigate to `url` in the real browser and save a PDF to `dest_path`.

        Returns True on success. Safe to call from any thread; requests queue
        onto the single browser thread.
        """
        try:
            return self._call(self._fetch_pdf_impl, url, dest_path, referer, timeout=90)
        except Exception as e:
            logger.debug(f"Browser fetch failed for {url}: {e}")
            return False

    # -- implementation (executes on the browser thread only) -----------

    def _fetch_pdf_impl(self, url: str, dest_path: Path, referer: Optional[str]) -> bool:
        page = self._context.new_page()
        captured = {}

        def on_response(response):
            if "captured" in captured:
                return
            try:
                ct = response.headers.get("content-type", "")
            except Exception:
                return
            if "application/pdf" in ct:
                try:
                    captured["captured"] = response.body()
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            goto_kwargs = {"wait_until": "domcontentloaded", "timeout": self.nav_timeout_ms}
            if referer:
                goto_kwargs["referer"] = referer

            # Season the domain once up front (only for known-hard publishers
            # where the origin is known before navigating). After the first
            # paper, this is a no-op and the article loads directly - the same
            # reason Zotero's warm session is fast.
            self._ensure_warmed(page, url)

            resp = page.goto(url, **goto_kwargs)
            page.wait_for_timeout(1500)

            # Detect-then-remediate: if the (possibly multi-hop) redirect
            # landed on a Cloudflare challenge, warm up the session by
            # visiting the bare origin of the FINAL domain, then retry.
            # Verified live: a direct deep-link to a ScienceDirect article
            # shows an interactive CAPTCHA, but the same link passes cleanly
            # once the session has visited sciencedirect.com's homepage first
            # - direct deep-linking looks exactly like the access pattern a
            # scraping bot has; natural browsing doesn't. This can't be done
            # pre-emptively on the original `url` passed in: a resolver chain
            # like doi.org -> linkinghub.elsevier.com -> www.sciencedirect.com
            # means the domain that actually needs warming up is only known
            # after this first navigation lands.
            #
            # The redirect chain can also finish LATE and non-deterministically
            # (verified: sometimes <1s, sometimes several seconds) - a
            # DOM-query "execution context was destroyed" error partway through
            # is therefore just as strong a signal as the challenge title, and
            # is handled the same way rather than merely waited out.
            if self._looks_challenged(page):
                resp = self._remediate_and_renavigate(page, url, goto_kwargs)

            if captured.get("captured"):
                dest_path.write_bytes(captured["captured"])
                return True

            if resp is not None:
                try:
                    ct = resp.headers.get("content-type", "")
                except Exception:
                    ct = ""
                if "application/pdf" in ct:
                    dest_path.write_bytes(resp.body())
                    return True

            # Not a direct PDF response. The (possibly redirected) landing page
            # URL is the correct Referer for the PDF request that follows.
            article_url = page.url

            pdf_href = self._find_pdf_href_with_retry(page, url, goto_kwargs)
            if pdf_href:
                from urllib.parse import urljoin
                pdf_url = urljoin(article_url, pdf_href)
                # Open in a NEW page rather than reusing `page`/clicking the
                # link: Playwright's synthetic click hung indefinitely on
                # ScienceDirect's floating "View PDF" button (a fixed-position
                # element Playwright's actionability checks never consider
                # stable), while a plain navigation to the same resolved href
                # works fine and is far more robust across publishers.
                pdf_bytes = self._capture_pdf_from_url(pdf_url, referer=article_url)
                if pdf_bytes:
                    dest_path.write_bytes(pdf_bytes)
                    return True

            # Last resort: a download-shaped element with no plain `href`
            # (a JS onclick handler rather than a real link) - only a genuine
            # click can trigger this, so fall back to Playwright's download event.
            for selector in _DOWNLOAD_SELECTORS:
                if selector.startswith("meta"):
                    continue
                try:
                    locator = page.locator(selector).first
                    if locator.count() == 0 or locator.get_attribute("href"):
                        continue  # already covered by _find_pdf_href above
                    with page.expect_download(timeout=8000) as dl_info:
                        locator.click(timeout=5000)
                    dl_info.value.save_as(str(dest_path))
                    return True
                except Exception:
                    continue

            return False
        finally:
            page.close()

    # Substrings of Cloudflare (and similar) interstitial page titles. Checked
    # case-insensitively. Kept short and specific to avoid false-positiving on
    # a legitimate article whose own title happens to contain one of these
    # words in a different sense.
    _CHALLENGE_TITLE_MARKERS = ("just a moment", "security verification", "checking your browser")

    def _looks_challenged(self, page) -> bool:
        """Whether `page` is currently showing a bot-check interstitial."""
        try:
            title = (page.title() or "").lower()
        except Exception:
            # If we can't even read the title, the page is mid-navigation -
            # treat that as "still settling" rather than "challenged".
            return False
        return any(marker in title for marker in self._CHALLENGE_TITLE_MARKERS)

    @staticmethod
    def _origin_of(url: str) -> Optional[str]:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}/"

    def _warm_up_origin(self, page, url: str):
        """Visit the bare origin of `url` before the real target navigation.

        Some Cloudflare-protected publishers challenge a cold direct deep-link
        but not a session that has just browsed the site normally (verified:
        Elsevier). Best-effort - failures here must never block the real fetch.
        Records the origin as warmed so we do this at most once per session.
        """
        origin = self._origin_of(url)
        if not origin:
            return
        try:
            page.goto(origin, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(1200)
            self._warmed_origins.add(origin)
        except Exception as e:
            logger.debug(f"Warm-up navigation failed for {url}: {e}")

    def _ensure_warmed(self, page, url: str):
        """
        Proactively warm a known bot-protected origin once, before navigating
        to the article - so the FIRST paper on that domain also loads cleanly
        (no challenge -> detect -> re-navigate round-trip), and every later
        paper skips this entirely because the origin is already warmed.

        Only pays the homepage visit for domains known to challenge cold
        deep-links; everything else navigates straight to the target.
        """
        origin = self._origin_of(url)
        if not origin or origin in self._warmed_origins:
            return
        if is_browser_required_domain(url):
            logger.debug(f"Priming session for {origin} (first paper this session)")
            self._warm_up_origin(page, url)

    def _wait_for_url_to_stabilize(self, page, max_wait_ms: int = 4000, poll_ms: int = 500) -> str:
        """
        Poll `page.url` until it stops changing, and return the settled value.

        `wait_for_load_state()` only waits for a lifecycle event of whatever
        navigation is already in progress - it does NOT wait for a further
        redirect that hasn't started yet, which is exactly the situation right
        after a "context was destroyed" error (verified: a doi.org ->
        linkinghub.elsevier.com -> www.sciencedirect.com chain caught
        mid-flight kept reporting the linkinghub hop as final via
        wait_for_load_state, when sciencedirect.com - the actual
        Cloudflare-gated domain - was still one hop away). Polling the URL
        itself across a short window catches the real final destination
        regardless of how many more hops remain or how long they take.
        """
        import time
        last_url = page.url
        deadline = time.monotonic() + max_wait_ms / 1000
        while time.monotonic() < deadline:
            page.wait_for_timeout(poll_ms)
            current = page.url
            if current == last_url:
                return current
            last_url = current
        return last_url

    def _remediate_and_renavigate(self, page, url: str, goto_kwargs: dict):
        """
        Warm up the session against the page's CURRENT (final, post-redirect)
        origin, then re-navigate to `url` from scratch.

        Shared by both detection paths in `_fetch_pdf_impl`: a challenge title
        on the landing page, and a "context was destroyed" error raised later
        while querying the DOM (the redirect chain can finish late and
        non-deterministically - verified anywhere from <1s to several seconds
        - so a mid-query context-destroy is just as strong a signal as the
        title check, just caught at a different point).

        A "context was destroyed" error means a redirect was IN FLIGHT at
        query time, so `page.url` at that instant can still show a stale
        intermediate hop rather than the true final domain (verified: a
        doi.org -> linkinghub.elsevier.com -> www.sciencedirect.com chain
        caught mid-flight reported linkinghub.elsevier.com, and warming up
        THAT origin doesn't help - sciencedirect.com is the one actually
        gating access). Waiting for the navigation to finish before reading
        `page.url` ensures the origin we warm up is the one that matters.
        """
        resp = None
        for round_num in range(2):
            final_url = self._wait_for_url_to_stabilize(page)
            logger.debug(f"Challenge/mid-redirect detected at {final_url[:80]}, "
                        f"warming up origin and retrying (round {round_num + 1}/2)")
            self._warm_up_origin(page, final_url)
            resp = page.goto(url, **goto_kwargs)
            page.wait_for_timeout(1500)
            if not self._looks_challenged(page):
                break
            logger.debug(f"Still challenged after warm-up at {page.url[:80]}")
        return resp

    def _find_pdf_href_with_retry(self, page, url: str, goto_kwargs: dict,
                                  max_attempts: int = 3) -> Optional[str]:
        """
        Call `_find_pdf_href`, remediating if the page is mid-navigation.

        See `_remediate_and_renavigate` for why a "context was destroyed"
        error here triggers the same warm-up-and-retry as a challenge title,
        rather than just a short wait: a fixed wait is not reliable against a
        redirect that finishes at a non-deterministic time.
        """
        last_error = None
        for attempt in range(max_attempts):
            try:
                return self._find_pdf_href(page)
            except Exception as e:
                if "context was destroyed" not in str(e).lower():
                    raise
                last_error = e
                logger.debug(f"DOM query hit mid-navigation (attempt {attempt + 1}/{max_attempts}): {e}")
                self._remediate_and_renavigate(page, url, goto_kwargs)
        logger.debug(f"Still failing after {max_attempts} attempts: {last_error}")
        return None

    def _find_pdf_href(self, page) -> Optional[str]:
        """Find a PDF link's href: citation_pdf_url meta tag, then any
        download-shaped <a> with a plain href attribute."""
        meta = page.query_selector('meta[name="citation_pdf_url"]')
        if meta:
            content = meta.get_attribute("content")
            if content:
                return content

        for selector in _DOWNLOAD_SELECTORS:
            if selector.startswith("meta"):
                continue
            try:
                locator = page.locator(selector).first
                if locator.count() == 0:
                    continue
                href = locator.get_attribute("href")
                if href:
                    return href
            except Exception as e:
                logger.debug(f"_find_pdf_href: selector {selector!r} failed: {e}")
                continue
        return None

    def _capture_pdf_from_url(self, pdf_url: str, referer: Optional[str]) -> Optional[bytes]:
        """
        Fetch `pdf_url` in a new page and return the PDF bytes, or None.

        Uses a real page navigation (not a raw HTTP request) and captures the
        bytes via the `response` event, not a second fetch of the final URL.
        Verified necessary for Elsevier: the PDF asset is served from a
        separate CDN subdomain (pdf.sciencedirectassets.com) behind its own
        JS-executed security check. A real Camoufox page navigation passes it
        (JS-driven challenges resolve automatically), but a subsequent raw
        `APIRequestContext.get()` on the same resolved URL does NOT - it has no
        JS engine, so it gets a "Security verification" HTML page instead of
        the PDF bytes. The `response` listener sees the real bytes as they
        stream through the browser's own successful navigation.
        """
        page = self._context.new_page()
        captured = {}

        def on_response(response):
            if "bytes" in captured:
                return
            try:
                ct = response.headers.get("content-type", "")
            except Exception:
                return
            if "application/pdf" in ct:
                try:
                    captured["bytes"] = response.body()
                except Exception:
                    pass

        page.on("response", on_response)
        try:
            # "commit" returns as soon as the response starts, and we then poll
            # for the captured bytes - returning the instant the PDF arrives.
            # This replaces a "networkidle" wait, which blocks until ALL network
            # activity stops (slow, and never truly idle for a PDF viewer that
            # keeps streaming). Navigating to a raw PDF can also make goto()
            # "fail" in Playwright even while the bytes stream fine, so the goto
            # exception is deliberately swallowed - the response listener is the
            # real success signal, not goto's return.
            goto_kwargs = {"timeout": self.nav_timeout_ms, "wait_until": "commit"}
            if referer:
                goto_kwargs["referer"] = referer
            try:
                page.goto(pdf_url, **goto_kwargs)
            except Exception as e:
                logger.debug(f"goto for PDF candidate returned an error (often benign): {e}")

            for _ in range(60):  # up to ~15s, but returns as soon as bytes land
                if "bytes" in captured:
                    break
                page.wait_for_timeout(250)
        except Exception as e:
            logger.debug(f"Failed to fetch PDF candidate {pdf_url}: {e}")
        finally:
            page.close()
        return captured.get("bytes")


def is_browser_required_domain(url: Optional[str]) -> bool:
    """Whether `url` belongs to a publisher known to block every HTTP strategy."""
    if not url:
        return False
    url_lower = url.lower()
    return any(domain in url_lower for domain in KNOWN_BROWSER_REQUIRED_DOMAINS)
