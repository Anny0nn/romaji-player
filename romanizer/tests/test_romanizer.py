import json
import subprocess
import sys

import pytest

from romanizer import Converter, slice_bytes


@pytest.fixture(scope="session")
def converter():
    return Converter()


def request(converter, raw, overrides=None):
    return {
        "protocol_version": 1,
        "request_id": "fixture",
        "track_id": "synthetic",
        "snapshot_id": "fixture",
        "occurrence_id": 0,
        "override_revision": 0,
        "expected_conversion_signature": converter.signature,
        "raw_line": raw,
        "overrides": overrides or [],
    }


@pytest.mark.parametrize(
    "text,wanted", [("闇夜", "やみよ"), ("行こう", "ゆこう"), ("ハッカ色", "はっかいろ")]
)
def test_context_candidates_preserve_inflection_and_exact_source(converter, text, wanted):
    value = request(converter, "  " + text + "  ")
    value["command"] = "candidates"
    result = converter.convert(value)
    group = next(g for g in result["reading_candidates"] if g["expected_text"] == text)
    assert slice_bytes(value["raw_line"], group["raw_span"]) == text
    assert wanted in [c["hiragana"] for c in group["candidates"]]
    if text == "行こう":
        assert "ゆく" not in [c["hiragana"] for c in group["candidates"]]
    assert sum(len(g["candidates"]) for g in result["reading_candidates"]) <= 192
    assert all(len(g["candidates"]) <= 16 for g in result["reading_candidates"])


def test_canonical_kana_correction_and_protected_candidates(converter):
    edit = {
        "id": "verified",
        "kind": "mapping_kana",
        "raw_span": [0, 6],
        "expected_text": "闇夜",
        "replacement": "yami yo",
        "hiragana": "やみ よ",
    }
    value = request(converter, "闇夜", [edit])
    value["command"] = "candidates"
    result = converter.convert(value)
    assert result["romaji"] == "yami yo"
    assert result["hiragana"] == "やみ よ"
    assert result["reading_candidates"] == []
    edit["hiragana"] = "あんや"
    result = converter.convert(value)
    assert result["pending_overrides"]
    assert result["romaji"] == "an'ya"


def test_sakura_uses_verified_sung_reading_without_changing_source_anchors(converter):
    raw = "君は故郷を出た"
    normal = converter.convert(request(converter, raw))
    fixture = request(converter, raw)
    fixture["track_id"] = "1lTfD2M6UpJRWi3YLb8qb5"
    corrected = converter.convert(fixture)
    assert "machi" in corrected["romaji"]
    word = next(w for w in corrected["words"] if w["expected_text"] == "故郷")
    assert slice_bytes(corrected["hiragana"], word["hiragana_span"]) == "まち"
    assert word["raw_span"] == [6, 12]
    assert [w["raw_span"] for w in corrected["words"]] == [w["raw_span"] for w in normal["words"]]
    assert "machi" not in normal["romaji"]
    assert corrected["applied_override_ids"] == []


def test_verified_song_reading_requires_context_and_defers_to_saved_edits(converter):
    fixture = request(converter, "故郷へ帰る")
    fixture["track_id"] = "1lTfD2M6UpJRWi3YLb8qb5"
    assert "machi" not in converter.convert(fixture)["romaji"]
    override = {
        "id": "mine",
        "kind": "reading",
        "raw_span": [6, 12],
        "expected_text": "故郷",
        "replacement": "furusato",
    }
    fixture = request(converter, "君は故郷を出た", [override])
    fixture["track_id"] = "1lTfD2M6UpJRWi3YLb8qb5"
    result = converter.convert(fixture)
    assert "furusato" in result["romaji"]
    assert "machi" not in result["romaji"]
    assert result["applied_override_ids"] == ["mine"]


def test_verified_reading_maps_actual_utf8_positions_with_provider_spacing(converter):
    fixture = request(converter, "君 は 故郷 を 出た")
    fixture["track_id"] = "1lTfD2M6UpJRWi3YLb8qb5"
    result = converter.convert(fixture)
    word = next(w for w in result["words"] if w["expected_text"] == "故郷")
    assert word["raw_span"] == [8, 14]
    assert slice_bytes(result["romaji"], word["output_span"]) == "machi"


