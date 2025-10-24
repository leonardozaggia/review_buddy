"""
Fetch Paper Metadata

Search multiple academic databases and generate bibliography files.

Usage:
    python 01_fetch_metadata.py

Configuration:
    Set API keys in .env file (see .env.example)
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.paper_searcher import PaperSearcher
from src.config import Config

# Load environment variables
load_dotenv()

# Configure logging to show progress
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Configuration
#QUERY = "machine learning AND healthcare"                      # <- Specify your query here
QUERY = Path("query.txt").read_text(encoding="utf-8").strip()   # <- Alternatively, parse a query from a .txt file
YEAR_FROM = 2020
MAX_RESULTS_PER_SOURCE = 999999                                 # Use 999999 for unlimited search
OUTPUT_DIR = Path("results")

def main():
    """Main execution function"""
    print("=" * 80)
    print("REVIEW BUDDY - FETCH PAPER METADATA")
    print("=" * 80)
    print()
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Check configuration
    config = Config(max_results_per_source=MAX_RESULTS_PER_SOURCE)
    
    available_sources = []
    if config.has_scopus_access():
        available_sources.append("Scopus")
    if config.has_pubmed_access():
        available_sources.append("PubMed")
    if config.has_arxiv_access():
        available_sources.append("arXiv")
    if config.has_scholar_access():
        available_sources.append("Google Scholar")
    if config.has_ieee_access():
        available_sources.append("IEEE Xplore")
    
    if not available_sources:
        print("❌ ERROR: No API keys configured!")
        print()
        print("Please create a .env file with at least one API key:")
        print("  - Copy .env.example to .env")
        print("  - Add your API keys")
        print()
        print("See README.md for setup instructions.")
        return 1
    
    print(f"✓ Available sources: {', '.join(available_sources)}")
    print()
    print(f"Search query: {QUERY}")
    print(f"Year from: {YEAR_FROM}")
    print(f"Max results per source: {MAX_RESULTS_PER_SOURCE}")
    print()
    
    # Create searcher
    searcher = PaperSearcher(config)
    
    # Search all sources
    print("=" * 80)
    print("SEARCHING...")
    print("=" * 80)
    
    papers = searcher.search_all(query=QUERY, year_from=YEAR_FROM)
    
    # Display results
    print()
    print("=" * 80)
    print(f"FOUND {len(papers)} UNIQUE PAPERS")
    print("=" * 80)
    
    # Count papers by source
    source_counts = {}
    for paper in papers:
        for source in paper.sources:
            source_counts[source] = source_counts.get(source, 0) + 1
    
    print()
    print("Papers by source:")
    for source, count in sorted(source_counts.items()):
        print(f"  {source}: {count}")
    
    # Generate output files
    print()
    print("=" * 80)
    print("GENERATING OUTPUT FILES...")
    print("=" * 80)
    
    bib_file = OUTPUT_DIR / "references.bib"
    ris_file = OUTPUT_DIR / "references.ris"
    csv_file = OUTPUT_DIR / "papers.csv"
    
    searcher.generate_bibliography(papers, format="bibtex", output_file=str(bib_file))
    searcher.generate_bibliography(papers, format="ris", output_file=str(ris_file))
    searcher.export_to_csv(papers, output_file=str(csv_file))
    
    print(f"✓ BibTeX: {bib_file}")
    print(f"✓ RIS: {ris_file}")
    print(f"✓ CSV: {csv_file}")
    print()
    print("=" * 80)
    print("COMPLETE!")
    print("=" * 80)
    print()
    print("Next step: Run 02_abstract_filter.py to filter papers by abstract")
    print("Or skip filtering and run 03_download_papers.py to download PDFs")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())