#!/usr/bin/env python3
"""
Test CDP connection to Chrome.

First, start Chrome with debugging:
  chrome.exe --remote-debugging-port=9222 --user-data-dir=".browser_data_real"

Then run this script to test the connection.
"""

import socket
import sys

def check_chrome_debugging():
    """Check if Chrome is listening on debugging port."""
    port = 9222
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"Error checking port: {e}")
        return False

def test_cdp_connection():
    """Test connecting to Chrome via CDP."""
    if not check_chrome_debugging():
        print("❌ Chrome is not running with debugging port 9222")
        print("\nTo start Chrome with debugging, run:")
        print('  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --user-data-dir=".browser_data_real"')
        return False
    
    print("✓ Chrome is listening on port 9222")
    
    try:
        from playwright.sync_api import sync_playwright
        
        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            contexts = browser.contexts
            
            if contexts:
                print(f"✓ Connected to Chrome with {len(contexts)} context(s)")
                
                # Check for pages/tabs
                context = contexts[0]
                pages = context.pages
                print(f"  Found {len(pages)} tab(s)")
                
                for i, page in enumerate(pages):
                    print(f"    Tab {i+1}: {page.url[:60]}...")
                
                # Test creating a new page
                print("\n  Testing page creation...")
                test_page = context.new_page()
                test_page.goto("https://www.google.com", timeout=10000)
                print(f"  ✓ Created test page: {test_page.url}")
                test_page.close()
                
                print("\n✓ CDP connection working!")
                print("  Downloads will use your authenticated Chrome session.")
                return True
            else:
                print("❌ Connected but no browser context found")
                return False
                
        finally:
            playwright.stop()
            
    except Exception as e:
        print(f"❌ Error connecting via CDP: {e}")
        return False

if __name__ == "__main__":
    success = test_cdp_connection()
    sys.exit(0 if success else 1)
