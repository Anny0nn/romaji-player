"""Bounded mapping and independent rejection, without real song inputs or models."""

import io
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa"), str(ROOT / "tifa/vendor")]
from reading_policy import decision, verify
from reading_repair import mapped_candidates, source_text


@pytest.mark.parametrize("language", ["ja", "en", None])
def test_blind_language_trials_keep_transcription_task_and_release_models(
    monkeypatch, tmp_path, language
):
    import refinement_helper
    from reading_repair import transcribe

    holder = SimpleNamespace(model=object(), model_path="loaded")
    mx = ModuleType("mlx.core")
    mx.set_memory_limit = lambda _: None
    mx.set_cache_limit = lambda _: None
    whisper = ModuleType("mlx_whisper")
    implementation = ModuleType("mlx_whisper.transcribe")
    implementation.ModelHolder = holder
    calls, released = [], []

    def decode(samples, **options):
        calls.append(options)
        return {"segments": [{"text": "synthetic"}], "language": "en"}

    whisper.transcribe = decode
    monkeypatch.setitem(sys.modules, "mlx", ModuleType("mlx"))
    monkeypatch.setitem(sys.modules, "mlx.core", mx)
    monkeypatch.setitem(sys.modules, "mlx_whisper", whisper)
    monkeypatch.setitem(sys.modules, "mlx_whisper.transcribe", implementation)
    monkeypatch.setattr(refinement_helper, "release", lambda: released.append(True))
    diagnostics = {}
    assert transcribe(
        np.ones(16000, dtype=np.float32),
        tmp_path,
        tmp_path / "progress",
        "fixture",
        language=language,
        diagnostics=diagnostics,
    ) == [{"text": "synthetic"}]
    assert calls[0]["language"] == language
    assert calls[0]["task"] == "transcribe"
    assert calls[0]["initial_prompt"] is None
    assert calls[0]["condition_on_previous_text"] is False
    assert diagnostics == {"detected_language": "en"}
    assert holder.model is None and holder.model_path is None
    assert released == [True]


def test_optional_transcript_rejections_are_withheld_but_protocol_errors_remain_fatal():
    import reading_repair

    segments = [{"words": [{"word": "桜", "start": 0, "end": 1, "probability": 1}]}]

    class RejectingConverter:
        def __init__(self, error):
            self.error = error

        def convert(self, _request, candidates=False):
            raise self.error

    assert (
        reading_repair.transcript_matches(
            segments,
            0,
            16000,
            [],
            {},
            RejectingConverter(reading_repair.ConversionRejected()),
        )
        == []
    )
    with pytest.raises(ValueError, match="Stale"):
        reading_repair.transcript_matches(
            segments, 0, 16000, [], {}, RejectingConverter(ValueError("Stale"))
        )
    inputs = {"requests": [{"occurrence_id": 0}], "protected": []}
    with pytest.raises(reading_repair.ConversionRejected):
        reading_repair.propose(
            inputs,
            [(0, 0, 16000, [])],
            RejectingConverter(reading_repair.ConversionRejected()),
            [],
            [],
            {},
            {},
            [],
        )


def test_unconvertible_optional_reading_does_not_discard_other_valid_candidates(
    monkeypatch,
):
    import reading_repair

    candidates = [{"hiragana": "bad"}, {"hiragana": "さくら"}]
    monkeypatch.setattr(reading_repair, "mapped_candidates", lambda *_: candidates)
    monkeypatch.setattr(reading_repair, "output_words", lambda _: [])

    class StubConverter:
        def convert(self, _):
            return {}

        def canonical(self, kana, _):
            if kana == "bad":
                raise reading_repair.ConversionRejected()
            return {"hiragana": kana, "romaji": "sakura"}

    segments = [{"words": [{"word": "桜", "start": 0, "end": 1, "probability": 1}]}]
    assert reading_repair.transcript_matches(
        segments, 0, 16000, [], {}, StubConverter()
    ) == [{"hiragana": "さくら", "romaji": "sakura"}]


@pytest.mark.parametrize(
    "reply_id,protocol,typed",
    [(1, 2, True), (2, 2, False), (1, 1, False), (1, 9, False)],
)
def test_compact_rejections_require_matching_protocol_and_request_identity(
    reply_id, protocol, typed
):
    from reading_repair import ConversionRejected, Converter

    converter = Converter.__new__(Converter)
    response = {
        "protocol_version": protocol,
        "request_id": reply_id,
        "error": "invalid_request",
    }
    converter.process = SimpleNamespace(
        stdin=io.BytesIO(), stdout=io.BytesIO(json.dumps(response).encode() + b"\n")
    )
    with pytest.raises(ValueError) as raised:
        converter.exchange({"protocol_version": 2, "request_id": 1})
    assert isinstance(raised.value, ConversionRejected) == typed