@pytest.mark.parametrize("raw", ["青い地球にありがとう", "青い 地球 に ありがとう"])
def test_departure_sung_hoshi_preserves_spans_and_saved_readings(converter, raw):
    fixture = request(converter, raw)
    normal = converter.convert(fixture)
    fixture["track_id"] = "4cH6RfZ1qIuz6sumRoDEGK"
    corrected = converter.convert(fixture)
    word = next(w for w in corrected["words"] if w["expected_text"] == "地球")
    assert slice_bytes(corrected["romaji"], word["output_span"]) == "hoshi"
    assert slice_bytes(corrected["hiragana"], word["hiragana_span"]) == "ほし"
    assert [w["raw_span"] for w in corrected["words"]] == [w["raw_span"] for w in normal["words"]]
    assert "chikyuu" in normal["romaji"]
    fixture["overrides"] = [
        {
            "id": "saved",
            "kind": "reading",
            "raw_span": word["raw_span"],
            "expected_text": "地球",
            "replacement": "chikyuu",
        }
    ]
    edited = converter.convert(fixture)
    assert "chikyuu" in edited["romaji"]
    assert "hoshi" not in edited["romaji"]
    assert edited["applied_override_ids"] == ["saved"]


def test_departure_reading_requires_the_verified_line_context(converter):
    fixture = request(converter, "地球を大切に")
    fixture["track_id"] = "4cH6RfZ1qIuz6sumRoDEGK"
    assert "chikyuu" in converter.convert(fixture)["romaji"]


@pytest.mark.parametrize("raw", ["ハッカ色の月", "ハッカ色 の 月", "薄荷色の月"])
def test_tabi_color_reading_preserves_source_spans_and_saved_edits(converter, raw):
    fixture = request(converter, raw)
    original = converter.convert(fixture)
    fixture["track_id"] = "6KeWalxT7jDYdNfwiBtBzt"
    corrected = converter.convert(fixture)
    word = next(w for w in corrected["words"] if "色" in w["expected_text"])
    assert slice_bytes(corrected["romaji"], word["output_span"]) == "hakkairo"
    assert slice_bytes(corrected["hiragana"], word["hiragana_span"]) == "はっかいろ"
    assert [w["raw_span"] for w in corrected["words"]] == [w["raw_span"] for w in original["words"]]
    fixture["overrides"] = [
        {
            "id": "saved",
            "kind": "reading",
            "raw_span": word["raw_span"],
            "expected_text": word["expected_text"],
            "replacement": "hakkashoku",
        }
    ]
    edited = converter.convert(fixture)
    assert "hakkashoku" in edited["romaji"]
    assert "hakkairo" not in edited["romaji"]
    assert edited["applied_override_ids"] == ["saved"]


def test_tabi_color_reading_requires_song_and_line_context(converter):
    assert "hakkairo" not in converter.convert(request(converter, "ハッカ色の月"))["romaji"]
    fixture = request(converter, "ハッカ色を探す")
    fixture["track_id"] = "6KeWalxT7jDYdNfwiBtBzt"
    assert "hakkairo" not in converter.convert(fixture)["romaji"]


@pytest.mark.parametrize(
    ("raw", "romaji"),
    [
        ("桜へはを", "sakura e wa o"),
        ("食べた", "tabeta"),
        ("がっこう", "gakkou"),
        ("コーヒー", "koohii"),
        ("さくら は さくら", "sakura wa sakura"),
        ("  English  song!  ", "  English  song!  "),
    ],
)
def test_contextual_readings_and_complete_raw_anchors(converter, raw, romaji):
    result = converter.convert(request(converter, raw))
    assert result["romaji"] == romaji
    for word in result["words"]:
        assert slice_bytes(raw, word["raw_span"]) == word["expected_text"]
        assert slice_bytes(romaji, word["output_span"])


def test_normalization_preserves_original_bytes_not_normalized_offsets(converter):
    raw = "  ｶﾞ ガ"
    result = converter.convert(request(converter, raw))
    assert result["normalized_line"] == "  ガ ガ"
    assert [w["raw_span"] for w in result["words"]] == [[2, 8], [9, 15]]
    assert [w["expected_text"] for w in result["words"]] == ["ｶﾞ", "ガ"]
    assert [5, 5] not in result["boundary_associations"]


def test_joined_nodes_are_one_word(converter):
    result = converter.convert(request(converter, "食べた"))
    assert len(result["words"]) == 1
    assert len(result["words"][0]["constituent_nodes"]) == 2
    assert result["words"][0]["raw_span"] == [0, 9]


