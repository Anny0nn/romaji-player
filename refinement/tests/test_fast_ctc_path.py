"""Research verifier acceleration preserves the shipped decoder, including ties."""

import random
import sys
from pathlib import Path

import pytest

sys.path[:0] = [
    str(Path(__file__).resolve().parents[2] / "scripts"),
    str(Path(__file__).resolve().parents[1]),
]
from fast_ctc_path import ctc_path as fast
from refinement_policy import ctc_path as shipped


def test_replay_paths_match_shipped_repeats_impossible_targets_and_ties():
    randomizer = random.Random(1103)
    for _ in range(100):
        width = randomizer.randrange(2, 8)
        rows = [
            [float(randomizer.randrange(-4, 1)) for _ in range(width)]
            for _ in range(randomizer.randrange(1, 20))
        ]
        labels = [
            randomizer.randrange(1, width) for _ in range(randomizer.randrange(1, 12))
        ]
        assert fast(rows, labels) == shipped(rows, labels)
    assert fast([[-1, -1]] * 8, [1, 1, 1]) == shipped([[-1, -1]] * 8, [1, 1, 1])
    assert fast([[-1, -1]], [1, 1]) is None


@pytest.mark.parametrize(
    "rows,labels",
    [([[float("nan"), -1]], [1]), ([[-1, -1], [0]], [1]), ([[-1, -1]], [3])],
)
def test_invalid_input_matches_shipped_rejection(rows, labels):
    for implementation in (fast, shipped):
        with pytest.raises(ValueError):
            implementation(rows, labels)
