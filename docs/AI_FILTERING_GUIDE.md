# AI-Powered Abstract Filtering Guide

## ⚠️ IMPORTANT: Free Tier Limitations

**The default free model (`openai/gpt-oss-20b:free`) has a 50 requests per day limit.**

- **Suitable for**: Small datasets (≤50 papers), testing, evaluation
- **Not suitable for**: Large systematic reviews (>50 papers)
- **Solutions**:
  1. Use keyword filtering (`02_abstract_filter.py`) - no limits
  2. Upgrade to paid model (see "Cost Considerations" below)
  3. Split processing across multiple days
  4. Use AI filtering only for borderline cases after keyword pre-filtering

## Overview

This guide covers the AI-powered filtering feature that uses Large Language Models (LLMs) to analyze paper abstracts and make intelligent filtering decisions.

Unlike keyword-based filtering that matches exact words, AI filtering understands context and meaning, reducing false positives and improving accuracy.

## Features

- **Contextual Understanding**: LLM analyzes meaning, not just keywords
- **Multi-Filter Analysis**: All filters evaluated in a single API call
- **Confidence Scoring**: Each decision includes a confidence score
- **Manual Review Flagging**: Low-confidence papers flagged for human review
- **Response Caching**: Avoid redundant API calls
- **Detailed Logging**: Full audit trail of AI decisions
- **Cost Tracking**: Monitor API usage and costs

## Setup

### 1. Install Dependencies

```bash
pip install openai
```

Or install all dependencies:

```bash
pip install -r requirements.txt
```

### 2. Get OpenRouter API Key

