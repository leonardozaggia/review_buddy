"""
Test the new configuration-based filtering approach.
"""

from src.abstract_filter import AbstractFilter
from src.models import Paper

# Create test papers
papers = [
    Paper(
        title="EEG Analysis in Pediatric Patients",
        abstract="We studied EEG patterns in children and adolescents with ADHD."
    ),
    Paper(
        title="BCI System for Motor Rehabilitation",
        abstract="A brain-computer interface for post-stroke rehabilitation."
    ),
    Paper(
        title="Artifact Removal in EEG",
        abstract="Novel methods for removing ocular artifacts from EEG recordings."
    ),
]

# Initialize filter
filter_tool = AbstractFilter()

# Test 1: Add domain-specific BCI filter
print("Test 1: Adding BCI filter")
bci_keywords = [
    'brain-computer interface', 'bci', 'brain-machine interface',
    'motor rehabilitation'  # Custom addition
]
filter_tool.add_custom_filter('bci', bci_keywords)
print(f"Created 'bci' filter with {len(bci_keywords)} keywords")

# Test 2: Add custom filter for pediatric studies
print("\nTest 2: Adding custom filter for pediatric studies")
filter_tool.add_custom_filter('pediatric', ['children', 'adolescent', 'pediatric'])
print("Created 'pediatric' filter")

# Test 3: Add another custom filter for artifact papers
print("\nTest 3: Adding custom filter for artifact papers")
filter_tool.add_custom_filter('artifacts', ['artifact removal', 'artifact rejection', 'ocular artifact'])
print("Created 'artifacts' filter")

# Apply filters
print("\nApplying filters...")
results = filter_tool.apply_all_filters(
    papers,
    filters_to_apply=['bci', 'pediatric', 'artifacts']
)

# Show results
print(f"\nResults:")
print(f"  Kept: {len(results['kept'])} papers")
print(f"  Filtered: {sum(len(p) for p in results['filtered'].values())} papers")
print(f"\nBreakdown:")
for filter_name, filtered_papers in results['filtered'].items():
    if filtered_papers:
        print(f"  {filter_name}: {len(filtered_papers)} papers")
        for paper in filtered_papers:
            print(f"    - {paper.title}")

print(f"\nKept papers:")
for paper in results['kept']:
    print(f"  - {paper.title}")

print("\n✅ Test completed successfully!")

