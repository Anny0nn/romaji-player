"""Replay closed source-contrast candidates over original frozen song groups privately.

Count gains/losses/moves without app writes. Existing fragment presence, rather
than a crop-relative timestamp's sign, determines which original clocks are protected.
"""

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from hubertfa_research import digest, private_path
from source_contrast_policy import POLICY, recover_original_groups, supported


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.manifest, args.suite, args.observations, args.output = map(
        private_path, (args.manifest, args.suite, args.observations, args.output)
    )
    manifest = json.loads(args.manifest.read_text())
    recipe = json.loads((args.observations / "identity.json").read_text())
    complete = json.loads((args.observations / "complete.json").read_text())
    if (
        manifest["identity"]["suite_sha256"] != digest(args.suite)
        or recipe["manifest_sha256"] != digest(args.manifest)
        or complete["identity_sha256"] != digest(args.observations / "identity.json")
    ):
        raise ValueError(
            "Unclosed observations or changed frozen source/crop identity."
        )
    rows = {}
    for entry in complete["records"]:
        path = args.observations / entry["file"]
        if Path(entry["file"]).name != entry["file"] or digest(path) != entry["sha256"]:
            raise ValueError("Changed completed acoustic evidence.")
        row = json.loads(path.read_text())["record"]
        if row["id"] in rows:
            raise ValueError("Duplicate acoustic ownership.")
        rows[row["id"]] = row
    if set(rows) != {c["id"] for c in manifest["cases"]}:
        raise ValueError("Incomplete source candidate collection.")
    counts, occurrences = {}, {}
    for song in json.loads(args.suite.read_text())["songs"]:
        result = Path(song["result_path"])
        if digest(result) != song["result_sha256"]:
            raise ValueError("Frozen saved baseline changed.")
        saved = json.loads(result.read_text())
        occurrences[song["track"]] = {
            o["id"]: o for o in saved["snapshot"]["occurrences"]
        }
        counts[song["track"]] = Counter(
            original_groups=saved["total_words"],
            original_timed=saved["timed_words"],
            added=0,
            moved=0,
            lost=0,
        )
    private = []
    for group in manifest["groups"]:
        count = counts[group["track"]]
        original = occurrences[group["track"]][group["occurrence"]]
        present = {tuple(f["raw_span"]) for f in original["fragments"]}
        baseline = [
            {**u, "protected": tuple(u["raw_span"]) in present}
            for u in group["baseline"]
        ]
        views = [rows[ident]["words"] for ident in group["ids"]]
        output = recover_original_groups(
            baseline, views, group["length_ms"], group["source_word_count"]
        )
        count["tested_cues"] += 1
        for old, new, a, b in zip(baseline, output, *views, strict=True):
            if old["protected"]:
                count["moved"] += (old["start_ms"], old["end_ms"]) != (
                    new["start_ms"],
                    new["end_ms"],
                )
                count["lost"] += old != new
            else:
                count["dual_acoustic_missing_candidates"] += supported(
                    a, group["length_ms"]
                ) and supported(b, group["length_ms"])
                count["added"] += new["start_ms"] >= 0
        private.append({**group, "protected_baseline": baseline, "result": output})
    for count in counts.values():
        count["proposed_timed"] = (
            count["original_timed"] + count["added"] - count["lost"]
        )
    summary = {
        "per_song": counts,
        "totals": {
            key: sum(count.get(key, 0) for count in counts.values())
            for key in (
                "original_groups",
                "original_timed",
                "tested_cues",
                "added",
                "moved",
                "lost",
                "proposed_timed",
                "dual_acoustic_missing_candidates",
            )
        },
        "policy": POLICY,
        "policy_sha256": digest(Path(__file__).with_name("source_contrast_policy.py")),
        "evaluator_sha256": digest(Path(__file__)),
        "manifest_sha256": digest(args.manifest),
        "observation_complete_sha256": digest(args.observations / "complete.json"),
        "promoted": False,
        "saved_app_data_changed": False,
        "timing_accuracy_not_inferred_from_coverage": True,
    }
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False)
    )
    (args.output / "private-records.json").write_text(
        json.dumps(private, indent=2, allow_nan=False)
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
