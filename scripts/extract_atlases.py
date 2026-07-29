#!/usr/bin/env python3
"""
Extract which brain ATLAS / parcellation each downloaded paper used.

Scans the PDFs in results/pdfs/, pulls their text, and matches against a curated
registry of neonatal/infant-specific and general brain atlases. Produces:

  results/atlas_usage.csv    one row per paper: title, DOI, file, atlases found
  results/atlas_summary.csv  one row per atlas: how many papers used it
  results/atlas_matches.csv  one row per paper x atlas, with the matched snippet
                             (the auditable evidence for each assignment)

The atlas is usually named in the Methods, not the abstract - which is exactly
why the AI screen kept ALL empirical neonatal fMRI papers and we recover the
atlas here from full text.

Usage:
    python scripts/extract_atlases.py
    python scripts/extract_atlases.py --pdf-dir results/pdfs --bib results/references_filtered_ai.bib
"""

import argparse
import csv
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# Atlas-context words. A bare author surname (Gousias, Craddock, Dosenbach...)
# appears constantly in citations without the study using that group's atlas, so
# those surnames only count when one of these words sits within ~60 chars.
_GUARD = (r"(?:atlas|template|parcellat\w*|segment\w*|registrat\w*|register\w*|"
          r"labell?ing|labell?ed|scheme|space|\bROIs?\b|network)")


def _guarded(surname: str):
    """Two patterns: surname followed by, or preceded by, an atlas-context word."""
    return [rf"{surname}[^.\n]{{0,60}}{_GUARD}", rf"{_GUARD}[^.\n]{{0,60}}{surname}"]


