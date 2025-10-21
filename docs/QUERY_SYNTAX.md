# Query Syntax Guide

Complete guide for writing effective search queries across all sources.

## Basic Operators

| Operator | Syntax | Example |
|----------|--------|---------|
| **AND** | `term1 AND term2` | `machine learning AND healthcare` |
| **OR** | `term1 OR term2` | `neural networks OR deep learning` |
| **NOT** | `term1 NOT term2` | `AI NOT reinforcement` |
| **Exact phrase** | `"phrase"` | `"machine learning"` |
| **Grouping** | `(...)` | `(AI OR ML) AND diagnosis` |

**Note**: Multiple terms without operators default to AND.

## Source Compatibility

| Source | AND/OR/NOT | Exact Phrase | Notes |
|--------|-----------|--------------|-------|
| **Scopus** | ✅ Full support | ✅ | Highest precision |
| **PubMed** | ✅ Full support | ✅ | Medical index, field-specific |
| **arXiv** | ✅ Basic | ✅ | Title/abstract search |
| **Scholar** | ⚠️ Limited | ✅ | Broadest coverage, less precise |
| **IEEE** | ✅ Full support | ✅ | Engineering focus |

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

```
("machine learning" OR "deep learning" OR AI) AND
("healthcare" OR "medical" OR "clinical") AND
(diagnosis OR prognosis OR treatment)
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

```
("machine learning" OR "deep learning" OR AI) AND
(healthcare OR medical OR clinical) AND
(2020:2024)
```

### Methodology-Focused

```
("random forest" OR "support vector machine" OR "neural network") AND
healthcare AND
classification
```

### Application-Specific

```
"machine learning" AND
("electronic health records" OR EHR) AND
("risk prediction" OR prognosis)
```

### Emerging Topics

```
("quantum computing" OR "quantum machine learning") AND
(healthcare OR medicine)
```

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

## Source-Specific Tips

**Scopus**: Most comprehensive, use field codes for precision  
**PubMed**: Use MeSH terms for medical concepts  
**arXiv**: Best for recent preprints, simpler queries work better  
**Scholar**: Broadest coverage, expect more noise  
**IEEE**: Best for engineering, strong Boolean support