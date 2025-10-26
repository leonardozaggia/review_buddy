"""
Postprocessing utilities.
"""

import logging
from typing import List, Dict, Any
from pathlib import Path

from src.models import Paper
from .io import save_papers


logger = logging.getLogger(__name__)


def postprocess_results(
    results: Dict[str, Any], 
    output_dir: str,
    save_filtered: bool = True
) -> Dict[str, str]:
    """
    Postprocess filtering results: save outputs, generate reports.
    
    Args:
        results: Filter results dictionary
        output_dir: Directory to save outputs
        save_filtered: Whether to save filtered-out papers
    
    Returns:
        Dictionary mapping output type to file paths
    """
    logger.info("Postprocessing filter results")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    kept_papers = results['kept']
    filtered_papers = results.get('filtered', {})
    manual_review = results.get('manual_review', [])
    
    output_files = {}
    
    # Save kept papers
    kept_csv = output_path / "papers_filtered.csv"
    kept_bib = output_path / "papers_filtered.bib"
    save_papers(kept_papers, str(kept_csv), format="csv")
    save_papers(kept_papers, str(kept_bib), format="bibtex")
    output_files['kept_csv'] = str(kept_csv)
    output_files['kept_bib'] = str(kept_bib)
    logger.info(f"Saved {len(kept_papers)} kept papers")
    
    # Save manual review papers if any
    if manual_review:
        review_csv = output_path / "manual_review.csv"
        save_papers(manual_review, str(review_csv), format="csv")
        output_files['manual_review'] = str(review_csv)
        logger.info(f"Saved {len(manual_review)} papers for manual review")
    
    # Save filtered-out papers by category
    if save_filtered and filtered_papers:
        filtered_dir = output_path / "filtered_out"
        filtered_dir.mkdir(exist_ok=True)
        
        for filter_name, papers_list in filtered_papers.items():
            if papers_list:
                csv_file = filtered_dir / f"{filter_name}.csv"
                save_papers(papers_list, str(csv_file), format="csv")
                logger.info(f"Saved {len(papers_list)} {filter_name} papers")
    
    return output_files


def generate_summary_report(results: Dict[str, Any], output_path: str) -> None:
    """
    Generate a text summary report of filtering results.
    
    Args:
        results: Filter results dictionary
        output_path: Path to save report
    """
    summary = results.get('summary', {})
    
    lines = [
        "=" * 70,
        "FILTERING SUMMARY REPORT",
        "=" * 70,
        "",
        f"Initial papers:        {summary.get('initial_count', 0)}",
        f"Papers kept:           {summary.get('final_count', 0)}",
        f"Papers filtered out:   {summary.get('total_filtered', 0)}",
    ]
    
    if 'manual_review_count' in summary:
        lines.append(f"Manual review needed:  {summary['manual_review_count']}")
    
    retention_rate = (
        summary['final_count'] / summary['initial_count'] * 100 
        if summary.get('initial_count', 0) > 0 else 0
    )
    lines.append(f"Retention rate:        {retention_rate:.1f}%")
    
    lines.append("")
    lines.append("Breakdown by filter:")
    
    for filter_name, count in summary.get('filtered_by_category', {}).items():
        lines.append(f"  - {filter_name:20s}: {count:4d} papers")
    
    if 'api_stats' in summary:
        api_stats = summary['api_stats']
        lines.extend([
            "",
            "AI Model Usage:",
            f"  - Model calls:         {api_stats['api_calls']}",
            f"  - Cache hits:          {api_stats['cache_hits']}",
            f"  - Failed calls:        {api_stats['failed_calls']}",
            f"  - Cache hit rate:      {api_stats['cache_hit_rate']}",
            f"  - Model:               {api_stats['model']}",
        ])
    
    lines.append("")
    lines.append("=" * 70)
    
    report_text = "\n".join(lines)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    
    logger.info(f"Summary report saved to: {output_path}")
