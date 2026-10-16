"""Exact source-owned protocol for the existing native raw-timing helper."""

import math
import struct


def request(cases):
    data = bytearray(struct.pack("<II", 2, len(cases)))
    for number, case in enumerate(cases):
        audio, targets = case["audio"], case["targets"]
        data.extend(
            struct.pack(
                "<IIII",
                number,
                audio["first_sample"],
                audio["last_sample"],
                len(targets),
            )
        )
        previous = 0
        for word in targets:
            first, last = word["raw_span"]
            text = word["text"]
            encoded = text.encode()
            if (
                any(type(v) is not int for v in (first, last))
                or not 0 <= previous <= first < last <= 8192
                or not encoded
                or len(encoded) > 8192
                or any(c.isspace() for c in text)
            ):
                raise ValueError("Invalid source-owned native word group.")
            previous = last
            data.extend(struct.pack("<III", first, last, len(encoded)))
            data.extend(encoded)
    return bytes(data)


def validate_reply(case, reply):
    targets = case["targets"]
    empty = [{"raw_span": w["raw_span"], "start_ms": -1, "end_ms": -1} for w in targets]
    if not reply["units"]:
        return empty
    units = reply["units"]
    if len(units) != len(targets) or any(
        a["raw_span"] != b["raw_span"] or a["text"] != b["text"]
        for a, b in zip(units, targets, strict=True)
    ):
        raise ValueError("Native reply changed original word ownership.")
    length_ms = (case["audio"]["last_sample"] - case["audio"]["first_sample"]) / 16
    result = []
    for unit, withheld in zip(units, empty, strict=True):
        first, last = unit["start_ms"], unit["end_ms"]
        valid = (
            all(
                isinstance(v, (int, float))
                and not isinstance(v, bool)
                and math.isfinite(v)
                for v in (first, last)
            )
            and 0 <= first < last <= length_ms
        )
        result.append(
            {**withheld, "start_ms": first, "end_ms": last} if valid else withheld
        )
    return result
