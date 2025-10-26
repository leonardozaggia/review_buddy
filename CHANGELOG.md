# Changelog

All notable changes to Review Buddy will be documented in this file.

## [2.0.0] - 2025-10-26

### 🎉 Major Refactor

**Breaking Changes:**
- New CLI command structure (`reviewbuddy` instead of separate scripts)
- New configuration system (YAML-based)
- New directory structure (`core/` module)

**Added:**
- **Unified CLI**: Single `reviewbuddy` command with subcommands (search, filter, download, run, init, info)
- **Streamlit GUI**: Web interface for complete pipeline with three-step workflow
- **Modular Architecture**: Separated core logic from interfaces
- **Configuration System**: YAML-based config with Pydantic validation
- **Filter Engine Interface**: Abstract base class for consistent filtering API
- **Dual Filter Engines**: Normal (keyword) and AI (LLM) engines with same interface
- **Test Suite**: Pytest-based tests for core modules
- **Sample Data**: Example CSV for testing and demos
- **Demo Script**: `demo.py` showing end-to-end usage
- **Package Structure**: `pyproject.toml` with proper dependencies
- **Rich CLI Output**: Better formatting, progress bars, colors

**Improved:**
- **Better Organization**: `core/` for business logic, `src/` for implementations
- **Consistent APIs**: All engines implement `filter_records()` 
- **Error Handling**: More informative error messages
- **Documentation**: Migration guide, usage examples, architecture docs
- **Type Safety**: Pydantic models for configuration validation
- **Logging**: Structured logging with Rich

**Maintained:**
- **Backward Compatibility**: Original `01_*.py`, `02_*.py`, `03_*.py` scripts still work
- **Existing Features**: All search sources, download methods, and filters preserved
- **Output Formats**: BibTeX, RIS, CSV export unchanged

### New CLI Commands

```bash
reviewbuddy init          # Create config.yaml
reviewbuddy search        # Search papers
reviewbuddy filter        # Filter papers (--engine normal|ai)
reviewbuddy download      # Download PDFs
reviewbuddy run           # Full pipeline
reviewbuddy info          # Show config
```

### New Modules

- `core/config_loader.py` - Configuration management
- `core/engines.py` - Filter engine factory
- `core/filter_normal.py` - Keyword filter engine
- `core/filter_ai.py` - AI filter engine  
- `core/io.py` - I/O utilities
- `core/postprocess.py` - Result processing
- `core/preprocess.py` - Preprocessing utilities
- `cli.py` - Unified CLI
- `app.py` - Streamlit GUI
- `demo.py` - Demo script

### Migration Guide

**Old → New:**
- `python 01_fetch_metadata.py` → `reviewbuddy search`
- `python 02_abstract_filter.py` → `reviewbuddy filter --engine normal`
- `python 02_abstract_filter_AI.py` → `reviewbuddy filter --engine ai`
- `python 03_download_papers.py` → `reviewbuddy download`
- All steps → `reviewbuddy run`

**Old scripts continue to work for backward compatibility.**

### Requirements

**New Dependencies:**
- `pydantic>=2.0.0` - Configuration validation
- `pyyaml>=6.0` - YAML parsing
- `typer[all]>=0.9.0` - CLI framework
- `rich>=13.0.0` - Terminal formatting
- `streamlit>=1.28.0` - GUI framework
- `pandas>=1.3.0` - Data handling

### Documentation

- Updated README with quick start, migration guide, and examples
- Added `docs/NEW_FEATURES_V2.md` with filtering engine comparison
- Maintained existing docs (QUERY_SYNTAX.md, DOWNLOADER_GUIDE.md, etc.)

---

## [1.0.0] - 2023

Initial release with separate scripts for search, filter, and download.
