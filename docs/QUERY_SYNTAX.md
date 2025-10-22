# Query Syntax Guide

Complete guide for writing effective search queries across all sources.

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