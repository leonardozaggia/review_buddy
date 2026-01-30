# Zotero Translation Server Setup

The Zotero Translation Server enhances PDF downloads by extracting metadata and discovering PDF links from academic publishers.

---

## Quick Start (After PC Restart)

If you've already set up Docker and the Zotero container:

```powershell
# 1. Start Docker Desktop (if not running)
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
# Wait ~30 seconds for Docker to fully start

# 2. Start Zotero container
docker start zotero-translation

# 3. Verify it's running
docker ps --filter "name=zotero"
# Should show: zotero-translation ... Up ...

# 4. Run your download script
python 03_download_papers.py
```

**That's it!** If you used `--restart unless-stopped` during setup, the container auto-starts with Docker.

---

## First-Time Setup (Windows AMD64/x64)

> **Note**: The official `zotero/translation-server` image only supports ARM64. On Windows/Intel, you must build from source.

### Step 1: Install Docker Desktop

1. Download from https://www.docker.com/products/docker-desktop
2. Run installer, **select WSL 2 backend** (recommended)
3. Restart PC when prompted
4. Launch Docker Desktop and wait for it to fully start (~30 seconds)

### Step 2: Clone Zotero Server

```powershell
# Navigate to your projects folder (adjust path as needed)
cd C:\Users\YOUR_USERNAME\Projects

# Clone with submodules - THIS IS IMPORTANT!
git clone --recurse-submodules https://github.com/zotero/translation-server.git

cd translation-server
```

### Step 3: Create Custom Dockerfile

Create a file named `Dockerfile.local` in the translation-server folder:

```dockerfile
FROM node:lts

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install --legacy-peer-deps

# Copy source code
COPY . .

# Clone translators (excluded by .dockerignore)
RUN git clone --depth 1 https://github.com/zotero/translators.git modules/translators

EXPOSE 1969

CMD ["node", "src/server.js"]
```

### Step 4: Build and Run

```powershell
# Build the image (takes 2-3 minutes)
docker build -f Dockerfile.local -t zotero-local .

# Run with auto-restart enabled
docker run -d -p 1969:1969 --restart unless-stopped --name zotero-translation zotero-local

# Verify it's working
curl http://localhost:1969
# Should return: "Zotero Translation Server is Running"
```

### Step 5: Test Integration

```powershell
cd C:\Users\YOUR_USERNAME\Projects\review_buddy

# Quick test
python -c "from src.searchers.zotero_client import ZoteroTranslationClient; z = ZoteroTranslationClient(); print('Available:', z.is_available())"
# Should print: Available: True

# Run download script
python 03_download_papers.py
```

---

## Container Management

```powershell
# Check status
docker ps --filter "name=zotero"

# Stop
docker stop zotero-translation

# Start
docker start zotero-translation

# View logs
docker logs zotero-translation

# Remove completely (to recreate)
docker rm -f zotero-translation
```

---

## Configuration

In `03_download_papers.py`:

```python
USE_ZOTERO = True   # Enable/disable
ZOTERO_SERVER_URL = "http://localhost:1969"
```

Or in `.env`:

```bash
ZOTERO_SERVER_URL=http://localhost:1969
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Cannot connect to Docker" | Start Docker Desktop and wait 30 seconds |
| Container not found | Run `docker ps -a` to check, then `docker start zotero-translation` |
| Port 1969 in use | `docker rm -f zotero-translation` then recreate |
| Server not responding | Check logs: `docker logs zotero-translation` |
| ARM64 platform error | You need to build from source (see Step 3 above) |

---

## What Zotero Does

- Extracts metadata from DOIs, PMIDs, arXiv IDs
- Resolves DOIs to canonical publisher URLs
- Constructs PDF URLs for open access journals
- Supports 600+ academic sources

### Why Zotero Desktop Downloads More Papers

The Zotero Desktop app can download more papers than this script because:

1. **Browser Integration**: Desktop app runs in your browser with your cookies/sessions
2. **Institutional Access**: If you're logged into your university, Zotero inherits that access
3. **Interactive Auth**: Desktop can prompt for login when needed

The Translation Server is headless - it only extracts metadata and constructs URLs, but can't authenticate to paywalled publishers.

### Recommended Workflow

For maximum downloads:

1. **Run Review Buddy first** - downloads all freely available papers
2. **Import `failed_downloads.bib` into Zotero Desktop** - it will download the rest using your institutional access
3. **Export PDFs from Zotero** to your results folder

This hybrid approach gets you the best of both worlds.
