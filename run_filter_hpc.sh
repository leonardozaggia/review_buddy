#!/bin/bash
#SBATCH --partition=mpcg.p
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --job-name=paper_filter
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --output=logs/filter_%j.out
#SBATCH --error=logs/filter_%j.err


# ==============================================================================
# SLURM Job Script for AI-Powered Paper Filtering with Ollama
# ==============================================================================
#
# Usage:
#   sbatch run_filter_hpc.sh
#
# This script:
#   1. Starts Ollama server in background
#   2. Runs AI filtering on all papers
#   3. Saves results and stops Ollama
#
# Requirements:
#   - Ollama installed in user account
#   - Model pulled (e.g., ollama pull llama3.1)
#   - Conda environment with dependencies
# ==============================================================================

echo "=========================================="
echo "Paper Filtering Job Started"
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURM_NODELIST"
echo "Date: $(date)"
echo "=========================================="

# Create logs directory if it doesn't exist
mkdir -p logs

# Load modules or activate your conda environment
module load Miniforge3
module load ollama/0.8.0-GCCcore-13.1.0-CUDA-12.9.1
conda activate autosearch

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "Error: Ollama not found in PATH"
    echo "Install Ollama from: https://ollama.ai"
    exit 1
fi

# Start Ollama server in background
echo "Starting Ollama server..."
export OLLAMA_HOST=127.0.0.1:11434
ollama serve > logs/ollama_${SLURM_JOB_ID}.log 2>&1 &
OLLAMA_PID=$!
echo "Ollama server started with PID: $OLLAMA_PID"

# Wait for Ollama to be ready
echo "Waiting for Ollama to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "Ollama is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "Error: Ollama failed to start within 30 seconds"
        kill $OLLAMA_PID 2>/dev/null
        exit 1
    fi
    sleep 1
done

# List available models
echo "Available Ollama models:"
ollama list

# Run the filtering script
echo "=========================================="
echo "Starting AI filtering..."
echo "=========================================="
# Use smaller, faster model that's better at structured output on CPU
export OLLAMA_MODEL="llama3.1:70b"
python 02_abstract_filter_AI.py

FILTER_EXIT_CODE=$?

# Stop Ollama server
echo "Stopping Ollama server..."
kill $OLLAMA_PID 2>/dev/null
wait $OLLAMA_PID 2>/dev/null

echo "=========================================="
echo "Job Completed"
echo "Exit code: $FILTER_EXIT_CODE"
echo "Date: $(date)"
echo "=========================================="

exit $FILTER_EXIT_CODE
