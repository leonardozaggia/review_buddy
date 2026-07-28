"""
Test that the browser fetcher is aimed at the right URL.

Regression test for a bug found in a real run: Scopus/PubMed hand us a database
*record* URL (scopus.com/inward/record.uri, pubmed.ncbi.nlm.nih.gov/<pmid>/),
which is login-walled and has no PDF. The browser must follow the DOI
(https://doi.org/<DOI> -> real publisher) instead. Before the fix, 22 of 23
failures were subscription papers whose only URL was a scopus.com record page.

Run: pytest tests/test_browser_target.py -v
"""

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.searchers.paper_downloader import PaperDownloader


@pytest.fixture
def downloader():
    d = PaperDownloader(output_dir=tempfile.mkdtemp(), use_zotero=False, use_browser=False)
    yield d
    d.close()


@pytest.mark.parametrize("doi,url,expected", [
    # Scopus record page + DOI -> follow the DOI
    ("10.1016/j.cognition.2026.106618",
     "https://www.scopus.com/inward/record.uri?partnerID=x&doi=10.1016%2f...",
     "https://doi.org/10.1016/j.cognition.2026.106618"),
    # PubMed abstract page + DOI -> follow the DOI
    ("10.3390/s26113349", "https://pubmed.ncbi.nlm.nih.gov/40000000/",
     "https://doi.org/10.3390/s26113349"),
    # A real publisher URL -> keep it (don't bounce through doi.org)
    ("10.1016/x", "https://www.sciencedirect.com/science/article/pii/S123",
     "https://www.sciencedirect.com/science/article/pii/S123"),
    # No DOI -> fall back to whatever URL we have
    (None, "https://www.mdpi.com/2076-3417/11/11/5088",
     "https://www.mdpi.com/2076-3417/11/11/5088"),
    # DOI but no URL -> DOI resolver
    ("10.1/abc", None, "https://doi.org/10.1/abc"),
])
def test_browser_target_prefers_doi_over_aggregator(downloader, doi, url, expected):
    assert downloader._browser_target(doi, url) == expected


def test_aggregator_hosts_cover_the_common_databases(downloader):
    hosts = downloader._AGGREGATOR_HOSTS
    assert "scopus.com" in hosts
    assert "pubmed.ncbi.nlm.nih.gov" in hosts
