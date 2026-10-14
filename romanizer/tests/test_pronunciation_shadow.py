"""Dictionary shadows reuse production node/source mapping, never its lemma."""

import importlib.util
import sys
from pathlib import Path

import pytest

from romanizer import Converter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "pronunciation_shadow", ROOT / "scripts/export-pronunciation-shadow.py"
)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


@pytest.fixture(scope="module")
def converter():
    return Converter()


def test_inflected_pronunciation_and_particle_keep_written_words(converter):
    response = exporter.shadow(converter, "東京へ行こう", 1)
    assert response["failure"] is None
    words = response["words"]
    assert [(w["hiragana"], w["pronunciation_kana"]) for w in words] == [
        ("とうきょう", "とーきょー"),
        ("へ", "え"),
        ("いこう", "いこー"),
    ]
    assert words[-1]["raw_span"] == [9, 18]
    assert words[-1]["expected_text"] == "行こう"
    assert words[-1]["romaji"] == "ikou"


def test_long_vowels_are_lexical_not_a_global_ou_replacement(converter):
    words = exporter.shadow(converter, "思う 子牛 光景", 1)["words"]
    assert [w["pronunciation_kana"] for w in words] == ["おもう", "こうし", "こーけー"]


def test_normalization_preserves_original_utf8_envelopes(converter):
    raw = "　東京へ行こう"
    result = exporter.shadow(converter, raw, 1)
    assert result["failure"] is None
    for word in result["words"]:
        a, b = word["raw_span"]
        assert raw.encode()[a:b].decode() == word["expected_text"]


def test_unknown_kanji_never_receive_an_invented_reading(converter):
    result = exporter.shadow(converter, "𠮷", 1)
    assert all(w["pronunciation_kana"] is None for w in result["words"])
