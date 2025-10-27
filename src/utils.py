"""
Utility functions for loading and saving papers.
"""

import logging
import csv
from pathlib import Path
from datetime import date, datetime
from typing import List, Dict, Set, Any

from .models import Paper


logger = logging.getLogger(__name__)


def load_papers_from_bib(bib_file: Path) -> List[Paper]:
    """
    Load papers from BibTeX file.
    
    Args:
        bib_file: Path to BibTeX file
    
    Returns:
        List of Paper objects
    """
    papers = []
    
    try:
        with open(bib_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split into entries
        entries = content.split('@')[1:]  # Skip before first @
        
        for entry in entries:
            try:
                # Extract fields
                lines = entry.strip().split('\n')
                
                # Parse entry
                title = None
                authors = []
                abstract = None
                doi = None
                pmid = None
                arxiv_id = None
                year = None
                journal = None
                url = None
                
                for line in lines:
                    line = line.strip().rstrip(',')
                    
                    if '=' in line:
                        field, value = line.split('=', 1)
                        field = field.strip().lower()
                        value = value.strip().strip('{}').strip()
                        
                        if field == 'title':
                            title = value
                        elif field == 'author':
                            authors = [a.strip() for a in value.split(' and ')]
                        elif field == 'abstract':
                            abstract = value
                        elif field == 'doi':
                            doi = value
                        elif field == 'pmid':
                            pmid = value
                        elif field == 'arxiv_id':
                            arxiv_id = value
                        elif field == 'year':
                            try:
                                year = int(value)
                            except:
                                pass
                        elif field == 'journal':
                            journal = value
                        elif field == 'url':
                            url = value
                
                if title:
                    paper = Paper(title=title)
                    paper.authors = authors
                    paper.abstract = abstract
                    paper.doi = doi
                    paper.pmid = pmid
                    paper.arxiv_id = arxiv_id
                    paper.journal = journal
                    paper.url = url
                    
                    if year:
                        paper.publication_date = date(year, 1, 1)
                    
                    papers.append(paper)
                    
            except Exception as e:
                logger.debug(f"Failed to parse entry: {e}")
                continue
        
        logger.info(f"Loaded {len(papers)} papers from {bib_file}")
        return papers
        
    except Exception as e:
        logger.error(f"Failed to load papers from {bib_file}: {e}")
        return []


def save_papers_csv(papers: List[Paper], output_file: Path):
    """
    Save papers to CSV file.
    
    Args:
        papers: List of Paper objects
        output_file: Path to output CSV file
    """
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Title', 'Authors', 'Journal', 'Year', 'DOI', 
                'PMID', 'URL', 'Has_Abstract'
            ])
            
            for paper in papers:
                authors_str = '; '.join(paper.authors) if paper.authors else ''
                year = paper.publication_date.year if paper.publication_date else ''
                has_abstract = 'Yes' if paper.abstract else 'No'
                
                writer.writerow([
                    paper.title,
                    authors_str,
                    paper.journal or '',
                    year,
                    paper.doi or '',
                    paper.pmid or '',
                    paper.url or '',
                    has_abstract
                ])
        
        logger.info(f"Saved {len(papers)} papers to {output_file}")
        
    except Exception as e:
        logger.error(f"Failed to save CSV: {e}")


def save_papers_bib(papers: List[Paper], output_file: Path):
    """
    Save papers to BibTeX file.
    
    Args:
        papers: List of Paper objects
        output_file: Path to output BibTeX file
    """
    try:
        entries = []
        for i, paper in enumerate(papers, 1):
            entry = paper.to_bibtex_entry(f"paper_{i}")
            entries.append(entry)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n\n'.join(entries))
        
        logger.info(f"Saved {len(papers)} papers to {output_file}")
        
    except Exception as e:
        logger.error(f"Failed to save BibTeX: {e}")


