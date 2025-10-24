"""
Process a single batch of papers for AI filtering.

This script is called by the SLURM array job to process one batch.
Each array task processes a different batch independently.

Usage:
    python process_batch.py --batch-id 0 --ollama-url http://localhost:11434
"""

import argparse
import logging
from pathlib import Path

from src.ai_abstract_filter import AIAbstractFilter
from src.llm_client import OllamaClient
from src.utils import load_papers_from_bib, save_papers_csv, save_papers_bib
import json


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Filter configuration (same as 02_abstract_filter_AI.py)
FILTERS_CONFIG = {
    'epilepsy': {
        'enabled': True,
        'prompt': "Does this paper focus primarily on epileptic spikes, seizure detection, or epileptiform activity?",
    },
    'bci': {
        'enabled': True,
        'prompt': "Is this paper about brain-computer interfaces (BCI) or brain-machine interfaces (BMI)?",
    },
    'non_human': {
        'enabled': True,
        'prompt': "Is this paper based on animal studies, in-vitro experiments, or computational models only (not human subjects)?",
    },
    'non_empirical': {
        'enabled': True,
        'prompt': "Is this a review paper, survey, meta-analysis, or opinion piece without original empirical data collection?",
    },
}


def main():
    parser = argparse.ArgumentParser(description="Process one batch of papers")
    parser.add_argument(
        '--batch-id',
        type=int,
        required=True,
        help='Batch ID to process'
    )
    parser.add_argument(
        '--ollama-url',
        type=str,
        default='http://localhost:11434',
        help='Ollama server URL'
    )
    parser.add_argument(
        '--model',
        type=str,
        default='llama3.1',
        help='Ollama model to use'
    )
    parser.add_argument(
        '--confidence-threshold',
        type=float,
        default=0.5,
        help='Confidence threshold for filtering'
    )
    
    args = parser.parse_args()
    
    # Setup paths
    batch_dir = Path("results/batches")
    output_dir = Path("results/batch_results")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    batch_file = batch_dir / f"batch_{args.batch_id}.bib"
    
    logger.info(f"Processing batch {args.batch_id}")
    logger.info(f"Input: {batch_file}")
    logger.info(f"Ollama URL: {args.ollama_url}")
    logger.info(f"Model: {args.model}")
    
    # Check if batch file exists
    if not batch_file.exists():
        logger.error(f"Batch file not found: {batch_file}")
        return 1
    
    # Load papers
    papers = load_papers_from_bib(batch_file)
    logger.info(f"Loaded {len(papers)} papers from batch {args.batch_id}")
    
    # Initialize Ollama client
    logger.info("Initializing Ollama client...")
    try:
        llm_client = OllamaClient(
            model=args.model,
            base_url=args.ollama_url,
            temperature=0.0,
            cache_dir=output_dir / f"cache_{args.batch_id}",
            retry_attempts=3
        )
    except Exception as e:
        logger.error(f"Failed to initialize Ollama client: {e}")
        return 1
    
    # Create AI filter
    ai_filter = AIAbstractFilter(
        llm_client=llm_client,
        confidence_threshold=args.confidence_threshold,
        log_decisions=True,
        log_dir=output_dir
    )
    
    # Apply filters
    logger.info("Applying AI filters...")
    results = ai_filter.apply_all_filters(papers, FILTERS_CONFIG)
    
    kept_papers = results['kept']
    filtered_papers = results['filtered']
    manual_review = results['manual_review']
    summary = results['summary']
    
    # Save results for this batch
    batch_output_dir = output_dir / f"batch_{args.batch_id}"
    batch_output_dir.mkdir(exist_ok=True)
    
    # Save kept papers
    save_papers_csv(kept_papers, batch_output_dir / "kept.csv")
    save_papers_bib(kept_papers, batch_output_dir / "kept.bib")
    
    # Save manual review papers
    if manual_review:
        save_papers_csv(manual_review, batch_output_dir / "manual_review.csv")
    
    # Save filtered papers by category
    filtered_dir = batch_output_dir / "filtered"
    filtered_dir.mkdir(exist_ok=True)
    for filter_name, papers_list in filtered_papers.items():
        if papers_list:
            save_papers_csv(papers_list, filtered_dir / f"{filter_name}.csv")
    
    # Save summary
    with open(batch_output_dir / "summary.json", 'w') as f:
        json.dump(summary, f, indent=2)
    
    logger.info(f"Batch {args.batch_id} processing complete")
    logger.info(f"  Papers kept: {len(kept_papers)}/{len(papers)}")
    logger.info(f"  Manual review: {len(manual_review)}")
    logger.info(f"Results saved to: {batch_output_dir}")
    
    return 0


if __name__ == "__main__":
    exit(main())
