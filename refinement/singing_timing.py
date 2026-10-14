"""Mixed mora/phone CTC word boundaries from observed token frames.

A mora may cover several phones inside one source word; it cannot straddle two
words. No interior timestamps are divided between phones. Complete ownership and
ordinary CTC repeat/blank rules are required, including repeated long vowels.
"""

from refinement_policy import agree, coherent_line, recover_gaps, supported_raw
from singing_phonemes import kana_phones, token_phones


def recover_singing_gaps(baseline, trial, evidence, length_ms, source_words):
    """Add independently supported gaps without changing any retained interval.

    TIFA still needs a complete positive-similarity path and at least .90 token
    agreement. The independent singing model must reach .45 mean probability
    and agree on both endpoints within 150 ms, with coherent phrase context.
    These are measured model checks, not a guarantee of perceptual accuracy.
    """
    candidates = supported_raw(trial, evidence, length_ms)
    for i, candidate in enumerate(candidates):
        if (
            not 0.45 <= evidence[i]["mean_probability"] <= 1
            or not agree(candidate, evidence[i], 150)
            or not 0 <= candidate["start_ms"] < candidate["end_ms"] <= length_ms
            or candidate["end_ms"] - candidate["start_ms"] < 80
        ):
            candidates[i] = {**candidate, "start_ms": -1, "end_ms": -1}
    context = [
        trial["units"][i] if old["start_ms"] >= 0 else candidates[i]
        for i, old in enumerate(baseline)
    ]
    if not coherent_line(context, evidence, source_words):
        return [dict(u) for u in baseline]
    repaired = recover_gaps(baseline, candidates, evidence)
    return [
        {**old, "start_ms": new["start_ms"], "end_ms": new["end_ms"]}
        for old, new in zip(baseline, repaired, strict=True)
    ]


def word_alignment(logp, blank, words, vocabulary, *, word_phones=None):
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
    if word_phones is not None and len(word_phones) != len(words):
        raise ValueError("Pronunciation alternatives changed source-word ownership.")
    for owner, word in enumerate(words):
        sequence = (
            word_phones[owner]
            if word_phones is not None
            else kana_phones(word["text"], word.get("romaji", ""))
        )
        if not sequence:
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
