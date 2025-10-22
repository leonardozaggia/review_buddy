# Review Buddy

Search and download academic papers from multiple sources with intelligent fallback strategies.

## Features

- **5 Search Sources**: Scopus, PubMed, arXiv, Google Scholar, IEEE Xplore
- **Smart Deduplication**: Merges results across sources automatically
- **Abstract-Based Filtering**: Remove unwanted papers with keyword or AI-powered filtering
- **AI-Powered Filtering**: Use LLMs for intelligent, context-aware filtering (optional)
  - ⚠️ **FREE TIER LIMIT**: 50 requests/day on free OpenRouter model
- **10+ Download Methods**: arXiv, bioRxiv, Unpaywall, PMC, publisher patterns, HTML scraping, Crossref, Sci-Hub (optional)
- **Multiple Formats**: BibTeX, RIS, CSV export
- **Production Ready**: Comprehensive error handling and logging

## Quick Start

**1. Install dependencies:**
```bash
pip install -r requirements.txt
```

**2. Configure API keys:**
```bash
cp .env.example .env
# Edit .env and add at least one API key
```

**3. Run:**
```bash
python 01_fetch_metadata.py     # Search papers
python 02_abstract_filter.py    # Filter by keywords (optional)
# OR
python 02_abstract_filter_AI.py # Filter with AI (optional, requires OpenRouter key)
python 03_download_papers.py    # Download PDFs
```

Results in `results/` folder: `papers.csv`, `references.bib`, `references.ris`, `pdfs/`

## ⚠️ AI Filtering Limitations

**The free OpenRouter model has a 50 requests/day limit.**

- For datasets with **>50 papers**, use keyword filtering (`02_abstract_filter.py`) or upgrade to a paid model
- Free tier resets daily
- Paid models available: `anthropic/claude-3-haiku`, `openai/gpt-4o-mini` (see `docs/AI_FILTERING_GUIDE.md`)
- Keyword filtering has no limits and works for any dataset size

## Configuration

### API Keys (at least one required)

