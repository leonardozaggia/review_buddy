"""
Tests for the central run-configuration loader (src/settings.py).

Run: pytest tests/test_settings.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.settings import Settings, load_settings, _deep_merge


def test_deep_merge_recurses_dicts_but_replaces_lists():
    base = {"a": {"x": 1, "y": 2}, "list": [1, 2, 3], "keep": "me"}
    override = {"a": {"y": 20, "z": 30}, "list": [9]}
    merged = _deep_merge(base, override)
    assert merged["a"] == {"x": 1, "y": 20, "z": 30}  # dict merged key-by-key
    assert merged["list"] == [9]                       # list replaced wholesale
    assert merged["keep"] == "me"                      # untouched key preserved
    # inputs not mutated
    assert base["a"]["y"] == 2


def test_example_config_loads_with_expected_shape():
    s = load_settings()
    assert set(s.search) >= {"year_from", "sources", "max_results_per_source"}
    assert isinstance(s.download["use_zotero"], bool)
    assert "epilepsy" in s.filter["keywords"]
    # the bmi false-positive keyword must stay out of the bci filter
    assert "bmi" not in s.filter["keywords"]["bci"]


def test_partial_override_keeps_untouched_defaults(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "download:\n  use_browser: true\n  max_workers: 8\nsearch:\n  year_from: 2018\n",
        encoding="utf-8",
    )
    s = load_settings(config_path=cfg)
    assert s.download["use_browser"] is True       # overridden
    assert s.download["max_workers"] == 8          # overridden
    assert s.download["use_zotero"] is True         # default preserved
    assert s.search["year_from"] == 2018            # overridden
    assert s.search["sources"] == ["scopus", "pubmed", "arxiv"]  # default list kept (scholar excluded)


def test_resolve_query_prefers_inline(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("search:\n  query: 'EEG AND attention'\n", encoding="utf-8")
    s = load_settings(config_path=cfg)
    assert s.resolve_query() == "EEG AND attention"


def test_resolve_query_falls_back_to_file(tmp_path):
    qfile = tmp_path / "myquery.txt"
    qfile.write_text("  brain AND behaviour  \n", encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"search:\n  query: null\n  query_file: {qfile}\n", encoding="utf-8")
    s = load_settings(config_path=cfg)
    assert s.resolve_query() == "brain AND behaviour"


def test_enabled_filters_returns_only_on(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "filter:\n  enabled:\n    no_abstract: true\n    bci: false\n    non_human: true\n",
        encoding="utf-8",
    )
    s = load_settings(config_path=cfg)
    # example defaults get overridden per-key; only the ones set true remain on
    enabled = s.enabled_filters()
    assert "no_abstract" in enabled and "non_human" in enabled
    assert "bci" not in enabled


def test_filter_collections_replace_not_accumulate(tmp_path):
    """Defining filters/keywords in config must REPLACE the defaults, not add
    to them - otherwise a domain-specific config still runs the template's
    filters. (Regression: neonate AI config ran 7 filters instead of 3.)"""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "filter:\n"
        "  keywords:\n"
        "    my_only_filter: [foo, bar]\n"
        "ai_filter:\n"
        "  filters:\n"
        "    my_ai_filter:\n"
        "      enabled: true\n"
        "      prompt: 'x?'\n",
        encoding="utf-8",
    )
    s = load_settings(config_path=cfg)
    assert list(s.filter["keywords"].keys()) == ["my_only_filter"]      # not epilepsy/bci/...
    assert list(s.ai_filter["filters"].keys()) == ["my_ai_filter"]      # not the 4 defaults


def test_missing_config_yaml_uses_example_defaults(tmp_path):
    """A non-existent user config must not error - example is the base."""
    s = load_settings(config_path=tmp_path / "does_not_exist.yaml")
    assert isinstance(s, Settings)
    assert s.download["max_workers"] == 4
