"""Paired written/spoken reading trials against frozen source groups and singing audio."""

import argparse
import contextlib
import io
import json
import os
import resource
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from audio_first_evaluation import read_run
from audio_first_models import ROOT, digest
from mac_completeness_inputs import load_suite

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]


def main():
    import numpy as np
    from singing_timing import recover_singing_gaps, word_alignment
    from tifa_helper import Aligner, prepare_model

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--conversions", type=Path, required=True)
    parser.add_argument("--recognition", type=Path, required=True)
    parser.add_argument("--audio-manifest", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--policy", choices=("written", "spoken"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if ROOT == args.output.resolve() or ROOT in args.output.resolve().parents:
        parser.error("Keep lyric-bearing observations outside the checkout.")
    _, suite, hashes = load_suite(args.manifest)
    recipe, recognition, _ = read_run(args.recognition, args.audio_manifest)
    if recipe["engine"] != "romaji":
        raise ValueError("Expected independent audio-only singing posteriors.")
    conversions = {
        r["id"]: r for r in json.loads(args.conversions.read_text())["records"]
    }
    if set(conversions) != {row["id"] for row in suite} or not all(
        row["id"] in recognition for row in suite
    ):
        raise ValueError(
            "Conversion or acoustic evidence is missing suite occurrences."
        )
    args.output.mkdir(mode=0o700, exist_ok=False)
    os.umask(0o077)
    aligner = Aligner(prepare_model(args.archive))
    totals, records, cache = defaultdict(Counter), [], {}
    began = time.monotonic()
    for row in suite:
        case, words, baseline = row["kim"], row["words"], row["baseline"]
        conversion = conversions[row["id"]]
        if conversion["request"]["raw_line"] != case["raw_line"]:
            raise ValueError("Changed source line.")
        selected = {
            tuple(w["raw_span"]): w
            for w in conversion["response"]["words"]
            if w["raw_span"]
        }
        targets, changed = [], []
        for word in words:
            mapped = selected[tuple(word["raw_span"])]
            reading = mapped["reading"]
            if (
                reading["written"] != word["hiragana"]
                or reading["romaji"] != word["romaji"]
            ):
                raise ValueError("Selected reading differs from the frozen baseline.")
            spoken = (
                reading["pronunciation"]
                if args.policy == "spoken" and not word["protected_reading"]
                else None
            )
            targets.append(
                {
                    "raw_span": word["raw_span"],
                    "text": spoken or reading["alignment_text"],
                    "romaji": reading["romaji"],
                }
            )
            changed.append(bool(spoken and spoken != reading["written"]))
        counts = totals[case["track"]]
        counts["words"] += len(words)
        counts["before"] += sum(u["start_ms"] >= 0 for u in baseline)
        counts["changed_missing_targets"] += sum(
            changed[i] and u["start_ms"] < 0 for i, u in enumerate(baseline)
        )
        repaired = baseline
        if any(
            u["start_ms"] < 0
            and all("ぁ" <= c <= "ゖ" or c in "ー " for c in words[i]["hiragana"])
            for i, u in enumerate(baseline)
        ):
            saved = recognition[row["id"]]
            if (
                saved["case"]["sha256"] != case["audio_sha256"]
                or saved["case"]["first_sample"] != case["start_ms"] * 16
                or saved["case"]["last_sample"] != case["end_ms"] * 16
            ):
                raise ValueError("Singing evidence uses another crop.")
            path = Path(case["pcm"])
            if path not in cache:
                if digest(path) != case["audio_sha256"]:
                    raise ValueError("Vocal audio changed.")
                cache = {path: np.memmap(path, dtype="<f4", mode="r")}
            samples = np.array(
                cache[path][case["start_ms"] * 16 : case["end_ms"] * 16], copy=True
            )
            raw = []
            with contextlib.redirect_stdout(io.StringIO()):
                trial = aligner.align(samples, targets, diagnostics=raw)
            with np.load(
                args.recognition / saved["heads"]["romaji"]["posterior"],
                allow_pickle=False,
            ) as archive:
                evidence = word_alignment(
                    archive["logp"],
                    int(archive["blank"]),
                    targets,
                    recipe["model"]["heads"]["romaji"],
                )
            repaired = recover_singing_gaps(
                baseline,
                {"units": trial, "raw_units": raw},
                evidence,
                len(samples) // 16,
                len(words),
            )
        for previous, current in zip(baseline, repaired, strict=True):
            if previous["start_ms"] >= 0 and previous != current:
                raise ValueError("A retained timing changed.")
            counts["gains"] += previous["start_ms"] < 0 <= current["start_ms"]
            counts["after"] += current["start_ms"] >= 0
        records.append({"id": row["id"], "units": repaired})
    summary = {
        "policy": args.policy,
        "input_hashes": hashes,
        "conversion_sha256": digest(args.conversions),
        "recognition_receipt_sha256": digest(args.recognition / "complete.json"),
        "archive_sha256": digest(args.archive),
        "implementation_sha256": digest(Path(__file__)),
        "per_track": dict(totals),
        "seconds": time.monotonic() - began,
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    (args.output / "records.json").write_text(json.dumps(records))
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(
        json.dumps(
            {
                "policy": args.policy,
                "per_track": dict(totals),
                "seconds": summary["seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
