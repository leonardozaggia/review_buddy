#!/usr/bin/env python3
"""
Label each downloaded paper with the brain atlas it ACTUALLY USED, by having a
local LLM read the paper's atlas-relevant Methods passages.

Why this exists: `extract_atlases.py` is a regex pass. It is fast and precise on
names it knows, but it cannot tell "we registered our data to the UNC atlas"
(usage) from "see Gousias et al. for a review" (a citation), and it misses any
atlas whose name is not in the registry. This script closes both gaps:

  1. Pull the text, drop the reference list.
  2. Keep only the passages that talk about atlases/parcellation/registration -
     typically the Methods - so the model reads evidence, not the whole paper.
  3. Ask the LLM which atlas the AUTHORS USED for their own analysis, and make
     it quote the sentence that proves it.

Every label therefore carries a verbatim quote, so a human can verify it without
reopening the PDF. Responses are cached, so the run is resumable.

Output: results/atlas_labels_llm.csv
        (file, doi, title, atlas_used, atlases, canonical, confidence,
         evidence_quote, regex_atlases, agreement)

Usage:
    python scripts/label_atlases_llm.py                     # all PDFs
    python scripts/label_atlases_llm.py --limit 20          # quick sample
    python scripts/label_atlases_llm.py --only generic_atlas_terms_only,no_atlas_found
    python scripts/label_atlases_llm.py --model llama3.1:8b
"""

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.extract_atlases import (  # noqa: E402
    build_pdf_index, extract_text, strip_references, find_atlases,
)

# Passages worth showing the model: anything about atlases, parcellation,
# registration, segmentation or ROI definition.
EVIDENCE_RE = re.compile(
    r"(atlas|atlases|parcellat\w+|template|segment\w+|registrat\w+|registered|"
    r"normali[sz]\w+|labell?ing|\bROIs?\b|regions? of interest|standard space)",
    re.IGNORECASE,
)

WINDOW = 420          # chars of context to keep on each side of a hit
MAX_EVIDENCE = 3800   # cap total evidence sent to the model

SYSTEM = """You are a neuroimaging methods expert. You read excerpts from a \
neonatal fMRI paper and report which brain atlas, parcellation, or template the \
authors USED in their own analysis.

CRITICAL RULES:
- Report an atlas ONLY if the authors used it for their own data: registration, \
spatial normalization, segmentation, parcellation, or ROI definition.
- Do NOT report atlases that merely appear in citations, background, or \
comparisons to other studies' work.
- Use the standard short name: dHCP, UNC infant, M-CRIB, ALBERTs, Draw-EM, \
Edinburgh Neonatal Atlas, JHU neonatal, Serag, Gousias, Fonov/NIHPD, AAL, \
Harvard-Oxford, Desikan-Killiany, Destrieux, Schaefer, Yeo, Power-264, Gordon, \
Glasser/HCP-MMP, Brainnetome, Shen-268, Craddock, Talairach, MNI152/ICBM.
- A study-specific or custom-built template counts: name it "study-specific template".
- If the authors used no atlas (e.g. seed-based or ICA analysis only), say so.

Respond with ONLY a valid JSON object, no other text:
{"atlas_used": true, "atlases": ["dHCP"], "evidence_quote": "verbatim sentence \
from the excerpts", "confidence": 0.9}

- atlas_used: true or false
- atlases: list of short names, [] if none
- evidence_quote: ONE verbatim sentence copied from the excerpts proving usage ("" if none)
- confidence: 0.0 to 1.0"""

