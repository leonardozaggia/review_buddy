# Configuration

**All run options live in one file: `config.yaml`.** Query, year range, sources,
filters and download toggles are set there — not by editing the `.py` scripts —
so your settings never clutter git history (`config.yaml` is gitignored).

```bash
cp config.example.yaml config.yaml    # one-time; then edit config.yaml
```

`config.yaml` only needs the keys you want to change; everything else falls back
to the documented defaults in `config.example.yaml`, which is the authoritative
annotated reference. API keys and emails are the exception — those stay in `.env`
(secrets, not run settings). See [SETUP.md](SETUP.md).

```yaml
search:
  year_from: 2018
  sources: [pubmed, arxiv]
download:
  use_browser: true
  max_workers: 8
```

Run a different config with `python main.py --config my.yaml`.

## Search

```yaml
search:
  query: "machine learning AND healthcare"   # or null to read query_file
  query_file: query.txt
  year_from: 2020
  year_to: null                 # null = up to the current year
  max_results_per_source: 50    # use a big number (e.g. 999999) for "unlimited"
  pubmed_field: tiab            # Title/Abstract only; null = all fields
  sources: [scopus, pubmed, arxiv]
  output_dir: results
```

**Query.** Set `query` inline, or leave it null and put the query in `query.txt`
— handy for long multi-line boolean queries. Whitespace and newlines are
normalised automatically.

| Operator | Example | Result |
|----------|---------|--------|
| AND | `machine learning AND healthcare` | Both terms required |
| OR | `neural networks OR deep learning` | Either term |
| NOT | `AI NOT reinforcement` | Exclude term |
| `" "` | `"machine learning"` | Exact phrase |
| `( )` | `(AI OR ML) AND diagnosis` | Grouping |
| `*` | `Electroencephalogra*` | Wildcard (removed automatically for arXiv) |

Queries are adapted per source automatically. Field-specific syntax, per-source
compatibility and worked examples: [QUERY_SYNTAX.md](QUERY_SYNTAX.md).

**`pubmed_field: tiab` matters more than it looks.** Without it PubMed matches
*all* fields — references, affiliations, MeSH — and gets hugely noisy: a
neonatal-fMRI query returns ~13,900 all-field results vs ~800 with `tiab`.

**Sources.** `scholar` is deliberately not in the default list; Google blocks
automated queries aggressively, so it typically hangs or serves a CAPTCHA. It is
guarded by a hard timeout so it cannot stall a run, but expect 0 results without
a proxy.

Duplicate handling across sources is described in [DEDUPLICATION.md](DEDUPLICATION.md).

## Keyword filter

```yaml
filter:
  enabled:
    no_abstract: true       # drop papers with no abstract
    non_english: true       # needs langdetect
    epilepsy: true
    bci: true
    non_human: true
    non_empirical: true
  keywords:
    epilepsy: [epileptic spike, interictal spike, epileptiform, ...]
    # add your own filters here — the key is the filter name
```

A paper is removed if any keyword matches (whole-word) in title or abstract.
Defining `enabled` or `keywords` in your `config.yaml` **replaces** the defaults
wholesale, so a domain-specific config runs exactly the filters you list.

Each filter writes what it removed to `results/filtered_out/<filter>.csv` so you
can check for false positives and iterate. A complete worked example — custom
filters, output, how to tighten keywords that catch too much — is in
[FILTER_WORKFLOW_EXAMPLE.md](FILTER_WORKFLOW_EXAMPLE.md).

## LLM filter

```yaml
ai_filter:
  model: gemma3:4b             # any Ollama model; OLLAMA_MODEL env var overrides
  ollama_url: http://localhost:11434
  confidence_threshold: 0.5    # min confidence (0-1) to actually exclude a paper
  temperature: 0.1
  retry_attempts: 3
  cache_responses: true
  structured_output: true      # constrain replies to a JSON schema
  max_workers: 4               # concurrent requests to Ollama; 1 is serial
  filters:
    non_empirical:
      enabled: true
      prompt: "Is this a review, survey, meta-analysis, or opinion piece without original empirical data?"
      description: "Reviews and non-empirical papers"
```

Each filter is a natural-language yes/no question about the paper. No regex, no
keyword list.

### Phrase prompts positively

Ask **"is this a paper we want?"** and set `invert: true`, rather than "is this a
paper we drop?". Models under ~10B parameters answer negated questions ("does
this study *lack* fMRI?") with sound reasoning and the opposite answer often
enough to break a filter silently. On this repo's corpus that single change took
one filter from **0.35 to 0.91** agreement with hand labels. Compare candidate
models and prompt polarities on your own corpus with
`scripts/benchmark_ollama_models.py`.

### Choosing a model

Measured on a 6 GB-VRAM laptop GPU, agreement scored against hand-labelled
papers by `scripts/benchmark_ollama_models.py`:

| Model | Agreement | Per paper (serial) | Per 1000 papers |
|---|---|---|---|
| `gemma3:4b` | 0.906 | ~7-16 s | ~2-4.5 h |
| `gemma3:12b` | 0.935 | ~37 s | ~10 h |
| `gpt-oss:20b` | 0.971 | ~20 s | ~5.5 h |

`max_workers: 4` cuts wall time substantially whenever the model does not fit
entirely in VRAM, because inference is memory-bound there: the real 5,295-paper
run averaged **3.7 s/paper** end to end with `gemma3:4b` at 4 workers.

Use `gemma3:4b` while you are still iterating on filter wording, then do the
final pass with `gpt-oss:20b` if the extra accuracy is worth the wall time.
Avoid reasoning models such as `qwen3` — their thinking cannot be disabled
reliably and they take ~90 s per paper.

`structured_output: true` constrains replies to a JSON schema. Turn it off only
for models that return nothing with it (gpt-oss does; it falls back
automatically).

### Caching

Responses are cached under `results/ai_cache/`, so an interrupted run resumes
cheaply and re-runs are near-instant. The cache key includes the model name and
the filter set, so changing either correctly forces re-evaluation rather than
silently reusing old verdicts.

### Output

| File | Contents |
|---|---|
| `results/papers_filtered_ai.csv` | Papers kept |
| `results/references_filtered_ai.bib` | Bibliography of kept papers |
| `results/manual_review_ai.csv` | Low-confidence decisions, flagged for a human |
| `results/filtered_out_ai/` | What each filter removed, one CSV per filter |
| `results/ai_filtering_log_*.json` | Per-paper decision, confidence and reasoning |

`03_download_papers.py` picks `results/references_filtered.bib` if it exists and
falls back to `results/references.bib`. To download the AI-filtered set, point
`download.bib_file` at `results/references_filtered_ai.bib`.

Compare the two filtering strategies on the same corpus with
`python scripts/compare_filters.py`.

## Download

```yaml
download:
  bib_file: null          # null = auto-pick filtered, else unfiltered
  output_dir: results/pdfs
  max_workers: 4          # parallel download workers (1 = sequential)
  use_zotero: true        # Zotero resolver chain (OA index + translation server)
  use_scihub: false       # Sci-Hub fallback (use responsibly, per local law)
  use_browser: false      # Camoufox real-browser fetcher (Cloudflare publishers)
```

`use_zotero` helps even without the local translation server running, because
Zotero's open-access index is a remote service. `use_browser` needs a one-time
Camoufox install — see [SETUP.md](SETUP.md).

Strategy order, per-method behaviour and the log format:
[DOWNLOADER_GUIDE.md](DOWNLOADER_GUIDE.md). Why the resolver chain is built the
way it is: [ZOTERO_HOW_IT_WORKS.md](ZOTERO_HOW_IT_WORKS.md).
