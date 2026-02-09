# Review Buddy

Search and download academic papers from multiple sources with intelligent fallback strategies.

## Features

- **5 Search Sources**: Scopus, PubMed, arXiv, Google Scholar, IEEE Xplore
- **Smart Deduplication**: Merges results across sources automatically
- **Abstract-Based Filtering**: Remove unwanted papers (non-English, animal studies, reviews, etc.)
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
python 02_abstract_filter.py    # Filter by abstract (optional)
python 03_download_papers.py    # Download PDFs
```

**Optional: AI-powered filtering with Ollama** 

For more sophisticated filtering, use `02_abstract_filter_ai.py` with a local LLM (Ollama). This provides:
- Natural language filter definitions (no regex patterns needed)
- Confidence scores and reasoning for each decision
- Customizable filters for your specific review criteria

**Quick setup:**
```bash
# 1. Install Ollama (if not already installed)
# Visit https://ollama.ai and follow installation instructions for your OS

# 2. Pull a model (one-time)
ollama pull llama3.1:8b

# 3. Start Ollama server (in a separate terminal)
ollama serve

# 4. Run AI filtering
python 02_abstract_filter_ai.py
```

The script will cache LLM responses to avoid redundant API calls. First run may take 10-30 minutes depending on the number of papers and your hardware. Subsequent runs with cached papers are much faster.

**HPC/Cluster users**: See `run_filter_hpc.sh` for a SLURM job script example that manages the Ollama server automatically.

Results in `results/` folder: `papers.csv`, `references.bib`, `references.ris`, `pdfs/`

**Note:** The download script automatically uses filtered results (`references_filtered.bib`) if available, otherwise uses original results (`references.bib`).

## Configuration

### API Keys (at least one required)

**Scopus**: Get from [Elsevier Developer Portal](https://dev.elsevier.com/)  
**PubMed**: Use any valid email (free, no registration)  
**IEEE** (optional): Get from [IEEE Developer Portal](https://developer.ieee.org/)

**arXiv and Google Scholar work without keys.**

Edit `.env`:
```bash
SCOPUS_API_KEY=your_key_here
PUBMED_EMAIL=your.email@example.com
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


**📖 Details**: See [Downloader Guide](docs/DOWNLOADER_GUIDE.md)

## Customization

**AI Filtering** (`02_abstract_filter_ai.py`):

Customize filters by editing the `FILTERS_CONFIG` dictionary in the script:

```python
FILTERS_CONFIG = {
    'epilepsy': {
        'enabled': True,
        'prompt': "Does this paper focus primarily on epileptic spikes or seizure detection?",
        'description': "Papers about epilepsy-related spike detection"
    },
    'your_custom_filter': {
        'enabled': True,
        'prompt': "Your natural language question about the paper",
        'description': "Brief description for logs"
    },
}
```

**Model Configuration:**
```python
AI_CONFIG = {
    'model': 'llama3.1:8b',           # Ollama model (change if needed)
    'confidence_threshold': 0.5,      # Min confidence to filter (0.0-1.0)
    'temperature': 0.1,               # Low for consistency
    'cache_responses': True,          # Avoid redundant LLM calls
}
```

**System requirements:**
- RAM: 8GB minimum (16GB+ recommended for 8B models)
- Models: Any Ollama-compatible model (`llama3.1`, `mistral`, `phi3`, etc.)
- Speed: ~10-30 papers/minute on CPU (faster with GPU)

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

- **[Query Syntax](docs/QUERY_SYNTAX.md)** - Advanced query examples by field
- **[Filter Workflow Example](docs/FILTER_WORKFLOW_EXAMPLE.md)** - Complete filtering workflow with examples
- **[Downloader Guide](docs/DOWNLOADER_GUIDE.md)** - PDF download strategies and troubleshooting
- **[Deduplication Logic](docs/DEDUPLICATION.md)** - How duplicate papers are merged (prioritizes PubMed)

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
├── 02_abstract_filter.py        # Keyword-based filtering (optional)
├── 02_abstract_filter_ai.py     # AI/LLM-based filtering (optional)
├── 03_download_papers.py        # Download PDFs
├── .env.example                 # Configuration template
├── src/
│   ├── config.py               # Config management
│   ├── models.py               # Paper data model
│   ├── paper_searcher.py       # Search coordinator
│   ├── abstract_filter.py      # Keyword filtering logic
│   ├── ai_abstract_filter.py   # AI filtering logic
│   ├── llm_client.py           # Ollama LLM client
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
    ├── ai_cache/               # Cached LLM responses
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
