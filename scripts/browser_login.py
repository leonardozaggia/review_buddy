#!/usr/bin/env python3
"""
One-time interactive login/verification for the browser-based PDF fetcher.

The browser fetcher (src/searchers/browser_fetcher.py) reuses a persistent
Camoufox (anti-detect Firefox) profile so that whatever session state you
establish here carries over to headless downloads later:
  - your institution's SSO / library proxy (EZproxy, Shibboleth, OpenAthens...)
  - a Cloudflare interactive challenge you solve once (the resulting
    cf_clearance cookie persists in this profile)

Neither Camoufox nor Playwright can solve a login form or a CAPTCHA for you -
this script just gives you a real, visible window to do it yourself, once.

IMPORTANT: this uses the SAME Camoufox profile the automated downloader reads
(DEFAULT_PROFILE_DIR). Logging in with a plain/different browser would not
help, since cookies aren't shared between browser profiles.

Usage:
    python scripts/browser_login.py
    python scripts/browser_login.py https://www.sciencedirect.com https://onlinelibrary.wiley.com

Then run 03_download_papers.py as usual with USE_BROWSER = True.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.searchers.browser_fetcher import DEFAULT_PROFILE_DIR, KNOWN_BROWSER_REQUIRED_DOMAINS


def main():
    urls = sys.argv[1:] or [f"https://{d}" for d in KNOWN_BROWSER_REQUIRED_DOMAINS]

    try:
        from camoufox.sync_api import Camoufox
        engine = "camoufox"
    except ImportError:
        engine = None
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("❌ Neither camoufox nor playwright installed. Run:")
            print("   pip install camoufox[geoip]")
            print("   python -m camoufox fetch")
            return 1
        print("⚠ camoufox not installed - falling back to plain Playwright Firefox.")
        print("  This works for login, but the resulting session may still be")
        print("  challenged later since navigator.webdriver stays visible to sites")
        print("  Cloudflare protects. Recommended: pip install camoufox[geoip] && python -m camoufox fetch")

    print("=" * 70)
    print("BROWSER LOGIN - one-time setup for the browser PDF fetcher")
    print("=" * 70)
    print(f"\nProfile directory: {DEFAULT_PROFILE_DIR.resolve()}")
    print("\nA real browser window will open. For each publisher tab:")
    print("  - log in via your institution's access point (SSO / library proxy)")
    print("  - solve any Cloudflare/CAPTCHA challenge you're shown")
    print("  - confirm you can see a 'View PDF' / 'Download PDF' link on an article")
    print("\nWhen you're done, come back to this terminal and press Enter.")
    print("=" * 70)

    DEFAULT_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    if engine == "camoufox":
        context_cm = Camoufox(persistent_context=True, user_data_dir=str(DEFAULT_PROFILE_DIR),
                              headless=False, humanize=True)
        context = context_cm.__enter__()
    else:
        pw_cm = sync_playwright()
        p = pw_cm.__enter__()
        context = p.firefox.launch_persistent_context(str(DEFAULT_PROFILE_DIR), headless=False)

    try:
        for url in urls:
            page = context.new_page()
            try:
                page.goto(url, timeout=45000)
            except Exception as e:
                print(f"  ⚠ Could not load {url}: {e}")

        input("\nPress Enter here once you've finished logging in (this closes the browser)... ")
    finally:
        # Camoufox's __exit__ closes the browser context itself; closing it
        # again here would raise on an already-closed context. For the plain
        # Playwright fallback, sync_playwright()'s cm does NOT auto-close the
        # context, so we must do it ourselves before tearing down the driver.
        if engine == "camoufox":
            context_cm.__exit__(None, None, None)
        else:
            context.close()
            pw_cm.__exit__(None, None, None)

    print(f"\n✓ Session saved to {DEFAULT_PROFILE_DIR.resolve()}")
    print("You can now run 03_download_papers.py with USE_BROWSER = True.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
