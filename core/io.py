"""
I/O utilities for loading and saving papers.
"""

import logging
import csv
from pathlib import Path
from typing import List, Optional
import pandas as pd

from src.models import Paper
from src.utils import load_papers_from_bib as _load_papers_from_bib
from src.utils import save_papers_csv as _save_papers_csv
from src.utils import save_papers_bib as _save_papers_bib


logger = logging.getLogger(__name__)


def load_papers(file_path: str, format: str = "auto") -> List[Paper]:
    """
    Load papers from file (BibTeX, CSV, or auto-detect).
    
    Args:
        file_path: Path to input file
        format: Format hint ('bibtex', 'csv', 'auto')
    
    Returns:
        List of Paper objects
    """
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")
    
    # Auto-detect format
    if format == "auto":
        suffix = path.suffix.lower()
        if suffix in ['.bib', '.bibtex']:
            format = "bibtex"
        elif suffix == '.csv':
            format = "csv"
        else:
            # Try BibTeX first
            format = "bibtex"
    
    if format == "bibtex":
        return _load_papers_from_bib(path)
    elif format == "csv":
        return load_papers_from_csv(path)
    else:
        raise ValueError(f"Unsupported format: {format}")


def load_papers_from_csv(csv_path: Path) -> List[Paper]:
    """
    Load papers from CSV file.
    
    Args:
        csv_path: Path to CSV file
    
    Returns:
        List of Paper objects
    """
    papers = []
    
    try:
        df = pd.read_csv(csv_path)
        
        for _, row in df.iterrows():
            paper = Paper(title=row.get('Title', row.get('title', '')))
            
            # Map CSV columns to Paper fields
            if 'Authors' in row:
                authors_str = row['Authors']
                if pd.notna(authors_str):
                    paper.authors = [a.strip() for a in str(authors_str).split(';')]
            
            if 'Abstract' in row and pd.notna(row['Abstract']):
                paper.abstract = str(row['Abstract'])
            
            if 'DOI' in row and pd.notna(row['DOI']):
                paper.doi = str(row['DOI'])
            
            if 'PMID' in row and pd.notna(row['PMID']):
                paper.pmid = str(row['PMID'])
            
            if 'Journal' in row and pd.notna(row['Journal']):
                paper.journal = str(row['Journal'])
            
            if 'URL' in row and pd.notna(row['URL']):
                paper.url = str(row['URL'])
            
            papers.append(paper)
        
        logger.info(f"Loaded {len(papers)} papers from CSV: {csv_path}")
        return papers
        
    except Exception as e:
        logger.error(f"Failed to load papers from CSV {csv_path}: {e}")
        return []


def save_papers(
    papers: List[Paper], 
    output_path: str, 
    format: str = "auto",
    output_dir: Optional[str] = None
) -> None:
    """
    Save papers to file in specified format.
    
    Args:
        papers: List of Paper objects
        output_path: Output file path
        format: Output format ('bibtex', 'csv', 'auto')
        output_dir: Optional output directory (creates if doesn't exist)
    """
    path = Path(output_path)
    
    # Create output directory if specified
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Auto-detect format
    if format == "auto":
        suffix = path.suffix.lower()
        if suffix in ['.bib', '.bibtex']:
            format = "bibtex"
        elif suffix == '.csv':
            format = "csv"
        else:
            format = "csv"  # Default to CSV
    
    if format == "bibtex":
        _save_papers_bib(papers, path)
    elif format == "csv":
        _save_papers_csv(papers, path)
    else:
        raise ValueError(f"Unsupported format: {format}")
    
    logger.info(f"Saved {len(papers)} papers to: {output_path}")


def get_papers_dataframe(papers: List[Paper]) -> pd.DataFrame:
    """
    Convert papers to pandas DataFrame for analysis/preview.
    
    Args:
        papers: List of Paper objects
    
    Returns:
        DataFrame with paper information
    """
    data = []
    for paper in papers:
        data.append({
            'Title': paper.title,
            'Authors': '; '.join(paper.authors) if paper.authors else '',
            'Journal': paper.journal or '',
            'Year': paper.publication_date.year if paper.publication_date else '',
            'DOI': paper.doi or '',
            'PMID': paper.pmid or '',
            'Has_Abstract': 'Yes' if paper.abstract else 'No',
            'Abstract_Length': len(paper.abstract) if paper.abstract else 0,
        })
    
    return pd.DataFrame(data)
