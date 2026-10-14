"""Pronunciation hypotheses remain acoustic input, never displayed corrections."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from singing_recovery import pronunciation_targets


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
