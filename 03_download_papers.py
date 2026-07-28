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