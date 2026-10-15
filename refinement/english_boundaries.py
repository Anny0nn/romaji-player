"""Independent English boundary observations, separate from lexical recognition."""

import math
from difflib import SequenceMatcher
from itertools import pairwise

from english_timing import english_key


def observed_lexemes(
    targets, segments, length_ms, *, offset_ms=0, context_length_ms=None
):
    """Unique multiword audio recognition; only its observed midpoint locates a word.

    Context timestamps can extend beyond a cue. Preserve them in recognition data;
    no trimming, rescaling or endpoint transfer to the saved timing is permitted.
    """
    context_length_ms = length_ms if context_length_ms is None else context_length_ms
    if (
        not isinstance(context_length_ms, (int, float))
        or isinstance(context_length_ms, bool)
        or not math.isfinite(context_length_ms)
        or context_length_ms <= 0
    ):
        raise ValueError("Invalid original recognition context length.")
    source = [english_key(t.get("expected_text", t["text"])) for t in targets]
    words = [w for s in segments for w in s.get("words", [])]
    keys = [english_key(w.get("word")) for w in words]
    left = [key or f"source-unavailable:{i}" for i, key in enumerate(source)]
    right = [key or f"observed-unavailable:{i}" for i, key in enumerate(keys)]
    result = [
        {
            "raw_span": t["raw_span"],
            "source_match": False,
            "observed_midpoint_ms": None,
            "probability": 0.0,
            "matched_words": 0,
        }
        for t in targets
    ]
    for block in SequenceMatcher(
        None, left, right, autojunk=False
    ).get_matching_blocks():
        if block.size < 2 or any(
            key is None for key in source[block.a : block.a + block.size]
        ):
            continue
        text = left[block.a : block.a + block.size]
        if (
            sum(
                left[i : i + len(text)] == text
                for i in range(len(left) - len(text) + 1)
            )
            != 1
            or sum(
                right[i : i + len(text)] == text
                for i in range(len(right) - len(text) + 1)
            )
            != 1
        ):
            continue
        for i in range(block.size):
            word = words[block.b + i]
            start, end, probability = (
                word.get(k) for k in ("start", "end", "probability")
            )
            if (
                not all(
                    isinstance(v, (int, float))
                    and not isinstance(v, bool)
                    and math.isfinite(v)
                    for v in (start, end, probability)
                )
                or not 0 <= start < end <= context_length_ms / 1000
                or not 0.7 <= probability <= 1
            ):
                continue
            midpoint = (start + end) * 500 + offset_ms
            if 0 <= midpoint <= length_ms:
                result[block.a + i].update(
                    source_match=True,
                    observed_midpoint_ms=midpoint,
                    probability=probability,
                    matched_words=block.size,
                )
    return result


def paired_boundary(tifa, singing, length_ms):
    """Both conditioned aligners agree; neither supplies lexical verification."""
    if tifa["raw_span"] != singing["raw_span"]:
        raise ValueError("English boundary observations changed source ownership.")
    for unit in (tifa, singing):
        if not all(
            isinstance(unit.get(key), (int, float))
            and not isinstance(unit[key], bool)
            and math.isfinite(unit[key])
            for key in ("start_ms", "end_ms")
        ):
            return None
        if (
            not 0 < unit["start_ms"] < unit["end_ms"] < length_ms
            or unit["end_ms"] - unit["start_ms"] < 80
        ):
            return None
    agreement, similarity = tifa.get("agreement"), tifa.get("mean_similarity")
    if (
        tifa.get("reason") not in ("retained", "token_agreement")
        or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in (agreement, similarity)
        )
        or not 0.90 <= agreement <= 1
        or similarity <= 0
        or singing.get("complete") is not True
        or any(abs(tifa[key] - singing[key]) > 150 for key in ("start_ms", "end_ms"))
    ):
        return None
    return {
        "raw_span": tifa["raw_span"],
        "start_ms": tifa["start_ms"],
        "end_ms": tifa["end_ms"],
    }


