"""Exploratory localized acoustic gate; not promoted or independently recognized text."""

import math

POLICY = {
    "minimum_duration_ms": 80,
    "minimum_mean_log_probability": -2.3,
    "minimum_silence_contrast_nats": 0.7,
    "minimum_wrong_verse_contrast_nats": 0.7,
    "minimum_own_mask_drop_nats": 0.7,
    "minimum_localized_excess_nats": 0.35,
}


def supported(unit, length_ms, *, wrong_verse=True):
    """Undefined/conditional-only evidence is withheld, with original clock edges."""
    fields = [
        "start_ms",
        "end_ms",
        "source_mean_log_probability",
        "silence_contrast_nats",
        "own_mask_drop_nats",
        "localized_excess_nats",
    ]
    if wrong_verse:
        fields.append("wrong_verse_contrast_nats")
    if any(
        not isinstance(unit.get(k), (int, float))
        or isinstance(unit[k], bool)
        or not math.isfinite(unit[k])
        for k in fields
    ):
        return False
    return (
        0 < unit["start_ms"] < unit["end_ms"] < length_ms
        and unit["end_ms"] - unit["start_ms"] >= POLICY["minimum_duration_ms"]
        and unit["source_mean_log_probability"]
        >= POLICY["minimum_mean_log_probability"]
        and unit["silence_contrast_nats"] >= POLICY["minimum_silence_contrast_nats"]
        and (
            not wrong_verse
            or unit["wrong_verse_contrast_nats"]
            >= POLICY["minimum_wrong_verse_contrast_nats"]
        )
        and unit["own_mask_drop_nats"] >= POLICY["minimum_own_mask_drop_nats"]
        and unit["localized_excess_nats"] >= POLICY["minimum_localized_excess_nats"]
    )


def recover_original_groups(baseline, views, length_ms, source_words):
    """Research-only overlay: adjacent evidence, same groups, immutable old clocks."""
    from itertools import pairwise

    if (
        not baseline
        or type(source_words) is not int
        or source_words < len(baseline)
        or len(views) != 2
        or any(len(v) != len(baseline) for v in views)
    ):
        raise ValueError("Acoustic views changed original group count.")
    if any(
        a["raw_span"] != b["raw_span"] or a["raw_span"] != c["raw_span"]
        for a, b, c in zip(baseline, *views, strict=True)
    ):
        raise ValueError("Acoustic views changed original source spans.")
    # The two views use the same authenticated TIFA/HFA seed clock. None is copied
    # from a transcription or a transformed recording.
    eligible = {
        i
        for i, (a, b) in enumerate(zip(*views, strict=True))
        if supported(a, length_ms)
        and supported(b, length_ms)
        and (a["start_ms"], a["end_ms"]) == (b["start_ms"], b["end_ms"])
    }
    original = [dict(u) for u in baseline]
    if not any(
        u["start_ms"] >= 0 or u.get("protected", False) for u in original
    ) and len(eligible) < math.ceil(0.7 * source_words):
        return original
    for index in sorted(eligible):
        if (
            original[index]["start_ms"] >= 0
            or original[index].get("protected", False)
            or not ({index - 1, index + 1} & eligible)
        ):
            continue
        candidate = {
            **original[index],
            "start_ms": views[0][index]["start_ms"],
            "end_ms": views[0][index]["end_ms"],
        }
        trial = [candidate if n == index else u for n, u in enumerate(original)]
        timed = [u for u in trial if u["start_ms"] >= 0 or u.get("protected", False)]
        if all(a["end_ms"] <= b["start_ms"] for a, b in pairwise(timed)):
            original[index] = candidate
    return original
