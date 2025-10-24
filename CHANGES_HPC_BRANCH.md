# HPC Branch - Changes Summary

This branch (`hpc_filt`) has been modified to use local Ollama models instead of OpenRouter API for AI-powered abstract filtering on HPC clusters.

## What Changed

### ✅ Removed
- OpenRouter API dependencies
- `openai` package requirement
- API key requirements (`.env` for OpenRouter)
- Rate limits (50 requests/day on free tier)
- External API calls

### ✅ Added
- **Ollama integration** - Local LLM inference
- **SLURM job scripts** - HPC cluster support
- **Parallel processing** - Array job support for large datasets
- **Batch processing utilities** - Split, process, and merge
- **HPC documentation** - Complete setup and usage guides

## New Files

### HPC Scripts
- `run_filter_hpc.sh` - Single job script for small datasets
- `run_filter_hpc_array.sh` - Array job script for parallel processing
- `split_papers_for_hpc.py` - Split papers into batches
- `process_batch.py` - Process individual batch
- `merge_batches.py` - Merge results from all batches

### Documentation
- `HPC_SETUP.md` - Complete HPC setup guide
- `QUICK_START_HPC.md` - Quick reference guide
- `CHANGES_HPC_BRANCH.md` - This file

## Modified Files

### Core Components
- `src/llm_client.py` - Replaced `OpenRouterClient` with `OllamaClient`
- `src/ai_abstract_filter.py` - Updated to use `OllamaClient`
- `02_abstract_filter_AI.py` - Updated configuration for Ollama
- `test_ai_setup.py` - Updated tests for Ollama

### Configuration
- `requirements.txt` - Removed `openai` package

## Key Differences

### Before (OpenRouter)
```python
# Required API key
llm_client = OpenRouterClient(
    api_key=os.getenv('OPENROUTER_API_KEY'),
    model='openai/gpt-oss-20b:free'
)
# Limited to 50 requests/day (free tier)
```

### After (Ollama)
```python
# No API key needed
llm_client = OllamaClient(
    model='llama3.1',
    base_url='http://localhost:11434'
)
# No rate limits, runs locally
```

## Usage Comparison

### OpenRouter (Old)
```bash
# Setup
echo "OPENROUTER_API_KEY=your_key" >> .env
pip install openai

# Run (limited to 50 papers/day)
python 02_abstract_filter_AI.py
```

### Ollama (New)
```bash
# Setup
ollama pull llama3.1

# Run (no limits)
sbatch run_filter_hpc.sh

# Or parallel for large datasets
python split_papers_for_hpc.py --num-batches 10
sbatch run_filter_hpc_array.sh
python merge_batches.py
```

## Benefits

1. **No API Costs** - Everything runs locally
2. **No Rate Limits** - Process unlimited papers
3. **Privacy** - Data never leaves your cluster
4. **Parallelization** - Use SLURM arrays for speed
5. **Reproducibility** - Same model, same results

## Performance

### Sequential Processing
- ~1-2 seconds per paper
- 100 papers ≈ 3-5 minutes
- 1000 papers ≈ 30-50 minutes

### Parallel Processing (10 batches)
- 1000 papers ≈ 5-10 minutes (10x speedup)
- Limited only by cluster resources

## Model Options

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| llama3.1 | 4.7GB | Medium | High |
| llama3.2 | 2.0GB | Fast | Good |
| mistral | 4.1GB | Medium | High |
| phi3 | 2.3GB | Fast | Good |

## Compatibility

### Works With
- ✅ SLURM clusters
- ✅ CPU-only nodes (no GPU needed)
- ✅ Conda environments
- ✅ Python 3.10.9

### Requirements
- Ollama installed
- 4+ CPU cores recommended
- 16GB+ RAM (adjust based on model)
- Sufficient disk space for models

## Migration Guide

If you were using the `ai_filtering` branch:

1. **Switch branch:**
   ```bash
   git checkout hpc_filt
   ```

2. **Remove old dependencies:**
   ```bash
   pip uninstall openai
   ```

3. **Install Ollama:**
   ```bash
   curl -fsSL https://ollama.ai/install.sh | sh
   ollama pull llama3.1
   ```

4. **Update your workflow:**
   - No more `.env` file needed
   - Use SLURM scripts instead of direct Python
   - Follow `QUICK_START_HPC.md`

## Testing

```bash
# Start Ollama
ollama serve &

# Run test
python test_ai_setup.py

# Should see:
# ✓ ALL TESTS PASSED!
```

## Support

- **Ollama issues:** https://github.com/ollama/ollama/issues
- **SLURM help:** Check your cluster documentation
- **General questions:** See HPC_SETUP.md

## Future Improvements

Potential enhancements:
- [ ] GPU support (if available)
- [ ] Dynamic batch sizing
- [ ] Progress tracking dashboard
- [ ] Resume from failed batches
- [ ] Multi-model ensemble

## Notes

- This branch is specifically for HPC cluster usage
- For local/desktop use, consider the standard keyword filtering
- Models download to `~/.ollama/models/` (can be large)
- First run is slower (model loading)
- Subsequent runs benefit from caching
