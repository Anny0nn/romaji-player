"""Join adjacent source cues without losing occurrence or UTF-8 ownership."""

import math


def join_cues(crops, occurrences, first_sample, last_sample):
    if (
        type(first_sample) is not int
        or type(last_sample) is not int
        or not 0 <= first_sample < last_sample
        or last_sample - first_sample > 480000
        or not crops
    ):
        raise ValueError("Joint source context is outside bounded recording samples.")
    lines, targets, owners, baseline = [], [], [], []
    offset, previous_sample, seen = 0, -1, set()
    for crop in crops:
        occurrence = crop["occurrence"]
        if (
            occurrence in seen
            or not first_sample
            <= crop["start_sample"]
            < crop["end_sample"]
            <= last_sample
            or crop["start_sample"] < previous_sample
            or occurrences[occurrence]["raw_line"] != crop["raw_line"]
        ):
            raise ValueError(
                "Joint source cue identity, order or sample bounds changed."
            )
        seen.add(occurrence)
        previous_sample = crop["start_sample"]
        data, previous_byte = crop["raw_line"].encode(), 0
        fragments = {
            tuple(f["raw_span"]): f for f in occurrences[occurrence]["fragments"]
        }
        if len(fragments) != len(occurrences[occurrence]["fragments"]):
            raise ValueError("Duplicate saved source fragment.")
        for target in crop["targets"]:
            first, last = target["raw_span"]
            if (
                type(first) is not int
                or type(last) is not int
                or not previous_byte <= first < last <= len(data)
            ):
                raise ValueError("Changed original word source ownership.")
            try:
                data[:first].decode()
                data[first:last].decode()
            except UnicodeDecodeError as error:
                raise ValueError(
                    "Joint context splits an original UTF-8 character."
                ) from error
            previous_byte = last
            span = [first + offset, last + offset]
            targets.append({**target, "raw_span": span})
            owners.append({"occurrence": occurrence, "raw_span": target["raw_span"]})
            fragment = fragments.get(tuple(target["raw_span"]))
            interval = fragment["interval"] if fragment else None
            baseline.append(
                {
                    "raw_span": span,
                    "start_ms": interval["start_ms"] - first_sample / 16
                    if interval
                    else -1,
                    "end_ms": interval["end_ms"] - first_sample / 16
                    if interval
                    else -1,
                    "protected": fragment is not None,
                }
            )
        lines.append(crop["raw_line"])
        offset += len(data) + 1
    return {
        "raw_line": "\n".join(lines),
        "targets": targets,
        "owners": owners,
        "baseline": baseline,
        "first_sample": first_sample,
        "last_sample": last_sample,
        "source_word_count": sum(c["source_word_count"] for c in crops),
    }


def reattach_units(joined, units):
    if len(units) != len(joined["targets"]) or any(
        a["raw_span"] != b["raw_span"]
        for a, b in zip(units, joined["targets"], strict=True)
    ):
        raise ValueError("Joint observation changed original group ownership.")
    result = {}
    length = (joined["last_sample"] - joined["first_sample"]) / 16
    for unit, owner in zip(units, joined["owners"], strict=True):
        start, end = unit["start_ms"], unit["end_ms"]
        empty = start == end == -1
        if not empty and (
            any(
                not isinstance(v, (int, float))
                or isinstance(v, bool)
                or not math.isfinite(v)
                for v in (start, end)
            )
            or not 0 <= start < end <= length
        ):
            raise ValueError("Joint word has no valid observed acoustic envelope.")
        result.setdefault(owner["occurrence"], []).append(
            {
                "raw_span": owner["raw_span"],
                "start_ms": start + joined["first_sample"] / 16 if not empty else -1,
                "end_ms": end + joined["first_sample"] / 16 if not empty else -1,
            }
        )
    return result
