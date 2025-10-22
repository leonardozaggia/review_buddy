"""
Compare keyword-based vs AI-based filtering strategies.

This script compares the results from both filtering approaches to help
evaluate and validate the AI filtering performance.

Usage:
    1. Run 02_abstract_filter.py first (keyword-based)
    2. Run 02_abstract_filter_AI.py second (AI-based)
    3. Run this script to compare results

Output:
    - Comparison report printed to console
    - results/filtering_comparison_*.txt - Detailed comparison report
    - results/filtering_comparison_*.csv - Paper-by-paper comparison
"""

import logging
from pathlib import Path
from datetime import datetime
from typing import List, Set, Dict
import csv

from src.utils import load_papers_from_bib
from src.models import Paper


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_paper_set(bib_file: Path) -> Set[str]:
    """
    Load papers from bib file and return set of titles.
    
    Args:
        bib_file: Path to bibliography file
    
    Returns:
        Set of paper titles (normalized)
    """
    if not bib_file.exists():
        return set()
    
    papers = load_papers_from_bib(bib_file)
    return {p.title.lower().strip() for p in papers}


def load_papers_dict(bib_file: Path) -> Dict[str, Paper]:
    """
    Load papers from bib file and return dict keyed by title.
    
    Args:
        bib_file: Path to bibliography file
    
    Returns:
        Dict mapping normalized titles to Paper objects
    """
    if not bib_file.exists():
        return {}
    
    papers = load_papers_from_bib(bib_file)
    return {p.title.lower().strip(): p for p in papers}


