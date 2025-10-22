# AI-Powered Filtering - Quick Start

## ⚠️ CRITICAL: Free Tier Limitations

**The free model has a 50 requests per day limit.**

- **Works for**: ≤50 papers per day
- **Not suitable for**: Large datasets (>50 papers)
- **Alternatives**: 
  - Use keyword filtering (no limits)
  - Upgrade to paid model (~$0.15-0.25 per 100 papers)
  - Split processing across multiple days

## Installation

1. **Install the OpenAI package:**
   ```powershell
   pip install openai
   ```

2. **Get your OpenRouter API key:**
   - Visit https://openrouter.ai/keys
   - Sign up/login
   - Create a new API key
   - Copy the key

3. **Add to your `.env` file:**
   ```bash
   OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxx
   ```

## Basic Usage

### Run AI Filtering

```powershell
# Make sure you've run the metadata fetch first
python 01_fetch_metadata.py

# Run AI-powered filtering
python 02_abstract_filter_AI.py
```

### Compare with Keyword Filtering

```powershell
# Run keyword filtering
python 02_abstract_filter.py

# Run AI filtering
python 02_abstract_filter_AI.py

# Compare results
python compare_filtering_strategies.py
```

## Output Files

After running `02_abstract_filter_AI.py`:

```
results/
├── papers_filtered_ai.csv          # Papers kept by AI
├── references_filtered_ai.bib      # BibTeX for kept papers
├── manual_review_ai.csv            # Papers needing manual review
├── ai_filtering_log_*.json         # Detailed decision log
├── filtered_out_ai/                # Papers filtered by each category
│   ├── epilepsy.csv
│   ├── bci.csv
│   ├── non_human.csv
│   └── non_empirical.csv
└── ai_cache/                       # Cached API responses
    └── *.json
```

## Customization

### Edit Filters

Open `02_abstract_filter_AI.py` and modify `FILTERS_CONFIG`:

```python
FILTERS_CONFIG = {
    'your_filter_name': {
        'enabled': True,
        'prompt': "Your natural language question here?",
        'description': "Brief description"
    },
}
```

### Adjust AI Settings

Modify `AI_CONFIG` in `02_abstract_filter_AI.py`:

```python
AI_CONFIG = {
    'confidence_threshold': 0.5,  # 0.0-1.0 (lower = more conservative)
    'cache_responses': True,      # Set False to disable caching
}
```

## Understanding Results

### Manual Review Papers

Papers are flagged for manual review when:
- API call failed (network error, rate limit, etc.)
- Confidence score below threshold
- AI response incomplete or ambiguous

**Action:** Review `manual_review_ai.csv` and make manual decisions

### Decision Log

The JSON log (`ai_filtering_log_*.json`) contains:
- Every paper analyzed
- AI decision for each filter
- Confidence scores
- Reasoning for each decision

**Use for:** Understanding why papers were filtered/kept

### Comparison Report

After running `compare_filtering_strategies.py`:
- Text report: `filtering_comparison_*.txt`
- CSV comparison: `filtering_comparison_*.csv`

Categories in CSV:
- **Both_Kept**: Both methods agree to keep
- **Both_Filtered**: Both methods agree to filter
- **Keyword_Only**: Kept by keyword, filtered by AI
- **AI_Only**: Kept by AI, filtered by keyword

## Troubleshooting

### "OPENROUTER_API_KEY not found"
- Check `.env` file exists in project root
- Verify key is set: `OPENROUTER_API_KEY=sk-or-v1-...`
- No quotes needed around the key

### "Import openai could not be resolved"
- Run: `pip install openai`
- Verify installation: `pip list | findstr openai`

### "API call failed"
- Check internet connection
- Verify API key is correct
- Check OpenRouter status: https://status.openrouter.ai/
- Papers will be flagged for manual review automatically

### "Rate limit exceeded" or "429 error"
- **Free model limit reached** (50/day)
- **Solutions**:
  1. Wait 24 hours for reset
  2. Use keyword filtering instead
  3. Upgrade to paid model (edit `model` in `AI_CONFIG`)
  4. Process in batches over multiple days
- Papers will be flagged for manual review automatically

### Many papers in manual review
- This is normal if confidence threshold is high
- Try lowering threshold to 0.4-0.5
- Review AI decision log to understand patterns

## Cost Information

### Free Model (`openai/gpt-oss-20b:free`)
- **Cost per paper:** $0.00
- **Daily limit:** 50 requests
- **Quality:** Good for binary classification

**Example for ≤50 papers:**
- API calls: ~50
- Time: 1-2 minutes
- Cost: **$0.00**

### Paid Models (For >50 Papers)
- **`anthropic/claude-3-haiku`**: ~$0.25 per 100 papers
- **`openai/gpt-4o-mini`**: ~$0.15 per 100 papers

**To upgrade**, edit `02_abstract_filter_AI.py`:
```python
AI_CONFIG = {
    'model': 'anthropic/claude-3-haiku',  # or 'openai/gpt-4o-mini'
    # ... rest unchanged
}
```

## Best Practices

1. **Start small:** Test on 10-20 papers first
2. **Review decisions:** Check the JSON log
3. **Compare methods:** Run both keyword and AI filtering
4. **Validate results:** Manually check disagreements
5. **Use caching:** Keep it enabled for re-runs
6. **Monitor manual review:** Check flagged papers

## Next Steps

After filtering:

1. **Review manual_review_ai.csv** - Make final decisions
2. **Download PDFs:**
   ```powershell
   python 03_download_papers.py
   ```

## Support

- Full guide: `docs/AI_FILTERING_GUIDE.md`
- Implementation details: `docs/AI_FILTERING_IMPLEMENTATION.md`
- Keyword filtering: `docs/ABSTRACT_FILTERING.md`