# ---------------------------------------------------------------------------
# Atlas registry: canonical name -> list of regex patterns. Patterns are
# compiled case-INSENSITIVE, BUT acronym tokens that collide with common words
# are wrapped in a scoped `(?-i:...)` group to force case-SENSITIVE matching for
# just that token (e.g. `(?-i:UNC)` so we don't match "f-unc-tional", and
# `(?-i:AAL)` / `(?-i:ALBERTs)` so all-caps acronyms don't hit ordinary words or
# the surname "Albert"). Common-word author names (Power, Gordon, Shen, Shi) are
# additionally guarded with nearby context ("atlas"/"parcellation"/a number/a
# year). Order doesn't matter; a paper can match several atlases.
# ---------------------------------------------------------------------------
ATLAS_REGISTRY = {
    # --- neonatal / infant specific -------------------------------------
    "UNC neonatal/infant (UNC-Chapel Hill)": [
        r"(?-i:UNC)\b(?:[\s\-]?Chapel\s*Hill)?[^.\n]{0,30}(?:neonat|newborn|infant|pediatric|paediatric)",
        r"(?:neonat|newborn|infant|preterm)[^.\n]{0,20}(?-i:UNC)\b",
    ],
    "dHCP (developing Human Connectome Project)": [
        r"\bdHCP\b", r"developing\s+Human\s+Connectome\s+Project",
    ],
    "M-CRIB (Melbourne Children's Regional Infant Brain)": [
        r"M[\s\-]?CRIB(?:[\s\-]?2\.?0|[\s\-]?S)?\b",
        r"Melbourne\s+Children'?s?\s+Regional\s+Infant\s+Brain",
    ],
    # ALBERT token is case-sensitive (all-caps "ALBERTs"); the title-case
    # "Albert" is almost always an author name. Long form stays case-insensitive.
    "ALBERT / ALBERTs (Gousias/Imperial)": [
        r"\b(?-i:ALBERTs)\b",
        r"\b(?-i:ALBERT)\s+(?:atlas|template|neonat|infant)",
        r"Automatic\s+Labell?ing\s+of\s+Brain",
    ],
    "Edinburgh Neonatal Atlas (ENA)": [
        r"Edinburgh\s+Neonatal\s+Atlas", r"\b(?-i:ENA)(?:33|50)\b",
    ],
    "JHU neonatal (Oishi)": [
        r"JHU[^.\n]{0,20}(?:neonat|infant)", r"Oishi[^.\n]{0,20}(?:atlas|neonat|template)",
        r"neonat[^.\n]{0,10}JHU",
    ],
    "Serag neonatal atlas": [r"Serag[^.\n]{0,25}(?:atlas|template|neonat)"],
    # Both orders occur: "Shi et al. neonatal atlas" AND "the neonatal atlas
    # [Shi et al., 2011]" - the second form was missed until a hand-check found it.
    "Shi neonatal atlas": [
        r"Shi[^.\n]{0,20}neonat[^.\n]{0,15}(?:atlas|template)",
        r"(?:atlas|template)[^.\n]{0,12}\[?\bShi\b\s+et\s+al",
        r"\bShi\b\s+et\s+al[^.\n]{0,25}(?:atlas|template|parcellat)",
    ],
    # Atlases surfaced by the LLM pass that the registry originally lacked.
    "CRL / Gholipour (fetal-neonatal)": [
        r"Gholipour", r"\b(?-i:CRL)\b[^.\n]{0,25}(?:atlas|template)",
        r"(?:atlas|template)[^.\n]{0,20}\b(?-i:CRL)\b",
        r"Computational\s+Radiology\s+Lab",
    ],
    "Kuklisova-Murgasova neonatal": [r"Kuklisova[\s\-]?Murgasova", r"Kuklisova"],
    "LPBA40 (LONI Probabilistic Brain Atlas)": [
        r"\b(?-i:LPBA)[\s\-]?40\b", r"LONI\s+Probabilistic\s+Brain\s+Atlas",
    ],
    "NeuroMark (ICN template)": [r"NeuroMark"],
    # Gousias is a common author in neonatal-segmentation reference lists; only
    # count it when an atlas/segmentation word is nearby (i.e. actually used).
    "Gousias neonatal atlas": _guarded("Gousias"),
    "Draw-EM (developing brain segmentation)": [r"Draw[\s\-]?EM\b"],
    "Fonov / NIHPD infant templates": [
        *_guarded("Fonov"), r"\b(?-i:NIHPD)\b", r"MNI[^.\n]{0,15}infant",
    ],
    "Imperial neonatal atlas": [r"Imperial[^.\n]{0,25}neonat"],
    "generic 'neonatal/infant atlas or template'": [
        r"(?:neonat\w*|infant|newborn|age[\s\-]?(?:specific|appropriate))\s+(?:brain\s+)?(?:atlas|template|parcellation)",
        r"study[\s\-]?specific\s+(?:atlas|template)",
    ],

    # --- general adult/pediatric atlases sometimes applied to neonates ---
    "AAL (Automated Anatomical Labeling)": [
        r"\b(?-i:AAL)[\s\-]?(?:2|3)?\b", r"Automated\s+Anatomical\s+Label",
    ],
    "Harvard-Oxford": [r"Harvard[\s\-]?Oxford"],
    "Desikan-Killiany (FreeSurfer)": [r"Desikan(?:[\s\-]Killiany)?"],
    "Destrieux (FreeSurfer)": [r"Destrieux"],
    "Brainnetome": [r"Brainnetome"],
    "Schaefer": [r"Schaefer[^.\n]{0,20}(?:atlas|parcellation|200|400|\d{3})",
                 r"Schaefer\s+(?:et\s+al|20\d\d)"],
    "Yeo networks": [r"Yeo[^.\n]{0,15}(?:network|7|17|2011)"],
    # Power 264-ROI ATLAS is Power et al. 2011. Deliberately NOT matching bare
    # "Power et al" because "Power et al. 2012/2014" is the motion-scrubbing
    # (framewise displacement) paper, a different work cited by almost every
    # rs-fMRI study - that would massively over-count.
    "Power (264)": [r"Power[^.\n]{0,15}(?:atlas|parcellation|\b264\b|2011)"],
    "Gordon": [r"Gordon[^.\n]{0,15}(?:atlas|parcellation|333|2016)"],
    "Craddock": _guarded("Craddock"),
    "Shen (268)": [r"Shen[^.\n]{0,10}(?:268|atlas|parcellation)"],
    "Glasser / HCP-MMP": [r"(?-i:HCP)[\s\-]?(?-i:MMP)", r"Glasser[^.\n]{0,20}(?:atlas|parcellation|2016)",
                          r"multi[\s\-]?modal\s+parcellation"],
    "Talairach": [r"Talairach[^.\n]{0,20}(?:atlas|space|coordinate|Tournoux|normali)",
                  r"(?:atlas|space|coordinate|normali\w+)[^.\n]{0,20}Talairach"],
    "Brodmann": [r"Brodmann\s+area"],
    "ICBM / MNI152 template": [r"\b(?-i:ICBM)\b", r"MNI[\s\-]?152"],
    "Gordon/Power/Dosenbach seed sets": _guarded("Dosenbach"),
}

