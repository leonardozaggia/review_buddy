"""
Diagnostic script to run selected searchers and print parsed publication years.
Run from repo root:
    python scripts\debug_searchers.py --query "EEG" --year-from 2020 --year-to 2024 --max 30

This script calls ArxivSearcher and ScholarSearcher (if available) and prints
summary lines for each returned Paper object for quick inspection.
"""
import argparse
import logging
import sys
from datetime import datetime

# Ensure repo root is on path
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.searchers.arxiv_searcher import ArxivSearcher

try:
    from src.searchers.scholar_searcher import ScholarSearcher
    SCHOLAR_AVAILABLE = True
except Exception:
    SCHOLAR_AVAILABLE = False

from src.models import Paper


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("debug_searchers")


def print_paper_summary(p: Paper):
    title = (p.title[:120] + "...") if p.title and len(p.title) > 120 else (p.title or "<no title>")
    year = p.publication_date.year if getattr(p, 'publication_date', None) else None
    sources_str = ','.join(sorted(list(p.sources))) if getattr(p, 'sources', None) else ''
    doi_str = (p.doi or '')
    arxiv_id_str = (getattr(p, 'arxiv_id', '') or '')
    year_str = str(year) if year is not None else ''
    print(f"{sources_str:20} | Year: {year_str:6} | DOI: {doi_str:30} | ID: {arxiv_id_str:20} | {title}")


def run_arxiv(query, year_from, year_to, max_results):
    print('\n=== arXiv ===')
    s = ArxivSearcher(max_results=max_results)
    papers = s.search(query, year_from=year_from, year_to=year_to)
    print(f"arXiv returned {len(papers)} papers")
    for p in papers:
        print_paper_summary(p)


def run_scholar(query, year_from, year_to, max_results):
    print('\n=== Google Scholar ===')
    if not SCHOLAR_AVAILABLE:
        print("scholarly library not available; skipping Scholar tests")
        return
    try:
        s = ScholarSearcher(max_results=max_results)
    except Exception as e:
        print(f"Failed to initialize ScholarSearcher: {e}")
        return
    
    # Use the ScholarSearcher.search() method which properly handles year filtering
    print(f"INFO: Searching Google Scholar with year_from={year_from}, year_to={year_to}")
    papers = s.search(query, year_from=year_from, year_to=year_to)
    
    print(f"Scholar returned {len(papers)} papers")
    for p in papers:
        print_paper_summary(p)
    
    return [(None, p) for p in papers]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--query', required=True)
    parser.add_argument('--year-from', type=int, default=None)
    parser.add_argument('--year-to', type=int, default=None)
    parser.add_argument('--max', type=int, default=30)
    parser.add_argument('--dump-raw-scholar', action='store_true', help='Print raw Scholar result dicts for out-of-range items')
    parser.add_argument('--no-year', action='store_true', help="Don't pass year filters to searchers (useful to compare raw Scholar behavior)")
    args = parser.parse_args()

    yf = None if args.no_year else args.year_from
    yt = None if args.no_year else args.year_to

    run_arxiv(args.query, yf, yt, args.max)
    scholar_results = run_scholar(args.query, yf, yt, args.max)

    # If requested, dump raw Scholar dicts for items that are outside the requested year range
    if args.dump_raw_scholar and scholar_results:
        print('\n=== Raw Scholar result inspection ===')
        for raw, p in scholar_results:
            parsed_year = p.publication_date.year if getattr(p, 'publication_date', None) else None
            # Dump any entries that are outside (if year filters were provided)
            if args.no_year:
                # If no-year mode, just print the first 10 raw dicts
                print('RAW:', raw)
            else:
                if (args.year_from and parsed_year and parsed_year < args.year_from) or \
                   (args.year_to and parsed_year and parsed_year > args.year_to) or \
                   (parsed_year is None):
                    print('OUT-OF-RANGE RAW: parsed_year=', parsed_year)
                    print(raw)
