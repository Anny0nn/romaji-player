"""Check interval-conditioned phone evidence on opened PJS development audio.

Close scores and observed frame clocks before reading human timing. Candidate
windows use only original TIFA observations, never reference labels. No model
inference, commercial coverage claim, app writes or new holdout claim.
"""

import argparse
import json
import math
import os
import time
from collections import Counter
from pathlib import Path

from audio_first_evaluation import read_run
from audio_first_models import ROOT, digest, kana_sequence_phones, source_word_phones
from contrastive_phones import contrastive_score
from hubertfa_research import private_path
from singing_reference import SILENCE, htk_labels, verify_extracted, wilson


def local_observation(logp, blank, phones, vocabulary, clock):
    """Fixed 120 ms padding; retain observed frames without clipping boundaries."""
    if (
        any(p.startswith("unsupported:") for p in phones)
        or not 0 <= clock["start_ms"] < clock["end_ms"]
        or clock["end_ms"] - clock["start_ms"] < 80
        or clock["end_ms"] > (len(logp) - 1) * 20 + 25
    ):
        return {"eligible": False}
    first = max(0, math.floor((clock["start_ms"] - 120) / 20))
    last = min(len(logp), math.ceil((clock["end_ms"] + 120) / 20))
    score = contrastive_score(logp[first:last], blank, phones, vocabulary, observe=True)
    path = score["path"]
    result = {"eligible": True, "window_frames": [first, last], "score": score}
    if path is None:
        result.update(lexical_pass=False, paired=False)
        return result
    start = (first + path["first_frame"]) * 20
    end = (first + path["last_frame"]) * 20 + 25
    lexical = (
        score["union_margin"] is not None
        and score["union_margin"] > 0
        and score["blank_margin"] is not None
        and score["blank_margin"] > 0
        and path["mean_frame_probability"] >= 0.45
    )
    paired = (
        lexical
        and path["first_frame"] > 0
        and path["last_frame"] < last - first - 1
        and end - start >= 80
        and abs(start - clock["start_ms"]) <= 150
        and abs(end - clock["end_ms"]) <= 150
    )
    return {
        **result,
        "start_ms": start,
        "end_ms": end,
        "lexical_pass": lexical,
        "paired": paired,
    }


def main():
    import numpy as np

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--recognition", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--pjs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for key, value in vars(args).items():
        setattr(args, key, private_path(value))
    recipe, recognition, _ = read_run(args.recognition, args.manifest)
    if (
        recipe["engine"] != "romaji"
        or recipe["model"]["stride_samples"] != 320
        or recipe["model"]["receptive_field_samples"] != 400
    ):
        raise ValueError("Expected closed independent RomajiASR posteriors.")
    cases = json.loads(args.cases.read_text())["cases"]
    baseline = json.loads(args.baseline.read_text())
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    identity = {
        "manifest_sha256": digest(args.manifest),
        "cases_sha256": digest(args.cases),
        "baseline_sha256": digest(args.baseline),
        "recognition_complete_sha256": digest(args.recognition / "complete.json"),
        "code": {
            name: digest(ROOT / name)
            for name in (
                "scripts/benchmark-contrastive-phones.py",
                "scripts/contrastive_phones.py",
                "scripts/audio_first_models.py",
                "scripts/audio_first_evaluation.py",
                "scripts/singing_reference.py",
                "refinement/singing_phonemes.py",
            )
        },
        "policy": {
            "padding_ms": 120,
            "minimum_union_margin_nats": 0,
            "minimum_blank_margin_nats": 0,
            "minimum_mean_emission_frame_probability": 0.45,
            "minimum_duration_ms": 80,
            "maximum_endpoint_disagreement_ms": 150,
            "cut_edge": "withheld",
            "frame_ms": 20,
            "receptive_ms": 25,
        },
        "purpose": "opened development; source-conditioned likelihood ratios are not probabilities",
    }
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2))
    vocabulary = recipe["model"]["heads"]["romaji"]
    cache, observations = {}, []
    began = time.monotonic()
    for case in cases:
        name, index = case["recording"], case["word"]
        if baseline[name]["words"] != case["words"]:
            raise ValueError("TIFA baseline changed original group ownership.")
        clock = baseline[name]["before"][index]
        word = case["words"][index]
        if clock["raw_span"] != word["raw_span"]:
            raise ValueError("TIFA word belongs to a different source span.")
        if name not in cache:
            path = args.recognition / recognition[name]["heads"]["romaji"]["posterior"]
            with np.load(path, allow_pickle=False) as data:
                cache[name] = (data["logp"], int(data["blank"]))
        logp, blank = cache[name]
        if blank != recipe["model"]["blank"]:
            raise ValueError("Changed CTC blank identity.")
        original = source_word_phones(word)
        fault = kana_sequence_phones(case["fault_kana"])
        observations.append(
            {
                "id": case["id"],
                "original": local_observation(logp, blank, original, vocabulary, clock),
                "wrong_reading": (
                    local_observation(logp, blank, fault, vocabulary, clock)
                    if fault != original
                    else None
                ),
                "tifa": clock,
            }
        )
    observation_path = args.output / "observations.json"
    observation_path.write_text(json.dumps(observations, allow_nan=False))
    seconds = time.monotonic() - began
    # This is opened development, but no human clock chooses the window or score.
    references, totals = {}, Counter()
    for case, observation in zip(cases, observations, strict=True):
        name = case["recording"]
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
            raise ValueError("Changed human phone ownership.")
        original, fault = observation["original"], observation["wrong_reading"]
        paired = original.get("paired", False)

        def correct(clock, reference=reference):
            return (
                abs(clock["start_ms"] - reference[0]["start_ms"]) <= 150
                and abs(clock["end_ms"] - reference[-1]["end_ms"]) <= 200
            )

        totals.update(
            original_groups=1,
            eligible=original["eligible"],
            lexical_pass=original.get("lexical_pass", False),
            paired=paired,
            tifa_correct=paired and correct(observation["tifa"]),
            ctc_correct=paired and correct(original),
            wrong_readings=fault is not None,
            wrong_reading_lexical_pass=bool(fault and fault.get("lexical_pass")),
            wrong_reading_paired=bool(fault and fault.get("paired")),
        )
    summary = {
        "totals": totals,
        "tifa_wilson_95_descriptive": wilson(totals["tifa_correct"], totals["paired"]),
        "cached_seconds": seconds,
        "recordings": len(cache),
        "identity_sha256": digest(args.output / "identity.json"),
        "observations_sha256": digest(observation_path),
        "labels_archive_sha256": digest(args.pjs / "labels.zip"),
        "promoted": False,
        "saved_app_data_changed": False,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
