"""Shared measured timing policy; no model, playback or interpolation dependencies."""

import math


def ctc_path(rows, labels, blank=0):
    """Exact CTC Viterbi path; impossible targets return None, never fake times."""
    if not rows or not labels or any(i == blank for i in labels):
        return None
    width = len(rows[0])
    if (
        not 0 <= blank < width
        or any(len(row) != width for row in rows)
        or any(i < 0 or i >= width for i in labels)
    ):
        raise ValueError("Invalid CTC vocabulary or matrix.")
    if any(not math.isfinite(x) for row in rows for x in row):
        raise ValueError("Nonfinite CTC evidence.")
    states = [blank]
    for label in labels:
        states.extend((label, blank))
    previous = [-math.inf] * len(states)
    previous[0] = 0.0
    back = []
    for row in rows:
        current, sources = [], []
        for s, token in enumerate(states):
            options = [(previous[s], s)]
            if s:
                options.append((previous[s - 1], s - 1))
            if s > 1 and token != blank and token != states[s - 2]:
                options.append((previous[s - 2], s - 2))
            score, source = max(options, key=lambda item: item[0])
            current.append(score + row[token])
            sources.append(source)
        back.append(sources)
        previous = current
    state = max((len(states) - 1, len(states) - 2), key=lambda s: previous[s])
    if not math.isfinite(previous[state]):
        return None
    path = []
    for t in range(len(rows) - 1, -1, -1):
        path.append(state)
        state = back[t][state]
    return path[::-1]


def agree(a, b, tolerance=200):
    """Compare both observed boundaries, keeping missing/degenerate spans missing."""
    return (
        0 <= a["start_ms"] < a["end_ms"]
        and 0 <= b["start_ms"] < b["end_ms"]
        and abs(a["start_ms"] - b["start_ms"]) <= tolerance
        and abs(a["end_ms"] - b["end_ms"]) <= tolerance
    )


def phonetic_support(alignment, evidence):
    value = evidence.get("mean_probability", 0)
    return math.isfinite(value) and 0.3 <= value <= 1 and agree(alignment, evidence)


def recover_gaps(baseline, vocals, phonetic=None):
    """Fill only nonoverlapping vocal gaps next to stable baseline anchors.

    Both boundaries of the nearest existing words must agree within 200 ms.
    Entirely unanchored lines stay missing. This tests consistency, not accuracy.
    """
    if [u["raw_span"] for u in baseline] != [u["raw_span"] for u in vocals]:
        raise ValueError("Changed source word anchors.")
    if phonetic is not None and [u["raw_span"] for u in baseline] != [
        u["raw_span"] for u in phonetic
    ]:
        raise ValueError("Changed phonetic word anchors.")

    def valid(unit):
        return 0 <= unit["start_ms"] < unit["end_ms"]

    result = [dict(u) for u in baseline]
    for i, new in enumerate(vocals):
        if valid(baseline[i]) or not valid(new):
            continue
        left = next((j for j in range(i - 1, -1, -1) if valid(baseline[j])), None)
        right = next(
            (j for j in range(i + 1, len(baseline)) if valid(baseline[j])), None
        )
        neighbors = [j for j in (left, right) if j is not None]
        if phonetic is None:
            if not neighbors or any(
                not agree(baseline[j], vocals[j]) for j in neighbors
            ):
                continue
        elif not phonetic_support(new, phonetic[i]):
            continue
        if (left is not None and new["start_ms"] < baseline[left]["end_ms"]) or (
            right is not None and new["end_ms"] > baseline[right]["start_ms"]
        ):
            continue
        previous = next((j for j in range(i - 1, -1, -1) if valid(result[j])), None)
        if previous is not None and new["start_ms"] < result[previous]["end_ms"]:
            continue
        result[i] = dict(new)
    return result


