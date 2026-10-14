"""Missing English-word recovery from observed Whisper and independent TIFA spans."""

import math
import re
from difflib import SequenceMatcher
from itertools import pairwise


def english_key(text):
    if not isinstance(text, str) or any(c.isalpha() and not c.isascii() for c in text):
        return None
    if not any(c.isascii() and c.isalpha() for c in text):
        return None
    return re.sub(r"[^a-z0-9]", "", text.lower()) or None


def observed_words(targets, segments, length_ms):
    """Unique contiguous lexical matches retain whole observed word endpoints."""
    source = [english_key(t.get("expected_text", t["text"])) for t in targets]
    observed = [word for segment in segments for word in segment.get("words", [])]
    keys = [english_key(w.get("word")) for w in observed]
    left = [key or f"source-non-english:{i}" for i, key in enumerate(source)]
    right = [key or f"observed-non-english:{i}" for i, key in enumerate(keys)]
    result = [
        {"raw_span": t["raw_span"], "start_ms": -1, "end_ms": -1, "probability": 0.0}
        for t in targets
    ]
    for block in SequenceMatcher(
        None, left, right, autojunk=False
    ).get_matching_blocks():
        if not block.size:
            continue
        context = left[block.a : block.a + block.size]
        if any(key is None for key in source[block.a : block.a + block.size]):
            continue
        if (
            sum(
                left[i : i + len(context)] == context
                for i in range(len(left) - len(context) + 1)
            )
            != 1
            or sum(
                right[i : i + len(context)] == context
                for i in range(len(right) - len(context) + 1)
            )
            != 1
        ):
            continue
        single = block.size == 1
        if single and (
            block.a
            and source[block.a - 1] is not None
            or block.a + 1 < len(source)
            and source[block.a + 1] is not None
        ):
            continue
        for offset in range(block.size):
            word = observed[block.b + offset]
            start, end, probability = (
                word.get(k) for k in ("start", "end", "probability")
            )
            if not all(
                isinstance(v, (int, float))
                and not isinstance(v, bool)
                and math.isfinite(v)
                for v in (start, end, probability)
            ):
                continue
            start, end = round(start * 1000), round(end * 1000)
            if (
                not 0 <= start < end <= length_ms
                or not (0.9 if single else 0.7) <= probability <= 1
            ):
                continue
            result[block.a + offset].update(
                start_ms=start, end_ms=end, probability=probability
            )
    return result


def recover_english(baseline, targets, trials, views, length_ms):
    """Preserve every old interval; add only independently observed noncolliding words."""
    expected = [t["raw_span"] for t in targets]
    if (
        len(views) != 2
        or not trials
        or any(
            [u["raw_span"] for u in row] != expected
            for row in [baseline, *trials, *views]
        )
    ):
        raise ValueError("English evidence has different source-word ownership.")

    def valid(unit):
        return (
            all(
                isinstance(unit[k], (int, float))
                and not isinstance(unit[k], bool)
                and math.isfinite(unit[k])
                for k in ("start_ms", "end_ms")
            )
            and 0 <= unit["start_ms"] < unit["end_ms"] <= length_ms
        )

    result = [dict(u) for u in baseline]
    candidates = {}
    for index, word in enumerate(targets):
        if valid(baseline[index]) or not english_key(
            word.get("expected_text", word["text"])
        ):
            continue
        observations = [view[index] for view in views]
        if not all(
            valid(u)
            and math.isfinite(u["probability"])
            and 0.7 <= u["probability"] <= 1
            for u in observations
        ):
            continue
        if any(
            abs(observations[0][k] - observations[1][k]) > 150
            for k in ("start_ms", "end_ms")
        ):
            continue
        for trial in trials:
            candidate = trial[index]
            agreement, similarity = (
                candidate.get("agreement"),
                candidate.get("mean_similarity"),
            )
            if (
                candidate.get("reason") not in ("retained", "token_agreement")
                or not valid(candidate)
                or candidate["end_ms"] - candidate["start_ms"] < 80
            ):
                continue
            if (
                not all(
                    isinstance(v, (int, float)) and math.isfinite(v)
                    for v in (agreement, similarity)
                )
                or not 0.9 <= agreement <= 1
                or similarity <= 0
            ):
                continue
            if any(
                abs(candidate[k] - observation[k]) > 150
                for observation in observations
                for k in ("start_ms", "end_ms")
            ):
                continue
            candidates[index] = {
                **baseline[index],
                "start_ms": candidate["start_ms"],
                "end_ms": candidate["end_ms"],
                "repair": "english-observed",
            }
            break
    # Fully untimed lines need coherent, observed English coverage, not one common word.
    if not any(valid(u) for u in baseline):
        english = [
            i
            for i, w in enumerate(targets)
            if english_key(w.get("expected_text", w["text"]))
        ]
        if len(english) != len(targets) or len(candidates) < max(
            2, math.ceil(len(targets) * 0.7)
        ):
            return result
    tentative = [
        (i, candidates.get(i, original))
        for i, original in enumerate(baseline)
        if i in candidates or valid(original)
    ]
    conflicts = set()
    for (first, left), (last, right) in pairwise(tentative):
        if left["end_ms"] > right["start_ms"]:
            conflicts.update(i for i in (first, last) if i in candidates)
    for index, candidate in candidates.items():
        if index not in conflicts:
            result[index] = candidate
    return result
