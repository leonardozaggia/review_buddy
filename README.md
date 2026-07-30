# Review Buddy

Systematic-review legwork, end to end: search the databases, screen every
abstract with a local LLM, and actually retrieve the PDFs.

The last part is where most tools give up. This one treats it as the main event.

A real run on this repo: **5,498 unique papers** pulled from Scopus and PubMed,
**5,295 abstracts screened** by a model running on a 6 GB laptop GPU, PDFs
fetched in parallel — overnight, on one machine, without sending a single
abstract to a third party.

## What it does

- **Search.** One boolean query across Scopus, PubMed, arXiv, IEEE Xplore and
  Google Scholar. Results are deduplicated and merged across sources into
  `papers.csv`, `references.bib` and `references.ris`.
- **Screen.** Your inclusion criteria, written as plain-English yes/no questions,
  applied to every abstract by a local Ollama model. Nothing leaves the machine.
  Every decision is logged with a confidence score and the model's reasoning, and
  low-confidence calls are flagged for a human instead of being silently dropped.
- **Download.** A resolver chain modelled on what Zotero actually does, backed by
  a real-browser fallback for publishers that block HTTP clients on sight.

## The numbers

Every figure below is produced by a script in this repository, on real corpora.

### Screening quality and speed

`scripts/benchmark_ollama_models.py` scores candidate models against 48
hand-labelled papers drawn from a real corpus, on the repo's actual filter
prompts:

| Model | Agreement with hand labels |
|---|---|
| `gpt-oss:20b` | **0.971** |
| `gemma3:12b` | 0.935 |
| `gemma3:4b` | 0.906 |

Throughput on the full 5,295-paper run: **3.7 s per paper** with `gemma3:4b` on
a 6 GB-VRAM laptop GPU at 4 concurrent requests — about **5.4 hours** for the
whole corpus, unattended. Responses are cached, so an interrupted run resumes
cheaply and re-runs are near-instant.

Iterate on filter wording with `gemma3:4b`; do the final pass with `gpt-oss:20b`
if the accuracy is worth the wall time.

### PDF retrieval

`scripts/benchmark_zotero_ab.py`, 123 real DOIs, run twice over the same set on
a university network:

| Configuration | PDFs retrieved |
|---|---|
| Built-in fallback chain | 41/123 (33%) |
| **+ Zotero resolver chain** | **48/123 (39%)** |

That headline hides the interesting part — the per-publisher breakdown:

| Publisher | Retrieved |
|---|---|
| Springer | 8/8 |
| Frontiers | 11/12 |
| PLOS | 3/3 |
| **Elsevier** | **4/49** |

Elsevier alone accounts for 45 of the 75 failures, and it is not a resolver
problem: it is Cloudflare bot-blocking on subscription content.

So the next step was a real browser. With the Camoufox fetcher enabled, a
follow-up on 12 fresh DOIs across Elsevier, Wiley, MDPI and Frontiers retrieved
**8/12 (67%)**, with the browser directly responsible for 5 of the 8:

| Publisher | Before | With browser fetcher |
|---|---|---|
| Wiley | 0/9 | **3/3** |
| Elsevier | 4/49 (~8%) | **2/3** |

Getting there took more than "add a browser" — see
[docs/ZOTERO_HOW_IT_WORKS.md](docs/ZOTERO_HOW_IT_WORKS.md) for the full
investigation, including why a stock Playwright Firefox is still blocked.

### Method by method

`scripts/benchmark_downloaders.py` measures every strategy against a fixed set
spanning open-access, preprint and paywalled publishers, and renders this chart
(open internet connection, no institutional access):

![Download method comparison](docs/images/download_benchmark.png)

Light bar is reach (papers the method applies to), dark bar is PDFs actually
retrieved. Three things it shows:

- **No single method dominates.** The fallback chain retrieved 8/12 — more than
  any individual strategy.
- **Source-specific methods are perfect but narrow.** arXiv 2/2, bioRxiv 1/1,
  and useless everywhere else.