1. Go to [OpenRouter](https://openrouter.ai/keys)
2. Sign up or log in
3. Create a new API key
4. Copy the key

### 3. Configure Environment

Add your API key to `.env` file:

```bash
OPENROUTER_API_KEY=your_actual_api_key_here
```

## Usage

### Basic Workflow

1. **Run metadata fetching** (if not done already):
   ```bash
   python 01_fetch_metadata.py
   ```

2. **Run AI filtering**:
   ```bash
   python 02_abstract_filter_AI.py
   ```

3. **Review results** in `results/` directory

4. **Compare with keyword filtering** (optional):
   ```bash
   python compare_filtering_strategies.py
   ```

### Output Files

After running `02_abstract_filter_AI.py`:

- `results/papers_filtered_ai.csv` - Papers that passed all filters
- `results/references_filtered_ai.bib` - Filtered bibliography
- `results/manual_review_ai.csv` - Papers flagged for manual review
- `results/filtered_out_ai/` - Papers removed by each filter
- `results/ai_filtering_log_*.json` - Detailed decision log
- `results/ai_cache/` - Cached API responses

## Configuration

### Filter Configuration

Edit `02_abstract_filter_AI.py` to customize filters:

```python
FILTERS_CONFIG = {
    'epilepsy': {
        'enabled': True,
        'prompt': "Does this paper focus primarily on epileptic spikes?",
        'description': "Papers about epilepsy-related spike detection"
    },
    # Add more filters...
}
```

### AI Configuration

Adjust AI model settings:

```python
AI_CONFIG = {
    'model': 'openai/gpt-oss-20b:free',  # Free model
    'temperature': 0.0,                   # Deterministic
    'max_tokens': 200,                    # Response length
    'confidence_threshold': 0.5,          # Min confidence (0.0-1.0)
    'retry_attempts': 3,                  # API retry attempts
    'cache_responses': True,              # Enable caching
}
```

### Confidence Threshold

The `confidence_threshold` (0.0 to 1.0) determines how confident the AI must be to filter a paper:

- **0.3-0.5**: Conservative (fewer false negatives, more manual review)
- **0.5-0.7**: Balanced (recommended)
- **0.7-1.0**: Aggressive (more false negatives, less manual review)

## How It Works

### Multi-Filter Analysis

The AI evaluates all filters in a single API call:

1. Combines paper title and abstract
2. Sends to LLM with all filter questions
3. Receives JSON response with decisions for each filter
4. Applies confidence threshold
5. Flags low-confidence papers for manual review

### Example API Response

```json
{
  "epilepsy": {
    "answer": "NO",
    "confidence": 0.95,
    "reason": "Paper studies cognitive processes, not seizures"
  },
  "bci": {
    "answer": "NO",
    "confidence": 0.9,
    "reason": "No brain-computer interface mentioned"
  },
  "non_human": {
    "answer": "NO",
    "confidence": 0.85,
    "reason": "Study involves human participants"
  },
  "non_empirical": {
    "answer": "YES",
    "confidence": 0.6,
    "reason": "Appears to be a review paper"
  }
}
```

### Manual Review Cases

Papers are flagged for manual review when:

1. **API call fails** - Network error, rate limit, etc.
2. **Low confidence** - Confidence below threshold
3. **Missing response** - LLM didn't answer a filter question
4. **Parse error** - Response couldn't be parsed

## Comparing Strategies

Use the validation script to compare keyword vs AI filtering:

```bash
python compare_filtering_strategies.py
```

### Output

- **Text Report**: Detailed comparison with paper lists
- **CSV File**: Paper-by-paper comparison for analysis
- **Metrics**: Agreement rate, filtering rates, differences

### Interpretation

- **High agreement (>90%)**: Both methods consistent
- **Moderate agreement (75-90%)**: Review disagreements
- **Low agreement (<75%)**: Significant differences, investigate

### Categories

- **Both_Kept**: Agreed to keep (high confidence)
- **Both_Filtered**: Agreed to filter (high confidence)
- **Keyword_Only**: Kept by keyword, filtered by AI (review)
- **AI_Only**: Kept by AI, filtered by keyword (review)

## Cost Considerations

### Free Model (⚠️ LIMITED)

Using `openai/gpt-oss-20b:free`:
- **Cost**: $0.00 per call
- **Rate limits**: **50 requests per day** (hard limit)
- **Quality**: Good for binary classification
- **Best for**: Testing, small datasets (≤50 papers), evaluation
- **Not suitable for**: Large systematic reviews or production use

### Paid Models (Recommended for Production)

For larger datasets or better performance:
- **`anthropic/claude-3-haiku`**: $0.25 per 1M input tokens
  - Fast, accurate, cost-effective
  - ~$0.0025 per paper (250 tokens avg)
  - 100 papers ≈ $0.25
- **`openai/gpt-4o-mini`**: $0.15 per 1M input tokens
  - Good balance of cost and quality
  - ~$0.0015 per paper
  - 100 papers ≈ $0.15
- **`openai/gpt-4o`**: $2.50 per 1M input tokens
  - Best accuracy
  - ~$0.025 per paper
  - 100 papers ≈ $2.50

### How to Switch Models

Edit `02_abstract_filter_AI.py`:

```python
AI_CONFIG = {
    'model': 'anthropic/claude-3-haiku',  # Change from default
    # ... rest of config
}
```
- `openai/gpt-4o` - Best accuracy

## Caching

Response caching saves costs and time:

- Responses stored in `results/ai_cache/`
- Cache key based on paper + filters
- Automatic cache lookup before API call
- Re-run script without additional API costs

### Clear Cache

To force re-processing:

```bash
# PowerShell
Remove-Item -Recurse results/ai_cache/
```

## Troubleshooting

### "API call failed"

**Possible causes:**
- Invalid API key
- Network issues
- Rate limiting
- Model unavailable

**Solutions:**
1. Check `.env` file has correct API key
2. Verify internet connection
3. Wait a few minutes and retry
4. Check OpenRouter status

### "No papers flagged for manual review"

This is normal if:
- All papers have high-confidence decisions
- Confidence threshold is low
- No API errors occurred

### "Many papers in manual review"

**Possible causes:**
- Confidence threshold too high
- API issues
- Ambiguous abstracts

**Solutions:**
1. Lower confidence threshold to 0.4-0.5
2. Review AI decision log
3. Check API stats in output

### "High disagreement with keyword filtering"

**Possible actions:**
1. Review papers in disagreement categories
2. Check AI reasoning in decision log
3. Adjust filter prompts for clarity
4. Consider using intersection of both methods

## Best Practices

1. **Start small**: Test on 10-20 papers first
2. **Review manual_review papers**: These need human judgment
3. **Check decision log**: Understand AI reasoning
4. **Compare strategies**: Validate against keyword filtering
5. **Iterate prompts**: Refine filter questions based on results
6. **Use caching**: Enable to save costs on re-runs
7. **Monitor costs**: Track API usage (shown in output)

## Advanced Usage

### Custom Filters

Add domain-specific filters:

```python
'methodology_filter': {
    'enabled': True,
    'prompt': "Does this paper use ONLY computational modeling without empirical EEG data?",
    'description': "Pure computational studies"
},
```

### Batch Processing

For large datasets, process in batches:

```python
# In 02_abstract_filter_AI.py
# Process first 100 papers as test
papers = papers[:100]
```

### Combining Approaches

Use keyword pre-filter + AI for edge cases:

1. Run keyword filter first (fast, cheap)
2. Apply AI to borderline cases only
3. Combine results for final dataset

## Decision Log Analysis

The JSON decision log contains detailed information:

```python
import json

# Load decision log
with open('results/ai_filtering_log_*.json') as f:
    data = json.load(f)

# Analyze low-confidence decisions
low_conf = [
    d for d in data['decisions']
    if any(r['confidence'] < 0.6 for r in d['all_filter_results'].values())
]
```

## Support

For issues or questions:
1. Check this guide
2. Review decision logs
3. Compare with keyword filtering
4. Check OpenRouter documentation
