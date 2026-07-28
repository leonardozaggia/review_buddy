"""
Regression tests for bugs fixed during the 2026-07 review.

Each test corresponds to a specific defect; the docstring names it. These are
pure-unit tests (no network) except where noted, so they run fast in CI.

Run: pytest tests/test_bugfixes.py -v
"""

import sys
import tempfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models import Paper, normalize_title, normalize_doi
from src.paper_searcher import PaperSearcher
from src.searchers.pubmed_searcher import PubMedSearcher
from src.searchers.scopus_searcher import ScopusSearcher
from src.searchers.paper_downloader import PaperDownloader
from src.utils import load_papers_from_bib, save_papers_bib


@pytest.fixture
def downloader(tmp_path):
    return PaperDownloader(output_dir=str(tmp_path), use_zotero=False)


# --- Bug 1: cross-source deduplication -------------------------------------

def test_normalize_helpers():
    assert normalize_title("Deep Learning.") == normalize_title("deep learning")
    assert normalize_doi("https://doi.org/10.1/AB") == "10.1/ab"
    assert normalize_doi("doi:10.1/X") == "10.1/x"


def test_dedup_by_normalized_title_merges_sources():
    """Same title differing only by trailing period + source should merge."""
    s = PaperSearcher()
    p1 = Paper(title="Deep Learning"); p1.sources = {"Scopus"}
    p2 = Paper(title="Deep Learning."); p2.sources = {"PubMed"}; p2.pmid = "123"
    s._add_papers([p1]); s._add_papers([p2])
    assert len(s.papers) == 1
    kept = next(iter(s.papers.values()))
    assert {"Scopus", "PubMed"} <= kept.sources


def test_dedup_by_doi_different_titles():
    """Same DOI with different titles should still be one paper."""
    s = PaperSearcher()
    a = Paper(title="Title A"); a.doi = "10.1/x"; a.sources = {"arXiv"}
    b = Paper(title="Totally Different"); b.doi = "10.1/X"; b.sources = {"Scopus"}
    s._add_papers([a]); s._add_papers([b])
    assert len(s.papers) == 1


# --- Bug 2: PubMed structured abstracts ------------------------------------

def test_pubmed_structured_abstract_full():
    xml = """<PubmedArticle><MedlineCitation><PMID>1</PMID><Article>
    <ArticleTitle>Structured Test</ArticleTitle>
    <Abstract>
    <AbstractText Label="BACKGROUND">We studied <i>things</i>.</AbstractText>
    <AbstractText Label="METHODS">We recruited 40 patients.</AbstractText>
    <AbstractText Label="RESULTS">Effect was large.</AbstractText>
    <AbstractText Label="CONCLUSIONS">It works.</AbstractText>
    </Abstract></Article></MedlineCitation></PubmedArticle>"""
    s = PubMedSearcher(email="x@y.com")
    p = s._parse_article(ET.fromstring(xml))
    assert "BACKGROUND:" in p.abstract and "CONCLUSIONS:" in p.abstract
    assert "recruited 40 patients" in p.abstract
    assert "things" in p.abstract  # inline markup not truncated


# --- Bug 3: bibtexparser round-trip ----------------------------------------

def test_bibtex_load_preserves_all_fields():
    bib = """@article{Smith_2021,
      title = {A Study of Things},
      author = {Jane Smith and Bob Jones},
      journal = {Journal of Tests},
      year = {2021},
      volume = {12}, number = {3}, pages = {45--67},
      publisher = {Elsevier}, issn = {1234-5678}, doi = {10.1/abc},
      abstract = {Contact author@example.com with n=40 participants.},
    }"""
    d = Path(tempfile.mkdtemp())
    f = d / "in.bib"; f.write_text(bib, encoding="utf-8")
    papers = load_papers_from_bib(f)
    assert len(papers) == 1
    p = papers[0]
    assert (p.volume, p.issue, p.pages) == ("12", "3", "45--67")
    assert p.publisher == "Elsevier" and p.issn == "1234-5678"
    assert "author@example.com" in p.abstract  # '@' in abstract not mangled
    assert p.cite_key == "Smith_2021"


def test_bibtex_save_preserves_cite_key():
    d = Path(tempfile.mkdtemp())
    p = Paper(title="X"); p.cite_key = "Smith_2021"
    p.publication_date = date(2021, 1, 1); p.authors = ["Jane Smith"]
    out = d / "out.bib"; save_papers_bib([p], out)
    assert "@article{Smith_2021," in out.read_text(encoding="utf-8")


