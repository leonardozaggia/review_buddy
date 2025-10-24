"""
Merge results from parallel batch processing.

After all array job tasks complete, run this script to merge the results
from all batches into final filtered outputs.

Usage:
    python merge_batches.py
"""

import logging
from pathlib import Path
import json
from collections import defaultdict

from src.utils import load_papers_from_bib, save_papers_csv, save_papers_bib


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def merge_batches():
    """Merge all batch results into final outputs."""
    
    batch_results_dir = Path("results/batch_results")
    output_dir = Path("results")
    
    if not batch_results_dir.exists():
        logger.error(f"Batch results directory not found: {batch_results_dir}")
        logger.error("Make sure batch processing completed successfully")
        return 1
    
    # Find all batch directories
    batch_dirs = sorted([
        d for d in batch_results_dir.iterdir() 
        if d.is_dir() and d.name.startswith('batch_')
    ])
    
    if not batch_dirs:
        logger.error("No batch results found")
        return 1
    
    logger.info(f"Found {len(batch_dirs)} batch results to merge")
    
    # Collect papers from all batches
    all_kept_papers = []
    all_manual_review = []
    all_filtered = defaultdict(list)
    
    # Aggregate summaries
    total_initial = 0
    total_filtered_by_category = defaultdict(int)
    total_api_calls = 0
    total_cache_hits = 0
    total_failed_calls = 0
    
    for batch_dir in batch_dirs:
        batch_id = batch_dir.name.split('_')[1]
        logger.info(f"Processing batch {batch_id}...")
        
        # Load kept papers
        kept_file = batch_dir / "kept.bib"
        if kept_file.exists():
            kept = load_papers_from_bib(kept_file)
            all_kept_papers.extend(kept)
            logger.info(f"  Batch {batch_id}: {len(kept)} kept papers")
        
        # Load manual review papers
        manual_file = batch_dir / "manual_review.csv"
        if manual_file.exists():
            # Load from CSV (simpler for this purpose)
            import csv
            with open(manual_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Store just the title and DOI for tracking
                    all_manual_review.append({'title': row.get('title', ''), 'doi': row.get('doi', '')})
        
        # Load filtered papers
        filtered_dir = batch_dir / "filtered"
        if filtered_dir.exists():
            for filter_file in filtered_dir.glob("*.csv"):
                filter_name = filter_file.stem
                import csv
                with open(filter_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        all_filtered[filter_name].append({'title': row.get('title', ''), 'doi': row.get('doi', '')})
        
        # Load summary
        summary_file = batch_dir / "summary.json"
        if summary_file.exists():
            with open(summary_file, 'r') as f:
                summary = json.load(f)
                total_initial += summary.get('initial_count', 0)
                
                for cat, count in summary.get('filtered_by_category', {}).items():
                    total_filtered_by_category[cat] += count
                
                api_stats = summary.get('api_stats', {})
                total_api_calls += api_stats.get('api_calls', 0)
                total_cache_hits += api_stats.get('cache_hits', 0)
                total_failed_calls += api_stats.get('failed_calls', 0)
    
    # Remove duplicates (based on title+doi)
    def deduplicate_papers(papers):
        seen = set()
        unique = []
        for p in papers:
            key = (p.title if hasattr(p, 'title') else p.get('title', ''), 
                   p.doi if hasattr(p, 'doi') else p.get('doi', ''))
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique
    
    all_kept_papers = deduplicate_papers(all_kept_papers)
    
    logger.info("\n" + "="*70)
    logger.info("MERGED RESULTS SUMMARY")
    logger.info("="*70)
    logger.info(f"Total papers processed:  {total_initial}")
    logger.info(f"Papers kept:             {len(all_kept_papers)}")
    logger.info(f"Papers for manual review: {len(all_manual_review)}")
    logger.info(f"Retention rate:          {len(all_kept_papers)/total_initial*100:.1f}%")
    
    logger.info("\nFiltered by category:")
    for cat, count in sorted(total_filtered_by_category.items()):
        logger.info(f"  {cat:20s}: {count:4d} papers")
    
    logger.info("\nTotal Ollama usage:")
    logger.info(f"  Model calls:  {total_api_calls}")
    logger.info(f"  Cache hits:   {total_cache_hits}")
    logger.info(f"  Failed calls: {total_failed_calls}")
    total_requests = total_api_calls + total_cache_hits
    if total_requests > 0:
        logger.info(f"  Cache rate:   {total_cache_hits/total_requests*100:.1f}%")
    
    # Save merged results
    logger.info("\n" + "="*70)
    logger.info("SAVING MERGED RESULTS")
    logger.info("="*70)
    
    save_papers_csv(all_kept_papers, output_dir / "papers_filtered_ai.csv")
    save_papers_bib(all_kept_papers, output_dir / "references_filtered_ai.bib")
    logger.info(f"Saved {len(all_kept_papers)} kept papers")
    
    if all_manual_review:
        # Save manual review list (just titles and DOIs)
        with open(output_dir / "manual_review_ai.csv", 'w', encoding='utf-8', newline='') as f:
            import csv
            writer = csv.DictWriter(f, fieldnames=['title', 'doi'])
            writer.writeheader()
            for paper in all_manual_review:
                writer.writerow(paper)
        logger.info(f"Saved {len(all_manual_review)} papers for manual review")
    
    # Save aggregated summary
    merged_summary = {
        'total_initial': total_initial,
        'total_kept': len(all_kept_papers),
        'total_manual_review': len(all_manual_review),
        'filtered_by_category': dict(total_filtered_by_category),
        'api_stats': {
            'total_calls': total_api_calls,
            'cache_hits': total_cache_hits,
            'failed_calls': total_failed_calls,
            'cache_hit_rate': f"{total_cache_hits/total_requests*100:.1f}%" if total_requests > 0 else "0%"
        }
    }
    
    with open(output_dir / "merged_summary.json", 'w') as f:
        json.dump(merged_summary, f, indent=2)
    
    logger.info("\n" + "="*70)
    logger.info("MERGE COMPLETE!")
    logger.info("="*70)
    logger.info(f"Final results saved to:")
    logger.info(f"  - {output_dir / 'papers_filtered_ai.csv'}")
    logger.info(f"  - {output_dir / 'references_filtered_ai.bib'}")
    logger.info(f"  - {output_dir / 'merged_summary.json'}")
    
    return 0


if __name__ == "__main__":
    exit(merge_batches())
