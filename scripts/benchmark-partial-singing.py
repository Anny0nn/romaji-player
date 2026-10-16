"""Partial-source CTC on opened PJS development data, with exact word envelopes.

Reuse authenticated audio-only posteriors; close all observations before reading
human boundaries. Report placement separately from timing accuracy. No app writes,
inference, held-out labels, new model dependencies or commercial corpus sweeps.
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
from hubertfa_research import private_path
from partial_singing_ctc import align_partial
from singing_reference import SILENCE, htk_labels, verify_extracted, wilson

sys.path.insert(0, str(ROOT / "refinement"))
from singing_phonemes import token_phones


def main():
    import numpy as np

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--recognition", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--pjs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for key in vars(args):
        setattr(args, key, private_path(getattr(args, key)))
    recipe, recognition, _ = read_run(args.recognition, args.manifest)
    if recipe["engine"] != "romaji":
        raise ValueError("Expected the frozen independent singing CTC posteriors.")
    cases = json.loads(args.cases.read_text())["cases"]
    if any(c["recording"] not in recognition for c in cases):
        raise ValueError("Cases include recordings outside the opened development run.")
    policy = {
        "deletion_phone_cost": 1.0,
        "background_frame_cost": 0.7,
        "minimum_probability": 0.45,
        "minimum_deletion_margin_nats": 2.0,
        "minimum_duration_ms": 80,
        "adjacent_qualifying_word_required": True,
    }
    identity = {
        "manifest_sha256": digest(args.manifest),
        "cases_sha256": digest(args.cases),
        "recognition_complete_sha256": digest(args.recognition / "complete.json"),
        "code": {
            name: digest(ROOT / "scripts" / name)
            for name in ("benchmark-partial-singing.py", "partial_singing_ctc.py")
        },
        "policy": policy,
        "purpose": "development-only partial-path placement and timing; no lexical gold claim",
    }
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2))
    vocabulary = {
        label: token_phones(token)
        for token, label in recipe["model"]["heads"]["romaji"].items()
    }
    observations = {}
    started = time.monotonic()
    for case in cases:
        name = case["recording"]
        if name in observations:
            if observations[name]["words"] != case["words"]:
                raise ValueError("Frozen word groups changed within a recording.")
            continue
        path = args.recognition / recognition[name]["heads"]["romaji"]["posterior"]
        with np.load(path, allow_pickle=False) as cache:
            result = align_partial(
                cache["logp"],
                int(cache["blank"]),
                [source_word_phones(w) for w in case["words"]],
                vocabulary,
                margins=True,
            )
        eligible = {
            i
            for i, u in enumerate(result["units"])
            if u["placed"]
            and u["mean_probability"] >= policy["minimum_probability"]
            and u["deletion_margin_nats"] >= policy["minimum_deletion_margin_nats"]
            and u["end_ms"] - u["start_ms"] >= policy["minimum_duration_ms"]
        }
        for i, u in enumerate(result["units"]):
            u["qualifies"] = i in eligible and bool({i - 1, i + 1} & eligible)
        observations[name] = {"words": case["words"], **result}
        (args.output / (name + ".json")).write_text(json.dumps(observations[name]))
        print(json.dumps({"recordings_completed": len(observations)}), flush=True)
    inference_seconds = time.monotonic() - started
    # No reference clock was read before all candidate observations closed.
    (args.output / "observations.json").write_text(json.dumps(observations))
    references, totals, records = {}, Counter(), []
    for case in cases:
        name, word = case["recording"], case["word"]
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
        reference = references[name][first:last]
        if [r["phone"] for r in reference] != case["reference_phones"]:
            raise ValueError("Original human word envelope changed.")
        unit = observations[name]["units"][word]
        correct = (
            unit["placed"]
            and abs(unit["start_ms"] - reference[0]["start_ms"]) <= 150
            and abs(unit["end_ms"] - reference[-1]["end_ms"]) <= 200
        )
        totals.update(
            original_groups=1,
            placed=unit["placed"],
            placed_joint_correct=correct,
            qualifies=unit["qualifies"],
            qualifying_joint_correct=unit["qualifies"] and correct,
        )
        records.append({"id": case["id"], "prediction": unit, "reference": reference})
    summary = {
        "totals": totals,
        "qualifying_wilson_95_descriptive": wilson(
            totals["qualifying_joint_correct"], totals["qualifies"]
        ),
        "recordings": len(observations),
        "decode_seconds": inference_seconds,
        "identity_sha256": digest(args.output / "identity.json"),
        "observations_sha256": digest(args.output / "observations.json"),
        "labels_archive_sha256": digest(args.pjs / "labels.zip"),
        "promoted": False,
        "saved_app_data_changed": False,
    }
    (args.output / "private-reference-results.json").write_text(json.dumps(records))
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
