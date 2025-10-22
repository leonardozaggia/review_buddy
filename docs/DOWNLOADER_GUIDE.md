# Paper Downloader Guide

## Overview

The Paper Downloader module automatically downloads PDFs for papers from your search results. It prioritizes open-access sources and provides fallback strategies for maximum coverage.

## Features

✅ **Multi-strategy download approach:**
1. Direct PDF links (if available in metadata)
2. arXiv PDFs (fully automatic, no API key needed)
3. Unpaywall (open access papers via DOI)
4. Sci-Hub (optional fallback for paywalled papers)

✅ **Smart handling:**
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

### 1. Direct PDF Links
- **When**: Paper metadata includes a direct PDF URL
- **Success Rate**: High for arXiv, preprints
- **API Key**: None required

### 2. arXiv
- **When**: Paper has arXiv ID or arXiv DOI
- **Success Rate**: Nearly 100% for arXiv papers
- **API Key**: None required
- **Example**: Any paper with DOI starting with `10.48550/arXiv.`

### 3. Unpaywall
- **When**: Paper has a DOI and is open access
- **Success Rate**: ~30-50% depending on field
- **API Key**: Email address required (free)
- **Coverage**: Finds legal OA versions from publishers, repositories, etc.

### 4. Sci-Hub (Optional)
- **When**: Enabled and paper has DOI
- **Success Rate**: Variable (depends on Sci-Hub availability)
- **Legal Note**: Use responsibly and in accordance with local laws
- **Setup**: `pip install scihub`

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
- **Open access (Unpaywall)**: 30-50% success
- **Paywalled (with Sci-Hub)**: Variable, 50-80% success
- **Overall (OA only)**: 40-60% success
- **Overall (with Sci-Hub)**: 60-85% success

*Note: Success rates vary by research field, publication year, and publisher.*
