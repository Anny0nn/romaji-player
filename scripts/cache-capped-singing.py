"""Authenticate the frozen cap, reuse/collect vocals and export blind context windows.

No recording, lyrics service, or model downloads. Private source-bearing receipts
are separate from the audio-only recognition manifest. Completed stems are immutable.
"""

import argparse
import importlib.metadata
import json
import os
import sys
from pathlib import Path

from audio_first_models import ROOT, digest
from hubertfa_research import private_path

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
from english_timing import english_key


def write(path, value):
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as handle:
        json.dump(value, handle, indent=2, allow_nan=False)


def context_windows(crops, max_samples=480000):
    """Union whole, ordered Rust crops, overlapping by cue index. No new word clock."""
    if not crops or type(max_samples) is not int or max_samples <= 0:
        raise ValueError("Invalid context crop list or bound.")
    previous = -1
    for crop in crops:
        if (
            not all(type(crop[k]) is int for k in ("start_sample", "end_sample"))
            or not previous <= crop["start_sample"] < crop["end_sample"]
            or crop["end_sample"] - crop["start_sample"] > max_samples
        ):
            raise ValueError("Invalid or unordered Rust crop.")
        previous = crop["start_sample"]
    result, index = [], 0
    while index < len(crops):
        first = crops[index]["start_sample"]
        last, stop = crops[index]["end_sample"], index + 1
        while (
            stop < len(crops)
            and max(last, crops[stop]["end_sample"]) - first <= max_samples
        ):
            last = max(last, crops[stop]["end_sample"])
            stop += 1
        result.append(
            {
                "first_sample": first,
                "last_sample": last,
                "occurrences": [c["occurrence"] for c in crops[index:stop]],
            }
        )
        if stop == len(crops):
            break
        index += max(1, (stop - index) // 2)
    return result


def main():
    import numpy as np
    from refinement_helper import separate, verify_assets

    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-mix-cases", type=Path)
    parser.add_argument("--reuse-kim-cases", type=Path)
    parser.add_argument("--reuse-romanized-cache", type=Path)
    parser.add_argument("--reuse-probe-identity", type=Path)
    args = parser.parse_args()
    for name in (
        "suite",
        "selection",
        "models",
        "output",
        "reuse_mix_cases",
        "reuse_kim_cases",
        "reuse_romanized_cache",
        "reuse_probe_identity",
    ):
        value = getattr(args, name)
        if value is not None:
            setattr(args, name, private_path(value))
    suite, selection = (
        json.loads(path.read_text()) for path in (args.suite, args.selection)
    )
    if suite["selection_sha256"] != digest(args.selection) or {
        r["track"] for r in suite["songs"]
    } != {r["track"] for r in selection["low"] + selection["high"]}:
        raise ValueError("Changed frozen song set.")
    if bool(args.reuse_mix_cases) != bool(args.reuse_kim_cases):
        parser.error("both reuse case manifests are required")
    if bool(args.reuse_romanized_cache) != bool(args.reuse_probe_identity):
        parser.error("romanized cache reuse requires its authenticated probe identity")
    reuse = {}
    if args.reuse_mix_cases:
        mix = {
            r["id"]: r
            for r in json.loads(args.reuse_mix_cases.read_text())
            if not r["id"].startswith("control:")
        }
        for row in json.loads(args.reuse_kim_cases.read_text()):
            original = mix.get(row["id"])
            if original:
                reuse.setdefault(row["track"], []).append((original, row))
    verify_assets(args.models)
    signature = {
        "suite": digest(args.suite),
        "selection": digest(args.selection),
        "models": digest(ROOT / "refinement/refinement-model-files.json"),
        "runner": digest(Path(__file__)),
        "separator": digest(ROOT / "refinement/refinement_helper.py"),
        "versions": {
            name: importlib.metadata.version(name) for name in ("mlx", "numpy", "scipy")
        },
        "reuse": {
            name: digest(getattr(args, name))
            for name in ("reuse_mix_cases", "reuse_kim_cases", "reuse_probe_identity")
            if getattr(args, name)
        },
    }
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    identity = args.output / "identity.json"
    if identity.exists():
        if json.loads(identity.read_text()) != signature:
            raise ValueError("Cache recipe changed; use another output directory.")
    else:
        write(identity, signature)
    contexts, songs = [], []
    for row in suite["songs"]:
        for field, expected in (("path", "sha256"), ("result_path", "result_sha256")):
            if digest(private_path(row[field])) != row[expected]:
                raise ValueError("Frozen source job/result changed.")
        job = json.loads(Path(row["path"]).read_text())
        saved = json.loads(Path(row["result_path"]).read_text())
        if (
            job["producer"] != "Rust crop_targets"
            or job["sample_rate"] != 16000
            or job["snapshot"] != saved["snapshot"]["id"]
            or job["delay_ms"] != saved["delay_ms"]
            or digest(private_path(row["pcm"])) != job["mono_pcm_sha256"]
        ):
            raise ValueError("Changed source/recording identity or clock.")
        occurrences = {r["id"]: r for r in saved["snapshot"]["occurrences"]}
        nominated = []
        for crop in job["crops"]:
            occurrence = occurrences[crop["occurrence"]]
            timed = {tuple(f["raw_span"]) for f in occurrence["fragments"]}
            raw = occurrence["raw_line"].encode()
            if any(
                tuple(t["raw_span"]) not in timed
                and english_key(raw[t["raw_span"][0] : t["raw_span"][1]].decode())
                for t in crop["targets"]
            ):
                nominated.append(crop["occurrence"])
        if not nominated:
            songs.append(
                {
                    "track": row["track"],
                    "eligible": False,
                    "reason": "no_missing_latin_source_groups",
                }
            )
            continue
        folder = args.output / row["track"]
        folder.mkdir(mode=0o700, exist_ok=True)
        receipt = folder / "stem.json"
        if receipt.exists():
            stem = json.loads(receipt.read_text())
            if (
                stem["original_pcm_sha256"] != job["mono_pcm_sha256"]
                or stem["identity_sha256"] != digest(identity)
                or digest(private_path(stem["path"])) != stem["sha256"]
            ):
                raise ValueError("Changed completed stem identity or bytes.")
        else:
            reused = None
            for original, candidate in reuse.get(row["track"], []):
                if (
                    original["audio_sha256"] == job["mono_pcm_sha256"]
                    and digest(private_path(candidate["pcm"]))
                    == candidate["audio_sha256"]
                ):
                    reused = Path(candidate["pcm"])
                    break
            if reused is None and args.reuse_romanized_cache:
                candidate = args.reuse_romanized_cache / row["track"] / "kim.pcm"
                parent = json.loads(args.reuse_probe_identity.read_text())
                if (
                    candidate.exists()
                    and parent["selection"] == digest(args.selection)
                    and parent["job"] == row["sha256"]
                    and parent["source_result"] == row["result_sha256"]
                    and parent["models"] == signature["models"]
                    and digest(candidate) == parent["vocals"]
                ):
                    reused = candidate
            path = reused or folder / "kim.pcm"
            if not reused:
                stereo_path = private_path(row["stereo"])
                stereo_sha = digest(stereo_path)
                stereo = np.asarray(
                    np.memmap(stereo_path, dtype="<f4", mode="r").reshape(-1, 2).T
                )
                vocals = separate(
                    stereo,
                    job["recording_samples"],
                    args.models,
                    "Kim",
                    folder / "progress.txt",
                )
                temporary = folder / "kim.pcm.partial"
                vocals.astype("<f4").tofile(temporary)
                del vocals, stereo
                if digest(stereo_path) != stereo_sha:
                    raise ValueError("Original stereo changed while separating.")
                temporary.rename(path)
            if path.stat().st_size != job["recording_samples"] * 4:
                raise ValueError("Stem changed original sample count.")
            stem = {
                "path": str(path),
                "sha256": digest(path),
                "original_pcm_sha256": job["mono_pcm_sha256"],
                "identity_sha256": digest(identity),
                "reused": bool(reused),
            }
            write(receipt, stem)
        windows = context_windows(job["crops"])
        # Each nominated cue chooses one whole-context union, before recognition.
        chosen = {}
        for occurrence in nominated:
            crop = next(c for c in job["crops"] if c["occurrence"] == occurrence)
            eligible = [
                (i, window)
                for i, window in enumerate(windows)
                if occurrence in window["occurrences"]
            ]
            center = (crop["start_sample"] + crop["end_sample"]) / 2
            index, _ = min(
                eligible,
                key=lambda pair: (
                    abs(
                        center - (pair[1]["first_sample"] + pair[1]["last_sample"]) / 2
                    ),
                    pair[0],
                ),
            )
            chosen[str(occurrence)] = index
        for index in sorted(set(chosen.values())):
            window = windows[index]
            for role, path, sha in (
                ("mix", row["pcm"], job["mono_pcm_sha256"]),
                ("kim", stem["path"], stem["sha256"]),
            ):
                contexts.append(
                    {
                        "id": f"{row['track']}:{index}:{role}",
                        "path": str(path),
                        "sha256": sha,
                        "encoding": "pcm",
                        "first_sample": window["first_sample"],
                        "last_sample": window["last_sample"],
                    }
                )
        songs.append(
            {
                "track": row["track"],
                "eligible": True,
                "job_sha256": row["sha256"],
                "result_sha256": row["result_sha256"],
                "stem_receipt_sha256": digest(receipt),
                "cue_context": chosen,
                "windows": windows,
            }
        )
        print(
            json.dumps(
                {
                    "track": row["track"],
                    "reused_vocals": stem["reused"],
                    "context_windows": len(set(chosen.values())),
                }
            ),
            flush=True,
        )
    if not (args.output / "audio-contexts.json").exists():
        write(args.output / "audio-contexts.json", {"version": 1, "cases": contexts})
        write(
            args.output / "suite-contexts.json",
            {
                "identity_sha256": digest(identity),
                "audio_manifest_sha256": digest(args.output / "audio-contexts.json"),
                "songs": songs,
            },
        )
    elif json.loads((args.output / "audio-contexts.json").read_text()) != {
        "version": 1,
        "cases": contexts,
    }:
        raise ValueError("Completed recognition contexts changed.")
    print(
        json.dumps(
            {
                "songs": len(songs),
                "eligible_songs": sum(s["eligible"] for s in songs),
                "audio_cases": len(contexts),
            }
        )
    )


if __name__ == "__main__":
    main()
