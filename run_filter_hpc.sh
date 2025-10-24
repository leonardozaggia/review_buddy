#!/bin/bash
#SBATCH --job-name=paper_filter
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
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

# Load conda environment
echo "Loading conda environment..."
source ~/.bashrc
conda activate review_buddy || {
    echo "Error: Could not activate conda environment 'review_buddy'"
    echo "Create it with: conda create -n review_buddy python=3.10.9"
    exit 1
}

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