# Map free-text model output onto canonical families for counting.
CANON = [
    ("dHCP", ["dhcp", "developing human connectome"]),
    ("UNC neonatal/infant", ["unc", "chapel hill", "bcp", "infant 0-1-2", "unc-bcp"]),
    ("M-CRIB", ["m-crib", "mcrib", "melbourne children"]),
    ("ALBERTs", ["albert"]),
    ("Draw-EM", ["draw-em", "drawem"]),
    ("Edinburgh Neonatal Atlas (ENA)", ["edinburgh", "ena33", "ena50"]),
    ("JHU neonatal (Oishi)", ["jhu", "oishi"]),
    ("Serag neonatal", ["serag"]),
    ("Shi neonatal", ["shi et al", "shi 2011", "shi neonatal"]),
    ("CRL / Gholipour (fetal-neonatal)", ["gholipour", "crl", "computational radiology"]),
    ("Kuklisova-Murgasova neonatal", ["kuklisova", "murgasova"]),
    ("LPBA40", ["lpba"]),
    ("NeuroMark (ICN template)", ["neuromark"]),
    ("Gousias neonatal", ["gousias"]),
    ("Fonov / NIHPD infant", ["fonov", "nihpd"]),
    ("study-specific template", ["study-specific", "study specific", "custom template",
                                 "in-house template", "cohort-specific"]),
    ("AAL", ["aal", "automated anatomical label"]),
    ("Harvard-Oxford", ["harvard"]),
    ("Desikan-Killiany", ["desikan", "killiany", "aparc"]),
    ("Destrieux", ["destrieux", "a2009s"]),
    ("Schaefer", ["schaefer"]),
    ("Yeo networks", ["yeo"]),
    ("Power-264", ["power"]),
    ("Gordon", ["gordon"]),
    ("Glasser / HCP-MMP", ["glasser", "hcp-mmp", "hcpmmp", "multimodal parcellation"]),
    ("Brainnetome", ["brainnetome"]),
    ("Shen-268", ["shen"]),
    ("Craddock", ["craddock"]),
    ("Talairach", ["talairach"]),
    ("MNI152 / ICBM", ["mni", "icbm", "montreal neuro"]),
    ("FreeSurfer (unspecified)", ["freesurfer", "infant freesurfer"]),
]


# A vague description ("a neonatal atlas", "an age-appropriate template") is a
# real finding - the study used SOME infant atlas but only cited it by number -
# so it gets its own bucket instead of a junk "other:" label.
VAGUE_RE = re.compile(
    r"^(a|an|the)?\s*(existing|standard|published|age[\s\-]?appropriate|"
    r"neonatal|infant|newborn|pediatric|paediatric|custom)?\s*"
    r"(labell?ed\s+)?(segmentation\s+|anatomical\s+|brain\s+)?"
    r"(atlas|atlases|template|parcellation)$", re.IGNORECASE)


def canonicalize(name: str) -> str:
    low = name.lower().strip()
    if not low:
        return ""
    for canon, keys in CANON:
        if any(k in low for k in keys):
            return canon
    if VAGUE_RE.match(low):
        return "unnamed neonatal atlas/template (cited only)"
    return f"other: {name.strip()[:40]}"


# --- grounding -------------------------------------------------------------
# The LLM will happily invent a specific name when the text only says "an
# existing neonatal atlas" (observed: it answered "dHCP" for a paper where the
# string dHCP never appears). So every named label must be VERIFIED to occur in
# the paper text before it is counted. We reuse the strict regex registry for
# this, which is exactly what it is good at.
from scripts.extract_atlases import COMPILED as _RX  # noqa: E402

