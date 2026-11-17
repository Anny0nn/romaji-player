"""Provider ruby never changes source groups or outranks saved/sung readings."""

import pytest
from test_romanizer import request

from romanizer import Converter


@pytest.fixture(scope="module")
def converter():
    return Converter()


def supplied(raw, surface, kana):
    a = raw.index(surface)
    return {
        "raw_span": [len(raw[:a].encode()), len(raw[: a + len(surface)].encode())],
        "expected_text": surface,
        "hiragana": kana,
    }


def test_explicit_source_reading_preserves_groups_and_clears_dictionary_shadow(converter):
    raw = "青い地球にありがとう"
    original = converter.convert(request(converter, raw))
    value = request(converter, raw)
    value["supplied_readings"] = [supplied(raw, "地球", "ほし")]
    result = converter.convert(value)
    assert result["supplied_readings_version"] == 1
    assert [w["raw_span"] for w in result["words"]] == [w["raw_span"] for w in original["words"]]
    word = next(w for w in result["words"] if w["expected_text"] == "地球")
    assert word["reading"]["written"] == "ほし"
    assert word["reading"]["romaji"] == "hoshi"
    assert word["reading"]["pronunciation"] is None
    assert word["reading"]["origin"] == "source"
    assert word["override_id"] is None


def test_source_ruby_cannot_replace_curated_or_saved_readings(converter):
    raw = "青い地球にありがとう"
    value = request(converter, raw)
    value["track_id"] = "4cH6RfZ1qIuz6sumRoDEGK"
    value["supplied_readings"] = [supplied(raw, "地球", "ちきゅう")]
    result = converter.convert(value)
    assert (
        next(w for w in result["words"] if w["expected_text"] == "地球")["reading"]["written"]
        == "ほし"
    )
    value["overrides"] = [
        {
            "id": "saved",
            "kind": "reading_kana",
            "raw_span": [6, 12],
            "expected_text": "地球",
            "replacement": "sekai",
            "hiragana": "せかい",
        }
    ]
    result = converter.convert(value)
    assert (
        next(w for w in result["words"] if w["expected_text"] == "地球")["reading"]["written"]
        == "せかい"
    )


def test_partial_and_cross_word_ruby_abstain_without_regrouping(converter):
    for raw, surface, kana in [("学校", "学", "が"), ("君は故郷を出た", "君は故郷", "きみはまち")]:
        value = request(converter, raw)
        original = converter.convert(value)
        value["supplied_readings"] = [supplied(raw, surface, kana)]
        result = converter.convert(value)
        assert result["romaji"] == original["romaji"]
        assert [w["raw_span"] for w in result["words"]] == [
            w["raw_span"] for w in original["words"]
        ]


def test_invalid_or_overlapping_ruby_is_rejected(converter):
    value = request(converter, "地球")
    value["supplied_readings"] = [supplied("地球", "地球", "hoshi")]
    with pytest.raises(ValueError):
        converter.convert(value)
    value["supplied_readings"] = [supplied("地球", "地球", "ほし")] * 2
    with pytest.raises(ValueError):
        converter.convert(value)


def test_malformed_provider_entries_do_not_crash_the_persistent_protocol(converter):
    value = request(converter, "地球")
    for bad in (None, 42, "not a ruby record"):
        value["supplied_readings"] = [bad]
        with pytest.raises(ValueError):
            converter.convert(value)