@pytest.mark.parametrize(
    ("raw", "hiragana"),
    [
        ("今日は桜を食べた", "きょう は さくら を たべた"),
        ("桜へはを", "さくら へ は を"),
        ("ｶﾞ 食べた を", "が たべた を"),
        ("コーヒー", "こーひー"),
        ("  English  song!  ", "  English  song!  "),
    ],
)
def test_hiragana_readings_share_complete_original_word_groups(converter, raw, hiragana):
    result = converter.convert(request(converter, raw))
    assert result["hiragana"] == hiragana
    for word in result["words"]:
        assert slice_bytes(hiragana, word["hiragana_span"])
        assert slice_bytes(raw, word["raw_span"]) == word["expected_text"]


def test_hiragana_atomic_reading_override_and_unknown_readings(converter):
    override = {
        "id": "kana",
        "kind": "reading",
        "raw_span": [0, 9],
        "expected_text": "さくら",
        "replacement": "sa ku ra",
    }
    result = converter.convert(request(converter, "さくら を", [override]))
    assert result["hiragana"] == "さ く ら を"
    assert slice_bytes(result["hiragana"], result["words"][0]["hiragana_span"]) == "さ く ら"
    assert result["words"][0]["raw_span"] == [0, 9]
    override["replacement"] = "space reading"
    assert converter.convert(request(converter, "さくら を", [override]))["hiragana"] == "？ を"
    assert "𰻞" not in converter.convert(request(converter, "未知𰻞"))["hiragana"]


def test_repeated_word_correction_and_spaces_rebuild_ranges(converter):
    override = {
        "id": "reading-1",
        "kind": "reading",
        "raw_span": [10, 19],
        "expected_text": "さくら",
        "replacement": "new reading",
    }
    result = converter.convert(request(converter, "さくら さくら を", [override]))
    assert result["romaji"] == "sakura new reading o"
    assert [slice_bytes(result["romaji"], w["output_span"]) for w in result["words"]] == [
        "sakura",
        "new reading",
        "o",
    ]
    assert [w["raw_span"] for w in result["words"]] == [[0, 9], [10, 19], [20, 23]]
    assert result["applied_override_ids"] == ["reading-1"]


@pytest.mark.parametrize("span,text", [([1, 9], "さくら"), ([0, 9], "wrong")])
def test_invalid_or_changed_raw_anchor_is_pending(converter, span, text):
    override = {
        "id": "bad",
        "kind": "reading",
        "raw_span": span,
        "expected_text": text,
        "replacement": "good",
    }
    result = converter.convert(request(converter, "さくら", [override]))
    assert result["romaji"] == "sakura"
    assert result["pending_overrides"][0]["id"] == "bad"
    assert not result["applied_override_ids"]


def test_explicit_mapping_can_group_complete_source_words(converter):
    override = {
        "id": "group",
        "kind": "mapping",
        "raw_span": [0, 7],
        "expected_text": "桜 を",
        "replacement": "sakura o",
    }
    result = converter.convert(request(converter, "桜 を", [override]))
    assert len(result["words"]) == 1
    assert result["words"][0]["raw_span"] == [0, 7]
    assert result["romaji"] == "sakura o"


def test_unknown_characters_remain_available_for_correction(converter):
    result = converter.convert(request(converter, "未知𰻞"))
    assert "𰻞" in result["romaji"]
    assert "?" not in result["romaji"]


@pytest.mark.parametrize("raw,romaji,kana", [("〜〜る", "ru", "る"), ("〜〜空", "sora", "そら")])
def test_unpronounced_leading_tokens_keep_exact_source_and_display_spans(
    converter, raw, romaji, kana
):
    result = converter.convert(request(converter, raw))
    assert result["romaji"].strip() == romaji
    assert len(result["words"]) == 1
    word = result["words"][0]
    assert word["raw_span"] == [6, 9]
    assert slice_bytes(raw, word["raw_span"]) == raw[-1]
    assert slice_bytes(result["romaji"], word["output_span"]) == romaji
    assert slice_bytes(result["hiragana"], word["hiragana_span"]) == kana


def test_protocol_rejects_wrong_signature(converter):
    fixture = request(converter, "桜")
    fixture["expected_conversion_signature"] = "old"
    with pytest.raises(ValueError, match="signature_mismatch"):
        converter.convert(fixture)


