"""
Download Papers Using Authenticated Chrome Session

This script uses your real Chrome browser (with your institutional login)
to download papers. It opens Chrome with your saved session and automates
the download process.

Usage:
    1. First run: python 03a_login_real_browser.py (to log in)
    2. Then run: python 03c_download_with_chrome.py
"""

import subprocess
import sys
import os
import csv
import time
import shutil
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

def get_failed_papers():
    """Read the list of failed papers."""
    failed_csv = Path("results/pdfs/failed_downloads.csv")
    if not failed_csv.exists():
        return []
    
    papers = []
    with open(failed_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            doi = row.get('DOI', '').strip()
            title = row.get('Title', 'Unknown')[:60]
            if doi:
                papers.append({
                    'doi': doi,
                    'title': title,
                    'filename': doi.replace('/', '_').replace('.', '_') + '.pdf'
                })
    return papers

def main():
    print("=" * 70)
    print("REVIEW BUDDY - DOWNLOAD WITH AUTHENTICATED CHROME")
    print("=" * 70)
    print()
    
    chrome_path = find_chrome()
    if not chrome_path:
        print("ERROR: Chrome not found!")
        return 1
    
    papers = get_failed_papers()
    if not papers:
        print("No failed papers to download.")
        print("Run 03_download_papers.py first.")
        return 0
    
    print(f"Found {len(papers)} papers to download.")
    print()
    
    # Check for authenticated session
    user_data_dir = Path(__file__).parent / ".browser_data_real"
    if not user_data_dir.exists():
        print("ERROR: No authenticated browser session found!")
        print("First run: python 03a_login_real_browser.py")
        return 1
    
    output_dir = Path("results/pdfs")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Set Chrome download directory
    downloads_dir = Path.home() / "Downloads"
    
    print("INSTRUCTIONS:")
    print("1. Chrome will open with your institutional login")
    print("2. For each paper, click 'Download PDF' or 'PDF' link")
    print(f"3. PDFs will download to: {downloads_dir}")
    print()
    print("After downloading, I'll help you move them to results/pdfs/")
    print()
    
    input("Press Enter to start...")
    print()
    
    # Track which papers to download
    downloaded = []
    
    for i, paper in enumerate(papers, 1):
        doi = paper['doi']
        title = paper['title']
        filename = paper['filename']
        
        # Skip if already downloaded
        if (output_dir / filename).exists():
            print(f"[{i}/{len(papers)}] SKIP (already exists): {title}")
            continue
        
        url = f"https://doi.org/{doi}"
        print(f"\n[{i}/{len(papers)}] {title}")
        print(f"   DOI: {doi}")
        print(f"   Opening: {url}")
        
        # Open in authenticated Chrome
        subprocess.Popen([
            chrome_path,
            f"--user-data-dir={user_data_dir}",
            url
        ])
        
        print()
        print("   → Download the PDF, then:")
        choice = input("   Press Enter for next, 's' to skip rest, 'q' to quit: ").strip().lower()
        
        if choice == 'q':
            break
        elif choice == 's':
            break
    
    print()
    print("=" * 70)
    print("MOVING DOWNLOADED PDFS")
    print("=" * 70)
    print()
    
    # Look for newly downloaded PDFs
    pdf_files = list(downloads_dir.glob("*.pdf"))
    recent_pdfs = [f for f in pdf_files if (time.time() - f.stat().st_mtime) < 3600]  # Last hour
    
    if recent_pdfs:
        print(f"Found {len(recent_pdfs)} recent PDF(s) in Downloads:")
        for pdf in recent_pdfs:
            print(f"  - {pdf.name}")
        
        print()
        move = input("Move these to results/pdfs/? (y/n): ").strip().lower()
        
        if move == 'y':
            for pdf in recent_pdfs:
                dest = output_dir / pdf.name
                if not dest.exists():
                    shutil.move(str(pdf), str(dest))
                    print(f"  Moved: {pdf.name}")
                else:
                    print(f"  Skipped (exists): {pdf.name}")
    else:
        print("No recent PDFs found in Downloads folder.")
        print("If you downloaded PDFs, move them manually to results/pdfs/")
    
    print()
    print("=" * 70)
    print("DONE!")
    print("=" * 70)
    print()
    print("Run 'python 03_download_papers.py' again to check status.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
