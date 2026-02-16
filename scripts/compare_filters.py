#!/usr/bin/env python3
"""
Compare AI-based filtering vs keyword-based filtering results
"""

import pandas as pd
import sys
from pathlib import Path

# Add repo root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.utils import save_filter_comparison

def load_csv_safe(filepath):
    """Load CSV file, handling potential errors"""
    try:
        return pd.read_csv(filepath)
    except Exception as e:
        print(f"Warning: Could not load {filepath}: {e}")
        return pd.DataFrame()

def main():
    # Define paths
    results_dir = Path("results")
    
    # Load main datasets
    papers_all = pd.read_csv(results_dir / "papers.csv")
    papers_filtered_keyword = pd.read_csv(results_dir / "papers_filtered.csv")
    papers_filtered_ai = pd.read_csv(results_dir / "papers_filtered_ai.csv")
    
    print("=" * 80)
    print("FILTERING COMPARISON: AI vs Keyword-based")
    print("=" * 80)
    
    # Basic statistics
    print("\n📊 BASIC STATISTICS")
    print("-" * 80)
    print(f"Total papers retrieved:        {len(papers_all):4d}")
    print(f"Papers after keyword filter:   {len(papers_filtered_keyword):4d} ({len(papers_filtered_keyword)/len(papers_all)*100:.1f}%)")
    print(f"Papers after AI filter:        {len(papers_filtered_ai):4d} ({len(papers_filtered_ai)/len(papers_all)*100:.1f}%)")
    
    # Identify papers by URL or DOI (more reliable than title)
    keyword_papers = set(papers_filtered_keyword['URL'].values)
    ai_papers = set(papers_filtered_ai['URL'].values)
    
    # Load filtered out papers first to check for data quality issues
    filtered_out_keyword = {
        'bci': load_csv_safe(results_dir / "filtered_out" / "bci.csv"),
        'no_abstract': load_csv_safe(results_dir / "filtered_out" / "no_abstract.csv"),
        'non_human': load_csv_safe(results_dir / "filtered_out" / "non_human.csv"),
    }
    
    filtered_out_ai = {
        'bci': load_csv_safe(results_dir / "filtered_out_ai" / "bci.csv"),
        'no_abstract': load_csv_safe(results_dir / "filtered_out_ai" / "no_abstract.csv"),
        'non_empirical': load_csv_safe(results_dir / "filtered_out_ai" / "non_empirical.csv"),
        'non_human': load_csv_safe(results_dir / "filtered_out_ai" / "non_human.csv"),
    }
    
    # Check for data quality issues - papers in both kept and filtered
    all_filtered_out_ai = pd.concat(filtered_out_ai.values(), ignore_index=True)
    filtered_out_urls = set(all_filtered_out_ai['URL'].values)
    
    duplicates_in_kept_and_filtered = []
    overlap_kept_filtered = ai_papers & filtered_out_urls
    if overlap_kept_filtered:
        print("\n⚠️  DATA QUALITY ISSUE DETECTED!")
        print("-" * 80)
        print(f"Found {len(overlap_kept_filtered)} paper(s) appearing in BOTH kept and filtered lists:")
        for url in overlap_kept_filtered:
            paper_kept = papers_filtered_ai[papers_filtered_ai['URL'] == url].iloc[0]
            paper_filtered = all_filtered_out_ai[all_filtered_out_ai['URL'] == url].iloc[0]
            
            # Find which category
            category = None
            for cat_name, cat_df in filtered_out_ai.items():
                if url in cat_df['URL'].values:
                    category = cat_name
                    break
            
            print(f"\n  • {paper_kept['Title'][:70]}...")
            print(f"    URL: {url}")
            print(f"    Exclusion category: {category}")
            
            duplicates_in_kept_and_filtered.append({
                'title': paper_kept['Title'],
                'authors': paper_kept['Authors'],
                'url': url,
                'category': category
            })
        print()
    
    # Calculate overlaps (for papers that were kept)
    
    # Calculate overlaps
    both_included = keyword_papers & ai_papers
    only_keyword = keyword_papers - ai_papers
    only_ai = ai_papers - keyword_papers
    
    print("\n🔄 OVERLAP ANALYSIS")
    print("-" * 80)
    print(f"Papers included by BOTH:       {len(both_included):4d}")
    print(f"Papers ONLY by keyword:        {len(only_keyword):4d}")
    print(f"Papers ONLY by AI:             {len(only_ai):4d}")
    
    # Agreement rate
    total_decisions = len(keyword_papers | ai_papers)
    agreement_rate = len(both_included) / total_decisions * 100 if total_decisions > 0 else 0
    print(f"\n✓ Agreement rate:              {agreement_rate:.1f}%")
    
    # Show some examples of disagreement
    print("\n" + "=" * 80)
    print("PAPERS ONLY INCLUDED BY KEYWORD FILTER (first 5)")
    print("=" * 80)
    only_keyword_examples = []
    if only_keyword:
        only_keyword_df = papers_filtered_keyword[papers_filtered_keyword['URL'].isin(only_keyword)].head(5)
        for idx, row in only_keyword_df.iterrows():
            print(f"\n• {row['Title'][:70]}...")
            print(f"  Authors: {row['Authors']}")
            print(f"  URL: {row['URL']}")
            only_keyword_examples.append({
                'title': row['Title'],
                'authors': row['Authors'],
                'url': row['URL']
            })
    
    print("\n" + "=" * 80)
    print("PAPERS ONLY INCLUDED BY AI FILTER (first 5)")
    print("=" * 80)
    only_ai_examples = []
    if only_ai:
        only_ai_df = papers_filtered_ai[papers_filtered_ai['URL'].isin(only_ai)].head(5)
        for idx, row in only_ai_df.iterrows():
            print(f"\n• {row['Title'][:70]}...")
            print(f"  Authors: {row['Authors']}")
            print(f"  URL: {row['URL']}")
            only_ai_examples.append({
                'title': row['Title'],
                'authors': row['Authors'],
                'url': row['URL']
            })
    
    # Analyze filtered out papers
    print("\n" + "=" * 80)
    print("EXCLUSION CATEGORIES ANALYSIS")
    print("=" * 80)
    
    print("\n📋 KEYWORD FILTER EXCLUSIONS:")
    print("-" * 80)
    for category, df in filtered_out_keyword.items():
        print(f"  {category.replace('_', ' ').title():<20} {len(df):4d} papers")
    
    total_keyword_excluded = sum(len(df) for df in filtered_out_keyword.values())
    print(f"  {'Total Excluded':<20} {total_keyword_excluded:4d} papers")
    
    print("\n📋 AI FILTER EXCLUSIONS:")
    print("-" * 80)
    for category, df in filtered_out_ai.items():
        print(f"  {category.replace('_', ' ').title():<20} {len(df):4d} papers")
    
    total_ai_excluded = sum(len(df) for df in filtered_out_ai.values())
    print(f"  {'Total Excluded':<20} {total_ai_excluded:4d} papers")
    
    # Category-by-category comparison
    print("\n" + "=" * 80)
    print("CATEGORY-BY-CATEGORY COMPARISON")
    print("=" * 80)
    
    category_comparison = {}
    for category in ['bci', 'no_abstract', 'non_human']:
        keyword_cat = set(filtered_out_keyword[category]['URL'].values) if not filtered_out_keyword[category].empty else set()
        ai_cat = set(filtered_out_ai[category]['URL'].values) if not filtered_out_ai[category].empty else set()
        
        both_excluded = keyword_cat & ai_cat
        only_keyword_excluded = keyword_cat - ai_cat
        only_ai_excluded = ai_cat - keyword_cat
        
        print(f"\n{category.replace('_', ' ').upper()}:")
        print(f"  Keyword filter: {len(keyword_cat):4d} papers")
        print(f"  AI filter:      {len(ai_cat):4d} papers")
        print(f"  Both excluded:  {len(both_excluded):4d} papers")
        print(f"  Only keyword:   {len(only_keyword_excluded):4d} papers")
        print(f"  Only AI:        {len(only_ai_excluded):4d} papers")
        
        category_comparison[category] = {
            'keyword': len(keyword_cat),
            'ai': len(ai_cat),
            'both': len(both_excluded),
            'only_keyword': len(only_keyword_excluded),
            'only_ai': len(only_ai_excluded)
        }
    
    # Non-empirical is only in AI
    if not filtered_out_ai['non_empirical'].empty:
        print(f"\nNON-EMPIRICAL (AI only):")
        print(f"  AI filter: {len(filtered_out_ai['non_empirical']):4d} papers")
        
        category_comparison['non_empirical'] = {
            'keyword': 0,
            'ai': len(filtered_out_ai['non_empirical']),
            'both': 0,
            'only_keyword': 0,
            'only_ai': len(filtered_out_ai['non_empirical'])
        }
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"""
The keyword-based filter is {'more' if len(papers_filtered_keyword) > len(papers_filtered_ai) else 'less'} permissive than the AI filter.
- Keyword filter kept {len(papers_filtered_keyword)} papers ({len(papers_filtered_keyword)/len(papers_all)*100:.1f}%)
- AI filter kept {len(papers_filtered_ai)} papers ({len(papers_filtered_ai)/len(papers_all)*100:.1f}%)
- Agreement on {len(both_included)} papers ({agreement_rate:.1f}% of decisions)

The AI filter has an additional category: non-empirical ({len(filtered_out_ai['non_empirical'])} papers)
""")
    
    # Prepare data for saving
    keyword_exclusions = {cat: len(df) for cat, df in filtered_out_keyword.items()}
    ai_exclusions = {cat: len(df) for cat, df in filtered_out_ai.items()}
    
    comparison_data = {
        'total_papers': len(papers_all),
        'keyword_kept': len(papers_filtered_keyword),
        'ai_kept': len(papers_filtered_ai),
        'both_included': len(both_included),
        'only_keyword': len(only_keyword),
        'only_ai': len(only_ai),
        'agreement_rate': agreement_rate,
        'keyword_exclusions': keyword_exclusions,
        'ai_exclusions': ai_exclusions,
        'keyword_excluded_total': total_keyword_excluded,
        'ai_excluded_total': total_ai_excluded,
        'category_comparison': category_comparison,
        'only_keyword_examples': only_keyword_examples,
        'only_ai_examples': only_ai_examples,
        'duplicates_in_kept_and_filtered': duplicates_in_kept_and_filtered
    }
    
    # Save comparison results
    comparison_file = results_dir / "filter_comparison.txt"
    save_filter_comparison(comparison_data, comparison_file)
    print(f"\n💾 Saved detailed comparison to {comparison_file}")


if __name__ == "__main__":
    main()
