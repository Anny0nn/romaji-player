"""Bounded Japanese source-gap replay using closed, source-blind posteriors.

Compare forced and deletion-aware CTC as verifiers of fresh TIFA boundaries on
the same samples. Existing source groups/intervals are immutable. This is research,
not a promoted model, source reading change or app write.
"""

import argparse
import contextlib
import io
import json
import os
import sys
from collections import Counter
from pathlib import Path

from audio_first_evaluation import read_run
from hubertfa_research import ROOT, digest, private_path
from partial_singing_ctc import align_partial
from source_contrast_policy import overlay_original_groups

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
from refinement_policy import supported_raw
from singing_phonemes import kana_phones, token_phones
from singing_timing import word_alignment


def main():
    import numpy as np
    from tifa_helper import Aligner, prepare_model

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--audio-manifest", type=Path, required=True)
    parser.add_argument("--recognition", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for name in vars(args):
        setattr(args, name, private_path(getattr(args, name)))
    manifest = json.loads(args.manifest.read_text())
    recipe, recognition, _ = read_run(args.recognition, args.audio_manifest)
    if recipe["engine"] != "romaji":
        raise ValueError("Expected independent source-blind singing CTC.")
    identity = {
        "manifest_sha256": digest(args.manifest),
        "recognition_receipt_sha256": digest(args.recognition / "complete.json"),
        "archive_sha256": digest(args.archive),
        "code": {
            name: digest(ROOT / name)
            for name in (
                "scripts/probe-partial-source.py",
                "scripts/partial_singing_ctc.py",
                "scripts/source_contrast_policy.py",
                "refinement/singing_timing.py",
                "refinement/refinement_policy.py",
                "tifa/tifa_helper.py",
            )
        },
        "minimum_deletion_margin_nats": 2.0,
        "maximum_endpoint_disagreement_ms": 150,
        "minimum_singing_probability": 0.45,
        "minimum_duration_ms": 80,
        "promoted": False,
    }
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2))
    tifa = Aligner(prepare_model(args.archive))
    vocab = recipe["model"]["heads"]["romaji"]
    vocabulary_phones = {label: token_phones(token) for token, label in vocab.items()}
    cases = {c["id"]: c for c in manifest["cases"]}
    totals, records, audio_cache = {}, [], {}
    for group in manifest["groups"]:
        observed_id = next(i for i in group["ids"] if i.endswith(":source:kim"))
        target_id = next(i for i in group["ids"] if i.endswith(":selected-reading:kim"))
        observed, case = recognition[observed_id], cases[target_id]
        if observed["case"] != {"id": observed_id, **case["audio"]}:
            raise ValueError("Source/recognition samples changed.")
        targets = case["targets"]
        source_phones = [
            kana_phones(t["text"], t["romaji"]) or ["unsupported-source-word"]
            for t in targets
        ]
        with np.load(
            args.recognition / observed["heads"]["romaji"]["posterior"],
            allow_pickle=False,
        ) as value:
            forced = word_alignment(value["logp"], int(value["blank"]), targets, vocab)
            partial = align_partial(
                value["logp"],
                int(value["blank"]),
                source_phones,
                vocabulary_phones,
                margins=True,
            )["units"]
        partial = [
            {**u, "raw_span": t["raw_span"]}
            for u, t in zip(partial, targets, strict=True)
        ]
        audio = case["audio"]
        if audio["path"] not in audio_cache:
            path = Path(audio["path"])
            if digest(path) != audio["sha256"]:
                raise ValueError("Changed original vocal recording.")
            audio_cache[audio["path"]] = np.memmap(path, dtype="<f4", mode="r")
        samples = audio_cache[audio["path"]][
            audio["first_sample"] : audio["last_sample"]
        ]
        raw = []
        with contextlib.redirect_stdout(io.StringIO()):
            units = tifa.align(samples, targets, diagnostics=raw)
        length = len(samples) / 16
        count = totals.setdefault(
            group["track"],
            Counter(cues=0, forced_added=0, partial_added=0, lost=0, moved=0),
        )
        count["cues"] += 1
        results = {}
        for mode, evidence in (("forced", forced), ("partial", partial)):
            clocks = supported_raw({"units": units, "raw_units": raw}, evidence, length)
            eligible = {
                i
                for i, (clock, unit) in enumerate(zip(clocks, evidence, strict=True))
                if 0 < clock["start_ms"] < clock["end_ms"] < length
                and clock["end_ms"] - clock["start_ms"] >= 80
                and 0.45 <= unit["mean_probability"] <= 1
                and max(abs(clock[k] - unit[k]) for k in ("start_ms", "end_ms")) <= 150
                and (
                    mode == "forced"
                    or unit["deletion_margin_nats"] is not None
                    and unit["deletion_margin_nats"] >= 2
                )
            }
            updated = overlay_original_groups(
                group["baseline"], clocks, eligible, group["source_word_count"]
            )
            for old, new in zip(group["baseline"], updated, strict=True):
                count[mode + "_added"] += not old["protected"] and new["start_ms"] >= 0
                if old["protected"]:
                    count["lost"] += new != old
                    count["moved"] += (old["start_ms"], old["end_ms"]) != (
                        new["start_ms"],
                        new["end_ms"],
                    )
            results[mode] = {
                "evidence": evidence,
                "eligible_indices": sorted(eligible),
                "result": updated,
            }
        records.append(
            {
                "track": group["track"],
                "occurrence": group["occurrence"],
                "baseline": group["baseline"],
                "tifa": units,
                "raw": raw,
                "methods": results,
            }
        )
        print(json.dumps({"completed_cues": len(records)}), flush=True)
    summary = {
        "per_song": totals,
        "saved_app_data_changed": False,
        "promoted": False,
        "identity_sha256": digest(args.output / "identity.json"),
    }
    (args.output / "private-records.json").write_text(json.dumps(records, indent=2))
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