# Terms that indicate SOME atlas/parcellation was used even if unnamed
GENERIC_ATLAS_HINTS = re.compile(
    r"\b(atlas|parcellation|parcellate|template|regions?[\s\-]of[\s\-]interest|\bROIs?\b)\b",
    re.IGNORECASE,
)

# Compiled case-INSENSITIVE; individual acronym tokens opt back into
# case-sensitivity via scoped `(?-i:...)` groups inside their patterns.
COMPILED = {name: [re.compile(p, re.IGNORECASE) for p in pats]
            for name, pats in ATLAS_REGISTRY.items()}


def safe_filename(name: str) -> str:
    """Mirror PaperDownloader._safe_filename so we can map PDFs back to papers."""
    cleaned = "".join(c if c.isalnum() else "_" for c in name)
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    return f"{cleaned[:70]}_{digest}"


def build_pdf_index(bib_path: Path) -> dict:
    """Map PDF stem -> {title, doi} using the bib the downloader worked from."""
    index = {}
    if not bib_path or not bib_path.exists():
        return index
    try:
        from src.utils import load_papers_from_bib
    except Exception:
        return index
    for p in load_papers_from_bib(bib_path):
        paper_id = p.doi or getattr(p, "arxiv_id", None) or p.title or p.url
        if not paper_id:
            continue
        index[safe_filename(paper_id)] = {"title": p.title or "", "doi": p.doi or ""}
    return index


_REF_HEADING = re.compile(
    r"(?im)^[ \t]*(references|bibliography|literature cited|reference list)[ \t]*$")


def strip_references(text: str) -> str:
    """Drop the reference list so bibliography author names aren't mistaken for
    atlas usage. Cuts at the first 'References'/'Bibliography' heading that
    appears in the back 40% of the document (earlier mentions, e.g. "see
    References", are left alone). Returns the text unchanged if no heading found.
    """
    n = len(text)
    for m in _REF_HEADING.finditer(text):
        if m.start() > 0.4 * n:
            return text[:m.start()]
    return text


def extract_text(pdf_path: Path, max_pages: int = 60) -> str:
    import fitz
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return ""
    parts = []
    try:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            parts.append(page.get_text())
    finally:
        doc.close()
    return "\n".join(parts)


