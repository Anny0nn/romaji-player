"""Fresh local TIFA paths against cached singing posteriors on frozen source spans.

Explicit Japanese-romaji hypothesis, not automatic language classification.
Uses authenticated Rust windows and existing separated audio; never captures.
This is exploratory evidence, not a promoted app recipe or correctness claim.
"""

import argparse
import contextlib
import io
import json
import os
import resource
import sys
import time
from collections import Counter
from pathlib import Path

from audio_first_models import ROOT, digest
from hubertfa_research import private_path
from romaji_source_phones import acoustic_spelling, japanese_romaji_phones
from singing_region_probe import recover_regions, strict_candidates

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa"), str(ROOT / "tifa/vendor")]


def write(path, value):
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as handle:
        json.dump(value, handle, indent=2, allow_nan=False)


def main():
    import numpy as np
    from refinement_helper import verify_assets
    from singing_timing import word_alignment
    from tifa_helper import Aligner, prepare_model

    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--track", required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for field in ("suite", "selection", "cache", "models", "archive", "output"):
        setattr(args, field, private_path(getattr(args, field)))
    suite = json.loads(args.suite.read_text())
    if suite["selection_sha256"] != digest(args.selection):
        raise ValueError("Changed frozen selection.")
    selection = json.loads(args.selection.read_text())
    selected = selection["low"] + selection["high"]
    if args.track not in {row["track"] for row in selected}:
        raise ValueError("Song is outside the frozen cap.")
    items = [row for row in suite["songs"] if row["track"] == args.track]
    if len(items) != 1:
        raise ValueError("Missing or duplicate authenticated song.")
    item = items[0]
    for field, expected in (("path", "sha256"), ("result_path", "result_sha256")):
        if digest(private_path(item[field])) != item[expected]:
            raise ValueError("Changed Rust job or source result.")
    job, saved = (
        json.loads(Path(item[field]).read_text()) for field in ("path", "result_path")
    )
    if (
        job["producer"] != "Rust crop_targets"
        or job["sample_rate"] != 16000
        or job["snapshot"] != saved["snapshot"]["id"]
        or job["delay_ms"] != saved["delay_ms"]
        or digest(private_path(item["pcm"])) != job["mono_pcm_sha256"]
    ):
        raise ValueError("Changed recording, source snapshot, delay or sample clock.")
    verify_assets(args.models)
    vocabulary = json.loads(
        (args.models / "singing/verified-v1/phoneme_vocab.json").read_text()
    )
    vocals_path = args.cache / "kim.pcm"
    if vocals_path.stat().st_size != job["recording_samples"] * 4:
        raise ValueError("Separated audio length does not match Rust recording.")
    signature = {
        "suite": digest(args.suite),
        "selection": digest(args.selection),
        "job": item["sha256"],
        "source_result": item["result_sha256"],
        "vocals": digest(vocals_path),
        "archive": digest(args.archive),
        "models": digest(ROOT / "refinement/refinement-model-files.json"),
        "code": {
            name: digest(Path(__file__).with_name(name))
            for name in (
                "probe-local-romaji.py",
                "romaji_source_phones.py",
                "singing_region_probe.py",
            )
        },
        "posteriors": {
            str(i): digest(args.cache / f"posterior-{i}.npz")
            for i in range(len(job["crops"]))
        },
        "route": "explicit Japanese-romaji hypothesis; no lyric/language selection",
    }
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    write(args.output / "identity.json", signature)
    aligner = Aligner(prepare_model(args.archive))
    vocals = np.memmap(vocals_path, dtype="<f4", mode="r")
    occurrences = {row["id"]: row for row in saved["snapshot"]["occurrences"]}
    started = time.monotonic()
    totals = Counter()
    for number, crop in enumerate(job["crops"]):
        targets = crop["targets"]
        fragments = {
            tuple(f["raw_span"]): f
            for f in occurrences[crop["occurrence"]]["fragments"]
        }
        baseline, protected = [], []
        for index, target in enumerate(targets):
            fragment = fragments.get(tuple(target["raw_span"]))
            interval = fragment["interval"] if fragment else None
            baseline.append(
                {
                    "raw_span": target["raw_span"],
                    "start_ms": interval["start_ms"] - crop["lyric_origin_ms"]
                    if interval
                    else -1,
                    "end_ms": interval["end_ms"] - crop["lyric_origin_ms"]
                    if interval
                    else -1,
                }
            )
            if fragment and not fragment["source"].startswith("alignment:"):
                protected.append(index)
        phones = [japanese_romaji_phones(target["text"]) for target in targets]
        if not all(phones) or not any(unit["start_ms"] < 0 for unit in baseline):
            totals["unparsed_or_complete_crops"] += 1
            continue
        acoustic_targets = [
            {**target, "text": acoustic_spelling(target["text"])} for target in targets
        ]
        first, last = crop["start_sample"], crop["end_sample"]
        length_ms = (last - first) // 16
        if not 0 <= first < last <= len(vocals):
            raise ValueError("Rust crop lies outside the recording.")
        with np.load(args.cache / f"posterior-{number}.npz") as value:
            logp, blank = value["logp"], int(value["blank"])
        if abs(len(logp) * 20 - length_ms) > 40:
            raise ValueError("Cached singing frames do not match the Rust crop clock.")
        independent = word_alignment(
            logp, blank, targets, vocabulary, word_phones=phones
        )
        raw = []
        with contextlib.redirect_stdout(io.StringIO()):
            units = aligner.align(
                vocals[first:last],
                acoustic_targets,
                diagnostics=raw,
                phonetic_aliases=dict(enumerate(phones)),
            )
        trial = {"units": units, "raw_units": raw}
        full_updated, full_events = recover_regions(
            baseline,
            trial,
            independent,
            length_ms,
            crop["source_word_count"],
            protected=protected,
        )
        full_added = {
            i
            for i, (old, new) in enumerate(zip(baseline, full_updated, strict=True))
            if old["start_ms"] < 0 <= new["start_ms"]
        }
        totals["full_window_proposed_additions"] += len(full_added)
        strong = strict_candidates(trial, independent, length_ms)
        local_trials = []
        for index, old in enumerate(baseline):
            if old["start_ms"] >= 0 or index in protected:
                continue
            left = next(
                (j for j in range(index - 1, -1, -1) if strong[j]["start_ms"] >= 0),
                None,
            )
            right = next(
                (
                    j
                    for j in range(index + 1, len(targets))
                    if strong[j]["start_ms"] >= 0
                ),
                None,
            )
            if left is None and right is None:
                totals["no_fresh_anchor"] += 1
                continue
            begin, end = (
                left if left is not None else index,
                right if right is not None else index,
            )
            if end - begin + 1 > 8:
                totals["local_target_limit"] += 1
                continue
            first_ms = (
                max(0, (strong[left]["start_ms"] - 200) // 20 * 20)
                if left is not None
                else 0
            )
            last_ms = (
                min(length_ms, (strong[right]["end_ms"] + 219) // 20 * 20)
                if right is not None
                else length_ms
            )
            frame_first, frame_last = (
                int(first_ms // 20),
                min(len(logp), int((last_ms + 19) // 20)),
            )
            local_evidence = word_alignment(
                logp[frame_first:frame_last],
                blank,
                targets[begin : end + 1],
                vocabulary,
                word_phones=phones[begin : end + 1],
            )
            local_raw = []
            with contextlib.redirect_stdout(io.StringIO()):
                local_units = aligner.align(
                    vocals[first + int(first_ms * 16) : first + int(last_ms * 16)],
                    acoustic_targets[begin : end + 1],
                    diagnostics=local_raw,
                    phonetic_aliases=dict(enumerate(phones[begin : end + 1])),
                )
            for collection in (local_units, local_raw, local_evidence):
                for unit in collection:
                    if unit["start_ms"] >= 0:
                        unit["start_ms"] += first_ms
                        unit["end_ms"] += first_ms
            # Each local trial is evaluated separately; never mix boundaries from
            # different windows into a path that no model actually observed.
            fresh_units, fresh_raw, fresh_evidence = (
                list(units),
                list(raw),
                list(independent),
            )
            fresh_units[begin : end + 1] = local_units
            fresh_raw[begin : end + 1] = local_raw
            fresh_evidence[begin : end + 1] = local_evidence
            updated, events = recover_regions(
                baseline,
                {"units": fresh_units, "raw_units": fresh_raw},
                fresh_evidence,
                length_ms,
                crop["source_word_count"],
                protected=protected,
            )
            added = [
                i
                for i, (a, b) in enumerate(zip(baseline, updated, strict=True))
                if a["start_ms"] < 0 <= b["start_ms"]
            ]
            moved = [
                i
                for i, (a, b) in enumerate(zip(baseline, updated, strict=True))
                if a["start_ms"] >= 0
                and (a["start_ms"], a["end_ms"]) != (b["start_ms"], b["end_ms"])
            ]
            local_trials.append(
                {
                    "target": index,
                    "groups": [begin, end],
                    "local_samples": [int(first_ms * 16), int(last_ms * 16)],
                    "added_indices": added,
                    "moved_indices": moved,
                    "updated": updated,
                    "units": local_units,
                    "raw": local_raw,
                    "independent": local_evidence,
                    "events": events,
                }
            )
            totals["local_trials"] += 1
        unique_added = {i for row in local_trials for i in row["added_indices"]}
        unique_moved = {i for row in local_trials for i in row["moved_indices"]}
        totals["proposed_unique_additions"] += len(unique_added)
        totals["local_proposals_beyond_full_window"] += len(unique_added - full_added)
        totals["proposed_unique_moves"] += len(unique_moved)
        totals["probed_crops"] += 1
        write(
            args.output / f"crop-{number}.json",
            {
                "occurrence": crop["occurrence"],
                "baseline": baseline,
                "full_trial": trial,
                "full_independent": independent,
                "full_updated": full_updated,
                "full_events": full_events,
                "local_trials": local_trials,
            },
        )
        print(
            json.dumps(
                {
                    "crop": number,
                    "local_trials": len(local_trials),
                    "proposed_additions": len(unique_added),
                    "proposed_moves": len(unique_moved),
                }
            ),
            flush=True,
        )
    summary = {
        "track": args.track,
        "original_timed": saved["timed_words"],
        "original_total": saved["total_words"],
        "counts": totals,
        "commercial_correctness_measured": False,
        "merged_recipe_evaluated": False,
        "saved_app_result_changed": False,
        "wall_seconds": time.monotonic() - started,
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    write(args.output / "summary.json", summary)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
