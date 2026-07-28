"""
Filter papers based on abstract content.

This script loads papers from the previous search step, applies various filters
to exclude unwanted papers, and saves the filtered results.

CUSTOMIZE YOUR FILTERS BELOW - Edit the settings in the CONFIG section.

Usage:
    python 02_abstract_filter.py

Output:
    - results/papers_filtered.csv - Filtered papers
    - results/references_filtered.bib - Filtered bibliography
    - results/filtered_out/ - Papers removed by each filter
"""

import logging
from pathlib import Path

from src.abstract_filter import AbstractFilter
from src.utils import load_papers_from_bib, save_papers_csv, save_papers_bib
from src.settings import load_settings


# ============================================================================
# CONFIGURATION
# ============================================================================
# All filter settings live in config.yaml (see config.example.yaml) under
# `filter:`. Edit that file - not this script - to enable/disable filters or
# change keyword lists, so your customizations stay out of git history.
# ============================================================================

_FILTER = load_settings().filter
FILTERS_ENABLED = _FILTER.get("enabled", {})   # {filter_name: bool}
KEYWORD_FILTERS = _FILTER.get("keywords", {})  # {filter_name: [keywords]}


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main filtering workflow"""
    
    logger.info("="*70)
    logger.info("ABSTRACT-BASED PAPER FILTERING")
    logger.info("="*70)
    
    # Setup paths
    results_dir = Path("results")
    bib_file = results_dir / "references.bib"
    filtered_dir = results_dir / "filtered_out"
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
    
    # Create filter and register all keyword filters
    filter_tool = AbstractFilter()
    
    # Register all keyword-based filters
    for filter_name, keywords in KEYWORD_FILTERS.items():
        filter_tool.add_custom_filter(filter_name, keywords)
        logger.info(f"Registered filter '{filter_name}' with {len(keywords)} keywords")
    
    # Determine which filters to apply
    filters_to_apply = [name for name, enabled in FILTERS_ENABLED.items() if enabled]
    
    logger.info(f"\nFilters to apply: {', '.join(filters_to_apply)}")
    
    # Apply filters
    logger.info("\n" + "="*70)
    logger.info("APPLYING FILTERS")
    logger.info("="*70 + "\n")
    
    results = filter_tool.apply_all_filters(papers, filters_to_apply=filters_to_apply)
    
    kept_papers = results['kept']
    filtered_papers = results['filtered']
    summary = results['summary']
    
    # Print summary
    logger.info("\n" + "="*70)
    logger.info("FILTERING SUMMARY")
    logger.info("="*70)
    logger.info(f"Initial papers:        {summary['initial_count']}")
    logger.info(f"Papers kept:           {summary['final_count']}")
    logger.info(f"Papers filtered out:   {summary['total_filtered']}")
    logger.info(f"Retention rate:        {summary['final_count']/summary['initial_count']*100:.1f}%")
    logger.info("\nBreakdown by filter:")
    for filter_name, count in summary['filtered_by_category'].items():
        logger.info(f"  - {filter_name:20s}: {count:4d} papers")
    
    # Save filtered papers
    logger.info("\n" + "="*70)
    logger.info("SAVING RESULTS")
    logger.info("="*70)
    
    # Save kept papers
    save_papers_csv(kept_papers, results_dir / "papers_filtered.csv")
    save_papers_bib(kept_papers, results_dir / "references_filtered.bib")
    
    # Save filtered out papers by category
    for filter_name, papers_list in filtered_papers.items():
        if papers_list:
            csv_file = filtered_dir / f"{filter_name}.csv"
            save_papers_csv(papers_list, csv_file)
            logger.info(f"Saved {len(papers_list)} {filter_name} papers to {csv_file}")
    
    logger.info("\n" + "="*70)
    logger.info("FILTERING COMPLETE!")
    logger.info("="*70)
    logger.info(f"\nFiltered results saved to:")
    logger.info(f"  - {results_dir / 'papers_filtered.csv'}")
    logger.info(f"  - {results_dir / 'references_filtered.bib'}")
    logger.info(f"\nFiltered out papers saved to: {filtered_dir}/")
    logger.info("\nNext step: Run 03_download_papers.py to download PDFs")


if __name__ == "__main__":
    main()
