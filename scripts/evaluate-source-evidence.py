"""Evaluate closed conditional evidence against human word clocks or negative controls.

This is an exploratory development gate. It does not promote an app recipe or
combine reference correctness with retained commercial coverage.
"""

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from hubertfa_research import digest, private_path
from singing_reference import evaluate
from source_contrast_policy import POLICY, supported


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--silence-only", action="store_true")
    args = parser.parse_args()
    args.manifest, args.observations, args.output = map(
        private_path, (args.manifest, args.observations, args.output)
    )
    identity = json.loads((args.observations / "identity.json").read_text())
    complete = json.loads((args.observations / "complete.json").read_text())
    if identity["manifest_sha256"] != digest(args.manifest) or complete[
        "identity_sha256"
    ] != digest(args.observations / "identity.json"):
        raise ValueError("Not completed evidence for this exact candidate set.")
    rows = {}
    for entry in complete["records"]:
        path = args.observations / entry["file"]
        if path.parent != args.observations or digest(path) != entry["sha256"]:
            raise ValueError("Changed completed source observation.")
        envelope = json.loads(path.read_text())
        row = envelope["record"]
        if row["id"] in rows:
            raise ValueError("Duplicate evidence ownership.")
        rows[row["id"]] = row
    manifest = json.loads(args.manifest.read_text())
    if set(rows) != {c["id"] for c in manifest["cases"]}:
        raise ValueError("Incomplete candidate observations.")
    by_song, raw_records, gated_records = defaultdict(Counter), [], []
    for case in manifest["cases"]:
        row = rows[case["id"]]
        if [u["raw_span"] for u in row["words"]] != [
            u["raw_span"] for u in case["targets"]
        ]:
            raise ValueError("Observation changed original group identities.")
        length_ms = (case["audio"]["last_sample"] - case["audio"]["first_sample"]) / 16
        flags = [
            supported(u, length_ms, wrong_verse=not args.silence_only)
            for u in row["words"]
        ]
        count = by_song[case.get("song", "controls")]
        count["original_groups"] += len(flags)
        count["qualifying_groups"] += sum(flags)
        if case.get("negative"):
            count["false_accepts"] += sum(flags)
            continue
        refs = case["reference"]
        if [u["raw_span"] for u in refs] != [u["raw_span"] for u in case["targets"]]:
            raise ValueError("Human references changed original group identities.")
        raw, gated = [], []
        for ref, observed, flag in zip(refs, row["words"], flags, strict=True):
            # The metric's phone field is the exact human word string here.
            reference = {**ref, "phone": ref["text"]}
            valid = observed["start_ms"] >= 0
            raw.append(
                {
                    **reference,
                    "start_ms": observed["start_ms"] if valid else -1,
                    "end_ms": observed["end_ms"] if valid else -1,
                }
            )
            gated.append(
                {
                    **reference,
                    "start_ms": observed["start_ms"] if flag else -1,
                    "end_ms": observed["end_ms"] if flag else -1,
                }
            )
            correct = (
                valid
                and abs(observed["start_ms"] - ref["start_ms"]) <= 150
                and abs(observed["end_ms"] - ref["end_ms"]) <= 200
            )
            count["qualifying_joint_correct"] += flag and correct
        references = [{**u, "phone": u["text"]} for u in refs]
        raw_records.append(
            {"id": case["id"], "reference": references, "predicted": raw}
        )
        gated_records.append(
            {"id": case["id"], "reference": references, "predicted": gated}
        )
    summary = {
        "policy": POLICY,
        "wrong_verse_required": not args.silence_only,
        "by_song": dict(by_song),
        "observed_boundaries": {
            **evaluate(raw_records),
            "granularity": "human_normalized_word",
        },
        "contrast_gate": {
            **evaluate(gated_records),
            "granularity": "human_normalized_word",
        },
        "promoted": False,
        "boundary_kinds": sorted(
            {
                u.get("boundary_kind", "unspecified")
                for row in rows.values()
                for u in row["words"]
            }
        ),
        "saved_app_data_changed": False,
        "observation_complete_sha256": digest(args.observations / "complete.json"),
        "manifest_sha256": digest(args.manifest),
        "policy_sha256": digest(Path(__file__).with_name("source_contrast_policy.py")),
        "evaluator_sha256": digest(Path(__file__)),
    }
    os.umask(0o077)
    with args.output.open("x") as output:
        json.dump(summary, output, indent=2, allow_nan=False)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
