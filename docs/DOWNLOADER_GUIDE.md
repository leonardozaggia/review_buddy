# Paper Downloader Guide

## Overview

The Paper Downloader module automatically downloads PDFs for papers from your search results. It prioritizes open-access sources and provides fallback strategies for maximum coverage.

## Features

✅ **Multi-strategy download approach with automatic fallback:**
1. Direct PDF links (if available in metadata)
2. arXiv PDFs (fully automatic, no API key needed)
3. bioRxiv/medRxiv (for biomedical preprints)
4. Unpaywall (open access papers via DOI)
5. Crossref API (full-text links)
6. PubMed Central (US & Europe mirrors)
7. Publisher-specific patterns (MDPI, Frontiers, Nature, IEEE, ScienceDirect, Springer, PLOS)
8. ResearchGate & Academia.edu (academic social networks)
9. HTML scraping (extracts PDF links from paper pages)
10. Sci-Hub (optional fallback for paywalled papers)

✅ **Smart handling:**
- DOI lookup via Crossref (if DOI missing)
- Deduplication (skips already downloaded papers)
- Robust error handling and detailed logging
- User-agent spoofing for better compatibility
- PDF content validation

## Setup

### Required Dependencies

```bash
pip install requests python-dotenv bibtexparser rispy
```

### Optional Dependencies

For Sci-Hub support:
```bash
pip install scihub
```

### Environment Configuration

Add to your `.env` file:
```
UNPAYWALL_EMAIL=your.email@example.com
```

Unpaywall requires an email address for API access (free, no registration needed).

## Usage

### Basic Usage

```python
from searchers.paper_downloader import PaperDownloader

# Initialize downloader
downloader = PaperDownloader(
    output_dir="results/pdfs",
    use_scihub=False,  # Set to True to enable Sci-Hub fallback
    unpaywall_email="your.email@example.com"
)

# Download from BibTeX file
downloader.download_from_bib("results/references.bib")

# Or download from RIS file
downloader.download_from_ris("results/references.ris")
```

### With Environment Variables

```python
import os
from dotenv import load_dotenv
from searchers.paper_downloader import PaperDownloader

load_dotenv()

downloader = PaperDownloader(
    output_dir="results/pdfs",
    use_scihub=True,
    unpaywall_email=os.getenv("UNPAYWALL_EMAIL")
)

downloader.download_from_bib("results/references.bib")
```

### Integration Example

See `03_download_papers.py` for a complete workflow example.

## Download Strategies

The downloader attempts strategies in the following order:

### 1. Direct PDF Links
- **When**: Paper metadata includes a direct PDF URL
- **Success Rate**: High for arXiv, preprints
- **API Key**: None required

### 2. arXiv
- **When**: Paper has arXiv ID or arXiv DOI
- **Success Rate**: Nearly 100% for arXiv papers
- **API Key**: None required
- **Example**: Any paper with DOI starting with `10.48550/arXiv.`

### 3. bioRxiv/medRxiv
- **When**: URL contains biorxiv.org or medrxiv.org
- **Success Rate**: ~95% for preprints
- **API Key**: None required
- **Coverage**: Biomedical preprints

### 4. Unpaywall
- **When**: Paper has a DOI and is open access
- **Success Rate**: ~30-50% depending on field
- **API Key**: Email address required (free)
- **Coverage**: Finds legal OA versions from publishers, repositories, etc.

### 5. Crossref API
- **When**: Paper has DOI
- **Success Rate**: Variable
- **API Key**: None required
- **Coverage**: Publisher full-text links

### 6. PubMed Central
- **When**: Paper has PMID or PubMed URL
- **Success Rate**: High for PMC papers
- **API Key**: None required
- **Coverage**: US and Europe PMC mirrors

### 7. Publisher-Specific Patterns
- **When**: DOI or URL matches known publisher
- **Success Rate**: 60-80% for supported publishers
- **API Key**: None required
- **Supported**: MDPI, Frontiers, Nature, IEEE, ScienceDirect, Springer, PLOS

