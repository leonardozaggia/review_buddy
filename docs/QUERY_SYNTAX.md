# Query Syntax Guide

Complete guide for writing effective search queries across all sources.

## Note: Scopus field scoping changed (re-fetch older corpora)

Queries are scoped to title/abstract/keywords by wrapping them in
`TITLE-ABS-KEY(...)`. Until this was fixed, redundant outer parentheses were
stripped with a naive "starts with `(` and ends with `)`" test — which is also
true of the standard systematic-review shape `(A) AND (B) AND (C)`. Stripping
those produced:

```
TITLE-ABS-KEY(A) AND (B) AND (C)
```

Only group A was field-scoped. Groups B and C escaped the restriction and were
matched against **every Scopus field**, including reference lists, affiliations
and funding text — so papers that merely *cited* something on-topic were pulled
in. Measured on two real queries, 2020 onward:

| Query | Before | After |
|---|---|---|
| stroke × cognition × longitudinal methods | 5751 | **544** |
| EEG single-trial × behaviour | 2446 | **116** |

That is a 10–21x inflation, nearly all of it off-topic. It also explains
spurious collisions with the 5000-record ceiling on queries that legitimately
return a few hundred papers.

**If you built a Scopus corpus before this fix, re-run the search** — the old
result set is not a superset you can simply filter, it is a differently-scoped
query.

## Write one query in plain boolean syntax — never in Scopus syntax

Every source receives the **same query string**. Only Scopus understands its own
field codes and operators, and no other source treats them as an error — they
just quietly produce nothing:

| Query | Scopus | PubMed | arXiv |
|-------|--------|--------|-------|
| `("single-trial" OR "trial-by-trial") AND (EEG OR ERP)` | works | **603** | 58 |
| `TITLE-ABS-KEY(("single-trial" OR "trial-by-trial") AND (EEG OR ERP))` | works | **0** | 58 (unrelated) |
| `ABS("single-trial") AND KEY(EEG)` | works | **0** | 24247 (unrelated) |
| `"single-trial" W/5 EEG` | works | **0** | 7413 (unrelated) |
| `"single-trial" PRE/3 EEG` | works | **0** | 11290 (unrelated) |

PubMed has no `TITLE-ABS-KEY` field, so it reads the code as an ordinary search
term and ANDs it into the query — `"TITLE-ABS-KEY"[Title/Abstract] AND (...)`.
No paper contains that phrase, so you get **0 results with HTTP 200, no error
and no warning**: identical to "this database has nothing on your topic". A
Scopus-native query is therefore the classic cause of "Scopus found thousands,
PubMed found none".

The searcher now detects these constructs and warns before running, but the fix
is always the same: use quoted phrases, `AND` / `OR` / `NOT`, and parentheses,
and let each searcher adapt the query for its own API.

## Wildcards behave differently on every source

**PubMed needs 4+ leading characters.** It ignores shorter truncations, so
`Response tim*` silently contributes nothing. Write `time*` instead.

**arXiv has no wildcards at all**, and the searcher strips them. That does *not*
degrade to a prefix search — it leaves a literal token that usually matches
nothing, and the damage is per-term and unpredictable:

| written | sent to arXiv | arXiv hits |
|---|---|---|
| `Trajector*` | `Trajector` | 3 — vs 59,712 for `Trajectory` |
| `Ischemi*` | `Ischemi` | 0 — vs 324 for `Ischemic` |
| `Fluctuat*` | `Fluctuat` | 79,436 — the stemmer happens to rescue this one |

So a wildcard-heavy query can return near-zero from arXiv while returning
thousands from Scopus, and the zero means "the terms didn't translate", not
"arXiv has no such papers". The searcher warns and names every truncated term.
If arXiv matters for a search, spell the variants out: `trajectory OR
trajectories`.

**Scopus is the only source where wildcards work as written.**

## `NOT` is rewritten per source

`NOT` is not portable either. Scopus needs `AND NOT`, arXiv needs `ANDNOT`, and
PubMed takes `NOT` as-is; the searchers translate it for you. One arXiv
subtlety worth knowing, because it is invisible when it bites: a trailing
`ANDNOT` clause swallows the date restriction the searcher appends, which
silently drops the year filter. The query is parenthesised before the date
clause is added to prevent this, so no action is needed — but if you hand-build
an arXiv query elsewhere, wrap it.

