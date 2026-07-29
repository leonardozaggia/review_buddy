#!/usr/bin/env python
"""
Benchmark Ollama models on the repo's real abstract-filtering task.

Scores each model on a hand-labelled sample of papers drawn from the corpus,
measuring the three things that actually decide which model to run:

  1. accuracy   - per-filter agreement with hand-assigned gold labels
  2. JSON       - how often the raw reply parses as JSON with no repair
  3. speed      - median seconds per paper

Two prompt modes are compared:
  plain   - exactly what src/llm_client.py sends today (free-form JSON request)
  schema  - same prompt, but with Ollama's structured-output JSON schema

The 48 gold labels live in scripts/benchmark_data/gold_labels.json. They carry
titles and DOIs but not abstracts, so no publisher text is redistributed - build
the sample locally from your own .bib first:

  python scripts/benchmark_ollama_models.py --rebuild-sample results/references.bib \
      --gold scripts/benchmark_data/gold_labels.json --sample sample.json

Usage:
  python scripts/benchmark_ollama_models.py --models llama3.2:3b qwen3:4b \
      --sample sample.json --gold scripts/benchmark_data/gold_labels.json \
      --out bench.json
"""

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.llm_client import OllamaClient  # noqa: E402
from src.models import Paper  # noqa: E402


# The filter set from config.neonatal_fmri.yaml. Kept inline so the benchmark
# is reproducible even if the config changes.
FILTERS = {
    "not_neonatal": (
        "Is the study population NOT human neonates, newborns, preterm infants, "
        "fetuses, or infants under about 2 years old? Answer yes if it studies "
        "only older children, adolescents, adults, or animals."
    ),
    "no_fmri": (
        "Does this study lack functional MRI data? Answer yes if it uses only "
        "structural MRI, diffusion MRI/DTI, EEG, MEG, fNIRS, or other non-fMRI "
        "methods, with no BOLD, resting-state, or task-based fMRI."
    ),
    "non_empirical": (
        "Is this a review, meta-analysis, systematic review, study protocol, "
        "editorial, commentary, or a methods/software paper WITHOUT an original "
        "neuroimaging dataset of participants?"
    ),
}


# The same three decisions asked in the positive direction. Each filter in
# FILTERS above asks "is this paper BAD?", which small models answer with the
# right reasoning and the wrong polarity. These ask "is this paper GOOD?" and
# the answer is inverted in code, so a YES here means keep.
FILTERS_POSITIVE = {
    "is_neonatal": (
        "Is the study population human neonates, newborns, preterm infants, "
        "fetuses, or infants under about 2 years old?"
    ),
    "has_fmri": (
        "Does this study report functional MRI data - that is, BOLD, "
        "resting-state fMRI, or task-based fMRI?"
    ),
    "is_empirical": (
        "Does this paper report an original study with its own participants, "
        "rather than being a review, meta-analysis, systematic review, study "
        "protocol, editorial, or commentary?"
    ),
}

# positive filter name -> the negative filter it stands in for
POSITIVE_TO_NEGATIVE = {
    "is_neonatal": "not_neonatal",
    "has_fmri": "no_fmri",
    "is_empirical": "non_empirical",
}


def build_schema(filter_names):
    """JSON schema for Ollama structured outputs."""
    entry = {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "enum": ["YES", "NO"]},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["answer", "confidence", "reason"],
    }
    return {
        "type": "object",
        "properties": {n: entry for n in filter_names},
        "required": list(filter_names),
    }


def call_model(base_url, model, prompt, mode, schema, temperature, timeout, think):
    """One /api/generate call. Returns (text, seconds, error)."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": 4096},
    }
    if mode == "schema":
        payload["format"] = schema
    if think is not None:
        payload["think"] = think

    t0 = time.perf_counter()
    try:
        r = requests.post(f"{base_url}/api/generate", json=payload, timeout=timeout)
        # Models that don't support thinking reject the field; retry without it.
        if r.status_code == 400 and think is not None:
            payload.pop("think")
            r = requests.post(f"{base_url}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        dt = time.perf_counter() - t0
        return r.json().get("response", ""), dt, None
    except Exception as e:  # noqa: BLE001
        return "", time.perf_counter() - t0, str(e)


def strict_json(text):
    """Parse with no repair at all - measures raw format compliance."""
    try:
        return json.loads(text.strip())
    except Exception:  # noqa: BLE001
        return None


def repaired_json(text, client):
    """Parse using the repo's existing salvage logic."""
    try:
        return client._parse_response(text)
    except Exception:  # noqa: BLE001
        return None