def compare_filtering_strategies():
    """Compare keyword-based and AI-based filtering results."""
    
    logger.info("="*80)
    logger.info("FILTERING STRATEGY COMPARISON")
    logger.info("="*80)
    
    results_dir = Path("results")
    
    # Load keyword-based results
    keyword_kept_file = results_dir / "references_filtered.bib"
    keyword_kept = load_paper_set(keyword_kept_file)
    keyword_kept_dict = load_papers_dict(keyword_kept_file)
    
    # Load AI-based results
    ai_kept_file = results_dir / "references_filtered_ai.bib"
    ai_kept = load_paper_set(ai_kept_file)
    ai_kept_dict = load_papers_dict(ai_kept_file)
    
    # Load original papers
    original_file = results_dir / "references.bib"
    original = load_paper_set(original_file)
    original_dict = load_papers_dict(original_file)
    
    # Check if files exist
    if not keyword_kept_file.exists():
        logger.error(f"Keyword filtering results not found: {keyword_kept_file}")
        logger.error("Please run 02_abstract_filter.py first")
        return
    
    if not ai_kept_file.exists():
        logger.error(f"AI filtering results not found: {ai_kept_file}")
        logger.error("Please run 02_abstract_filter_AI.py first")
        return
    
    if not original_file.exists():
        logger.error(f"Original papers not found: {original_file}")
        logger.error("Please run 01_fetch_metadata.py first")
        return
    
    # Calculate metrics
    logger.info(f"\nDataset sizes:")
    logger.info(f"  Original papers:           {len(original)}")
    logger.info(f"  Keyword filtering kept:    {len(keyword_kept)}")
    logger.info(f"  AI filtering kept:         {len(ai_kept)}")
    
    # Calculate overlap and differences
    both_kept = keyword_kept & ai_kept
    only_keyword = keyword_kept - ai_kept
    only_ai = ai_kept - keyword_kept
    both_filtered = original - (keyword_kept | ai_kept)
    
    logger.info(f"\nOverlap analysis:")
    logger.info(f"  Kept by BOTH methods:      {len(both_kept)}")
    logger.info(f"  Kept by KEYWORD only:      {len(only_keyword)}")
    logger.info(f"  Kept by AI only:           {len(only_ai)}")
    logger.info(f"  Filtered by BOTH methods:  {len(both_filtered)}")
    
    # Calculate agreement metrics
    total_papers = len(original)
    agreement = (len(both_kept) + len(both_filtered)) / total_papers * 100
    
    logger.info(f"\nAgreement metrics:")
    logger.info(f"  Overall agreement:         {agreement:.1f}%")
    logger.info(f"  Disagreement rate:         {100-agreement:.1f}%")
    
    # Filtering rates
    keyword_filter_rate = (1 - len(keyword_kept)/total_papers) * 100
    ai_filter_rate = (1 - len(ai_kept)/total_papers) * 100
    
    logger.info(f"\nFiltering rates:")
    logger.info(f"  Keyword filtering rate:    {keyword_filter_rate:.1f}%")
    logger.info(f"  AI filtering rate:         {ai_filter_rate:.1f}%")
    logger.info(f"  Difference:                {abs(keyword_filter_rate - ai_filter_rate):.1f}%")
    
    # Check for manual review papers
    manual_review_file = results_dir / "manual_review_ai.csv"
    if manual_review_file.exists():
        with open(manual_review_file, 'r', encoding='utf-8') as f:
            manual_review_count = sum(1 for line in f) - 1  # Subtract header
        logger.info(f"\nAI manual review:")
        logger.info(f"  Papers flagged for review: {manual_review_count}")
    
    # Generate detailed report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = results_dir / f"filtering_comparison_{timestamp}.txt"
    comparison_csv = results_dir / f"filtering_comparison_{timestamp}.csv"
    
    logger.info(f"\nGenerating detailed reports...")
    
    # Write text report
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("FILTERING STRATEGY COMPARISON REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("DATASET SIZES\n")
        f.write("-" * 80 + "\n")
        f.write(f"Original papers:           {len(original)}\n")
        f.write(f"Keyword filtering kept:    {len(keyword_kept)}\n")
        f.write(f"AI filtering kept:         {len(ai_kept)}\n\n")
        
        f.write("OVERLAP ANALYSIS\n")
        f.write("-" * 80 + "\n")
        f.write(f"Kept by BOTH methods:      {len(both_kept)}\n")
        f.write(f"Kept by KEYWORD only:      {len(only_keyword)}\n")
        f.write(f"Kept by AI only:           {len(only_ai)}\n")
        f.write(f"Filtered by BOTH methods:  {len(both_filtered)}\n\n")
        
        f.write("AGREEMENT METRICS\n")
        f.write("-" * 80 + "\n")
        f.write(f"Overall agreement:         {agreement:.1f}%\n")
        f.write(f"Disagreement rate:         {100-agreement:.1f}%\n\n")
        
        f.write("FILTERING RATES\n")
        f.write("-" * 80 + "\n")
        f.write(f"Keyword filtering rate:    {keyword_filter_rate:.1f}%\n")
        f.write(f"AI filtering rate:         {ai_filter_rate:.1f}%\n")
        f.write(f"Difference:                {abs(keyword_filter_rate - ai_filter_rate):.1f}%\n\n")
        
        # List papers kept by keyword only
        if only_keyword:
            f.write("\nPAPERS KEPT BY KEYWORD ONLY (potential false negatives for AI)\n")
            f.write("-" * 80 + "\n")
            for i, title in enumerate(sorted(only_keyword), 1):
                paper = keyword_kept_dict.get(title)
                f.write(f"\n{i}. {title.title()}\n")
                if paper and paper.doi:
                    f.write(f"   DOI: {paper.doi}\n")
        
        # List papers kept by AI only
        if only_ai:
            f.write("\n\nPAPERS KEPT BY AI ONLY (potential false negatives for keyword)\n")
            f.write("-" * 80 + "\n")
            for i, title in enumerate(sorted(only_ai), 1):
                paper = ai_kept_dict.get(title)
                f.write(f"\n{i}. {title.title()}\n")
                if paper and paper.doi:
                    f.write(f"   DOI: {paper.doi}\n")
    
    logger.info(f"Text report saved to: {report_file}")
    
    # Write CSV comparison
    with open(comparison_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'Title', 'DOI', 'Keyword_Kept', 'AI_Kept', 'Agreement', 'Category'
        ])
        
        for title in sorted(original):
            paper = original_dict.get(title)
            keyword_decision = title in keyword_kept
            ai_decision = title in ai_kept
            agreement_status = keyword_decision == ai_decision
            
            if agreement_status:
                if keyword_decision:
                    category = 'Both_Kept'
                else:
                    category = 'Both_Filtered'
            else:
                if keyword_decision:
                    category = 'Keyword_Only'
                else:
                    category = 'AI_Only'
            
            writer.writerow([
                title.title() if paper else title,
                paper.doi if paper and paper.doi else '',
                'Yes' if keyword_decision else 'No',
                'Yes' if ai_decision else 'No',
                'Yes' if agreement_status else 'No',
                category
            ])
    
    logger.info(f"CSV comparison saved to: {comparison_csv}")
    
    # Summary recommendations
    logger.info("\n" + "="*80)
    logger.info("RECOMMENDATIONS")
    logger.info("="*80)
    
    if agreement > 90:
        logger.info("✓ High agreement (>90%) - Both methods are consistent")
    elif agreement > 75:
        logger.info("⚠ Moderate agreement (75-90%) - Review disagreements carefully")
    else:
        logger.info("✗ Low agreement (<75%) - Significant differences, manual review needed")
    
    if only_keyword:
        logger.info(f"\n⚠ {len(only_keyword)} papers kept by keyword but filtered by AI")
        logger.info("  → These might be false positives in keyword filtering")
        logger.info("  → Or false negatives in AI filtering - review AI decisions")
    
    if only_ai:
        logger.info(f"\n⚠ {len(only_ai)} papers kept by AI but filtered by keyword")
        logger.info("  → These might be false negatives in keyword filtering")
        logger.info("  → Or false positives in AI filtering - review AI reasoning")
    
    logger.info("\nNext steps:")
    logger.info("  1. Review papers in 'Keyword_Only' and 'AI_Only' categories")
    logger.info("  2. Check AI filtering log for reasoning on disagreements")
    logger.info("  3. Decide which filtering approach to use for final dataset")
    logger.info("  4. Consider combining both approaches (intersection for high precision)")


if __name__ == "__main__":
    compare_filtering_strategies()