## Query Input Methods

### Inline Query (Simple)
```python
QUERY = "machine learning AND healthcare"
```

### Text File (Recommended for Complex Queries)
Create a `query.txt` file with your search terms:
```python
QUERY = Path("query.txt").read_text(encoding="utf-8").strip()
```

**Example `query.txt`:**
```
(
  "machine learning" OR "deep learning" OR "artificial intelligence"
)
AND
(
  healthcare OR medical OR clinical
)
NOT
(
  review OR "systematic review"
)
```

**Benefits:**
- Multi-line formatting for readability
- Easy to edit complex boolean queries
- Whitespace and newlines are automatically normalized
- Supports all boolean operators and grouping

## Basic Operators

| Operator | Syntax | Example |
|----------|--------|---------|
| **AND** | `term1 AND term2` | `machine learning AND healthcare` |
| **OR** | `term1 OR term2` | `neural networks OR deep learning` |
| **NOT** | `term1 NOT term2` | `AI NOT reinforcement` |
| **Exact phrase** | `"phrase"` | `"machine learning"` |
| **Grouping** | `(...)` | `(AI OR ML) AND diagnosis` |
| **Wildcard** | `term*` | `Electroencephalogra*` (matches any suffix) |

**Note**: Multiple terms without operators default to AND.

## Source Compatibility

| Source | AND/OR/NOT | Exact Phrase | Wildcards | Notes |
|--------|-----------|--------------|-----------|-------|
| **Scopus** | ✅ Full support | ✅ | ✅ | Highest precision |
| **PubMed** | ✅ Full support | ✅ | ✅ | Medical index, field-specific |
| **arXiv** | ✅ Basic | ✅ | ❌ | Wildcards auto-removed |
| **Scholar** | ⚠️ Limited | ✅ | ⚠️ | Broadest coverage, less precise |
| **IEEE** | ✅ Full support | ✅ | ✅ | Engineering focus |

**Note**: Queries are automatically adapted for each source (e.g., wildcards removed for arXiv, NOT converted to AND NOT for Scopus).

## Query Examples by Field

### Healthcare/Medicine

**General:**
```
machine learning AND healthcare
(AI OR "artificial intelligence") AND diagnosis
deep learning AND "medical imaging"
```

**Specific conditions:**
```
(diabetes OR "metabolic syndrome") AND "machine learning"
COVID-19 AND (diagnosis OR prognosis) AND AI
"breast cancer" AND "deep learning" NOT review
```

**Treatment/intervention:**
```
"drug discovery" AND "machine learning"
"personalized medicine" AND AI
(chemotherapy OR radiotherapy) AND "predictive modeling"
```

### Computer Science

**Machine learning:**
```
"convolutional neural network" AND image
(reinforcement learning OR RL) AND robotics
"transfer learning" AND "computer vision"
```

**AI techniques:**
```
"graph neural networks" OR GNN
"attention mechanism" AND transformer
(LSTM OR GRU) AND "time series"
```

**Applications:**
```
"natural language processing" AND healthcare
"computer vision" AND manufacturing
"anomaly detection" AND cybersecurity
```

### Engineering

**General:**
```
"machine learning" AND (manufacturing OR industrial)
AI AND "predictive maintenance"
"digital twin" AND optimization
```

**IoT & Systems:**
```
"internet of things" AND "machine learning"
"edge computing" AND AI
(sensor OR IoT) AND "anomaly detection"
```

### Interdisciplinary

**Climate & Environment:**
```
"machine learning" AND ("climate change" OR "global warming")
AI AND "environmental monitoring"
"deep learning" AND "weather prediction"
```

**Finance & Economics:**
```
"machine learning" AND ("stock prediction" OR trading)
AI AND "credit risk"
"algorithmic trading" NOT cryptocurrency
```

**Education:**
```
"machine learning" AND "personalized learning"
AI AND "educational technology"
"adaptive learning" AND recommendation
```

## Advanced Techniques

