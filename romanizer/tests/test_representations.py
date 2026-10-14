"""A selected reading owns every script and model target, including after repair."""

import pytest

from romanizer import Converter, katakana, slice_bytes


@pytest.fixture(scope="module")
def converter():
    return Converter()


def convert(converter, raw, overrides=()):
    return converter.convert(
        {
            "protocol_version": 2,
            "request_id": 1,
            "track_id": "synthetic",
            "snapshot_id": "fixture",
            "occurrence_id": 0,
            "override_revision": 0,
            "expected_conversion_signature": converter.signature,
            "raw_line": raw,
            "overrides": list(overrides),
        }
    )


@pytest.mark.parametrize(
    "raw",
    [
        "東京へ行こう",
        "ｶﾞ 食べた を",
        "か\u3099 ヴ きゃ ぱっと",
        "思う 子牛 光景",
        "夢 LADY 123!",
        "Hello, WORLD!",
        "𠮷",
        "闇夜",
        "",
    ],
)
def test_scripts_and_targets_keep_the_selected_source_groups(converter, raw):
    response = convert(converter, raw)
    assert response["representation"] == "source-reading-v1"
    assert response["katakana"] == katakana(response["hiragana"])
    for word in response["words"]:
        selected = word["reading"]
        assert slice_bytes(response["romaji"], word["output_span"]) == selected["romaji"]
        assert slice_bytes(response["hiragana"], word["hiragana_span"]) == (
            selected["written"] or "？"
        )
        assert slice_bytes(response["katakana"], word["katakana_span"]) == katakana(
            selected["written"] or "？"
        )
        if word["raw_span"]:
            assert slice_bytes(raw, word["raw_span"]) == word["expected_text"]
        text = selected["written"] or word["expected_text"] or ""
        assert selected["alignment_text"] == "".join(c for c in text if c.isalnum())


def test_pronunciation_is_inflected_and_keeps_written_orthography(converter):
    words = convert(converter, "東京へ行こう")["words"]
    assert [(w["reading"]["written"], w["reading"]["pronunciation"]) for w in words] == [
        ("とうきょう", "とーきょー"),
        ("へ", "え"),
        ("いこう", "いこー"),
    ]


@pytest.mark.parametrize(
    "raw,kana", [("闇夜", "やみよ"), ("行こう", "ゆこう"), ("闇夜", "やみ よ")]
)
def test_sung_correction_never_inherits_the_wrong_dictionary_pronunciation(converter, raw, kana):
    response = convert(
        converter,
        raw,
        [
            {
                "id": "saved",
                "kind": "mapping_kana",
                "raw_span": [0, len(raw.encode())],
                "expected_text": raw,
                "replacement": converter.kana_romaji(kana),
                "hiragana": kana,
            }
        ],
    )
    assert not response["pending_overrides"]
    assert len(response["words"]) == 1
    reading = response["words"][0]["reading"]
    assert reading["written"] == kana
    assert reading["pronunciation"] is None
    assert reading["origin"] == "saved"
    assert response["katakana"] == katakana(kana)
    assert response["words"][0]["expected_text"] == raw


def test_old_wire_protocol_is_explicitly_rejected(converter):
    with pytest.raises(ValueError, match="unsupported_protocol"):
        converter.convert({"protocol_version": 1, "command": "hello", "request_id": 1})


@pytest.mark.parametrize(
    "raw,pieces",
    [
        ("ゲ・ン・カ・イ", ["ゲ", "ン", "カ", "イ"]),
        ("ゲ・ン・カ・イまで", ["ゲ", "ン", "カ", "イ", "まで"]),
        ("ゲ・ﾝ・ｶ・ｲ", ["ゲ", "ﾝ", "ｶ", "ｲ"]),
    ],
)
def test_unknown_dotted_kana_keeps_words_and_maps_each_exact_source_piece(converter, raw, pieces):
    result = convert(converter, raw)
    assert result["romaji"].startswith("ge/n/ka/i")
    assert result["hiragana"].startswith("げ/ん/か/い")
    assert result["katakana"].startswith("ゲ/ン/カ/イ")
    assert len(result["words"]) == len(pieces)
    assert [w["expected_text"] for w in result["words"]] == pieces
    assert all(w["reading"]["origin"] == "source" for w in result["words"][:4])
    for word, piece in zip(result["words"], pieces, strict=True):
        assert slice_bytes(raw, word["raw_span"]) == piece
        assert word["mapping_status"] == "mapped"
        assert word["reading"]["written"]


@pytest.mark.parametrize(
    "surface,output",
    [
        ("ゲ・ン", "ge/m"),
        ("ゲ・・ン", "ge/n"),
        ("限・界", "gen/kai"),
        ("ゲ・A", "ge/A"),
        ("ゲ・ン", "gen"),
    ],
)
def test_subnode_mapping_withholds_non_kana_or_inexact_reconstruction(converter, surface, output):
    assert (
        converter.dotted_kana_parts(
            surface, output, [0, len(surface.encode())], [0, len(output.encode())]
        )
        == []
    )


def test_subnode_reading_edit_keeps_other_words_and_reattaches(converter):
    raw = "ゲ・ン・カ・イ"
    edit = {
        "id": "saved",
        "kind": "reading_kana",
        "raw_span": [12, 15],
        "expected_text": "カ",
        "hiragana": "かあ",
        "replacement": "kaa",
    }
    for _ in range(2):
        result = convert(converter, raw, [edit])
        assert result["pending_overrides"] == []
        assert result["romaji"] == "ge/n/kaa/i"
        assert result["hiragana"] == "げ/ん/かあ/い"
        assert len(result["words"]) == 4
        assert [w["raw_span"] for w in result["words"]] == [[0, 3], [6, 9], [12, 15], [18, 21]]
