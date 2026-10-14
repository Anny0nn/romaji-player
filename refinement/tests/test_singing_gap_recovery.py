"""Independent singing support fills gaps without rewriting retained highlights."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from singing_timing import recover_singing_gaps


def unit(index, start, end, **extra):
    return {
        "raw_span": [index * 3, (index + 1) * 3],
        "start_ms": start,
        "end_ms": end,
        **extra,
    }


def inputs():
    baseline = [
        unit(0, 0, 100, text="あ"),
        unit(1, -1, -1, text="い"),
        unit(2, 450, 600, text="う"),
    ]
    trial = {
        "units": [unit(0, 10, 120), unit(1, -1, -1), unit(2, 470, 620)],
        "raw_units": [
            unit(0, 10, 120, reason="retained"),
            unit(
                1,
                200,
                350,
                reason="token_agreement",
                agreement=0.95,
                mean_similarity=0.4,
            ),
            unit(2, 470, 620, reason="retained"),
        ],
    }
    independent = [
        unit(0, 20, 125, mean_probability=0.7),
        unit(1, 210, 355, mean_probability=0.8),
        unit(2, 480, 625, mean_probability=0.7),
    ]
    return baseline, trial, independent


def test_missing_word_recovery_preserves_all_retained_intervals_and_text():
    baseline, trial, evidence = inputs()
    result = recover_singing_gaps(baseline, trial, evidence, 1000, 3)
    assert result[0] == baseline[0] and result[2] == baseline[2]
    assert result[1] == unit(1, 200, 350, text="い")
    assert baseline[1]["start_ms"] == -1


@pytest.mark.parametrize("value", [0.44, math.nan, math.inf, 1.1])
def test_low_or_nonfinite_independent_support_is_not_coverage(value):
    baseline, trial, evidence = inputs()
    evidence[1]["mean_probability"] = value
    assert recover_singing_gaps(baseline, trial, evidence, 1000, 3) == baseline


@pytest.mark.parametrize(
    "change",
    [
        {"start_ms": 80},
        {"end_ms": 500},
        {"end_ms": 260},
        {"agreement": 0.89},
        {"mean_similarity": 0},
        {"reason": "incomplete"},
        {"start_ms": 400, "end_ms": 550},
    ],
)
def test_collisions_bad_tifa_paths_or_disagreeing_endpoints_stay_missing(change):
    baseline, trial, evidence = inputs()
    trial["raw_units"][1].update(change)
    assert recover_singing_gaps(baseline, trial, evidence, 1000, 3) == baseline


def test_wrong_phrase_and_unsupported_words_count_in_context_denominator():
    baseline, trial, evidence = inputs()
    evidence[0]["mean_probability"] = 0.01
    evidence[2]["mean_probability"] = 0.01
    assert recover_singing_gaps(baseline, trial, evidence, 1000, 3) == baseline
    baseline, trial, evidence = inputs()
    assert recover_singing_gaps(baseline, trial, evidence, 1000, 8) == baseline


def test_source_word_order_cannot_be_changed_by_a_timing_trial():
    baseline, trial, evidence = inputs()
    evidence[1]["raw_span"] = [9, 12]
    with pytest.raises(ValueError, match="source anchors"):
        recover_singing_gaps(baseline, trial, evidence, 1000, 3)
