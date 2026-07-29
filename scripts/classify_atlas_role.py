#!/usr/bin/env python3
"""
Decide WHAT ROLE each atlas played in each paper - the distinction that actually
matters for an "which atlas was used" review.

Naming an atlas is not the same as using it as a parcellation. "dHCP" in
particular means four different things across this literature:

  dataset            "127 infants from the dHCP cohort"        -> not an atlas
  pipeline           "preprocessed with the dHCP pipeline"     -> only counts if
                     (the dHCP structural pipeline runs Draw-EM, which DOES
                      produce 87 labelled regions - so this can yield ROIs)
  template_only      "registered to the dHCP 40-week template" -> no ROIs
  roi_parcellation   "parcellated into 87 regions; mean time
                      series extracted per region"             -> THE ONE THAT COUNTS

Only `roi_parcellation` gives regions you can extract values from. This script
classifies every (paper, atlas) pair into one of those roles, with a verbatim
quote and, where stated, the number of regions.

Output: results/atlas_roles.csv          one row per paper x atlas
        results/atlas_roi_summary.csv     parcellations that yield extractable ROIs

Usage:
    python scripts/classify_atlas_role.py
    python scripts/classify_atlas_role.py --limit 20
    python scripts/classify_atlas_role.py --atlas dHCP
"""

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.extract_atlases import (  # noqa: E402
    COMPILED as _RX, extract_text, strip_references,
)
from scripts.label_atlases_llm import _CANON_TO_REGISTRY, parse_json  # noqa: E402

ROLES = ("roi_parcellation", "roi_unsupported", "template_only",
         "tissue_segmentation", "dataset", "pipeline", "unclear")

# Language that signals regions were actually defined/extracted.
ROI_SIGNAL = re.compile(
    r"(parcellat\w+|regions? of interest|\bROIs?\b|\bnodes?\b|"
    r"\d{2,3}\s*(?:regions|areas|parcels|labels|structures|nodes)|"
    r"(?:mean|average)\s+(?:time\s?series|signal|BOLD)|"
    r"extract\w*\s+(?:from|per|for)\s+(?:each\s+)?(?:region|ROI|parcel)|"
    r"regional\s+(?:volume|value|measure|connectivity))", re.IGNORECASE)

REGION_COUNT = re.compile(
    r"\b(\d{2,3})\s*(?:cortical\s+|anatomical\s+|brain\s+|distinct\s+)?"
    r"(regions|areas|parcels|labels|structures|nodes|ROIs)\b", re.IGNORECASE)

WINDOW = 460
MAX_EVIDENCE = 3600

SYSTEM = """You are a neuroimaging methods expert. Given excerpts from a paper \
and the name of one atlas/resource, decide WHAT ROLE that resource played.

Choose exactly one role:
- "roi_parcellation": it provided LABELLED REGIONS the authors extracted values \
from (regional volumes, per-region time series, network nodes, ROI connectivity).
- "template_only": used ONLY as a spatial target for registration/normalization. \
No regional values extracted from it.
- "tissue_segmentation": used only to segment tissue classes (grey/white matter, \
CSF), not to define anatomical regions of interest.
- "dataset": it names a DATA SOURCE or cohort the scans came from, not an atlas.
- "pipeline": it names PREPROCESSING SOFTWARE only.
- "unclear": the excerpts do not say.

IMPORTANT: a resource can be a dataset AND supply a parcellation. Choose \
"roi_parcellation" whenever the excerpts show labelled regions being used for \
measurement, even if it is also a cohort or pipeline.

Respond with ONLY valid JSON:
{"role": "roi_parcellation", "n_regions": 87, "evidence_quote": "verbatim \
sentence from the excerpts", "confidence": 0.9}

- n_regions: integer number of regions if explicitly stated, else null
- evidence_quote: ONE verbatim sentence copied from the excerpts
- confidence: 0.0 to 1.0"""


def mention_patterns(canon: str):
    """Regexes that locate this atlas in the text."""
    key = _CANON_TO_REGISTRY.get(canon)
    if key and key in _RX:
        return _RX[key]
    if canon.startswith("other: "):
        raw = canon[7:].strip()
        toks = [t for t in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", raw)
                if t.lower() not in {"atlas", "template", "brain", "et", "al"}]
        if toks:
            return [re.compile(rf"\b{re.escape(toks[0])}", re.IGNORECASE)]
    return [re.compile(r"atlas|template|parcellat", re.IGNORECASE)]


PROXIMITY = 600  # chars: how close ROI language must sit to an atlas mention


