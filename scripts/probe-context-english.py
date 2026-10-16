"""Frozen-corpus English lexical observations and paired boundary trial.

Context ASR is audio-only. Source words enter only this reconciliation step.
Private outputs are proposals; the app and original results are never changed.
"""

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

from audio_first_models import ROOT, digest
from hubertfa_research import private_path

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
from english_boundaries import observed_lexemes


def observations(folder, audio_manifest, *, partial=False):
    recipe = json.loads((folder / "recipe.json").read_text())
    if (
        recipe["manifest_sha256"] != digest(audio_manifest)
        or recipe["language"] != "en"
        or recipe["initial_prompt"] is not None
        or recipe["condition_on_previous_text"] is not False
        or recipe["implementation_sha256"]
        != digest(ROOT / "scripts/transcribe-timing-crops.py")
    ):
        raise ValueError("Changed source-blind context recognition recipe.")
    recipe_sha = digest(folder / "recipe.json")
    cases = json.loads(audio_manifest.read_text())["cases"]
    if partial:
        entries = [
            {"file": hashlib.sha256(c["id"].encode()).hexdigest() + ".json"}
            for c in cases
        ]
    else:
        complete = json.loads((folder / "complete.json").read_text())
        if complete["recipe_sha256"] != recipe_sha or len(complete["records"]) != len(
            cases
        ):
            raise ValueError("Incomplete or changed context recognition.")
        entries = complete["records"]
    result, hashes = {}, {}
    for case, entry in zip(cases, entries, strict=True):
        if Path(entry["file"]).name != entry["file"]:
            raise ValueError("Unsafe context record name.")
        path = folder / entry["file"]
        if partial and not path.exists():
            continue
        sha = digest(path)
        if not partial and sha != entry["sha256"]:
            raise ValueError("Context recognition observation changed.")
        try:
            row = json.loads(path.read_text())
        except json.JSONDecodeError:
            if partial:
                continue
            raise
        if (
            row["case"] != case
            or row["recipe_sha256"] != recipe_sha
            or digest(path) != sha
        ):
            raise ValueError("Changed completed context observation.")
        result[case["id"]] = row
        hashes[case["id"]] = sha
    return result, {"recipe": recipe_sha, "records": hashes, "partial": partial}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--recognition", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--partial", action="store_true")
    args = parser.parse_args()
    for name in ("suite", "contexts", "recognition", "output"):
        setattr(args, name, private_path(getattr(args, name)))
    records, recognition_sha = observations(
        args.recognition, args.contexts / "audio-contexts.json", partial=args.partial
    )
    contexts = json.loads((args.contexts / "suite-contexts.json").read_text())
    if contexts["audio_manifest_sha256"] != digest(
        args.contexts / "audio-contexts.json"
    ) or contexts["identity_sha256"] != digest(args.contexts / "identity.json"):
        raise ValueError("Context cache identity changed.")
    suite = json.loads(args.suite.read_text())
    results, output, eligible = [], {}, {r["track"]: r for r in contexts["songs"]}
    for item in suite["songs"]:
        counts = Counter()
        if (
            digest(Path(item["path"])) != item["sha256"]
            or digest(Path(item["result_path"])) != item["result_sha256"]
        ):
            raise ValueError("Original Rust crops or source result changed.")
        job, saved = (
            json.loads(Path(item[field]).read_text())
            for field in ("path", "result_path")
        )
        song = eligible[item["track"]]
        counts.update(
            original_words=saved["total_words"], original_timed=saved["timed_words"]
        )
        if not song["eligible"]:
            output[item["track"]] = counts
            continue
        if (
            song["job_sha256"] != item["sha256"]
            or song["result_sha256"] != item["result_sha256"]
        ):
            raise ValueError("Context ownership differs from current frozen job.")
        byid = {r["id"]: r for r in saved["snapshot"]["occurrences"]}
        for crop in job["crops"]:
            selected = song["cue_context"].get(str(crop["occurrence"]))
            if selected is None:
                continue
            cases = [
                records.get(f"{item['track']}:{selected}:{role}")
                for role in ("mix", "kim")
            ]
            if not all(cases):
                counts["pending_cues"] += 1
                continue
            line = byid[crop["occurrence"]]
            raw = line["raw_line"].encode()
            fragments = {tuple(f["raw_span"]): f for f in line["fragments"]}
            targets = [
                {
                    **t,
                    "expected_text": raw[t["raw_span"][0] : t["raw_span"][1]].decode(),
                }
                for t in crop["targets"]
            ]
            length_ms = (crop["end_sample"] - crop["start_sample"]) / 16
            views = [
                observed_lexemes(
                    targets,
                    case["segments"],
                    length_ms,
                    offset_ms=(case["case"]["first_sample"] - crop["start_sample"])
                    / 16,
                    context_length_ms=(
                        case["case"]["last_sample"] - case["case"]["first_sample"]
                    )
                    / 16,
                )
                for case in cases
            ]
            baseline = [
                {
                    "raw_span": t["raw_span"],
                    "start_ms": fragments[tuple(t["raw_span"])]["interval"]["start_ms"]
                    - crop["lyric_origin_ms"]
                    if tuple(t["raw_span"]) in fragments
                    else -1,
                    "end_ms": fragments[tuple(t["raw_span"])]["interval"]["end_ms"]
                    - crop["lyric_origin_ms"]
                    if tuple(t["raw_span"]) in fragments
                    else -1,
                }
                for t in targets
            ]
            for old, mix, kim in zip(baseline, *views, strict=True):
                if old["start_ms"] >= 0:
                    continue
                counts["missing_source_groups_checked"] += 1
                counts["mix_lexical"] += mix["source_match"]
                counts["kim_lexical"] += kim["source_match"]
                counts["both_lexical"] += mix["source_match"] and kim["source_match"]
            counts["completed_cues"] += 1
            results.append(
                {
                    "track": item["track"],
                    "occurrence": crop["occurrence"],
                    "targets": targets,
                    "baseline": baseline,
                    "views": views,
                    "source_word_count": crop["source_word_count"],
                    "crop": crop,
                }
            )
        output[item["track"]] = counts
    signature = {
        "suite": digest(args.suite),
        "contexts": digest(args.contexts / "suite-contexts.json"),
        "recognition": recognition_sha,
        "runner": digest(Path(__file__)),
        "lexical_policy": digest(ROOT / "refinement/english_boundaries.py"),
    }
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.umask(0o077)
    with (args.output / "private-records.json").open("x") as handle:
        json.dump(results, handle, indent=2, allow_nan=False)
    signature["records_sha256"] = digest(args.output / "private-records.json")
    for name, data in (
        ("identity.json", signature),
        (
            "summary.json",
            {
                "lexical_only": True,
                "partial": args.partial,
                "per_track": output,
                "both_lexical_gaps": sum(c["both_lexical"] for c in output.values()),
                "app_data_changed": False,
            },
        ),
    ):
        with (args.output / name).open("x") as handle:
            json.dump(data, handle, indent=2, allow_nan=False)
    print(json.dumps({"partial": args.partial, "per_track": output}))


if __name__ == "__main__":
    main()
