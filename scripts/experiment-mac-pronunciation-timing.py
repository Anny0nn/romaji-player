"""Real-song missing-word replay of dictionary pronunciation with TIFA + singing CTC."""

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
from singing_word_alignment import word_alignment

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]


def main():
    import numpy as np
    from refinement_policy import agree, coherent_line, recover_gaps, supported_raw
    from tifa_helper import Aligner, prepare_model

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--recognition", type=Path, required=True)
    parser.add_argument("--audio-manifest", type=Path, required=True)
    parser.add_argument("--shadow", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--nomination", choices=("changed", "missing-ja"), default="changed"
    )
    parser.add_argument("--written", action="store_true")
    args = parser.parse_args()
    if ROOT in args.output.resolve().parents:
        parser.error("Lyrics and timings stay outside the checkout.")
    _, suite, hashes = load_suite(args.manifest)
    recipe, recognition, _ = read_run(args.recognition, args.audio_manifest)
    shadows = json.loads(args.shadow.read_text())["records"]
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.umask(0o077)
    aligner = Aligner(prepare_model(args.archive))
    began, cache, records, totals = time.monotonic(), {}, [], defaultdict(Counter)
    for number, row in enumerate(suite, 1):
        case, words, baseline = row["kim"], row["words"], row["baseline"]
        counts = totals[case["track"]]
        counts["words"] += len(words)
        counts["baseline"] += sum(u["start_ms"] >= 0 for u in baseline)
        shadow = shadows[row["id"]]
        by_span = {tuple(w["raw_span"]): w for w in shadow["words"]}
        targets, nominated = [], []
        for index, word in enumerate(words):
            candidate = by_span.get(tuple(word["raw_span"]))
            spoken = (
                candidate["pronunciation_kana"]
                if candidate
                and candidate["hiragana"] == word["hiragana"]
                and not word["protected_reading"]
                else None
            )
            if args.written:
                spoken = None
            targets.append(
                {
                    "raw_span": word["raw_span"],
                    "text": spoken or word["hiragana"],
                    "romaji": word["romaji"],
                }
            )
            japanese = bool(word["hiragana"]) and all(
                "ぁ" <= c <= "ゖ" or c in "ー " for c in word["hiragana"]
            )
            eligible = (
                spoken and spoken != word["hiragana"]
                if args.nomination == "changed"
                else japanese
            )
            if eligible and baseline[index]["start_ms"] < 0:
                nominated.append(index)
        counts["nominated"] += len(nominated)
        if not nominated:
            continue
        raw_row = recognition[row["id"]]
        if (
            raw_row["case"]["sha256"] != case["audio_sha256"]
            or raw_row["case"]["first_sample"] != case["start_ms"] * 16
            or raw_row["case"]["last_sample"] != case["end_ms"] * 16
        ):
            raise ValueError("Singing evidence uses another vocal window.")
        path = Path(case["pcm"])
        if path not in cache:
            if digest(path) != case["audio_sha256"]:
                raise ValueError("Vocal recording changed.")
            cache = {path: np.memmap(path, dtype="<f4", mode="r")}
        samples = np.array(
            cache[path][case["start_ms"] * 16 : case["end_ms"] * 16], copy=True
        )
        diagnostics = []
        with contextlib.redirect_stdout(io.StringIO()):
            trial = aligner.align(samples, targets, diagnostics=diagnostics)
        posterior = raw_row["heads"]["romaji"]["posterior"]
        with np.load(args.recognition / posterior, allow_pickle=False) as archive:
            evidence = word_alignment(
                archive["logp"],
                int(archive["blank"]),
                targets,
                recipe["model"]["heads"]["romaji"],
            )
        candidate = supported_raw(
            {"units": trial, "raw_units": diagnostics}, evidence, len(samples) // 16
        )
        for index in range(len(candidate)):
            if (
                index not in nominated
                or evidence[index]["mean_probability"] < 0.45
                or not agree(candidate[index], evidence[index], 150)
            ):
                candidate[index] = {**candidate[index], "start_ms": -1, "end_ms": -1}
        # Existing intervals stay byte-for-byte unchanged. Add only noncolliding gaps.
        combined = [
            trial[i] if baseline[i]["start_ms"] >= 0 else candidate[i]
            for i in range(len(words))
        ]
        coherent = coherent_line(combined, evidence, len(words))
        repaired = recover_gaps(baseline, candidate, evidence) if coherent else baseline
        for index in nominated:
            counts["tifa_supported"] += candidate[index]["start_ms"] >= 0
            gained = baseline[index]["start_ms"] < 0 <= repaired[index]["start_ms"]
            counts["gains"] += gained
            records.append(
                {
                    "id": row["id"],
                    "track": case["track"],
                    "raw_span": words[index]["raw_span"],
                    "before": baseline[index],
                    "after": repaired[index],
                    "tifa": trial[index],
                    "diagnostic": diagnostics[index],
                    "singing": evidence[index],
                    "coherent": coherent,
                    "gained": gained,
                }
            )
        if number % 50 == 0:
            print(json.dumps({"processed": number, "total": len(suite)}), flush=True)
    summary = {
        "nomination": args.nomination,
        "pronunciation": "written" if args.written else "dictionary-shadow",
        "inputs_sha256": hashes,
        "recognition_receipt_sha256": digest(args.recognition / "complete.json"),
        "shadow_sha256": digest(args.shadow),
        "archive_sha256": digest(args.archive),
        "implementation_sha256": digest(Path(__file__)),
        "per_track": dict(totals),
        "total_seconds": time.monotonic() - began,
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    (args.output / "records.json").write_text(json.dumps(records, ensure_ascii=False))
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(
        json.dumps(
            {"per_track": dict(totals), "total_seconds": summary["total_seconds"]}
        )
    )


if __name__ == "__main__":
    main()
