# Complete Workflow Example: Abstract Filtering

This example demonstrates the full workflow from search to filtered papers using the new user-friendly configuration approach.

## Scenario

You're conducting a systematic review on **EEG-based cognitive assessment** but want to exclude:
- Papers without abstracts
- Non-English papers
- Epilepsy-related studies
- Brain-computer interface research
- Animal studies
- Review papers
- **Custom**: fMRI-only studies (you want EEG-based research)
- **Custom**: Pediatric studies (you want adult populations)

## Step 1: Fetch Papers

```bash
python 01_fetch_metadata.py
```

**Result**: `results/references.bib` with 250 papers from multiple sources

## Step 2: Configure Filters

Edit `02_abstract_filter.py`:

```python
# ============================================================================
# CONFIGURATION - CUSTOMIZE YOUR FILTERS HERE
# ============================================================================

# Enable/disable filters
FILTERS_ENABLED = {
    'no_abstract': True,        # Always recommended
    'non_english': True,        # Requires langdetect
    'epilepsy': True,          # Exclude epilepsy research
    'bci': True,               # Exclude BCI research
    'non_human': True,         # Exclude animal studies
    'non_empirical': True,     # Exclude reviews
    'fmri_only': True,             # Custom: exclude fMRI-only studies
    'pediatric': True,             # Custom: exclude pediatric studies
}

# Define keyword-based filters
# Add, remove, or modify filters as needed for your research area
KEYWORD_FILTERS = {
    # Built-in filters (you can add keywords to these)
    'epilepsy': [
        'epileptic spike', 'epileptic spikes', 'interictal spike', 'ictal spike',
        'spike detection', 'epileptiform', 'seizure spike', 'spike-wave',
        'paroxysmal spike', 'sharp wave', 'spike discharge',
        'temporal lobe epilepsy',  # Add more specific terms
        'TLE',
    ],
    
    'bci': [
        'brain-computer interface', 'brain computer interface', 'bci',
        'brain-machine interface', 'brain machine interface', 'bmi',
        'neural interface', 'thought control', 'mind control',
        'p300 speller', 'motor imagery bci', 'steady-state visual'
    ],
    
    'non_human': [
        # Animals
        'rat', 'rats', 'mouse', 'mice', 'murine', 'rodent', 'rodents',
        'monkey', 'monkeys', 'primate', 'primates', 'macaque', 'macaques',
        'pig', 'pigs', 'porcine', 'sheep', 'ovine', 'rabbit', 'rabbits',
        'cat', 'cats', 'feline', 'dog', 'dogs', 'canine',
        'zebrafish', 'drosophila', 'c. elegans', 'caenorhabditis',
        # Non-human contexts
        'in vitro', 'in-vitro', 'cell culture', 'cell line', 'cultured cells',
        'animal model', 'animal study', 'animal experiment',
        'non-human', 'non human', 'nonhuman',
        'non-human primate',  # Add more specific terms
    ],
    
    'non_empirical': [
        'systematic review', 'meta-analysis', 'meta analysis', 'literature review',
        'scoping review', 'narrative review', 'review article', 'state of the art',
        'state-of-the-art review', 'survey paper', 'comprehensive review'
    ],
    
    # Your custom filters
    'fmri_only': [
        'fMRI',
        'functional MRI',
        'functional magnetic resonance',
        'BOLD signal',
        'blood oxygen level dependent',
    ],
    
    'pediatric': [
        'children',
        'child',
        'pediatric',
        'paediatric',
        'infant',
        'toddler',
        'adolescent',
        'school-age',
    ],
}
```

## Step 3: Run Filtering

```bash
python 02_abstract_filter.py
```

**Output**:

