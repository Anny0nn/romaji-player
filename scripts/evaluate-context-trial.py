"""Replay a private context challenger through the shared application policy.

Manifest: mix_cases, rust_manifests, cases, tifa, mms, results [{track,path}].
All outputs stay private. Models are not loaded; baseline fragments are unchanged
unless the atomic, independently supported context policy admits a repair.
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
from context_policy import apply_context

spec = importlib.util.spec_from_file_location(
    "diagnostics", ROOT / "scripts/diagnose-song-suite.py"
)
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


def evaluate(cases, mix, rust, tifa, mms, results):
    originals = diagnostics.attach_rust_crops(mix, rust)
    tifa, mms = diagnostics.indexed(tifa), diagnostics.indexed(mms)
    if set(tifa) != set(mms) or set(tifa) != {c["id"] for c in cases}:
        raise ValueError("Changed context experiment case set.")
    output, ledger = {}, []
    for track, saved in results.items():
        rows = sorted(
            [
                c
                for c in originals
                if c.get("track") == track and not c["id"].startswith("control:")
            ],
            key=lambda c: (c["start_ms"], c["occurrence"]),
        )
        lines = {line["id"]: line for line in saved["snapshot"]["occurrences"]}
        positions = {row["occurrence"]: i for i, row in enumerate(rows)}
        crops, baseline = [], []
        for row in rows:
            if (
                saved["base_snapshot"] != row["snapshot"]
                or saved["delay_ms"] != row["delay_ms"]
                or lines[row["occurrence"]]["raw_line"] != row["raw_line"]
            ):
                raise ValueError("Saved source/clock changed before context replay.")
            targets, units = [], []
            for word in row["words"]:
                text = (
                    "".join(c for c in word["hiragana"] if c.isalnum())
                    or word["expected_text"]
                )
                target = {
                    "raw_span": word["raw_span"],
                    "text": text,
                    "romaji": word["romaji"],
                }
                targets.append(target)
                fragments = [
                    f
                    for f in lines[row["occurrence"]]["fragments"]
                    if f["raw_span"] == word["raw_span"]
                ]
                if len(fragments) > 1:
                    raise ValueError(
                        "Unexpected multiple saved intervals per source word."
                    )
                units.append(
                    {
                        **target,
                        "start_ms": fragments[0]["interval"]["start_ms"]
                        - row["lyric_origin_ms"]
                        if fragments
                        else -1,
                        "end_ms": fragments[0]["interval"]["end_ms"]
                        - row["lyric_origin_ms"]
                        if fragments
                        else -1,
                    }
                )
            crops.append((row["occurrence"], *row["rust_crop_samples"], targets))
            baseline.append(units)
        jobs, trials, proofs = [], [], []
        for case in [c for c in cases if c["track"] == track]:
            if case["parent_snapshot"] != saved["base_snapshot"]:
                raise ValueError("Changed parent source snapshot.")
            trial, proof = tifa[case["id"]], mms[case["id"]]
            if any(
                any(record[k] != case[k] for k in diagnostics.IDENTITY)
                for record in (trial, proof)
            ):
                raise ValueError("Changed context audio/source/crop identity.")
            owners = [
                (
                    positions[o["occurrence"]],
                    next(
                        i
                        for i, t in enumerate(crops[positions[o["occurrence"]]][3])
                        if t["raw_span"] == o["raw_span"]
                    ),
                )
                for o in case["owners"]
            ]
            targets = [
                {
                    "raw_span": w["raw_span"],
                    "text": "".join(c for c in w["hiragana"] if c.isalnum())
                    or w["expected_text"],
                    "romaji": w["romaji"],
                }
                for w in case["words"]
            ]
            jobs.append(
                {
                    "crop": (len(jobs), *case["rust_crop_samples"], targets),
                    "owners": owners,
                    "nominated": [o["nominated"] for o in case["owners"]],
                    "source_words": sum(
                        rows[i]["source_word_count"]
                        for i in sorted({line for line, _ in owners})
                    ),
                }
            )
            trials.append(trial)
            proofs.append(proof["units"])
        repaired = apply_context(baseline, crops, jobs, trials, proofs)
        counts = {
            "baseline": sum(u["start_ms"] >= 0 for units in baseline for u in units),
            "new_words": 0,
            "lost_words": 0,
            "changed_existing": 0,
        }
        for row, old, new in zip(rows, baseline, repaired, strict=True):
            for before, after in zip(old, new, strict=True):
                gained = before["start_ms"] < 0 <= after["start_ms"]
                lost = before["start_ms"] >= 0 > after["start_ms"]
                changed = before["start_ms"] >= 0 and any(
                    before[k] != after[k] for k in ("start_ms", "end_ms")
                )
                counts["new_words"] += gained
                counts["lost_words"] += lost
                counts["changed_existing"] += changed
                if gained or lost or changed:
                    ledger.append(
                        {
                            "track": track,
                            "occurrence": row["occurrence"],
                            "raw_span": after["raw_span"],
                            "gained": gained,
                            "before": before,
                            "after": after,
                            "lyric_origin_ms": row["lyric_origin_ms"],
                        }
                    )
        if counts["baseline"] != saved["timed_words"]:
            raise ValueError("Replay baseline coverage differs from frozen result.")
        counts["retained"] = (
            counts["baseline"] + counts["new_words"] - counts["lost_words"]
        )
        output[track] = counts
    return output, ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = args.manifest.resolve()
    config = json.loads(manifest.read_text())
    hashes = {}

    def load(name):
        data = (manifest.parent / name).resolve().read_bytes()
        hashes[name] = hashlib.sha256(data).hexdigest()
        return json.loads(data)

    results = {}
    for row in config["results"]:
        if row["track"] in results:
            raise ValueError("Duplicate saved recording.")
        results[row["track"]] = load(row["path"])
    summary, ledger = evaluate(
        load(config["cases"]),
        load(config["mix_cases"]),
        [load(path) for path in config["rust_manifests"]],
        load(config["tifa"]),
        load(config["mms"]),
        results,
    )
    output = diagnostics.private_output(args.output)
    diagnostics.write_private(
        output / "summary.json",
        {
            "per_track": summary,
            "input_sha256": hashes,
            "policy_sha256": hashlib.sha256(
                (ROOT / "refinement/context_policy.py").read_bytes()
            ).hexdigest(),
        },
    )
    diagnostics.write_private(output / "ledger.jsonl", ledger, jsonl=True)
    print(
        json.dumps(
            {
                "new_words": sum(v["new_words"] for v in summary.values()),
                "lost_words": sum(v["lost_words"] for v in summary.values()),
                "changed_existing": sum(
                    v["changed_existing"] for v in summary.values()
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