def build_evidence(text: str, canon: str) -> tuple:
    """Windows around this atlas's mentions, plus ROI-language windows.

    Returns (evidence, n_mentions, roi_near_mention). `roi_near_mention` is the
    honest signal: ROI/parcellation language within PROXIMITY chars of where the
    atlas is actually named. Global ROI language is NOT enough - almost every
    fMRI paper mentions ROIs somewhere, which made the model attribute a
    parcellation role to atlases that were only cited as a dataset.
    """
    spans = []
    mention_pos = []
    for pat in mention_patterns(canon):
        for m in pat.finditer(text):
            spans.append((max(0, m.start() - WINDOW), min(len(text), m.end() + WINDOW)))
            mention_pos.append((m.start(), m.end()))
            if len(mention_pos) >= 8:
                break
        if len(mention_pos) >= 8:
            break
    n_mentions = len(mention_pos)

    roi_near = any(
        any(ms - PROXIMITY <= m.start() <= me + PROXIMITY for ms, me in mention_pos)
        for m in ROI_SIGNAL.finditer(text)
    )
    for m in list(ROI_SIGNAL.finditer(text))[:6]:
        spans.append((max(0, m.start() - 300), min(len(text), m.end() + 300)))
    if not spans:
        return "", 0, False
    spans.sort()
    merged = [spans[0]]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    out, total = [], 0
    for s, e in merged:
        chunk = " ".join(text[s:e].split())
        if total + len(chunk) > MAX_EVIDENCE:
            chunk = chunk[: max(0, MAX_EVIDENCE - total)]
        if chunk:
            out.append(chunk)
            total += len(chunk)
        if total >= MAX_EVIDENCE:
            break
    return "\n---\n".join(out), n_mentions, roi_near


