"""Pronunciation hypotheses remain acoustic input, never displayed corrections."""

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
from singing_recovery import pronunciation_targets


def test_dictionary_shadow_is_a_fresh_trial_and_preserves_reading_and_retained_times(
    monkeypatch,
):
    import numpy as np
    import singing_recovery

    targets = [
        {
            "text": "とうきょう",
            "romaji": "toukyou",
            "raw_span": [0, 6],
            "pronunciation": "とーきょー",
        },
        {
            "text": "ゆこう",
            "romaji": "yukou",
            "raw_span": [6, 15],
            "pronunciation": None,
        },
    ]
    baseline = [
        {"raw_span": [0, 6], "start_ms": -1, "end_ms": -1},
        {"raw_span": [6, 15], "start_ms": 500, "end_ms": 900},
    ]
    attempted = []

    class Aligner:
        def align(self, samples, words, **_):
            attempted.append([w["text"] for w in words])
            return baseline

    monkeypatch.setattr(
        singing_recovery,
        "word_alignment",
        lambda *_args, **_kwargs: [{"mean_probability": 0.8}] * 2,
    )
    monkeypatch.setattr(
        singing_recovery, "recover_singing_gaps", lambda old, *_args: old
    )
    result = singing_recovery.recover(
        np.zeros(16000),
        [(0, 0, 16000, targets)],
        Aligner(),
        [(None, None)],
        {},
        [baseline],
        {"0": 2},
        lambda _: None,
    )
    assert attempted == [["とうきょう", "ゆこう"], ["とーきょー", "ゆこう"]]
    assert result == [baseline]
    assert targets[0]["text"] == "とうきょう"
    assert targets[1]["pronunciation"] is None


class Converter:
    def convert(self, text):
        if text == "unknown":
            return []
        group = SimpleNamespace(phonemes=["l", "ah", "v"])
        return [SimpleNamespace(readings=[SimpleNamespace(paths=[[group]])])]


def test_english_acoustic_alias_does_not_rewrite_source_or_japanese_reading():
    targets = [
        {"text": "Love", "romaji": "Love", "raw_span": [0, 4]},
        {"text": "さくら", "romaji": "sakura", "raw_span": [4, 13]},
    ]
    aligner = SimpleNamespace(converters={"en": Converter()})
    aliases, phones = pronunciation_targets(aligner, targets, "loan")
    assert aliases == {0: ["r", "a", "b", "u"]}
    assert phones[1] == ["s", "a", "k", "u", "r", "a"]
    assert targets[0]["text"] == "Love" and targets[0]["raw_span"] == [0, 4]


def test_unknown_english_does_not_receive_an_invented_pronunciation():
    targets = [{"text": "unknown", "romaji": "unknown", "raw_span": [0, 7]}]
    aliases, phones = pronunciation_targets(
        SimpleNamespace(converters={"en": Converter()}), targets, "direct"
    )
    assert aliases == {} and phones == [None]
