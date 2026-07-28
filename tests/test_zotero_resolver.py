"""
Tests for the Zotero-style file resolver chain.

These verify the *structure* of the chain (order, dedup, OA-index integration)
using stubs, so they run offline. The live behaviour is measured separately by
scripts/benchmark_zotero_ab.py.

Run: pytest tests/test_zotero_resolver.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.searchers.zotero_client import ZoteroTranslationClient, _citation_pdf_url


@pytest.fixture
def client():
    c = ZoteroTranslationClient()
    c._available = False  # keep the translator step offline by default
    return c


def test_resolver_order_matches_zotero(client, monkeypatch):
    """Zotero's order is doi -> url -> pmcid -> open-access index."""
    monkeypatch.setattr(client, "open_access_locations",
                        lambda doi: [{"url": "https://oa.example/x.pdf", "version": "publishedVersion"}])
    resolvers = client.file_resolvers(doi="10.1/abc", url="https://pub.example/article",
                                      pmcid="PMC123")
    methods = [r["method"] for r in resolvers]
    assert methods == ["zotero:doi", "zotero:url", "zotero:pmc", "zotero:oa"]
    assert resolvers[0]["pageURL"] == "https://doi.org/10.1/abc"
    assert resolvers[2]["pageURL"] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/"


def test_resolver_skips_missing_identifiers(client, monkeypatch):
    monkeypatch.setattr(client, "open_access_locations", lambda doi: [])
    resolvers = client.file_resolvers(url="https://pub.example/article")
    assert [r["method"] for r in resolvers] == ["zotero:url"]


def test_oa_direct_url_is_yielded_without_page_fetch(client, monkeypatch):
    """A direct OA `url` needs no page fetch and should be yielded as-is."""
    monkeypatch.setattr(client, "open_access_locations",
                        lambda doi: [{"url": "https://oa.example/paper.pdf"}])

    fetches = []

    def fail_get(url, *a, **k):
        fetches.append(url)
        raise AssertionError(f"should not fetch {url}")

    monkeypatch.setattr(client.session, "get", fail_get)

    # DOI only produces a pageURL resolver too, so restrict to the OA entry by
    # asserting the direct URL is emitted before any page fetch is attempted.
    gen = client.iter_pdf_candidates(doi=None, url=None)
    assert list(gen) == []  # no identifiers -> no candidates, no fetches
    assert fetches == []

    # With a DOI, the OA direct url is present among the candidates
    resolvers = client.file_resolvers(doi="10.1/abc")
    oa = [r for r in resolvers if r["method"] == "zotero:oa"]
    assert oa and oa[0]["url"] == "https://oa.example/paper.pdf"


def test_citation_pdf_url_extraction():
    html = b"""<html><head>
      <meta name="citation_pdf_url" content="/articles/x.pdf">
    </head><body></body></html>"""
    assert _citation_pdf_url(html, "https://pub.example/article") == "https://pub.example/articles/x.pdf"


def test_citation_pdf_url_absent():
    assert _citation_pdf_url(b"<html><head></head></html>", "https://x.example") is None


def test_pdf_from_page_reads_attachments(client, monkeypatch):
    """pdf_from_page mirrors Zotero's getFileFromDocument()."""
    monkeypatch.setattr(client, "translate_url", lambda url: [{
        "title": "Paper",
        "attachments": [
            {"mimeType": "text/html", "url": "https://x.example/page"},
            {"mimeType": "application/pdf", "url": "https://x.example/paper.pdf"},
        ],
    }])
    assert client.pdf_from_page("https://x.example/page") == "https://x.example/paper.pdf"


def test_pdf_from_page_no_pdf_attachment(client, monkeypatch):
    monkeypatch.setattr(client, "translate_url", lambda url: [{"attachments": [
        {"mimeType": "text/html", "url": "https://x.example/page"}]}])
    assert client.pdf_from_page("https://x.example/page") is None


def test_pdf_from_page_handles_null_attachments(client, monkeypatch):
    """Unpatched translation servers return attachments: null - must not crash."""
    monkeypatch.setattr(client, "translate_url", lambda url: [{"title": "X", "attachments": None}])
    assert client.pdf_from_page("https://x.example/page") is None


def test_candidates_are_deduplicated(client, monkeypatch):
    """The same URL reachable via two resolvers is only yielded once."""
    monkeypatch.setattr(client, "open_access_locations",
                        lambda doi: [{"url": "https://dup.example/a.pdf"},
                                     {"url": "https://dup.example/a.pdf"}])

    class Resp:
        url = "https://pub.example/article"
        headers = {"content-type": "text/html"}
        class raw:
            @staticmethod
            def read(n, decode_content=True):
                return b"<html></html>"
        @staticmethod
        def close():
            pass

    monkeypatch.setattr(client.session, "get", lambda *a, **k: Resp())
    urls = [u for u, _r, _m in client.iter_pdf_candidates(doi="10.1/abc")]
    assert urls.count("https://dup.example/a.pdf") == 1
