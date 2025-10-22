# AI Filtering Implementation Summary

## Overview

Implemented AI-powered abstract filtering system using Large Language Models (LLMs) via OpenRouter API as an alternative to keyword-based filtering.

## Files Created

### Core Implementation
1. **`src/llm_client.py`** (351 lines)
   - OpenRouter API client using OpenAI SDK
   - Multi-filter analysis in single API call
   - Response caching with MD5 hash keys
   - Retry logic with exponential backoff
   - Usage tracking and statistics

2. **`src/ai_abstract_filter.py`** (262 lines)
   - AI-powered filter class
   - Confidence threshold filtering
   - Manual review flagging for low confidence/errors
   - Detailed decision logging to JSON
   - Compatible with existing Paper model

3. **`02_abstract_filter_AI.py`** (203 lines)
   - Main AI filtering script
   - Configurable filter prompts
   - Mirror structure of keyword version
   - Environment variable configuration
   - Comprehensive output and logging

### Validation & Documentation
4. **`compare_filtering_strategies.py`** (253 lines)
   - Compare keyword vs AI filtering results
   - Agreement metrics and analysis
   - Paper-by-paper comparison CSV
   - Detailed text report generation
   - Recommendations based on agreement

5. **`docs/AI_FILTERING_GUIDE.md`** (384 lines)
   - Complete usage guide
   - Setup instructions
   - Configuration examples
   - Troubleshooting section
   - Best practices

### Configuration
6. **Updated files:**
   - `requirements.txt` - Added `openai>=1.0.0`
   - `.env.example` - Added `OPENROUTER_API_KEY`
   - `README.md` - Updated with AI filtering info

## Key Features

### Multi-Filter Single Call
- All filters evaluated in one API request
- Reduces API calls and costs significantly
- Returns JSON with all filter decisions

### Confidence-Based Filtering
- Each decision includes confidence score (0.0-1.0)
- Configurable threshold (default: 0.5)
- Low-confidence papers flagged for manual review

### Manual Review System
- Papers flagged when:
  - API call fails
  - Confidence below threshold
  - Missing filter response
  - Parse errors
- Kept papers but marked separately
- Exported to `manual_review_ai.csv`

### Response Caching
- Cache key: MD5 hash of (title + abstract + filters)
- Stored in `results/ai_cache/`
- Automatic cache lookup before API call
- Enable/disable via config

### Detailed Logging
- All decisions logged to JSON with timestamp
- Includes:
  - Full filter results
  - Confidence scores
  - AI reasoning
  - API success/failure
- Audit trail for validation

### Cost Tracking
- API call counter
- Cache hit rate
- Failed call counter
- Displayed in output

## Configuration

### Filter Definition
```python
FILTERS_CONFIG = {
    'filter_name': {
        'enabled': True,
        'prompt': "Natural language question",
        'description': "Human-readable description"
    }
}
```

### AI Settings
```python
AI_CONFIG = {
    'model': 'openai/gpt-oss-20b:free',
    'temperature': 0.0,
    'max_tokens': 200,
    'confidence_threshold': 0.5,
    'retry_attempts': 3,
    'cache_responses': True
}
```

## Workflow

1. Load papers from `results/references.bib`
2. Filter papers without abstracts (no AI needed)
3. For each paper with abstract:
   - Check cache first
   - If not cached, call LLM with all filters
   - Parse JSON response
   - Apply confidence threshold
   - Flag for manual review if needed
   - Cache successful response
4. Save results:
   - `papers_filtered_ai.csv` - Kept papers
   - `manual_review_ai.csv` - Needs review
   - `filtered_out_ai/` - Filtered by category
   - `ai_filtering_log_*.json` - Decision log

## Validation Strategy

Compare with keyword filtering using `compare_filtering_strategies.py`:

### Metrics
- Agreement rate (both methods agree)
- Disagreement breakdown
- Filtering rate comparison
- Papers unique to each method

### Output
- Text report with paper lists
- CSV with paper-by-paper comparison
- Categories: Both_Kept, Both_Filtered, Keyword_Only, AI_Only

## Advantages Over Keywords

1. **Context understanding**: Interprets meaning, not just words
2. **Fewer false positives**: Won't match "corroded" for "rodent"
3. **Nuance detection**: Distinguishes review types
4. **Adaptability**: Easy to refine with prompt changes
5. **Auditability**: Clear reasoning for each decision

## Error Handling

### Robust Retry Logic
- 3 retry attempts with exponential backoff
- Waits: 1s, 2s, 4s
- Logs all failures

### Graceful Degradation
- API failure → flag for manual review
- Parse error → flag for manual review
- Missing filter → flag for manual review
- Always keeps paper (conservative)

### Cache Resilience
- Cache read/write failures logged but non-fatal
- Operations continue without cache

## Testing Recommendations

1. **Small test run**: 10-20 papers first
2. **Validate decisions**: Review AI reasoning in log
3. **Compare strategies**: Run comparison script
4. **Manual validation**: Spot-check manual review papers
5. **Cost check**: Monitor API usage stats

## Free Tier Usage

Using `openai/gpt-oss-20b:free`:
- **Cost**: $0.00
- **Quality**: Good for binary classification
- **Speed**: ~1-2 seconds per paper
- **Rate limits**: Generous for typical use

For 100 papers with 4 filters:
- API calls: ~100 (one per paper)
- Estimated time: 2-3 minutes
- Cost: $0.00

## Future Enhancements

Possible improvements:
1. Batch API requests for better performance
2. Parallel processing with rate limiting
3. Confidence calibration based on validation
4. Hybrid approach: keyword pre-filter + AI for edge cases
5. Integration with existing test suite
6. Support for other LLM providers (Anthropic, local models)

## Git Branch

All changes committed to `ai_filtering` branch.

## Dependencies

New dependency:
- `openai>=1.0.0` - OpenAI Python SDK (works with OpenRouter)

## Environment Variables

New required variable for AI filtering:
- `OPENROUTER_API_KEY` - Get from https://openrouter.ai/keys

## Backward Compatibility

- Keyword filtering unchanged
- Both approaches can coexist
- No breaking changes to existing code
- Optional feature, not required
