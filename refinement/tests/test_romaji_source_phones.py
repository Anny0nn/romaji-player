"""Romaji hypotheses preserve marked vowels and Japanese phoneme identities."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from romaji_source_phones import acoustic_spelling, japanese_romaji_phones


@pytest.mark.parametrize(
    "text,expected",
    [
        ("tōkyō", ["t", "o", "o", "ky", "o", "o"]),
        ("SHIN", ["sh", "i", "N"]),
        ("shin'ya", ["sh", "i", "N", "y", "a"]),
        ("gakkou", ["g", "a", "cl", "k", "o", "u"]),
        ("matcha", ["m", "a", "cl", "ch", "a"]),
        ("onna", ["o", "N", "n", "a"]),
    ],
)
def test_marked_romaji_is_a_literal_bounded_phone_hypothesis(text, expected):
    original = text
    assert japanese_romaji_phones(text) == expected
    assert text == original


@pytest.mark.parametrize(
    "text", ["hello", "rock'n'roll", "123", "とお", "a " * 100, "a" * 97]
)
def test_unparsed_text_stays_unsupported(text):
    assert japanese_romaji_phones(text) is None


def test_ascii_english_lookalikes_are_only_hypotheses_not_language_classification():
    assert japanese_romaji_phones("to") == ["t", "o"]
    assert japanese_romaji_phones("no") == ["n", "o"]
    assert acoustic_spelling("TŌ") == "too"
