"""Research word-local CTC with explicit lyric deletion and unowned audio.

Unlike a forced complete transcript, the graph can skip an entire source word.
Background consumes real unmasked acoustic frames without owning a lyric span;
returning from background requires an observed blank. Within words, ordinary CTC
repeat/blank rules and complete phone ownership apply. No skipped word gets a clock.
Scores are path scores, not calibrated lexical probabilities.
"""

import math
from itertools import pairwise


def align_partial(
    logp,
    blank,
    word_phones,
    vocabulary_phones,
    *,
    frame_ms=20,
    receptive_ms=25,
    deletion_phone_cost=1.0,
    background_frame_cost=0.7,
    margins=False,
):
    import numpy as np

    if (
        logp.ndim != 2
        or not 0 < len(logp) <= 3000
        or not 0 <= blank < logp.shape[1]
        or len(word_phones) > 128
        or any(not p for p in word_phones)
        or not np.isfinite(logp).all()
        or (logp > 0).any()
        or not np.allclose(np.logaddexp.reduce(logp, axis=1), 0, atol=1e-4)
        or any(
            not math.isfinite(v) or v <= 0
            for v in (
                frame_ms,
                receptive_ms,
                deletion_phone_cost,
                background_frame_cost,
            )
        )
        or any(
            type(k) is not int or not 0 <= k < logp.shape[1] for k in vocabulary_phones
        )
    ):
        raise ValueError("Invalid partial CTC acoustic/ownership contract.")
    phones, owners, bounds = [], [], [0]
    for word, sequence in enumerate(word_phones):
        phones.extend(sequence)
        owners.extend([word] * len(sequence))
        bounds.append(len(phones))
    if not phones or len(phones) > 512:
        raise ValueError("Partial CTC requires bounded complete source phones.")
    boundary_count = len(phones) + 1
    arcs, ending = [], [[] for _ in range(boundary_count)]
    for first in range(len(phones)):
        for label, sequence in vocabulary_phones.items():
            last = first + len(sequence)
            if (
                label == blank
                or not sequence
                or phones[first:last] != list(sequence)
                or owners[first] != owners[last - 1]
            ):
                continue
            state = boundary_count + len(arcs)
            arcs.append((first, last, label, state))
            ending[last].append((label, state))
    background = {b: boundary_count + len(arcs) + i for i, b in enumerate(bounds)}
    parents = [
        [
            p,
            *(state for _, state in ending[p]),
            *([background[p]] if p in background else []),
        ]
        for p in range(boundary_count)
    ]
    parents.extend(
        [state, first, *(s for other, s in ending[first] if other != label)]
        for first, _, label, state in arcs
    )
    parents.extend(
        [state, position, *(s for _, s in ending[position])]
        for position, state in background.items()
    )
    count, width = len(parents), max(map(len, parents))
    if count > 4096:
        raise ValueError("Partial CTC graph exceeds its bounded pilot size.")
    indices = np.array([p + [count] * (width - len(p)) for p in parents])
    emissions = np.column_stack(
        [logp[:, blank]] * boundary_count
        + [logp[:, label] for _, _, label, _ in arcs]
        + [np.max(np.delete(logp, blank, axis=1), axis=1) - background_frame_cost]
        * len(background)
    )
    arc_owners = {state: owners[first] for first, _, _, state in arcs}

    def closure(scores, actual=None):
        for word, (first, last) in enumerate(pairwise(bounds)):
            penalty = deletion_phone_cost * len(word_phones[word])
            for start, end in ((first, last), (background[first], background[last])):
                candidate = scores[start] - penalty
                if candidate > scores[end]:
                    scores[end] = candidate
                    if actual is not None:
                        actual[end] = actual[start]

    def decode(forbidden=None, trace=False):
        previous = np.full(count + 1, -np.inf)
        previous[0] = 0
        closure(previous)
        back, emitters = [], []
        for row in emissions:
            options = previous[indices]
            choices = options.argmax(axis=1)
            following = options[np.arange(count), choices] + row
            if forbidden is not None:
                for state, owner in arc_owners.items():
                    if owner == forbidden:
                        following[state] = -np.inf
            actual = np.arange(count)
            closure(following, actual)
            previous[:count] = following
            if trace:
                back.append(indices[np.arange(count), choices])
                emitters.append(actual)
        final = [len(phones), background[len(phones)], *(s for _, s in ending[-1])]
        state = max(final, key=lambda s: previous[s])
        score = float(previous[state])
        path = []
        if trace:
            for actual, parent in zip(reversed(emitters), reversed(back), strict=True):
                emitted = int(actual[state])
                path.append(emitted)
                state = int(parent[emitted])
        return score, np.asarray(path[::-1])

    score, path = decode(trace=True)
    observations = [[] for _ in word_phones]
    coverage = np.zeros(len(phones), dtype=bool)
    greedy = logp.argmax(axis=1)
    for first, last, label, state in arcs:
        frames = np.flatnonzero(path == state)
        if not len(frames):
            continue
        coverage[first:last] = True
        observations[owners[first]].append(
            (
                int(frames[0]),
                int(frames[-1]),
                float(np.exp(logp[frames, label]).mean()),
                float((greedy[frames] == label).mean()),
                last - first,
            )
        )
    units, skipped = [], []
    for word, values in enumerate(observations):
        placed = bool(values) and coverage[bounds[word] : bounds[word + 1]].all()
        if values and not placed:
            raise ValueError("Partial path assigned only a piece of a source word.")
        if not placed:
            skipped.append(word)
        margin = (
            max(0.0, score - decode(forbidden=word)[0]) if placed and margins else None
        )
        units.append(
            {
                "word": word,
                "placed": bool(placed),
                "start_ms": min(v[0] for v in values) * frame_ms if placed else -1,
                "end_ms": max(v[1] for v in values) * frame_ms + receptive_ms
                if placed
                else -1,
                "mean_probability": sum(v[2] * v[4] for v in values)
                / len(word_phones[word])
                if placed
                else 0.0,
                "greedy_agreement": sum(v[3] * v[4] for v in values)
                / len(word_phones[word])
                if placed
                else 0.0,
                "deletion_margin_nats": margin,
            }
        )
    return {"units": units, "path_score": score, "skipped_words": skipped}
