"""
Progress tracking utilities for paper searching.

Provides consistent progress indicators across all searchers.
"""

import sys
from typing import Optional

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


class ProgressTracker:
    """
    Unified progress tracker that uses tqdm if available, falls back to simple logging.
    """
    
    def __init__(self, total: int, desc: str, disable: bool = False):
        """
        Initialize progress tracker.
        
        Args:
            total: Total number of items
            desc: Description of the task
            disable: Whether to disable progress output
        """
        self.total = total
        self.desc = desc
        self.disable = disable
        self.current = 0
        self.pbar = None
        
        if not disable:
            if TQDM_AVAILABLE:
                # Use tqdm for nice progress bar
                self.pbar = tqdm(
                    total=total,
                    desc=desc,
                    unit="papers",
                    file=sys.stdout,
                    ncols=80
                )
            else:
                # Fallback to simple print
                print(f"{desc}: 0/{total} papers", end='\r', flush=True)
    
    def update(self, n: int = 1):
        """
        Update progress by n items.
        
        Args:
            n: Number of items to increment by
        """
        if self.disable:
            return
        
        self.current += n
        
        if self.pbar is not None:
            self.pbar.update(n)
        else:
            # Simple progress update
            print(f"{self.desc}: {self.current}/{self.total} papers", end='\r', flush=True)
    
    def set_description(self, desc: str):
        """
        Update the progress description.
        
        Args:
            desc: New description
        """
        self.desc = desc
        if self.pbar is not None:
            self.pbar.set_description(desc)
    
    def close(self):
        """Close the progress tracker."""
        if self.pbar is not None:
            self.pbar.close()
        elif not self.disable:
            print()  # New line after progress
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def create_progress_tracker(total: int, desc: str, disable: bool = False) -> ProgressTracker:
    """
    Factory function to create a progress tracker.
    
    Args:
        total: Total number of items
        desc: Description of the task
        disable: Whether to disable progress output
    
    Returns:
        ProgressTracker instance
    """
    return ProgressTracker(total, desc, disable)