def extract_answers(parsed, filter_names):
    """Pull YES/NO per filter out of a parsed reply; None if absent/unusable."""
    out = {}
    for n in filter_names:
        v = (parsed or {}).get(n)
        if isinstance(v, dict) and "answer" in v:
            a = str(v["answer"]).strip().upper()
            out[n] = a if a in ("YES", "NO") else None
        elif isinstance(v, str) and v.strip().upper() in ("YES", "NO"):
            out[n] = v.strip().upper()
        else:
            out[n] = None
    return out


def to_negative_space(answers):
    """
    Map positively-phrased answers onto the filter-fires convention.

    The rest of the scoring assumes YES = exclude the paper. A positive filter
    answers YES = keep, so both the name and the answer are flipped here and
    everything downstream is comparable to the negative run.
    """
    out = {}
    for pos, neg in POSITIVE_TO_NEGATIVE.items():
        a = answers.get(pos)
        out[neg] = None if a is None else ("NO" if a == "YES" else "YES")
    return out


def run_model(model, papers, gold, args):
    client = OllamaClient(model=model, base_url=args.base_url, cache_dir=None)
    active = FILTERS_POSITIVE if args.polarity == "positive" else FILTERS
    names = list(active)
    schema = build_schema(names)

    results = {}
    for mode in args.modes:
        recs = []
        print(f"\n  [{model}] mode={mode}", flush=True)
        for i, p in enumerate(papers, 1):
            paper = Paper(title=p["title"], abstract=p["abstract"])
            prompt = f"{client.system_prompt}\n\n{client._create_user_prompt(paper, active)}"
            text, dt, err = call_model(
                args.base_url, model, prompt, mode, schema,
                args.temperature, args.timeout, args.think,
            )
            s = strict_json(text)
            rp = s if s is not None else repaired_json(text, client)
            answers = extract_answers(rp, names)
            if args.polarity == "positive":
                answers = to_negative_space(answers)
            recs.append({
                "id": p["id"],
                "seconds": dt,
                "error": err,
                "strict_ok": s is not None,
                "repaired_ok": rp is not None,
                "answers": answers,
                "raw_head": text[:300],
            })
            if i % 8 == 0 or i == len(papers):
                med = statistics.median(r["seconds"] for r in recs)
                print(f"    {i}/{len(papers)}  median {med:.1f}s/paper", flush=True)

        # answers are always normalised to the negative (filter-fires) space,
        # so both polarities score against the same gold labels
        results[mode] = score(recs, gold, list(FILTERS))
        results[mode]["polarity"] = args.polarity
        results[mode]["records"] = recs
    return results


def score(recs, gold, names):
    n = len(recs)
    strict = sum(r["strict_ok"] for r in recs)
    repaired = sum(r["repaired_ok"] for r in recs)
    errs = sum(bool(r["error"]) for r in recs)
    times = [r["seconds"] for r in recs]

    per_filter = {}
    for fn in names:
        correct = graded = missing = 0
        fp = fn_ = 0
        for r in recs:
            g = gold.get(str(r["id"]), {}).get(fn)
            if g is None:          # ambiguous -> not scored
                continue
            a = r["answers"].get(fn)
            if a is None:
                missing += 1
                graded += 1
                continue
            graded += 1
            if a == g:
                correct += 1
            elif a == "YES":
                fp += 1            # wrongly excluded a paper
            else:
                fn_ += 1           # wrongly kept a paper
        per_filter[fn] = {
            "graded": graded,
            "correct": correct,
            "accuracy": round(correct / graded, 4) if graded else None,
            "false_exclusions": fp,
            "false_inclusions": fn_,
            "unparseable": missing,
        }

    graded_tot = sum(v["graded"] for v in per_filter.values())
    corr_tot = sum(v["correct"] for v in per_filter.values())
    return {
        "n_papers": n,
        "errors": errs,
        "strict_json_rate": round(strict / n, 4),
        "repaired_json_rate": round(repaired / n, 4),
        "median_s": round(statistics.median(times), 2),
        "mean_s": round(statistics.mean(times), 2),
        "total_s": round(sum(times), 1),
        "overall_accuracy": round(corr_tot / graded_tot, 4) if graded_tot else None,
        "per_filter": per_filter,
    }