```
======================================================================
ABSTRACT-BASED PAPER FILTERING
======================================================================

Loading papers from results\references.bib...
Loaded 250 papers
Registered filter 'epilepsy' with 13 keywords
Registered filter 'bci' with 11 keywords
Registered filter 'non_human' with 31 keywords
Registered filter 'non_empirical' with 11 keywords
Registered filter 'fmri_only' with 5 keywords
Registered filter 'pediatric' with 8 keywords

Filters to apply: no_abstract, non_english, epilepsy, bci, non_human, non_empirical, fmri_only, pediatric

======================================================================
APPLYING FILTERS
======================================================================

Starting with 250 papers
No abstract filter: 238 papers kept, 12 filtered out
Non-English filter: 233 papers kept, 5 filtered out
Epilepsy filter: 215 papers kept, 18 filtered out
BCI filter: 204 papers kept, 11 filtered out
Non-human filter: 156 papers kept, 48 filtered out
Non-empirical filter: 142 papers kept, 14 filtered out
Custom: fmri_only filter: 119 papers kept, 23 filtered out
Custom: pediatric filter: 104 papers kept, 15 filtered out

Final result: 104 papers kept, 146 papers filtered out

======================================================================
FILTERING SUMMARY
======================================================================
Initial papers:        250
Papers kept:           104
Papers filtered out:   146
Retention rate:        41.6%

Breakdown by filter:
  - no_abstract       :   12 papers
  - non_english       :    5 papers
  - epilepsy          :   18 papers
  - bci               :   11 papers
  - non_human         :   48 papers
  - non_empirical     :   14 papers
  - fmri_only         :   23 papers
  - pediatric         :   15 papers

======================================================================
SAVING RESULTS
======================================================================
Saved 104 kept papers to results\papers_filtered.csv
Saved 104 kept papers to results\references_filtered.bib
Saved 12 no_abstract papers to results\filtered_out\no_abstract.csv
Saved 5 non_english papers to results\filtered_out\non_english.csv
Saved 18 epilepsy papers to results\filtered_out\epilepsy.csv
Saved 11 bci papers to results\filtered_out\bci.csv
Saved 48 non_human papers to results\filtered_out\non_human.csv
Saved 14 non_empirical papers to results\filtered_out\non_empirical.csv
Saved 23 fmri_only papers to results\filtered_out\fmri_only.csv
Saved 15 pediatric papers to results\filtered_out\pediatric.csv

======================================================================
FILTERING COMPLETE!
======================================================================

Filtered results saved to:
  - results\papers_filtered.csv
  - results\references_filtered.bib

Filtered out papers saved to: results\filtered_out\

Next step: Run 03_download_papers.py to download PDFs
```

## Step 4: Review Filtered Papers (Optional)

Check the filtered-out papers to verify nothing important was removed:

```bash
# Check papers filtered by your custom fMRI filter
type results\filtered_out\fmri_only.csv

# Check pediatric papers that were excluded
type results\filtered_out\pediatric.csv
```

If you find false positives (good papers incorrectly filtered), adjust your keywords and re-run.

## Step 5: Download PDFs

```bash
python 03_download_papers.py
```

Now you'll download only 104 papers instead of 250!

### AI-powered filtering (cluster note)

The repository also includes an AI-powered filter (`02_abstract_filter_AI.py`) which uses a local LLM (we use Ollama in our examples). Large models can be resource intensive — GPU nodes or a short HPC job are recommended for reasonable throughput. See `run_filter_hpc.sh` for a ready-made SLURM job script; minimally you should:

- Ensure Ollama is installed and a model is pulled (e.g., `ollama pull llama3.1`).
- Run on a node with sufficient RAM/CPU or a GPU if using a larger model.
- Use the provided `run_filter_hpc.sh` (or `salloc`/`sbatch`) to start Ollama, run the AI filter, and stop the server cleanly.

This step is optional — the keyword-based `02_abstract_filter.py` works without these dependencies.

## Result Structure

```
results/
├── papers.csv                      # Original 250 papers
├── references.bib                  # Original bibliography
├── papers_filtered.csv             # ✅ 104 filtered papers
├── references_filtered.bib         # ✅ Bibliography of filtered papers
└── filtered_out/                   # Papers removed by each filter
    ├── no_abstract.csv             # 12 papers
    ├── non_english.csv             # 5 papers
    ├── epilepsy.csv                # 18 papers
    ├── bci.csv                     # 11 papers
    ├── non_human.csv               # 48 papers
    ├── non_empirical.csv           # 14 papers
    ├── fmri_only.csv                   # 23 papers (custom)
    └── pediatric.csv                   # 15 papers (custom)
```

## Iterating on Filters

If you review `fmri_only.csv` and find that some papers use both EEG and fMRI (which you want to keep), refine your filter:

```python
KEYWORD_FILTERS = {
    # ... other filters ...
    
    'fmri_only': [
        # Only filter papers that mention ONLY fMRI, not combined studies
        'fMRI only',
        'exclusively fMRI',
        'solely fMRI',
        # Remove general terms that catch combined studies
        # 'functional magnetic resonance',  # Too broad - removed
        # 'BOLD signal',  # Too broad - removed
    ],
}
```

Then re-run:
```bash
python 02_abstract_filter.py
```

The script will re-filter from the original 250 papers with your updated criteria.

## Tips for Custom Filters

### Good Keywords
- **Specific phrases**: "fMRI only", "exclusively fMRI"
- **Technical terms**: "BOLD signal", "blood oxygen level dependent"
- **Context-specific**: "pediatric population", "child participants"

### Keywords to Avoid
- **Too broad**: "brain", "imaging", "signal" (match too many papers)
- **Ambiguous**: "young" (could mean young adults), "small" (sample size?)
- **Common words**: "study", "research", "analysis"

### Testing Your Filters
1. Start with conservative (specific) keywords
2. Check `filtered_out/your_filter.csv` to see what was removed
3. Add broader keywords if needed
4. Review again and iterate

This gives you fine-grained control over what papers to include in your systematic review!