- **The 4 misses are all paywalled or Cloudflare-protected.** No method reaches
  those without institutional access.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env                    # add one API key / your email
cp config.example.yaml config.yaml      # query, years, sources, filters
python scripts/setup_zotero.py          # one-time, optional — see below
python main.py --ai                     # fetch -> screen -> download
```

`main.py` preflight-checks what each step needs, auto-starts the services it can
(the Zotero translation server; Ollama, including pulling the model), prints an
exact fix for anything missing, and reports how long each step took.

Useful variants: `python main.py` (fast keyword filter, no LLM),
`--skip-download` (stop after screening), `--config my.yaml`.

Or run the steps yourself:

```bash
python 01_fetch_metadata.py
python 02_abstract_filter_ai.py   # or 02_abstract_filter.py for keyword filtering
python 03_download_papers.py
```

### One-time: the Zotero translation server

The download step gets noticeably better PDF coverage with the vendored Zotero
translation server, which extracts PDF links from publisher landing pages. It is
a **git submodule**, so a fresh clone does not have it — `scripts/setup_zotero.py`
initialises it, runs `npm install` and applies a required patch. It needs Node.js
and only has to be done once.

You don't have to remember: both `main.py` and `03_download_papers.py` detect a
missing or unstarted server and offer to set it up and launch it for you. Skipping
it is fine too — Zotero's *hosted* open-access index needs no local server, so
downloads still work, you just retrieve fewer PDFs
([the numbers](#pdf-retrieval): 33% → 39% on a 123-DOI set).

Output lands in `results/`: `papers.csv`, `references.bib`, `references.ris`,
`pdfs/`, plus a per-paper decision log for the screening step.

## Detail

| If you want to | Read |
|---|---|
| Install it properly, set API keys, add the optional services | [docs/SETUP.md](docs/SETUP.md) |
| Configure a run — query, filters, models, download toggles | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| Write a good boolean query | [docs/QUERY_SYNTAX.md](docs/QUERY_SYNTAX.md) |
| See filtering end to end on a worked example | [docs/FILTER_WORKFLOW_EXAMPLE.md](docs/FILTER_WORKFLOW_EXAMPLE.md) |
| Understand the download strategies | [docs/DOWNLOADER_GUIDE.md](docs/DOWNLOADER_GUIDE.md) |
| Know how Zotero really fetches PDFs, and how the browser fetcher beats Cloudflare | [docs/ZOTERO_HOW_IT_WORKS.md](docs/ZOTERO_HOW_IT_WORKS.md) |
| See how duplicates across sources are merged | [docs/DEDUPLICATION.md](docs/DEDUPLICATION.md) |

## What it will not do

- **Elsevier is still hard.** ScienceDirect sits behind Cloudflare's interactive
  challenge on subscription content. The browser fetcher turns ~8% into
  something usable, but this is an arms race and there is no honest claim of a
  fix. Wiley and MDPI behave the same way; Wiley recovered better.
- **Paywalls are paywalls.** The resolver chain only *finds* a PDF link. You
  still need access — campus network or VPN. IP-based access works; cookie-based
  library logins largely do not.
- **Screening is a filter, not a reviewer.** At 0.971 agreement the best model
  still disagrees with a human on roughly 1 paper in 34. Read
  `manual_review_ai.csv` and spot-check `filtered_out_ai/` before trusting a
  corpus.
- **Google Scholar is unreliable.** Google blocks automated queries; it is off by
  default and hard-timeout-guarded so it cannot stall a run.
- **Local LLM screening costs wall time, not money.** Thousands of abstracts is
  an overnight job, not a coffee break.
- **Benchmarks drift.** Publisher rate limits and IP reputation contaminate
  repeated runs — treat cross-run deltas of a few papers as noise, and space
  re-runs out.

## Legal notice

Respect copyright and publisher terms of service. Check your institutional
access rights. The Sci-Hub fallback is off by default; enabling it is your
decision under your local law. Keep your API keys private.

## License

MIT.
