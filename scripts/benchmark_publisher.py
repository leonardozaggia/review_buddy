#!/usr/bin/env python3
"""
Per-publisher download benchmark.

Builds a sample of DOIs from one publisher (Elsevier by default, matched on DOI
prefix), runs the real PaperDownloader over it with the full strategy chain, and
reports the retrieval rate plus which strategy won each paper.

The sample is drawn from a live Scopus search rather than a fixed list, so the
number reflects current publisher behaviour rather than a set that was curated
when the blocking rules were different. It is spread across publication years
and capped per journal so one title cannot dominate.

Results depend heavily on the network you run it from - IP-based institutional
access dominates - so run it where you actually download, and record that
context alongside the number.

Usage:
    python scripts/benchmark_publisher.py --query query.txt --limit 100
    python scripts/benchmark_publisher.py --bib results/references.bib --limit 50
    python scripts/benchmark_publisher.py --query query.txt --publisher wiley
"""

import argparse
import json
import os
import random
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.searchers.paper_downloader import PaperDownloader

# DOI prefixes by publisher. A DOI prefix identifies the registrant, which is
# the most reliable publisher signal available without an extra metadata call.
PREFIXES = {
    "elsevier": ("10.1016/", "10.1006/", "10.1053/", "10.1054/"),
    "wiley": ("10.1002/", "10.1111/"),
    "springer": ("10.1007/", "10.1038/", "10.1186/"),
    "mdpi": ("10.3390/",),
    "frontiers": ("10.3389/",),
    "taylorfrancis": ("10.1080/",),
    "sage": ("10.1177/",),
}


def sample_from_scopus(query: str, publisher: str, limit: int,
                       year_from: int, year_to: int, per_journal: int):
    """Draw a year-spread, journal-capped sample of one publisher's DOIs."""
    from src.searchers.scopus_searcher import ScopusSearcher

    key = os.getenv("SCOPUS_API_KEY")
    if not key:
        sys.exit("SCOPUS_API_KEY is not set - use --bib to supply a sample instead.")

    prefixes = PREFIXES[publisher]
    searcher = ScopusSearcher(api_key=key, max_results=max(400, limit * 4), timeout=60)

    by_year = {}
    for year in range(year_from, year_to + 1):
        papers = searcher.search(query, year_from=year, year_to=year)
        by_year[year] = [p for p in papers
                         if p.doi and p.doi.lower().startswith(prefixes)]
        print(f"  {year}: {len(papers):>4} fetched, {len(by_year[year]):>3} {publisher}")

    random.seed(20260730)
    pools = {y: random.sample(v, len(v)) for y, v in by_year.items()}
    sample, journals, seen = [], defaultdict(int), set()

    while len(sample) < limit and any(pools.values()):
        for year in sorted(pools):
            if len(sample) >= limit:
                break
            while pools[year]:
                p = pools[year].pop()
                journal = (p.journal or "unknown").strip()
                if p.doi.lower() in seen or journals[journal] >= per_journal:
                    continue
                seen.add(p.doi.lower())
                journals[journal] += 1
                sample.append(p)
                break

    print(f"\n  sample: {len(sample)} papers across {len(journals)} journals")
    return [{"title": p.title, "doi": p.doi,
             "journal": p.journal or "",
             "year": p.publication_date.year if p.publication_date else ""}
            for p in sample]


def sample_from_bib(bib_path: str, publisher: str, limit: int):
    import bibtexparser
    prefixes = PREFIXES[publisher]
    with open(bib_path, encoding="utf-8") as f:
        entries = bibtexparser.load(f).entries
    hits = [e for e in entries
            if e.get("doi", "").lower().startswith(prefixes)]
    print(f"  {len(hits)} {publisher} DOIs in {bib_path}")
    return hits[:limit]


def write_bib(entries, path: Path):
    def esc(t):
        return (t or "").replace("{", "").replace("}", "").replace("\\", "")

    blocks = []
    for i, e in enumerate(entries, 1):
        blocks.append(
            f"@article{{bench{i:04d},\n"
            f"  title = {{{esc(e.get('title'))}}},\n"
            f"  journal = {{{esc(e.get('journal'))}}},\n"
            f"  year = {{{e.get('year', '')}}},\n"
            f"  doi = {{{e['doi']}}},\n}}"
        )
    path.write_text("\n\n".join(blocks), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--query", help="query file to draw a fresh Scopus sample from")
    src.add_argument("--bib", help="existing .bib to draw the sample from")
    ap.add_argument("--publisher", default="elsevier", choices=sorted(PREFIXES))
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--year-from", type=int, default=2020)
    ap.add_argument("--year-to", type=int, default=2026)
    ap.add_argument("--per-journal", type=int, default=6,
                    help="cap per journal so one title cannot dominate")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-browser", action="store_true",
                    help="disable the Camoufox fetcher (measures the HTTP-only chain)")
    ap.add_argument("--no-zotero", action="store_true")
    ap.add_argument("--out", default="scripts/benchmark_data/publisher_bench")
    args = ap.parse_args()

    if args.query:
        query = Path(args.query).read_text(encoding="utf-8")
        entries = sample_from_scopus(query, args.publisher, args.limit,
                                     args.year_from, args.year_to, args.per_journal)
    else:
        entries = sample_from_bib(args.bib, args.publisher, args.limit)

    if not entries:
        sys.exit(f"No {args.publisher} DOIs found in the sample.")

    out_dir = Path(args.out)
    if out_dir.exists():
        shutil.rmtree(out_dir)          # fresh dir: nothing skipped as already-downloaded
    out_dir.mkdir(parents=True)
    bib_path = out_dir / "sample.bib"
    write_bib(entries, bib_path)

    start = time.time()
    downloader = PaperDownloader(
        output_dir=str(out_dir),
        use_scihub=False,
        unpaywall_email=os.getenv("UNPAYWALL_EMAIL") or os.getenv("PUBMED_EMAIL"),
        use_zotero=not args.no_zotero,
        zotero_url=os.getenv("ZOTERO_TRANSLATION_SERVER", "http://127.0.0.1:1969"),
        max_workers=args.workers,
        use_browser=not args.no_browser,
    )
    downloader.download_from_bib(str(bib_path))
    elapsed = time.time() - start

    stats = dict(downloader.stats)
    total = stats.get("total", len(entries))
    ok = stats.get("success", 0)

    print("\n" + "=" * 68)
    print(f"{args.publisher.upper()} DOWNLOAD BENCHMARK - {total} DOIs")
    print(f"  browser={'off' if args.no_browser else 'on'}  "
          f"zotero={'off' if args.no_zotero else 'on'}  workers={args.workers}")
    print("=" * 68)
    print(f"  retrieved : {ok}/{total}  ({100.0 * ok / max(total, 1):.0f}%)")
    print(f"  failed    : {stats.get('failed', 0)}")
    print(f"  wall time : {elapsed / 60:.1f} min  ({elapsed / max(total, 1):.1f}s per paper)")
    print("\n  by strategy:")
    times = stats.get("time_by_method", {})
    for method, n in sorted(stats.get("by_method", {}).items(), key=lambda kv: -kv[1]):
        print(f"    {method:<28} {n:>3}   avg {times.get(method, 0) / max(n, 1):>5.1f}s")

    (out_dir / "result.json").write_text(
        json.dumps({**stats, "elapsed_s": round(elapsed, 1),
                    "publisher": args.publisher,
                    "browser": not args.no_browser,
                    "zotero": not args.no_zotero}, indent=2, default=str),
        encoding="utf-8")
    print(f"\n  wrote {out_dir / 'result.json'}")


if __name__ == "__main__":
    main()
