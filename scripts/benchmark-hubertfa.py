"""Research-only singing boundary benchmark; used NUS development labels only.

Run with the existing experimental environment. Downloads, checkpoints, phones
and recordings remain outside the checkout. This runner cannot open heldout labels.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import resource
import time
from pathlib import Path

from english_phone_reference import labels, phrase_groups
from hubertfa_research import ASSETS, ResearchAligner, assets, digest, private_path
from singing_reference import evaluate


def write(path, value):
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
    ) as handle:
        json.dump(value, handle, indent=2, allow_nan=False)


def canonical_digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def write_checkpoint(path, row, identity):
    write(
        path,
        {
            "identity_sha256": canonical_digest(identity),
            "record_sha256": canonical_digest(row),
            "record": row,
        },
    )


def read_checkpoint(path, identity):
    value = json.loads(path.read_text())
    if value["identity_sha256"] != canonical_digest(identity) or value[
        "record_sha256"
    ] != canonical_digest(value["record"]):
        raise ValueError("Changed completed observation or evidence identity.")
    return value["record"]


def word_records(rows, *, supported):
    result = []
    for row in rows:
        reference, predicted = [], []
        for word in dict.fromkeys(u["word"] for u in row["reference"]):
            indices = [i for i, u in enumerate(row["reference"]) if u["word"] == word]
            units = [row["predicted"][i] for i in indices]
            ref = {
                "unit": word,
                "phone": " ".join(row["reference"][i]["phone"] for i in indices),
                "start_ms": row["reference"][indices[0]]["start_ms"],
                "end_ms": row["reference"][indices[-1]]["end_ms"],
            }
            valid = all(0 <= u["start_ms"] < u["end_ms"] for u in units)
            if supported:
                valid = (
                    valid
                    and sum(u["mean_probability"] for u in units) / len(units) >= 0.45
                )
            reference.append(ref)
            predicted.append(
                {
                    **ref,
                    "start_ms": units[0]["start_ms"] if valid else -1,
                    "end_ms": units[-1]["end_ms"] if valid else -1,
                }
            )
        result.append({"id": row["id"], "reference": reference, "predicted": predicted})
    return result


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["fetch", "run"])
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", choices=["cpu", "mps"], default="cpu")
    args = parser.parse_args()
    model_dir = private_path(args.model_directory)
    assets(model_dir, download=args.operation == "fetch")
    if args.operation == "fetch":
        print("Pinned research-only assets verified; nothing bundled in the app.")
        return
    if not args.manifest or not args.output:
        parser.error("run needs --manifest and --output")
    manifest, output = private_path(args.manifest), private_path(args.output)
    config = json.loads(manifest.read_text())
    dev, reserve = config["development"], config["heldout"]
    if not dev or not reserve or len(set(dev + reserve)) != len(dev + reserve):
        raise ValueError("Invalid or overlapping development/reserve IDs.")
    songs = {row["id"]: row for row in config["songs"]}
    if len(songs) != len(config["songs"]) or not set(dev) <= songs.keys():
        raise ValueError("Duplicate or missing development song.")
    for name in dev:
        for field in ("audio", "annotation"):
            private_path(songs[name][field])
    # Reserve paths/labels are neither opened nor hashed by this development runner.
    signature = {
        "manifest": digest(manifest),
        "model": digest(ASSETS),
        "code": {
            name: digest(Path(__file__).with_name(name))
            for name in (
                "benchmark-hubertfa.py",
                "hubertfa_research.py",
                "english_phone_reference.py",
                "singing_reference.py",
            )
        },
        "versions": {
            name: importlib.metadata.version(name)
            for name in (
                "torch",
                "transformers",
                "numpy",
                "scipy",
                "soundfile",
                "PyYAML",
            )
        },
        "device": args.device,
        "partition": "development",
        "probability_threshold": 0.45,
        "inputs": {
            name: {
                field: digest(songs[name][field]) for field in ("audio", "annotation")
            }
            for name in dev
        },
        "preprocessing": "raw mono 44100; scipy polyphase 160/441; no waveform normalization; 10ms ties-to-even feature grid; no added left padding",
    }
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = output / "identity.json"
    if receipt.exists():
        if json.loads(receipt.read_text()) != signature:
            raise ValueError("Changed evidence identity; use a fresh output directory.")
    else:
        write(receipt, signature)
    if (output / "summary.json").exists():
        print("Authenticated benchmark already complete.")
        return
    import numpy as np
    import soundfile as sf
    import torch

    torch.set_num_threads(4)

    started = time.monotonic()
    backend = ResearchAligner(model_dir, args.device)
    load_seconds = time.monotonic() - started
    started = time.monotonic()
    records = []
    resumed = 0
    for name in dev:
        song = songs[name]
        waveform, rate = sf.read(song["audio"], dtype="float32")
        if rate != 44100 or waveform.ndim != 1 or not np.isfinite(waveform).all():
            raise ValueError("Expected original mono 44.1 kHz NUS recording.")
        reference = labels(
            Path(song["annotation"]).read_text(), len(waveform) * 1000 / rate
        )
        for index, phrase in enumerate(phrase_groups(reference)):
            path = output / f"{name}-{index}.json"
            if path.exists():
                records.append(read_checkpoint(path, signature))
                resumed += 1
                continue
            first = max(0, int((phrase[0]["start_ms"] - 500) * 44.1))
            last = min(len(waveform), int((phrase[-1]["end_ms"] + 300) * 44.1))
            relative = [
                {
                    **r,
                    "start_ms": r["start_ms"] - first / 44.1,
                    "end_ms": r["end_ms"] - first / 44.1,
                }
                for r in phrase
            ]
            if last - first > 30 * rate:
                predicted, diagnostic = (
                    [
                        {**r, "start_ms": -1, "end_ms": -1, "mean_probability": 0.0}
                        for r in relative
                    ],
                    {"status": "long_phrase"},
                )
            else:
                predicted, diagnostic = backend.infer(waveform[first:last], relative)
            row = {
                "id": f"{name}:{index}",
                "reference": relative,
                "predicted": predicted,
                "diagnostic": diagnostic,
                "crop_samples": [first, last],
            }
            write_checkpoint(path, row, signature)
            records.append(row)
            print(
                json.dumps(
                    {
                        "song": name,
                        "phrase": index,
                        "phones": len(relative),
                        "status": diagnostic["status"],
                    }
                ),
                flush=True,
            )
    for name in dev:
        if {
            field: digest(songs[name][field]) for field in ("audio", "annotation")
        } != signature["inputs"][name]:
            raise ValueError("Reference input changed during inference.")
    summary = {
        "signature": signature,
        "songs": len(dev),
        "resumed_phrases": resumed,
        "phone_metrics": evaluate(records),
        "word_group_metrics": {
            **evaluate(word_records(records, supported=False)),
            "granularity": "human_sp_word_group",
        },
        "supported_word_group_metrics": {
            **evaluate(word_records(records, supported=True)),
            "granularity": "human_sp_word_group",
        },
        "word_spelling_accuracy_measured": False,
        "model_load_seconds": load_seconds,
        "wall_seconds_after_load_this_invocation": time.monotonic() - started,
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "mps_driver_bytes": torch.mps.driver_allocated_memory()
        if args.device == "mps"
        else None,
    }
    write(output / "summary.json", summary)
    print(
        json.dumps(
            {
                "word_groups": summary["word_group_metrics"],
                "supported_word_groups": summary["supported_word_group_metrics"],
                "wall_seconds": summary["wall_seconds_after_load_this_invocation"],
            }
        )
    )


if __name__ == "__main__":
    main()
