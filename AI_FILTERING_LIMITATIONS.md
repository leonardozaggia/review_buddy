# ⚠️ AI Filtering - Important Limitations

## Free Tier Restrictions

The default AI filtering uses OpenRouter's free model which has **strict limitations**:

### 50 Requests Per Day Limit

- **Maximum papers per day**: 50
- **Limit resets**: Every 24 hours
- **No workaround**: Hard limit enforced by OpenRouter

## When AI Filtering Works

✅ **Good for:**
- Testing the AI filtering feature
- Small datasets (≤50 papers)
- Evaluation and comparison
- Quality checking a subset of papers

❌ **Not suitable for:**
- Large systematic reviews (>50 papers)
- Production workflows
- Time-sensitive projects
- Batch processing large datasets

## Solutions

### 1. Use Keyword Filtering (Recommended)

The keyword-based filter has **no limitations**:
```bash
python 02_abstract_filter.py
```

**Advantages:**
- Unlimited papers
- Fast processing
- No API costs
- Reliable and predictable

### 2. Upgrade to Paid Model

Edit `02_abstract_filter_AI.py`:

```python
AI_CONFIG = {
    'model': 'anthropic/claude-3-haiku',  # ~$0.25 per 100 papers
    # OR
    'model': 'openai/gpt-4o-mini',        # ~$0.15 per 100 papers
}
```

**Costs for 100 papers:**
- Claude 3 Haiku: ~$0.25
- GPT-4o Mini: ~$0.15
- GPT-4o: ~$2.50

### 3. Hybrid Approach

Combine both methods:

1. **Pre-filter with keywords** - Remove obvious exclusions (fast, free)
2. **AI filter borderline cases** - Use AI for uncertain papers only
3. **Manual review** - Check flagged papers

### 4. Split Processing

For free tier:
- Process up to 50 papers per day
- Continue next day for remaining papers
- Use caching to avoid reprocessing

## Current Status (Branch: ai_filtering)

This feature is in a **separate branch** due to the free tier limitations.

**Will NOT be merged to main** until:
- A better free model is available, OR
- Users can easily configure paid models, OR
- A hybrid keyword+AI approach is implemented

## Recommendation

**For most users**: Use keyword filtering (`02_abstract_filter.py`)
- No limitations
- Works for any dataset size
- Well-tested and reliable

**For small datasets**: Try AI filtering for comparison
- Better context understanding
- Fewer false positives
- Good for evaluation

## Questions?

See full documentation:
- `docs/AI_FILTERING_GUIDE.md` - Complete guide
- `docs/AI_FILTERING_QUICKSTART.md` - Quick start
- `README.md` - Main documentation
