#!/usr/bin/env python3
"""
Set up the vendored Zotero translation server (primary PDF fetcher).

Steps:
  1. Initialise the git submodule at vendor/translation-server (+ its own submodules)
  2. npm install
  3. Apply the review_buddy patch that exposes translator PDF links
     (upstream's /web endpoint drops the `attachments` field)

Idempotent: re-running skips steps already done.

After this, start the server with:
    cd vendor/translation-server && node src/server.js

Requires: git and Node.js (npm) on PATH.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TS_DIR = ROOT / "vendor" / "translation-server"
PATCH = ROOT / "vendor" / "patches" / "expose-attachments.patch"
PATCH_MARKER = "review_buddy patch"
PATCHED_FILE = TS_DIR / "src" / "webSession.js"


def run(cmd, cwd=None):
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    print("=" * 70)
    print("REVIEW BUDDY - ZOTERO TRANSLATION SERVER SETUP")
    print("=" * 70)

    # 1. Submodule init
    if not (TS_DIR / "package.json").exists():
        print("\n[1/3] Initialising translation-server submodule...")
        run(["git", "submodule", "update", "--init", "--recursive"], cwd=ROOT)
    else:
        print("\n[1/3] Submodule already present - skipping init.")

    if not (TS_DIR / "package.json").exists():
        print("\n❌ Submodule not found after init. Is this a git checkout with submodules?")
        return 1

    # 2. npm install
    if not (TS_DIR / "node_modules").exists():
        print("\n[2/3] Installing Node dependencies (this can take a few minutes)...")
        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        run([npm, "install", "--no-audit", "--no-fund"], cwd=TS_DIR)
    else:
        print("\n[2/3] node_modules already present - skipping npm install.")

    # 3. Apply the attachments patch (idempotent)
    print("\n[3/3] Applying attachments patch...")
    text = PATCHED_FILE.read_text(encoding="utf-8") if PATCHED_FILE.exists() else ""
    if PATCH_MARKER in text:
        print("      Patch already applied - skipping.")
    else:
        run(["git", "apply", str(PATCH)], cwd=TS_DIR)
        print("      ✓ Patch applied.")

    print("\n" + "=" * 70)
    print("✓ Setup complete. Start the server with:")
    print("    cd vendor/translation-server && node src/server.js")
    print("Then run: python 03_download_papers.py")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
