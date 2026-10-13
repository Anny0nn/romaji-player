"""Recorded-free CTC checks, including the recognizer's mixed mora vocabulary."""

import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa/vendor")]
from singing_phonemes import kana_phones, lattice_score, token_phones


def exhaustive(logp, blank, phones, vocabulary):
    inverse = {i: token for token, i in vocabulary.items()}
    values = []
    for path in itertools.product(range(logp.shape[1]), repeat=len(logp)):
        expansion, last = [], None
        for token in path:
            if token != last and token != blank:
                expansion.extend(token_phones(inverse[token]))
            last = token
        if expansion == phones:
            values.append(sum(logp[t, label] for t, label in enumerate(path)))
    return float(np.logaddexp.reduce(values)) if values else None


@pytest.mark.parametrize(
    "phones", [["k", "a"], ["a", "a"], ["k", "a", "k", "a"], ["z"]]
)
def test_mixed_mora_and_phone_forward_sum_matches_exhaustive_ctc(phones):
    vocabulary = {"<blank>": 0, "k": 1, "a": 2, "ka": 3}
    logp = np.log(
        np.array([[0.2, 0.3, 0.3, 0.2], [0.1, 0.2, 0.3, 0.4], [0.4, 0.2, 0.3, 0.1]])
    )
    expected = exhaustive(logp, 0, phones, vocabulary)
    actual = lattice_score(logp, 0, phones, vocabulary)
    assert actual == pytest.approx(expected) if expected is not None else actual is None


def test_pronunciation_keeps_gemination_nasal_particles_and_inflection():
    assert kana_phones("やみよ") == ["y", "a", "m", "i", "y", "o"]
    assert kana_phones("ゆこう") == ["y", "u", "k", "o", "u"]
    assert kana_phones("はっかいろ") == ["h", "a", "cl", "k", "a", "i", "r", "o"]
    assert kana_phones("しんや") == ["sh", "i", "N", "y", "a"]
    assert kana_phones("は", "wa") == ["w", "a"]
    assert kana_phones("へ", "e") == ["e"]
    assert kana_phones("闇夜") is None
    assert kana_phones("ー") is None
    assert kana_phones("ゆく") != kana_phones("ゆこう")


def test_nonfinite_or_invalid_vocabulary_cannot_score_a_candidate():
    with pytest.raises(ValueError):
        lattice_score(np.array([[math.nan, 0]]), 0, ["a"], {"a": 1})
    with pytest.raises(ValueError):
        lattice_score(np.array([[0.0, 0.0]]), 0, ["a"], {"a": 9})
    assert lattice_score(np.zeros((1, 2)), 0, ["a", "a"], {"a": 1}) is None
