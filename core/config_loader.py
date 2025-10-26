"""
Configuration loader using Pydantic for type-safe YAML configs.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
import yaml


class IOConfig(BaseModel):
    """I/O paths configuration"""
    input_path: str = Field(default="results/references.bib", description="Input bibliography file")
    output_dir: str = Field(default="results", description="Output directory")
    pdf_dir: str = Field(default="results/pdfs", description="PDF download directory")


class SearchConfig(BaseModel):
    """Search/metadata fetch configuration"""
    query: str = Field(default="", description="Search query")
    year_from: int = Field(default=2020, description="Search from year")
    max_results_per_source: int = Field(default=999999, description="Max results per source")


class NormalFilterConfig(BaseModel):
    """Normal (keyword-based) filter configuration"""
    enabled_filters: List[str] = Field(
        default_factory=lambda: ["no_abstract", "non_english", "non_human", "non_empirical"],
        description="List of filters to apply"
    )
    keywords: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Custom keyword filters"
    )


class AIFilterConfig(BaseModel):
    """AI filter configuration"""
    model: str = Field(default="llama3.1:8b", description="Ollama model name")
    ollama_url: str = Field(default="http://localhost:11434", description="Ollama server URL")
    temperature: float = Field(default=0.1, description="Sampling temperature")
    confidence_threshold: float = Field(default=0.5, description="Minimum confidence for filtering")
    cache_responses: bool = Field(default=True, description="Enable response caching")
    retry_attempts: int = Field(default=3, description="Number of retry attempts")
    filters: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="AI filter definitions with prompts"
    )


class DownloadConfig(BaseModel):
    """Download configuration"""
    use_scihub: bool = Field(default=False, description="Enable Sci-Hub fallback")
    unpaywall_email: Optional[str] = Field(default=None, description="Unpaywall API email")


class PipelineConfig(BaseModel):
    """Complete pipeline configuration"""
    engine: str = Field(default="normal", description="Filter engine: 'normal' or 'ai'")
    io: IOConfig = Field(default_factory=IOConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    normal: NormalFilterConfig = Field(default_factory=NormalFilterConfig)
    ai: AIFilterConfig = Field(default_factory=AIFilterConfig)
    download: DownloadConfig = Field(default_factory=DownloadConfig)
    
    @field_validator('engine')
    @classmethod
    def validate_engine(cls, v: str) -> str:
        """Validate engine choice"""
        if v not in ['normal', 'ai']:
            raise ValueError(f"Engine must be 'normal' or 'ai', got: {v}")
        return v
    
    def get_filter_config(self):
        """Get the appropriate filter config based on engine"""
        if self.engine == "ai":
            return self.ai
        return self.normal


def load_config(config_path: Optional[str] = None) -> PipelineConfig:
    """
    Load configuration from YAML file with environment variable overrides.
    
    Args:
        config_path: Path to config.yaml (default: config.yaml in current dir)
    
    Returns:
        PipelineConfig instance
    """
    if config_path is None:
        config_path = "config.yaml"
    
    config_file = Path(config_path)
    
    # Load from YAML if exists
    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    
    # Override with environment variables
    if os.getenv('FILTER_ENGINE'):
        data['engine'] = os.getenv('FILTER_ENGINE')
    
    if os.getenv('UNPAYWALL_EMAIL'):
        if 'download' not in data:
            data['download'] = {}
        data['download']['unpaywall_email'] = os.getenv('UNPAYWALL_EMAIL')
    
    if os.getenv('OLLAMA_MODEL'):
        if 'ai' not in data:
            data['ai'] = {}
        data['ai']['model'] = os.getenv('OLLAMA_MODEL')
    
    if os.getenv('OLLAMA_URL'):
        if 'ai' not in data:
            data['ai'] = {}
        data['ai']['ollama_url'] = os.getenv('OLLAMA_URL')
    
    # Create config
    config = PipelineConfig(**data)
    
    return config


def create_default_config(output_path: str = "config.yaml"):
    """
    Create a default config.yaml file.
    
    Args:
        output_path: Path where to save the config file
    """
    default_config = {
        'engine': 'normal',
        'io': {
            'input_path': 'results/references.bib',
            'output_dir': 'results',
            'pdf_dir': 'results/pdfs',
        },
        'search': {
            'query': 'machine learning AND healthcare',
            'year_from': 2020,
            'max_results_per_source': 999999,
        },
        'normal': {
            'enabled_filters': ['no_abstract', 'non_english', 'non_human', 'non_empirical'],
            'keywords': {
                'epilepsy': [
                    'epileptic spike', 'epileptic spikes', 'interictal spike', 
                    'ictal spike', 'seizure spike'
                ],
                'bci': [
                    'brain-computer interface', 'brain computer interface', 
                    'bci', 'brain-machine interface'
                ],
                'non_human': [
                    'rat', 'rats', 'mouse', 'mice', 'rodent', 'rodents',
                    'monkey', 'monkeys', 'primate', 'in vitro', 'cell culture'
                ],
                'non_empirical': [
                    'systematic review', 'meta-analysis', 'literature review',
                    'review article', 'survey paper'
                ]
            }
        },
        'ai': {
            'model': 'llama3.1:8b',
            'ollama_url': 'http://localhost:11434',
            'temperature': 0.1,
            'confidence_threshold': 0.5,
            'cache_responses': True,
            'retry_attempts': 3,
            'filters': {
                'epilepsy': {
                    'enabled': True,
                    'prompt': 'Does this paper focus primarily on epileptic spikes, seizure detection, or epileptiform activity?',
                    'description': 'Papers about epilepsy-related spike detection'
                },
                'bci': {
                    'enabled': True,
                    'prompt': 'Is this paper about brain-computer interfaces (BCI) or brain-machine interfaces (BMI)?',
                    'description': 'Papers about BCI/BMI systems'
                },
                'non_human': {
                    'enabled': True,
                    'prompt': 'Is this paper based on animal studies, in-vitro experiments, or computational models only (not human subjects)?',
                    'description': 'Non-human or in-vitro studies'
                },
                'non_empirical': {
                    'enabled': True,
                    'prompt': 'Is this a review paper, survey, meta-analysis, or opinion piece without original empirical data collection?',
                    'description': 'Reviews and non-empirical papers'
                }
            }
        },
        'download': {
            'use_scihub': False,
            'unpaywall_email': None,
        }
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(default_config, f, default_flow_style=False, sort_keys=False)
    
    print(f"Created default config at: {output_path}")
