"""
Tests for the real-browser (Firefox/Gecko) PDF fetcher.

These test the threading/queue bridge and the domain-routing helper without
launching a real browser (no Playwright dependency needed to run this file).
A live smoke test against real publishers is done separately, manually, since
it needs network access and an installed Firefox binary - see
docs/ZOTERO_HOW_IT_WORKS.md for those measured results.

Run: pytest tests/test_browser_fetcher.py -v
"""

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.searchers.browser_fetcher import (
    KNOWN_BROWSER_REQUIRED_DOMAINS,
    BrowserFetcher,
    is_browser_required_domain,
)


# --- domain routing -----------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://www.sciencedirect.com/science/article/pii/S0896627318300734", True),
    ("https://onlinelibrary.wiley.com/doi/10.1111/x", True),
    ("https://www.mdpi.com/2076-3417/11/11/5088", True),
    ("https://journals.plos.org/plosone/article?id=1", False),
    ("https://arxiv.org/abs/1706.03762", False),
    (None, False),
    ("", False),
])
def test_is_browser_required_domain(url, expected):
    assert is_browser_required_domain(url) is expected


def test_known_domains_are_the_ones_measured_as_bot_protected():
    """Sanity check the constant matches what's documented (Elsevier/Wiley/MDPI)."""
    assert "sciencedirect.com" in KNOWN_BROWSER_REQUIRED_DOMAINS
    assert "onlinelibrary.wiley.com" in KNOWN_BROWSER_REQUIRED_DOMAINS
    assert "mdpi.com" in KNOWN_BROWSER_REQUIRED_DOMAINS


# --- graceful degradation without playwright installed -------------------

def _block_browser_imports(monkeypatch):
    """Simulate neither camoufox nor playwright being installed."""
    import builtins
    real_import = builtins.__import__

    def blocking_import(name, *args, **kwargs):
        if name.startswith("playwright") or name.startswith("camoufox"):
            raise ImportError(f"simulated: {name} not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocking_import)


def test_unavailable_without_playwright_or_camoufox(monkeypatch, tmp_path):
    """If neither browser engine can be imported, the fetcher must report
    unavailable, not raise, so the downloader can fall back to other strategies."""
    _block_browser_imports(monkeypatch)

    bf = BrowserFetcher(profile_dir=tmp_path / "profile")
    assert bf.is_available() is False
    assert "camoufox" in (bf._error or "").lower()
    assert "playwright" in (bf._error or "").lower()
    bf.close()  # must not raise even though nothing was started


def test_fetch_pdf_returns_false_when_unavailable(monkeypatch, tmp_path):
    _block_browser_imports(monkeypatch)

    bf = BrowserFetcher(profile_dir=tmp_path / "profile")
    assert bf.fetch_pdf("https://example.com/paper", tmp_path / "out.pdf") is False


def test_falls_back_to_plain_firefox_when_camoufox_missing(monkeypatch, tmp_path):
    """Camoufox is preferred (hides navigator.webdriver); if it's not
    installed but Playwright is, we should still get a working (if more
    detectable) browser rather than failing outright."""
    import builtins
    real_import = builtins.__import__

    def blocking_import(name, *args, **kwargs):
        if name.startswith("camoufox"):
            raise ImportError("simulated: camoufox not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocking_import)

    bf = BrowserFetcher(profile_dir=tmp_path / "profile", headless=True)
    try:
        # This machine has Playwright+Firefox installed (verified earlier in
        # this session), so the fallback path should succeed and be flagged
        # as NOT using camoufox.
        assert bf.is_available() is True
        assert bf.using_camoufox is False
    finally:
        bf.close()


# --- call bridge (queue/future mechanics), without a real browser --------

class _FakeFetcher(BrowserFetcher):
    """Bypasses _run's Playwright startup so we can test the call bridge alone."""

    def __init__(self):
        # Skip BrowserFetcher.__init__ (which starts the real _run thread);
        # build just the pieces _call() depends on.
        import queue
        self._tasks = queue.Queue()
        self._ready = threading.Event()
        self._available = True
        self._error = None
        self._closed = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
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


def test_call_bridge_returns_value_from_worker_thread():
    bf = _FakeFetcher()
    try:
        result = bf._call(lambda x: x * 2, 21)
        assert result == 42
    finally:
        bf.close()


def test_call_bridge_propagates_exceptions():
    bf = _FakeFetcher()
    try:
        def boom():
            raise ValueError("kaboom")
        with pytest.raises(ValueError, match="kaboom"):
            bf._call(boom)
    finally:
        bf.close()


def test_call_bridge_is_thread_safe_from_multiple_callers():
    """Several worker threads (as in the parallel downloader) can submit
    concurrently; each gets its own correct result back."""
    bf = _FakeFetcher()
    results = {}

    def worker(n):
        results[n] = bf._call(lambda x: x + 1, n)

    try:
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert results == {i: i + 1 for i in range(10)}
    finally:
        bf.close()


def test_call_bridge_times_out():
    bf = _FakeFetcher()
    try:
        with pytest.raises(TimeoutError):
            bf._call(lambda: time.sleep(2), timeout=0.1)
    finally:
        bf.close()
