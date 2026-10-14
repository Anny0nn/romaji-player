"""Research compatibility import of the shared singing-word alignment implementation."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa/vendor")]
from singing_timing import word_alignment

__all__ = ["word_alignment"]
