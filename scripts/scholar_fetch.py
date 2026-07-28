#!/usr/bin/env python3
"""
Standalone Google Scholar fetch, run as a subprocess by ScholarSearcher.

Why a separate process: the `scholarly` library provides no timeout and blocks
in a way that in-process (thread OR multiprocessing) timeouts can't reliably
interrupt on Windows. Running it as a plain subprocess lets the parent enforce
a hard deadline with subprocess.run(timeout=...), whose kill() uses a real
TerminateProcess and actually stops a hung scholarly call.

Writes a JSON list of paper dicts to the given OUTPUT FILE (not stdout). Writing
to a file - and having the parent NOT capture stdout - is deliberate: scholarly
can spawn grandchild processes that inherit a stdout pipe, so a parent using
subprocess.run(capture_output=True) would block forever on a pipe that never
reaches EOF even after the child is killed. A file sidesteps that entirely.

Usage (invoked by ScholarSearcher, not by hand):
    python scripts/scholar_fetch.py <out_file> <max_results> <year_from|-> <year_to|-> <query...>
"""

import json
import sys


def main() -> int:
    if len(sys.argv) < 6:
        return 0

    out_file = sys.argv[1]
    max_results = int(sys.argv[2])
    year_from = None if sys.argv[3] == "-" else int(sys.argv[3])
    year_to = None if sys.argv[4] == "-" else int(sys.argv[4])
    query = " ".join(sys.argv[5:])

    out = []
    try:
        from scholarly import scholarly

        results = scholarly.search_pubs(query, year_low=year_from, year_high=year_to)
        for result in results:
            if len(out) >= max_results:
                break
            bib = result.get("bib", {}) or {}
            title = bib.get("title")
            if not title:
                continue
            authors = bib.get("author", [])
            if isinstance(authors, str):
                authors = [authors]
            pub_url = result.get("pub_url") or result.get("eprint_url")
            doi = None
            if pub_url and "doi.org" in pub_url:
                doi = pub_url.split("doi.org/")[-1].split("?")[0]
            out.append({
                "title": title,
                "authors": list(authors) if authors else [],
                "abstract": bib.get("abstract"),
                "journal": bib.get("venue"),
                "year": int(bib["pub_year"]) if str(bib.get("pub_year", "")).isdigit() else None,
                "url": pub_url,
                "doi": doi,
                "citations": result.get("num_citations"),
            })
    except Exception:
        # Blocked / CAPTCHA / parse error -> emit whatever we have (often none)
        pass

    try:
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(out, f)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