def save_failed_downloads(papers: List[Paper], output_dir: Path):
    """
    Save papers that failed to download to CSV and BibTeX files.
    
    Args:
        papers: List of Paper objects that failed to download
        output_dir: Directory to save the failed downloads files
    """
    if not papers:
        logger.info("No failed downloads to save")
        return
    
    try:
        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save CSV
        csv_file = output_dir / "failed_downloads.csv"
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Title', 'Authors', 'Journal', 'Year', 'DOI', 
                'PMID', 'arXiv_ID', 'URL', 'Has_Abstract'
            ])
            
            for paper in papers:
                authors_str = '; '.join(paper.authors) if paper.authors else ''
                year = paper.publication_date.year if paper.publication_date else ''
                has_abstract = 'Yes' if paper.abstract else 'No'
                
                writer.writerow([
                    paper.title,
                    authors_str,
                    paper.journal or '',
                    year,
                    paper.doi or '',
                    paper.pmid or '',
                    paper.arxiv_id or '',
                    paper.url or '',
                    has_abstract
                ])
        
        logger.info(f"Saved {len(papers)} failed downloads to {csv_file}")
        
        # Save BibTeX
        bib_file = output_dir / "failed_downloads.bib"
        entries = []
        for i, paper in enumerate(papers, 1):
            entry = paper.to_bibtex_entry(f"failed_{i}")
            entries.append(entry)
        
        with open(bib_file, 'w', encoding='utf-8') as f:
            f.write('\n\n'.join(entries))
        
        logger.info(f"Saved {len(papers)} failed downloads to {bib_file}")
        
    except Exception as e:
        logger.error(f"Failed to save failed downloads: {e}")


