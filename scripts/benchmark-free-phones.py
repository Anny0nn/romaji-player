"""Evaluate complete words matched after source-blind phone recognition.

Cache observations before opening the already used PJS development clocks. Report
free-decoder envelopes and TIFA-paired clocks separately. No inference or app writes.
The source is used for correspondence only, never for decoding phone probabilities.
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

from audio_first_evaluation import read_run
from audio_first_models import ROOT, digest, source_word_phones
from free_phone_words import observe_words
from hubertfa_research import private_path
from singing_reference import SILENCE, htk_labels, verify_extracted, wilson

sys.path.insert(0, str(ROOT / "refinement"))
from singing_phonemes import token_phones


def main():
    import numpy as np

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--recognition", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--pjs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context-phones", type=int, default=2)
    parser.add_argument("--minimum-word-phones", type=int, default=1)
    args = parser.parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, private_path(value))
    if args.context_phones < 0 or args.minimum_word_phones < 1:
        parser.error("Context is nonnegative and word length is positive.")
    recipe, recognition, _ = read_run(args.recognition, args.manifest)
    if recipe["engine"] != "romaji":
        raise ValueError("Expected closed independent RomajiASR posteriors.")
    cases = json.loads(args.cases.read_text())["cases"]
    baseline = json.loads(args.baseline.read_text())
    if any(c["recording"] not in recognition for c in cases):
        raise ValueError("Cases are outside the closed recognition run.")
    identity = {
        "manifest_sha256": digest(args.manifest),
        "cases_sha256": digest(args.cases),
        "baseline_sha256": digest(args.baseline),
        "recognition_complete_sha256": digest(args.recognition / "complete.json"),
        "code": {
            name: digest(ROOT / "scripts" / name)
            for name in ("benchmark-free-phones.py", "free_phone_words.py")
        },
        "policy": {
            "context_phones": args.context_phones,
            "minimum_word_phones": args.minimum_word_phones,
            "minimum_probability": 0.45,
            "minimum_duration_ms": 80,
            "maximum_paired_endpoint_difference_ms": 150,
            "frame_ms": 20,
            "receptive_ms": 25,
        },
        "purpose": "opened development; phonetic presence cannot establish kanji spelling",
    }
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2))
    vocab = {
        label: token_phones(token)
        for token, label in recipe["model"]["heads"]["romaji"].items()
    }
    observations = {}
    began = time.monotonic()
    for case in cases:
        name = case["recording"]
        if name in observations:
            if observations[name]["words"] != case["words"]:
                raise ValueError("Changed original word ownership within a recording.")
            continue
        if baseline[name]["words"] != case["words"]:
            raise ValueError("Baseline belongs to different original word groups.")
        path = args.recognition / recognition[name]["heads"]["romaji"]["posterior"]
        with np.load(path, allow_pickle=False) as cache:
            units = observe_words(
                cache["logp"],
                int(cache["blank"]),
                [
                    {"raw_span": w["raw_span"], "phones": source_word_phones(w)}
                    for w in case["words"]
                ],
                vocab,
                frame_ms=20,
                receptive_ms=25,
                context_phones=args.context_phones,
                minimum_word_phones=args.minimum_word_phones,
            )
        if [u["raw_span"] for u in units] != [
            u["raw_span"] for u in baseline[name]["before"]
        ]:
            raise ValueError("TIFA baseline changed source span identity.")
        observations[name] = {"words": case["words"], "units": units}
    observation_path = args.output / "observations.json"
    observation_path.write_text(json.dumps(observations, allow_nan=False))
    seconds = time.monotonic() - began
    # Candidate correspondence and clocks close before any human timing is read.
    references, totals, records = {}, Counter(), []
    for case in cases:
        name, index = case["recording"], case["word"]
        if name not in references:
            label = args.pjs / "labels" / (name + ".lab")
            verify_extracted(args.pjs / "labels.zip", label)
            references[name] = [
                r
                for r in htk_labels(
                    label.read_text(), recognition[name]["case"]["last_sample"] / 16
                )
                if r["phone"] not in SILENCE
            ]
        first, last = case["reference_phone_span"]
        reference = references[name][first:last]
        if [r["phone"] for r in reference] != case["reference_phones"]:
            raise ValueError("Human reference phone ownership changed.")
        unit = observations[name]["units"][index]
        old = baseline[name]["before"][index]
        match = (
            unit["source_match"]
            and unit["probability"] >= 0.45
            and unit["end_ms"] - unit["start_ms"] >= 80
        )
        paired = (
            match
            and 0 <= old["start_ms"] < old["end_ms"]
            and abs(unit["start_ms"] - old["start_ms"]) <= 150
            and abs(unit["end_ms"] - old["end_ms"]) <= 150
        )

        def correct(clock, reference=reference):
            return (
                abs(clock["start_ms"] - reference[0]["start_ms"]) <= 150
                and abs(clock["end_ms"] - reference[-1]["end_ms"]) <= 200
            )

        totals.update(
            original_groups=1,
            phonetic_matches=match,
            free_clock_correct=match and correct(unit),
            tifa_paired=paired,
            tifa_clock_correct=paired and correct(old),
        )
        records.append(
            {"id": case["id"], "free": unit, "tifa": old, "reference": reference}
        )
    summary = {
        "totals": totals,
        "paired_wilson_95_descriptive": wilson(
            totals["tifa_clock_correct"], totals["tifa_paired"]
        ),
        "recordings": len(observations),
        "cached_seconds": seconds,
        "identity_sha256": digest(args.output / "identity.json"),
        "observations_sha256": digest(observation_path),
        "labels_archive_sha256": digest(args.pjs / "labels.zip"),
        "promoted": False,
        "saved_app_data_changed": False,
    }
    (args.output / "private-reference-results.json").write_text(json.dumps(records))
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
