#!/usr/bin/env python3
"""
Final atlas report: merge the LLM labels with the regex pass and the paper
metadata, then cross-tabulate atlas usage by publication year.

Label precedence per paper:
  1. LLM label, if it survived the grounding check  -> source "llm"
     (the LLM judges USAGE - "we registered to X" vs "see X et al." - and the
      name is verified to occur in the paper text)
  2. otherwise the regex hit, flagged for review    -> source "regex_only"
     (a name is present but no usage statement was confirmed)
  3. otherwise none                                 -> source "none"

Outputs:
  results/atlas_final.csv     per paper: year, atlas(es), source, evidence
  results/atlas_by_year.csv   atlas x year matrix (adoption over time)
  results/atlas_final_summary.csv
"""

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NEONATAL = {
    "dHCP", "UNC neonatal/infant", "M-CRIB", "ALBERTs", "Draw-EM",
    "Edinburgh Neonatal Atlas (ENA)", "JHU neonatal (Oishi)", "Serag neonatal",
    "Gousias neonatal", "Fonov / NIHPD infant", "study-specific template",
    "unnamed neonatal atlas/template (cited only)", "Imperial neonatal",
    "Shi neonatal", "CRL / Gholipour (fetal-neonatal)", "Kuklisova-Murgasova neonatal",
}

# regex-pass names -> LLM canonical names, so the two passes can be merged
REGEX_TO_CANON = {
    "dHCP (developing Human Connectome Project)": "dHCP",
    "UNC neonatal/infant (UNC-Chapel Hill)": "UNC neonatal/infant",
    "M-CRIB (Melbourne Children's Regional Infant Brain)": "M-CRIB",
    "ALBERT / ALBERTs (Gousias/Imperial)": "ALBERTs",
    "Draw-EM (developing brain segmentation)": "Draw-EM",
    "Edinburgh Neonatal Atlas (ENA)": "Edinburgh Neonatal Atlas (ENA)",
    "JHU neonatal (Oishi)": "JHU neonatal (Oishi)",
    "Serag neonatal atlas": "Serag neonatal",
    "Shi neonatal atlas": "Shi neonatal",
    "CRL / Gholipour (fetal-neonatal)": "CRL / Gholipour (fetal-neonatal)",
    "Kuklisova-Murgasova neonatal": "Kuklisova-Murgasova neonatal",
    "LPBA40 (LONI Probabilistic Brain Atlas)": "LPBA40",
    "NeuroMark (ICN template)": "NeuroMark (ICN template)",
    "Gousias neonatal atlas": "Gousias neonatal",
    "Fonov / NIHPD infant templates": "Fonov / NIHPD infant",
    "Imperial neonatal atlas": "Imperial neonatal",
    "Shi neonatal atlas": "Shi neonatal",
    "generic 'neonatal/infant atlas or template'":
        "unnamed neonatal atlas/template (cited only)",
    "AAL (Automated Anatomical Labeling)": "AAL",
    "Harvard-Oxford": "Harvard-Oxford",
    "Desikan-Killiany (FreeSurfer)": "Desikan-Killiany",
    "Destrieux (FreeSurfer)": "Destrieux",
    "Schaefer": "Schaefer",
    "Yeo networks": "Yeo networks",
    "Power (264)": "Power-264",
    "Gordon": "Gordon",
    "Gordon/Power/Dosenbach seed sets": "Power-264",
    "Glasser / HCP-MMP": "Glasser / HCP-MMP",
    "Brainnetome": "Brainnetome",
    "Shen (268)": "Shen-268",
    "Craddock": "Craddock",
    "Talairach": "Talairach",
    "Brodmann": "Brodmann",
    "ICBM / MNI152 template": "MNI152 / ICBM",
}


def is_neonatal(atlas: str) -> bool:
    """Neonatal-specific if it's a known infant atlas, or an 'other:' label whose
    own text says it is (e.g. 'other: Infant Brain Probability Templates')."""
    if atlas in NEONATAL:
        return True
    return bool(re.search(r"neonat|infant|newborn|fetal|foetal|preterm|perinatal",
                          atlas, re.I))