def find_atlases(text: str):
    """Return (list of atlas canonical names matched, first snippet per atlas)."""
    hits = {}
    for name, patterns in COMPILED.items():
        for pat in patterns:
            m = pat.search(text)
            if m:
                s = max(0, m.start() - 40)
                e = min(len(text), m.end() + 40)
                snippet = " ".join(text[s:e].split())
                hits[name] = snippet
                break
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", default="results/pdfs")
    ap.add_argument("--bib", default=None,
                    help="bib to map PDFs->titles (default: references_filtered_ai.bib "
                         "then references_filtered.bib)")
    ap.add_argument("--out", default="results/atlas_usage.csv")
    ap.add_argument("--all-pdfs", action="store_true",
                    help="scan every PDF in --pdf-dir, including ones absent "
                         "from the bib (default: bib members only)")
    args = ap.parse_args()

    pdf_dir = (ROOT / args.pdf_dir) if not Path(args.pdf_dir).is_absolute() else Path(args.pdf_dir)
    pdfs = sorted(pdf_dir.glob("*.pdf")) if pdf_dir.exists() else []
    if not pdfs:
        print(f"No PDFs found in {pdf_dir} yet. Run this after downloads complete.")
        return 0

    if args.bib:
        bib = Path(args.bib)
    else:
        cand = [pdf_dir.parent / "references_filtered_ai.bib",
                pdf_dir.parent / "references_filtered.bib"]
        bib = next((c for c in cand if c.exists()), None)
    index = build_pdf_index(bib) if bib else {}

    # results/pdfs accumulates across runs, so it holds PDFs from screening
    # passes that are no longer part of the corpus. Counting those would put
    # papers the filter has since excluded back into the atlas totals, so by
    # default only PDFs named in the bib are scanned.
    if index and not args.all_pdfs:
        in_bib = [p for p in pdfs if p.stem in index]
        skipped = len(pdfs) - len(in_bib)
        if skipped:
            print(f"Skipping {skipped} PDFs not in {bib.name} "
                  f"(left over from an earlier run; --all-pdfs to include them)")
        pdfs = in_bib
        if not pdfs:
            print("No PDFs matched the bib - is this the bib the downloader used?")
            return 1

    print(f"Scanning {len(pdfs)} PDFs in {pdf_dir}"
          + (f" (titles from {bib.name})" if bib else " (no bib mapping)"))

    rows = []
    match_rows = []  # long format: one row per (paper, atlas) with its snippet
    from collections import Counter
    atlas_counts = Counter()
    named_papers = 0
    generic_only = 0
    none_papers = 0

    for i, pdf in enumerate(pdfs, 1):
        text = strip_references(extract_text(pdf))
        meta = index.get(pdf.stem, {})
        if not text.strip():
            rows.append({"title": meta.get("title", ""), "doi": meta.get("doi", ""),
                         "file": pdf.name, "n_atlases": 0, "atlases": "",
                         "status": "no_text (scanned/encrypted?)", "snippet": ""})
            none_papers += 1
            continue
        hits = find_atlases(text)
        if hits:
            named_papers += 1
            for name, snippet in hits.items():
                atlas_counts[name] += 1
                match_rows.append({"file": pdf.name, "doi": meta.get("doi", ""),
                                   "title": meta.get("title", "")[:120],
                                   "atlas": name, "snippet": snippet[:200]})
        elif GENERIC_ATLAS_HINTS.search(text):
            generic_only += 1
        else:
            none_papers += 1
        rows.append({
            "title": meta.get("title", "")[:120],
            "doi": meta.get("doi", ""),
            "file": pdf.name,
            "n_atlases": len(hits),
            "atlases": "; ".join(hits.keys()),
            "status": "named" if hits else ("generic_atlas_terms_only"
                       if GENERIC_ATLAS_HINTS.search(text) else "no_atlas_found"),
            "snippet": (list(hits.values())[0] if hits else "")[:160],
        })
        if i % 25 == 0:
            print(f"  ...{i}/{len(pdfs)}")

    out = (ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["title", "doi", "file", "n_atlases",
                                          "atlases", "status", "snippet"])
        w.writeheader()
        w.writerows(rows)

    summ = out.parent / "atlas_summary.csv"
    with open(summ, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["atlas", "n_papers"])
        for name, n in atlas_counts.most_common():
            w.writerow([name, n])

    matches = out.parent / "atlas_matches.csv"
    with open(matches, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "doi", "title", "atlas", "snippet"])
        w.writeheader()
        w.writerows(match_rows)

    print("\n" + "=" * 70)
    print("ATLAS EXTRACTION SUMMARY")
    print("=" * 70)
    print(f"PDFs scanned:                 {len(pdfs)}")
    print(f"  with a NAMED atlas:         {named_papers}")
    print(f"  generic atlas terms only:   {generic_only}")
    print(f"  no atlas mention / no text: {none_papers}")
    print(f"\nTop atlases:")
    for name, n in atlas_counts.most_common(20):
        print(f"  {n:4d}  {name}")
    print(f"\nPer-paper table:  {out}")
    print(f"Atlas counts:     {summ}")
    print(f"Evidence table:   {matches}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
