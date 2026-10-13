"""Research-only mixed mora/phone CTC word boundaries from observed token frames.

A mora may cover several phones inside one source word; it cannot straddle two
words. No interior timestamps are divided between phones. Complete ownership and
ordinary CTC repeat/blank rules are required, including repeated long vowels.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa/vendor")]
from singing_phonemes import kana_phones, token_phones


def word_alignment(logp, blank, words, vocabulary):
    import numpy as np

    result = [
        {
            "raw_span": w["raw_span"],
            "start_ms": -1,
            "end_ms": -1,
            "mean_probability": 0.0,
        }
        for w in words
    ]
    if logp.ndim != 2 or not np.isfinite(logp).all() or not 0 <= blank < logp.shape[1]:
        raise ValueError("Invalid independent singing CTC evidence.")
    phones, owners = [], []
    for owner, word in enumerate(words):
        sequence = kana_phones(word["text"], word.get("romaji", ""))
        if sequence is None:
            return result
        phones.extend(sequence)
        owners.extend([owner] * len(sequence))
    if not phones or len(phones) > 512 or not 0 < len(logp) <= 1600:
        return result
    boundaries = len(phones) + 1
    arcs, ending = [], [[] for _ in range(boundaries)]
    for first in range(len(phones)):
        for token, label in vocabulary.items():
            sequence = token_phones(token)
            last = first + len(sequence)
            if label == blank or not sequence or phones[first:last] != sequence:
                continue
            if owners[first] != owners[last - 1]:
                continue
            if not 0 <= label < logp.shape[1]:
                raise ValueError("Invalid independent singing vocabulary.")
            state = boundaries + len(arcs)
            arcs.append((first, last, label, state))
            ending[last].append((label, state))
    if not ending[-1] or boundaries + len(arcs) > 2048:
        return result
    parents = [[p, *(state for _, state in ending[p])] for p in range(boundaries)]
    for first, _, label, state in arcs:
        parents.append(
            [state, first, *(s for other, s in ending[first] if other != label)]
        )
    count, width = len(parents), max(map(len, parents))
    indices = np.array([row + [count] * (width - len(row)) for row in parents])
    emissions = np.array([blank] * boundaries + [arc[2] for arc in arcs])
    previous = np.full(count + 1, -np.inf)
    previous[0] = 0
    back = []
    for row in logp:
        options = previous[indices]
        choices = options.argmax(axis=1)
        sources = indices[np.arange(count), choices]
        previous[:count] = options[np.arange(count), choices] + row[emissions]
        back.append(sources)
    endings = [len(phones), *(state for _, state in ending[-1])]
    state = max(endings, key=lambda s: previous[s])
    if not np.isfinite(previous[state]):
        return result
    path = []
    for sources in reversed(back):
        path.append(state)
        state = int(sources[state])
    path = np.array(path[::-1])
    coverage = np.zeros(len(phones), dtype=bool)
    observations = [[] for _ in words]
    for first, last, label, state in arcs:
        frames = np.flatnonzero(path == state)
        if not frames.size:
            continue
        coverage[first:last] = True
        probability = float(np.exp(logp[frames, label]).mean())
        observations[owners[first]].append(
            (frames[0], frames[-1], probability, last - first)
        )
    if not coverage.all():
        return result
    for unit, values in zip(result, observations, strict=True):
        unit.update(
            start_ms=int(min(r[0] for r in values) * 20),
            end_ms=int(max(r[1] for r in values) * 20 + 25),
            mean_probability=sum(r[2] * r[3] for r in values)
            / sum(r[3] for r in values),
        )
    return result
