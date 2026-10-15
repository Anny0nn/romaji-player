import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tifa_helper import (
    Aligner,
    pronunciation,
    read_manifest,
    result_line,
    retain_interval,
    vowel_extensions,
)


def test_imported_numerical_code_matches_reviewed_upstream():
    folder = Path(__file__).resolve().parents[1] / "vendor"
    local = json.loads((folder / "local-sha256.json").read_text())
    for name, expected in json.loads(
        (folder / "original-sha256.json").read_text()
    ).items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == local.get(
            name, expected
        )


def test_unsupported_word_keeps_neighbors_and_multi_part_reading_atomic():
    from g2p.converters.base import G2PGroup, G2PReading, G2PWord
    from lib.vocabulary import Vocabulary

    class Converter:
        def convert(self, text):
            return [
                G2PWord(
                    text=part, readings=[G2PReading(paths=[[G2PGroup(part, [part])]])]
                )
                for part in text.split()
            ]

    aligner = Aligner.__new__(Aligner)
    aligner.vocabulary = Vocabulary(symbol_to_id={"ja/あ": 3, "en/you": 4, "en/can": 5})
    aligner.converters = {"ja": Converter(), "en": Converter()}
    targets = [
        {"text": "あ", "romaji": "a"},
        {"text": "unknown", "romaji": "unknown"},
        {"text": "You can", "romaji": "You can"},
        {"text": "あ", "romaji": "a"},
    ]
    words, indices = aligner.words(targets)
    assert indices == [0, 2, 3]
    assert [word.language for word in words] == ["ja", "en", "ja"]
    assert len(words[1].readings[0].paths[0]) == 2
    assert words[0].text == words[2].text


def test_silence_never_forces_positive_spans_or_loads_pronunciations():
    aligner = Aligner.__new__(Aligner)
    target = {"raw_span": [6, 9], "text": "は", "romaji": "wa"}
    assert aligner.align(np.zeros(16000, dtype=np.float32), [target]) == [
        {"raw_span": [6, 9], "text": "は", "start_ms": -1, "end_ms": -1}
    ]


def test_pronunciation_selection_is_opt_in_and_keeps_complete_word_alternatives():
    from types import SimpleNamespace

    import torch
    from lib.path_traversal import materialize_paths

    # Second candidate adds a phone; choosing individual tokens would mix readings.
    tensors = {
        "paths": torch.tensor([[[3, 4], [0, 5], [6, 6]]]),
        "words": torch.tensor([[1, 1, 2]]),
        "groups": torch.tensor([[[1, 1], [0, 2], [1, 1]]]),
        "candidates": torch.tensor([[[True, True], [True, False]]]),
    }
    calls = []
    spec = object()

    class Backend:
        def score(self, received, **kwargs):
            assert received is spec
            assert kwargs["unit"] == "levenshtein"
            calls.append(kwargs)
            return SimpleNamespace(choices=torch.tensor([[2, 1]]))

    aligner = Aligner.__new__(Aligner)
    aligner.backend = Backend()
    original = aligner.pronunciation_choices(spec, tensors, False)
    assert original.tolist() == [[1, 1]]
    assert calls == []
    selected = aligner.pronunciation_choices(spec, tensors, True)
    tokens, owners, _ = materialize_paths(
        tensors["paths"], tensors["words"], tensors["groups"], selected
    )
    assert tokens.tolist() == [[4, 5, 6]]
    assert owners.tolist() == [[1, 1, 2]]
    assert len(calls) == 1


def test_missing_kana_dictionary_entry_preserves_supported_source_words(tmp_path):
    from g2p.converters.japanese import JapaneseKanaConverter
    from lib.vocabulary import Vocabulary

    dictionary = tmp_path / "kana.txt"
    dictionary.write_text("a\ta\n")
    converter = JapaneseKanaConverter(str(dictionary))
    with pytest.raises(KeyError):
        converter.convert("あぁ")
    aligner = Aligner.__new__(Aligner)
    aligner.vocabulary = Vocabulary(symbol_to_id={"ja/a": 3})
    aligner.converters = {"ja": converter}
    words, indices = aligner.words(
        [
            {"text": "あ", "romaji": "a"},
            {"text": "あぁ", "romaji": "aa"},
            {"text": "あ", "romaji": "a"},
        ]
    )
    assert indices == [0, 2]
    assert len(words) == 2
    words, indices = aligner.words(
        [{"text": "あぁ", "romaji": "aa"}], expand_vowels=True
    )
    assert indices == [0]
    assert words[0].text == "あぁ"
    assert [g.phonemes for g in words[0].readings[0].paths[0]] == [["a"], ["a"]]


def test_phonetic_alias_keeps_one_source_word_and_rejects_unknown_phone():
    from lib.vocabulary import Vocabulary

    aligner = Aligner.__new__(Aligner)
    aligner.vocabulary = Vocabulary(symbol_to_id={"ja/a": 3, "ja/b": 4})
    aligner.converters = {}
    targets = [{"text": "word", "romaji": "word", "raw_span": [0, 4]}]
    words, indices = aligner.words(targets, phonetic_aliases={0: ["b", "a"]})
    assert indices == [0] and len(words) == 1
    assert words[0].text == "word" and words[0].language == "ja"
    assert [g.phonemes for g in words[0].readings[0].paths[0]] == [["b", "a"]]
    assert aligner.words(targets, phonetic_aliases={0: ["unknown"]}) == ([], [])
    with pytest.raises(ValueError, match="ownership"):
        aligner.words(targets, phonetic_aliases={1: ["a"]})