### Combining Multiple Concepts

**Inline:**
```python
QUERY = '("machine learning" OR "deep learning" OR AI) AND ("healthcare" OR "medical" OR "clinical") AND (diagnosis OR prognosis OR treatment)'
```

**Text file (`query.txt`):**
```
(
  "machine learning" OR "deep learning" OR AI
)
AND
(
  healthcare OR medical OR clinical
)
AND
(
  diagnosis OR prognosis OR treatment
)
```

### Excluding Noise

```
machine learning AND healthcare NOT review
AI AND diagnosis NOT "systematic review"
deep learning NOT survey NOT overview
```

### Year Filtering

Some sources support year filters in query:
```
machine learning AND healthcare AND 2020:2024
```

Or use script parameters:
```python
YEAR_FROM = 2020
YEAR_TO = 2024
```

### Field-Specific Searches

**PubMed supports field tags:**
```
machine learning[Title] AND cancer[MeSH]
AI[Title/Abstract] AND diagnosis
```

**Scopus supports field codes:**
```
TITLE(machine learning) AND KEY(healthcare)
```

## Tips for Better Results

1. **Start broad, then narrow:**
   ```
   # Broad
   machine learning healthcare
   
   # Narrower
   machine learning AND healthcare AND diagnosis
   
   # Specific
   "deep learning" AND "medical imaging" AND "brain tumor"
   ```

2. **Use synonyms with OR:**
   ```
   (AI OR "artificial intelligence" OR "machine learning")
   (COVID-19 OR coronavirus OR SARS-CoV-2)
   ```

3. **Exclude common noise:**
   ```
   machine learning NOT review
   AI NOT "systematic review" NOT meta-analysis
   ```

4. **Exact phrases for precision:**
   ```
   "convolutional neural network"  # Better than: convolutional neural network
   "random forest"                 # Better than: random forest
   ```

5. **Group related terms:**
   ```
   (diabetes OR obesity OR "metabolic syndrome") AND machine learning
   ```

## Common Patterns

### Literature Review Search

**Text file format (`query.txt`):**
```
(
  "machine learning" OR "deep learning" OR "artificial intelligence"
)
AND
(
  healthcare OR medical OR clinical
)
```

Then set `YEAR_FROM = 2020` in the script.

### Methodology-Focused

**Text file format:**
```
(
  "random forest" OR "support vector machine" OR "neural network"
)
AND
healthcare
AND
classification
```

### Application-Specific

**Text file format:**
```
"machine learning"
AND
(
  "electronic health records" OR EHR
)
AND
(
  "risk prediction" OR prognosis
)
```

### Emerging Topics

```
("quantum computing" OR "quantum machine learning") AND
(healthcare OR medicine)
```

## Best Practices

### Use Text Files for Complex Queries
For queries with multiple concepts, create a `query.txt` file:
```
(
  "Single-trial" OR "Trial-by-trial" OR "Within-subject"
)
AND
(
  EEG OR "Event-related potential" OR Electroencephalogra*
)
NOT
(
  Animal OR Patient OR Clinical
)
```

Then in `01_fetch_metadata.py`:
```python
QUERY = Path("query.txt").read_text(encoding="utf-8").strip()
```

### Format for Readability
- Use newlines and indentation
- One concept per group
- Comments are removed automatically

## Troubleshooting

**Too many results?**
- Add more specific terms
- Use exact phrases
- Exclude common noise terms

**Too few results?**
- Use OR for synonyms
- Broaden terms
- Remove NOT exclusions
- Check spelling

**Wrong topic results?**
- Add domain-specific terms
- Use exact phrases
- Add exclusions with NOT

**Source-specific errors?**
- Check [Source Compatibility](#source-compatibility) table
- Wildcards not supported on arXiv (auto-removed)
- Complex nested queries may need simplification for some sources

## Source-Specific Tips

**Scopus**: Most comprehensive, use field codes for precision  
**PubMed**: Use MeSH terms for medical concepts  
**arXiv**: Best for recent preprints, simpler queries work better  
**Scholar**: Broadest coverage, expect more noise  
**IEEE**: Best for engineering, strong Boolean support