"""Observed English phone paths on HubertFA's 10 ms CTC output grid.

CTC and alignment heads share an encoder; they are not independent families.
This is pronunciation evidence, never orthographic gold or timestamp interpolation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "refinement"))
from refinement_policy import ctc_path


def word_observations(logp, reference, vocabulary, targets):
    import numpy as np

    if (
        logp.ndim != 2
        or set(vocabulary.values()) != set(range(logp.shape[1]))
        or not np.isfinite(logp).all()
        or (logp > 0).any()
        or not np.allclose(np.logaddexp.reduce(logp, axis=1), 0, atol=1e-4)
    ):
        raise ValueError("Invalid unmasked singing CTC probabilities.")
    result = [
        {
            "raw_span": t["raw_span"],
            "start_ms": -1,
            "end_ms": -1,
            "mean_probability": 0.0,
            "minimum_phone_probability": 0.0,
            "greedy_agreement": 0.0,
            "minimum_phone_greedy_agreement": 0.0,
            "first_phone_greedy_agreement": 0.0,
            "last_phone_greedy_agreement": 0.0,
        }
        for t in targets
    ]
    if not reference:
        return result
    if any(
        type(r["word"]) is not int or not 0 <= r["word"] < len(targets)
        for r in reference
    ):
        raise ValueError("Singing CTC changed original word ownership.")
    labels = [vocabulary[r["phone"]] for r in reference]
    if any(label == 0 for label in labels):
        raise ValueError("Lexical phone path contains blank/silence.")
    path = ctc_path(logp.tolist(), labels, 0)
    if path is None:
        return result
    path = np.asarray(path)
    greedy = logp.argmax(axis=1)
    for owner, unit in enumerate(result):
        indices = [i for i, r in enumerate(reference) if r["word"] == owner]
        if not indices or indices != list(range(indices[0], indices[-1] + 1)):
            continue
        frames = [np.flatnonzero(path == 2 * i + 1) for i in indices]
        if any(not len(f) for f in frames):
            continue
        probabilities = [
            float(np.exp(logp[f, labels[i]]).mean())
            for i, f in zip(indices, frames, strict=True)
        ]
        agreement = [
            float((greedy[f] == labels[i]).mean())
            for i, f in zip(indices, frames, strict=True)
        ]
        unit.update(
            start_ms=int(frames[0][0]) * 10,
            end_ms=(int(frames[-1][-1]) + 1) * 10,
            mean_probability=sum(probabilities) / len(probabilities),
            minimum_phone_probability=min(probabilities),
            greedy_agreement=sum(agreement) / len(agreement),
            minimum_phone_greedy_agreement=min(agreement),
            first_phone_greedy_agreement=agreement[0],
            last_phone_greedy_agreement=agreement[-1],
        )
    return result


def verified_phone_views(units, *, length_ms):
    """Frozen exploratory gate; every phone, not just a confident long vowel."""
    eligible = {
        i
        for i, u in enumerate(units)
        if 0 < u["start_ms"] < u["end_ms"] < length_ms
        and u["minimum_phone_probability"] >= 0.45
        and u["greedy_agreement"] >= 0.90
    }
    return [
        {
            "raw_span": u["raw_span"],
            "kind": "singing-ctc",
            "source_match": i in eligible and (i - 1 in eligible or i + 1 in eligible),
            "minimum_phone_probability": u["minimum_phone_probability"],
            "greedy_agreement": u["greedy_agreement"],
            "observed_midpoint_ms": (u["start_ms"] + u["end_ms"]) / 2
            if u["start_ms"] >= 0
            else None,
            "probability": u["mean_probability"],
            "matched_words": 2
            if i in eligible and (i - 1 in eligible or i + 1 in eligible)
            else 0,
        }
        for i, u in enumerate(units)
    ]
