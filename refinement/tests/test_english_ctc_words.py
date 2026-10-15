import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from english_ctc_words import verified_phone_views, word_observations


def test_aliases_to_blank_do_not_create_extra_model_classes():
    vocabulary = {"SP": 0, "AP": 0, "": 0, "k": 1, "aa": 2}
    logp = np.log(
        np.array(
            [[0.98, 0.01, 0.01]] * 2
            + [[0.01, 0.98, 0.01]] * 8
            + [[0.01, 0.01, 0.98]] * 10
            + [[0.98, 0.01, 0.01]] * 2
        )
    )
    source = [{"word": 0, "phone": "k"}, {"word": 0, "phone": "aa"}]
    units = word_observations(logp, source, vocabulary, [{"raw_span": [17, 23]}])
    assert units[0]["raw_span"] == [17, 23]
    assert (units[0]["start_ms"], units[0]["end_ms"]) == (20, 200)
    assert units[0]["minimum_phone_probability"] == pytest.approx(0.98)
    assert not verified_phone_views(units, length_ms=220)[0]["source_match"]
    assert all(
        u["source_match"]
        for u in verified_phone_views(
            [units[0], {**units[0], "raw_span": [24, 29]}], length_ms=220
        )
    )


def test_repeat_requires_blank_and_low_probability_phone_cannot_hide_in_vowel():
    vocabulary = {"SP": 0, "k": 1}
    source = [{"word": 0, "phone": "k"}] * 2
    targets = [{"raw_span": [0, 1]}]
    unit = word_observations(
        np.log(np.array([[0.05, 0.95]])), source, vocabulary, targets
    )[0]
    assert unit["start_ms"] == -1
    logp = np.log(
        np.array(
            [[0.99, 0.01]] * 2
            + [[0.1, 0.9]] * 5
            + [[0.99, 0.01]] * 5
            + [[0.7, 0.3]] * 5
            + [[0.99, 0.01]] * 2
        )
    )
    units = word_observations(logp, source, vocabulary, targets)
    assert units[0]["minimum_phone_probability"] < 0.45
    assert not verified_phone_views(units, length_ms=190)[0]["source_match"]


def test_invalid_probability_normalization_and_source_owners_are_rejected():
    vocabulary = {"SP": 0, "k": 1}
    targets = [{"raw_span": [0, 1]}]
    for matrix, owner in ((np.zeros((4, 2)), 0), (np.log(np.full((4, 2), 0.5)), 4)):
        with pytest.raises(ValueError):
            word_observations(
                matrix, [{"word": owner, "phone": "k"}], vocabulary, targets
            )