def repair_regions(baseline, vocals, phonetic):
    """Repair a gap and at most three neighbors with independent support for all.

    Every changed interval must agree with the independent phonetic observation.
    Keep the region ordered and inside unchanged outer anchors. Never trim or
    stretch an interval to fit, or discard an existing baseline interval.
    """
    result = recover_gaps(baseline, vocals, phonetic)

    def valid(unit):
        return 0 <= unit["start_ms"] < unit["end_ms"]

    for i, candidate in enumerate(vocals):
        if valid(result[i]) or not phonetic_support(candidate, phonetic[i]):
            continue
        left = right = i
        while True:
            previous = next(
                (j for j in range(left - 1, -1, -1) if valid(result[j])), None
            )
            following = next(
                (j for j in range(right + 1, len(result)) if valid(result[j])), None
            )
            bounds = left, right
            if (
                previous is not None
                and vocals[left]["start_ms"] < result[previous]["end_ms"]
            ):
                left = previous
            if (
                following is not None
                and vocals[right]["end_ms"] > result[following]["start_ms"]
            ):
                right = following
            if right - left + 1 > 4 or any(
                not phonetic_support(vocals[j], phonetic[j])
                for j in range(left, right + 1)
            ):
                break
            if any(
                vocals[j]["end_ms"] > vocals[j + 1]["start_ms"]
                for j in range(left, right)
            ):
                break
            if bounds == (left, right):
                for j in range(left, right + 1):
                    result[j] = {**vocals[j], "repair": "phonetic-region"}
                break
    return result


def supported_raw(vocals, phonetic, length_ms):
    """Experimental candidates: preserve production filtering, add a second model.

    Only complete, positive-similarity paths rejected for token agreement qualify.
    Fix the 0.90 candidate cutoff before evaluating the new-song results; still
    require MMS probability and both observed endpoints. Never relax bounds/duration.
    """
    units, raw = vocals["units"], vocals["raw_units"]
    if [u["raw_span"] for u in units] != [u["raw_span"] for u in raw]:
        raise ValueError("Changed raw candidate source anchors.")
    if [u["raw_span"] for u in units] != [u["raw_span"] for u in phonetic]:
        raise ValueError("Changed phonetic source anchors.")
    result = [dict(u) for u in units]
    for i, candidate in enumerate(raw):
        if units[i]["start_ms"] >= 0 or candidate["reason"] != "token_agreement":
            continue
        agreement, similarity = (
            candidate.get("agreement"),
            candidate.get("mean_similarity"),
        )
        if (
            agreement is None
            or similarity is None
            or not math.isfinite(agreement)
            or not 0.90 <= agreement <= 1
            or not math.isfinite(similarity)
            or similarity <= 0
            or not 0 <= candidate["start_ms"] < candidate["end_ms"] <= length_ms
            or candidate["end_ms"] - candidate["start_ms"] < 80
            or not phonetic_support(candidate, phonetic[i])
        ):
            continue
        result[i] = {
            "raw_span": candidate["raw_span"],
            "start_ms": candidate["start_ms"],
            "end_ms": candidate["end_ms"],
            "repair": "phonetic-raw",
        }
    return result


def coherent_line(candidates, phonetic, source_words=None):
    """Follow-up guard: half the line and at least two words when possible.

    Isolated coincidences in a wrong verse cannot authorize repairs. Missing and
    unsupported source words count; this guard is not a correctness score.
    """
    if len(candidates) != len(phonetic) or [u["raw_span"] for u in candidates] != [
        u["raw_span"] for u in phonetic
    ]:
        raise ValueError("Changed line-context evidence.")
    source_words = len(candidates) if source_words is None else source_words
    if not isinstance(source_words, int) or source_words < len(candidates):
        raise ValueError("Invalid original source word count.")
    required = min(source_words, max(2, math.ceil(source_words / 2)))
    return (
        bool(candidates)
        and sum(
            phonetic_support(a, b) for a, b in zip(candidates, phonetic, strict=True)
        )
        >= required
    )


def chunk_windows(length, size):
    """Half-overlapping fixed windows, with real samples at exact original indices."""
    if length <= 0 or size <= 0 or size % 2:
        raise ValueError("Invalid separation chunk dimensions.")
    for start in range(-size // 2, length, size // 2):
        first, last = max(0, start), min(length, start + size)
        yield start, first, last


def ctc_labels(words, vocabulary):
    if any(
        c.isalpha() and c not in vocabulary
        for word in words
        for c in word["romaji"].lower()
    ):
        return None
    spellings = [
        "".join(c for c in w["romaji"].lower() if c in vocabulary and c.isalpha())
        for w in words
    ]
    if not spellings or not all(spellings) or "|" not in vocabulary:
        return None
    return [vocabulary[c] for c in "|".join(spellings)]