### 8. ResearchGate & Academia.edu
- **When**: Title available
- **Success Rate**: Variable (20-30%)
- **API Key**: None required
- **Coverage**: Papers uploaded by authors

### 9. HTML Scraping
- **When**: URL available
- **Success Rate**: Variable (30-50%)
- **API Key**: None required
- **Coverage**: Extracts PDF links from paper landing pages

### 10. Sci-Hub (Optional)
- **When**: Enabled and paper has DOI
- **Success Rate**: Variable (depends on Sci-Hub availability)
- **Legal Note**: Use responsibly and in accordance with local laws
- **Setup**: Enabled via `USE_SCIHUB = True` in script

## Output

### Downloaded PDFs
- Saved to specified output directory
- Named using sanitized DOI or title
- Skips duplicates automatically

### Download Log
- Created in output directory as `download.log`
- Records all attempts, successes, and failures
- Useful for troubleshooting and tracking coverage

## Troubleshooting

### No Papers Downloaded

1. **Check environment variables:**
   ```python
   import os
   print(os.getenv("UNPAYWALL_EMAIL"))
   ```

2. **Verify .env file is loaded:**
   ```python
   from dotenv import load_dotenv
   load_dotenv()  # Add path if .env is not in current directory
   ```

3. **Check the log file:**
   - Look in `{output_dir}/download.log`
   - Check for specific error messages

### Low Success Rate

- **arXiv papers**: Should have ~100% success
- **OA papers**: Depend on Unpaywall coverage (~30-50%)
- **Paywalled papers**: Require Sci-Hub (enable with `use_scihub=True`)

### Sci-Hub Issues

The `scihub` library can be unstable due to:
- Changing Sci-Hub domains
- Connection timeouts
- API changes

If Sci-Hub fails, the downloader will log the error and continue with other papers.

## Testing

Run the test script to verify setup:

```bash
python searchers/test_paper_downloader.py
```

This will:
- Test arXiv downloads
- Test Unpaywall downloads
- Test Sci-Hub (if enabled)
- Report success rates

## Best Practices

1. **Start with open access**: Disable Sci-Hub initially to see OA coverage
2. **Check logs**: Review `download.log` to understand failures
3. **Batch processing**: Download in batches if you have many papers
4. **Respect rate limits**: The downloader includes reasonable delays
5. **Legal compliance**: Understand copyright and access rights in your jurisdiction

## Example Workflow

```python
# 1. Search for papers
from paper_searcher import PaperSearcher
from config import Config

config = Config(max_results_per_source=100)
searcher = PaperSearcher(config)
papers = searcher.search_all("machine learning healthcare", year_from=2020)

# 2. Generate bibliography
searcher.generate_bibliography(papers, format="bibtex", output_file="results/references.bib")

# 3. Download PDFs
from searchers.paper_downloader import PaperDownloader
import os
from dotenv import load_dotenv

load_dotenv()

downloader = PaperDownloader(
    output_dir="results/pdfs",
    use_scihub=False,  # Start with OA only
    unpaywall_email=os.getenv("UNPAYWALL_EMAIL")
)

downloader.download_from_bib("results/references.bib")

# 4. Check results
import os
pdf_count = len([f for f in os.listdir("results/pdfs") if f.endswith(".pdf")])
print(f"Downloaded {pdf_count} / {len(papers)} papers")
```

## Success Rate Expectations

Based on typical research queries:

- **arXiv papers**: 95-100% success
- **bioRxiv/medRxiv preprints**: 95-100% success
- **PubMed Central papers**: 90-95% success
- **Open access publishers (MDPI, Frontiers, PLOS)**: 80-90% success
- **Other open access (Unpaywall)**: 30-50% success
- **Paywalled (with Sci-Hub)**: Variable, 50-80% success
- **Overall (without Sci-Hub)**: 50-70% success
- **Overall (with Sci-Hub)**: 70-90% success

*Note: Success rates vary by research field, publication year, and publisher.*
