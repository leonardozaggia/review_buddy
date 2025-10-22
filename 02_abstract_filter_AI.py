"""
AI-powered filter for papers based on abstract content.

This script loads papers from the previous search step, applies AI-based filters
using LLM to analyze abstracts, and saves the filtered results.

CUSTOMIZE YOUR FILTERS BELOW - Edit the settings in the CONFIG section.

Usage:
    python 02_abstract_filter_AI.py

Requirements:
    - Set OPENROUTER_API_KEY in .env file
    - Install openai package: pip install openai

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
from dotenv import load_dotenv

from src.ai_abstract_filter import AIAbstractFilter
from src.llm_client import OpenRouterClient
from src.utils import load_papers_from_bib, save_papers_csv, save_papers_bib


# Load environment variables
load_dotenv()


# ============================================================================
# CONFIGURATION - CUSTOMIZE YOUR FILTERS HERE
# ============================================================================

# ⚠️ IMPORTANT: FREE MODEL LIMITATION
# The default free model has a 50 requests per day limit.
# For datasets >50 papers:
#   1. Use keyword filtering (02_abstract_filter.py) instead
#   2. Upgrade to paid model (see docs/AI_FILTERING_GUIDE.md)
#   3. Split processing across multiple days

# AI Model Configuration
AI_CONFIG = {
    'model': 'openai/gpt-oss-20b:free',  # ⚠️ 50 requests/day limit
    'temperature': 0.0,                   # Deterministic responses
    'max_tokens': 200,                    # Token limit per response
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
    logger.info("AI-POWERED ABSTRACT FILTERING")
    logger.info("="*70)
    
    # Setup paths
    results_dir = Path("results")
    bib_file = results_dir / "references.bib"
    filtered_dir = results_dir / "filtered_out_ai"
    filtered_dir.mkdir(exist_ok=True)
    
    # Check API key
    api_key = os.getenv('OPENROUTER_API_KEY')
    if not api_key:
        logger.error("OPENROUTER_API_KEY not found in environment variables!")
        logger.error("Please set it in your .env file")
        return
    
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
    
    # Initialize LLM client
    logger.info("\nInitializing OpenRouter client...")
    logger.info(f"Model: {AI_CONFIG['model']}")
    logger.info(f"Confidence threshold: {AI_CONFIG['confidence_threshold']}")
    
    cache_dir = results_dir / "ai_cache" if AI_CONFIG['cache_responses'] else None
    
    try:
        llm_client = OpenRouterClient(
            api_key=api_key,
            model=AI_CONFIG['model'],
            temperature=AI_CONFIG['temperature'],
            max_tokens=AI_CONFIG['max_tokens'],
            cache_dir=cache_dir,
            retry_attempts=AI_CONFIG['retry_attempts']
        )
    except Exception as e:
        logger.error(f"Failed to initialize LLM client: {e}")
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
    
    logger.info("\nAPI Usage:")
    api_stats = summary['api_stats']
    logger.info(f"  - API calls made:      {api_stats['api_calls']}")
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
