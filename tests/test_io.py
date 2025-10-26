"""
Tests for I/O operations.
"""

import pytest
from pathlib import Path
from datetime import date

from src.models import Paper
from core.io import load_papers, save_papers, get_papers_dataframe


@pytest.fixture
def sample_papers():
    """Create sample papers for testing"""
    papers = [
        Paper(
            title="Machine Learning in Healthcare",
            authors=["John Doe", "Jane Smith"],
            abstract="This paper discusses ML applications in healthcare...",
            doi="10.1234/ml.2023.001",
            journal="Journal of AI",
            publication_date=date(2023, 1, 1)
        ),
        Paper(
            title="Deep Learning for Medical Imaging",
            authors=["Alice Johnson"],
            abstract="We present a deep learning approach for medical imaging...",
            doi="10.1234/dl.2023.002",
            pmid="12345678",
            publication_date=date(2023, 6, 15)
        ),
    ]
    return papers


def test_save_and_load_csv(sample_papers, tmp_path):
    """Test saving and loading papers in CSV format"""
    csv_file = tmp_path / "test_papers.csv"
    
    # Save
    save_papers(sample_papers, str(csv_file), format="csv")
    assert csv_file.exists()
    
    # Load
    loaded = load_papers(str(csv_file), format="csv")
    assert len(loaded) == 2
    assert loaded[0].title == "Machine Learning in Healthcare"
    assert loaded[1].doi == "10.1234/dl.2023.002"


def test_save_and_load_bibtex(sample_papers, tmp_path):
    """Test saving and loading papers in BibTeX format"""
    bib_file = tmp_path / "test_papers.bib"
    
    # Save
    save_papers(sample_papers, str(bib_file), format="bibtex")
    assert bib_file.exists()
    
    # Load
    loaded = load_papers(str(bib_file), format="bibtex")
    assert len(loaded) == 2
    assert any("Machine Learning" in p.title for p in loaded)


def test_get_papers_dataframe(sample_papers):
    """Test converting papers to DataFrame"""
    df = get_papers_dataframe(sample_papers)
    
    assert len(df) == 2
    assert "Title" in df.columns
    assert "Authors" in df.columns
    assert "DOI" in df.columns
    assert df.iloc[0]["Title"] == "Machine Learning in Healthcare"


def test_auto_format_detection(sample_papers, tmp_path):
    """Test automatic format detection"""
    csv_file = tmp_path / "test.csv"
    bib_file = tmp_path / "test.bib"
    
    # Save with auto format
    save_papers(sample_papers, str(csv_file), format="auto")
    save_papers(sample_papers, str(bib_file), format="auto")
    
    assert csv_file.exists()
    assert bib_file.exists()
    
    # Load with auto format
    loaded_csv = load_papers(str(csv_file), format="auto")
    loaded_bib = load_papers(str(bib_file), format="auto")
    
    assert len(loaded_csv) == 2
    assert len(loaded_bib) == 2
