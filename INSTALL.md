# Installation Guide - Review Buddy v2.0

## Quick Install

### Method 1: pip install (Recommended)

```bash
# Clone repository
git clone https://github.com/leonardozaggia/review_buddy.git
cd review_buddy

# Install package with all dependencies
pip install -e .

# Verify installation
reviewbuddy --help
```

### Method 2: Manual requirements

```bash
# Install dependencies directly
pip install -r requirements.txt

# Run scripts directly
python3 cli.py --help
streamlit run app.py
```

## Dependencies

### Core Requirements

These are needed for basic functionality:

```
requests>=2.31.0
lxml>=4.9.0
python-dotenv>=1.0.0
beautifulsoup4>=4.12.0
tqdm>=4.66.0
bibtexparser>=1.4.0
rispy>=0.7.0
langdetect>=1.0.9
```

### v2.0 Requirements

Additional dependencies for the refactored version:

```
pandas>=1.3.0
pydantic>=2.0.0
pyyaml>=6.0
typer[all]>=0.9.0
rich>=13.0.0
streamlit>=1.28.0
```

### Optional

```
scholarly>=1.7.0    # For Google Scholar
scihub              # For Sci-Hub downloads
pytest>=7.0.0       # For running tests
```

## API Keys Setup

1. Copy environment template:
```bash
cp .env.example .env
```

2. Edit `.env` and add at least one API key:

```bash
# At least one required:
SCOPUS_API_KEY=your_scopus_key
PUBMED_EMAIL=your.email@example.com
IEEE_API_KEY=your_ieee_key

# Optional but recommended:
UNPAYWALL_EMAIL=your.email@example.com

# For AI filtering:
OLLAMA_MODEL=llama3.1:8b
OLLAMA_URL=http://localhost:11434
```

## Configuration

Create config file:

```bash
reviewbuddy init
```

This creates `config.yaml` with defaults. Edit as needed.

## Verify Installation

### Test CLI

```bash
reviewbuddy --help
reviewbuddy info
```

### Test Demo

```bash
python3 demo.py
```

This should:
1. Load sample papers from `data/sample_papers.csv`
2. Apply filters
3. Save results to `demo_output/`

### Test GUI

```bash
streamlit run app.py
```

Opens web interface at `http://localhost:8501`

## Troubleshooting

### ModuleNotFoundError: pydantic

```bash
pip install pydantic>=2.0.0
```

### ModuleNotFoundError: typer

```bash
pip install typer[all]>=0.9.0 rich>=13.0.0
```

### ModuleNotFoundError: streamlit

```bash
pip install streamlit>=1.28.0
```

### Command not found: reviewbuddy

If you used Method 2 (manual), run:
```bash
pip install -e .
```

Or use scripts directly:
```bash
python3 cli.py --help
```

### Old scripts not working

Old scripts `01_*.py`, `02_*.py`, `03_*.py` still work but need base dependencies:
```bash
pip install requests lxml python-dotenv beautifulsoup4 tqdm bibtexparser rispy langdetect
```

## Development Setup

For contributing:

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=core --cov=src --cov-report=html

# Format code
black .

# Type checking
mypy core/ src/
```

## Platform-Specific Notes

### macOS

Python 3 is pre-installed:
```bash
python3 --version
pip3 install -e .
```

### Linux

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3 python3-pip
pip3 install -e .
```

### Windows

```bash
# Install Python from python.org first
python --version
pip install -e .
```

## Minimal Setup (No GUI)

If you only want CLI:

```bash
pip install requests lxml python-dotenv beautifulsoup4 tqdm \
    bibtexparser rispy langdetect pandas pydantic pyyaml \
    typer[all] rich

# Skip streamlit
```

## Testing Installation

```bash
# Validate Python syntax
python3 -m py_compile cli.py app.py demo.py core/*.py

# Run tests
pytest tests/

# Try demo
python3 demo.py

# Try CLI
python3 cli.py info
```
