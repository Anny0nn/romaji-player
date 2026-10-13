"""Fresh TIFA timings for admitted controlled reading repairs; no app writes."""

import argparse
import contextlib
import importlib.util
import io
import json
import os
import random
import resource
import sys
import time
from collections import defaultdict
from pathlib import Path

from audio_first_models import ROOT, digest
from singing_reference import SILENCE, htk_labels, quantile, verify_extracted

sys.path.insert(0, str(ROOT / "tifa"))
spec = importlib.util.spec_from_file_location(
    "blind_runner", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)


def summarize(rows):
    retained = [r for r in rows if r["interval"]["start_ms"] >= 0]
    readable = [r for r in retained if r["correct_reading"]]
    groups = defaultdict(list)
    for row in rows:
        groups[row["recording"]].append(row)
    ids, samples, rng = sorted(groups), [], random.Random(0)
    for _ in range(2000 if groups else 0):
        sample = [r for key in rng.choices(ids, k=len(ids)) for r in groups[key]]
        samples.append(sum(r["joint_correct"] for r in sample) / len(sample))
    return {
        "admitted": len(rows),
        "retained_timings": len(retained),
        "correct_readings_with_timing": len(readable),
        "joint_correct": sum(r["joint_correct"] for r in rows),
        "joint_fraction_of_admissions": sum(r["joint_correct"] for r in rows)
        / len(rows)
        if rows
        else None,
        "phrase_bootstrap_95": [quantile(samples, 0.025), quantile(samples, 0.975)],
        "onset_error_ms_median": quantile([r["onset_error_ms"] for r in readable], 0.5),
        "offset_error_ms_median": quantile(
            [r["offset_error_ms"] for r in readable], 0.5
        ),
    }


def main():
    from tifa_helper import Aligner, prepare_model

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--admissions", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--pjs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if ROOT in args.output.resolve().parents:
        parser.error("Private results must remain outside the checkout.")
    manifest = {
        c["id"]: c for c in blind.manifest_cases(json.loads(args.manifest.read_text()))
    }
    frozen = json.loads(args.cases.read_text())
    cases = {c["id"]: c for c in frozen["cases"]}
    admissions = [
        r
        for r in json.loads(args.admissions.read_text())
        if r["condition"] == "injected"
        and r["method"] in ("current-core", "core-then-blind")
    ]
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    began = time.monotonic()
    aligner = Aligner(prepare_model(args.archive))
    cache, timings, captured = {}, {}, []
    for number, row in enumerate(admissions, 1):
        case = cases[row["case"]]
        audio_case = manifest[case["recording"]]
        words = [
            {"raw_span": w["raw_span"], "text": w["hiragana"], "romaji": w["romaji"]}
            for w in case["words"]
        ]
        # Only this source word is faulty, and this row's admitted reading replaces it.
        # Correctness labels are never used to select targets or skip an inference.
        index = case["word"]
        words[index].update(
            text=row["selected"]["hiragana"], romaji=row["selected"]["romaji"]
        )
        key = (case["recording"], tuple((w["text"], w["romaji"]) for w in words))
        if key not in timings:
            samples = blind.load_samples(audio_case, args.manifest.parent, cache)
            with contextlib.redirect_stdout(io.StringIO()):
                timings[key] = aligner.align(samples, words)
        captured.append(
            {
                "case": row["case"],
                "method": row["method"],
                "interval": timings[key][index],
            }
        )
        if number % 50 == 0:
            print(json.dumps({"timed": number, "total": len(admissions)}), flush=True)
    blind.write(output / "timings.json", captured)
    # Raw inference closes before reading the manual phone labels.
    labels, evaluated = {}, []
    for row, captured_row in zip(admissions, captured, strict=True):
        case = cases[row["case"]]
        name = case["recording"]
        if name not in labels:
            path = args.pjs / "labels" / f"{name}.lab"
            verify_extracted(args.pjs / "labels.zip", path)
            labels[name] = [
                r
                for r in htk_labels(
                    path.read_text(), manifest[name]["last_sample"] / 16
                )
                if r["phone"] not in SILENCE
            ]
        first, last = case["reference_phone_span"]
        reference = labels[name][first:last]
        if [r["phone"] for r in reference] != case["reference_phones"]:
            raise ValueError("Frozen word's human reference envelope changed.")
        interval = captured_row["interval"]
        retained = interval["start_ms"] >= 0
        onset = (
            abs(interval["start_ms"] - reference[0]["start_ms"]) if retained else None
        )
        offset = abs(interval["end_ms"] - reference[-1]["end_ms"]) if retained else None
        evaluated.append(
            {
                **captured_row,
                "recording": name,
                "correct_reading": row["correct"],
                "onset_error_ms": onset,
                "offset_error_ms": offset,
                "joint_correct": bool(
                    retained and row["correct"] and onset <= 150 and offset <= 200
                ),
            }
        )
    baseline = {r["case"]: r for r in evaluated if r["method"] == "current-core"}
    fallback = {r["case"]: r for r in evaluated if r["method"] == "core-then-blind"}
    result = {
        "manifest_sha256": digest(args.manifest),
        "cases_sha256": digest(args.cases),
        "admissions_sha256": digest(args.admissions),
        "archive_sha256": digest(args.archive),
        "timings_sha256": digest(output / "timings.json"),
        "labels_archive_sha256": digest(args.pjs / "labels.zip"),
        "implementation_sha256": digest(Path(__file__)),
        "aligner_sha256": digest(ROOT / "tifa/tifa_helper.py"),
        "total_seconds": time.monotonic() - began,
        "process_lifetime_peak_rss_bytes": resource.getrusage(
            resource.RUSAGE_SELF
        ).ru_maxrss,
        "unique_full_line_alignments": len(timings),
        "metrics": {
            method: summarize([r for r in evaluated if r["method"] == method])
            for method in ("current-core", "core-then-blind")
        },
        "common_admissions": len(baseline.keys() & fallback.keys()),
        "common_identical_intervals": sum(
            baseline[k]["interval"] == fallback[k]["interval"]
            for k in baseline.keys() & fallback.keys()
        ),
        "additional_joint_correct": sum(
            r["joint_correct"] for k, r in fallback.items() if k not in baseline
        ),
    }
    blind.write(output / "evaluated.json", evaluated)
    blind.write(output / "summary.json", result)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "metrics",
                    "common_admissions",
                    "common_identical_intervals",
                    "additional_joint_correct",
                    "total_seconds",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
