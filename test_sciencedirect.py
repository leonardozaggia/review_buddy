#!/usr/bin/env python3
"""Test downloading a ScienceDirect paper via CDP."""

import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.DEBUG, format='[%(levelname)s] %(message)s')

sys.path.insert(0, str(Path(__file__).parent))

from src.searchers.browser_downloader import BrowserDownloader

def test_sciencedirect():
    # Test with an Elsevier paper that we have access to
    doi = "10.1016/j.cognition.2025.106088"
    url = f"https://doi.org/{doi}"
    
    output_dir = Path("test_downloads")
    output_dir.mkdir(exist_ok=True)
    
    print("="*60)
    print("Testing ScienceDirect Download")
    print("="*60)
    print(f"DOI: {doi}")
    print(f"URL: {url}")
    
    downloader = BrowserDownloader(
        output_dir=str(output_dir),
        headless=False,
        timeout=60000
    )
    
    try:
        print("\n→ Connecting to Chrome via CDP...")
        downloader._ensure_browser()
        
        if downloader._use_real_session:
            print("✓ Connected to authenticated Chrome!")
        else:
            print("⚠ Using standalone browser (not CDP)")
        
        print(f"\n→ Attempting download...")
        result = downloader.download_pdf(
            url=url,
            filename="test_sciencedirect.pdf",
            doi=doi
        )
        
        if result and result.exists():
            print(f"\n✓ SUCCESS! Downloaded: {result}")
            print(f"  Size: {result.stat().st_size} bytes")
        else:
            print(f"\n❌ Download failed")
            
    finally:
        downloader.close()

if __name__ == "__main__":
    test_sciencedirect()