def years_from_bib(bib: Path) -> dict:
    """DOI (lowercased) -> year, parsed straight from the .bib."""
    out = {}
    if not bib.exists():
        return out
    text = bib.read_text(encoding="utf-8", errors="ignore")
    for entry in text.split("\n@")[1:]:
        doi = re.search(r"^\s*doi\s*=\s*\{([^}]*)\}", entry, re.M | re.I)
        yr = re.search(r"^\s*year\s*=\s*\{?(\d{4})", entry, re.M | re.I)
        if doi and yr:
            out[doi.group(1).strip().lower()] = int(yr.group(1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="results/atlas_labels_llm.csv")
    ap.add_argument("--bib", default="results/references_filtered_ai.bib")
    ap.add_argument("--outdir", default="results")
    args = ap.parse_args()

    def rooted(p):
        p = Path(p)
        return p if p.is_absolute() else ROOT / p

    labels_path, outdir = rooted(args.labels), rooted(args.outdir)
    if not labels_path.exists():
        print(f"Missing {labels_path} - run scripts/label_atlases_llm.py first.")
        return 1

    year_by_doi = years_from_bib(rooted(args.bib))
    rows = list(csv.DictReader(open(labels_path, encoding="utf-8")))

    final, src_counts, atlas_counts = [], Counter(), Counter()
    by_year = defaultdict(Counter)
    year_totals = Counter()

    for r in rows:
        llm = [a for a in (r.get("canonical") or "").split("; ") if a]
        rx_raw = [a for a in (r.get("regex_atlases") or "").split("; ") if a]
        rx = sorted({REGEX_TO_CANON.get(a, "") for a in rx_raw} - {""})

        if llm:
            atlases, source = llm, "llm"
        elif rx:
            atlases, source = rx, "regex_only"
        else:
            atlases, source = [], "none"

        year = year_by_doi.get((r.get("doi") or "").strip().lower())
        src_counts[source] += 1
        for a in atlases:
            atlas_counts[a] += 1
            if year:
                by_year[a][year] += 1
        if year:
            year_totals[year] += 1

        final.append({
            "title": r.get("title", ""), "doi": r.get("doi", ""),
            "year": year or "", "file": r.get("file", ""),
            "atlases": "; ".join(atlases),
            "n_atlases": len(atlases),
            "neonatal_specific": "yes" if any(is_neonatal(a) for a in atlases) else
                                 ("no" if atlases else ""),
            "source": source,
            "confidence": r.get("confidence", ""),
            "evidence_quote": r.get("evidence_quote", ""),
            "rejected_unverified": r.get("rejected_unverified", ""),
        })

    outdir.mkdir(parents=True, exist_ok=True)
    fp = outdir / "atlas_final.csv"
    with open(fp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(final[0].keys()))
        w.writeheader()
        w.writerows(final)

    fs = outdir / "atlas_final_summary.csv"
    with open(fs, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["atlas", "n_papers", "type"])
        for a, n in atlas_counts.most_common():
            w.writerow([a, n, "neonatal-specific" if is_neonatal(a) else "general/adult"])

    years = sorted(y for y in year_totals if 2009 < y < 2030)
    fy = outdir / "atlas_by_year.csv"
    with open(fy, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["atlas"] + years + ["total"])
        for a, _ in atlas_counts.most_common():
            row = [by_year[a].get(y, 0) for y in years]
            w.writerow([a] + row + [sum(row)])
        w.writerow(["ALL PAPERS (denominator)"] + [year_totals[y] for y in years]
                   + [sum(year_totals[y] for y in years)])

    n_lab = sum(1 for r in final if r["atlases"])
    n_neo = sum(1 for r in final if r["neonatal_specific"] == "yes")
    print("=" * 70)
    print("FINAL ATLAS REPORT")
    print("=" * 70)
    print(f"papers: {len(final)} | with an atlas: {n_lab} | neonatal-specific: {n_neo}")
    print(f"label source: {dict(src_counts)}")
    print("\nTop atlases (merged, LLM-verified first):")
    for a, n in atlas_counts.most_common(22):
        kind = "neo" if is_neonatal(a) else "gen"
        print(f"  {n:5d}  [{kind}]  {a}")
    print(f"\nAdoption by year (top 6 atlases):")
    top = [a for a, _ in atlas_counts.most_common(6)]
    print("  " + "atlas".ljust(38) + "".join(str(y).rjust(6) for y in years))
    for a in top:
        print("  " + a[:36].ljust(38)
              + "".join(str(by_year[a].get(y, 0)).rjust(6) for y in years))
    print("  " + "(all papers)".ljust(38)
          + "".join(str(year_totals[y]).rjust(6) for y in years))
    print(f"\nPer paper:  {fp}\nSummary:    {fs}\nBy year:    {fy}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
