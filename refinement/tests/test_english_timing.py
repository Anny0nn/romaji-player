"""Observed English recovery preserves source ownership and existing timestamps."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from english_timing import observed_words, recover_english


def targets(text="we sing tonight"):
    offset, result = 0, []
    for word in text.split():
        result.append(
            {"raw_span": [offset, offset + len(word)], "text": word, "romaji": word}
        )
        offset += len(word) + 1
    return result


def segments(text="we sing tonight"):
    return [
        {
            "words": [
                {"word": word, "start": i + 0.1, "end": i + 0.6, "probability": 0.95}
                for i, word in enumerate(text.split())
            ]
        }
    ]


def evidence():
    words = targets()
    observed = observed_words(words, segments(), 4000)
    baseline = [
        {"raw_span": w["raw_span"], "start_ms": -1, "end_ms": -1} for w in words
    ]
    trial = [
        {**w, "reason": "token_agreement", "agreement": 0.96, "mean_similarity": 0.6}
        for w in observed
    ]
    return words, baseline, trial, observed


def test_exact_context_keeps_each_observed_word_without_dividing_line_time():
    words, baseline, trial, observed = evidence()
    baseline[0].update(start_ms=90, end_ms=590)
    repaired = recover_english(baseline, words, [trial], [observed, observed], 4000)
    assert repaired[0] == baseline[0]
    assert [w["start_ms"] for w in repaired] == [90, 1100, 2100]
    assert baseline[1]["start_ms"] == -1


def test_wrong_or_ambiguous_repeated_phrase_never_attaches():
    for source, recognized in [
        ("we sing tonight", "another wrong verse"),
        ("hey hey", "hey hey hey"),
    ]:
        result = observed_words(targets(source), segments(recognized), 5000)
        assert all(w["start_ms"] == -1 for w in result)


def test_paired_views_and_independent_positive_tifa_are_required():
    words, baseline, trial, observed = evidence()
    shifted = [
        {**w, "start_ms": w["start_ms"] + 500, "end_ms": w["end_ms"] + 500}
        for w in observed
    ]
    assert (
        recover_english(baseline, words, [trial], [observed, shifted], 4000) == baseline
    )
    weak = [{**w, "agreement": 0.89} for w in trial]
    assert (
        recover_english(baseline, words, [weak], [observed, observed], 4000) == baseline
    )
    for probability in (float("nan"), float("inf"), 1.1):
        bad = [{**w, "probability": probability} for w in observed]
        assert (
            recover_english(baseline, words, [trial], [bad, observed], 4000) == baseline
        )


def test_collision_is_rejected_instead_of_moving_existing_neighbor():
    words, baseline, trial, observed = evidence()
    baseline[0].update(start_ms=0, end_ms=1300)
    repaired = recover_english(baseline, words, [trial], [observed, observed], 4000)
    assert repaired[0] == baseline[0]
    assert repaired[1]["start_ms"] == -1
    assert repaired[2]["start_ms"] == 2100


def test_stale_word_owner_or_missing_view_fails_closed():
    words, baseline, trial, observed = evidence()
    bad = copy.deepcopy(trial)
    bad[0]["raw_span"] = [1, 3]
    with pytest.raises(ValueError):
        recover_english(baseline, words, [bad], [observed, observed], 4000)
    with pytest.raises(ValueError):
        recover_english(baseline, words, [trial], [observed], 4000)


def test_contraction_matches_without_rewriting_its_original_byte_span():
    words = targets("don't stop")
    result = observed_words(words, segments("dont stop"), 4000)
    assert result[0]["raw_span"] == [0, 5]
    assert result[0]["start_ms"] == 100


def test_common_single_word_and_nonfinite_timestamps_are_withheld():
    assert all(
        w["start_ms"] == -1 for w in observed_words(targets(), segments("sing"), 4000)
    )
    bad = segments()
    bad[0]["words"][1]["start"] = float("nan")
    assert observed_words(targets(), bad, 4000)[1]["start_ms"] == -1