def ask(evidence: str, atlas: str, model: str, url: str, cache: Path,
        retries: int = 3) -> dict:
    key = hashlib.md5(f"role1|{model}|{atlas}|{evidence}".encode()).hexdigest()
    cf = cache / f"{key}.json"
    if cf.exists():
        try:
            return json.loads(cf.read_text(encoding="utf-8"))
        except Exception:
            pass
    prompt = (f"{SYSTEM}\n\nResource to classify: \"{atlas}\"\n\n"
              f"Excerpts:\n\"\"\"\n{evidence}\n\"\"\"\n\n"
              f"What role did \"{atlas}\" play? JSON only.")
    last = None
    for attempt in range(retries):
        try:
            r = requests.post(f"{url.rstrip('/')}/api/generate",
                              json={"model": model, "prompt": prompt, "stream": False,
                                    "options": {"temperature": 0.0, "num_ctx": 8192,
                                                "num_predict": 250}}, timeout=300)
            r.raise_for_status()
            p = parse_json(r.json()["response"])
            role = str(p.get("role", "unclear")).strip().lower()
            if role not in ROLES:
                role = "unclear"
            nr = p.get("n_regions")
            try:
                nr = int(nr) if nr not in (None, "", "null") else None
            except (TypeError, ValueError):
                nr = None
            res = {"role": role, "n_regions": nr,
                   "evidence_quote": str(p.get("evidence_quote", ""))[:400],
                   "confidence": float(p.get("confidence", 0.0) or 0.0), "error": ""}
            cf.write_text(json.dumps(res), encoding="utf-8")
            return res
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return {"role": "unclear", "n_regions": None, "evidence_quote": "",
            "confidence": 0.0, "error": str(last)[:120]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", default="results/atlas_final.csv")
    ap.add_argument("--pdf-dir", default="results/pdfs")
    ap.add_argument("--out", default="results/atlas_roles.csv")
    # see the note in label_atlases_llm.py on why this is no longer llama3.2:3b
    ap.add_argument("--model", default="gemma3:4b")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--cache-dir", default="results/atlas_role_cache")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--atlas", default="", help="only this atlas (substring)")
    args = ap.parse_args()

    def rooted(p):
        p = Path(p)
        return p if p.is_absolute() else ROOT / p

    final_p, pdf_dir, out = rooted(args.final), rooted(args.pdf_dir), rooted(args.out)
    cache = rooted(args.cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    if not final_p.exists():
        print(f"Missing {final_p} - run scripts/atlas_report.py first.")
        return 1

    # Fail fast if Ollama is down. Without this the run "succeeds" while every
    # call errors out and every pair silently lands in `unclear` - which looks
    # like a finding but is an outage. (Happened once; hence the check.)
    try:
        requests.get(f"{args.ollama_url.rstrip('/')}/api/tags", timeout=5).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Ollama unreachable at {args.ollama_url} ({exc}).\n"
              f"Start it with:  ollama serve")
        return 2

    pairs = []
    for r in csv.DictReader(open(final_p, encoding="utf-8")):
        for a in (r.get("atlases") or "").split("; "):
            if a and (not args.atlas or args.atlas.lower() in a.lower()):
                pairs.append((r, a))
    if args.limit:
        pairs = pairs[: args.limit]
    print(f"Classifying {len(pairs)} (paper x atlas) pairs with {args.model}")

    rows, t0 = [], time.time()
    role_counts, roi_by_atlas = Counter(), Counter()
    text_cache = {}
    consecutive_errors = 0

    for i, (r, atlas) in enumerate(pairs, 1):
        fn = r["file"]
        if fn not in text_cache:
            if len(text_cache) > 60:
                text_cache.clear()
            text_cache[fn] = strip_references(extract_text(pdf_dir / fn))
        text = text_cache[fn]
        evidence, n_mentions, roi_near = (build_evidence(text, atlas) if text.strip()
                                          else ("", 0, False))

        if not evidence:
            res = {"role": "unclear", "n_regions": None, "evidence_quote": "",
                   "confidence": 0.0, "error": "no evidence text"}
        else:
            res = ask(evidence, atlas, args.model, args.ollama_url, cache)
            # A dead server mid-run would otherwise fill the rest of the table
            # with bogus "unclear" rows; stop instead so partial output is honest.
            consecutive_errors = consecutive_errors + 1 if res["error"] else 0
            if consecutive_errors >= 10:
                print(f"\nABORTING at pair {i}: 10 consecutive Ollama errors "
                      f"({res['error']}). Results so far are written; re-run to resume "
                      f"(successful answers are cached).")
                break

        # deterministic cross-check: an explicit region count near the atlas name
        rc = None
        for m in REGION_COUNT.finditer(evidence):
            v = int(m.group(1))
            if 4 <= v <= 999:
                rc = v
                break
        roi_lang = bool(ROI_SIGNAL.search(evidence))
        quote_ok = ""
        if res["evidence_quote"]:
            q = res["evidence_quote"][:60].strip()
            quote_ok = "yes" if q and q in " ".join(text.split()) else "no"

        role = res["role"]
        # Guard: claiming this atlas supplied the ROIs requires ROI/parcellation
        # language NEAR where the atlas is named. Global ROI language is not
        # enough - nearly every fMRI paper says "ROI" somewhere, and allowing
        # that made the model call a dataset citation a parcellation.
        if role == "roi_parcellation" and not roi_near:
            role = "roi_unsupported"
        role_counts[role] += 1
        if role == "roi_parcellation":
            roi_by_atlas[atlas] += 1

        rows.append({
            "file": fn, "doi": r.get("doi", ""), "year": r.get("year", ""),
            "title": r.get("title", "")[:110], "atlas": atlas, "role": role,
            "n_regions": res["n_regions"] if res["n_regions"] else (rc or ""),
            "regions_in_text": rc or "", "roi_language": "yes" if roi_lang else "no",
            "roi_near_mention": "yes" if roi_near else "no",
            "n_mentions": n_mentions, "confidence": f"{res['confidence']:.2f}",
            "quote_verbatim": quote_ok,
            "evidence_quote": res["evidence_quote"].replace("\n", " ")[:300],
            "label_source": r.get("source", ""), "error": res["error"],
        })
        if i % 25 == 0 or i == len(pairs):
            el = time.time() - t0
            print(f"  {i}/{len(pairs)} ({el/i:.1f}s/pair, "
                  f"~{(len(pairs)-i)*el/i/60:.0f} min left) roi={role_counts['roi_parcellation']}",
                  flush=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # papers (not pairs) that have >=1 genuine ROI parcellation
    roi_papers = {r["file"] for r in rows if r["role"] == "roi_parcellation"}
    fs = out.parent / "atlas_roi_summary.csv"
    with open(fs, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["atlas", "n_papers_as_ROI_parcellation"])
        for a, n in roi_by_atlas.most_common():
            w.writerow([a, n])

    print("\n" + "=" * 70)
    print(f"ATLAS ROLE CLASSIFICATION  ({(time.time()-t0)/60:.1f} min)")
    print("=" * 70)
    print(f"pairs classified: {len(rows)}")
    for role in ROLES:
        print(f"  {role:22} {role_counts[role]}")
    print(f"\npapers with >=1 extractable ROI parcellation: {len(roi_papers)}")
    print("\nAtlases actually used as ROI parcellations:")
    for a, n in roi_by_atlas.most_common(20):
        print(f"  {n:4d}  {a}")
    by_role_atlas = defaultdict(Counter)
    for r in rows:
        by_role_atlas[r["atlas"]][r["role"]] += 1
    print("\nRole split for the headline atlases:")
    for a in ["dHCP", "AAL", "UNC neonatal/infant", "CRL / Gholipour (fetal-neonatal)",
              "Kuklisova-Murgasova neonatal", "MNI152 / ICBM"]:
        if a in by_role_atlas:
            c = by_role_atlas[a]
            print(f"  {a:34} " + "  ".join(f"{k}={c[k]}" for k in ROLES if c[k]))
    print(f"\nPer pair:   {out}\nROI counts: {fs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