# --- Bug 4: filename collisions --------------------------------------------

def test_safe_filename_no_collision(downloader):
    a = downloader._safe_filename("A" * 100 + " first paper")
    b = downloader._safe_filename("A" * 100 + " second paper")
    assert a != b
    assert downloader._safe_filename("A" * 100 + " first paper") == a  # idempotent
    assert all(c.isalnum() or c == "_" for c in a)


# --- Bug 5: PMC never returns an HTML-directory URL ------------------------

def test_pmc_never_returns_directory_url(downloader, monkeypatch):
    """The old code returned /pmc/articles/PMCxxx/pdf/ which serves HTML."""
    import src.searchers.paper_downloader as pdmod

    class FakeResp:
        status_code = 200
        content = b'<OA><records></records></OA>'
        def json(self):
            return {"records": [{"pmcid": "PMC123"}]}

    monkeypatch.setattr(pdmod.__dict__.get("requests", None) or __import__("requests"),
                        "get", lambda *a, **k: FakeResp())
    # With no OA pdf link and stubbed network, must not return the bad dir URL
    result = downloader._get_pmc_pdf("999")
    assert result is None or not result.rstrip("/").endswith("/pdf")


# --- Bug 6: arXiv id handling ----------------------------------------------

@pytest.mark.parametrize("entry,expected", [
    ({"arxiv_id": "2101.00001"}, "https://arxiv.org/pdf/2101.00001"),
    ({"arxiv_id": "2101.00001v3"}, "https://arxiv.org/pdf/2101.00001"),
    ({"url": "https://arxiv.org/abs/math/0211159"}, "https://arxiv.org/pdf/math/0211159"),
    ({"url": "https://arxiv.org/abs/cond-mat/0211159v2"}, "https://arxiv.org/pdf/cond-mat/0211159"),
    ({"doi": "10.48550/arXiv.2312.00752"}, "https://arxiv.org/pdf/2312.00752"),
])
def test_arxiv_id_variants(downloader, entry, expected):
    assert downloader._get_arxiv_pdf(entry) == expected


# --- Bug 7: Scopus full author list ----------------------------------------

def test_scopus_full_author_array():
    s = ScopusSearcher(api_key="dummy", fetch_abstracts=False)
    entry = {"dc:title": "X", "dc:creator": "Kenzhaliyev B.K.", "author": [
        {"given-name": "Bagdaulet", "surname": "Kenzhaliyev"},
        {"authname": "Smith J."},
        {"given-name": "Jane", "surname": "Doe"},
    ]}
    p = s._parse_entry(entry)
    assert p.authors == ["Bagdaulet Kenzhaliyev", "Smith J.", "Jane Doe"]


def test_scopus_author_fallback_to_creator():
    s = ScopusSearcher(api_key="dummy", fetch_abstracts=False)
    p = s._parse_entry({"dc:title": "Y", "dc:creator": "Solo A."})
    assert p.authors == ["Solo A."]


# --- Bug 8: dedup index safety ---------------------------------------------

def test_csv_dedup_keeps_pubmed_row():
    import importlib.util
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("dedup", root / "04_deduplicate_extra.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

    d = Path(tempfile.mkdtemp()); f = d / "papers.csv"
    pd.DataFrame([
        {"Title": "Paper A", "DOI": "10.1/a", "Year": 2020, "Sources": "Scopus"},
        {"Title": "Paper B", "DOI": "10.1/b", "Year": 2019, "Sources": "arXiv"},
        {"Title": "Paper A dup", "DOI": "10.1/a", "Year": 2021, "Sources": "PubMed"},
    ]).to_csv(f, index=False)
    stats = m.deduplicate_csv(f)
    out = pd.read_csv(f)
    assert stats["duplicates"] == 1 and len(out) == 2
    assert out[out["DOI"] == "10.1/a"].iloc[0]["Sources"] == "PubMed"


# --- Bug 9: 'bmi' keyword removed ------------------------------------------

def test_bmi_not_in_bci_filter():
    root = Path(__file__).resolve().parent.parent
    src = (root / "02_abstract_filter.py").read_text(encoding="utf-8")
    ns = {}
    exec(compile(src[: src.index("# Configure logging")], "02_abstract_filter.py", "exec"), ns)
    assert "bmi" not in ns["KEYWORD_FILTERS"]["bci"]
