# Quick Start - HPC Filtering

Fast reference for running AI filtering on HPC cluster with Ollama.

## One-Time Setup

```bash
# 1. Create environment
conda create -n review_buddy python=3.10.9
conda activate review_buddy
pip install -r requirements.txt

# 2. Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# 3. Pull model (choose one)
ollama pull llama3.1     # Recommended
ollama pull llama3.2     # Smaller/faster
ollama pull mistral      # Alternative
```

## Small Dataset (<200 papers)

```bash
# 1. Fetch papers
python 01_fetch_metadata.py

# 2. Submit single job
sbatch run_filter_hpc.sh

# 3. Check status
squeue -u $USER
tail -f logs/filter_*.out

# 4. Results in:
# results/papers_filtered_ai.csv
# results/references_filtered_ai.bib
```

## Large Dataset (>200 papers)

```bash
# 1. Fetch papers
python 01_fetch_metadata.py

# 2. Split into batches
python split_papers_for_hpc.py --num-batches 10

# 3. Update array size in run_filter_hpc_array.sh
# Change: #SBATCH --array=0-9

# 4. Submit array job
sbatch run_filter_hpc_array.sh

# 5. Monitor
squeue -u $USER
watch -n 10 'squeue -u $USER'

# 6. After completion, merge
python merge_batches.py

# 7. Results in:
# results/papers_filtered_ai.csv
# results/references_filtered_ai.bib
# results/merged_summary.json
```

## Test Setup

```bash
# Start Ollama (if not running)
ollama serve &

# Run test
python test_ai_setup.py
```

## Troubleshooting

### Ollama not starting
```bash
# Check if already running
ps aux | grep ollama

# Kill existing and restart
pkill ollama
ollama serve &
```

### Model not found
```bash
# List models
ollama list

# Pull missing model
ollama pull llama3.1
```

### Job fails
```bash
# Check logs
cat logs/filter_*.err
cat logs/ollama_*.log

# Test locally first
python 02_abstract_filter_AI.py
```

## Resource Guidelines

| Papers | Batches | CPUs | Memory | Time |
|--------|---------|------|--------|------|
| <100   | 1       | 4    | 16GB   | 30m  |
| 100-500| 5-10    | 4    | 16GB   | 1h   |
| 500-1000| 10-20  | 4    | 16GB   | 2h   |
| >1000  | 20-50   | 4    | 16GB   | 2h   |

## Customize Filters

Edit `process_batch.py` or `02_abstract_filter_AI.py`:

```python
FILTERS_CONFIG = {
    'my_filter': {
        'enabled': True,
        'prompt': "Your question about the paper?",
    },
}
```

## Full Documentation

See `HPC_SETUP.md` for complete guide.
