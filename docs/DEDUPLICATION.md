# Deduplication Logic

## Overview

When searching multiple sources, the same paper often appears in different databases. Review Buddy intelligently deduplicates results while preserving all useful metadata.

**Papers are duplicates if they share:**
- Same DOI (most reliable), OR
- Same title (case-insensitive)

## Priority System

When duplicates are found, the "primary" entry is selected using this hierarchy:

### 1. PubMed Priority (Highest)
**PubMed papers are always preferred.**

**Why?** PMID enables access to PubMed Central (PMC), which has the highest success rate for free PDF downloads.

### 2. Publication Date (Secondary)
If PubMed status is equal, **prefer the more recent publication** for updated metadata and current citations.

### 3. Has Date vs No Date
Prefer papers with publication dates over those without.

### 4. Default
Keep the first entry encountered.

## Data Merging

The primary paper retains all its fields. Missing fields are filled from duplicate papers:

- **Authors**: Takes the more complete list
- **Abstract, DOI, PMID, arXiv ID, Journal details, URLs**: Filled if missing
- **Keywords & Sources**: Merged from all duplicates
- **Citations**: Takes the highest count

## Example Scenarios

**Scenario 1: PubMed vs Scopus**
- Scopus: "AI in Medicine" (2024, DOI, 10 citations)
- PubMed: "AI in Medicine" (2024, PMID, abstract)
- **Result**: PubMed primary → PMID + DOI + abstract + 10 citations merged

**Scenario 2: Different dates**
- arXiv: "Neural Networks" (2024-01-15)
- IEEE: "Neural Networks" (2024-03-20, DOI)
- **Result**: IEEE primary (more recent) → DOI + arXiv ID merged

**Scenario 3: PubMed trumps date**
- arXiv: "Deep Learning" (2024) ❌
- PubMed: "Deep Learning" (2023) ✓ PRIMARY
- **Result**: PubMed primary (PubMed priority) → arXiv data merged

**Script `04_deduplicate_extra.py`**
For advanced users, an additional deduplication script `04_deduplicate_extra.py` is provided. This can be used to deduplicate CSV or BibTeX files using the same logic as above, especially useful if multiple files were appended together.

Usage:
```bash
python 04_deduplicate_extra.py path/to/papers.csv
python 04_deduplicate_extra.py path/to/references.bib
```
It can also be used to check missed duplicates, it will identify them, report them, and merge accordingly.