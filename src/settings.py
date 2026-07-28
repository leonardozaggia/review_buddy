"""
Central run-configuration loader.

All tunable options for the pipeline scripts (01/02/03) live in ONE place:
`config.yaml` at the project root. That file is gitignored, so your query,
filters, and toggles never clutter git history - unlike editing constants
inside the tracked scripts.

Precedence (later wins):
    1. config.example.yaml   (tracked template = documented defaults)
    2. config.yaml           (your gitignored overrides; may be partial)

Because `config.example.yaml` is always loaded as the base, `config.yaml` only
needs to contain the keys you actually want to change.

API keys / emails do NOT belong here - those stay in `.env` (see src/config.py).
"""

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
_EXAMPLE = _ROOT / "config.example.yaml"
_CONFIG = _ROOT / "config.yaml"

# Last-resort defaults, used only if config.example.yaml is missing (it is
# tracked, so this is a safety net, not the primary source of defaults).
_FALLBACK_DEFAULTS: Dict[str, Any] = {
    "search": {
        "query": None,
        "query_file": "query.txt",
        "year_from": 2020,
        "year_to": None,
        "max_results_per_source": 10,
        "sources": ["scopus", "pubmed", "arxiv"],
        "pubmed_field": "tiab",
        "output_dir": "results",
    },
    "filter": {"enabled": {}, "keywords": {}},
    "ai_filter": {
        "model": "gemma3:4b",
        "ollama_url": "http://localhost:11434",
        "confidence_threshold": 0.5,
        "temperature": 0.1,
        "structured_output": True,
        "retry_attempts": 3,
        "cache_responses": True,
        "filters": {},
    },
    "download": {
        "bib_file": None,
        "output_dir": "results/pdfs",
        "max_workers": 4,
        "use_zotero": True,
        "use_scihub": False,
        "use_browser": False,
    },
}


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# Nested dicts that are "collections of named items" - when the user provides
# one, they mean it to REPLACE the defaults wholesale, not accumulate on top of
# them. Without this, defining 3 AI filters in config.yaml would run those 3
# PLUS the 4 default filters (their keys merge in). Dotted paths from the root.
_REPLACE_WHOLESALE_PATHS = (
    "filter.enabled",
    "filter.keywords",
    "ai_filter.filters",
)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any], _path: str = "") -> Dict[str, Any]:
    """Recursively merge `override` into `base`, returning a new dict.

    Dicts merge key-by-key; lists and other scalars replace wholesale (so
    setting `search.sources` replaces the default list). The specific
    collection paths in `_REPLACE_WHOLESALE_PATHS` also replace wholesale even
    though they are dicts - see the constant's docstring.
    """
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        cur_path = f"{_path}.{key}".lstrip(".")
        if (isinstance(value, dict) and isinstance(result.get(key), dict)
                and cur_path not in _REPLACE_WHOLESALE_PATHS):
            result[key] = _deep_merge(result[key], value, cur_path)
        else:
            result[key] = copy.deepcopy(value)
    return result


class Settings:
    """Thin wrapper over the merged config dict with a couple of helpers."""

    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    @property
    def search(self) -> Dict[str, Any]:
        return self._data.get("search", {})

    @property
    def filter(self) -> Dict[str, Any]:
        return self._data.get("filter", {})

    @property
    def ai_filter(self) -> Dict[str, Any]:
        return self._data.get("ai_filter", {})

    @property
    def download(self) -> Dict[str, Any]:
        return self._data.get("download", {})

    def resolve_query(self) -> str:
        """
        Return the search query: the inline `search.query` if set, otherwise
        the contents of `search.query_file` (default query.txt).
        """
        s = self.search
        query = s.get("query")
        if query and str(query).strip():
            return str(query).strip()
        query_file = s.get("query_file") or "query.txt"
        path = Path(query_file)
        if not path.is_absolute():
            path = _ROOT / path
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        raise FileNotFoundError(
            f"No query configured: set `search.query` in config.yaml or create {query_file}"
        )

    def enabled_filters(self) -> List[str]:
        """Names of the filters toggled on, in config order."""
        return [name for name, on in (self.filter.get("enabled") or {}).items() if on]


def load_settings(config_path: Optional[Path] = None) -> Settings:
    """
    Load merged settings.

    Args:
        config_path: optional explicit path to a user config file, overriding
                     the default `config.yaml` lookup (useful for tests).

    Precedence for the user-override file: explicit `config_path` arg, else the
    `REVIEW_BUDDY_CONFIG` env var (set by main.py --config so subprocess steps
    inherit it), else `config.yaml`.
    """
    import os
    base = _read_yaml(_EXAMPLE) or copy.deepcopy(_FALLBACK_DEFAULTS)
    if config_path:
        user_path = Path(config_path)
    elif os.getenv("REVIEW_BUDDY_CONFIG"):
        user_path = Path(os.environ["REVIEW_BUDDY_CONFIG"])
    else:
        user_path = _CONFIG
    override = _read_yaml(user_path)
    merged = _deep_merge(base, override)
    return Settings(merged)
