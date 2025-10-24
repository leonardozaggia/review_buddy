# HPC Setup Guide - AI Filtering with Ollama

This guide explains how to set up and run AI-powered paper filtering on an HPC cluster using local Ollama models.

## Overview

The system runs LLM-based abstract filtering entirely on your HPC cluster using Ollama, with no external API calls or rate limits. Papers can be processed in parallel using SLURM array jobs for fast processing of large datasets.

## Prerequisites

- SLURM cluster access
- Conda/Miniconda installed
- Sufficient disk space for models (~4-20GB depending on model)

## Step 1: Initial Setup

### 1.1 Clone Repository

```bash
cd ~/
git clone <your-repo-url> review_buddy
cd review_buddy
git checkout hpc_filt  # Use the HPC branch
```

### 1.2 Create Conda Environment

```bash
conda create -n review_buddy python=3.10.9
conda activate review_buddy
pip install -r requirements.txt
```

### 1.3 Install Ollama

```bash
# Download and install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Verify installation
which ollama
# Should show: ~/.local/bin/ollama or similar
```

### 1.4 Pull Model

```bash
# Pull the model you want to use (this may take a while)
ollama pull llama3.1

# Verify model is available
ollama list
```

**Available models:**
- `llama3.1` (4.7GB) - Recommended, good balance
- `llama3.2` (2.0GB) - Smaller, faster
- `mistral` (4.1GB) - Alternative option
- `phi3` (2.3GB) - Compact model

**Note:** Models are stored in `~/.ollama/models/` by default.

## Step 2: Prepare Your Papers

### 2.1 Fetch Papers (on login node or local machine)

```bash
# Edit query.txt with your search terms
python 01_fetch_metadata.py
```

This creates `results/references.bib` with all papers to filter.

## Step 3: Choose Processing Method

### Option A: Single Job (Small Datasets <200 papers)

For smaller datasets, process all papers in one job:

```bash
# Edit run_filter_hpc.sh if needed (adjust resources)
sbatch run_filter_hpc.sh
```

**Monitor progress:**
```bash
squeue -u $USER
tail -f logs/filter_*.out
```

### Option B: Parallel Processing (Large Datasets >200 papers)

For large datasets, split into batches and process in parallel:

#### 3.1 Split Papers into Batches

```bash
# Split into 10 batches (adjust as needed)
python split_papers_for_hpc.py --num-batches 10
```

This creates `results/batches/batch_0.bib` through `batch_9.bib`.

#### 3.2 Edit Array Job Script

Edit `run_filter_hpc_array.sh` and update the array parameter:

```bash
#SBATCH --array=0-9  # Change to match number of batches
```

For example:
- 5 batches: `--array=0-4`
- 10 batches: `--array=0-9`
- 20 batches: `--array=0-19`

#### 3.3 Submit Array Job

```bash
sbatch run_filter_hpc_array.sh
```

**Monitor progress:**
```bash
squeue -u $USER
# Watch specific task outputs
tail -f logs/filter_array_*_0.out  # Task 0
tail -f logs/filter_array_*_5.out  # Task 5
```

#### 3.4 Merge Results

After all tasks complete:

```bash
python merge_batches.py
```

This merges all batch results into:
- `results/papers_filtered_ai.csv`
- `results/references_filtered_ai.bib`
- `results/merged_summary.json`

## Step 4: Review Results

```bash
# View summary
cat results/merged_summary.json

# Check papers kept
wc -l results/papers_filtered_ai.csv

# Review papers needing manual review
cat results/manual_review_ai.csv
```

## Configuration

### Model Selection

Edit `02_abstract_filter_AI.py` (or `process_batch.py` for parallel jobs):

```python
AI_CONFIG = {
    'model': 'llama3.1',  # Change to your preferred model
    'ollama_url': 'http://localhost:11434',
    'confidence_threshold': 0.5,  # Adjust threshold (0.0-1.0)
}
```

### Filter Customization

Edit `process_batch.py` or `02_abstract_filter_AI.py`:

```python
FILTERS_CONFIG = {
    'your_filter': {
        'enabled': True,
        'prompt': "Your natural language question about the paper?",
    },
}
```

### Resource Allocation

Edit SLURM scripts to adjust resources:

```bash
#SBATCH --cpus-per-task=4    # CPU cores
#SBATCH --mem=16G            # Memory
#SBATCH --time=02:00:00      # Time limit
```

**Guidelines:**
- CPU: 4-8 cores recommended for Ollama
- Memory: 16GB for most models, 32GB for larger models
- Time: ~1-2 seconds per paper, estimate accordingly

## Troubleshooting

### Issue: Ollama fails to start

**Check logs:**
```bash
cat logs/ollama_*.log
```

**Common causes:**
- Port already in use (array jobs use different ports automatically)
- Model not pulled: `ollama list` to verify
- Insufficient memory: increase `--mem` in SLURM script

### Issue: Model not found

```bash
# List available models
ollama list

# Pull missing model
ollama pull llama3.1
```

### Issue: Timeout errors

Increase timeout in `src/llm_client.py`:

```python
response = requests.post(
    ...,
    timeout=300  # Increase from 120 to 300 seconds
)
```

### Issue: Out of memory

**Solutions:**
1. Use smaller model: `llama3.2` or `phi3`
2. Increase SLURM memory: `#SBATCH --mem=32G`
3. Process fewer papers per batch

### Issue: Array job tasks fail randomly

**Check for:**
- Disk quota: `quota -s`
- Temp space: `df -h /tmp`
- Network issues: test with single job first

## Performance Tips

### Optimize Batch Size

- **Small papers (short abstracts):** 50-100 papers per batch
- **Large papers (long abstracts):** 20-50 papers per batch
- **More batches = faster processing** (up to cluster limits)

### Use Caching

Caching is enabled by default. If re-running:
```python
AI_CONFIG = {
    'cache_responses': True,  # Keep this enabled
}
```

### Monitor Resource Usage

```bash
# While job is running
sstat -j <job_id> --format=JobID,AveCPU,AveRSS,MaxRSS

# After job completes
sacct -j <job_id> --format=JobID,Elapsed,MaxRSS,State
```

## Cost Comparison

### OpenRouter API (original)
- Free tier: 50 papers/day max
- Paid tier: ~$0.15-$2.50 per 100 papers

### HPC Ollama (this implementation)
- **Cost: $0** (uses cluster allocation)
- **Limit: None** (process thousands of papers)
- **Speed: Parallelizable** (10x faster with array jobs)

## Example Workflow

```bash
# 1. Setup (one time)
conda activate review_buddy
ollama pull llama3.1

# 2. Fetch papers
python 01_fetch_metadata.py

# 3. Split for parallel processing
python split_papers_for_hpc.py --num-batches 10

# 4. Submit array job
sbatch run_filter_hpc_array.sh

# 5. Wait for completion
watch squeue -u $USER

# 6. Merge results
python merge_batches.py

# 7. Review
cat results/merged_summary.json
head results/papers_filtered_ai.csv
```

## Support

For issues specific to:
- **Ollama:** https://github.com/ollama/ollama
- **SLURM:** Check your cluster documentation
- **This tool:** See README.md

## Advanced: Custom Models

To use a different model:

```bash
# Pull model
ollama pull <model-name>

# Update config
# Edit AI_CONFIG['model'] in scripts

# Test locally first
python 02_abstract_filter_AI.py
```

## Notes

- First run is slower (model loading)
- Subsequent runs use cached responses
- Models run on CPU (no GPU needed)
- Each array task uses separate Ollama instance
- Results are automatically deduplicated when merged
