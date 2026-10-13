"""Human phone-boundary metrics; kept separate from commercial word coverage."""

import math
import random
from collections import defaultdict

SILENCE = {"pau", "sil", "silB", "silE"}


def verify_extracted(archive_path, path):
    """A frozen archive must also authenticate the extracted inference input."""
    import hashlib
    import zipfile
    from pathlib import Path

    with zipfile.ZipFile(archive_path) as archive:
        matches = [name for name in archive.namelist() if Path(name).name == path.name]
        with path.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if (
            len(matches) != 1
            or hashlib.sha256(archive.read(matches[0])).hexdigest() != actual
        ):
            raise ValueError("Extracted reference changed from its frozen archive.")


def htk_labels(text, duration_ms):
    """PJS .lab times are integer 100 ns ticks, not score or synthesis times."""
    result, previous = [], 0
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 3:
            raise ValueError("Expected a monophone HTK label.")
        first, last = int(fields[0]), int(fields[1])
        if not previous <= first < last or last / 10_000 > duration_ms + 1:
            raise ValueError("Invalid, overlapping or out-of-recording label.")
        previous = last
        result.append(
            {
                "unit": len(result),
                "phone": fields[2],
                "start_ms": first / 10_000,
                "end_ms": last / 10_000,
                "uncertainty_ms": None,
            }
        )
    if not result:
        raise ValueError("Empty reference labels.")
    return result


def wilson(correct, count):
    if not count:
        return None
    z, p = 1.959963984540054, correct / count
    denominator = 1 + z * z / count
    center = (p + z * z / (2 * count)) / denominator
    radius = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count**2)) / denominator
    return [max(0, center - radius), min(1, center + radius)]


def quantile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower = int(position)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (
        position - lower
    )


def evaluate(records):
    """Missing spans are abstentions. Phone inputs do not test recognition accuracy."""
    errors, groups = [], defaultdict(list)
    total = 0
    for record in records:
        reference, predicted = record["reference"], record["predicted"]
        if len(reference) != len(predicted):
            raise ValueError("Reference and predicted phone ownership changed.")
        for ref, unit in zip(reference, predicted, strict=True):
            if ref["unit"] != unit["unit"] or ref["phone"] != unit["phone"]:
                raise ValueError("Reference and prediction are not the same phone.")
            if ref["phone"] in SILENCE:
                continue
            total += 1
            start, end = unit["start_ms"], unit["end_ms"]
            if start == end == -1:
                groups[record["id"]].append(None)
                continue
            if not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end:
                raise ValueError("Invalid predicted phone interval.")
            pair = abs(start - ref["start_ms"]), abs(end - ref["end_ms"])
            errors.append(pair)
            groups[record["id"]].append(pair)
    onset, offset = [p[0] for p in errors], [p[1] for p in errors]
    correct = sum(a <= 150 and b <= 200 for a, b in errors)
    randomizer = random.Random(0)
    ids = sorted(groups)
    bootstrap = []
    if ids:
        for _ in range(2000):
            pairs = [
                p
                for key in randomizer.choices(ids, k=len(ids))
                for p in groups[key]
                if p is not None
            ]
            if pairs:
                bootstrap.append(
                    sum(a <= 150 and b <= 200 for a, b in pairs) / len(pairs)
                )
    return {
        "granularity": "phone",
        "recognition_accuracy_measured": False,
        "phrases": len(groups),
        "reference_units": total,
        "aligned_units": len(errors),
        "abstentions": total - len(errors),
        "joint_onset_150_offset_200": correct,
        "joint_fraction": correct / len(errors) if errors else None,
        "wilson_95_descriptive": wilson(correct, len(errors)),
        "phrase_bootstrap_95": [quantile(bootstrap, 0.025), quantile(bootstrap, 0.975)],
        "errors_ms": {
            key: {
                "median": quantile(values, 0.5),
                "p90": quantile(values, 0.9),
                "p95": quantile(values, 0.95),
                "fractions_within": {
                    str(limit): sum(v <= limit for v in values) / len(values)
                    if values
                    else None
                    for limit in (50, 100, 150, 200, 250)
                },
            }
            for key, values in (("onset", onset), ("offset", offset))
        },
    }


def selected_ids(split, partition, receipt, expected_receipt):
    dev, heldout = split["development"], split["heldout"]
    if not dev or not heldout or len(set(dev + heldout)) != len(dev + heldout):
        raise ValueError("Invalid or overlapping reference partition.")
    if partition == "heldout":
        if receipt != expected_receipt:
            raise ValueError(
                "Freeze exact recipes and reference assets before opening heldout labels."
            )
        return heldout
    if partition != "development":
        raise ValueError("Unknown reference partition.")
    return dev
