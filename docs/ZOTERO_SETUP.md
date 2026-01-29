# Zotero Translation Server Setup Guide

## Overview

The Zotero Translation Server is an optional enhancement for Review Buddy's paper download functionality. It leverages Zotero's extensive library of web translators to extract metadata and discover PDF links from various academic sources.

## What It Does

When enabled, Review Buddy uses Zotero Translation Server to:

1. **Extract metadata** from DOIs, PMIDs, arXiv IDs, and paper URLs
2. **Discover PDF links** that may not be found through other methods
3. **Enrich paper information** from publisher websites

The Zotero translators support hundreds of academic publishers and databases, including:
- Major publishers (Elsevier, Springer, Wiley, Nature, etc.)
- Databases (PubMed, Scopus, Web of Science)
- Preprint servers (arXiv, bioRxiv, SSRN)
- Institutional repositories
- And many more

## Installation

### Option 1: Docker (Recommended)

The easiest way to run the Zotero Translation Server is using Docker:

```bash
# Pull and run the container
docker run -d -p 1969:1969 --name zotero-translation zotero/translation-server

# Verify it's running
curl http://localhost:1969
# Should return "Zotero Translation Server is running"
```

To stop the server:
```bash
docker stop zotero-translation
```

To start it again:
```bash
docker start zotero-translation
```

To remove the container:
```bash
docker rm zotero-translation
```

### Option 2: Docker Compose

If you prefer Docker Compose, add this to your `docker-compose.yml`:

```yaml
version: '3'
services:
  zotero-translation:
    image: zotero/translation-server
    ports:
      - "1969:1969"
    restart: unless-stopped
```

Then run:
```bash
docker-compose up -d
```

### Option 3: Node.js (Manual Installation)

If you prefer to run it directly with Node.js:

```bash
# Clone the repository
git clone https://github.com/zotero/translation-server.git
cd translation-server

# Install dependencies
npm install

# Start the server
npm start
```

The server will run on `http://localhost:1969` by default.

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Zotero Translation Server URL (optional, defaults to localhost:1969)
ZOTERO_SERVER_URL=http://localhost:1969

# Enable/disable Zotero integration (optional, defaults to true)
ZOTERO_ENABLED=true

# Request timeout in seconds (optional, defaults to 30)
ZOTERO_TIMEOUT=30
```

### Script Configuration

In `03_download_papers.py`, you can also configure directly:

```python
USE_ZOTERO = True  # Set to False to disable
ZOTERO_SERVER_URL = os.getenv("ZOTERO_SERVER_URL", "http://localhost:1969")
```

## Usage

### Automatic Usage

When the Zotero Translation Server is running, Review Buddy automatically uses it as a fallback method during PDF downloads:

```bash
# Start Zotero server (if using Docker)
docker start zotero-translation

# Run the download script
python 03_download_papers.py
```

The logs will show when Zotero is being used:
```
[INFO] Zotero Translation Server available at http://localhost:1969
...
[INFO]   → Trying Zotero Translation Server...
[INFO]   → Found via Zotero: https://example.com/paper.pdf
[INFO]   ✓ SUCCESS via Zotero Translation Server
```

### Manual Testing

You can test the Zotero client directly:

```python
from src.searchers.zotero_client import ZoteroTranslationClient

client = ZoteroTranslationClient()

# Check if server is available
if client.is_available():
    print("Server is running!")
    
    # Test with a DOI
    metadata = client.translate_identifier("10.1371/journal.pone.0123456", "doi")
    if metadata:
        print(f"Title: {metadata.get('title')}")
        
        # Check for PDF attachment
        pdf_url = client.extract_pdf_url(metadata)
        if pdf_url:
            print(f"PDF URL: {pdf_url}")
else:
    print("Server not available")
```

## Download Priority

With Zotero enabled, the download order is:

1. **Direct PDF links** (if URL ends with .pdf)
2. **Zotero Translation Server** ← NEW
3. arXiv
4. bioRxiv/medRxiv
5. Unpaywall
6. Crossref API
7. PubMed Central
8. Publisher-specific patterns
9. ResearchGate/Academia.edu
10. HTML scraping
11. Sci-Hub (optional)

Zotero is positioned early in the fallback chain because it can often find PDFs that would otherwise require more complex scraping.

## Troubleshooting

### Server Not Available

If you see this warning:
```
[WARNING] Zotero Translation Server not available at http://localhost:1969
```

1. **Check if Docker is running:**
   ```bash
   docker ps | grep zotero
   ```

2. **Start the container:**
   ```bash
   docker start zotero-translation
   # Or if it doesn't exist:
   docker run -d -p 1969:1969 --name zotero-translation zotero/translation-server
   ```

3. **Verify the server is responding:**
   ```bash
   curl http://localhost:1969
   ```

### Connection Errors

If you're running the server on a different host or port:

1. Update your `.env` file:
   ```bash
   ZOTERO_SERVER_URL=http://your-server:1969
   ```

2. Ensure the port is accessible (firewall rules, etc.)

### Slow Translations

Some publishers may take longer to translate. The default timeout is 30 seconds. You can increase it:

```bash
ZOTERO_TIMEOUT=60
```

### No PDF Found

Even when Zotero successfully translates a page, it may not find a PDF if:
- The paper is paywalled
- The translator doesn't support PDF extraction for that publisher
- The PDF link is dynamically generated

This is normal - the download will continue to the next fallback method.

## Performance Considerations

- **First request may be slow**: The server needs to warm up
- **Rate limiting**: Some publishers may rate limit requests
- **Memory usage**: The Docker container uses about 200-400MB of RAM

## Disabling Zotero

If you want to disable Zotero without stopping the server:

1. **In `.env`:**
   ```bash
   ZOTERO_ENABLED=false
   ```

2. **In `03_download_papers.py`:**
   ```python
   USE_ZOTERO = False
   ```

3. **In code:**
   ```python
   downloader = PaperDownloader(
       output_dir="results/pdfs",
       use_zotero=False
   )
   ```

## API Reference

### Zotero Translation Server Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/web` | POST | Translate a URL |
| `/search` | POST | Translate an identifier (DOI, PMID, etc.) |
| `/export` | POST | Convert metadata to different formats |

### ZoteroTranslationClient Methods

| Method | Description |
|--------|-------------|
| `is_available()` | Check if server is running |
| `translate_url(url)` | Extract metadata from URL |
| `translate_identifier(id, type)` | Extract metadata from DOI/PMID/etc. |
| `extract_pdf_url(metadata)` | Get PDF URL from metadata |
| `batch_translate(items)` | Process multiple items |

## Further Reading

- [Zotero Translation Server GitHub](https://github.com/zotero/translation-server)
- [Zotero Translators](https://www.zotero.org/support/translators)
- [Review Buddy Downloader Guide](DOWNLOADER_GUIDE.md)