@pytest.mark.parametrize("invalid", [{"protocol_version": 999, "request_id": "bad"}, [], None])
def test_persistent_process_survives_bad_request(converter, invalid):
    inputs = [invalid, request(converter, "桜")]
    process = subprocess.run(
        [sys.executable, "romanizer/romanizer.py"],
        input="\n".join(json.dumps(x) for x in inputs) + "\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    responses = [json.loads(line) for line in process.stdout.splitlines()]
    assert responses[0]["error"] == "invalid_request"
    assert responses[1]["romaji"] == "sakura"
    assert not process.stderr


def test_cross_word_gemination_flags_only_affected_words(converter):
    result = converter.convert(request(converter, "桜 あっ そこ"))
    assert result["words"][0]["raw_span"] == [0, 3]
    assert all(w["mapping_status"] == "needs_review" for w in result["words"][1:])


@pytest.mark.parametrize(
    "raw,source,romaji,kana",
    [
        ("桜ぱっと飛ぶ", "ぱっと", "patto", "ぱっと"),
        ("強がってた", "強がってた", "tsuyogatteta", "つよがってた"),
        ("余裕ぶっこいている", "余裕ぶっこいて", "yoyuubukkoite", "よゆうぶっこいて"),
    ],
)
def test_contiguous_gemination_maps_complete_pronunciation_group(
    converter, raw, source, romaji, kana
):
    result = converter.convert(request(converter, raw))
    word = next(w for w in result["words"] if w["expected_text"] == source)
    assert slice_bytes(raw, word["raw_span"]) == source
    assert slice_bytes(result["romaji"], word["output_span"]) == romaji
    assert slice_bytes(result["hiragana"], word["hiragana_span"]) == kana
    assert all(w["mapping_status"] == "mapped" for w in result["words"])
    assert len(word["constituent_nodes"]) >= 2
    assert word["normalized_span"] == [
        word["constituent_nodes"][0][0],
        word["constituent_nodes"][-1][1],
    ]


def test_gemination_reading_override_keeps_group_source_identity(converter):
    override = {
        "id": "reading",
        "kind": "reading",
        "raw_span": [3, 12],
        "expected_text": "ぱっと",
        "replacement": "pat to",
    }
    result = converter.convert(request(converter, "桜ぱっと飛ぶ", [override]))
    word = next(w for w in result["words"] if w["override_id"] == "reading")
    assert result["applied_override_ids"] == ["reading"]
    assert word["raw_span"] == [3, 12]
    assert slice_bytes(result["romaji"], word["output_span"]) == "pat to"
    assert slice_bytes(result["hiragana"], word["hiragana_span"]) == "ぱっ と"


def test_explicit_mapping_repairs_unresolved_group_without_changing_neighbors(converter):
    raw = "桜 あっ そこ を"
    override = {
        "id": "repair",
        "kind": "mapping",
        "raw_span": [4, 17],
        "expected_text": "あっ そこ",
        "replacement": "a soko",
    }
    result = converter.convert(request(converter, raw, [override]))
    assert result["romaji"] == "sakura a soko o"
    assert result["applied_override_ids"] == ["repair"]
    assert [w["raw_span"] for w in result["words"]] == [[0, 3], [4, 17], [18, 21]]
    assert all(w["mapping_status"] == "mapped" for w in result["words"])
    assert slice_bytes(result["romaji"], result["words"][1]["output_span"]) == "a soko"


def test_mapping_cannot_take_only_part_of_a_displayed_group(converter):
    override = {
        "id": "partial",
        "kind": "mapping",
        "raw_span": [0, 3],
        "expected_text": "食",
        "replacement": "shoku",
    }
    result = converter.convert(request(converter, "食べた", [override]))
    assert result["romaji"] == "tabeta"
    assert result["pending_overrides"][0]["id"] == "partial"
    assert all(w["mapping_reason"] == "cross_word_gemination" for w in result["words"][1:])


def test_canonical_command_does_not_resegment_explicit_spaces(converter):
    q = request(converter, "ゆこう はっかいろ")
    q["command"] = "canonical"
    assert converter.convert(q)["canonical_reading"] == {
        "hiragana": "ゆこう はっかいろ",
        "romaji": "yukou hakkairo",
    }
    q["raw_line"] = "行こう"
    with pytest.raises(ValueError, match="canonical"):
        converter.convert(q)
