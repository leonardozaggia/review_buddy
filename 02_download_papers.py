"""
Download Paper PDFs

Download PDFs for papers from bibliography file using multiple strategies.

Usage:
    python 02_download_papers.py

Configuration:
    Set UNPAYWALL_EMAIL in .env file (see .env.example)
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.searchers.paper_downloader import PaperDownloader

# Load environment variables
load_dotenv()

# Configuration
BIB_FILE = Path("results/references.bib")
OUTPUT_DIR = Path("results/pdfs")
USE_SCIHUB = False  # Set to True to enable Sci-Hub fallback (use responsibly)

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
    print()
    
    # Create downloader
    print("=" * 80)
    print("STARTING DOWNLOAD...")
    print("=" * 80)
    print()
    
    downloader = PaperDownloader(
        output_dir=str(OUTPUT_DIR),
        use_scihub=USE_SCIHUB,
        unpaywall_email=unpaywall_email
    )
    
    # Download papers
    downloader.download_from_bib(str(BIB_FILE))
    
    # Count downloaded PDFs
    pdf_count = len([f for f in OUTPUT_DIR.iterdir() if f.suffix == ".pdf"])
    
    print()
    print("=" * 80)
    print("DOWNLOAD COMPLETE!")
    print("=" * 80)
    print(f"Downloaded: {pdf_count} PDFs")
    print(f"Location: {OUTPUT_DIR}")
    print(f"Log file: {OUTPUT_DIR / 'download.log'}")
    print()
    print("Check the log file for detailed results and any errors.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())