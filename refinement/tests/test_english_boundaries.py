"""Recognition confidence cannot invent or overrule observed word boundaries."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from english_boundaries import (
    lexical_support,
    observed_lexemes,
    paired_boundary,
    recover_verified_boundaries,
)


def test_confidence_statistics_are_typed_and_require_complete_phone_support():
    assert not lexical_support({"probability": 0.52})
    phone = {
        "kind": "singing-ctc",
        "probability": 0.52,
        "minimum_phone_probability": 0.48,
        "greedy_agreement": 1.0,
    }
    assert lexical_support(phone)
    for change in (
        {"minimum_phone_probability": 0.2},
        {"minimum_phone_probability": True},
        {"minimum_phone_probability": 0.8},
        {"greedy_agreement": 0.7},
        {"probability": float("nan")},
        {"kind": "unknown"},
    ):
        assert not lexical_support({**phone, **change})


def fixture():
    targets = [
        {"raw_span": [i * 2, i * 2 + 1], "text": text, "expected_text": text}
        for i, text in enumerate(["the", "quiet", "light"])
    ]
    baseline = [
        {"raw_span": t["raw_span"], "start_ms": -1, "end_ms": -1} for t in targets
    ]
    tifa = [
        {
            **t,
            "start_ms": 100 + i * 300,
            "end_ms": 350 + i * 300,
            "reason": "retained",
            "agreement": 1.0,
            "mean_similarity": 0.4,
        }
        for i, t in enumerate(targets)
    ]
    singing = [
        {
            **t,
            "start_ms": t["start_ms"] + 20,
            "end_ms": t["end_ms"] - 10,
            "complete": True,
        }
        for t in tifa
    ]
    views = [
        [
            {
                "raw_span": t["raw_span"],
                "probability": 0.9,
                "source_match": True,
                "matched_words": 3,
                "observed_midpoint_ms": (t["start_ms"] + t["end_ms"]) / 2,
            }
            for t in tifa
        ]
        for _ in range(2)
    ]
    return baseline, targets, tifa, singing, views


def test_lexical_proof_is_separate_from_asr_boundary_accuracy():
    baseline, targets, tifa, singing, views = fixture()
    views[0][0].update(observed_midpoint_ms=225)
    views[1][0].update(observed_midpoint_ms=230)
    out = recover_verified_boundaries(baseline, targets, tifa, singing, views, 1200)
    assert [(u["start_ms"], u["end_ms"]) for u in out] == [
        (100, 350),
        (400, 650),
        (700, 950),
    ]
    assert "start_ms" not in views[0][0]


@pytest.mark.parametrize(
    "changed",
    [{"end_ms": 600}, {"complete": False}, {"start_ms": 0}, {"end_ms": float("nan")}],
)
def test_conditioned_alignment_without_both_observed_endpoints_cannot_pass(changed):
    _, _, tifa, singing, _ = fixture()
    singing[0].update(changed)
    assert paired_boundary(tifa[0], singing[0], 1200) is None


@pytest.mark.parametrize(
    "changed",
    [{"agreement": 0.89}, {"mean_similarity": -0.1}, {"reason": "incomplete"}],
)
def test_tifa_path_rules_remain_strict(changed):
    _, _, tifa, singing, _ = fixture()
    tifa[0].update(changed)
    assert paired_boundary(tifa[0], singing[0], 1200) is None


def test_low_confidence_or_another_occurrence_is_withheld():
    for changed in (
        {"probability": 0.69},
        {"observed_midpoint_ms": 1100},
        {"source_match": False},
        {"matched_words": 1},
    ):
        baseline, targets, tifa, singing, views = fixture()
        views[0][1].update(changed)
        assert (
            recover_verified_boundaries(baseline, targets, tifa, singing, views, 1200)
            == baseline
        )


def test_existing_interval_and_saved_reading_are_preserved():
    baseline, targets, tifa, singing, views = fixture()
    baseline[0].update(start_ms=90, end_ms=355)
    targets[2]["protected_reading"] = True
    out = recover_verified_boundaries(baseline, targets, tifa, singing, views, 1200)
    assert out[0] == baseline[0] and out[2] == baseline[2]
    assert out[1]["start_ms"] == 400


def test_collision_with_old_interval_is_withheld_without_trimming():
    baseline, targets, tifa, singing, views = fixture()
    baseline[0].update(start_ms=90, end_ms=500)
    out = recover_verified_boundaries(baseline, targets, tifa, singing, views, 1200)
    assert out[0] == baseline[0] and out[1] == baseline[1]


def test_original_missing_denominator_and_ownership_cannot_be_erased():
    baseline, targets, tifa, singing, views = fixture()
    assert (
        recover_verified_boundaries(
            baseline, targets, tifa, singing, views, 1200, source_words=5
        )
        == baseline
    )
    changed = copy.deepcopy(singing)
    changed[0]["raw_span"] = [4, 8]
    with pytest.raises(ValueError, match="ownership"):
        recover_verified_boundaries(baseline, targets, tifa, changed, views, 1200)


def test_context_lexemes_keep_true_midpoints_without_clipping_or_endpoint_transfer():
    _, targets, _, _, _ = fixture()
    segments = [
        {
            "words": [
                {
                    "word": t["text"],
                    "start": i * 0.3,
                    "end": i * 0.3 + 0.5,
                    "probability": 0.9,
                }
                for i, t in enumerate(targets)
            ]
        }
    ]
    observed = observed_lexemes(
        targets, segments, 1000, offset_ms=-100, context_length_ms=1200
    )
    assert [u["source_match"] for u in observed] == [True, True, True]
    assert observed[0]["observed_midpoint_ms"] == 150
    assert "start_ms" not in observed[0]
    assert segments[0]["words"][0]["start"] == 0


def test_invalid_context_bounds_cannot_supply_a_plausible_midpoint():
    _, targets, _, _, _ = fixture()
    for start, end in ((-0.2, 0.8), (0.2, 2.0)):
        segments = [
            {
                "words": [
                    {"word": t["text"], "start": start, "end": end, "probability": 0.99}
                    for t in targets
                ]
            }
        ]
        assert all(
            not u["source_match"]
            for u in observed_lexemes(targets, segments, 1200, context_length_ms=1200)
        )


def test_repeated_context_and_single_common_word_do_not_prove_source_match():
    _, targets, _, _, _ = fixture()
    words = [
        {"word": t["text"], "start": i * 0.3, "end": i * 0.3 + 0.2, "probability": 0.99}
        for i, t in enumerate(targets)
    ]
    repeated = observed_lexemes(targets, [{"words": words + words}], 1200)
    assert all(not u["source_match"] for u in repeated)
    single = observed_lexemes(targets[:1], [{"words": words[:1]}], 1200)
    assert not single[0]["source_match"]
