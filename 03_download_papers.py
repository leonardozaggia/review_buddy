"""
Download Paper PDFs

Download PDFs for papers from bibliography file using multiple strategies.

Usage:
    python 03_download_papers.py

Configuration:
    All options live in config.yaml (see config.example.yaml) under `download:`.
    API keys / emails stay in .env (see .env.example).
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

# This script's status lines use ✓/⚠/❌. On Windows stdout defaults to cp1252,
# which can't encode them - printing one raises UnicodeEncodeError and kills the
# run. Ask for UTF-8 and degrade instead of crashing if the console refuses.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.searchers.paper_downloader import PaperDownloader
from src.utils import save_failed_downloads
from src.settings import load_settings

# Load environment variables and run configuration
load_dotenv()
CONFIG = load_settings().download

# Resolve settings (bib_file: explicit if set, else auto-pick filtered > default)
if CONFIG.get("bib_file"):
    BIB_FILE = Path(CONFIG["bib_file"])
else:
    filtered = Path("results/references_filtered.bib")
    default = Path("results/references.bib")
    BIB_FILE = filtered if filtered.exists() else default

OUTPUT_DIR = Path(CONFIG.get("output_dir", "results/pdfs"))
USE_SCIHUB = CONFIG.get("use_scihub", False)
USE_ZOTERO = CONFIG.get("use_zotero", True)
MAX_WORKERS = CONFIG.get("max_workers", 4)
USE_BROWSER = CONFIG.get("use_browser", False)


def check_zotero_server():
    """
    Tell the user where the Zotero translation server stands, and offer to fix it.

    Running this step by step is the path where a fresh clone quietly gets the
    degraded resolver chain: the submodule needs a one-time setup that nothing
    else performs. It is optional (Zotero's hosted OA index needs no local
    server), so every branch here continues the run either way.

    Skipped when main.py already ran preflight, so we don't ask twice.
    """
    if os.getenv("REVIEW_BUDDY_PREFLIGHT") == "1":
        return

    from src import zotero_setup as zs

    host, port = zs.parse_host_port(os.getenv("ZOTERO_TRANSLATION_SERVER"))
    if zs.port_open(host, port):
        print(f"Zotero translation server: running ({host}:{port})")
        return

    missing = zs.setup_state()
    print("⚠ Zotero translation server is not running.")
    print()
    print("  It extracts PDF links from publisher landing pages and measurably")
    print("  improves the hit rate. Downloads still work without it — Zotero's")
    print("  hosted open-access index needs no local server — but you'll get fewer PDFs.")
    print()

    if missing:
        print(f"  It has never been set up here: {'; '.join(missing)}.")
        if not zs.node_available():
            print("  Setup needs Node.js, which isn't installed: https://nodejs.org")
            print("  Then run: python scripts/setup_zotero.py")
            print()
            print("Continuing without it...")
            print()
            return
        print("  Setup is one-time and takes a few minutes (npm install).")
        try:
            ans = input("  Run scripts/setup_zotero.py now? [y/N] ")
        except EOFError:
            ans = ""  # non-interactive (CI, piped stdin) -> never block the run
        if ans.strip().lower() not in ("y", "yes"):
            print()
            print("  Continuing without it. To enable it later:")
            for line in zs.SETUP_HINT.splitlines():
                print(f"    {line}")
            print()
            return
        if not zs.run_setup():
            print()
            print("  Setup failed — continuing without it.")
            print("  Run it manually to see why: python scripts/setup_zotero.py")
            print()
            return

    # Set up but not running (or just set up now) — offer to start it.
    if not zs.SERVER_JS.exists() or not zs.node_available():
        print("  To enable it:")
        for line in zs.SETUP_HINT.splitlines():
            print(f"    {line}")
        print()
        return

    try:
        ans = input("  Start it now (node src/server.js)? [Y/n] ")
    except EOFError:
        ans = "n"
    if ans.strip().lower() in ("", "y", "yes"):
        print("  Starting Zotero translation server...")
        if zs.start_server(host, port):
            print(f"  ✓ Running on {host}:{port}")
            print()
            return
        print("  Server did not come up in 30s — continuing without it.")
    else:
        print("  Continuing without it. Start it yourself with:")
        print("    cd vendor/translation-server && node src/server.js")
    print()


def main():
    """Main execution function"""
    print("=" * 80)
    print("REVIEW BUDDY - DOWNLOAD PAPERS")
    print("=" * 80)
    print()
    
    # Check if bibliography file exists
    if not BIB_FILE.exists():
        print(f"❌ ERROR: Bibliography file not found: {BIB_FILE}")
        print()
        print("Please run 01_fetch_metadata.py first to generate bibliography.")
        return 1
    
    # Get email from environment
    unpaywall_email = os.getenv("UNPAYWALL_EMAIL") or os.getenv("PUBMED_EMAIL")
    
    if not unpaywall_email:
        print("⚠ WARNING: No email configured!")
        print()
        print("For better download success rates, set UNPAYWALL_EMAIL in .env file.")
        print("Continuing with limited functionality...")
        print()
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Display configuration
    print(f"Input file: {BIB_FILE}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Unpaywall email: {unpaywall_email or 'Not set'}")
    print(f"Sci-Hub enabled: {USE_SCIHUB}")
    print(f"Browser fetcher enabled: {USE_BROWSER}")
    print()

    if USE_ZOTERO:
        check_zotero_server()

    # Create downloader
    print("=" * 80)
    print("STARTING DOWNLOAD...")
    print("=" * 80)
    print()
    
    downloader = PaperDownloader(
        output_dir=str(OUTPUT_DIR),
        use_scihub=USE_SCIHUB,
        unpaywall_email=unpaywall_email,
        use_zotero=USE_ZOTERO,
        zotero_url=os.getenv("ZOTERO_TRANSLATION_SERVER"),
        max_workers=MAX_WORKERS,
        use_browser=USE_BROWSER
    )
    
    # Download papers
    downloader.download_from_bib(str(BIB_FILE))
    
    # Get failed papers and save to CSV and BIB
    failed_papers = downloader.get_failed_papers()
    if failed_papers:
        print()
        print("=" * 80)
        print("SAVING FAILED DOWNLOADS...")
        print("=" * 80)
        save_failed_downloads(failed_papers, OUTPUT_DIR)
        print(f"Saved {len(failed_papers)} failed downloads to:")
        print(f"  - {OUTPUT_DIR / 'failed_downloads.csv'}")
        print(f"  - {OUTPUT_DIR / 'failed_downloads.bib'}")
    
    # Count downloaded PDFs
    pdf_count = len([f for f in OUTPUT_DIR.iterdir() if f.suffix == ".pdf"])
    
    print()
    print("=" * 80)
    print("DOWNLOAD COMPLETE!")
    print("=" * 80)
    print(f"Downloaded: {pdf_count} PDFs")
    print(f"Failed: {len(failed_papers)} papers")
    print(f"Location: {OUTPUT_DIR}")
    print(f"Log file: {OUTPUT_DIR / 'download.log'}")
    if failed_papers:
        print(f"Failed downloads list: {OUTPUT_DIR / 'failed_downloads.csv'}")
    print()
    print("Check the log file for detailed results and any errors.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())