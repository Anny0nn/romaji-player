"""Exact context clocks, independent evidence and atomic regional repairs."""

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
from context_policy import apply_context, joint_crops


def target(start, text="あ"):
    return {
        "raw_span": [start, start + 3],
        "text": text,
        "romaji": "a" if text == "あ" else text,
    }


def unit(span, start, end, **fields):
    return {"raw_span": span, "start_ms": start, "end_ms": end, **fields}


def fixture():
    crops = [
        (0, 8000, 25600, [target(0), target(3)]),
        (1, 16000, 32000, [target(0), target(3)]),
    ]
    baseline = [
        [unit([0, 3], 0, 100), unit([3, 6], 300, 400)],
        [unit([0, 3], -1, -1), unit([3, 6], 400, 500)],
    ]
    jobs = joint_crops(crops, baseline, {"0": 2, "1": 2})
    targets = jobs[0]["crop"][3]
    trial = [
        unit(t["raw_span"], first, last)
        for t, (first, last) in zip(
            targets, [(0, 100), (300, 400), (600, 700), (900, 1000)], strict=True
        )
    ]
    return (
        crops,
        baseline,
        jobs,
        [{"units": trial}],
        [[{**u, "mean_probability": 0.8} for u in trial]],
    )


def test_context_remaps_repeated_byte_spans_and_only_recording_relative_clock():
    crops, baseline, jobs, trials, proof = fixture()
    assert jobs[0]["crop"][1:3] == (8000, 32000)
    assert [t["raw_span"] for t in jobs[0]["crop"][3]] == [
        [0, 3],
        [3, 6],
        [7, 10],
        [10, 13],
    ]
    result = apply_context(baseline, crops, jobs, trials, proof)
    assert result[1][0] == unit([0, 3], 100, 200)
    assert result[0] == baseline[0] and result[1][1] == baseline[1][1]
    assert baseline[1][0]["start_ms"] == -1


def test_weak_independent_evidence_or_wrong_ownership_cannot_recover():
    crops, baseline, jobs, trials, proof = fixture()
    proof[0][2]["mean_probability"] = 0.44
    assert apply_context(baseline, crops, jobs, trials, proof) == baseline
    proof[0][2]["raw_span"] = [0, 3]
    with pytest.raises(ValueError, match="ownership"):
        apply_context(baseline, crops, jobs, trials, proof)


def test_equal_text_does_not_allow_swapping_repeated_source_words():
    crops, baseline, jobs, trials, proof = fixture()
    jobs[0]["owners"][0], jobs[0]["owners"][1] = (
        jobs[0]["owners"][1],
        jobs[0]["owners"][0],
    )
    with pytest.raises(ValueError, match="ownership"):
        apply_context(baseline, crops, jobs, trials, proof)


def test_latin_and_long_or_simultaneous_crops_stay_out_of_japanese_path():
    crops, baseline, _, _, _ = fixture()
    crops[1][3][0] = target(0, "love")
    assert joint_crops(crops, baseline, {"0": 2, "1": 2}) == []
    crops[1][3][0] = target(0)
    assert (
        joint_crops(
            [crops[0], (1, 8000, 32000, crops[1][3])], baseline, {"0": 2, "1": 2}
        )
        == []
    )
    assert (
        joint_crops(
            [crops[0], (1, 16000, 500000, crops[1][3])], baseline, {"0": 2, "1": 2}
        )
        == []
    )


def test_conflicting_joint_contexts_reject_both_atomic_proposals():
    crops, baseline, jobs, trials, proof = fixture()
    second, second_proof = copy.deepcopy(trials[0]), copy.deepcopy(proof[0])
    second["units"][2].update(start_ms=780, end_ms=880)
    second_proof[2].update(start_ms=780, end_ms=880)
    assert (
        apply_context(
            baseline, crops, jobs * 2, [trials[0], second], [proof[0], second_proof]
        )
        == baseline
    )


def test_wrong_verse_coincidence_cannot_meet_joint_phrase_guard():
    crops, baseline, jobs, trials, proof = fixture()
    for index in (0, 1, 3):
        proof[0][index]["mean_probability"] = 0.1
    assert apply_context(baseline, crops, jobs, trials, proof) == baseline


def test_context_does_not_extend_original_occurrence_bounds():
    crops, baseline, jobs, trials, proof = fixture()
    for start, end in [(350, 450), (1400, 1501)]:
        trials[0]["units"][2].update(start_ms=start, end_ms=end)
        proof[0][2].update(start_ms=start, end_ms=end)
        assert apply_context(baseline, crops, jobs, trials, proof) == baseline


def test_last_partial_sample_millisecond_is_allowed_but_cue_origin_is_exact():
    crops, baseline, _, _, _ = fixture()
    crops[1] = (1, 16000, 32007, crops[1][3])
    assert joint_crops(crops, baseline, {"0": 2, "1": 2})[0]["crop"][2] == 32007
    crops[1] = (1, 16001, 32007, crops[1][3])
    with pytest.raises(ValueError, match="clock"):
        joint_crops(crops, baseline, {"0": 2, "1": 2})