def save_filter_comparison(comparison_data: Dict[str, Any], output_file: Path):
    """
    Save filter comparison results to a text file.
    
    Args:
        comparison_data: Dictionary containing comparison statistics
        output_file: Path to output text file
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("FILTERING COMPARISON: AI vs Keyword-based\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            # Basic statistics
            f.write("📊 BASIC STATISTICS\n")
            f.write("-" * 80 + "\n")
            f.write(f"Total papers retrieved:        {comparison_data['total_papers']:4d}\n")
            f.write(f"Papers after keyword filter:   {comparison_data['keyword_kept']:4d} "
                   f"({comparison_data['keyword_kept']/comparison_data['total_papers']*100:.1f}%)\n")
            f.write(f"Papers after AI filter:        {comparison_data['ai_kept']:4d} "
                   f"({comparison_data['ai_kept']/comparison_data['total_papers']*100:.1f}%)\n\n")
            
            # Data quality issues
            if comparison_data.get('duplicates_in_kept_and_filtered'):
                f.write("⚠️  DATA QUALITY ISSUE DETECTED!\n")
                f.write("-" * 80 + "\n")
                f.write(f"Found {len(comparison_data['duplicates_in_kept_and_filtered'])} paper(s) "
                       f"appearing in BOTH kept and filtered lists:\n")
                for dup in comparison_data['duplicates_in_kept_and_filtered']:
                    f.write(f"  • {dup['title'][:70]}...\n")
                    f.write(f"    URL: {dup['url']}\n")
                    f.write(f"    Exclusion category: {dup['category']}\n")
                f.write("\n")
            
            # Overlap analysis
            f.write("🔄 OVERLAP ANALYSIS\n")
            f.write("-" * 80 + "\n")
            f.write(f"Papers included by BOTH:       {comparison_data['both_included']:4d}\n")
            f.write(f"Papers ONLY by keyword:        {comparison_data['only_keyword']:4d}\n")
            f.write(f"Papers ONLY by AI:             {comparison_data['only_ai']:4d}\n\n")
            f.write(f"✓ Agreement rate:              {comparison_data['agreement_rate']:.1f}%\n\n")
            
            # Examples of disagreement
            if comparison_data.get('only_keyword_examples'):
                f.write("=" * 80 + "\n")
                f.write("PAPERS ONLY INCLUDED BY KEYWORD FILTER (sample)\n")
                f.write("=" * 80 + "\n")
                for paper in comparison_data['only_keyword_examples']:
                    f.write(f"\n• {paper['title'][:70]}...\n")
                    f.write(f"  Authors: {paper['authors']}\n")
                    f.write(f"  URL: {paper['url']}\n")
                f.write("\n")
            
            if comparison_data.get('only_ai_examples'):
                f.write("=" * 80 + "\n")
                f.write("PAPERS ONLY INCLUDED BY AI FILTER (sample)\n")
                f.write("=" * 80 + "\n")
                for paper in comparison_data['only_ai_examples']:
                    f.write(f"\n• {paper['title'][:70]}...\n")
                    f.write(f"  Authors: {paper['authors']}\n")
                    f.write(f"  URL: {paper['url']}\n")
                f.write("\n")
            
            # Exclusion categories
            f.write("=" * 80 + "\n")
            f.write("EXCLUSION CATEGORIES ANALYSIS\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("📋 KEYWORD FILTER EXCLUSIONS:\n")
            f.write("-" * 80 + "\n")
            for category, count in comparison_data['keyword_exclusions'].items():
                f.write(f"  {category.replace('_', ' ').title():<20} {count:4d} papers\n")
            f.write(f"  {'Total Excluded':<20} {comparison_data['keyword_excluded_total']:4d} papers\n\n")
            
            f.write("📋 AI FILTER EXCLUSIONS:\n")
            f.write("-" * 80 + "\n")
            for category, count in comparison_data['ai_exclusions'].items():
                f.write(f"  {category.replace('_', ' ').title():<20} {count:4d} papers\n")
            f.write(f"  {'Total Excluded':<20} {comparison_data['ai_excluded_total']:4d} papers\n\n")
            
            # Category comparison
            if comparison_data.get('category_comparison'):
                f.write("=" * 80 + "\n")
                f.write("CATEGORY-BY-CATEGORY COMPARISON\n")
                f.write("=" * 80 + "\n\n")
                
                for category, stats in comparison_data['category_comparison'].items():
                    f.write(f"{category.replace('_', ' ').upper()}:\n")
                    f.write(f"  Keyword filter: {stats['keyword']:4d} papers\n")
                    f.write(f"  AI filter:      {stats['ai']:4d} papers\n")
                    f.write(f"  Both excluded:  {stats['both']:4d} papers\n")
                    f.write(f"  Only keyword:   {stats['only_keyword']:4d} papers\n")
                    f.write(f"  Only AI:        {stats['only_ai']:4d} papers\n\n")
            
            # Summary
            f.write("=" * 80 + "\n")
            f.write("SUMMARY\n")
            f.write("=" * 80 + "\n")
            f.write(f"\nThe keyword-based filter is "
                   f"{'more' if comparison_data['keyword_kept'] > comparison_data['ai_kept'] else 'less'} "
                   f"permissive than the AI filter.\n")
            f.write(f"- Keyword filter kept {comparison_data['keyword_kept']} papers "
                   f"({comparison_data['keyword_kept']/comparison_data['total_papers']*100:.1f}%)\n")
            f.write(f"- AI filter kept {comparison_data['ai_kept']} papers "
                   f"({comparison_data['ai_kept']/comparison_data['total_papers']*100:.1f}%)\n")
            f.write(f"- Agreement on {comparison_data['both_included']} papers "
                   f"({comparison_data['agreement_rate']:.1f}% of decisions)\n\n")
            
            if 'non_empirical' in comparison_data['ai_exclusions']:
                f.write(f"The AI filter has an additional category: non-empirical "
                       f"({comparison_data['ai_exclusions']['non_empirical']} papers)\n")
        
        logger.info(f"Saved filter comparison to {output_file}")
        
    except Exception as e:
        logger.error(f"Failed to save filter comparison: {e}")
