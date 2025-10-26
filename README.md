# Review Buddy

Search and download academic papers from multiple sources with intelligent fallback strategies.

## 🆕 Version 2.0 - Major Refactor

**Review Buddy has been refactored** to provide:
- **Unified CLI**: Single `reviewbuddy` command for all operations
- **Clean GUI**: Streamlit web interface for the complete pipeline
- **Modular Architecture**: Separate core logic from interfaces
- **Flexible Configuration**: YAML-based config with sensible defaults
- **Unified Filtering API**: Both keyword and AI filters use the same interface

### 🚀 Quick Start (New Way)

```bash
# Install
pip install -e .

# Initialize config
reviewbuddy init

# Run full pipeline
reviewbuddy run

# Or use the GUI
streamlit run app.py
```

### 📋 Migration Guide

**Old scripts still work!** The original `01_*.py`, `02_*.py`, `03_*.py` scripts are maintained for backward compatibility.

**New unified commands:**
| Old | New |
|-----|-----|
| `python 01_fetch_metadata.py` | `reviewbuddy search` |
| `python 02_abstract_filter.py` | `reviewbuddy filter --engine normal` |
| `python 02_abstract_filter_AI.py` | `reviewbuddy filter --engine ai` |
| `python 03_download_papers.py` | `reviewbuddy download` |
| All three steps | `reviewbuddy run` |

**Benefits of new CLI:**
- Consistent flags across all commands
- Single YAML config file
- Better error messages
- Progress indicators
- `--help` for every command

---

## Features

- **5 Search Sources**: Scopus, PubMed, arXiv, Google Scholar, IEEE Xplore
- **Smart Deduplication**: Merges results across sources automatically
- **Dual Filtering Engines**: Keyword-based (fast) or AI-powered (nuanced)
- **10+ Download Methods**: arXiv, bioRxiv, Unpaywall, PMC, publisher patterns, HTML scraping, Crossref, Sci-Hub (optional)
- **Multiple Formats**: BibTeX, RIS, CSV export
- **Production Ready**: Comprehensive error handling and logging
- **CLI & GUI**: Command-line tool + web interface

## Installation

### Option 1: pip install (recommended)

```bash
# Clone repository
git clone https://github.com/leonardozaggia/review_buddy.git
cd review_buddy

# Install with dependencies
pip install -e .

# Verify installation
reviewbuddy --help
```

### Option 2: Direct dependencies

```bash
pip install -r requirements.txt
```

## Quick Start - CLI

**1. Create configuration:**
```bash
reviewbuddy init
# Edit config.yaml with your search query and settings
```

**2. Configure API keys:**
```bash
cp .env.example .env
# Edit .env and add at least one API key
```

**3. Run the pipeline:**

```bash
# Full pipeline: search → filter → download
reviewbuddy run

# Or run individual steps:
reviewbuddy search --query "machine learning AND healthcare"
reviewbuddy filter --engine normal
reviewbuddy download
```

**4. View configuration:**
```bash
reviewbuddy info
```

### CLI Command Reference

```bash
# Initialize config.yaml
reviewbuddy init

# Search for papers
reviewbuddy search \
  --query "machine learning healthcare" \
  --year-from 2020 \
  --max-results 100

# Filter with keyword engine
reviewbuddy filter --engine normal

# Filter with AI engine
reviewbuddy filter --engine ai

# Download PDFs
reviewbuddy download --scihub

# Run full pipeline
reviewbuddy run --engine normal

# Skip steps in pipeline
reviewbuddy run --skip-search    # Use existing papers
reviewbuddy run --skip-filter    # Skip filtering
reviewbuddy run --skip-download  # Only search and filter

# Show current config
reviewbuddy info

# Use custom config file
reviewbuddy run --config my_config.yaml
```

## Quick Start - GUI

**Launch the GUI:**

```bash
streamlit run app.py
```

The GUI provides a three-step workflow:

1. **🔍 Search/Upload**: Search databases or upload existing papers
2. **🎯 Filter**: Apply keyword or AI filters with live preview
3. **⬇️ Download**: Download PDFs with progress tracking

**GUI Features:**
- File upload (BibTeX, CSV)
- Interactive configuration
- Real-time preview of papers
- Filter toggle (normal ↔ ai)
- Download CSV/BibTeX results
- Visual filtering statistics

## Configuration

### Config File (`config.yaml`)

The `config.yaml` file centralizes all pipeline settings:

```yaml
# Filter engine: 'normal' (keyword) or 'ai' (LLM)
engine: normal

# Input/output paths
io:
  input_path: results/references.bib
  output_dir: results
  pdf_dir: results/pdfs

# Search settings
search:
  query: machine learning AND healthcare
  year_from: 2020
  max_results_per_source: 999999

# Normal (keyword) filter
normal:
  enabled_filters:
    - no_abstract
    - non_english
    - non_human
    - non_empirical
  keywords:
    non_human:
      - rat
      - mouse
      - in vitro
    # Add custom filters here

# AI filter
ai:
  model: llama3.1:8b
  ollama_url: http://localhost:11434
  confidence_threshold: 0.5
  filters:
    non_human:
      enabled: true
      prompt: "Is this paper based on animal studies or in-vitro experiments?"
    # Add custom AI filters here

# Download settings
download:
  use_scihub: false
  unpaywall_email: null
```

**Generate default config:**
```bash
reviewbuddy init
```

### Environment Variables
### Environment Variables

API keys are configured in `.env` file:

```bash
cp .env.example .env
# Edit and add API keys
```

**Required (at least one):**

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
├── 02_abstract_filter.py        # Filter by abstract (optional)
├── 03_download_papers.py        # Download PDFs
├── .env.example                 # Configuration template
├── src/
│   ├── config.py               # Config management
│   ├── models.py               # Paper data model
│   ├── paper_searcher.py       # Search coordinator
│   ├── abstract_filter.py      # Abstract-based filtering
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
    ├── papers_filtered.csv     # After filtering
    ├── references.bib
    ├── references_filtered.bib # After filtering
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
