#!/usr/bin/env python3
"""
Review Buddy — the whole pipeline in one command.

Runs the three steps end to end, reading everything from config.yaml:

    01  fetch metadata   →   02  filter abstracts   →   03  download PDFs

Before running, it preflight-checks every dependency each enabled step needs,
auto-starts the services it can (the Zotero translation server, and Ollama for
the AI filter — including pulling the model), and prints an exact fix when
something is genuinely missing instead of failing with a stack trace.

Usage:
    python main.py                  # keyword filter (fast, no LLM)  [default]
    python main.py --ai             # LLM filter via local Ollama (starts it and pulls the model)
    python main.py --skip-download  # stop after filtering
    python main.py --config my.yaml # use a different config file
    python main.py --yes            # don't prompt (e.g. auto-pull the Ollama model)

Recommended environment: the `autosearch` conda env. If you launch this from a
different env that's missing dependencies, main.py will try to re-exec itself
with `autosearch` automatically.
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREFERRED_ENV = "autosearch"

# Line-buffer our own stdout so main.py's banners/summary interleave correctly
# with the (unbuffered) subprocess step output instead of all flushing at exit.
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

# Modules main.py itself needs before it can even load config. Kept to the ones
# imported transitively by src.settings + the step scripts' shared code.
_CORE_MODULES = ["yaml", "requests", "bs4", "pandas", "bibtexparser", "dotenv"]


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def c(text: str, color: str) -> str:
    """Best-effort ANSI color (no-op if the terminal doesn't support it)."""
    codes = {"red": "91", "green": "92", "yellow": "93", "blue": "94",
             "bold": "1", "dim": "2"}
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return text
    return f"\033[{codes.get(color, '0')}m{text}\033[0m"


def hr(title: str = ""):
    line = "=" * 78
    print(line)
    if title:
        print(title)
        print(line)


def module_missing(names):
    """Return the subset of `names` not importable in this interpreter."""
    import importlib.util
    return [n for n in names if importlib.util.find_spec(n) is None]


def port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        import requests
        requests.get(url, timeout=timeout)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Environment auto-selection: re-exec under a conda env that has the deps
# ---------------------------------------------------------------------------

def _conda_root() -> Path:
    """Best-effort path to the conda installation root."""
    exe = Path(sys.executable)
    parts = exe.parts
    if "envs" in parts:
        # .../<root>/envs/<name>/python(.exe)
        return Path(*parts[: parts.index("envs")])
    return exe.parent  # base env: python(.exe) sits in the root


def _env_python(env_name: str) -> Path:
    root = _conda_root()
    if os.name == "nt":
        return root / "envs" / env_name / "python.exe"
    return root / "envs" / env_name / "bin" / "python"


def maybe_reexec_into_env():
    """
    If core deps are missing here but the preferred conda env has them,
    re-launch this script with that env's interpreter. Guarded against loops.
    """
    if not module_missing(_CORE_MODULES):
        return  # current interpreter is fine
    if os.environ.get("REVIEW_BUDDY_REEXEC") == "1":
        return  # already tried once; fall through to the normal error path

    candidate = _env_python(PREFERRED_ENV)
    if candidate.exists() and candidate.resolve() != Path(sys.executable).resolve():
        print(c(f"→ Missing deps in this interpreter; switching to conda env "
                f"'{PREFERRED_ENV}'...", "yellow"))
        env = dict(os.environ, REVIEW_BUDDY_REEXEC="1")
        try:
            os.execve(str(candidate), [str(candidate), str(ROOT / "main.py"), *sys.argv[1:]], env)
        except OSError as e:
            print(c(f"  Could not switch env automatically ({e}).", "red"))


# ---------------------------------------------------------------------------
# Preflight: services and per-step dependencies
# ---------------------------------------------------------------------------

class Preflight:
    """Collects problems; hard failures block the run, warnings don't."""

    def __init__(self):
        self.errors = []    # (what, how_to_fix)
        self.warnings = []

    def error(self, what, fix):
        self.errors.append((what, fix))
        print(c(f"  ✗ {what}", "red"))
        for line in fix.splitlines():
            print(f"      {line}")

    def warn(self, what, note=""):
        self.warnings.append((what, note))
        print(c(f"  ⚠ {what}", "yellow"))
        if note:
            for line in note.splitlines():
                print(f"      {line}")

    def ok(self, what):
        print(c(f"  ✓ {what}", "green"))

    @property
    def blocked(self) -> bool:
        return bool(self.errors)


def ensure_zotero_server(pf: Preflight, url: str) -> bool:
    """Ensure the Zotero translation server is reachable; try to start it."""
    host, port = "127.0.0.1", 1969
    if "://" in url:
        rest = url.split("://", 1)[1]
        host = rest.split(":")[0].split("/")[0]
        if ":" in rest:
            try:
                port = int(rest.split(":", 1)[1].split("/")[0])
            except ValueError:
                pass

    if port_open(host, port):
        pf.ok(f"Zotero translation server ({host}:{port})")
        return True

    server_js = ROOT / "vendor" / "translation-server" / "src" / "server.js"
    node = shutil.which("node")
    if server_js.exists() and node:
        print(f"      starting Zotero translation server (node)...")
        try:
            subprocess.Popen(
                [node, str(server_js)],
                cwd=str(server_js.parent.parent),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError as e:
            pf.warn(f"Could not launch Zotero server ({e})", "Falling back to the OA index only.")
            return False
        for _ in range(30):
            if port_open(host, port):
                pf.ok(f"Zotero translation server started ({host}:{port})")
                return True
            time.sleep(1)
        pf.warn("Zotero server did not come up in 30s", "Continuing with the OA index only.")
        return False

    pf.warn(
        "Zotero translation server not running",
        "PDF finding still works via Zotero's open-access index, but the\n"
        "site-specific translators won't. To enable them:\n"
        "  python scripts/setup_zotero.py   (once)\n"
        "  cd vendor/translation-server && node src/server.js",
    )
    return False


def ensure_ollama(pf: Preflight, model: str, url: str, assume_yes: bool) -> bool:
    """Ensure Ollama is serving and the model is present; start/pull as needed."""
    if shutil.which("ollama") is None:
        pf.error("Ollama is not installed (needed for --ai)",
                 "Install it from https://ollama.com, then re-run.")
        return False

    tags_url = url.rstrip("/") + "/api/tags"
    if not http_ok(tags_url):
        print("      starting Ollama server (ollama serve)...")
        try:
            subprocess.Popen(["ollama", "serve"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            pf.error(f"Could not start Ollama ({e})", "Start it manually: ollama serve")
            return False
        for _ in range(20):
            if http_ok(tags_url):
                break
            time.sleep(1)
        if not http_ok(tags_url):
            pf.error("Ollama server did not become reachable", "Start it manually: ollama serve")
            return False

    # Is the model pulled?
    try:
        import requests
        tags = requests.get(tags_url, timeout=5).json()
        have = {m.get("name", "") for m in tags.get("models", [])}
    except Exception:
        have = set()
    # Ollama reports names like "llama3.1:8b"; also match the bare family
    if model in have or any(h.split(":")[0] == model.split(":")[0] for h in have):
        pf.ok(f"Ollama serving, model '{model}' available")
        return True

    size_note = "(~4.7 GB for llama3.1:8b, one-time)"
    if not assume_yes:
        try:
            ans = input(c(f"  ? Model '{model}' not pulled. Download it now {size_note}? [y/N] ", "yellow"))
        except EOFError:
            ans = ""  # non-interactive stdin -> don't pull; show the fix instead
        if ans.strip().lower() not in ("y", "yes"):
            pf.error(f"Model '{model}' not available",
                     f"Pull it when ready:  ollama pull {model}\n"
                     f"(or re-run with --yes to pull automatically)")
            return False
    print(f"      pulling {model} {size_note} — this can take a while...")
    rc = subprocess.run(["ollama", "pull", model]).returncode
    if rc != 0:
        pf.error(f"Failed to pull '{model}'", f"Try manually:  ollama pull {model}")
        return False
    pf.ok(f"Ollama serving, model '{model}' pulled")
    return True


def ensure_browser(pf: Preflight):
    """Check the Camoufox browser fetcher can run (only if use_browser)."""
    if module_missing(["camoufox"]):
        pf.warn("camoufox not installed (browser fetcher disabled)",
                "Cloudflare-protected publishers (Elsevier, Wiley, MDPI) will be skipped.\n"
                "Enable with:  pip install camoufox[geoip] && python -m camoufox fetch")
        return
    # Is the patched Firefox binary actually fetched?
    try:
        from camoufox.pkgman import get_path  # type: ignore
        get_path("firefox") if False else None  # API varies; fall through to a soft check
    except Exception:
        pass
    profile = ROOT / ".browser_profile"
    if not profile.exists():
        pf.warn("No .browser_profile yet",
                "For subscription publishers, log in once so the session is seasoned:\n"
                "  python scripts/browser_login.py")
        return

    # A locked profile makes every browser launch hang then give up (a Firefox
    # profile can only be opened by one process). Catch it before a whole run
    # is wasted on it.
    if (profile / "parent.lock").exists() and _camoufox_running():
        pf.warn("Browser profile appears to be in use (.browser_profile locked)",
                "Close any open browser_login.py / Camoufox window before running,\n"
                "otherwise the downloader's browser fetcher can't open the profile.\n"
                "If nothing is open, the lock is stale - it will be ignored once no\n"
                "'camoufox' process is running.")
    else:
        pf.ok("Camoufox browser fetcher ready")


def _camoufox_running() -> bool:
    """Best-effort check for a live camoufox/firefox process holding the profile."""
    try:
        if os.name == "nt":
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq camoufox.exe"],
                                 capture_output=True, text=True, timeout=8).stdout.lower()
            return "camoufox" in out
        out = subprocess.run(["pgrep", "-fi", "camoufox"], capture_output=True, text=True,
                             timeout=8).stdout
        return bool(out.strip())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Running the steps
# ---------------------------------------------------------------------------

def run_step(script: str, label: str, extra_env=None) -> tuple:
    """Run a pipeline script as a subprocess; return (returncode, seconds)."""
    hr(c(f"▶ {label}", "bold"))
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    start = time.monotonic()
    rc = subprocess.run([sys.executable, str(ROOT / script)], cwd=str(ROOT), env=env).returncode
    elapsed = time.monotonic() - start
    status = c("done", "green") if rc == 0 else c(f"FAILED (exit {rc})", "red")
    print(c(f"⏱ {label}: {elapsed:.0f}s — {status}", "dim"))
    return rc, elapsed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Review Buddy end-to-end pipeline")
    parser.add_argument("--ai", action="store_true",
                        help="use the LLM (Ollama) abstract filter instead of the keyword filter")
    parser.add_argument("--skip-download", action="store_true", help="stop after filtering")
    parser.add_argument("--config", default=None, help="path to a config file (default: config.yaml)")
    parser.add_argument("--yes", action="store_true", help="assume 'yes' to prompts (e.g. model pull)")
    args = parser.parse_args()

    # Load .env so preflight sees the same API keys the step scripts will.
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass

    # If config was given, make the step scripts see it too.
    if args.config:
        os.environ["REVIEW_BUDDY_CONFIG"] = args.config

    from src.settings import load_settings
    settings = load_settings(Path(args.config) if args.config else None)

    hr(c("REVIEW BUDDY — full pipeline", "bold"))
    sources = settings.search.get("sources", [])
    query_oneline = " ".join(settings.resolve_query().split())
    print(f"  Query:   {query_oneline[:70]}...")
    print(f"  Sources: {', '.join(sources)}")
    print(f"  Filter:  {'AI (Ollama)' if args.ai else 'keyword'}")
    print(f"  Download: {'yes' if not args.skip_download else 'skipped'}  "
          f"(browser={settings.download.get('use_browser')}, "
          f"zotero={settings.download.get('use_zotero')}, "
          f"workers={settings.download.get('max_workers')})")
    print()

    # ---- Preflight ------------------------------------------------------
    hr("PREFLIGHT")
    pf = Preflight()

    # Core deps (should be present after the re-exec attempt)
    missing_core = module_missing(_CORE_MODULES)
    if missing_core:
        pf.error(f"Missing core packages: {', '.join(missing_core)}",
                 f"Activate the project env:  conda activate {PREFERRED_ENV}\n"
                 f"or install them:  pip install {' '.join(missing_core)}")
    else:
        pf.ok("Core Python packages")

    # Step 01 needs
    if "scholar" in sources:
        if module_missing(["scholarly"]):
            pf.warn("scholarly not installed (Google Scholar source will be skipped)",
                    "pip install scholarly   — or remove 'scholar' from config.yaml sources")
        else:
            pf.warn("Google Scholar is enabled but is unreliable",
                    "Google blocks automated queries (CAPTCHA), so it usually returns 0\n"
                    "results without a proxy. It's hard-capped at 45s so it can't hang the\n"
                    "run, but consider removing 'scholar' from config.yaml sources.")
    if "scopus" in sources and not os.getenv("SCOPUS_API_KEY"):
        pf.warn("SCOPUS_API_KEY not set (Scopus will be skipped)", "Add it to .env")
    if "pubmed" in sources and not os.getenv("PUBMED_EMAIL"):
        pf.warn("PUBMED_EMAIL not set (PubMed will be skipped)", "Add it to .env")

    # Step 02 needs
    if args.ai:
        # read the configured model, so preflight pulls what the run will use
        ai_url = os.getenv("OLLAMA_URL",
                           settings.ai_filter.get("ollama_url", "http://localhost:11434"))
        ai_model = os.getenv("OLLAMA_MODEL", settings.ai_filter.get("model", "gemma3:4b"))
        ensure_ollama(pf, ai_model, ai_url, args.yes)
    else:
        if settings.filter.get("enabled", {}).get("non_english") and module_missing(["langdetect"]):
            pf.warn("langdetect not installed (non-English filter will be skipped)",
                    "pip install langdetect")

    # Step 03 needs
    if not args.skip_download:
        if module_missing(["curl_cffi"]):
            pf.warn("curl_cffi not installed (downloads more likely to hit HTTP 403)",
                    "pip install curl_cffi   — strongly recommended")
        if settings.download.get("use_zotero"):
            ensure_zotero_server(pf, os.getenv("ZOTERO_TRANSLATION_SERVER", "http://127.0.0.1:1969"))
        if settings.download.get("use_browser"):
            ensure_browser(pf)

    print()
    if pf.blocked:
        print(c("Preflight failed — fix the ✗ items above and re-run.", "red"))
        return 1
    print(c("Preflight passed.", "green"))
    print()

    # ---- Run the steps --------------------------------------------------
    timings = []
    rc, t = run_step("01_fetch_metadata.py", "STEP 1/3 — Fetch metadata")
    timings.append(("Fetch metadata", t, rc))
    if rc != 0:
        return _summary(timings, aborted=True)

    filter_script = "02_abstract_filter_ai.py" if args.ai else "02_abstract_filter.py"
    rc, t = run_step(filter_script, f"STEP 2/3 — Filter abstracts ({'AI' if args.ai else 'keyword'})")
    timings.append(("Filter abstracts", t, rc))
    if rc != 0:
        return _summary(timings, aborted=True)

    if not args.skip_download:
        rc, t = run_step("03_download_papers.py", "STEP 3/3 — Download PDFs")
        timings.append(("Download PDFs", t, rc))

    return _summary(timings)


def _summary(timings, aborted=False) -> int:
    hr(c("PIPELINE SUMMARY", "bold"))
    total = sum(t for _, t, _ in timings)
    for label, secs, rc in timings:
        mark = c("ok", "green") if rc == 0 else c("failed", "red")
        print(f"  {label:22s} {secs:6.0f}s   {mark}")
    print(f"  {'TOTAL':22s} {total:6.0f}s   ({total/60:.1f} min)")

    # Point at the outputs that exist
    results = ROOT / "results"
    for rel in ["references.bib", "references_filtered.bib",
                "references_filtered_ai.bib", "papers.csv", "pdfs"]:
        p = results / rel
        if p.exists():
            if p.is_dir():
                n = len(list(p.glob("*.pdf")))
                print(f"  → {p.relative_to(ROOT)}/  ({n} PDFs)")
            else:
                print(f"  → {p.relative_to(ROOT)}")
    print()
    if aborted:
        print(c("Pipeline aborted (a step failed above).", "red"))
        return 1
    print(c("Pipeline complete.", "green"))
    return 0


if __name__ == "__main__":
    maybe_reexec_into_env()
    sys.exit(main())
