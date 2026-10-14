"""Score timing-only recovery against frozen human PJS word envelopes."""

import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys
from collections import Counter
from pathlib import Path

from audio_first_evaluation import read_run
from audio_first_models import ROOT, digest
from singing_reference import SILENCE, htk_labels, verify_extracted, wilson

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
spec = importlib.util.spec_from_file_location(
    "blind_runner", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)


def main():
    import numpy as np
    from singing_recovery import recover
    from tifa_helper import Aligner, prepare_model

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--recognition", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--pjs", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pronunciations", type=Path)
    parser.add_argument(
        "--mask-frozen",
        action="store_true",
        help="Hide the frozen eligible timings before recovery; do not alter audio/targets.",
    )
    args = parser.parse_args()
    if ROOT in args.output.resolve().parents:
        parser.error("Private lyric and reference results stay outside the checkout.")
    recipe, recognition, _ = read_run(args.recognition, args.manifest)
    cases = json.loads(args.cases.read_text())["cases"]
    pronunciations = (
        json.loads(args.pronunciations.read_text()) if args.pronunciations else {}
    )
    selected = [c for c in cases if c["recording"] in recognition]
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.umask(0o077)
    aligner = Aligner(prepare_model(args.archive))
    cache, observations = {}, {}
    for case in selected:
        name = case["recording"]
        if name in observations:
            if observations[name]["words"] != case["words"]:
                raise ValueError("Frozen source words differ within a recording.")
            continue
        audio = recognition[name]["case"]
        samples = blind.load_samples(audio, args.manifest.parent, cache)
        targets = [
            {
                "raw_span": w["raw_span"],
                "text": w["hiragana"],
                "romaji": w["romaji"],
                "pronunciation": pronunciations.get(name, {}).get(str(w["raw_span"])),
            }
            for w in case["words"]
        ]
        path = args.recognition / recognition[name]["heads"]["romaji"]["posterior"]
        with (
            np.load(path, allow_pickle=False) as posterior,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            baseline = aligner.align(samples, targets)
            if args.mask_frozen:
                hidden = {c["word"] for c in selected if c["recording"] == name}
                baseline = [
                    {**u, "start_ms": -1, "end_ms": -1} if i in hidden else u
                    for i, u in enumerate(baseline)
                ]
            after = recover(
                samples,
                [(0, 0, len(samples), targets)],
                aligner,
                [(posterior["logp"], int(posterior["blank"]))],
                recipe["model"]["heads"]["romaji"],
                [baseline],
                {"0": len(targets)},
                lambda _: None,
            )[0]
        observations[name] = {
            "words": case["words"],
            "before": baseline,
            "after": after,
        }
    # Close observations before opening the human timing labels.
    (args.output / "observations.json").write_text(json.dumps(observations))
    references, rows, totals = {}, [], Counter()
    for case in selected:
        name, index = case["recording"], case["word"]
        if name not in references:
            label = args.pjs / "labels" / f"{name}.lab"
            verify_extracted(args.pjs / "labels.zip", label)
            references[name] = [
                r
                for r in htk_labels(
                    label.read_text(), recognition[name]["case"]["last_sample"] / 16
                )
                if r["phone"] not in SILENCE
            ]
        first, last = case["reference_phone_span"]
        ref = references[name][first:last]
        if [r["phone"] for r in ref] != case["reference_phones"]:
            raise ValueError("Human reference envelope changed.")
        before, after = [
            observations[name][stage][index] for stage in ("before", "after")
        ]
        if before["start_ms"] >= 0 and before != after:
            raise ValueError("A retained timing changed.")
        values = {}
        for stage, observed in (("before", before), ("after", after)):
            retained = observed["start_ms"] >= 0
            onset = abs(observed["start_ms"] - ref[0]["start_ms"]) if retained else None
            offset = abs(observed["end_ms"] - ref[-1]["end_ms"]) if retained else None
            correct = retained and onset <= 150 and offset <= 200
            totals[f"{stage}_retained"] += retained
            totals[f"{stage}_joint_correct"] += correct
            values[stage] = {
                "retained": retained,
                "correct": correct,
                "onset_error_ms": onset,
                "offset_error_ms": offset,
            }
        gained = not values["before"]["retained"] and values["after"]["retained"]
        totals["gains"] += gained
        totals["correct_gains"] += gained and values["after"]["correct"]
        rows.append({"id": case["id"], **values})
    result = {
        "cases": len(selected),
        "masked_frozen_timings": args.mask_frozen,
        "omitted_other_partition": len(cases) - len(selected),
        "recordings": len(observations),
        "totals": dict(totals),
        "new_word_correctness_wilson_95": wilson(
            totals["correct_gains"], totals["gains"]
        ),
        "inputs": {
            "manifest": digest(args.manifest),
            "cases": digest(args.cases),
            "recognition_receipt": digest(args.recognition / "complete.json"),
            "labels_archive": digest(args.pjs / "labels.zip"),
            "tifa_archive": digest(args.archive),
            "pronunciations": digest(args.pronunciations)
            if args.pronunciations
            else None,
        },
    }
    (args.output / "references.json").write_text(json.dumps(rows))
    (args.output / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
