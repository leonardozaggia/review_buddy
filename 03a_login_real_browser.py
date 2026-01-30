"""
Institutional Login Using Your Real Browser

This script connects to your actual Chrome/Edge browser instead of
using Playwright's automated browser. This bypasses bot detection.

Usage:
    1. Close all Chrome/Edge windows
    2. Run this script - it will launch Chrome with debugging enabled
    3. Log in to your institution
    4. Press Enter when done
    5. Run 03_download_papers.py
"""

import subprocess
import sys
import time
import os
from pathlib import Path

def find_chrome():
    """Find Chrome or Edge executable."""
    possible_paths = [
        # Chrome
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        # Edge
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

def main():
    print("=" * 70)
    print("REVIEW BUDDY - INSTITUTIONAL LOGIN (Real Browser)")
    print("=" * 70)
    print()
    
    chrome_path = find_chrome()
    if not chrome_path:
        print("ERROR: Could not find Chrome or Edge browser!")
        print("Please install Chrome or Edge.")
        return 1
    
    browser_name = "Edge" if "edge" in chrome_path.lower() else "Chrome"
    print(f"Found {browser_name}: {chrome_path}")
    print()
    
    # User data directory for persistent sessions
    user_data_dir = Path(__file__).parent / ".browser_data_real"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    
    print("This will open your real browser where you can log into")
    print("your institution's library portal.")
    print()
    print("Suggested login URLs:")
    print("  - https://www.sciencedirect.com (Elsevier)")
    print("  - https://onlinelibrary.wiley.com (Wiley)")
    print("  - https://journals.sagepub.com (SAGE)")
    print()
    
    url = input("Enter URL to open (press Enter for Wiley): ").strip()
    if not url:
        url = "https://onlinelibrary.wiley.com"
    
    print()
    print(f"Opening {browser_name} to: {url}")
    print()
    print("INSTRUCTIONS:")
    print("1. Log in with your institutional credentials")
    print("2. Navigate to a paywalled paper and verify you can access it")
    print("3. Close the browser when done")
    print()
    
    # Launch Chrome with remote debugging
    cmd = [
        chrome_path,
        f"--user-data-dir={user_data_dir}",
        "--remote-debugging-port=9222",
        url
    ]
    
    print(f"Launching {browser_name}...")
    process = subprocess.Popen(cmd)
    
    print()
    print("Browser opened! Log in and then close the browser when done.")
    print("Waiting for browser to close...")
    
    # Wait for browser to close
    process.wait()
    
    print()
    print("=" * 70)
    print("LOGIN COMPLETE!")
    print("=" * 70)
    print()
    print("Your session has been saved to:", user_data_dir)
    print()
    print("Now update 03_download_papers.py to use the real browser session,")
    print("or try downloading papers manually from the browser.")
    print()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
