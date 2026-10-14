"""Freeze a capped 70/30 mix from measured, incompletely timed recordings.

Input: {"schema_version": 1, "songs": [{"track", "status", ...}]}. Measured
rows require engine, model_sha256, base_snapshot, timed_words, total_words and result_sha256.
Other statuses are excluded and reported; they are never assigned zero coverage.
The output is created exclusively, so an existing frozen set cannot be reranked.
"""

import argparse
import hashlib
import json
import re
from fractions import Fraction
from pathlib import Path


def select(rows, cap=10):
    if type(cap) is not int or cap < 1:
        raise ValueError("The song cap must be a positive integer.")
    seen, eligible, excluded, engines = set(), [], [], set()
    for row in rows:
        track = row["track"]
        if not isinstance(track, str) or not re.fullmatch(r"[A-Za-z0-9]{22}", track):
            raise ValueError("Invalid Spotify recording identity.")
        if track in seen:
            raise ValueError(
                "Duplicate measurement; choose one frozen baseline per recording."
            )
        seen.add(track)
        status = row["status"]
        if not isinstance(status, str) or not status:
            raise ValueError("Missing measurement status.")
        if status in {"pending", "unmeasured", "captured", "running"}:
            raise ValueError("Finish the initial baseline sweep before freezing a set.")
        if status != "measured":
            excluded.append({"track": track, "reason": status})
            continue
        timed, total = row["timed_words"], row["total_words"]
        if (
            type(timed) is not int
            or type(total) is not int
            or not 0 <= timed <= total
            or total < 1
        ):
            raise ValueError("Invalid measured source-group counts.")
        if (
            not isinstance(row["engine"], str)
            or not row["engine"]
            or not isinstance(row["base_snapshot"], str)
            or not row["base_snapshot"]
            or not re.fullmatch(r"[a-f0-9]{64}", row["result_sha256"])
            or not re.fullmatch(r"[a-f0-9]{64}", row["model_sha256"])
        ):
            raise ValueError("Missing frozen result or recipe identity.")
        engines.add((row["engine"], row["model_sha256"]))
        if timed == total:
            excluded.append({"track": track, "reason": "fully_covered"})
        else:
            eligible.append(row)
    if len(engines) > 1:
        raise ValueError(
            "Coverage rankings must use the same baseline recipe and models."
        )

    effective_cap = min(cap, len(eligible))
    low_count = (7 * effective_cap + 5) // 10
    low = sorted(
        eligible,
        key=lambda row: (
            Fraction(row["timed_words"], row["total_words"]),
            row["track"],
        ),
    )[:low_count]
    low_ids = {row["track"] for row in low}
    high = sorted(
        (row for row in eligible if row["track"] not in low_ids),
        key=lambda row: (
            -Fraction(row["timed_words"], row["total_words"]),
            row["track"],
        ),
    )[: effective_cap - low_count]

    def frozen(row):
        return {
            key: row[key]
            for key in (
                "track",
                "engine",
                "model_sha256",
                "base_snapshot",
                "timed_words",
                "total_words",
                "result_sha256",
            )
        }

    return {
        "schema_version": 1,
        "policy": "lowest-70-highest-incomplete-30-v1",
        "requested_cap": cap,
        "effective_cap": effective_cap,
        "shortfall": cap - effective_cap,
        "engine": next(iter(engines))[0] if engines else None,
        "model_sha256": next(iter(engines))[1] if engines else None,
        "low": [frozen(row) for row in low],
        "high": [frozen(row) for row in high],
        "excluded": sorted(excluded, key=lambda row: row["track"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("measurements", type=Path)
    parser.add_argument("--cap", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = args.measurements.read_bytes()
        data = json.loads(raw)
        if data["schema_version"] != 1:
            raise ValueError("Unknown measurement schema.")
        result = select(data["songs"], args.cap)
        result["measurements_sha256"] = hashlib.sha256(raw).hexdigest()
        with args.output.open("x") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(
            1, "Invalid measurements or unavailable output; no frozen set replaced.\n"
        )
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("requested_cap", "effective_cap", "shortfall")
            }
        )
    )


if __name__ == "__main__":
    main()