_CANON_TO_REGISTRY = {
    "dHCP": "dHCP (developing Human Connectome Project)",
    "UNC neonatal/infant": "UNC neonatal/infant (UNC-Chapel Hill)",
    "M-CRIB": "M-CRIB (Melbourne Children's Regional Infant Brain)",
    "ALBERTs": "ALBERT / ALBERTs (Gousias/Imperial)",
    "Draw-EM": "Draw-EM (developing brain segmentation)",
    "Edinburgh Neonatal Atlas (ENA)": "Edinburgh Neonatal Atlas (ENA)",
    "JHU neonatal (Oishi)": "JHU neonatal (Oishi)",
    "Serag neonatal": "Serag neonatal atlas",
    "Shi neonatal": "Shi neonatal atlas",
    "CRL / Gholipour (fetal-neonatal)": "CRL / Gholipour (fetal-neonatal)",
    "Kuklisova-Murgasova neonatal": "Kuklisova-Murgasova neonatal",
    "LPBA40": "LPBA40 (LONI Probabilistic Brain Atlas)",
    "NeuroMark (ICN template)": "NeuroMark (ICN template)",
    "Gousias neonatal": "Gousias neonatal atlas",
    "Fonov / NIHPD infant": "Fonov / NIHPD infant templates",
    "AAL": "AAL (Automated Anatomical Labeling)",
    "Harvard-Oxford": "Harvard-Oxford",
    "Desikan-Killiany": "Desikan-Killiany (FreeSurfer)",
    "Destrieux": "Destrieux (FreeSurfer)",
    "Schaefer": "Schaefer",
    "Yeo networks": "Yeo networks",
    "Power-264": "Power (264)",
    "Gordon": "Gordon",
    "Glasser / HCP-MMP": "Glasser / HCP-MMP",
    "Brainnetome": "Brainnetome",
    "Shen-268": "Shen (268)",
    "Craddock": "Craddock",
    "Talairach": "Talairach",
    "MNI152 / ICBM": "ICBM / MNI152 template",
}

_EXTRA_VERIFY = {
    "study-specific template": [
        re.compile(r"(study|cohort|group|age)[\s\-]?specific\s+(atlas|template)", re.I),
        re.compile(r"(constructed|created|built|generated)[^.\n]{0,60}template", re.I),
        re.compile(r"(custom|in[\s\-]house|our own)\s+(atlas|template)", re.I),
    ],
    "FreeSurfer (unspecified)": [re.compile(r"FreeSurfer", re.I)],
    "unnamed neonatal atlas/template (cited only)": [
        re.compile(r"(neonat\w*|infant|newborn|age[\s\-]?appropriate|existing)"
                   r"[^.\n]{0,25}(atlas|template)", re.I),
        re.compile(r"(atlas|template)[^.\n]{0,25}(neonat\w*|infant|newborn)", re.I),
    ],
}


def verify_in_text(canon: str, text: str) -> bool:
    """True if this atlas name is actually attested in the paper's text."""
    key = _CANON_TO_REGISTRY.get(canon)
    if key and key in _RX:
        return any(p.search(text) for p in _RX[key])
    if canon in _EXTRA_VERIFY:
        return any(p.search(text) for p in _EXTRA_VERIFY[canon])
    if canon.startswith("other: "):
        raw = canon[7:].strip()
        toks = [t for t in re.findall(r"[A-Za-z\-]{4,}", raw) if t.lower() not in
                {"atlas", "template", "brain", "parcellation", "segmentation"}]
        if not toks:
            return bool(re.search(r"atlas|template|parcellat", text, re.I))
        return all(re.search(rf"\b{re.escape(t)}", text, re.I) for t in toks[:3])
    return False


def build_evidence(text: str) -> str:
    """Merge windows around atlas-related mentions into one compact excerpt."""
    spans = []
    for m in EVIDENCE_RE.finditer(text):
        spans.append((max(0, m.start() - WINDOW), min(len(text), m.end() + WINDOW)))
        if len(spans) > 400:
            break
    if not spans:
        return ""
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
    return "\n---\n".join(out)


def parse_json(raw: str) -> dict:
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        s, e = raw.find("{"), raw.rfind("}") + 1
        if s != -1 and e > s:
            try:
                return json.loads(raw[s:e])
            except json.JSONDecodeError:
                pass
    raise ValueError(f"unparseable: {raw[:160]}")


