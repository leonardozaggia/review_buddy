# Additional README sections for filtering engines and examples

## Filtering Engines Comparison

### Normal Engine (Keyword-Based)

Fast, rule-based filtering using keyword matching.

**Pros:**
- ✅ Fast (instant for 1000s of papers)
- ✅ Deterministic and reproducible
- ✅ No external dependencies
- ✅ Easy to customize

**Cons:**
- ❌ May miss context-dependent cases
- ❌ False positives/negatives from keyword matching

**Use when:** You have clear exclusion criteria, speed is important, or need reproducible results.

```bash
reviewbuddy filter --engine normal
```

### AI Engine (LLM-Powered)

Nuanced filtering using local Ollama LLM.

**Pros:**
- ✅ Understands context and nuance
- ✅ Natural language filter definitions
- ✅ Handles edge cases better
- ✅ Flags uncertain papers for manual review

**Cons:**
- ❌ Requires Ollama installation
- ❌ Slower (seconds per paper)
- ❌ Non-deterministic
- ❌ Requires GPU for large models

**Use when:** Filters require understanding context or catching subtle exclusions.

**Setup:**
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull model
ollama pull llama3.1:8b

# Run filtering
reviewbuddy filter --engine ai
```

## Usage Examples

### Example 1: Basic Workflow

```bash
# 1. Initialize
reviewbuddy init

# 2. Edit config.yaml - set your query
# query: "machine learning AND healthcare"

# 3. Add API keys to .env
# PUBMED_EMAIL=your@email.com

# 4. Run full pipeline
reviewbuddy run
```

### Example 2: Keyword Filtering

```bash
# Search
reviewbuddy search --query "deep learning medical imaging" --year-from 2020

# Filter with custom config
reviewbuddy filter --engine normal --config my_filters.yaml

# Download
reviewbuddy download
```

### Example 3: AI Filtering

```bash
# Start Ollama
ollama serve

# Filter with AI (in another terminal)
reviewbuddy filter --engine ai

# Results in results/papers_filtered.csv + manual_review.csv
```

### Example 4: Using the GUI

```bash
streamlit run app.py
# 1. Go to "Search" tab
# 2. Enter query or upload file
# 3. Go to "Filter" tab
# 4. Toggle engine (normal/ai)
# 5. Click "Apply Filters"
# 6. Go to "Download" tab
# 7. Download PDFs
```

### Example 5: Custom Workflow

```bash
# Search only
reviewbuddy search --query "AI diagnostics" --max-results 50

# Review papers manually, then filter
reviewbuddy filter --skip-search

# Download without Sci-Hub
reviewbuddy download --no-scihub
```

## Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=core --cov=src --cov-report=html

# View coverage
open htmlcov/index.html
```

## Demo Script

Try the included demo:

```bash
python demo.py
```

This runs the full pipeline on sample data in `data/sample_papers.csv`.

## Project Structure (v2.0)

```
review_buddy/
├── cli.py                       # Unified CLI (new)
├── app.py                       # Streamlit GUI (new)
├── config.yaml                  # Pipeline configuration (new)
├── demo.py                      # Demo script (new)
├── pyproject.toml               # Package metadata (new)
│
├── core/                        # Core modules (new)
│   ├── __init__.py
│   ├── config_loader.py        # YAML config + Pydantic models
│   ├── engines.py              # Filter engine factory
│   ├── filter_ai.py            # AI filter engine
│   ├── filter_normal.py        # Keyword filter engine
│   ├── io.py                   # Load/save papers
│   ├── postprocess.py          # Result postprocessing
│   └── preprocess.py           # Preprocessing utilities
│
├── src/                         # Original modules (maintained)
│   ├── abstract_filter.py      # Keyword filtering logic
│   ├── ai_abstract_filter.py   # AI filtering logic
│   ├── config.py               # API config
│   ├── llm_client.py           # Ollama client
│   ├── models.py               # Paper data model
│   ├── paper_searcher.py       # Search coordinator
│   ├── utils.py                # BibTeX/CSV utilities
│   └── searchers/              # Source implementations
│
├── tests/                       # Test suite (new)
│   ├── test_config.py
│   ├── test_filter_normal.py
│   └── test_io.py
│
├── data/                        # Sample data (new)
│   └── sample_papers.csv
│
├── docs/                        # Documentation
├── results/                     # Output directory
│
# Legacy scripts (maintained for compatibility)
├── 01_fetch_metadata.py
├── 02_abstract_filter.py
├── 02_abstract_filter_AI.py
└── 03_download_papers.py
```

## Architecture

```
┌─────────────────────────────────────┐
│           Interfaces                │
│  ┌─────────┐        ┌──────────┐  │
│  │   CLI   │        │   GUI    │  │
│  │ (Typer) │        │(Streamlit)│  │
│  └────┬────┘        └─────┬────┘  │
└───────┼──────────────────┼────────┘
        │                  │
┌───────┴──────────────────┴────────┐
│          Core Pipeline             │
│  ┌──────────────────────────────┐ │
│  │ PipelineConfig (Pydantic)    │ │
│  └──────────────────────────────┘ │
│  ┌──────────────────────────────┐ │
│  │ Filter Engines (Abstract)    │ │
│  │  ├─ NormalFilterEngine       │ │
│  │  └─ AIFilterEngine           │ │
│  └──────────────────────────────┘ │
│  ┌──────────────────────────────┐ │
│  │ I/O Layer                    │ │
│  │  ├─ load_papers()            │ │
│  │  └─ save_papers()            │ │
│  └──────────────────────────────┘ │
└────────────────────────────────────┘
```

Key design principles:
- **Separation of Concerns**: UI, business logic, and data are separated
- **Interface Consistency**: Both engines implement `filter_records()`
- **Configuration First**: All settings in YAML or env vars
- **Testability**: Core logic is unit-testable
- **Backward Compatibility**: Old scripts still work

## Environment Variables Reference

```bash
# Search API Keys
SCOPUS_API_KEY=your_scopus_key
PUBMED_EMAIL=your.email@example.com
IEEE_API_KEY=your_ieee_key

# Download
UNPAYWALL_EMAIL=your.email@example.com

# AI Filtering
OLLAMA_MODEL=llama3.1:8b
OLLAMA_URL=http://localhost:11434

# Override config.yaml
FILTER_ENGINE=normal  # or 'ai'
```
