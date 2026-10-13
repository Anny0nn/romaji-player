"""Repeat proposals retain occurrence identity and observed, ordered boundaries."""

import copy
import importlib.util
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location(
    "repeat_trial",
    Path(__file__).resolve().parents[2] / "scripts/experiment-repeat-windows.py",
)
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


def fixture():
    words = [
        {"raw_span": [0, 3], "hiragana": "あ", "expected_text": "あ", "romaji": "a"},
        {"raw_span": [3, 6], "hiragana": "か", "expected_text": "か", "romaji": "ka"},
    ]
    cases = [
        {
            "id": str(i),
            "occurrence": str(i),
            "track": "song",
            "snapshot": "s",
            "delay_ms": 250,
            "raw_line": "あか",
            "words": copy.deepcopy(words),
            "start_ms": i * 2000,
        }
        for i in range(2)
    ]
    result = {
        "base_snapshot": "s",
        "delay_ms": 250,
        "snapshot": {
            "source": {},
            "occurrences": [
                {
                    "id": str(i),
                    "raw_line": "あか",
                    "fragments": [
                        {
                            "raw_span": w["raw_span"],
                            "interval": {"start_ms": 100, "end_ms": 200},
                        }
                        for w in words[: 2 - i]
                    ],
                }
                for i in range(2)
            ],
        },
    }
    return cases, {"song": result}


def test_repeat_requires_same_source_reading_and_song():
    cases, results = fixture()
    pairs = trial.select(cases, results)
    assert len(pairs) == 1 and pairs[0][0]["id"] == "0" and pairs[0][1]["id"] == "1"
    cases[1]["words"][1]["romaji"] = "different"
    assert trial.select(cases, results) == []
    cases, results = fixture()
    cases[1]["track"] = "other"
    results["other"] = copy.deepcopy(results["song"])
    assert trial.select(cases, results) == []


def test_protected_reading_excludes_every_identical_repeat():
    cases, results = fixture()
    results["song"]["snapshot"]["source"]["derivation"] = {
        "readings": [{"raw_line": "あか"}]
    }
    assert trial.select(cases, results) == []


def test_dtw_uses_observed_frames_and_abstains_on_missing_or_distorted_path():
    path = np.array([[i, i + 1] for i in range(10)])
    interval = {"start_ms": 1080, "end_ms": 1140}
    assert trial.proposal(path, interval, 1000, 10, 11) == (100, 185)
    assert trial.proposal(path[:3], interval, 1000, 10, 11) is None
    warped = np.array([[i, i * 4] for i in range(10)])
    assert trial.proposal(warped, interval, 1000, 10, 40) is None


def test_independent_boundaries_need_complete_finite_confident_observations():
    unit = {"start_ms": 100, "end_ms": 300, "mean_probability": 0.8}
    assert trial.supported(unit, unit)
    for fields in (
        {"end_ms": 100},
        {"start_ms": -1},
        {"start_ms": float("nan")},
        {"mean_probability": 0.44},
        {"end_ms": 451},
    ):
        assert not trial.supported(unit, {**unit, **fields})


def test_conflicting_new_words_are_both_rejected_without_moving_saved_anchors():
    words = [{"raw_span": [i, i + 1]} for i in range(4)]
    current = {
        (0, 1): {"start_ms": 1100, "end_ms": 1200},
        (3, 4): {"start_ms": 1800, "end_ms": 1900},
    }
    rows = [
        {
            "raw_span": [i, i + 1],
            "reason": "model_supported",
            "prediction": {"start_ms": a, "end_ms": b},
        }
        for i, a, b in [(1, 300, 600), (2, 550, 700)]
    ]
    before = copy.deepcopy(current)
    trial.reject_overlaps(rows, words, current, 1000)
    assert [r["reason"] for r in rows] == ["overlap", "overlap"]
    assert current == before
