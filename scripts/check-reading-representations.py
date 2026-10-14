"""Compare a new converter to frozen legacy outputs; lyric-bearing files stay private."""

import argparse
import copy
import json
import os
import sys
from pathlib import Path

from audio_first_models import ROOT, digest

sys.path.insert(0, str(ROOT / "romanizer"))


def compatible(before, after):
    """Ignore only the explicitly versioned additions, never old mappings or readings."""
    before, after = copy.deepcopy(before), copy.deepcopy(after)
    for value in (before, after):
        value.pop("protocol_version")
        value.pop("conversion_signature")
        value.pop("katakana", None)
        value.pop("representation", None)
        for word in value["words"]:
            word.pop("reading", None)
            word.pop("katakana_span", None)
    return before == after


def main():
    from romanizer import PROTOCOL, Converter, slice_bytes

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frozen", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if ROOT == args.output.resolve() or ROOT in args.output.resolve().parents:
        parser.error("Choose a new private output outside the checkout.")
    if args.output.exists():
        parser.error("Do not overwrite a frozen receipt.")
    frozen = json.loads(args.frozen.read_text())
    converter = Converter()
    records, counts = (
        [],
        {"windows": 0, "groups": 0, "retained": 0, "changed_legacy_outputs": 0},
    )
    for row in frozen["records"]:
        request = {
            **row["request"],
            "protocol_version": PROTOCOL,
            "expected_conversion_signature": converter.signature,
        }
        response = converter.convert(request)
        unchanged = compatible(row["response"], response)
        counts["windows"] += 1
        counts["groups"] += len(response["words"])
        counts["retained"] += sum(u["start_ms"] >= 0 for u in row["baseline"])
        counts["changed_legacy_outputs"] += not unchanged
        for word in response["words"]:
            reading = word["reading"]
            if reading["romaji"] != slice_bytes(
                response["romaji"], word["output_span"]
            ):
                raise ValueError("Rendered romaji differs from the selected reading.")
        records.append({"id": row["id"], "request": request, "response": response})
    os.umask(0o077)
    args.output.write_text(
        json.dumps(
            {
                "frozen_sha256": digest(args.frozen),
                "conversion_signature": converter.signature,
                "counts": counts,
                "records": records,
            },
            ensure_ascii=False,
        )
    )
    print(json.dumps(counts))
    if counts["changed_legacy_outputs"]:
        raise SystemExit("The representation migration changed a frozen legacy output.")


if __name__ == "__main__":
    main()
