"""Exact research replay of refinement_policy.ctc_path with NumPy state updates.

The hundreds of verifier trials reuse the app's gates. This changes computation
cost only: the same predecessor order, float64 scores and CTC repeat rules apply.
Production uses its existing implementation.
"""

import math


def ctc_path(rows, labels, blank=0):
    import numpy as np

    if not rows or not labels or any(i == blank for i in labels):
        return None
    width = len(rows[0])
    if (
        not 0 <= blank < width
        or any(len(row) != width for row in rows)
        or any(i < 0 or i >= width for i in labels)
    ):
        raise ValueError("Invalid CTC vocabulary or matrix.")
    matrix = np.asarray(rows, dtype=np.float64)
    if not np.isfinite(matrix).all():
        raise ValueError("Nonfinite CTC evidence.")
    states = np.full(2 * len(labels) + 1, blank, dtype=np.int64)
    states[1::2] = labels
    size = len(states)
    indices = np.arange(size)
    parents = np.column_stack(
        (indices, np.maximum(indices - 1, 0), np.maximum(indices - 2, 0))
    )
    parents[0, 1] = size
    permitted = (
        (indices > 1)
        & (states != blank)
        & (states != states[np.maximum(indices - 2, 0)])
    )
    parents[~permitted, 2] = size
    previous = np.full(size + 1, -np.inf)
    previous[0] = 0.0
    back = []
    for row in matrix:
        options = previous[parents]
        chosen = options.argmax(axis=1)
        sources = parents[indices, chosen]
        previous[:size] = options[indices, chosen] + row[states]
        back.append(sources)
    state = max((size - 1, size - 2), key=lambda s: previous[s])
    if not math.isfinite(previous[state]):
        return None
    path = []
    for sources in reversed(back):
        path.append(int(state))
        state = sources[state]
    return path[::-1]
