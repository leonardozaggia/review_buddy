# Abstract-Based Filtering

## Overview

The abstract filtering step (`02_abstract_filter.py`) allows you to refine search results by removing unwanted papers based on their abstract content and metadata.

## When to Use

Run this **after** fetching metadata (`01_fetch_metadata.py`) and **before** downloading PDFs (`03_download_papers.py`):

```bash
python 01_fetch_metadata.py     # Fetch papers
python 02_abstract_filter.py    # Filter results (optional)
python 03_download_papers.py    # Download filtered papers
```

**Skip this step if:**
- You want all papers from your search
- You'll manually review results
- Your search query is already highly specific

## Filters Applied

### 1. No Abstract ✅ **High Confidence**
Removes papers without abstracts (cannot be analyzed).

### 2. Non-English Language ✅ **High Confidence**
Uses language detection on title/abstract to filter non-English papers.
- **Accuracy**: ~95%
- **Requires**: `langdetect` package (installed with requirements.txt)

### 3. Epileptic Spikes ⚠️ **Keyword-Based**
Removes papers about epileptic spike detection.
- **Keywords**: "epileptic spike", "interictal spike", "seizure spike", etc.
- **Accuracy**: ~90%

### 4. Brain-Computer Interfaces (BCI) ⚠️ **Keyword-Based**
Removes BCI/BMI papers.
- **Keywords**: "brain-computer interface", "BCI", "brain-machine interface", etc.
- **Accuracy**: ~85-90%

### 5. Non-Human Participants ⚠️ **Keyword-Based**
Removes animal studies and in-vitro research.
- **Keywords**: "rat", "mouse", "animal model", "in vitro", "cell culture", etc.
- **Accuracy**: ~70-80% (some studies mention animals for context)
- **Note**: Conservative - may keep some animal studies

### 6. Non-Empirical Articles ⚠️ **Keyword-Based**
Removes review papers and methods papers without data.
- **Review keywords**: "systematic review", "meta-analysis", "literature review", etc.
- **Smart detection**: Keeps papers with empirical indicators ("participants", "dataset", etc.)
- **Accuracy**: ~70-75%
- **Note**: Some reviews with meta-analysis may be kept

## Output Files

After filtering, you'll find:

```
results/
├── papers_filtered.csv          # Papers that passed all filters
├── references_filtered.bib      # Bibliography of filtered papers
└── filtered_out/                # Papers removed by each filter
    ├── no_abstract.csv
    ├── non_english.csv
    ├── epilepsy.csv
    ├── bci.csv
    ├── non_human.csv
    └── non_empirical.csv
```

## Customization

Edit `02_abstract_filter.py` to:

### Skip Specific Filters
```python
# In main(), modify filters_to_apply:
results = filter_tool.apply_all_filters(
    papers,
    filters_to_apply=['no_abstract', 'non_english']  # Only these two
)
```

### Add Custom Keywords
Edit `src/abstract_filter.py`:

```python
class AbstractFilter:
    # Add your own keywords
    CUSTOM_KEYWORDS = {
        'keyword1', 'keyword2', 'phrase to exclude'
    }
    
    def filter_custom(self, papers):
        return self.filter_by_keywords(
            papers, 
            self.CUSTOM_KEYWORDS, 
            "Custom"
        )
```

### Adjust Non-Human Detection
Add more animal keywords in `src/abstract_filter.py`:

```python
NON_HUMAN_KEYWORDS = {
    'rat', 'mouse', 'mice',
    # Add more:
    'ferret', 'guinea pig', 'hamster',
    # Add specific contexts:
    'animal subjects', 'veterinary'
}
```

## Performance

**Typical filtering results** (from 200 papers):
- No abstract: 5-10% removed
- Non-English: 1-5% removed
- Epilepsy/BCI: 5-15% removed (depends on query)
- Non-human: 10-30% removed
- Non-empirical: 10-20% removed

**Overall retention**: ~50-70% of papers kept

## Limitations

### False Positives (Good papers removed)
- **Non-human**: Papers mentioning animal models for comparison
- **Non-empirical**: Meta-analyses with original data
- **BCI**: Papers using BCI as a tool, not studying it

### False Negatives (Bad papers kept)
- **Non-human**: Implicit animal mentions ("the model organism", "the subjects")
- **Reviews**: Reviews without "review" in title/abstract
- **Language**: Mixed-language papers with English abstracts

## Recommendations

1. **Review filtered papers** before deleting - check `filtered_out/` folders
2. **Start conservative** - disable aggressive filters first
3. **Iterate** - Run filter, review results, adjust keywords
4. **Manual review** - For critical research, always manually review final set

## Example Session

```bash
# Fetch papers
$ python 01_fetch_metadata.py
# Found 250 papers

# Filter papers
$ python 02_abstract_filter.py
# Filtering complete: 142/250 papers kept (108 filtered)
# 
# Breakdown:
#   - no_abstract:    12 papers
#   - non_english:     5 papers
#   - epilepsy:       18 papers
#   - bci:            11 papers
#   - non_human:      48 papers
#   - non_empirical:  14 papers

# Download filtered papers
$ python 03_download_papers.py
# Will download 142 papers instead of 250
```

## Advanced: Phase 2 Filters

For higher accuracy, consider implementing:

1. **LLM-based classification**: Use GPT/Claude API for semantic filtering
2. **PubMed MeSH terms**: Leverage medical subject headings
3. **ML classifiers**: Train custom models on your domain
4. **Citation analysis**: Filter by citation count/impact

Contact maintainers if you need Phase 2 implementation.
