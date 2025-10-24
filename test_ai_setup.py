"""
Test script to verify AI filtering setup with Ollama.

This script tests the AI filtering components without processing papers.
Use this to verify your installation before running the full pipeline.

Usage:
    python test_ai_setup.py
"""

import os
import sys
import logging
from pathlib import Path

# Enable debug logging for this test
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

print("="*70)
print("AI FILTERING SETUP TEST (OLLAMA)")
print("="*70)

# Test 1: Check requests package
print("\n[1/5] Checking requests package installation...")
try:
    import requests
    print(f"✓ requests package installed")
except ImportError:
    print("✗ requests package not found")
    print("  Install with: pip install requests")
    sys.exit(1)

# Test 2: Check Ollama installation
print("\n[2/5] Checking Ollama installation...")
import subprocess
try:
    result = subprocess.run(['which', 'ollama'], capture_output=True, text=True)
    if result.returncode == 0:
        ollama_path = result.stdout.strip()
        print(f"✓ Ollama found at: {ollama_path}")
    else:
        print("✗ Ollama not found in PATH")
        print("  Install from: https://ollama.ai")
        sys.exit(1)
except Exception as e:
    print(f"✗ Error checking for Ollama: {e}")
    sys.exit(1)

# Test 3: Check module imports
print("\n[3/5] Checking module imports...")
try:
    from src.llm_client import OllamaClient
    print("✓ src.llm_client imported successfully")
except ImportError as e:
    print(f"✗ Failed to import src.llm_client: {e}")
    sys.exit(1)

try:
    from src.ai_abstract_filter import AIAbstractFilter
    print("✓ src.ai_abstract_filter imported successfully")
except ImportError as e:
    print(f"✗ Failed to import src.ai_abstract_filter: {e}")
    sys.exit(1)

# Test 4: Check if Ollama server is running
print("\n[4/5] Checking Ollama server...")
ollama_url = "http://localhost:11434"
try:
    response = requests.get(f"{ollama_url}/api/tags", timeout=5)
    if response.status_code == 200:
        models = response.json().get('models', [])
        print(f"✓ Ollama server is running at {ollama_url}")
        print(f"  Available models: {len(models)}")
        for model in models:
            print(f"    - {model['name']}")
    else:
        print(f"⚠ Ollama server responded with status {response.status_code}")
except requests.exceptions.ConnectionError:
    print("✗ Ollama server is not running")
    print("  Start with: ollama serve")
    print("  Or the server will start automatically in SLURM jobs")
    sys.exit(1)
except Exception as e:
    print(f"✗ Error connecting to Ollama: {e}")
    sys.exit(1)

# Test 5: Initialize client
print("\n[5/5] Initializing Ollama client...")
try:
    # Get first available model or use default
    response = requests.get(f"{ollama_url}/api/tags")
    models = response.json().get('models', [])
    
    if not models:
        print("✗ No models available in Ollama")
        print("  Pull a model with: ollama pull llama3.1")
        sys.exit(1)
    
    test_model = models[0]['name']
    print(f"  Testing with model: {test_model}")
    
    client = OllamaClient(
        model=test_model,
        base_url=ollama_url,
        cache_dir=None  # Disable caching for test
    )
    print("✓ Ollama client initialized successfully")
except Exception as e:
    print(f"✗ Failed to initialize client: {e}")
    sys.exit(1)

# Test 6: Optional API test
print("\n[6/6] API Connection Test")
print("Would you like to make a test inference call?")
print("(This will verify the model works correctly)")

try:
    response = input("Test inference? (y/n): ").strip().lower()
except:
    response = 'n'

if response == 'y':
    print("\nMaking test inference call...")
    
    # Create a simple test paper
    from src.models import Paper
    test_paper = Paper(
        title="Machine Learning in Healthcare: A Review",
        abstract="This paper reviews recent advances in machine learning applications for healthcare diagnosis and treatment."
    )
    
    # Test filters
    test_filters = {
        'test_filter': "Is this a review paper?"
    }
    
    try:
        result = client.check_paper(test_paper, test_filters)
        
        if result['success']:
            print("✓ Inference call successful!")
            print(f"\nTest result:")
            print(f"  Question: {test_filters['test_filter']}")
            print(f"  Answer: {'YES' if result['filters']['test_filter']['should_filter'] else 'NO'}")
            print(f"  Confidence: {result['filters']['test_filter']['confidence']:.2f}")
            print(f"  Reason: {result['filters']['test_filter']['reason']}")
        else:
            print("✗ Inference call failed")
            print(f"  Error: {result.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except Exception as e:
        print(f"✗ Inference call failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
else:
    print("Skipping inference test")

# Success!
print("\n" + "="*70)
print("✓ ALL TESTS PASSED!")
print("="*70)
print("\nYour Ollama AI filtering setup is ready to use.")
print("\nNext steps:")
print("  1. Run: python 01_fetch_metadata.py")
print("  2. For small datasets: sbatch run_filter_hpc.sh")
print("  3. For large datasets: python split_papers_for_hpc.py && sbatch run_filter_hpc_array.sh")
print("\nFor detailed instructions, see: HPC_SETUP.md")
