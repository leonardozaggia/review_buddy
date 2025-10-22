"""
Simple data models for papers, authors, and publications.
No complexity - just what we need to store and export data.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set
from datetime import date


@dataclass
class Author:
    """Represents a paper author"""
    name: str
    affiliation: Optional[str] = None
    email: Optional[str] = None


@dataclass
class Paper:
    """
    Represents a scientific paper with all metadata needed for 
    bibliography and downloading.
    """
    title: str
    authors: List[str] = field(default_factory=list)
    abstract: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None  # PubMed ID
    arxiv_id: Optional[str] = None
    publication_date: Optional[date] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    issn: Optional[str] = None
    isbn: Optional[str] = None
    url: Optional[str] = None
    pdf_url: Optional[str] = None
    keywords: Set[str] = field(default_factory=set)
    citations: Optional[int] = None
    sources: Set[str] = field(default_factory=set)  # Which databases found this paper
    
    def __hash__(self):
        """Hash based on title for deduplication"""
        return hash(self.title.lower().strip())
    
    def __eq__(self, other):
        """Papers are equal if they have the same title or same DOI"""
        if not isinstance(other, Paper):
            return False
        
        # If both have DOI, use that
        if self.doi and other.doi:
            return self.doi.lower() == other.doi.lower()
        
        # Otherwise use title
        return self.title.lower().strip() == other.title.lower().strip()
    
    def to_bibtex_entry(self, cite_key: Optional[str] = None) -> str:
        """
        Generate a BibTeX entry for this paper.
        
        Args:
            cite_key: Citation key (defaults to first_author_year)
        
        Returns:
            BibTeX formatted string
        """
        if cite_key is None:
            # Generate cite key: FirstAuthorLastName_Year
            if self.authors and self.publication_date:
                first_author = self.authors[0].split()[-1]  # Get last name
                cite_key = f"{first_author}_{self.publication_date.year}"
            else:
                cite_key = "Unknown"
        
        # Determine entry type
        entry_type = "article"  # Default
        if self.arxiv_id:
            entry_type = "misc"
        
        lines = [f"@{entry_type}{{{cite_key},"]
        
        # Add fields
        if self.title:
            lines.append(f'  title = {{{self.title}}},')
        if self.authors:
            authors_str = ' and '.join(self.authors)
            lines.append(f'  author = {{{authors_str}}},')
        if self.journal:
            lines.append(f'  journal = {{{self.journal}}},')
        if self.publication_date:
            lines.append(f'  year = {{{self.publication_date.year}}},')
        if self.volume:
            lines.append(f'  volume = {{{self.volume}}},')
        if self.issue:
            lines.append(f'  number = {{{self.issue}}},')
        if self.pages:
            lines.append(f'  pages = {{{self.pages}}},')
        if self.doi:
            lines.append(f'  doi = {{{self.doi}}},')
        if self.url:
            lines.append(f'  url = {{{self.url}}},')
        if self.pmid:
            lines.append(f'  pmid = {{{self.pmid}}},')
        if self.arxiv_id:
            lines.append(f'  arxiv_id = {{{self.arxiv_id}}},')
        if self.abstract:
            # Clean abstract for BibTeX
            clean_abstract = self.abstract.replace('{', '').replace('}', '')
            lines.append(f'  abstract = {{{clean_abstract}}},')
        
        lines.append("}")
        return '\n'.join(lines)
    
    def merge_with(self, other: 'Paper'):
        """
        Merge data from another paper object (for deduplication).
        Takes non-null values from other if this paper is missing them.
        
        This is called on the PRIMARY paper (the one we're keeping),
        and 'other' is the secondary paper we're merging data from.
        
        Args:
            other: Paper to merge data from
        """
        if not other:
            return
        
        # Merge authors list - take ours if we have more, otherwise take theirs
        if not self.authors and other.authors:
            self.authors = other.authors.copy()
        elif self.authors and other.authors and len(other.authors) > len(self.authors):
            self.authors = other.authors.copy()
        
        # Merge simple fields (take other if we don't have it)
        if not self.abstract and other.abstract:
            self.abstract = other.abstract
        if not self.doi and other.doi:
            self.doi = other.doi
        if not self.pmid and other.pmid:
            self.pmid = other.pmid
        if not self.arxiv_id and other.arxiv_id:
            self.arxiv_id = other.arxiv_id
        if not self.publication_date and other.publication_date:
            self.publication_date = other.publication_date
        if not self.journal and other.journal:
            self.journal = other.journal
        if not self.volume and other.volume:
            self.volume = other.volume
        if not self.issue and other.issue:
            self.issue = other.issue
        if not self.pages and other.pages:
            self.pages = other.pages
        if not self.publisher and other.publisher:
            self.publisher = other.publisher
        if not self.issn and other.issn:
            self.issn = other.issn
        if not self.isbn and other.isbn:
            self.isbn = other.isbn
        if not self.url and other.url:
            self.url = other.url
        if not self.pdf_url and other.pdf_url:
            self.pdf_url = other.pdf_url
        
        # Merge collections
        self.keywords.update(other.keywords)
        self.sources.update(other.sources)
        
        # Take higher citation count
        if other.citations and (not self.citations or other.citations > self.citations):
            self.citations = other.citations
