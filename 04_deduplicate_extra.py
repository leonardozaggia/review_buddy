#!/usr/bin/env python3
"""
EXTRA DEDUPLICATION!
You dont need this unless you appended multiple .bib or .csv files -> advanced use case.
You can also use this script if you do not trust the inbuilt deduplication logic.

This script can:
1. Remove duplicate papers from CSV files (by URL or DOI)
2. Remove duplicate papers from BibTeX files (by title, DOI, or PMID)
3. Always keep PubMed entries (if available) and prefer the most recent entries.

Usage:
    python fix_duplicates.py path/to/papers.csv        # Deduplicate CSV file
    python fix_duplicates.py path/to/references.bib    # Deduplicate BibTeX file
"""

import pandas as pd
import sys
import re
from pathlib import Path
import shutil
from datetime import datetime
from typing import List, Dict, Tuple, Set


def parse_bibtex_file(filepath: Path) -> List[Dict]:
    """
    Parse a BibTeX file into a list of entry dictionaries.
    
    Args:
        filepath: Path to BibTeX file
    
    Returns:
        List of dictionaries, each representing a BibTeX entry
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split into entries (everything between @ and the closing brace)
    entries = []
    entry_pattern = r'@(\w+)\{([^,]+),(.*?)\n\}'
    
    for match in re.finditer(entry_pattern, content, re.DOTALL):
        entry_type = match.group(1)
        cite_key = match.group(2).strip()
        fields_text = match.group(3)
        
        # Parse fields
        fields = {'entry_type': entry_type, 'cite_key': cite_key}
        field_pattern = r'(\w+)\s*=\s*\{([^}]*)\}'
        
        for field_match in re.finditer(field_pattern, fields_text):
            field_name = field_match.group(1).strip().lower()
            field_value = field_match.group(2).strip()
            fields[field_name] = field_value
        
        entries.append(fields)
    
    return entries


def bibtex_entry_to_string(entry: Dict) -> str:
    """Convert a BibTeX entry dictionary back to string format."""
    lines = [f"@{entry['entry_type']}{{{entry['cite_key']},"]
    
    # Add all fields except metadata
    for key, value in entry.items():
        if key not in ['entry_type', 'cite_key']:
            lines.append(f"  {key} = {{{value}}},")
    
    lines.append("}")
    return '\n'.join(lines)


def should_replace_bibtex_entry(existing: Dict, new: Dict) -> bool:
    """
    Determine if new entry should replace existing entry (same logic as paper_searcher.py).
    
    Priority logic:
    1. PubMed entries are preferred (check if PMID exists)
    2. If PubMed status is the same, prefer more recent publication (year field)
    3. If dates are equal/unknown, keep existing
    
    Args:
        existing: Currently stored entry
        new: New entry being compared
    
    Returns:
        True if new entry should replace existing, False otherwise
    """
    existing_is_pubmed = bool(existing.get('pmid'))
    new_is_pubmed = bool(new.get('pmid'))
    
    # Priority 1: Prefer PubMed
    if new_is_pubmed and not existing_is_pubmed:
        return True
    if existing_is_pubmed and not new_is_pubmed:
        return False
    
    # Priority 2: Prefer more recent publication
    existing_year = existing.get('year')
    new_year = new.get('year')
    
    if new_year and existing_year:
        try:
            return int(new_year) > int(existing_year)
        except (ValueError, TypeError):
            pass
    
    # If only one has a year, prefer the one with a year
    if new_year and not existing_year:
        return True
    if existing_year and not new_year:
        return False
    
    # Default: keep existing
    return False


def identify_bibtex_duplicates(entries: List[Dict]) -> Tuple[List[int], List[Tuple[int, int, str]]]:
    """
    Identify duplicate entries in BibTeX list using the same logic as Paper.__eq__().
    
    Priority matching (same as models.py Paper class):
    1. If both have DOI, compare DOIs (case-insensitive)
    2. Otherwise, compare titles (case-insensitive, stripped)
    
    When duplicates are found, keeps the "better" one based on:
    1. PubMed entries preferred (have PMID)
    2. More recent publication date preferred
    
    Args:
        entries: List of BibTeX entry dictionaries
    
    Returns:
        Tuple of (indices_to_keep, list of (idx1, idx2, reason) tuples)
    """
    duplicates = []
    seen_dois = {}  # DOI -> index
    seen_titles = {}  # normalized title -> index
    to_remove = set()
    
    for i, entry in enumerate(entries):
        # Normalize identifiers (same as Paper class)
        title = entry.get('title', '').lower().strip()
        doi = entry.get('doi', '').lower().strip() if entry.get('doi') else None
        
        # Priority 1: Check DOI match (highest priority, same as Paper.__eq__)
        if doi and doi in seen_dois:
            existing_idx = seen_dois[doi]
            existing_entry = entries[existing_idx]
            
            # Decide which to keep (same logic as paper_searcher.py)
            if should_replace_bibtex_entry(existing_entry, entry):
                # Replace: keep new, remove old
                duplicates.append((i, existing_idx, f"Same DOI: {doi} (kept newer/PubMed)"))
                to_remove.add(existing_idx)
                seen_dois[doi] = i
                if title:
                    seen_titles[title] = i
            else:
                # Keep existing, remove new
                duplicates.append((existing_idx, i, f"Same DOI: {doi}"))
                to_remove.add(i)
            continue
        
        # Priority 2: Check title match (same as Paper.__eq__)
        if title and title in seen_titles:
            existing_idx = seen_titles[title]
            existing_entry = entries[existing_idx]
            
            # Decide which to keep
            if should_replace_bibtex_entry(existing_entry, entry):
                # Replace: keep new, remove old
                duplicates.append((i, existing_idx, f"Same title (kept newer/PubMed)"))
                to_remove.add(existing_idx)
                seen_titles[title] = i
                if doi:
                    seen_dois[doi] = i
            else:
                # Keep existing, remove new
                duplicates.append((existing_idx, i, f"Same title: {title[:60]}..."))
                to_remove.add(i)
            continue
        
        # Record this entry
        if doi:
            seen_dois[doi] = i
        if title:
            seen_titles[title] = i
    
    # Indices to keep
    indices_to_keep = [i for i in range(len(entries)) if i not in to_remove]
    
    return indices_to_keep, duplicates


def deduplicate_bibtex(filepath: Path, output_path: Path = None) -> Dict:
    """
    Deduplicate a BibTeX file.
    
    Args:
        filepath: Path to input BibTeX file
        output_path: Path to output file (defaults to input_deduped.bib)
    
    Returns:
        Dictionary with statistics
    """
    print("=" * 80)
    print(f"DEDUPLICATING BIBTEX FILE: {filepath}")
    print("=" * 80)
    
    # Parse BibTeX file
    print(f"\n📖 Parsing BibTeX file...")
    entries = parse_bibtex_file(filepath)
    print(f"   Found {len(entries)} entries")
    
    # Identify duplicates
    print(f"\n🔍 Identifying duplicates...")
    indices_to_keep, duplicates = identify_bibtex_duplicates(entries)
    
    print(f"\n📊 DUPLICATE ANALYSIS:")
    print(f"   Total entries:        {len(entries)}")
    print(f"   Unique entries:       {len(indices_to_keep)}")
    print(f"   Duplicate entries:    {len(duplicates)}")
    
    if duplicates:
        print(f"\n🔄 IDENTIFIED DUPLICATES:")
        print("-" * 80)
        
        # Group duplicates by the entry they duplicate
        duplicate_groups = {}
        for original_idx, duplicate_idx, reason in duplicates:
            if original_idx not in duplicate_groups:
                duplicate_groups[original_idx] = []
            duplicate_groups[original_idx].append((duplicate_idx, reason))
        
        for original_idx, dups in sorted(duplicate_groups.items()):
            original = entries[original_idx]
            original_title = original.get('title', 'No title')[:70]
            print(f"\n   Original entry #{original_idx + 1}:")
            print(f"      Title: {original_title}...")
            print(f"      Cite key: {original.get('cite_key', 'N/A')}")
            if 'doi' in original:
                print(f"      DOI: {original['doi']}")
            
            print(f"   Duplicates ({len(dups)}):")
            for dup_idx, reason in dups:
                dup = entries[dup_idx]
                dup_title = dup.get('title', 'No title')[:60]
                print(f"      • Entry #{dup_idx + 1}: {dup_title}...")
                print(f"        Cite key: {dup.get('cite_key', 'N/A')}")
                print(f"        Reason: {reason}")
    
    # Backup original
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = filepath.parent / f"{filepath.stem}_backup_{timestamp}{filepath.suffix}"
    shutil.copy(filepath, backup_path)
    print(f"\n✓ Backed up original to: {backup_path}")
    
    # Write deduplicated entries (overwrite original)
    kept_entries = [entries[i] for i in indices_to_keep]
    with open(filepath, 'w', encoding='utf-8') as f:
        for entry in kept_entries:
            f.write(bibtex_entry_to_string(entry) + "\n\n")
    
    print(f"\n✓ Saved deduplicated file to: {filepath} (original overwritten)")
    print(f"   Removed {len(duplicates)} duplicate entries")
    
    return {
        'total': len(entries),
        'unique': len(indices_to_keep),
        'duplicates': len(duplicates),
        'duplicate_details': duplicates
    }


def should_replace_csv_row(existing: pd.Series, new: pd.Series) -> bool:
    """
    Determine if new row should replace existing row (same logic as paper_searcher.py).
    
    Priority logic:
    1. PubMed papers are preferred (check Sources column for "PubMed")
    2. If PubMed status is the same, prefer more recent publication (Year field)
    3. If dates are equal/unknown, keep existing
    
    Args:
        existing: Currently stored row
        new: New row being compared
    
    Returns:
        True if new row should replace existing, False otherwise
    """
    # Check if entries have "PubMed" in Sources
    existing_sources = str(existing.get('Sources', '')).lower()
    new_sources = str(new.get('Sources', '')).lower()
    
    existing_is_pubmed = 'pubmed' in existing_sources
    new_is_pubmed = 'pubmed' in new_sources
    
    # Priority 1: Prefer PubMed
    if new_is_pubmed and not existing_is_pubmed:
        return True
    if existing_is_pubmed and not new_is_pubmed:
        return False
    
    # Priority 2: Prefer more recent publication
    existing_year = existing.get('Year')
    new_year = new.get('Year')
    
    if pd.notna(new_year) and pd.notna(existing_year):
        try:
            return int(new_year) > int(existing_year)
        except (ValueError, TypeError):
            pass
    
    # If only one has a year, prefer the one with a year
    if pd.notna(new_year) and pd.isna(existing_year):
        return True
    if pd.isna(new_year) and pd.notna(existing_year):
        return False
    
    # Default: keep existing
    return False


def deduplicate_csv(filepath: Path, output_path: Path = None) -> Dict:
    """
    Deduplicate a CSV file using the same logic as Paper.__eq__() and paper_searcher.py.
    
    Priority matching (same as models.py Paper class):
    1. If both have DOI, compare DOIs (case-insensitive)
    2. Otherwise, compare titles (case-insensitive, stripped)
    
    When duplicates found, keeps the "better" one (same as paper_searcher.py):
    1. PubMed papers preferred (check Sources column)
    2. More recent publication date preferred (Year column)
    3. If equal/unknown, keep first occurrence
    
    Args:
        filepath: Path to input CSV file
        output_path: Ignored - always overwrites original
    
    Returns:
        Dictionary with statistics
    """
    print("=" * 80)
    print(f"DEDUPLICATING CSV FILE: {filepath}")
    print("=" * 80)
    
    # Load CSV
    print(f"\n📖 Reading CSV file...")
    df = pd.read_csv(filepath)
    print(f"   Found {len(df)} rows")
    
    # Check for required columns
    has_doi = 'DOI' in df.columns
    has_title = 'Title' in df.columns
    
    if not has_doi and not has_title:
        print("\n⚠️  Warning: No DOI or Title columns found")
        print("   Cannot deduplicate without identifiers!")
        return {'total': len(df), 'unique': len(df), 'duplicates': 0}
    
    dedup_method = "DOI (primary) and Title (fallback)" if has_doi else "Title only"
    print(f"   Deduplication method: {dedup_method}")
    print(f"   (Same logic as Paper.__eq__() in models.py)")
    
    # Find duplicates using Paper class logic + PubMed/date priority
    print(f"\n🔍 Identifying duplicates...")
    
    duplicates_info = []
    seen_dois = {}  # DOI -> index
    seen_titles = {}  # normalized title -> index
    duplicate_indices = []
    
    for idx, row in df.iterrows():
        # Normalize identifiers (same as Paper class)
        title = str(row.get('Title', '')).strip().lower() if has_title else None
        doi = str(row.get('DOI', '')).strip().lower() if has_doi and pd.notna(row.get('DOI')) else None
        
        # Skip empty rows
        if not title and not doi:
            continue
        
        # Priority 1: Check DOI match (same as Paper.__eq__)
        if doi and doi != 'nan' and doi in seen_dois:
            existing_idx = seen_dois[doi]
            existing_row = df.iloc[existing_idx]
            
            # Decide which to keep (same logic as paper_searcher.py)
            if should_replace_csv_row(existing_row, row):
                # Replace: keep new, remove old
                duplicate_indices.append(existing_idx)
                duplicates_info.append({
                    'original_idx': idx,
                    'duplicate_idx': existing_idx,
                    'title': row.get('Title', 'No title')[:70] if has_title else 'N/A',
                    'reason': f'Same DOI: {doi} (kept newer/PubMed)'
                })
                seen_dois[doi] = idx
                if title and title != 'nan':
                    seen_titles[title] = idx
            else:
                # Keep existing, remove new
                duplicate_indices.append(idx)
                duplicates_info.append({
                    'original_idx': existing_idx,
                    'duplicate_idx': idx,
                    'title': row.get('Title', 'No title')[:70] if has_title else 'N/A',
                    'reason': f'Same DOI: {doi}'
                })
            continue
        
        # Priority 2: Check title match (same as Paper.__eq__)
        if title and title != 'nan' and title in seen_titles:
            existing_idx = seen_titles[title]
            existing_row = df.iloc[existing_idx]
            
            # Decide which to keep
            if should_replace_csv_row(existing_row, row):
                # Replace: keep new, remove old
                duplicate_indices.append(existing_idx)
                duplicates_info.append({
                    'original_idx': idx,
                    'duplicate_idx': existing_idx,
                    'title': row.get('Title', 'No title')[:70] if has_title else 'N/A',
                    'reason': f'Same title (kept newer/PubMed)'
                })
                seen_titles[title] = idx
                if doi and doi != 'nan':
                    seen_dois[doi] = idx
            else:
                # Keep existing, remove new
                duplicate_indices.append(idx)
                duplicates_info.append({
                    'original_idx': existing_idx,
                    'duplicate_idx': idx,
                    'title': row.get('Title', 'No title')[:70] if has_title else 'N/A',
                    'reason': f'Same title'
                })
            continue
        
        # Record this entry
        if doi and doi != 'nan':
            seen_dois[doi] = idx
        if title and title != 'nan':
            seen_titles[title] = idx
    
    # Remove duplicates
    df_deduped = df.drop(index=duplicate_indices)
    
    print(f"\n📊 DUPLICATE ANALYSIS:")
    print(f"   Total rows:           {len(df)}")
    print(f"   Unique rows:          {len(df_deduped)}")
    print(f"   Duplicate rows:       {len(duplicate_indices)}")
    
    if duplicates_info:
        print(f"\n🔄 IDENTIFIED DUPLICATES:")
        print("-" * 80)
        
        # Group by original
        groups = {}
        for dup in duplicates_info:
            orig_idx = dup['original_idx']
            if orig_idx not in groups:
                groups[orig_idx] = []
            groups[orig_idx].append(dup)
        
        for orig_idx, dups in sorted(groups.items())[:10]:  # Show first 10
            original = df.iloc[orig_idx]
            print(f"\n   Original row #{orig_idx + 2}:")  # +2 for header and 0-indexing
            if 'Title' in df.columns:
                print(f"      Title: {original.get('Title', 'N/A')[:70]}...")
            if 'DOI' in df.columns and pd.notna(original.get('DOI')):
                print(f"      DOI: {original.get('DOI')}")
            if 'URL' in df.columns and pd.notna(original.get('URL')):
                print(f"      URL: {str(original.get('URL'))[:70]}...")
            
            print(f"   Duplicates ({len(dups)}):")
            for dup in dups[:5]:  # Show first 5 duplicates
                print(f"      • Row #{dup['duplicate_idx'] + 2}: {dup['title']}...")
                print(f"        Reason: {dup['reason']}")
        
        if len(groups) > 10:
            print(f"\n   ... and {len(groups) - 10} more duplicate groups")
    
    # Backup original
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = filepath.parent / f"{filepath.stem}_backup_{timestamp}{filepath.suffix}"
    shutil.copy(filepath, backup_path)
    print(f"\n✓ Backed up original to: {backup_path}")
    
    # Save deduplicated file (overwrite original)
    df_deduped.to_csv(filepath, index=False)
    print(f"\n✓ Saved deduplicated file to: {filepath} (original overwritten)")
    print(f"   Removed {len(duplicate_indices)} duplicate rows")
    
    return {
        'total': len(df),
        'unique': len(df_deduped),
        'duplicates': len(duplicate_indices),
        'duplicate_details': duplicates_info
    }


# The previous AI-filtering-specific helper was removed to keep this module
# general-purpose. When run without arguments the script will now interactively
# list CSV/BIB files in the `results/` folder and ask which one(s) to deduplicate.


def main():
    """Main entry point - route to appropriate deduplication function."""
    # Require exactly one path argument (script is now single-file only)
    if len(sys.argv) != 2:
        print("❌ Error: Please provide a single .csv or .bib file to deduplicate.")
        print("\nUsage:")
        print("  python 04_deduplicate_extra.py path/to/file.csv")
        print("  python 04_deduplicate_extra.py path/to/file.bib")
        sys.exit(1)

    filepath = Path(sys.argv[1])
    if not filepath.exists():
        print(f"❌ Error: File not found: {filepath}")
        sys.exit(1)

    # Determine file type and deduplicate
    if filepath.suffix.lower() == '.csv':
        stats = deduplicate_csv(filepath)
    elif filepath.suffix.lower() in ['.bib', '.bibtex']:
        stats = deduplicate_bibtex(filepath)
    else:
        print(f"❌ Error: Unsupported file type: {filepath.suffix}")
        print("   Supported types: .csv, .bib")
        sys.exit(1)

    # Final summary
    print("\n" + "=" * 80)
    print("DEDUPLICATION COMPLETE!")
    print("=" * 80)
    print(f"\n✅ Summary:")
    print(f"   Total entries:    {stats['total']}")
    print(f"   Unique entries:   {stats['unique']}")
    print(f"   Duplicates found: {stats['duplicates']}")
    print(f"   Retention rate:   {stats['unique']/stats['total']*100:.1f}%")


if __name__ == "__main__":
    main()
