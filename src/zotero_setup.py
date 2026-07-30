"""
Shared preflight for the vendored Zotero translation server.

main.py and 03_download_papers.py both need to answer the same two questions
before a download run, so the checks live here rather than in each caller:

  1. Is the local checkout set up?   submodule init + npm install + our patch
     -> fixed by  python scripts/setup_zotero.py   (one-time, needs git + Node)
  2. Is the server actually up?      listening on port 1969
     -> fixed by  node src/server.js  (main.py and 03 can spawn this for you)

Neither is fatal. The resolver chain still uses Zotero's *hosted* open-access
index, which needs no local server at all. What a missing server costs you is
the site-specific translator step - the part that extracts PDF links from
publisher landing pages - so it is worth telling the user exactly what to run
instead of silently degrading.

See docs/ZOTERO_HOW_IT_WORKS.md for why the translator step matters.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TS_DIR = ROOT / "vendor" / "translation-server"
SETUP_SCRIPT = ROOT / "scripts" / "setup_zotero.py"
SERVER_JS = TS_DIR / "src" / "server.js"

# Written into webSession.js by vendor/patches/expose-attachments.patch.
# Must stay in sync with scripts/setup_zotero.py.
PATCH_MARKER = "review_buddy patch"
_PATCHED_FILE = TS_DIR / "src" / "webSession.js"

DEFAULT_URL = "http://127.0.0.1:1969"

SETUP_HINT = (
    "python scripts/setup_zotero.py   (one-time: submodule, npm install, patch)\n"
    "cd vendor/translation-server && node src/server.js"
)


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------

def parse_host_port(url, default=("127.0.0.1", 1969)):
    """Pull (host, port) out of a server URL, falling back to `default`."""
    host, port = default
    if not url:
        return host, port
    rest = url.split("://", 1)[1] if "://" in url else url
    authority = rest.split("/", 1)[0]
    if ":" in authority:
        host_part, _, port_part = authority.partition(":")
        host = host_part or host
        try:
            port = int(port_part)
        except ValueError:
            pass
    elif authority:
        host = authority
    return host, port


def port_open(host, port, timeout=2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def setup_state():
    """
    What's missing from the local translation-server checkout.

    Returns a list of human-readable missing pieces; empty means ready to start.
    """
    if not (TS_DIR / "package.json").exists():
        # A plain `git clone` without --recursive lands here.
        return ["submodule not initialised — vendor/translation-server is empty"]

    missing = []
    if not (TS_DIR / "node_modules").exists():
        missing.append("Node dependencies not installed")
    try:
        patched = PATCH_MARKER in _PATCHED_FILE.read_text(encoding="utf-8")
    except OSError:
        patched = False
    if not patched:
        missing.append("attachments patch not applied")
    return missing


def is_set_up() -> bool:
    return not setup_state()


def node_available() -> bool:
    import shutil
    return shutil.which("node") is not None


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def run_setup() -> bool:
    """Run scripts/setup_zotero.py to completion. True if it succeeded."""
    if not SETUP_SCRIPT.exists():
        return False
    rc = subprocess.run([sys.executable, str(SETUP_SCRIPT)], cwd=str(ROOT)).returncode
    return rc == 0


def start_server(host="127.0.0.1", port=1969, wait=30) -> bool:
    """
    Spawn `node src/server.js` detached and wait for the port to open.

    Returns False if node/server.js are missing, the spawn failed, or the
    server didn't come up within `wait` seconds.
    """
    if not SERVER_JS.exists() or not node_available():
        return False
    import shutil
    try:
        subprocess.Popen(
            [shutil.which("node"), str(SERVER_JS)],
            cwd=str(SERVER_JS.parent.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    for _ in range(wait):
        if port_open(host, port):
            return True
        time.sleep(1)
    return False
