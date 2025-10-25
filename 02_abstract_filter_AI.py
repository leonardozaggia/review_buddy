"""
AI-powered filter for papers based on abstract content.

This script loads papers from the previous search step, applies AI-based filters
using local Ollama LLM to analyze abstracts, and saves the filtered results.

CUSTOMIZE YOUR FILTERS BELOW - Edit the settings in the CONFIG section.

Usage:
    python 02_abstract_filter_AI.py

Requirements:
    - Ollama installed with model pulled (e.g., llama3.1)
    - Ollama server running (starts automatically in SLURM job)

Output:
    - results/papers_filtered_ai.csv - Filtered papers
    - results/references_filtered_ai.bib - Filtered bibliography
    - results/manual_review_ai.csv - Papers flagged for manual review
    - results/filtered_out_ai/ - Papers removed by each filter
    - results/ai_filtering_log_*.json - Detailed decision log
"""

import logging
import os
from pathlib import Path

from src.ai_abstract_filter import AIAbstractFilter
from src.llm_client import OllamaClient
from src.utils import load_papers_from_bib, save_papers_csv, save_papers_bib


# ============================================================================
# CONFIGURATION - CUSTOMIZE YOUR FILTERS HERE
# ============================================================================

# AI Model Configuration
AI_CONFIG = {
    'model': os.getenv('OLLAMA_MODEL', 'llama3.1:8b'),  # Ollama model to use (can override with env var)
    'ollama_url': 'http://localhost:11434',  # Ollama server URL
    'temperature': 0.1,                   # Low but non-zero to avoid repetition loops
    'retry_attempts': 3,                  # Retry failed API calls
    'cache_responses': True,              # Cache to avoid redundant calls
    'confidence_threshold': 0.5,          # Min confidence to filter (0.0-1.0)
}

# Filter Definitions
# Define each filter with a natural language prompt
FILTERS_CONFIG = {
    'epilepsy': {
        'enabled': True,
        'prompt': "Does this paper focus primarily on epileptic spikes, seizure detection, or epileptiform activity?",
        'description': "Papers about epilepsy-related spike detection"
    },
    
    'bci': {
        'enabled': True,
        'prompt': "Is this paper about brain-computer interfaces (BCI) or brain-machine interfaces (BMI)?",
        'description': "Papers about BCI/BMI systems"
    },
    
    'non_human': {
        'enabled': True,
        'prompt': "Is this paper based on animal studies, in-vitro experiments, or computational models only (not human subjects)?",
        'description': "Non-human or in-vitro studies"
    },
    
    'non_empirical': {
        'enabled': True,
        'prompt': "Is this a review paper, survey, meta-analysis, or opinion piece without original empirical data collection?",
        'description': "Reviews and non-empirical papers"
    },
    
    # Add your own custom filters here - examples:
    # 'fmri_only': {
    #     'enabled': False,
    #     'prompt': "Does this paper use ONLY fMRI methods without any EEG/MEG/iEEG data?",
    #     'description': "Papers using only fMRI"
    # },
    # 'pediatric': {
    #     'enabled': False,
    #     'prompt': "Is this paper focused exclusively on pediatric populations (children/infants)?",
    #     'description': "Pediatric-only studies"
    # },
}

