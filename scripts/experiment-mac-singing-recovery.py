"""Replay the bundled singing timing fallback on saved native song baselines."""

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
    from singing_recovery import recover
    from tifa_helper import Aligner, prepare_model

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--recognition", type=Path, required=True)
    parser.add_argument("--audio-manifest", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if ROOT in args.output.resolve().parents:
        parser.error("Private source and timings stay outside the checkout.")
    _, suite, hashes = load_suite(args.manifest)
    recipe, recognition, _ = read_run(args.recognition, args.audio_manifest)
    if recipe["engine"] != "romaji":
        raise ValueError("Expected the independently captured singing recognizer.")
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.umask(0o077)
    aligner = Aligner(prepare_model(args.archive))
    began, totals, records, cache = time.monotonic(), defaultdict(Counter), [], {}
    for number, row in enumerate(suite, 1):
        case, baseline = row["kim"], row["baseline"]
        counts = totals[case["track"]]
        counts["words"] += len(row["words"])
        counts["before"] += sum(u["start_ms"] >= 0 for u in baseline)
        targets = [
            {
                "raw_span": w["raw_span"],
                "text": "".join(c for c in w["hiragana"] if c.isalnum()),
                "romaji": w["romaji"],
            }
            for w in row["words"]
        ]
        repaired = baseline
        if any(u["start_ms"] < 0 for u in baseline):
            saved = recognition[row["id"]]
            if (
                saved["case"]["sha256"] != case["audio_sha256"]
                or saved["case"]["first_sample"] != case["start_ms"] * 16
                or saved["case"]["last_sample"] != case["end_ms"] * 16
            ):
                raise ValueError("Independent evidence uses another vocal window.")
            path = Path(case["pcm"])
            if path not in cache:
                if digest(path) != case["audio_sha256"]:
                    raise ValueError("Vocal audio changed.")
                cache = {path: np.memmap(path, dtype="<f4", mode="r")}
            samples = np.array(
                cache[path][case["start_ms"] * 16 : case["end_ms"] * 16], copy=True
            )
            with (
                np.load(
                    args.recognition / saved["heads"]["romaji"]["posterior"],
                    allow_pickle=False,
                ) as saved_posterior,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                repaired = recover(
                    samples,
                    [(case["occurrence"], 0, len(samples), targets)],
                    aligner,
                    [(saved_posterior["logp"], int(saved_posterior["blank"]))],
                    recipe["model"]["heads"]["romaji"],
                    [baseline],
                    {str(case["occurrence"]): len(row["words"])},
                    lambda _: None,
                )[0]
        for a, b in zip(baseline, repaired, strict=True):
            if a["start_ms"] >= 0 and a != b:
                raise ValueError("A retained baseline interval changed.")
            counts["after"] += b["start_ms"] >= 0
            counts["gains"] += a["start_ms"] < 0 <= b["start_ms"]
        records.append({"id": row["id"], "units": repaired})
        if number % 50 == 0:
            print(json.dumps({"processed": number, "total": len(suite)}), flush=True)
    result = {
        "input_hashes": hashes,
        "recognition_receipt_sha256": digest(args.recognition / "complete.json"),
        "archive_sha256": digest(args.archive),
        "implementation_sha256": {
            p: digest(ROOT / p)
            for p in (
                "refinement/singing_recovery.py",
                "refinement/singing_timing.py",
                "refinement/english_singing_phones.py",
                "tifa/tifa_helper.py",
            )
        },
        "per_track": dict(totals),
        "seconds": time.monotonic() - began,
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    (args.output / "records.json").write_text(json.dumps(records))
    (args.output / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"per_track": dict(totals), "seconds": result["seconds"]}))


if __name__ == "__main__":
    main()
