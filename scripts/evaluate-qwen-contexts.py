"""Replay source-blind Qwen context recognition with fresh independent pair clocks.

Recognition never supplies word times. Match full source windows before assigning
words to occurrences, and preserve every existing fragment, including negative
crop-relative starts. Outputs are private research proposals, never app writes.
"""

import argparse
import importlib.util
import json
import os
from collections import Counter
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path
from qwen_lexical import context_matches, recognition_words, recover_recognized_pairs

spec = importlib.util.spec_from_file_location(
    "qwen_collector", ROOT / "scripts/collect-qwen-lexical.py"
)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
spec = importlib.util.spec_from_file_location(
    "english_boundary_probe", ROOT / "scripts/probe-english-boundaries.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in (
        "suite",
        "contexts",
        "paired",
        "lexical",
        "observations",
        "model-directory",
        "output",
    ):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    for key, value in vars(args).items():
        setattr(args, key, private_path(value))
    suite = json.loads(args.suite.read_text())
    context = json.loads((args.contexts / "suite-contexts.json").read_text())
    audio = json.loads((args.contexts / "audio-contexts.json").read_text())
    pair_id = json.loads((args.paired / "identity.json").read_text())
    lexical_id = json.loads((args.lexical / "identity.json").read_text())
    if (
        context["identity_sha256"] != digest(args.contexts / "identity.json")
        or context["audio_manifest_sha256"]
        != digest(args.contexts / "audio-contexts.json")
        or pair_id["suite"] != digest(args.suite)
        or pair_id["lexical_identity"] != digest(args.lexical / "identity.json")
        or pair_id["lexical_records"] != digest(args.lexical / "private-records.json")
        or lexical_id["contexts"] != digest(args.contexts / "suite-contexts.json")
        or lexical_id["suite"] != digest(args.suite)
        or lexical_id["records_sha256"] != digest(args.lexical / "private-records.json")
    ):
        raise ValueError("Changed frozen source, recognition context or paired recipe.")
    recipe, observed, tokenizer = collector.closed_observations(
        args.observations, args.model_directory
    )
    if recipe["manifest_sha256"] != digest(args.contexts / "audio-contexts.json") or {
        c["id"]: c for c in audio["cases"]
    } != {key: row["case"] for key, row in observed.items()}:
        raise ValueError("Closed recognition does not cover the exact frozen contexts.")
    lexical, counts, records, pair_hashes = {}, {}, [], {}
    recognition_counts = Counter(
        views=0, token_budget=0, other_language=0, unreconstructible_transcript=0
    )
    for key, row in observed.items():
        lexical[key], rejection = recognition_words(tokenizer, row, recipe["language"])
        recognition_counts["views"] += 1
        if rejection:
            recognition_counts[rejection] += 1
    by_track = {s["track"]: s for s in context["songs"]}
    for song in suite["songs"]:
        track = song["track"]
        if any(
            digest(Path(song[field])) != song[sha]
            for field, sha in (("path", "sha256"), ("result_path", "result_sha256"))
        ):
            raise ValueError("Frozen Rust source or baseline changed.")
        job = json.loads(Path(song["path"]).read_text())
        saved = json.loads(Path(song["result_path"]).read_text())
        counts[track] = count = Counter(
            original_groups=saved["total_words"],
            original_timed=saved["timed_words"],
            added=0,
            lost=0,
            moved=0,
        )
        metadata = by_track[track]
        if not metadata["eligible"]:
            continue
        if (
            metadata["job_sha256"] != song["sha256"]
            or metadata["result_sha256"] != song["result_sha256"]
        ):
            raise ValueError("Context belongs to another source snapshot.")
        crops = {c["occurrence"]: c for c in job["crops"]}
        occurrences = {o["id"]: o for o in saved["snapshot"]["occurrences"]}
        matches = {}
        for index, window in enumerate(metadata["windows"]):
            owners = [crops[n] for n in window["occurrences"]]
            for role in ("mix", "kim"):
                key = f"{track}:{index}:{role}"
                if key not in lexical:
                    continue
                case = observed[key]["case"]
                if (case["first_sample"], case["last_sample"]) != (
                    window["first_sample"],
                    window["last_sample"],
                ):
                    raise ValueError("Recognition changed source window bounds.")
                matches[index, role] = context_matches(owners, lexical[key])
        for occurrence, selected in metadata["cue_context"].items():
            occurrence = int(occurrence)
            crop = crops[occurrence]
            path = args.paired / f"{track}-{occurrence}.json"
            if not path.exists():
                count["no_cached_pair_cues"] += 1
                continue
            paired = probe.checkpoints.read_checkpoint(path, pair_id)
            if (paired["track"], paired["occurrence"]) != (track, occurrence):
                raise ValueError("Pair belongs to another occurrence.")
            pair_hashes[path.name] = digest(path)
            length_ms = (crop["end_sample"] - crop["start_sample"]) / 16
            clocks = [
                probe.paired_boundary(a, b, length_ms)
                or {"raw_span": t["raw_span"], "start_ms": -1, "end_ms": -1}
                for a, b, t in zip(
                    paired["tifa"], paired["hfa"], crop["targets"], strict=True
                )
            ]
            old = occurrences[occurrence]
            fragments = {tuple(f["raw_span"]): f for f in old["fragments"]}
            baseline = []
            for target in crop["targets"]:
                fragment = fragments.get(tuple(target["raw_span"]))
                baseline.append(
                    {
                        "raw_span": target["raw_span"],
                        "protected": fragment is not None,
                        **{
                            key: fragment["interval"][key] - crop["lyric_origin_ms"]
                            if fragment
                            else -1
                            for key in ("start_ms", "end_ms")
                        },
                    }
                )
            views = [matches[selected, role][occurrence] for role in ("mix", "kim")]
            result = recover_recognized_pairs(
                baseline, clocks, views, length_ms, crop["source_word_count"]
            )
            for old, new, a, b, clock in zip(
                baseline, result, *views, clocks, strict=True
            ):
                if old["protected"]:
                    count["lost"] += not new["protected"]
                    count["moved"] += old != new
                else:
                    count["gaps_checked"] += 1
                    count["dual_lexical_gaps"] += (
                        a["source_match"] and b["source_match"]
                    )
                    count["paired_dual_gaps"] += (
                        a["source_match"]
                        and b["source_match"]
                        and clock["start_ms"] >= 0
                    )
                    count["added"] += new["start_ms"] >= 0
            count["tested_cues"] += 1
            records.append(
                {
                    "track": track,
                    "occurrence": occurrence,
                    "baseline": baseline,
                    "clocks": clocks,
                    "views": views,
                    "result": result,
                }
            )
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (args.output / "private-records.json").write_text(
        json.dumps(records, allow_nan=False)
    )
    identity = {
        "suite_sha256": digest(args.suite),
        "context_sha256": digest(args.contexts / "suite-contexts.json"),
        "recognition_complete_sha256": digest(args.observations / "complete.json"),
        "pair_identity_sha256": digest(args.paired / "identity.json"),
        "pair_records": pair_hashes,
        "code": {
            name: digest(ROOT / "scripts" / name)
            for name in (
                "evaluate-qwen-contexts.py",
                "collect-qwen-lexical.py",
                "qwen_lexical.py",
                "source_contrast_policy.py",
            )
        },
        "records_sha256": digest(args.output / "private-records.json"),
    }
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2))
    summary = {
        "per_song": counts,
        "totals": dict(sum(counts.values(), Counter())),
        "recognition_views": recognition_counts,
        "promoted": False,
        "saved_app_data_changed": False,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