def test_large_valid_reply_keeps_identity_checks_and_the_following_reply():
    from reading_repair import REQUEST_LIMIT, Converter

    response = {
        "protocol_version": 2,
        "request_id": 1,
        "snapshot_id": "frozen",
        "conversion_signature": "a" * 64,
        "words": [{"synthetic_word_record": "x" * 460} for _ in range(200)],
    }
    raw = json.dumps(response).encode() + b"\n"
    assert len(raw) > REQUEST_LIMIT
    second = {**response, "request_id": 2, "words": []}
    converter = Converter.__new__(Converter)
    converter.process = SimpleNamespace(
        stdin=io.BytesIO(),
        stdout=io.BytesIO(raw + json.dumps(second).encode() + b"\n"),
    )
    request = {
        "protocol_version": 2,
        "request_id": 1,
        "snapshot_id": "frozen",
        "expected_conversion_signature": "a" * 64,
    }
    assert converter.exchange(request) == response
    assert converter.exchange({**request, "request_id": 2}) == second
    converter.process.stdout = io.BytesIO(raw)
    with pytest.raises(ValueError, match="Stale"):
        converter.exchange({**request, "snapshot_id": "different"})
    converter.process.stdout = io.BytesIO(raw)
    with pytest.raises(ValueError, match="changed"):
        converter.exchange({**request, "expected_conversion_signature": "b" * 64})


def test_request_and_reply_limits_still_reject_oversize_or_truncated_messages():
    from reading_repair import REPLY_LIMIT, REQUEST_LIMIT, Converter

    converter = Converter.__new__(Converter)
    converter.process = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO())
    with pytest.raises(ValueError, match="request exceeds"):
        converter.exchange({"raw_line": "x" * REQUEST_LIMIT})
    assert converter.process.stdin.getvalue() == b""
    for reply in (b" " * REPLY_LIMIT + b"\n", b"{}"):
        converter.process.stdout = io.BytesIO(reply)
        with pytest.raises(ValueError, match="reply limit"):
            converter.exchange({"request_id": 1})


def words(*values):
    return [{"text": t, "romaji": r} for t, r in values]


def test_model_target_rejects_changed_reading_and_dictionary_shadow_on_a_saved_edit():
    import copy

    from reading_repair import alignment_target

    converted = {"hiragana": "ゆこう", "romaji": "yukou"}
    word = {
        "raw_span": [0, 9],
        "expected_text": "行こう",
        "hiragana_span": [0, 9],
        "output_span": [0, 5],
        "override_id": "saved",
        "reading": {
            "written": "ゆこう",
            "romaji": "yukou",
            "alignment_text": "ゆこう",
            "pronunciation": None,
            "origin": "saved",
        },
    }
    assert alignment_target("行こう", converted, word)["text"] == "ゆこう"
    for change in [
        {"alignment_text": "いこう"},
        {"pronunciation": "いこー"},
        {"romaji": "ikou"},
    ]:
        damaged = copy.deepcopy(word)
        damaged["reading"].update(change)
        with pytest.raises(ValueError, match="Inconsistent"):
            alignment_target("行こう", converted, damaged)


def test_transcript_mapping_groups_split_tokens_through_stable_neighbors():
    old = words(
        ("あおい", "aoi"),
        ("ちきゅう", "chikyuu"),
        ("に", "ni"),
        ("ありがとう", "arigatou"),
    )
    new = words(
        ("あおい", "aoi"),
        ("ほ", "ho"),
        ("し", "shi"),
        ("に", "ni"),
        ("ありがとう", "arigatou"),
    )
    assert mapped_candidates(old, new) == [
        {"first": 1, "last": 2, "hiragana": "ほ し", "romaji": "ho shi"}
    ]
    assert (
        mapped_candidates(
            old, words(("さくら", "sakura"), ("もり", "mori"), ("あるく", "aruku"))
        )
        == []
    )
    assert (
        mapped_candidates(
            words(("ちきゅう", "chikyuu"), ("に", "ni")),
            words(("ほし", "hoshi"), ("に", "ni")),
        )
        == []
    )


def test_invalid_utf8_and_incomplete_source_spans_are_rejected():
    assert source_text("ｶﾞ 闇夜", [7, 13]) == "闇夜"
    for bounds in ([1, 3], [-1, 3], [0, 999], [True, 3], [3, 3]):
        with pytest.raises((ValueError, UnicodeDecodeError)):
            source_text("闇夜", bounds)


