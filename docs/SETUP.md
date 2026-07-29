# Setup

Everything you need to install once, plus the optional services. The 60-second
version is in the [README](../README.md); this page is the full detail.

## Requirements

- Python 3.7+
- `pip install -r requirements.txt`

`requirements.txt` marks which dependencies are optional and what each one
buys you. The ones worth knowing about:

| Package | Needed for |
|---|---|
| `curl_cffi` | TLS impersonation. Strongly recommended — many publishers, *including open-access ones* (MDPI, PLOS, PMC), return 403 to a plain `requests` client purely on TLS fingerprint. |
| `langdetect` | The non-English keyword filter |
| `matplotlib` | `scripts/benchmark_downloaders.py` chart rendering |
| `camoufox[geoip]`, `playwright` | The real-browser PDF fetcher (see below) |
| `scholarly` | Google Scholar search (unreliable — see limitations) |
| `scihub` | Sci-Hub fallback, off by default |

Recommended environment: the `autosearch` conda env. If you launch `main.py`
from a different env that is missing dependencies, it tries to re-exec itself
under `autosearch` automatically.

## API keys

At least one is required. Keys and emails live in `.env` — **not** in
`config.yaml`, which is for run settings.

```bash
cp .env.example .env
```

| Source | Key | Where |
|---|---|---|
| Scopus | `SCOPUS_API_KEY` | [Elsevier Developer Portal](https://dev.elsevier.com/) |
| PubMed | `PUBMED_EMAIL` | Any valid email — free, no registration |
| PubMed (rate limits) | `PUBMED_API_KEY` | [NCBI account](https://www.ncbi.nlm.nih.gov/account/) — optional |
| IEEE Xplore | `IEEE_API_KEY` | [IEEE Developer Portal](https://developer.ieee.org/) — optional |
| Unpaywall | `UNPAYWALL_EMAIL` | Any valid email; falls back to `PUBMED_EMAIL` |

**arXiv and Google Scholar need no keys.**

## Run configuration

```bash
cp config.example.yaml config.yaml    # then edit config.yaml
```

`config.yaml` is gitignored and only needs the keys you want to change.
See [CONFIGURATION.md](CONFIGURATION.md) for the full reference.

## Ollama (for the LLM abstract filter)

```bash
# 1. Install Ollama: https://ollama.ai
# 2. Pull a model (one-time)
ollama pull gemma3:4b
# 3. Start the server (separate terminal)
ollama serve
```

`python main.py --ai` starts Ollama and pulls the configured model for you, so
steps 2 and 3 are only needed if you run `02_abstract_filter_ai.py` directly.

Model choice, timing and prompt-writing advice: [CONFIGURATION.md](CONFIGURATION.md).

### HPC / cluster

`run_filter_hpc.sh` is a ready-made SLURM job script that starts the Ollama
server, runs the AI filter, and stops the server cleanly. Large models want a
GPU node; `gemma3:4b` runs comfortably on a 6 GB laptop GPU.

## Zotero translation server (optional, improves PDF hit rate)

The translation server adds site-specific PDF-link extraction to the resolver
chain. It is vendored as a git submodule.

```bash
python scripts/setup_zotero.py                        # init submodule, npm install, apply patch
cd vendor/translation-server && node src/server.js    # start it (port 1969), leave running
```

> The setup script applies a required patch
> (`vendor/patches/expose-attachments.patch`). Upstream translation-server strips
> PDF links from its `/web` response; the patch re-exposes them. This makes the
> submodule show as "modified" in git — that is expected.

If the server is not running, the downloader logs a notice and **silently falls
back** to the built-in strategies, so this is entirely optional. Change the URL
with `ZOTERO_TRANSLATION_SERVER` in `.env`.

Note that Zotero's own open-access index (`services.zotero.org/oa/search`) needs
**no local server at all** and already finds copies plain Unpaywall misses — so
`use_zotero: true` helps even if you never start the server. See
[ZOTERO_HOW_IT_WORKS.md](ZOTERO_HOW_IT_WORKS.md).

## Real-browser fetcher (optional, for Cloudflare publishers)

For publishers that block every HTTP client regardless of TLS fingerprint
(Elsevier/ScienceDirect, Wiley, MDPI), `download.use_browser: true` drives
[Camoufox](https://github.com/daijro/camoufox) — a patched, anti-detect Firefox —
as a last-resort strategy.

```bash
pip install camoufox[geoip] playwright
python -m camoufox fetch          # downloads the patched Firefox build
python scripts/browser_login.py   # one-time: solve any CAPTCHA yourself, headed
```

A plain real browser is *not* enough on its own: `navigator.webdriver` gives away
any WebDriver-based automation regardless of engine, and Camoufox is what patches
that out. The full investigation — including the IP-reputation caveat you want to
know about before benchmarking at scale — is in
[ZOTERO_HOW_IT_WORKS.md](ZOTERO_HOW_IT_WORKS.md).

## Troubleshooting

**No papers found**
- Check the API keys in `.env`
- Verify the query actually runs on one source at a time (`search.sources`)
- Try a simpler query; see [QUERY_SYNTAX.md](QUERY_SYNTAX.md)

**Downloads failing**
- Set `UNPAYWALL_EMAIL` in `.env`
- Read `results/pdfs/download.log` — it records every attempt and why it failed
- Turn on `download.use_browser` for Cloudflare-protected publishers
- Institutional access is IP-based: run from campus or VPN

**Import errors**
- Run scripts from the repository root: `python 01_fetch_metadata.py`

**LLM filter is slow or returns nothing**
- Check `ollama serve` is up and the model is pulled
- Drop `ai_filter.max_workers` to 1 to debug
- Avoid reasoning models such as `qwen3` — their thinking cannot be disabled
  reliably and they take ~90 s per paper

## Project structure

```
review_buddy/
├── main.py                      # runs all three steps from config.yaml
├── 01_fetch_metadata.py         # search + dedup + export
├── 02_abstract_filter.py        # keyword filtering
├── 02_abstract_filter_ai.py     # LLM filtering
├── 03_download_papers.py        # PDF retrieval
├── 04_deduplicate_extra.py      # standalone dedup for merged files
├── config.example.yaml          # run-configuration template
├── .env.example                 # API key template
├── src/
│   ├── settings.py             # config.yaml loader
│   ├── config.py               # config management
│   ├── models.py               # Paper data model
│   ├── paper_searcher.py       # search coordinator
│   ├── abstract_filter.py      # keyword filtering logic
│   ├── ai_abstract_filter.py   # AI filtering logic
│   ├── llm_client.py           # Ollama client
│   └── searchers/
│       ├── scopus_searcher.py
│       ├── pubmed_searcher.py
│       ├── arxiv_searcher.py
│       ├── scholar_searcher.py
│       ├── ieee_searcher.py
│       ├── zotero_client.py    # Zotero resolver chain
│       ├── http_client.py      # dual transport (requests + curl_cffi)
│       ├── browser_fetcher.py  # Camoufox fetcher
│       └── paper_downloader.py # strategy chain
├── docs/                        # this documentation
├── scripts/                     # benchmarks and utilities
├── vendor/translation-server/   # Zotero translation server (submodule)
└── results/                     # output (auto-created, gitignored)
    ├── papers.csv
    ├── papers_filtered.csv          # after keyword filtering
    ├── papers_filtered_ai.csv       # after AI filtering
    ├── manual_review_ai.csv         # low-confidence papers to check by hand
    ├── references.bib / .ris
    ├── references_filtered.bib
    ├── references_filtered_ai.bib
    ├── filtered_out/                # what each keyword filter removed, one CSV per filter
    ├── filtered_out_ai/             # same, for the LLM filter
    ├── ai_cache/                    # cached LLM responses
    ├── ai_filtering_log_*.json      # per-paper decisions, confidence, reasoning
    └── pdfs/
```
