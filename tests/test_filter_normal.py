"""
Tests for normal filter engine.
"""

import pytest
from datetime import date

from src.models import Paper
from core.filter_normal import NormalFilterEngine, create_default_keywords
from core.config_loader import NormalFilterConfig


@pytest.fixture
def sample_papers():
    """Create sample papers with different characteristics"""
    papers = [
        Paper(
            title="Machine Learning in Human Healthcare",
            abstract="We studied machine learning applications in human clinical trials with 100 patients.",
        ),
        Paper(
            title="Deep Learning for Rat Brain Analysis",
            abstract="We performed deep learning analysis on rat brain slices in vitro.",
        ),
        Paper(
            title="Review of Machine Learning Methods",
            abstract="This systematic review covers machine learning methods in healthcare.",
        ),
        Paper(
            title="BCI System for Communication",
            abstract="We developed a brain-computer interface for patient communication.",
        ),
        Paper(
            title="Paper Without Abstract",
            abstract=None,
        ),
    ]
    return papers


def test_normal_filter_engine_initialization():
    """Test engine initialization"""
    config = NormalFilterConfig()
    engine = NormalFilterEngine(config)
    
    assert engine.get_engine_name() == "normal"


def test_filter_no_abstract(sample_papers):
    """Test filtering papers without abstracts"""
    config = NormalFilterConfig(enabled_filters=["no_abstract"])
    engine = NormalFilterEngine(config)
    
    results = engine.filter_records(sample_papers)
    
    assert len(results['kept']) == 4  # 4 papers have abstracts
    assert len(results['filtered']['no_abstract']) == 1


def test_filter_non_human(sample_papers):
    """Test filtering non-human studies"""
    config = NormalFilterConfig(
        enabled_filters=["non_human"],
        keywords=create_default_keywords()
    )
    engine = NormalFilterEngine(config)
    
    results = engine.filter_records(sample_papers)
    
    # Should filter the rat study
    filtered_titles = [p.title for p in results['filtered'].get('non_human', [])]
    assert any("Rat" in title for title in filtered_titles)


def test_filter_non_empirical(sample_papers):
    """Test filtering review papers"""
    config = NormalFilterConfig(
        enabled_filters=["non_empirical"],
        keywords=create_default_keywords()
    )
    engine = NormalFilterEngine(config)
    
    results = engine.filter_records(sample_papers)
    
    # Should filter the review paper
    filtered_titles = [p.title for p in results['filtered'].get('non_empirical', [])]
    assert any("Review" in title for title in filtered_titles)


def test_filter_bci(sample_papers):
    """Test filtering BCI papers"""
    config = NormalFilterConfig(
        enabled_filters=["bci"],
        keywords=create_default_keywords()
    )
    engine = NormalFilterEngine(config)
    
    results = engine.filter_records(sample_papers)
    
    # Should filter the BCI paper
    filtered_titles = [p.title for p in results['filtered'].get('bci', [])]
    assert any("BCI" in title for title in filtered_titles)


def test_multiple_filters(sample_papers):
    """Test applying multiple filters"""
    config = NormalFilterConfig(
        enabled_filters=["no_abstract", "non_human", "non_empirical", "bci"],
        keywords=create_default_keywords()
    )
    engine = NormalFilterEngine(config)
    
    results = engine.filter_records(sample_papers)
    
    # Should keep only the first paper
    assert len(results['kept']) == 1
    assert results['kept'][0].title == "Machine Learning in Human Healthcare"
    
    # Check summary
    summary = results['summary']
    assert summary['initial_count'] == 5
    assert summary['final_count'] == 1
    assert summary['total_filtered'] == 4


def test_custom_keywords():
    """Test custom keyword filters"""
    papers = [
        Paper(
            title="fMRI Study of Brain",
            abstract="We used fMRI to study brain activation.",
        ),
        Paper(
            title="EEG Study of Brain",
            abstract="We used EEG to study brain waves.",
        ),
    ]
    
    config = NormalFilterConfig(
        enabled_filters=["fmri_only"],
        keywords={
            'fmri_only': ['fmri', 'functional magnetic resonance']
        }
    )
    engine = NormalFilterEngine(config)
    
    results = engine.filter_records(papers)
    
    assert len(results['kept']) == 1
    assert "EEG" in results['kept'][0].title