def recover_verified_boundaries(
    baseline, targets, tifa, singing, views, length_ms, *, source_words=None
):
    """ASR proves lexical occurrence; two other families supply both boundaries.

    Never use ASR as a gold transcript or copy its word clock. The ASR midpoint
    only restricts where a recognized word occurred. All old timings stay fixed.
    """
    expected = [t["raw_span"] for t in targets]
    if len(views) != 2 or any(
        [u["raw_span"] for u in row] != expected
        for row in (baseline, tifa, singing, *views)
    ):
        raise ValueError("English evidence changed source ownership.")
    source_words = len(targets) if source_words is None else source_words
    if type(source_words) is not int or source_words < len(targets):
        raise ValueError("Invalid original word denominator.")
    eligible = {}
    for i, target in enumerate(targets):
        if target.get("protected_reading") or not english_key(
            target.get("expected_text", target["text"])
        ):
            continue
        candidate = paired_boundary(tifa[i], singing[i], length_ms)
        if candidate is None:
            continue
        observed = [row[i] for row in views]
        if any(
            not all(
                isinstance(unit.get(k), (int, float))
                and not isinstance(unit[k], bool)
                and math.isfinite(unit[k])
                for k in ("observed_midpoint_ms", "probability")
            )
            or unit.get("source_match") is not True
            or type(unit.get("matched_words")) is not int
            or unit["matched_words"] < 2
            or not 0 <= unit["observed_midpoint_ms"] <= length_ms
            or not lexical_support(unit)
            or not candidate["start_ms"] - 150
            <= unit["observed_midpoint_ms"]
            <= candidate["end_ms"] + 150
            for unit in observed
        ):
            continue
        eligible[i] = candidate
    # A common isolated word cannot establish its phrase. Neighbor evidence must
    # also include a complete boundary pair, even if its old timing is retained.
    coherent = {i for i in eligible if i - 1 in eligible or i + 1 in eligible}
    result = [dict(u) for u in baseline]
    missing = {i: eligible[i] for i in coherent if baseline[i]["start_ms"] < 0}
    if not any(u["start_ms"] >= 0 for u in baseline) and (
        len(coherent) < max(2, math.ceil(source_words * 0.7))
        or len(targets)
        != sum(bool(english_key(t.get("expected_text", t["text"]))) for t in targets)
    ):
        return result
    tentative = [
        (i, missing.get(i, old))
        for i, old in enumerate(baseline)
        if i in missing or old["start_ms"] >= 0
    ]
    conflicts = set()
    for (first, left), (last, right) in pairwise(tentative):
        if left["end_ms"] > right["start_ms"]:
            conflicts.update(i for i in (first, last) if i in missing)
    for i, candidate in missing.items():
        if i not in conflicts:
            result[i] = {
                **baseline[i],
                "start_ms": candidate["start_ms"],
                "end_ms": candidate["end_ms"],
            }
    return result


def lexical_support(unit):
    """Model-specific statistics; Whisper confidence is not CTC probability.

    The phonetic path is exploratory and still needs labelled/wrong-path gates.
    Both views expose minimum-phone and greedy-agreement measurements.
    """
    probability = unit.get("probability")
    if (
        not isinstance(probability, (int, float))
        or isinstance(probability, bool)
        or not math.isfinite(probability)
    ):
        return False
    kind = unit.get("kind", "whisper")
    if kind == "whisper":
        return 0.70 <= unit["probability"] <= 1
    if kind != "singing-ctc":
        return False
    minimum, greedy = (
        unit.get("minimum_phone_probability"),
        unit.get("greedy_agreement"),
    )
    return (
        all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in (minimum, greedy)
        )
        and 0.45 <= minimum <= unit["probability"] <= 1
        and 0.90 <= greedy <= 1
    )