def test_correlated_views_require_absolute_support_context_and_finite_measurements():
    good = {"gain": 12, "margin": 9, "probability": 0.7, "context": 0.8}
    assert decision([good, good])
    for key, bad in [
        ("gain", 7.999),
        ("margin", 7.999),
        ("probability", 0.449999),
        ("context", 0.49999),
        ("gain", float("nan")),
    ]:
        assert not decision([good, {**good, key: bad}])
    assert not decision([good])


def test_independent_model_compares_all_alternatives_and_vetoes_contradiction(
    monkeypatch,
):
    import singing_phonemes

    scores = {
        "あおい いこう よ": 10.0,
        "あおい ゆこう よ": 11.0,
        "あおい ゆく よ": 15.0,
    }
    monkeypatch.setattr(
        singing_phonemes,
        "phrase_score",
        lambda _p, _b, w, _v: scores[" ".join(x["text"] for x in w)],
    )
    values = words(("あおい", "aoi"), ("いこう", "ikou"), ("よ", "yo"))
    candidate = {"hiragana": "ゆこう", "romaji": "yukou"}
    evidence = verify(
        values,
        1,
        candidate,
        [{"hiragana": "ゆく", "romaji": "yuku"}],
        np.zeros((1, 1)),
        0,
        {},
    )
    assert evidence["gain_milli"] == 1000
    assert evidence["margin_milli"] == -4000
    assert not evidence["supported"]
    scores["あおい ゆく よ"] = 11.5
    assert verify(values, 1, candidate, [], np.zeros((1, 1)), 0, {})["supported"]


def test_source_envelope_rejects_punctuation_gaps_partial_words_and_protected_groups():
    from reading_repair import complete_envelope

    def word(span):
        return {"raw_span": span, "mapping_status": "mapped", "override_id": None}

    assert complete_envelope(
        "闇夜 道", {"words": [word([0, 6]), word([7, 10])]}, [0, 10]
    )
    assert not complete_envelope(
        "闇夜、道", {"words": [word([0, 6]), word([9, 12])]}, [0, 12]
    )
    assert not complete_envelope(
        "闇夜 道", {"words": [word([0, 6]), word([7, 10])]}, [0, 3]
    )
    assert not complete_envelope(
        "闇夜", {"words": [{**word([0, 6]), "override_id": "user"}]}, [0, 6]
    )


def test_conflicting_repeat_or_saved_correction_withholds_shared_reading(monkeypatch):
    import reading_repair

    targets = [
        {"raw_span": [0, 6], "text": "あんや", "romaji": "anya"},
        {"raw_span": [6, 9], "text": "を", "romaji": "o"},
        {"raw_span": [9, 15], "text": "あるく", "romaji": "aruku"},
    ]

    class StubConverter:
        def convert(self, request, candidates=False):
            return {
                "words": [
                    {
                        "raw_span": t["raw_span"],
                        "override_id": None,
                        "mapping_status": "mapped",
                    }
                    for t in targets
                ],
                "reading_candidates": [
                    {
                        "raw_span": [0, 6],
                        "candidates": [
                            {"hiragana": "あんや", "romaji": "anya"},
                            {"hiragana": "やみよ", "romaji": "yamiyo"},
                        ],
                    }
                ],
            }

    def selection(
        _words, _index, _candidates, views, _vocabulary, include_baseline=False
    ):
        baseline = views[0][0] == 0
        return {
            "hiragana": "あんや" if baseline else "やみよ",
            "romaji": "anya" if baseline else "yamiyo",
            "baseline": baseline,
            "acoustic_pass": not baseline,
            "views": [{"gain": 20, "margin": 20, "probability": 0.9, "context": 1}] * 2,
        }

    monkeypatch.setattr(reading_repair, "rank", selection)
    monkeypatch.setattr(
        reading_repair,
        "verify",
        lambda *args, **kw: {
            "gain_milli": 10000,
            "margin_milli": 10000,
            "phone_ratio_ppm": 1500000,
            "transcript_supported": False,
            "supported": True,
        },
    )
    requests = [
        {"occurrence_id": i, "raw_line": "闇夜を歩く", "overrides": []}
        for i in range(2)
    ]
    crops = [(i, 0, 16000, targets) for i in range(2)]
    views = [[(1, 0), (0, 0)]] * 2
    inputs = {"requests": requests, "protected": []}
    assert reading_repair.propose(
        inputs, crops, StubConverter(), views, [(None, 0)] * 2, {}, {}, []
    ) == ([], [])
    inputs["protected"] = [{"occurrence_id": 1, "raw_span": [0, 6]}]
    views = [[(1, 0), (1, 0)]] * 2
    assert reading_repair.propose(
        inputs, crops, StubConverter(), views, [(None, 0)] * 2, {}, {}, []
    ) == ([], [])
