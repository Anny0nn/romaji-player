"""Offline region trial on cached paired observations; no app integration.

Every changed boundary is observed twice. Crop limits and retained neighbors
constrain the search; they never supply a timestamp. Existing automatic intervals
can move only if both models contradict them. Supplied/user intervals stay fixed.
"""

import math
import sys
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "refinement"))
from refinement_policy import agree, supported_raw
from singing_timing import recover_singing_gaps


def strict_candidates(trial, independent, length_ms):
    candidates = supported_raw(trial, independent, length_ms)
    for i, candidate in enumerate(candidates):
        probability = independent[i].get("mean_probability", 0)
        if (
            not math.isfinite(probability)
            or not 0.45 <= probability <= 1
            or not agree(candidate, independent[i], 150)
            or not 0 < candidate["start_ms"] < candidate["end_ms"] < length_ms
            or candidate["end_ms"] - candidate["start_ms"] < 80
        ):
            candidates[i] = {**candidate, "start_ms": -1, "end_ms": -1}
    return candidates


def recover_regions(
    baseline, trial, independent, length_ms, source_words, *, protected=()
):
    if [u["raw_span"] for u in baseline] != [u["raw_span"] for u in independent]:
        raise ValueError("Changed baseline source ownership.")
    if any(type(i) is not int or not 0 <= i < len(baseline) for i in protected):
        raise ValueError("Invalid protected word indices.")
    candidates = strict_candidates(trial, independent, length_ms)
    result = recover_singing_gaps(baseline, trial, independent, length_ms, source_words)
    for index in protected:
        result[index] = dict(baseline[index])
    events = []
    if source_words != len(baseline):
        return result, [{"reason": "unmapped_original_groups"}]

    def valid(unit):
        return 0 <= unit["start_ms"] < unit["end_ms"]

    def anchor(index):
        return (
            valid(candidates[index])
            and agree(result[index], candidates[index], 150)
            and agree(result[index], independent[index], 150)
        )

    for index, candidate in enumerate(candidates):
        if valid(result[index]) or not valid(candidate) or index in protected:
            continue
        first = last = index
        reason = None
        while True:
            left = next((j for j in range(first - 1, -1, -1) if valid(result[j])), None)
            right = next(
                (j for j in range(last + 1, len(result)) if valid(result[j])), None
            )
            changed = first, last
            if (
                left is not None
                and candidates[first]["start_ms"] < result[left]["end_ms"]
            ):
                first = left
            if (
                right is not None
                and candidates[last]["end_ms"] > result[right]["start_ms"]
            ):
                last = right
            if last - first + 1 > 4:
                reason = "region_limit"
                break
            if any(not valid(candidates[j]) for j in range(first, last + 1)):
                reason = "unsupported_region_word"
                break
            if changed == (first, last):
                break
        if reason is None:
            neighbors = [j for j in (left, right) if j is not None]
            if not neighbors or not all(anchor(j) for j in neighbors):
                reason = "unverified_outer_anchor"
            elif last - first + 1 + len(neighbors) < 2:
                reason = "insufficient_local_context"
        replacement = (
            [dict(u) for u in candidates[first : last + 1]] if reason is None else []
        )
        if reason is None:
            for j in range(first, last + 1):
                old, new = result[j], replacement[j - first]
                if j in protected:
                    replacement[j - first] = dict(old)
                elif valid(old):
                    if agree(old, new, 150) and agree(old, independent[j], 150):
                        replacement[j - first] = dict(old)
                    elif agree(old, new, 150) or agree(old, independent[j], 150):
                        reason = "old_boundary_not_contradicted_twice"
                        break
            chain = (
                ([result[left]] if left is not None else [])
                + replacement
                + ([result[right]] if right is not None else [])
            )
            if reason is None and any(
                a["end_ms"] > b["start_ms"] for a, b in pairwise(chain)
            ):
                reason = "observed_interval_overlap"
        if reason is None:
            added = moved = 0
            for j, new in zip(range(first, last + 1), replacement, strict=True):
                old = result[j]
                added += not valid(old)
                moved += valid(old) and (old["start_ms"], old["end_ms"]) != (
                    new["start_ms"],
                    new["end_ms"],
                )
                result[j] = {
                    **old,
                    "start_ms": new["start_ms"],
                    "end_ms": new["end_ms"],
                }
            events.append(
                {
                    "region": [first, last],
                    "reason": "paired_region",
                    "added": added,
                    "moved": moved,
                }
            )
        else:
            events.append({"region": [first, last], "reason": reason})
    return result, events
