"""Exhaustive label-path checks of local contrastive singing evidence."""

import itertools
import math
import runpy
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from contrastive_phones import contrastive_score
from singing_phonemes import token_phones

local_observation = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "scripts/benchmark-contrastive-phones.py")
)["local_observation"]


def enumerate_hypotheses(logp, target, vocabulary):
    inverse = {i: token_phones(t) for t, i in vocabulary.items()}
    atoms = {p[0] for i, p in inverse.items() if i and len(p) == 1}
    target_mass, foil_mass = [], []
    for path in itertools.product(range(logp.shape[1]), repeat=len(logp)):
        phones, previous = [], None
        for label in path:
            if label and label != previous:
                phones.extend(inverse[label])
            previous = label
        if len(phones) != len(target):
            continue
        differences = [b for a, b in zip(target, phones, strict=True) if a != b]
        score = sum(logp[t, label] for t, label in enumerate(path))
        if not differences:
            target_mass.append(score)
        elif len(differences) == 1 and differences[0] in atoms:
            foil_mass.append(score)
    return [
        float(np.logaddexp.reduce(x)) if x else None for x in (target_mass, foil_mass)
    ]


@pytest.mark.parametrize(
    "target", [["k", "a"], ["a", "a"], ["k", "a", "a"], ["k", "a", "k", "a"], ["z"]]
)
def test_target_and_union_match_exhaustive_paths_including_mora_and_repeats(target):
    vocabulary = {"<blank>": 0, "k": 1, "a": 2, "ka": 3, "n": 4}
    logp = np.log(np.random.default_rng(41).dirichlet(np.ones(5), size=4))
    expected = enumerate_hypotheses(logp, target, vocabulary)
    result = contrastive_score(logp, 0, target, vocabulary)
    for key, value in zip(
        ("target_logp", "substitution_union_logp"), expected, strict=True
    ):
        assert (
            result[key] == pytest.approx(value)
            if value is not None
            else result[key] is None
        )
    assert result["blank_logp"] == pytest.approx(logp[:, 0].sum())


def test_atomic_inventory_does_not_invent_standalone_consonants_from_mora():
    vocabulary = {"<blank>": 0, "a": 1, "n": 2, "kya": 3}
    logp = np.log(np.full((4, 4), 0.25))
    result = contrastive_score(logp, 0, ["ky", "a"], vocabulary)
    assert result["substitution_inventory"] == ["a", "n"]
    assert result["target_logp"] == pytest.approx(
        enumerate_hypotheses(logp, ["ky", "a"], vocabulary)[0]
    )
    assert result["substitution_union_logp"] == pytest.approx(
        enumerate_hypotheses(logp, ["ky", "a"], vocabulary)[1]
    )


def test_english_phone_labels_remain_atomic_instead_of_becoming_japanese_tokens():
    vocabulary = {"<blank>": 0, "aa": 1, "ng": 2}
    logp = np.log(np.array([[0.1, 0.8, 0.1], [0.8, 0.1, 0.1]]))
    result = contrastive_score(
        logp, 0, ["aa"], vocabulary, token_expansions={1: ["aa"], 2: ["ng"]}
    )
    # All ways of collapsing to one 'aa': [blank,aa], [aa,blank], [aa,aa].
    assert result["target_logp"] == pytest.approx(math.log(0.01 + 0.64 + 0.08))
    assert result["substitution_union_logp"] == pytest.approx(
        math.log(0.01 + 0.08 + 0.01)
    )
    assert result["substitution_inventory"] == ["aa", "ng"]
    for expansions in ({1: ["aa"]}, {1: ["aa"], 2: []}, {1: ["aa"], 2: [None]}):
        with pytest.raises(ValueError, match="expansions"):
            contrastive_score(logp, 0, ["aa"], vocabulary, token_expansions=expansions)


def test_phonetic_contrast_changes_sign_for_an_actual_confounder():
    vocabulary = {"<blank>": 0, "a": 1, "i": 2}
    logp = np.log(np.array([[0.1, 0.8, 0.1], [0.8, 0.1, 0.1]]))
    assert contrastive_score(logp, 0, ["a"], vocabulary)["union_margin"] > 0
    assert contrastive_score(logp, 0, ["i"], vocabulary)["union_margin"] < 0


