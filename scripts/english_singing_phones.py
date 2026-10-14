"""Compatibility export of the bundled pronunciation hypotheses for offline tools."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "bundled_english_singing_phones",
    Path(__file__).resolve().parents[1] / "refinement/english_singing_phones.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
japanese_hypothesis = module.japanese_hypothesis
