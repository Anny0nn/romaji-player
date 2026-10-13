"""Spoken shadows preserve written suffixes without changing acoustic phones."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from audio_first_pronunciation import (
    attach_shadow,
    pronunciation_boundaries,
    spelling_candidates,
)


def word():
    return {
        "raw_span": [0, 9],
        "expected_text": "行こう",
        "hiragana": "いこう",
        "romaji": "ikou",
    }


def test_dictionary_suffix_preserves_yukou_without_kanji_round_trip():
    old = word()
    source = attach_shadow([old], {"words": [{**old, "pronunciation_kana": "いこー"}]})[
        0
    ]
    phones = ["y", "u", "k", "o", "o"]
    inventory = {("y", "u"): ["ゆ"], ("k", "o"): ["こ"], ("o",): ["お"], ("i",): ["い"]}
    readings = spelling_candidates(phones, inventory, source)
    assert "ゆこう" in readings
    assert "ゆこお" in readings  # Still an alternative until spelling selection.
    assert phones == ["y", "u", "k", "o", "o"]
    assert source["hiragana"] == "いこう"


def test_shadow_rejects_stale_source_or_changed_display():
    old = word()
    for key, value in [
        ("raw_span", [3, 12]),
        ("romaji", "yukou"),
        ("expected_text", "進もう"),
    ]:
        with pytest.raises(ValueError):
            attach_shadow(
                [old], {"words": [{**old, key: value, "pronunciation_kana": "いこー"}]}
            )


def test_no_mora_boundary_inside_small_kana_or_uncertain_phone_edit():
    boundaries = pronunciation_boundaries("とうきょう", "とーきょー")
    assert not any(char == 3 for char, _ in boundaries)  # き|ょ is not a mora edge.
    assert pronunciation_boundaries("unmapped", "とー") == []


def test_spelling_candidate_bound_abstains_instead_of_selecting_arbitrarily():
    inventory = {("a",): ["あ", "ぁ"]}
    assert spelling_candidates(["a"], inventory, word(), limit=1) == []