def test_observed_frames_come_from_the_best_target_path_and_do_not_split_a_mora():
    vocabulary = {"<blank>": 0, "a": 1, "k": 2, "ka": 3}
    logp = np.log(
        np.array(
            [
                [0.97, 0.01, 0.01, 0.01],
                [0.01, 0.01, 0.01, 0.97],
                [0.97, 0.01, 0.01, 0.01],
            ]
        )
    )
    path = contrastive_score(logp, 0, ["k", "a"], vocabulary, observe=True)["path"]
    assert path["first_frame"] == path["last_frame"] == 1
    assert path["mean_frame_probability"] == pytest.approx(0.97)
    assert path["logp"] == pytest.approx(3 * np.log(0.97))


def test_blank_need_not_be_zero_and_impossible_frames_remain_impossible():
    logp = np.log(np.array([[0.1, 0.8, 0.1], [0.8, 0.1, 0.1]]))
    expected = contrastive_score(logp, 0, ["a"], {"<blank>": 0, "a": 1, "i": 2})
    actual = contrastive_score(
        logp[:, [1, 2, 0]], 2, ["a"], {"a": 0, "i": 1, "<blank>": 2}
    )
    assert actual == expected
    impossible = contrastive_score(
        np.array([[-np.inf, 0.0, -np.inf]]), 0, ["i"], {"<blank>": 0, "a": 1, "i": 2}
    )
    assert impossible["target_logp"] is None
    assert impossible["union_margin"] is None


@pytest.mark.parametrize(
    "matrix",
    [np.array([[np.nan, 0.0]]), np.zeros((2, 2)), np.array([[-np.inf, -np.inf]])],
)
def test_bad_posterior_cannot_produce_a_lexical_score(matrix):
    with pytest.raises(ValueError):
        contrastive_score(matrix, 0, ["a"], {"<blank>": 0, "a": 1})


def test_aliased_labels_and_unbounded_inputs_are_rejected():
    logp = np.log(np.full((2, 2), 0.5))
    with pytest.raises(ValueError):
        contrastive_score(logp, 0, ["a"], {"a": 1, "i": 1})
    with pytest.raises(ValueError):
        contrastive_score(logp, 0, [], {"a": 1})


def test_local_clock_keeps_actual_receptive_frame_edges_and_never_extends_a_peak():
    vocabulary = {"<blank>": 0, "a": 1, "i": 2}
    probabilities = np.tile([0.98, 0.01, 0.01], (30, 1))
    probabilities[10:15] = [0.01, 0.98, 0.01]
    result = local_observation(
        np.log(probabilities), 0, ["a"], vocabulary, {"start_ms": 200, "end_ms": 305}
    )
    assert result["paired"]
    assert result["start_ms"] == 200
    assert (
        result["end_ms"] == 305
    )  # last observed frame starts at 280; receptive field is 25ms
    probabilities[11:15] = [0.98, 0.01, 0.01]
    narrow = local_observation(
        np.log(probabilities), 0, ["a"], vocabulary, {"start_ms": 200, "end_ms": 305}
    )
    assert narrow["lexical_pass"]
    assert narrow["end_ms"] - narrow["start_ms"] == 25
    assert not narrow["paired"]


def test_cut_edges_unsupported_phones_and_outside_candidate_clocks_are_withheld():
    vocabulary = {"<blank>": 0, "a": 1, "i": 2}
    probabilities = np.tile([0.98, 0.01, 0.01], (20, 1))
    probabilities[:5] = [0.01, 0.98, 0.01]
    logp = np.log(probabilities)
    edge = local_observation(logp, 0, ["a"], vocabulary, {"start_ms": 0, "end_ms": 105})
    assert edge["lexical_pass"]
    assert not edge["paired"]
    for phones, clock in (
        (["unsupported:kanji"], {"start_ms": 20, "end_ms": 105}),
        (["a"], {"start_ms": -1, "end_ms": -1}),
        (["a"], {"start_ms": 200, "end_ms": 900}),
    ):
        assert local_observation(logp, 0, phones, vocabulary, clock) == {
            "eligible": False
        }