def rebuild_sample(bib_path, gold_path, out_path):
    """
    Reconstruct the benchmark sample by matching the gold labels against a local
    .bib. Ships the labels without abstracts, so the corpus text stays yours.
    """
    text = Path(bib_path).read_text(encoding="utf-8", errors="replace")
    entries = {}
    for chunk in re.split(r"\n@\w+\{", "\n" + text):
        def field(name):
            m = re.search(r"\n\s*" + name + r"\s*=\s*\{(.*?)\},?\n", chunk, re.S)
            return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        title, doi = field("title"), field("doi")
        abstract = field("abstract")
        if title and abstract:
            entries[_norm(title)] = {"title": title, "abstract": abstract, "doi": doi}
        if doi and abstract:
            entries[doi.strip().lower()] = {"title": title, "abstract": abstract, "doi": doi}

    gold = json.loads(Path(gold_path).read_text(encoding="utf-8"))["labels"]
    sample, missing = [], []
    for pid, lab in sorted(gold.items(), key=lambda kv: int(kv[0])):
        hit = (entries.get((lab.get("doi") or "").strip().lower())
               or entries.get(_norm(lab.get("title"))))
        if hit:
            sample.append({"id": int(pid), **hit})
        else:
            missing.append(lab.get("title", pid)[:70])

    Path(out_path).write_text(json.dumps(sample, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print(f"rebuilt {len(sample)}/{len(gold)} sample papers -> {out_path}")
    if missing:
        print(f"{len(missing)} not found in {bib_path} (they will simply be skipped):")
        for m in missing[:10]:
            print(f"   - {m}")


def _norm(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild-sample", metavar="BIB",
                    help="build the sample from this .bib using --gold, write "
                         "it to --sample, then exit")
    ap.add_argument("--models", nargs="+")
    ap.add_argument("--sample", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--out")
    ap.add_argument("--modes", nargs="+", default=["plain", "schema"])
    ap.add_argument("--base-url", default="http://localhost:11434")
    ap.add_argument("--temperature", type=float, default=0.1)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--think", default=None,
                    help="'false' to disable thinking on reasoning models")
    ap.add_argument("--polarity", choices=["negative", "positive"], default="negative",
                    help="negative = the repo's current 'is this paper bad?' "
                         "questions; positive = 'is this paper good?', inverted "
                         "in code. Isolates prompt phrasing from model ability.")
    args = ap.parse_args()

    if args.rebuild_sample:
        rebuild_sample(args.rebuild_sample, args.gold, args.sample)
        return
    if not args.models or not args.out:
        ap.error("--models and --out are required unless --rebuild-sample is given")

    if args.think is not None:
        args.think = args.think.lower() in ("true", "1", "yes")

    papers = json.loads(Path(args.sample).read_text(encoding="utf-8"))
    if args.limit:
        papers = papers[: args.limit]
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8"))["labels"]

    out = {}
    outpath = Path(args.out)
    for m in args.models:
        print(f"\n=== {m} ===", flush=True)
        try:
            out[m] = run_model(m, papers, gold, args)
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {e}", flush=True)
            out[m] = {"error": str(e)}
        # write incrementally so a slow model can't lose earlier results
        outpath.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"\nwrote {outpath}")
    for m, modes in out.items():
        if "error" in modes:
            continue
        for mode, s in modes.items():
            print(f"{m:22s} {mode:7s} acc={s['overall_accuracy']} "
                  f"json={s['strict_json_rate']} med={s['median_s']}s")


if __name__ == "__main__":
    main()
