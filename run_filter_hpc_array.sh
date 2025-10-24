#!/bin/bash
#SBATCH --job-name=paper_filter_array
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=logs/filter_array_%A_%a.out
#SBATCH --error=logs/filter_array_%A_%a.err
#SBATCH --array=0-9

# ==============================================================================
# SLURM Array Job Script for Parallel Paper Filtering
# ==============================================================================
#
# Usage:
#   python split_papers_for_hpc.py  # First, split papers into batches
#   sbatch run_filter_hpc_array.sh  # Then submit array job
#
# This script:
#   1. Starts Ollama server for this task
#   2. Processes one batch of papers (task-specific)
#   3. Saves results for this batch
#   4. After all tasks complete, run merge script
#
# Array Configuration:
#   - Adjust --array parameter based on number of batches
#   - Each task processes one batch independently
#   - Example: --array=0-9 for 10 batches
# ==============================================================================

echo "=========================================="
echo "Paper Filtering Array Job"
echo "Job ID: $SLURM_ARRAY_JOB_ID"
echo "Task ID: $SLURM_ARRAY_TASK_ID"
echo "Node: $SLURM_NODELIST"
echo "Date: $(date)"
echo "=========================================="

# Create logs directory
mkdir -p logs

# Load conda environment
echo "Loading conda environment..."
source ~/.bashrc
conda activate review_buddy || {
    echo "Error: Could not activate conda environment 'review_buddy'"
    exit 1
}

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "Error: Ollama not found in PATH"
    exit 1
fi

# Use unique port for this task to avoid conflicts
OLLAMA_PORT=$((11434 + SLURM_ARRAY_TASK_ID))
export OLLAMA_HOST=127.0.0.1:${OLLAMA_PORT}

# Start Ollama server in background
echo "Starting Ollama server on port ${OLLAMA_PORT}..."
ollama serve > logs/ollama_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.log 2>&1 &
OLLAMA_PID=$!
echo "Ollama server started with PID: $OLLAMA_PID"

# Wait for Ollama to be ready
echo "Waiting for Ollama to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:${OLLAMA_PORT}/api/tags > /dev/null 2>&1; then
        echo "Ollama is ready on port ${OLLAMA_PORT}!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "Error: Ollama failed to start within 30 seconds"
        kill $OLLAMA_PID 2>/dev/null
        exit 1
    fi
    sleep 1
done

# Run filtering for this specific batch
echo "=========================================="
echo "Processing batch ${SLURM_ARRAY_TASK_ID}..."
echo "=========================================="
python process_batch.py \
    --batch-id ${SLURM_ARRAY_TASK_ID} \
    --ollama-url http://localhost:${OLLAMA_PORT}

FILTER_EXIT_CODE=$?

# Stop Ollama server
echo "Stopping Ollama server..."
kill $OLLAMA_PID 2>/dev/null
wait $OLLAMA_PID 2>/dev/null

echo "=========================================="
echo "Task ${SLURM_ARRAY_TASK_ID} Completed"
echo "Exit code: $FILTER_EXIT_CODE"
echo "Date: $(date)"
echo "=========================================="

exit $FILTER_EXIT_CODE