**Scopus**: Get from [Elsevier Developer Portal](https://dev.elsevier.com/)  
**PubMed**: Use any valid email (free, no registration)  
**OpenRouter** (optional, for AI filtering): Get from [OpenRouter](https://openrouter.ai/keys)  
  - ⚠️ **FREE TIER LIMITATION**: 50 requests per day limit on `openai/gpt-oss-20b:free` model
  - For larger datasets (>50 papers), use paid models or keyword filtering
**IEEE** (optional): Get from [IEEE Developer Portal](https://developer.ieee.org/)

**arXiv and Google Scholar work without keys.**

Edit `.env`:
```bash
SCOPUS_API_KEY=your_key_here
PUBMED_EMAIL=your.email@example.com
OPENROUTER_API_KEY=your_key_here  # Optional, for AI filtering
UNPAYWALL_EMAIL=your.email@example.com  # Optional, for open access papers
```

## Query Syntax

Edit `QUERY` in `01_fetch_metadata.py`:

| Operator | Example | Result |
|----------|---------|--------|
| **AND** | `machine learning AND healthcare` | Both terms required |
| **OR** | `neural networks OR deep learning` | Either term |
| **NOT** | `AI NOT reinforcement` | Exclude term |
| **" "** | `"machine learning"` | Exact phrase |
| **( )** | `(AI OR ML) AND diagnosis` | Grouping |

**Inline query:**
```python
QUERY = "machine learning AND healthcare"
```

**From text file (supports multi-line, formatted queries):**
```python
QUERY = Path("query.txt").read_text(encoding="utf-8").strip()
```

**Examples:**
```python
"machine learning healthcare"                      # Implicit AND
"(COVID-19 OR coronavirus) AND diagnosis"          # Boolean logic
'"deep learning" AND "medical imaging"'            # Exact phrases
"AI AND cardiology NOT review"                     # Exclusion
```

**📖 More examples**: See [Query Syntax Guide](docs/QUERY_SYNTAX.md)

## PDF Download

**10+ intelligent strategies with automatic fallback:**

1. Direct PDF links → 2. arXiv → 3. bioRxiv/medRxiv → 4. Unpaywall API → 5. Crossref → 6. PubMed Central (US & Europe) → 7. Publisher patterns (MDPI, Frontiers, Nature, IEEE, ScienceDirect, Springer, PLOS) → 8. ResearchGate/Academia.edu → 9. HTML scraping → 10. Sci-Hub (optional)

**Expected success rates:**
- arXiv papers: 95%+
- bioRxiv/medRxiv: 95%+
- Open access publishers: 80-90%
- Overall (without Sci-Hub): 50-70%
- Overall (with Sci-Hub): 70-90%

**📖 Details**: See [Downloader Guide](docs/DOWNLOADER_GUIDE.md)

## Customization

**Search settings** (`01_fetch_metadata.py`):
```python
# Inline query
QUERY = "machine learning AND healthcare"

# Or from text file (for complex, multi-line queries)
QUERY = Path("query.txt").read_text(encoding="utf-8").strip()

YEAR_FROM = 2020
MAX_RESULTS_PER_SOURCE = 50
```

**Download settings** (`03_download_papers.py`):
```python
USE_SCIHUB = False  # Enable Sci-Hub fallback (use responsibly)
```

## Documentation

- **[Quick Start](docs/QUICKSTART.md)** - Fast setup guide
- **[Query Syntax](docs/QUERY_SYNTAX.md)** - Advanced query examples by field
- **[Abstract Filtering](docs/ABSTRACT_FILTERING.md)** - Filter papers by language, study type, topics
- **[AI Filtering Guide](docs/AI_FILTERING_GUIDE.md)** - AI-powered filtering with LLMs
- **[Downloader Guide](docs/DOWNLOADER_GUIDE.md)** - PDF download strategies and troubleshooting
- **[Deduplication Logic](docs/DEDUPLICATION.md)** - How duplicate papers are merged (prioritizes PubMed)
- **[Implementation](docs/IMPLEMENTATION_SUMMARY.md)** - Technical architecture details

## Troubleshooting

**No papers found?**
- Check API keys in `.env`
- Verify internet connection
- Try simpler query

**Downloads failing?**
- Set `UNPAYWALL_EMAIL` in `.env`
- Check `results/pdfs/download.log` for details
- Enable `USE_SCIHUB = True` (if legal in your jurisdiction)

**Import errors?**
- Run scripts from repository root: `python 01_fetch_metadata.py`

## Project Structure

```
review_buddy/
├── 01_fetch_metadata.py         # Search papers
├── 02_abstract_filter.py        # Filter by keywords (optional)
├── 02_abstract_filter_AI.py     # Filter with AI (optional)
├── 03_download_papers.py        # Download PDFs
├── compare_filtering_strategies.py  # Compare keyword vs AI filtering
├── .env.example                 # Configuration template
├── src/
│   ├── config.py               # Config management
│   ├── models.py               # Paper data model
│   ├── paper_searcher.py       # Search coordinator
│   ├── abstract_filter.py      # Keyword-based filtering
│   ├── ai_abstract_filter.py   # AI-powered filtering
│   ├── llm_client.py           # OpenRouter API client
│   └── searchers/              # Source implementations
│       ├── scopus_searcher.py
│       ├── pubmed_searcher.py
│       ├── arxiv_searcher.py
│       ├── scholar_searcher.py
│       ├── ieee_searcher.py
│       └── paper_downloader.py # Download logic
├── docs/                        # Documentation
└── results/                     # Output (auto-created)
    ├── papers.csv
    ├── papers_filtered.csv     # After keyword filtering
    ├── papers_filtered_ai.csv  # After AI filtering
    ├── references.bib
    ├── references_filtered.bib # After keyword filtering
    ├── references_filtered_ai.bib  # After AI filtering
    └── pdfs/
```

## Requirements

- Python 3.7+
- See `requirements.txt` for dependencies

## Legal Notice

- Respect copyright and terms of service
- Use Sci-Hub responsibly per local laws
- Keep API keys private
- Check institutional access rights

## License

MIT License - See LICENSE file
