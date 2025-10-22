"""
Utility functions for loading and saving papers.
"""

import logging
import csv
from pathlib import Path
from datetime import date
from typing import List

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