def ask_llm(evidence: str, model: str, url: str, cache_dir: Path,
            retries: int = 3) -> dict:
    key = hashlib.md5(f"v2|{model}|{evidence}".encode("utf-8")).hexdigest()
    cf = cache_dir / f"{key}.json"
    if cf.exists():
        try:
            return json.loads(cf.read_text(encoding="utf-8"))
        except Exception:
            pass
    prompt = (f"{SYSTEM}\n\nExcerpts from the paper:\n\"\"\"\n{evidence}\n\"\"\"\n\n"
              "Which atlas did the authors USE? Respond with JSON only.")
    last = None
    for attempt in range(retries):
        try:
            r = requests.post(
                f"{url.rstrip('/')}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False,
                      # num_ctx must be large enough to hold the evidence -
                      # Ollama's default (2048) would silently truncate it.
                      "options": {"temperature": 0.0, "num_ctx": 8192,
                                  "num_predict": 300}},
                timeout=300,
            )
            r.raise_for_status()
            parsed = parse_json(r.json()["response"])
            result = {
                "atlas_used": bool(parsed.get("atlas_used", False)),
                "atlases": [str(a) for a in (parsed.get("atlases") or []) if str(a).strip()],
                "evidence_quote": str(parsed.get("evidence_quote", ""))[:400],
                "confidence": float(parsed.get("confidence", 0.0) or 0.0),
                "error": "",
            }
            cf.write_text(json.dumps(result), encoding="utf-8")
            return result
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return {"atlas_used": False, "atlases": [], "evidence_quote": "",
            "confidence": 0.0, "error": str(last)[:120]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", default="results/pdfs")
    ap.add_argument("--usage-csv", default="results/atlas_usage.csv",
                    help="regex pass output, used for --only and agreement")
    ap.add_argument("--out", default="results/atlas_labels_llm.csv")
    ap.add_argument("--model", default="llama3.2:3b")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--cache-dir", default="results/atlas_llm_cache")
    ap.add_argument("--limit", type=int, default=0, help="only first N PDFs (sampling)")
    ap.add_argument("--only", default="", help="comma-separated regex-pass statuses to process")
    args = ap.parse_args()

    def rooted(p):
        p = Path(p)
        return p if p.is_absolute() else ROOT / p

    pdf_dir, out = rooted(args.pdf_dir), rooted(args.out)
    cache_dir = rooted(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {pdf_dir}")
        return 1

    # regex pass results: for --only filtering and for the agreement column
    regex_by_file = {}
    ucsv = rooted(args.usage_csv)
    if ucsv.exists():
        with open(ucsv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                regex_by_file[row["file"]] = row
    if args.only:
        want = {s.strip() for s in args.only.split(",") if s.strip()}
        pdfs = [p for p in pdfs if regex_by_file.get(p.name, {}).get("status") in want]
        print(f"--only {sorted(want)} -> {len(pdfs)} PDFs")
    if args.limit:
        pdfs = pdfs[: args.limit]

    bib = next((c for c in [pdf_dir.parent / "references_filtered_ai.bib",
                            pdf_dir.parent / "references_filtered.bib"] if c.exists()), None)
    index = build_pdf_index(bib) if bib else {}

    print(f"Labelling {len(pdfs)} PDFs with {args.model} (cache: {cache_dir.name})")
    rows, t0 = [], time.time()
    n_used = n_none = n_err = n_hallucinated = 0

    for i, pdf in enumerate(pdfs, 1):
        meta = index.get(pdf.stem, {})
        text = strip_references(extract_text(pdf))
        # whitespace-normalised copy, for checking the model quoted real text
        norm_text = " ".join(text.split())
        evidence = build_evidence(text) if text.strip() else ""
        regex_row = regex_by_file.get(pdf.name, {})
        regex_atlases = regex_row.get("atlases", "")

        if not evidence:
            rows.append({"file": pdf.name, "doi": meta.get("doi", ""),
                         "title": meta.get("title", "")[:120], "atlas_used": "",
                         "atlases": "", "canonical": "", "rejected_unverified": "",
                         "confidence": "", "quote_grounded": "",
                         "evidence_quote": "", "regex_atlases": regex_atlases,
                         "agreement": "no_evidence_text", "error": "no atlas-related text"})
            n_none += 1
        else:
            res = ask_llm(evidence, args.model, args.ollama_url, cache_dir)
            proposed = sorted({c for c in (canonicalize(a) for a in res["atlases"]) if c})
            # Grounding: keep only names actually attested in the paper text.
            canon = [c for c in proposed if verify_in_text(c, text)]
            rejected = [c for c in proposed if c not in canon]
            if rejected:
                n_hallucinated += len(rejected)
            if res["error"]:
                n_err += 1
            elif res["atlas_used"] and canon:
                n_used += 1
            else:
                n_none += 1
            llm_set = set(canon)
            rx_set = {a.split(" (")[0].strip() for a in regex_atlases.split("; ") if a}
            if not llm_set and not rx_set:
                agree = "both_none"
            elif llm_set and not rx_set:
                agree = "llm_only"
            elif rx_set and not llm_set:
                agree = "regex_only"
            else:
                agree = "overlap" if any(
                    any(w and w in r for w in c.lower().split()[:1]) or c.lower()[:5] in r.lower()
                    for c in llm_set for r in rx_set) else "differ"
            rows.append({
                "file": pdf.name, "doi": meta.get("doi", ""),
                "title": meta.get("title", "")[:120],
                "atlas_used": "yes" if (res["atlas_used"] and canon) else "no",
                "atlases": "; ".join(res["atlases"]),
                "canonical": "; ".join(canon),
                "rejected_unverified": "; ".join(rejected),
                "confidence": f"{res['confidence']:.2f}",
                "quote_grounded": "yes" if (res["evidence_quote"][:60].strip()
                                            and res["evidence_quote"][:60].strip() in norm_text)
                                  else ("" if not res["evidence_quote"] else "no"),
                "evidence_quote": res["evidence_quote"].replace("\n", " ")[:300],
                "regex_atlases": regex_atlases, "agreement": agree,
                "error": res["error"],
            })

        if i % 10 == 0 or i == len(pdfs):
            el = time.time() - t0
            rate = el / i
            print(f"  {i}/{len(pdfs)}  ({rate:.1f}s/paper, "
                  f"~{(len(pdfs) - i) * rate / 60:.0f} min left)  "
                  f"used={n_used} none={n_none} err={n_err}", flush=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "doi", "title", "atlas_used", "atlases",
                                          "canonical", "rejected_unverified", "confidence",
                                          "quote_grounded", "evidence_quote",
                                          "regex_atlases", "agreement", "error"])
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    counts = Counter()
    for r in rows:
        for c in (r["canonical"] or "").split("; "):
            if c:
                counts[c] += 1
    summ = out.parent / "atlas_summary_llm.csv"
    with open(summ, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["atlas", "n_papers"])
        for name, n in counts.most_common():
            w.writerow([name, n])

    print("\n" + "=" * 70)
    print(f"LLM LABELLING COMPLETE  ({(time.time() - t0) / 60:.1f} min)")
    print("=" * 70)
    print(f"papers labelled with an atlas: {n_used}")
    print(f"no atlas / no evidence:        {n_none}")
    print(f"errors:                        {n_err}")
    print(f"unverified names rejected:     {n_hallucinated}  (LLM named an atlas "
          f"absent from the paper text)")
    ungrounded = sum(1 for r in rows if r.get("quote_grounded") == "no")
    print(f"quotes not found verbatim:     {ungrounded}")
    print(f"\nagreement vs regex: {dict(Counter(r['agreement'] for r in rows))}")
    print("\nTop atlases (LLM):")
    for name, n in counts.most_common(25):
        print(f"  {n:4d}  {name}")
    print(f"\nPer-paper labels: {out}")
    print(f"Atlas counts:     {summ}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
