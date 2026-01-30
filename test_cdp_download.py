#!/usr/bin/env python3
"""
Test CDP download with the Wiley paper that failed.

This will open the paper in your authenticated Chrome and try to download it.
"""

import sys
import time
import logging
from pathlib import Path

# Set up logging to see what's happening
logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')

# Add src to path properly
sys.path.insert(0, str(Path(__file__).parent))

from src.searchers.browser_downloader import BrowserDownloader

def test_download():
    # The Wiley paper URL from Zotero
    test_url = "https://bera-journals.onlinelibrary.wiley.com/doi/pdfdirect/10.1111/bjet.13603"
    
    output_dir = Path("test_downloads")
    output_dir.mkdir(exist_ok=True)
    
    print("="*60)
    print("Testing CDP Download")
    print("="*60)
    print(f"\nTest URL: {test_url}")
    print(f"Output: {output_dir}")
    
    # Create browser downloader
    downloader = BrowserDownloader(
        output_dir=str(output_dir),
        headless=False,  # Show what's happening
        timeout=60000
    )
    
    try:
        print(f"\n→ Connecting to Chrome via CDP...")
        if downloader._try_connect_to_chrome():
            print("✓ Connected to authenticated Chrome!")
            print(f"  Using real session: {downloader._use_real_session}")
        else:
            print("❌ Could not connect via CDP, using standalone browser")
        
        print(f"\n→ Attempting download...")
        result = downloader.download_pdf(
            url=test_url,
            filename="test_wiley_paper.pdf",
            doi="10.1111/bjet.13603"
        )
        
        if result and result.exists():
            print(f"\n✓ SUCCESS! Downloaded: {result}")
            print(f"  Size: {result.stat().st_size} bytes")
        else:
            print(f"\n❌ Download failed")
            print("\nPossible reasons:")
            print("  1. You're not logged into Wiley in the Chrome window")
            print("  2. Your institution doesn't have Wiley access")
            print("\nTo fix: In the Chrome window, navigate to:")
            print("  https://bera-journals.onlinelibrary.wiley.com")
            print("  and log in via your institution")
            
    finally:
        downloader.close()

if __name__ == "__main__":
    test_download()