def test_explicit_english_phone_hypothesis_keeps_language_inventory_and_source_owner():
    from lib.vocabulary import Vocabulary

    aligner = Aligner.__new__(Aligner)
    aligner.vocabulary = Vocabulary(symbol_to_id={"en/k": 3, "en/aa": 4, "ja/a": 5})
    aligner.converters = {}
    targets = [{"text": "word", "romaji": "word", "raw_span": [8, 12]}]
    words, indices = aligner.words(
        targets, phonetic_aliases={0: {"language": "en", "phones": ["k", "aa"]}}
    )
    assert indices == [0] and len(words) == 1
    assert words[0].language == "en"
    assert [g.phonemes for g in words[0].readings[0].paths[0]] == [["k", "aa"]]
    assert aligner.words(
        targets, phonetic_aliases={0: {"language": "en", "phones": ["a"]}}
    ) == ([], [])
    for alias in (
        {"language": "xx", "phones": ["k"]},
        {"language": "en", "phones": "aa"},
        {"language": "en", "phones": [False]},
    ):
        with pytest.raises(ValueError, match="hypothesis"):
            aligner.words(targets, phonetic_aliases={0: alias})


def test_explicit_pronunciation_can_cover_macron_source_without_rewriting_it():
    from lib.vocabulary import Vocabulary

    aligner = Aligner.__new__(Aligner)
    aligner.vocabulary = Vocabulary(symbol_to_id={"ja/y": 3, "ja/o": 4})
    aligner.converters = {}
    targets = [{"text": "yō", "romaji": "yō", "raw_span": [5, 8]}]
    assert aligner.words(targets) == ([], [])
    words, indices = aligner.words(targets, phonetic_aliases={0: ["y", "o", "o"]})
    assert indices == [0] and len(words) == 1
    assert words[0].text == "yō" and words[0].language == "ja"
    assert [g.phonemes for g in words[0].readings[0].paths[0]] == [["y", "o", "o"]]
    assert targets == [{"text": "yō", "romaji": "yō", "raw_span": [5, 8]}]
    assert aligner.words(targets, phonetic_aliases={0: ["unknown"]}) == ([], [])


def test_vowel_fallback_never_rewrites_valid_digraphs_or_guesses_other_kana():
    assert (
        vowel_extensions("あぁぁ いぃ うぅ えぇ おぉ アァ")
        == "あああ いい うう ええ おお アア"
    )
    for unchanged in (
        "うぁ",
        "きぇ",
        "ふぁ",
        "きゃ",
        "ティー",
        "ぁ",
        "あぃ",
        "っ",
        "アぁ",
    ):
        assert vowel_extensions(unchanged) == unchanged


def test_library_amplitude_diagnostics_cannot_corrupt_jsonl(capsys):
    class Backend:
        def align(self, samples, targets):
            print("max value is tensor(1.01)")
            return []

    assert json.loads(result_line(Backend(), 4, None, None)) == {
        "occurrence": 4,
        "units": [],
    }
    assert capsys.readouterr().out == ""


def manifest():
    text, romaji = "は".encode(), b"wa"
    return (
        struct.pack("<10I", 3, 1, 4, 0, 16000, 1, 6, 9, len(text), 0)[:-4]
        + text
        + struct.pack("<I", len(romaji))
        + romaji
    )


def test_source_anchor_and_pronunciation_survive_protocol(tmp_path):
    path = tmp_path / "crops.bin"
    path.write_bytes(manifest())
    assert read_manifest(path, 16000) == [
        (4, 0, 16000, [{"raw_span": [6, 9], "text": "は", "romaji": "wa"}])
    ]
    assert pronunciation("は", "wa") == ("わ", "ja")
    assert pronunciation("へ", "e") == ("え", "ja")
    assert pronunciation("は", "ha") == ("は", "ja")
    assert pronunciation("You", "You") == ("you", "en")
    assert pronunciation("桜", "sakura")[1] is None


@pytest.mark.parametrize("change", ["short", "trailing", "protocol", "bounds"])
def test_malformed_manifest_rejected(tmp_path, change):
    data = manifest()
    if change == "short":
        data = data[:-1]
    if change == "trailing":
        data += b"x"
    if change == "protocol":
        data = struct.pack("<I", 2) + data[4:]
    path = tmp_path / "crops.bin"
    path.write_bytes(data)
    with pytest.raises((ValueError, struct.error)):
        read_manifest(path, 15000 if change == "bounds" else 16000)


def test_incomplete_paths_and_obvious_mismatches_withhold_without_interpolation():
    spans = np.array([[10, 14], [14, 24], [24, 24]])
    similarity = np.ones((100, 3))
    indices = np.array([0, 1])
    assert retain_interval(spans, indices, similarity, 0.999, 1000) == (100, 240)
    assert retain_interval(spans, np.array([2]), similarity, 0.999, 1000) == (-1, -1)
    assert retain_interval(spans, indices, similarity, 0.4, 1000) == (-1, -1)
    assert retain_interval(spans, indices, -similarity, 0.999, 1000) == (-1, -1)
    assert retain_interval(spans, indices, similarity, float("nan"), 1000) == (-1, -1)
    assert retain_interval(spans, indices, similarity, 0.999, 200) == (-1, -1)


def test_one_uncertain_word_does_not_drop_neighboring_observed_endpoints():
    spans = np.array([[10, 24], [30, 44], [50, 64]])
    similarity = np.ones((100, 3))
    probabilities = [0.999, 0.96, 0.999]
    retained = [
        retain_interval(spans, np.array([index]), similarity, probability, 1000)
        for index, probability in enumerate(probabilities)
    ]
    assert retained == [(100, 240), (-1, -1), (500, 640)]
