#!/usr/bin/env python3
"""
A/B benchmark: built-in fallback chain vs the Zotero resolver chain.

Runs the real PaperDownloader twice over the same set of DOIs - once with
Zotero disabled, once enabled - and reports how many PDFs each configuration
actually retrieved, plus which strategy won each paper.

This answers "does the Zotero path get me as many PDFs as pasting the DOIs
into the Zotero app?" - run it on the network you actually download from
(e.g. your university network), since IP-based access dominates the result.

Usage:
    python scripts/benchmark_zotero_ab.py --dois dois.json --limit 60
    python scripts/benchmark_zotero_ab.py --bib results/references.bib
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import os
from src.searchers.paper_downloader import PaperDownloader


def load_entries(args):
    """Return a list of bibtex-like entry dicts."""
    if args.bib:
        import bibtexparser
        with open(args.bib, encoding="utf-8") as f:
            return bibtexparser.load(f).entries
    data = json.loads(Path(args.dois).read_text(encoding="utf-8"))
    return [{"title": d.get("title") or d["doi"], "doi": d["doi"], "url": d.get("url"),
             "publisher": d.get("publisher", "?")} for d in data]


def run_config(entries, out_dir: Path, use_zotero: bool, workers: int, email: str):
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    d = PaperDownloader(output_dir=str(out_dir), use_zotero=use_zotero,
                        unpaywall_email=email, max_workers=workers)
    # Silence per-paper console chatter; the log file still has everything
    for h in list(d.logger.handlers):
        import logging as _l
        if isinstance(h, _l.StreamHandler) and not isinstance(h, _l.FileHandler):
            d.logger.removeHandler(h)

    start = time.time()
    d._download_all(entries)
    elapsed = time.time() - start

    pdfs = [f for f in out_dir.iterdir() if f.suffix == ".pdf"]
    return {
        "use_zotero": use_zotero,
        "papers": len(entries),
        "retrieved": len(pdfs),
        "elapsed_s": round(elapsed, 1),
        "by_method": {k: v for k, v in d.stats["by_method"].items() if v},
        "failed": d.stats["failed"],
        "total_bytes": sum(f.stat().st_size for f in pdfs),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dois", help="JSON file: [{doi, title, url, publisher}]")
    ap.add_argument("--bib", help="BibTeX file to use instead")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default="results/ab_benchmark")
    ap.add_argument("--only", choices=["builtin", "zotero"], help="Run just one config")
    args = ap.parse_args()

    if not args.dois and not args.bib:
        ap.error("provide --dois or --bib")

    entries = load_entries(args)[: args.limit]
    email = os.getenv("UNPAYWALL_EMAIL") or os.getenv("PUBMED_EMAIL")
    out_root = Path(args.out)

    print("=" * 72)
    print(f"A/B DOWNLOAD BENCHMARK - {len(entries)} papers, {args.workers} workers")
    print("=" * 72)

    results = {}
    if args.only != "zotero":
        print("\n[A] Built-in fallback chain (Zotero disabled)...")
        results["builtin"] = run_config(entries, out_root / "builtin", False, args.workers, email)
        r = results["builtin"]
        print(f"    retrieved {r['retrieved']}/{r['papers']} in {r['elapsed_s']}s  {r['by_method']}")

    if args.only != "builtin":
        print("\n[B] Zotero resolver chain enabled...")
        results["zotero"] = run_config(entries, out_root / "zotero", True, args.workers, email)
        r = results["zotero"]
        print(f"    retrieved {r['retrieved']}/{r['papers']} in {r['elapsed_s']}s  {r['by_method']}")

    out_json = out_root / "ab_results.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    if "builtin" in results and "zotero" in results:
        a, b = results["builtin"], results["zotero"]
        delta = b["retrieved"] - a["retrieved"]
        pct = lambda r: r["retrieved"] / r["papers"] * 100
        print(f"Built-in only : {a['retrieved']:3d}/{a['papers']} ({pct(a):.0f}%)  {a['elapsed_s']}s")
        print(f"With Zotero   : {b['retrieved']:3d}/{b['papers']} ({pct(b):.0f}%)  {b['elapsed_s']}s")
        print(f"Delta         : {delta:+d} papers")
    print(f"\nResults: {out_json}")
    print("=" * 72)


if __name__ == "__main__":
    main()
