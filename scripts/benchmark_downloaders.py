#!/usr/bin/env python3
"""
Benchmark PDF-download methods against a fixed set of test papers.

For each paper, every applicable strategy is asked to resolve a PDF URL, and
that URL is verified to actually serve a PDF (checked via a small ranged GET, so
we never download whole files). The per-method success counts are written to
`results/benchmark_results.json` and rendered to `docs/images/download_benchmark.png`
for the README.

The Zotero method requires a running translation server (see README). If it is
not reachable, its column is reported as "server not running" and skipped.

Usage:
    python scripts/benchmark_downloaders.py
    python scripts/benchmark_downloaders.py --no-plot     # JSON only
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.searchers.paper_downloader import PaperDownloader
from src.searchers.zotero_client import ZoteroTranslationClient


# Curated test set spanning open-access, preprint, and paywalled publishers.
# Each paper carries whatever identifiers a real pipeline row would have.
TEST_PAPERS = [
    {"label": "arXiv (Attention Is All You Need)", "type": "preprint",
     "arxiv_id": "1706.03762", "url": "https://arxiv.org/abs/1706.03762"},
    {"label": "arXiv (ResNet)", "type": "preprint",
     "arxiv_id": "1512.03385", "url": "https://arxiv.org/abs/1512.03385"},
    {"label": "PLOS ONE (OA)", "type": "open-access",
     "doi": "10.1371/journal.pone.0173664",
     "url": "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0173664",
     "title": "The miR-200 family is increased in dysplastic lesions in ulcerative colitis patients"},
    {"label": "MDPI Applied Sciences (OA)", "type": "open-access",
     "doi": "10.3390/app11115088",
     "url": "https://www.mdpi.com/2076-3417/11/11/5088"},
    {"label": "Frontiers (OA)", "type": "open-access",
     "doi": "10.3389/fnins.2019.00585",
     "url": "https://www.frontiersin.org/articles/10.3389/fnins.2019.00585/full"},
    {"label": "eLife (OA)", "type": "open-access",
     "doi": "10.7554/eLife.00013",
     "url": "https://elifesciences.org/articles/00013"},
    {"label": "PMC / PubMed (OA)", "type": "open-access",
     "pmid": "32493627",
     "url": "https://pubmed.ncbi.nlm.nih.gov/32493627/"},
    {"label": "bioRxiv (preprint)", "type": "preprint",
     "doi": "10.1101/2020.03.20.000133",
     "url": "https://www.biorxiv.org/content/10.1101/2020.03.20.000133v1"},
    {"label": "Nature (paywalled)", "type": "paywalled",
     "doi": "10.1038/nature14539",
     "url": "https://www.nature.com/articles/nature14539",
     "title": "Deep learning"},
    {"label": "ScienceDirect (paywalled)", "type": "paywalled",
     "doi": "10.1016/j.neuron.2018.01.048",
     "url": "https://www.sciencedirect.com/science/article/pii/S0896627318300618"},
    {"label": "IEEE Xplore (paywalled)", "type": "paywalled",
     "doi": "10.1109/CVPR.2016.90",
     "url": "https://ieeexplore.ieee.org/document/7780459"},
    {"label": "Wiley (paywalled)", "type": "paywalled",
     "doi": "10.1111/j.1460-9568.2011.07677.x",
     "url": "https://onlinelibrary.wiley.com/doi/10.1111/j.1460-9568.2011.07677.x"},
]

# Display order and human labels for the methods we compare.
METHOD_LABELS = {
    "zotero": "Zotero translators",
    "unpaywall": "Unpaywall",
    "crossref": "Crossref",
    "arxiv": "arXiv",
    "biorxiv": "bioRxiv/medRxiv",
    "pmc": "PubMed Central",
    "publisher": "Publisher patterns",
    "scraping": "HTML scraping",
}


def url_yields_pdf(session: requests.Session, url: str, referer: str = None, timeout: int = 25) -> bool:
    """Return True if `url` serves a real PDF.

    Mirrors PaperDownloader._download_pdf's verification (stream, check the
    content-type or leading %PDF magic bytes) so the benchmark reflects what the
    downloader would actually accept - just without saving the whole file.
    """
    if not url:
        return False
    headers = {"Accept": "application/pdf,application/octet-stream,*/*;q=0.8"}
    headers["Referer"] = referer or "https://www.google.com/"
    try:
        r = session.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True)
        if r.status_code != 200:
            r.close()
            return False
        ctype = r.headers.get("content-type", "").lower()
        chunk = next(r.iter_content(chunk_size=4096), b"")
        r.close()
        return "application/pdf" in ctype or chunk[:4] == b"%PDF"
    except requests.RequestException:
        return False


def run_benchmark():
    email = os.getenv("UNPAYWALL_EMAIL") or os.getenv("PUBMED_EMAIL")
    if not email:
        print("⚠ No UNPAYWALL_EMAIL/PUBMED_EMAIL in .env - Unpaywall will be under-reported.\n")
    downloader = PaperDownloader(output_dir="results/benchmark_tmp", use_zotero=False,
                                 unpaywall_email=email, max_workers=1)
    session = downloader.session

    zotero = ZoteroTranslationClient()
    zotero_up = zotero.is_available()
    if not zotero_up:
        print("⚠ Zotero translation server not running - its column will be skipped.")
        print("  Start it with: cd vendor/translation-server && node src/server.js\n")

    # results[method] = list of (paper_label, success_bool)
    results = {m: [] for m in METHOD_LABELS}
    per_paper = []

    for paper in TEST_PAPERS:
        label = paper["label"]
        doi = paper.get("doi")
        url = paper.get("url")
        title = paper.get("title", "")
        print(f"→ {label}")
        paper_row = {"label": label, "type": paper["type"], "methods": {}}

        # Build the candidate URL per method, then verify it yields a PDF.
        candidates = {}

        if zotero_up and (doi or url):
            pdf, page = zotero.get_pdf_url(doi=doi, url=url)
            candidates["zotero"] = (pdf, page)

        if doi:
            candidates["unpaywall"] = (downloader._get_unpaywall_pdf(doi), url)
            candidates["crossref"] = (downloader._get_crossref_pdf(doi, title), url)

        if paper.get("arxiv_id") or (url and "arxiv" in url.lower()):
            candidates["arxiv"] = (downloader._get_arxiv_pdf(paper), None)

        if url and ("biorxiv.org" in url.lower() or "medrxiv.org" in url.lower()):
            candidates["biorxiv"] = (downloader._get_biorxiv_pdf(url), url)

        if paper.get("pmid"):
            candidates["pmc"] = (downloader._get_pmc_pdf(paper["pmid"]), url)

        if url and doi:
            candidates["publisher"] = (downloader._get_publisher_pdf(url, doi), url)

        if url:
            candidates["scraping"] = (downloader._try_scrape_pdf_link(url), url)

        for method in METHOD_LABELS:
            if method not in candidates:
                paper_row["methods"][method] = None  # not applicable
                continue
            cand_url, referer = candidates[method]
            ok = url_yields_pdf(session, cand_url, referer=referer)
            results[method].append((label, ok))
            paper_row["methods"][method] = ok
            print(f"    {METHOD_LABELS[method]:22s}: {'✓' if ok else '·'}")
            time.sleep(0.3)  # be polite between hits

        per_paper.append(paper_row)

    # Aggregate: success count and applicable count per method
    summary = {}
    for method, rows in results.items():
        applicable = len(rows)
        hits = sum(1 for _, ok in rows if ok)
        summary[method] = {
            "label": METHOD_LABELS[method],
            "hits": hits,
            "applicable": applicable,
            "success_rate": (hits / applicable * 100) if applicable else 0.0,
        }

    # Pipeline-level: a paper counts as covered if ANY method succeeded, with and
    # without Zotero, to show what Zotero adds on top of the built-in chain.
    n_papers = len(TEST_PAPERS)
    covered_builtin = 0
    covered_with_zotero = 0
    zotero_only = 0
    for row in per_paper:
        methods = row["methods"]
        builtin_hit = any(v for k, v in methods.items() if k != "zotero" and v)
        zotero_hit = bool(methods.get("zotero"))
        covered_builtin += 1 if builtin_hit else 0
        covered_with_zotero += 1 if (builtin_hit or zotero_hit) else 0
        zotero_only += 1 if (zotero_hit and not builtin_hit) else 0

    pipeline = {
        "n_papers": n_papers,
        "covered_builtin": covered_builtin,
        "covered_with_zotero": covered_with_zotero,
        "zotero_only_wins": zotero_only,
        "zotero_available": zotero_up,
    }

    return {"summary": summary, "pipeline": pipeline, "per_paper": per_paper}


def render_chart(data: dict, out_path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    # --- validated palette (from dataviz skill references/palette.md) ---
    ACCENT = "#2a78d6"       # Zotero: retrieved (categorical slot 1, blue)
    ACCENT_BG = "#c9ddf5"    # Zotero: applicable (light tint of accent)
    NEUTRAL = "#6f6f6b"      # built-in: retrieved
    NEUTRAL_BG = "#dcdcd8"   # built-in: applicable (reach)
    INK = "#0b0b0b"
    MUTED = "#52514e"
    GRID = "#e6e6e3"

    n = data["pipeline"]["n_papers"]
    summary = data["summary"]
    items = [(m, s) for m, s in summary.items() if s["applicable"] > 0]
    # Sort by papers RETRIEVED (absolute reach), so general-purpose methods that
    # actually cover the corpus rank above narrow single-source methods.
    items.sort(key=lambda kv: (kv[1]["hits"], kv[1]["applicable"]))

    labels = [s["label"] for _, s in items]
    hits = [s["hits"] for _, s in items]
    applicable = [s["applicable"] for _, s in items]
    is_zotero = [m == "zotero" for m, _ in items]

    fig, ax = plt.subplots(figsize=(9.5, 0.6 * len(items) + 1.8), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")

    y = list(range(len(items)))
    # Background bar = applicable papers (reach); foreground = retrieved (hits)
    for i in y:
        bg = ACCENT_BG if is_zotero[i] else NEUTRAL_BG
        fg = ACCENT if is_zotero[i] else NEUTRAL
        ax.barh(i, applicable[i], color=bg, height=0.62, zorder=2)
        ax.barh(i, hits[i], color=fg, height=0.62, zorder=3)
        rate = (hits[i] / applicable[i] * 100) if applicable[i] else 0
        ax.text(applicable[i] + 0.15, i, f"{hits[i]}/{applicable[i]}  ({rate:.0f}%)",
                va="center", ha="left", fontsize=9, color=MUTED, zorder=4)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10, color=INK)
    ax.set_xlim(0, n + 2.2)
    ax.set_xticks(range(0, n + 1, 2))
    ax.set_xlabel("Papers (dark = PDF retrieved · light = method applicable)", fontsize=9, color=MUTED)

    ax.set_title("PDF download methods compared", fontsize=13, color=INK, pad=30,
                 loc="left", fontweight="bold")
    p = data["pipeline"]
    subtitle = (f"{n} papers across open-access, preprint & paywalled publishers   ·   "
                f"combined pipeline retrieved {p['covered_with_zotero']}/{n}")
    ax.annotate(subtitle, xy=(0, 1.015), xycoords="axes fraction",
                fontsize=9.5, color=MUTED, ha="left", va="bottom")

    ax.xaxis.grid(True, color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0)

    legend = ax.legend(
        handles=[Patch(color=ACCENT, label="Zotero – retrieved"),
                 Patch(color=ACCENT_BG, label="Zotero – applicable"),
                 Patch(color=NEUTRAL, label="Built-in – retrieved"),
                 Patch(color=NEUTRAL_BG, label="Built-in – applicable")],
        loc="lower right", frameon=False, fontsize=8.5, ncol=2)
    for text in legend.get_texts():
        text.set_color(MUTED)

    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"\n✓ Chart saved to {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-plot", action="store_true", help="Write JSON only, skip the chart")
    args = ap.parse_args()

    print("=" * 70)
    print("DOWNLOAD-METHOD BENCHMARK")
    print("=" * 70)
    data = run_benchmark()

    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    json_path = results_dir / "benchmark_results.json"
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\n✓ Raw results saved to {json_path}")

    p = data["pipeline"]
    print("\nPipeline coverage:")
    print(f"  Built-in methods only:   {p['covered_builtin']}/{p['n_papers']} papers")
    print(f"  With Zotero translators: {p['covered_with_zotero']}/{p['n_papers']} papers")
    print(f"  Papers only Zotero got:  {p['zotero_only_wins']}")

    if not args.no_plot:
        render_chart(data, Path("docs/images/download_benchmark.png"))


if __name__ == "__main__":
    main()
