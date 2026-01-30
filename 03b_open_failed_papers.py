"""
Open Failed Papers in Browser for Manual Download

Opens each failed paper in your authenticated Chrome browser.
You can then download each PDF manually.

Usage:
    python 03b_open_failed_papers.py
"""

import subprocess
import sys
import os
import csv
import time
from pathlib import Path

def find_chrome():
    """Find Chrome executable."""
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    return None

def main():
    print("=" * 70)
    print("REVIEW BUDDY - OPEN FAILED PAPERS FOR MANUAL DOWNLOAD")
    print("=" * 70)
    print()
    
    failed_csv = Path("results/pdfs/failed_downloads.csv")
    if not failed_csv.exists():
        print("No failed downloads file found.")
        print("Run 03_download_papers.py first.")
        return 1
    
    chrome_path = find_chrome()
    if not chrome_path:
        print("Chrome not found!")
        return 1
    
    # Read failed papers
    papers = []
    with open(failed_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            doi = row.get('DOI', '').strip()
            title = row.get('Title', 'Unknown')[:60]
            if doi:
                papers.append((doi, title))
    
    print(f"Found {len(papers)} papers to download manually.")
    print()
    
    # Use the authenticated Chrome profile
    user_data_dir = Path(__file__).parent / ".browser_data_real"
    
    print("This will open each paper in your authenticated Chrome browser.")
    print("For each paper:")
    print("  1. Click the PDF/Download link")
    print("  2. Save to: results/pdfs/")
    print()
    
    input("Press Enter to start opening papers...")
    print()
    
    for i, (doi, title) in enumerate(papers, 1):
        url = f"https://doi.org/{doi}"
        print(f"[{i}/{len(papers)}] {title}...")
        print(f"   Opening: {url}")
        
        # Open in Chrome with the saved session
        subprocess.Popen([
            chrome_path,
            f"--user-data-dir={user_data_dir}",
            url
        ])
        
        if i < len(papers):
            input("   Press Enter for next paper (or Ctrl+C to stop)...")
    
    print()
    print("=" * 70)
    print("DONE!")
    print("=" * 70)
    print()
    print("After downloading, run 03_download_papers.py again")
    print("to verify all papers are downloaded.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
