#!/usr/bin/env python3
"""
Demo script showing Review Buddy usage.

This script demonstrates the end-to-end pipeline:
1. Load sample data
2. Filter using normal engine
3. View results

Usage:
    python demo.py
"""

import sys
from pathlib import Path

# Add current dir to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config_loader import PipelineConfig
from core.io import load_papers, save_papers, get_papers_dataframe
from core.engines import get_filter_engine
from core.postprocess import postprocess_results, generate_summary_report


def main():
    """Run demo"""
    print("=" * 70)
    print("REVIEW BUDDY DEMO")
    print("=" * 70)
    print()
    
    # Step 1: Load sample data
    print("Step 1: Loading sample data...")
    data_file = Path("data/sample_papers.csv")
    
    if not data_file.exists():
        print(f"ERROR: Sample data not found: {data_file}")
        print("Please ensure data/sample_papers.csv exists.")
        return 1
    
    papers = load_papers(str(data_file))
    print(f"✓ Loaded {len(papers)} papers")
    print()
    
    # Show papers
    print("Sample papers:")
    for i, paper in enumerate(papers, 1):
        print(f"  {i}. {paper.title}")
    print()
    
    # Step 2: Configure filter
    print("Step 2: Configuring normal filter...")
    config = PipelineConfig()
    config.engine = "normal"
    config.normal.enabled_filters = ["non_empirical", "non_human"]
    config.normal.keywords = {
        'non_empirical': ['systematic review', 'review', 'meta-analysis'],
        'non_human': ['rat', 'mouse', 'mice', 'rodent', 'in vitro']
    }
    
    print(f"Engine: {config.engine}")
    print(f"Filters: {', '.join(config.normal.enabled_filters)}")
    print()
    
    # Step 3: Apply filters
    print("Step 3: Applying filters...")
    engine = get_filter_engine(config.engine, config.normal)
    results = engine.filter_records(papers)
    
    summary = results['summary']
    print(f"✓ Filtering complete")
    print(f"  Initial: {summary['initial_count']}")
    print(f"  Kept:    {summary['final_count']}")
    print(f"  Filtered: {summary['total_filtered']}")
    print()
    
    # Show breakdown
    print("Breakdown by filter:")
    for filter_name, count in summary['filtered_by_category'].items():
        if count > 0:
            print(f"  - {filter_name}: {count} papers")
    print()
    
    # Show kept papers
    print("Kept papers:")
    for i, paper in enumerate(results['kept'], 1):
        print(f"  {i}. {paper.title}")
    print()
    
    # Step 4: Save results
    print("Step 4: Saving results...")
    output_dir = Path("demo_output")
    output_dir.mkdir(exist_ok=True)
    
    output_files = postprocess_results(results, str(output_dir), save_filtered=True)
    
    print("✓ Results saved:")
    for key, path in output_files.items():
        print(f"  - {path}")
    
    # Save summary
    report_path = output_dir / "summary.txt"
    generate_summary_report(results, str(report_path))
    print(f"  - {report_path}")
    print()
    
    print("=" * 70)
    print("DEMO COMPLETE!")
    print("=" * 70)
    print()
    print("Next steps:")
    print("  1. View results in demo_output/")
    print("  2. Try: python cli.py filter --help")
    print("  3. Try: streamlit run app.py")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
