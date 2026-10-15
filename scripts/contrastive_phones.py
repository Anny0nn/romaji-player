"""Local pronunciation evidence from cached singing CTC posteriors.

Compare a target with the *union* of all representable same-length, one-phone
substitutions on identical frames. Scores are likelihood ratios, not calibrated
confidence, spelling evidence, or independent word boundaries. No source decoding
or app persistence happens here.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "refinement"))
from singing_phonemes import token_phones


def contrastive_score(logp, blank, phones, vocabulary, *, observe=False):
    """Exact CTC sums for target / one-substitution union / all-blank path.

    Only independently representable single-phone labels form the substitution
    inventory. Mora labels remain available in both hypotheses. No arbitrary
    edit, deletion, background or duration penalty is used. A positive union
    margin is stricter than beating each individual substitution separately.
    This closed competitor set does not establish open-set lexical correctness.
    """
    import numpy as np

    logp = np.asarray(logp, dtype=np.float64)
    if (
        logp.ndim != 2
        or not logp.shape[0]
        or not logp.shape[1]
        or not 0 <= blank < logp.shape[1]
        or np.isnan(logp).any()
        or np.isposinf(logp).any()
        or np.any(logp > 1e-6)
        or not np.allclose(np.logaddexp.reduce(logp, axis=1), 0, atol=1e-4)
    ):
        raise ValueError("Expected normalized CTC log probabilities.")
    if not phones or len(phones) > 128 or len(logp) > 1600:
        raise ValueError("Expected a bounded nonempty phone interval.")
    if len(set(vocabulary.values())) != len(vocabulary) or any(
        type(i) is not int or not 0 <= i < logp.shape[1] for i in vocabulary.values()
    ):
        raise ValueError("Invalid or aliased CTC vocabulary.")
    tokens = [
        (i, token_phones(token))
        for token, i in vocabulary.items()
        if i != blank and token_phones(token)
    ]
    inventory = sorted({p[0] for _, p in tokens if len(p) == 1})
    if not inventory:
        raise ValueError("No atomic substitution labels.")

    # Boundary(position, edits-used) plus emitting token arcs. CTC may remain
    # in a token state, or cross a boundary; adjacent equal labels need a blank.
    count = len(phones) + 1
    boundaries = count * 2
    ending = [[] for _ in range(boundaries)]
    states = []
    for first in range(len(phones)):
        for label, expansion in tokens:
            last = first + len(expansion)
            if last > len(phones):
                continue
            differences = [
                b for a, b in zip(phones[first:last], expansion, strict=True) if a != b
            ]
            if len(differences) > 1 or any(p not in inventory for p in differences):
                continue
            for edits in range(2 - len(differences)):
                start = edits * count + first
                end = (edits + len(differences)) * count + last
                index = boundaries + len(states)
                states.append((start, end, label, index))
                ending[end].append((label, index))
    parents = [[p, *(i for _, i in ending[p])] for p in range(boundaries)]
    for start, _, label, index in states:
        parents.append(
            [index, start, *(i for other, i in ending[start] if other != label)]
        )
    missing = len(parents)
    width = max(map(len, parents))
    indices = np.array([p + [missing] * (width - len(p)) for p in parents])
    emissions = np.array([blank] * boundaries + [s[2] for s in states])
    previous = np.full(missing + 1, -np.inf)
    previous[0] = 0
    best = previous.copy()
    history = []
    for row in logp:
        previous[:missing] = (
            np.logaddexp.reduce(previous[indices], axis=1) + row[emissions]
        )
        if observe:
            choices = np.argmax(best[indices], axis=1)
            parents_used = indices[np.arange(missing), choices]
            history.append(parents_used)
            best[:missing] = best[parents_used] + row[emissions]

    def final(edits):
        end = edits * count + len(phones)
        value = float(
            np.logaddexp.reduce(previous[[end, *(i for _, i in ending[end])]])
        )
        return value if math.isfinite(value) else None

    target, substitutions = final(0), final(1)
    silence = float(logp[:, blank].sum())
    result = {
        "target_logp": target,
        "substitution_union_logp": substitutions,
        "blank_logp": silence if math.isfinite(silence) else None,
        "union_margin": (
            target - substitutions
            if target is not None and substitutions is not None
            else None
        ),
        "blank_margin": (
            target - silence if target is not None and math.isfinite(silence) else None
        ),
        "phone_count": len(phones),
        "substitution_inventory": inventory,
    }
    if observe:
        result["path"] = None
        if target is not None:
            terminals = [len(phones), *(i for _, i in ending[len(phones)])]
            state = max(terminals, key=lambda i: best[i])
            labels = []
            for parents_used in reversed(history):
                labels.append(int(emissions[state]))
                state = int(parents_used[state])
            labels.reverse()
            active = [i for i, label in enumerate(labels) if label != blank]
            result["path"] = {
                "first_frame": active[0],
                "last_frame": active[-1],
                "mean_frame_probability": float(
                    np.exp(logp[active, np.array(labels)[active]]).mean()
                ),
                "logp": float(max(best[i] for i in terminals)),
            }
    return result
