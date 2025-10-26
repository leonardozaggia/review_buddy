"""
Pytest configuration and fixtures.
"""

import pytest
from pathlib import Path


@pytest.fixture
def sample_data_dir():
    """Get path to sample data directory"""
    return Path(__file__).parent.parent / "data"


@pytest.fixture
def results_dir(tmp_path):
    """Create temporary results directory"""
    results = tmp_path / "results"
    results.mkdir()
    return results
