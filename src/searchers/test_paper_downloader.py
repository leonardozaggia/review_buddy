"""
Test script for PaperDownloader module.
Checks Unpaywall, arXiv, and Sci-Hub download functionality for a set of sample DOIs and arXiv IDs.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from paper_downloader import PaperDownloader

# Load environment variables from .env in parent directory
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Set up test output directory
test_output_dir = Path(__file__).parent / "test_pdfs"
test_output_dir.mkdir(exist_ok=True)

# Get Unpaywall email from environment
unpaywall_email = os.getenv("UNPAYWALL_EMAIL") or os.getenv("PUBMED_EMAIL")

print(f"Environment check:")
print(f"  UNPAYWALL_EMAIL: {unpaywall_email or 'NOT SET'}")
print(f"  Test output dir: {test_output_dir}")
print()

# Instantiate downloader (enable Sci-Hub fallback)
downloader = PaperDownloader(
    output_dir=str(test_output_dir),
    use_scihub=True,
    unpaywall_email=unpaywall_email
)

# Test cases: mix of OA, paywalled, arXiv, and invalid DOIs
TEST_ENTRIES = [
    # arXiv direct (most reliable)
    {"title": "arXiv Example 1", "arxiv_id": "2101.00001"},
    {"title": "arXiv Example 2", "url": "https://arxiv.org/abs/2312.00001"},
    # Open access via Unpaywall
    {"title": "OA via Unpaywall", "doi": "10.1371/journal.pone.0000001"},
    # Paywalled, should fallback to Sci-Hub
    {"title": "Paywalled Example", "doi": "10.1038/nature01412"},
]

print("Testing PaperDownloader with sample entries...")
print("="*60)

for i, entry in enumerate(TEST_ENTRIES, 1):
    print(f"\nTest {i}/{len(TEST_ENTRIES)}: {entry['title']}")
    print("-"*60)
    downloader._download_paper(entry)

print("\n" + "="*60)
print(f"\nCheck '{test_output_dir}' for downloaded PDFs and 'download.log' for details.")

# Count successful downloads
pdf_files = list(test_output_dir.glob("*.pdf"))
print(f"\nSuccessfully downloaded: {len(pdf_files)} / {len(TEST_ENTRIES)} PDFs")
for pdf in pdf_files:
    print(f"  - {pdf.name} ({pdf.stat().st_size} bytes)")
