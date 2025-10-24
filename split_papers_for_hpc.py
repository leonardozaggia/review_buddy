"""
Split papers into batches for parallel processing on HPC.

This script divides the papers from references.bib into smaller batches
that can be processed in parallel using SLURM array jobs.

Usage:
    python split_papers_for_hpc.py --num-batches 10

Output:
    results/batches/batch_0.bib
    results/batches/batch_1.bib
    ...
    results/batches/batch_N.bib
"""

import argparse
import logging
from pathlib import Path
from src.utils import load_papers_from_bib, save_papers_bib


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def split_papers(papers, num_batches):
    """
    Split papers into roughly equal batches.
    
    Args:
        papers: List of Paper objects
        num_batches: Number of batches to create
    
    Returns:
        List of paper batches
    """
    batch_size = len(papers) // num_batches
    if len(papers) % num_batches != 0:
        batch_size += 1
    
    batches = []
    for i in range(num_batches):
        start_idx = i * batch_size
        end_idx = min((i + 1) * batch_size, len(papers))
        batch = papers[start_idx:end_idx]
        if batch:  # Only add non-empty batches
            batches.append(batch)
    
    return batches


def main():
    parser = argparse.ArgumentParser(
        description="Split papers into batches for parallel HPC processing"
    )
    parser.add_argument(
        '--num-batches',
        type=int,
        default=10,
        help='Number of batches to create (default: 10)'
    )
    parser.add_argument(
        '--input',
        type=str,
        default='results/references.bib',
        help='Input bibliography file (default: results/references.bib)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='results/batches',
        help='Output directory for batches (default: results/batches)'
    )
    
    args = parser.parse_args()
    
    # Setup paths
    input_file = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load papers
    logger.info(f"Loading papers from {input_file}...")
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        logger.error("Please run 01_fetch_metadata.py first")
        return 1
    
    papers = load_papers_from_bib(input_file)
    logger.info(f"Loaded {len(papers)} papers")
    
    # Split into batches
    logger.info(f"Splitting into {args.num_batches} batches...")
    batches = split_papers(papers, args.num_batches)
    
    # Save batches
    logger.info(f"Saving batches to {output_dir}...")
    for i, batch in enumerate(batches):
        batch_file = output_dir / f"batch_{i}.bib"
        save_papers_bib(batch, batch_file)
        logger.info(f"  Batch {i}: {len(batch)} papers -> {batch_file}")
    
    logger.info(f"\nSuccessfully created {len(batches)} batches")
    logger.info(f"Average batch size: {len(papers) / len(batches):.1f} papers")
    
    logger.info("\nNext steps:")
    logger.info(f"  1. Update run_filter_hpc_array.sh: --array=0-{len(batches)-1}")
    logger.info(f"  2. Submit job: sbatch run_filter_hpc_array.sh")
    logger.info(f"  3. After completion: python merge_batches.py")
    
    return 0


if __name__ == "__main__":
    exit(main())
