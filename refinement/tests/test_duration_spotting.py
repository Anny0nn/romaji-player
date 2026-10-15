"""Exhaustive duration/placement checks, independent of any singing model."""

import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from duration_spotting import contrast_pronunciation, spot_word


def test_marginal_and_map_equal_exhaustive_complete_state_placements():
    emissions = np.array([[-1, -4], [-0.5, -3], [-3, -0.5], [-4, -2], [-1, -1]])
    background = np.full(5, -2.0)
    duration = np.log(np.array([[0, 0.7, 0.3], [0, 0.4, 0.6]]) + 1e-300)
    duration[:, 0] = -np.inf
    paths = []
    for ds in itertools.product((1, 2), repeat=2):
        for start in range(6 - sum(ds)):
            end, value = start, -math.log(6)
            prior = value
            for state, length in enumerate(ds):
                value += duration[state, length]
                prior += duration[state, length]
                value += (
                    emissions[end : end + length, state]
                    - background[end : end + length]
                ).sum()
                end += length
            paths.append((value, prior, start, end))
    result = spot_word(emissions, background, duration)
    mass = float(np.logaddexp.reduce([p[0] for p in paths]))
    normalizer = float(np.logaddexp.reduce([p[1] for p in paths]))
    assert result["conditional_log_likelihood_ratio"] == pytest.approx(
        mass - normalizer
    )
    assert result["fit_prior_log_mass"] == pytest.approx(normalizer)
    best = max(paths)
    assert [result["first_frame"], result["last_frame_exclusive"]] == list(best[2:])
    for key, column in (("start_probabilities", 2), ("end_probabilities", 3)):
        expected = [
            sum(math.exp(p[0] - mass) for p in paths if p[column] == t)
            for t in range(6)
        ]
        assert result[key] == pytest.approx(expected)


def test_background_equal_to_target_has_zero_ratio_for_any_window_length():
    for length in (2, 5, 20):
        densities = np.full((length, 2), -3.0)
        result = spot_word(
            densities,
            densities[:, 0],
            np.array([[-np.inf, -math.log(2), -math.log(2)]] * 2),
        )
        assert result["conditional_log_likelihood_ratio"] == pytest.approx(0)


def test_repeated_acoustic_occurrences_remain_ambiguous_without_inventing_an_average_clock():
    target = np.array([[-6.0], [3.0], [-6.0], [-6.0], [3.0], [-6.0]])
    result = spot_word(target, np.zeros(6), np.array([[-np.inf, 0.0]]))
    assert result["first_frame"] in (1, 4)
    assert result["last_frame_exclusive"] == result["first_frame"] + 1
    assert result["start_90pct_frames"] == [1, 4]
    assert result["end_90pct_frames"] == [2, 5]


def test_all_source_states_consume_frames_and_impossible_word_stays_unplaced():
    assert (
        spot_word(np.zeros((1, 2)), np.zeros(1), np.array([[-np.inf, 0], [-np.inf, 0]]))
        is None
    )


@pytest.mark.parametrize(
    "change", ["nan", "zero_duration", "unnormalized", "dimensions"]
)
def test_invalid_input_cannot_create_a_measured_word(change):
    emissions, background = np.zeros((4, 1)), np.zeros(4)
    duration = np.array([[-np.inf, 0.0]])
    if change == "nan":
        emissions[0] = np.nan
    elif change == "zero_duration":
        duration = np.array([[0.0, -np.inf]])
    elif change == "unnormalized":
        duration[0, 1] = -2
    else:
        background = np.zeros(3)
    with pytest.raises(ValueError):
        spot_word(emissions, background, duration)


def test_pronunciation_contrast_matches_exhaustive_complete_sequence_sums():
    emissions = np.array([[-0.2, -3, -1], [-2, -0.1, -1], [-3, -0.4, -1]])
    background = np.full(3, -1.0)
    durations = np.array(
        [
            [-np.inf, math.log(0.3), math.log(0.7)],
            [-np.inf, 0, -np.inf],
            [-np.inf, math.log(0.8), math.log(0.2)],
        ]
    )
    phones, target = [[0], [1, 2], [2]], [0, 2]

    def exhaustive(sequence):
        states = [state for phone in sequence for state in phones[phone]]
        scores, priors = [], []
        for lengths in itertools.product((1, 2), repeat=len(states)):
            for start in range(4 - sum(lengths)):
                value = prior = -math.log(4)
                for state, length in zip(states, lengths, strict=True):
                    prior += durations[state, length]
                    value += (
                        durations[state, length]
                        + (
                            emissions[start : start + length, state]
                            - background[start : start + length]
                        ).sum()
                    )
                    start += length
                scores.append(value)
                priors.append(prior)
        fit = float(np.logaddexp.reduce(priors))
        return float(np.logaddexp.reduce(scores)) - fit if math.isfinite(fit) else None

    result = contrast_pronunciation(emissions, background, durations, phones, target)
    assert result["target_conditional_llr"] == pytest.approx(exhaustive(target))
    alternatives = []
    for observed in result["alternatives"]:
        sequence = list(target)
        sequence[observed["position"]] = observed["phone"]
        expected = exhaustive(sequence)
        assert observed["conditional_llr"] == pytest.approx(expected)
        if expected is not None:
            alternatives.append(expected)
    total = float(np.logaddexp.reduce(alternatives))
    assert result["substitution_sum_conditional_llr"] == pytest.approx(total)
    assert result["substitution_margin"] == pytest.approx(exhaustive(target) - total)


def test_identical_phone_densities_cannot_win_by_short_window_prior_bias():
    emissions = np.full((5, 3), -2.0)
    durations = np.array(
        [
            [-np.inf, 0, -np.inf],
            [-np.inf, -np.inf, 0],
            [-np.inf, math.log(0.5), math.log(0.5)],
        ]
    )
    result = contrast_pronunciation(
        emissions, emissions[:, 0], durations, [[0], [1], [2]], [0, 0]
    )
    assert result["target_conditional_llr"] == pytest.approx(0)
    assert result["substitution_margin"] == pytest.approx(-math.log(4))
    assert all(a["conditional_llr"] == pytest.approx(0) for a in result["alternatives"])


@pytest.mark.parametrize(
    "phones,target",
    [([[0], [0]], [0]), ([[0], []], [0]), ([[0], [1]], [True]), ([[0], [5]], [0])],
)
def test_aliased_or_invalid_phone_paths_cannot_inflate_alternative_evidence(
    phones, target
):
    with pytest.raises(ValueError):
        contrast_pronunciation(
            np.zeros((3, 2)), np.zeros(3), np.array([[-np.inf, 0]] * 2), phones, target
        )
