"""Source phonetics retain written particles while using sung wa/e pronunciation."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "refinement"),
    str(ROOT / "tifa/vendor"),
]
from audio_first_models import kana_sequence_phones, source_word_phones


def test_particle_orthography_and_pronunciation_are_not_conflated():
    assert source_word_phones({"hiragana": "は", "romaji": "wa"}) == ["w", "a"]
    assert source_word_phones({"hiragana": "は", "romaji": "ha"}) == ["h", "a"]
    assert source_word_phones({"hiragana": "へ", "romaji": "e"}) == ["e"]
    assert source_word_phones({"hiragana": "へ", "romaji": "he"}) == ["h", "e"]
    assert source_word_phones({"hiragana": "を", "romaji": "o"}) == ["o"]


def test_acoustic_kana_does_not_receive_textual_particle_reinterpretation():
    assert kana_sequence_phones("はへ") == ["h", "a", "h", "e"]
    assert kana_sequence_phones("わえ") == ["w", "a", "e"]
    assert source_word_phones({"hiragana": "あぁ", "romaji": "aa"}) == ["a", "a"]
