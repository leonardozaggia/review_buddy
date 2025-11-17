"""
Test script to compare PubMed API results with PubMed web interface.

Status of test: PASSED
- same number of results returned by API and web interface

This script:
1. Reads the query from query.txt
2. Fetches results from PubMed API
3. Saves results to a BibTeX file
4. Outputs the exact query string for PubMed's advanced search
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.searchers.pubmed_searcher import PubMedSearcher
from src.utils import save_papers_bib
from src.config import Config
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_query(query_file: str = "query.txt") -> str:
    """Load query from file."""
    query_path = Path(__file__).parent.parent / query_file
    with open(query_path, 'r', encoding='utf-8') as f:
        return f.read().strip()


def convert_query_to_pubmed_format(query: str) -> str:
    """
    Convert the query to PubMed advanced search format.
    
    PubMed uses different syntax than what we might have in query.txt.
    This function ensures the query works with PubMed's web interface.
    """
    # Normalize the query - remove extra whitespace and newlines
    normalized = ' '.join(query.split())
    
    return normalized


def generate_pubmed_web_query(query: str) -> str:
    """
    Generate the exact query string to paste in PubMed advanced search.
    
    The query should work in: https://pubmed.ncbi.nlm.nih.gov/advanced/
    """
    pubmed_query = convert_query_to_pubmed_format(query)
    
    print("\n" + "="*80)
    print("PUBMED ADVANCED SEARCH QUERY")
    print("="*80)
    print("\nGo to: https://pubmed.ncbi.nlm.nih.gov/advanced/")
    print("\nPaste the following query in the 'Query box':\n")
    print("-"*80)
    print(pubmed_query)
    print("-"*80)
    print("\n")
    
    return pubmed_query


def main():
    """Main function to test PubMed query."""
    
    # Load configuration from environment or use defaults
    config = Config()
    
    # Configuration
    EMAIL = config.pubmed_email or "your.email@example.com"
    API_KEY = config.pubmed_api_key
    MAX_RESULTS = config.max_results_per_source
    OUTPUT_DIR = Path(__file__).parent.parent / "test_results" / "pubmed_debug"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    if not config.pubmed_email:
        logger.warning("PUBMED_EMAIL not set in environment. Using placeholder email.")
        logger.warning("Set PUBMED_EMAIL environment variable for actual searches.")
    
    # Load query
    logger.info("Loading query from query.txt...")
    query = load_query()
    
    logger.info(f"Original query:\n{query}\n")
    
    # Generate PubMed web query format
    pubmed_web_query = generate_pubmed_web_query(query)
    
    # Save the web query to a file for easy copy-paste
    web_query_file = OUTPUT_DIR / "pubmed_web_query.txt"
    with open(web_query_file, 'w', encoding='utf-8') as f:
        f.write(pubmed_web_query)
    logger.info(f"Web query saved to: {web_query_file}")
    
    # Fetch results from PubMed API
    logger.info("Fetching results from PubMed API...")
    searcher = PubMedSearcher(
        email=EMAIL,
        api_key=API_KEY,
        max_results=MAX_RESULTS
    )
    
    papers = searcher.search(query)
    
    logger.info(f"\nPubMed API returned {len(papers)} papers")
    
    # Save to BibTeX
    if papers:
        bib_file = OUTPUT_DIR / "pubmed_api_results.bib"
        save_papers_bib(papers, bib_file)
        logger.info(f"Results saved to: {bib_file}")
        
        # Print first few results for verification
        logger.info("\nFirst 5 papers:")
        for i, paper in enumerate(papers[:5], 1):
            year = paper.publication_date.year if paper.publication_date else "N/A"
            logger.info(f"{i}. {paper.title[:100]}... ({year})")
            logger.info(f"   PMID: {paper.pmid}")
    
    # Instructions for comparison
    print("\n" + "="*80)
    print("COMPARISON INSTRUCTIONS")
    print("="*80)
    print("\n1. Go to PubMed Advanced Search:")
    print("   https://pubmed.ncbi.nlm.nih.gov/advanced/")
    print("\n2. Paste the query from above (or from pubmed_web_query.txt)")
    print("\n3. Click 'Search' and note the number of results")
    print(f"\n4. Our API returned: {len(papers)} papers")
    print("\n5. Download the results from PubMed web:")
    print("   - Click 'Save' button")
    print("   - Select 'All results'")
    print("   - Format: PubMed")
    print("   - Click 'Create file'")
    print("\n6. Compare the PMIDs between:")
    print(f"   - API results: {OUTPUT_DIR / 'pubmed_api_results.bib'}")
    print("   - Web results: (the file you downloaded)")
    print("\n7. You can also export web results as BibTeX for direct comparison:")
    print("   - Save > Format: BibTeX > Create file")
    print("\n" + "="*80)
    
    # Save PMIDs for easy comparison
    if papers:
        pmids_file = OUTPUT_DIR / "pubmed_api_pmids.txt"
        with open(pmids_file, 'w', encoding='utf-8') as f:
            for paper in papers:
                if paper.pmid:
                    f.write(f"{paper.pmid}\n")
        logger.info(f"\nPMIDs saved to: {pmids_file}")
        logger.info("You can compare this list with PMIDs from the web interface")


if __name__ == "__main__":
    main()
