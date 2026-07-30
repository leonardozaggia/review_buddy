"""
Tests for query construction and credential handling across the searchers.

These cover failure modes that are silent in production — a query that returns
the wrong number of papers, or a credential that makes an API reject every
request — so a regression here would not raise, it would just quietly change
results.

Run: pytest tests/test_query_building.py -v
"""

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config, is_placeholder
from src.paper_searcher import scopus_only_constructs
from src.searchers.pubmed_searcher import PubMedSearcher
from src.searchers.scopus_searcher import ScopusSearcher, _wrapped_in_parens


# --------------------------------------------------------------------------
# .env placeholders
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "your_pubmed_api_key_here",
    "your_scopus_api_key_here",
    "your.email@example.com",
    "<your-key>",
    "changeme",
])
def test_placeholder_values_are_detected(value):
    assert is_placeholder(value) is True


@pytest.mark.parametrize("value", [
    "a1b2c3d4e5f67890",
    "leozaggia@gmail.com",
    "7f3c9d2e",
    "yourkey123",          # 'your' without a separator is not the template form
])
def test_real_credentials_are_not_flagged(value):
    assert is_placeholder(value) is False


def test_placeholder_key_is_discarded_not_forwarded(monkeypatch):
    """A bogus key makes NCBI reject every request, so it must not survive."""
    monkeypatch.setenv("SCOPUS_API_KEY", "real123")
    monkeypatch.setenv("PUBMED_EMAIL", "me@uni.edu")
    monkeypatch.setenv("PUBMED_API_KEY", "your_pubmed_api_key_here")

    config = Config()

    assert config.pubmed_api_key is None
    assert config.scopus_api_key == "real123"
    # The email still gates the source, so PubMed remains available
    assert config.has_pubmed_access() is True


# --------------------------------------------------------------------------
# Scopus field scoping
# --------------------------------------------------------------------------

@pytest.mark.parametrize("query,expected", [
    ("(A OR B)", True),
    ("((A) AND (B))", True),
    ('("x (y)" OR z)', True),      # parens inside quotes don't count
    ("(A) AND (B)", False),        # two groups, not one wrapper
    ("(A) AND (B) AND (C)", False),
    ("A AND B", False),
    ("(A", False),
    ("(A))", False),
])
def test_wrapped_in_parens(query, expected):
    assert _wrapped_in_parens(query) is expected


def test_and_groups_stay_inside_the_field_restriction():
    """
    Regression: stripping "(A) AND (B)" to "TITLE-ABS-KEY(A) AND (B)" let B
    match every Scopus field including references, inflating real result sets
    by 10-21x.
    """
    searcher = ScopusSearcher.__new__(ScopusSearcher)
    built = ScopusSearcher._build_query(searcher, "(A) AND (B) AND (C)")
    assert built == "TITLE-ABS-KEY((A) AND (B) AND (C))"


def test_redundant_outer_parens_are_still_dropped():
    searcher = ScopusSearcher.__new__(ScopusSearcher)
    assert ScopusSearcher._build_query(searcher, "(A OR B)") == "TITLE-ABS-KEY(A OR B)"


def test_existing_field_codes_are_left_alone():
    searcher = ScopusSearcher.__new__(ScopusSearcher)
    assert ScopusSearcher._build_query(searcher, "TITLE-ABS-KEY(x)") == "TITLE-ABS-KEY(x)"


def test_standalone_not_becomes_and_not():
    searcher = ScopusSearcher.__new__(ScopusSearcher)
    assert ScopusSearcher._build_query(searcher, "(A) NOT (B)") == "TITLE-ABS-KEY((A) AND NOT (B))"


# --------------------------------------------------------------------------
# Scopus year slicing (the 5000-record per-query ceiling)
# --------------------------------------------------------------------------

def _searcher():
    s = ScopusSearcher.__new__(ScopusSearcher)
    s.MAX_RETRIEVABLE = 5000
    return s


def test_under_the_ceiling_runs_as_one_query():
    assert ScopusSearcher._plan_windows(_searcher(), 4000, 2020, None) == [(2020, None)]


def test_over_the_ceiling_splits_by_year():
    windows = ScopusSearcher._plan_windows(_searcher(), 5751, 2020, 2022)
    assert windows == [(2020, 2020), (2021, 2021), (2022, 2022)]


def test_open_ended_search_keeps_an_open_final_window():
    """Scopus carries in-press records dated beyond the current year."""
    windows = ScopusSearcher._plan_windows(_searcher(), 5751, 2020, None)
    assert windows[-1][1] is None


def test_year_windows_are_disjoint():
    a = ScopusSearcher._year_clause(2020, 2020)
    b = ScopusSearcher._year_clause(2021, 2021)
    assert a == " AND PUBYEAR > 2019 AND PUBYEAR < 2021"
    assert b == " AND PUBYEAR > 2020 AND PUBYEAR < 2022"


def test_cannot_slice_without_a_start_year():
    assert ScopusSearcher._plan_windows(_searcher(), 9000, None, None) == [(None, None)]


def test_cannot_slice_a_single_year_further():
    assert ScopusSearcher._plan_windows(_searcher(), 6000, 2024, 2024) == [(2024, 2024)]


# --------------------------------------------------------------------------
# PubMed: retmax clamp, and a failed request vs a genuinely empty one
# --------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _pubmed_returning(payload, captured=None):
    searcher = PubMedSearcher(email="x@y.z", max_results=999999)

    def get(url, params=None, timeout=None):
        if captured is not None:
            captured.update(params)
        return _FakeResponse(payload)

    searcher.session = types.SimpleNamespace(get=get)
    return searcher


def test_retmax_is_clamped_to_what_ncbi_will_serve():
    sent = {}
    searcher = _pubmed_returning({"esearchresult": {"count": "5", "idlist": ["1"] * 5}}, sent)
    searcher._search_pmids("q")
    assert sent["retmax"] == PubMedSearcher.MAX_RETMAX == 9999


def test_api_error_is_distinguishable_from_no_results():
    searcher = _pubmed_returning({"esearchresult": {"ERROR": "bad db"}})
    assert searcher._search_pmids("q") is None


def test_genuine_zero_returns_empty_list():
    searcher = _pubmed_returning({"esearchresult": {"count": "0", "idlist": []}})
    assert searcher._search_pmids("q") == []


# --------------------------------------------------------------------------
# Cross-source syntax portability
# --------------------------------------------------------------------------

def test_scopus_only_syntax_is_flagged():
    assert scopus_only_constructs("TITLE-ABS-KEY(x)") == ["TITLE-ABS-KEY(...)"]
    assert "proximity operator (W/n or PRE/n)" in scopus_only_constructs('"a" W/5 b')


def test_portable_boolean_query_is_clean():
    assert scopus_only_constructs('("a" OR "b") AND (c OR d)') == []
    assert scopus_only_constructs("Electroencephalogra* AND Behavio*") == []


def test_short_wildcard_is_flagged_for_pubmed():
    # PubMed ignores truncation with fewer than 4 leading characters
    assert len(scopus_only_constructs("Response tim*")) == 1
