"""
Test script to verify AI filtering setup.

This script tests the AI filtering components without processing papers.
Use this to verify your installation and API key before running the full pipeline.

Usage:
    python test_ai_setup.py
"""

import os
import sys
import logging
from pathlib import Path

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Note: python-dotenv not installed, reading .env manually")
    # Manual .env loading
    env_file = Path('.env')
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

# Enable debug logging for this test
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

print("="*70)
print("AI FILTERING SETUP TEST")
print("="*70)

# Test 1: Check openai package
print("\n[1/5] Checking OpenAI package installation...")
try:
    import openai
    print(f"✓ OpenAI package installed (version: {openai.__version__})")
except ImportError:
    print("✗ OpenAI package not found")
    print("  Install with: pip install openai")
    sys.exit(1)

# Test 2: Check API key
print("\n[2/5] Checking OpenRouter API key...")
api_key = os.getenv('OPENROUTER_API_KEY')
if api_key:
    print(f"✓ API key found (length: {len(api_key)})")
    if api_key.startswith('sk-or-'):
        print("✓ API key format looks correct")
    else:
        print("⚠ Warning: API key doesn't start with 'sk-or-' (might be invalid)")
else:
    print("✗ OPENROUTER_API_KEY not found in environment")
    print("  Add to .env file: OPENROUTER_API_KEY=your_key_here")
    sys.exit(1)

# Test 3: Check module imports
print("\n[3/5] Checking module imports...")
try:
    from src.llm_client import OpenRouterClient
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

# Test 4: Initialize client
print("\n[4/5] Initializing OpenRouter client...")
try:
    client = OpenRouterClient(
        api_key=api_key,
        model="openai/gpt-oss-20b:free",
        cache_dir=None  # Disable caching for test
    )
    print("✓ OpenRouter client initialized successfully")
except Exception as e:
    print(f"✗ Failed to initialize client: {e}")
    sys.exit(1)

# Test 5: Test API call (optional, only if user confirms)
print("\n[5/5] API Connection Test")
print("Would you like to make a test API call? This will verify your API key works.")
print("(This is free and won't count against any quotas)")

try:
    response = input("Test API? (y/n): ").strip().lower()
except:
    response = 'n'

if response == 'y':
    print("\nMaking test API call...")
    
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
            print("✓ API call successful!")
            print(f"\nTest result:")
            print(f"  Question: {test_filters['test_filter']}")
            print(f"  Answer: {'YES' if result['filters']['test_filter']['should_filter'] else 'NO'}")
            print(f"  Confidence: {result['filters']['test_filter']['confidence']:.2f}")
            print(f"  Reason: {result['filters']['test_filter']['reason']}")
        else:
            print("✗ API call failed")
            print(f"  Error: {result.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except Exception as e:
        print(f"✗ API call failed with exception: {e}")
        sys.exit(1)
else:
    print("Skipping API test")

# Success!
print("\n" + "="*70)
print("✓ ALL TESTS PASSED!")
print("="*70)
print("\nYour AI filtering setup is ready to use.")
print("\nNext steps:")
print("  1. Run: python 01_fetch_metadata.py")
print("  2. Run: python 02_abstract_filter_AI.py")
print("  3. Review: results/papers_filtered_ai.csv")
print("\nFor more information, see: docs/AI_FILTERING_QUICKSTART.md")
