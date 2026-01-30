"""
Institutional Login Helper

Opens a browser window for you to log into your institution's library.
The session is saved and reused for subsequent PDF downloads.

Usage:
    python 03a_institutional_login.py

After logging in, run 03_download_papers.py to download with institutional access.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))


def main():
    """Open browser for institutional login."""
    print("=" * 70)
    print("REVIEW BUDDY - INSTITUTIONAL LOGIN")
    print("=" * 70)
    print()
    print("This will open a browser where you can log into your institution's")
    print("library portal. Your session will be saved for PDF downloads.")
    print()
    print("Common login strategies:")
    print()
    print("  1. UNIVERSITY LIBRARY PORTAL")
    print("     Go to your university library homepage, click 'Login'")
    print("     Then visit a paywalled paper to authenticate")
    print()
    print("  2. PUBLISHER WEBSITES DIRECTLY")
    print("     Go to one of these and log in with your institution:")
    print("     - https://www.sciencedirect.com (Elsevier)")
    print("     - https://onlinelibrary.wiley.com (Wiley)")
    print("     - https://journals.sagepub.com (SAGE)")
    print("     - https://link.springer.com (Springer)")
    print()
    print("  3. GOOGLE SCHOLAR")
    print("     Less useful but can help with some open access papers")
    print()
    
    try:
        from src.searchers.browser_downloader import BrowserDownloader
    except ImportError:
        print("ERROR: Playwright not installed!")
        print("Run: pip install playwright && playwright install chromium")
        return 1
    
    # Ask for login URL
    print("Enter the URL to log in (press Enter for Wiley):")
    url = input("> ").strip()
    
    if not url:
        url = "https://onlinelibrary.wiley.com"
    
    print()
    print(f"Opening browser to: {url}")
    print()
    print("INSTRUCTIONS:")
    print("1. Log in with your institutional credentials")
    print("2. Navigate to a paywalled paper to verify access")
    print("3. When done, press Enter in this terminal to save session")
    print()
    print()
    
    # Create downloader with visible browser
    downloader = BrowserDownloader(
        output_dir="results/pdfs",
        headless=False  # Show the browser
    )
    
    try:
        downloader.login_interactive(url)
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    print()
    print("=" * 70)
    print("LOGIN COMPLETE!")
    print("=" * 70)
    print()
    print("Your session has been saved. Now run:")
    print("  python 03_download_papers.py")
    print()
    print("The browser will use your saved institutional credentials.")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
