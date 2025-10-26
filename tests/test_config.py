"""
Tests for configuration loader.
"""

import pytest
from pathlib import Path
import yaml

from core.config_loader import PipelineConfig, load_config, create_default_config


def test_default_config():
    """Test default configuration"""
    config = PipelineConfig()
    
    assert config.engine == "normal"
    assert config.io.input_path == "results/references.bib"
    assert config.search.year_from == 2020
    assert config.normal.enabled_filters is not None
    assert config.ai.model == "llama3.1:8b"


def test_engine_validation():
    """Test engine validation"""
    # Valid engines
    config1 = PipelineConfig(engine="normal")
    assert config1.engine == "normal"
    
    config2 = PipelineConfig(engine="ai")
    assert config2.engine == "ai"
    
    # Invalid engine
    with pytest.raises(ValueError):
        PipelineConfig(engine="invalid")


def test_load_config_from_yaml(tmp_path):
    """Test loading config from YAML file"""
    config_file = tmp_path / "test_config.yaml"
    
    config_data = {
        'engine': 'ai',
        'io': {
            'input_path': 'custom/path.bib',
            'output_dir': 'custom/output'
        },
        'search': {
            'query': 'test query',
            'year_from': 2015
        }
    }
    
    with open(config_file, 'w') as f:
        yaml.dump(config_data, f)
    
    config = load_config(str(config_file))
    
    assert config.engine == "ai"
    assert config.io.input_path == "custom/path.bib"
    assert config.io.output_dir == "custom/output"
    assert config.search.query == "test query"
    assert config.search.year_from == 2015


def test_load_config_nonexistent_file():
    """Test loading config from nonexistent file returns defaults"""
    config = load_config("nonexistent.yaml")
    
    # Should return default config
    assert config.engine == "normal"


def test_create_default_config(tmp_path):
    """Test creating default config file"""
    config_file = tmp_path / "config.yaml"
    
    create_default_config(str(config_file))
    
    assert config_file.exists()
    
    # Load and verify
    config = load_config(str(config_file))
    assert config.engine == "normal"
    assert config.search.year_from == 2020


def test_get_filter_config():
    """Test getting appropriate filter config"""
    config_normal = PipelineConfig(engine="normal")
    assert config_normal.get_filter_config() == config_normal.normal
    
    config_ai = PipelineConfig(engine="ai")
    assert config_ai.get_filter_config() == config_ai.ai