# ============================================================================
# END CONFIGURATION
# ============================================================================


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main AI filtering workflow"""
    
    logger.info("="*70)
    logger.info("AI-POWERED ABSTRACT FILTERING (LOCAL OLLAMA)")
    logger.info("="*70)
    
    # Setup paths
    results_dir = Path("results")
    bib_file = results_dir / "references.bib"
    filtered_dir = results_dir / "filtered_out_ai"
    filtered_dir.mkdir(exist_ok=True)
    
    # Check if input file exists
    if not bib_file.exists():
        logger.error(f"Input file not found: {bib_file}")
        logger.error("Please run 01_fetch_metadata.py first")
        return
    
    # Load papers
    logger.info(f"\nLoading papers from {bib_file}...")
    papers = load_papers_from_bib(bib_file)
    
    if not papers:
        logger.error("No papers loaded. Exiting.")
        return
    
    logger.info(f"Loaded {len(papers)} papers")
    
    # Initialize Ollama client
    logger.info("\nInitializing Ollama client...")
    logger.info(f"Model: {AI_CONFIG['model']}")
    logger.info(f"Ollama URL: {AI_CONFIG['ollama_url']}")
    logger.info(f"Confidence threshold: {AI_CONFIG['confidence_threshold']}")
    
    cache_dir = results_dir / "ai_cache" if AI_CONFIG['cache_responses'] else None
    
    try:
        llm_client = OllamaClient(
            model=AI_CONFIG['model'],
            base_url=AI_CONFIG['ollama_url'],
            temperature=AI_CONFIG['temperature'],
            cache_dir=cache_dir,
            retry_attempts=AI_CONFIG['retry_attempts']
        )
    except Exception as e:
        logger.error(f"Failed to initialize Ollama client: {e}")
        return
    
    # Create AI filter
    ai_filter = AIAbstractFilter(
        llm_client=llm_client,
        confidence_threshold=AI_CONFIG['confidence_threshold'],
        log_decisions=True,
        log_dir=results_dir
    )
    
    # Log enabled filters
    enabled = [name for name, cfg in FILTERS_CONFIG.items() if cfg.get('enabled', True)]
    logger.info(f"\nFilters enabled: {', '.join(enabled)}")
    for name in enabled:
        logger.info(f"  - {name}: {FILTERS_CONFIG[name]['description']}")
    
    # Apply filters
    logger.info("\n" + "="*70)
    logger.info("APPLYING AI FILTERS")
    logger.info("="*70 + "\n")
    
    results = ai_filter.apply_all_filters(papers, FILTERS_CONFIG)
    
    kept_papers = results['kept']
    filtered_papers = results['filtered']
    manual_review = results['manual_review']
    summary = results['summary']
    
    # Print summary
    logger.info("\n" + "="*70)
    logger.info("AI FILTERING SUMMARY")
    logger.info("="*70)
    logger.info(f"Initial papers:        {summary['initial_count']}")
    logger.info(f"Papers kept:           {summary['final_count']}")
    logger.info(f"Papers filtered out:   {summary['total_filtered']}")
    logger.info(f"Manual review needed:  {summary['manual_review_count']}")
    logger.info(f"Retention rate:        {summary['final_count']/summary['initial_count']*100:.1f}%")
    
    logger.info("\nBreakdown by filter:")
    for filter_name, count in summary['filtered_by_category'].items():
        logger.info(f"  - {filter_name:20s}: {count:4d} papers")
    
    logger.info("\nOllama Usage:")
    api_stats = summary['api_stats']
    logger.info(f"  - Model calls made:    {api_stats['api_calls']}")
    logger.info(f"  - Cache hits:          {api_stats['cache_hits']}")
    logger.info(f"  - Failed calls:        {api_stats['failed_calls']}")
    logger.info(f"  - Cache hit rate:      {api_stats['cache_hit_rate']}")
    logger.info(f"  - Model used:          {api_stats['model']}")
    
    # Save filtered papers
    logger.info("\n" + "="*70)
    logger.info("SAVING RESULTS")
    logger.info("="*70)
    
    # Save kept papers
    save_papers_csv(kept_papers, results_dir / "papers_filtered_ai.csv")
    save_papers_bib(kept_papers, results_dir / "references_filtered_ai.bib")
    logger.info(f"Saved {len(kept_papers)} kept papers")
    
    # Save manual review papers
    if manual_review:
        save_papers_csv(manual_review, results_dir / "manual_review_ai.csv")
        logger.info(f"Saved {len(manual_review)} papers for manual review")
    
    # Save filtered out papers by category
    for filter_name, papers_list in filtered_papers.items():
        if papers_list:
            csv_file = filtered_dir / f"{filter_name}.csv"
            save_papers_csv(papers_list, csv_file)
            logger.info(f"Saved {len(papers_list)} {filter_name} papers to {csv_file}")
    
    logger.info("\n" + "="*70)
    logger.info("AI FILTERING COMPLETE!")
    logger.info("="*70)
    logger.info(f"\nFiltered results saved to:")
    logger.info(f"  - {results_dir / 'papers_filtered_ai.csv'}")
    logger.info(f"  - {results_dir / 'references_filtered_ai.bib'}")
    
    if manual_review:
        logger.info(f"\nManual review needed:")
        logger.info(f"  - {results_dir / 'manual_review_ai.csv'}")
    
    logger.info(f"\nFiltered out papers saved to: {filtered_dir}/")
    logger.info(f"Decision log saved to: {results_dir}/ai_filtering_log_*.json")
    
    logger.info("\nNext step:")
    logger.info("  1. Review papers in manual_review_ai.csv")
    logger.info("  2. Run compare_filtering_strategies.py to compare with keyword filtering")
    logger.info("  3. Run 03_download_papers.py to download PDFs")


if __name__ == "__main__":
    main()
