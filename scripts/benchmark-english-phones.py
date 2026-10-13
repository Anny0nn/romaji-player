"""Private, frozen NUS human-phone benchmark for a speech-trained IPA verifier.

Manifest: model_directory, development [ids], heldout [ids], songs
[{id,audio,annotation}]. The NUS data remain research-only outside git.
This measures supplied-phone timing and probability, not recognized lyric accuracy.
"""

import argparse
import contextlib
import hashlib
import io
import json
import os
import resource
import sys
import time
from pathlib import Path

from english_phone_reference import labels, phrase_groups, tokens
from singing_reference import evaluate, selected_ids

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "refinement"))
from refinement_policy import ctc_path


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)


def infer(model, processor, samples, refs, vocabulary):
    import numpy as np
    import torch

    predicted = [
        {**r, "start_ms": -1, "end_ms": -1, "mean_probability": 0.0} for r in refs
    ]
    target = tokens(refs, vocabulary)
    if target is None:
        return predicted, "unsupported_inventory"
    inputs = processor(samples, sampling_rate=16000, return_tensors="pt").to("mps")
    with torch.inference_mode():
        logp = model(**inputs).logits[0].float().log_softmax(-1).cpu().numpy()
    path = ctc_path(logp.tolist(), target, 0)
    if path is None:
        return predicted, "incomplete"
    path = np.array(path)
    for index, result in enumerate(predicted):
        frames = np.flatnonzero(path == 2 * index + 1)
        if not frames.size:
            continue
        result.update(
            start_ms=int(frames[0] * 20),
            end_ms=min(int(frames[-1] * 20 + 25), len(samples) // 16),
            mean_probability=float(np.exp(logp[frames, target[index]]).mean()),
        )
    return predicted, "forced_phone_path"


def word_records(rows):
    result = []
    for row in rows:
        refs, predictions = [], []
        owners = list(dict.fromkeys(r["word"] for r in row["reference"]))
        for word in owners:
            indices = [i for i, r in enumerate(row["reference"]) if r["word"] == word]
            reference = {
                "unit": word,
                "phone": " ".join(row["reference"][i]["phone"] for i in indices),
                "start_ms": row["reference"][indices[0]]["start_ms"],
                "end_ms": row["reference"][indices[-1]]["end_ms"],
            }
            units = [row["predicted"][i] for i in indices]
            accepted = (
                all(u["start_ms"] >= 0 for u in units)
                and sum(u["mean_probability"] for u in units) / len(units) >= 0.45
            )
            refs.append(reference)
            predictions.append(
                {
                    **reference,
                    "start_ms": units[0]["start_ms"] if accepted else -1,
                    "end_ms": units[-1]["end_ms"] if accepted else -1,
                }
            )
        result.append({"id": row["id"], "reference": refs, "predicted": predictions})
    return result


def main():
    import numpy as np
    import soundfile as sf
    import torch
    from scipy.signal import resample_poly
    from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["freeze", "run"])
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--partition", choices=["development", "heldout"], default="development"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    manifest, output = args.manifest.resolve(), args.output.resolve()
    if (
        ROOT == manifest
        or ROOT in manifest.parents
        or ROOT == output
        or ROOT in output.parents
    ):
        parser.error("Reference files and outputs must live outside the checkout.")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.chmod(0o700)
    if (output / "summary.json").exists():
        parser.error("Use a fresh output directory.")
    config = json.loads(manifest.read_text())
    model_dir = Path(config["model_directory"])
    assets = json.loads((ROOT / "scripts/english-ctc-model-files.json").read_text())
    for name, expected in assets["files"].items():
        path = model_dir / name
        if (
            path.stat().st_size != expected["size"]
            or digest(path) != expected["sha256"]
        ):
            raise ValueError("Unverified English acoustic model.")
    files = {r["id"]: r for r in config["songs"]}
    if len(files) != len(config["songs"]):
        raise ValueError("Duplicate reference song ID.")
    signature = {
        "manifest": digest(manifest),
        "runner": digest(Path(__file__)),
        "mapping": digest(ROOT / "scripts/english_phone_reference.py"),
        "metrics": digest(ROOT / "scripts/singing_reference.py"),
        "ctc": digest(ROOT / "refinement/refinement_policy.py"),
        "model": digest(ROOT / "scripts/english-ctc-model-files.json"),
        "inputs": {
            key: {name: digest(Path(row[name])) for name in ("audio", "annotation")}
            for key, row in files.items()
        },
    }
    if args.operation == "freeze":
        write(output / "frozen.json", signature)
        print("English model, mapping and references frozen; no labels parsed.")
        return
    ids = selected_ids(
        config,
        args.partition,
        json.loads(args.receipt.read_text()) if args.receipt else None,
        signature,
    )
    if not set(ids) <= files.keys():
        raise ValueError("Missing reference input.")
    vocabulary = json.loads((model_dir / "vocab.json").read_text())
    processor = Wav2Vec2FeatureExtractor(
        **json.loads((model_dir / "preprocessor_config.json").read_text())
    )
    with contextlib.redirect_stdout(io.StringIO()):
        backend = (
            Wav2Vec2ForCTC.from_pretrained(
                model_dir, local_files_only=True, use_safetensors=True
            )
            .to("mps")
            .eval()
        )
    if (
        backend.config.pad_token_id != 0
        or backend.config.conv_stride != [5, 2, 2, 2, 2, 2, 2]
        or backend.config.conv_kernel != [10, 3, 3, 3, 3, 2, 2]
    ):
        raise ValueError("Changed phoneme clock or blank inventory.")
    records = []
    started = time.monotonic()
    for name in ids:
        song = files[name]
        waveform, rate = sf.read(song["audio"], dtype="float32")
        if waveform.ndim != 1 or not np.isfinite(waveform).all() or rate != 44100:
            raise ValueError("Expected original mono 44.1 kHz NUS recording.")
        refs = labels(Path(song["annotation"]).read_text(), len(waveform) * 1000 / rate)
        samples = resample_poly(waveform, 160, 441).astype(np.float32)
        for index, reference in enumerate(phrase_groups(refs)):
            first = max(0, int(reference[0]["start_ms"] - 500)) * 16
            last = min(len(samples), int(reference[-1]["end_ms"] + 300) * 16)
            relative = [
                {
                    **r,
                    "start_ms": r["start_ms"] - first / 16,
                    "end_ms": r["end_ms"] - first / 16,
                }
                for r in reference
            ]
            if last - first > 480000:
                prediction, status = (
                    [
                        {**r, "start_ms": -1, "end_ms": -1, "mean_probability": 0.0}
                        for r in relative
                    ],
                    "long_phrase",
                )
            else:
                prediction, status = infer(
                    backend, processor, samples[first:last], relative, vocabulary
                )
            records.append(
                {
                    "id": f"{name}:{index}",
                    "reference": relative,
                    "predicted": prediction,
                    "status": status,
                }
            )
    filtered = [
        {
            **row,
            "predicted": [
                {
                    **u,
                    "start_ms": u["start_ms"] if u["mean_probability"] >= 0.45 else -1,
                    "end_ms": u["end_ms"] if u["mean_probability"] >= 0.45 else -1,
                }
                for u in row["predicted"]
            ],
        }
        for row in records
    ]
    summary = {
        "partition": args.partition,
        "songs": len(ids),
        "signature": signature,
        "phone_metrics": evaluate(records),
        "supported_phone_metrics": evaluate(filtered),
        "word_group_metrics": {
            **evaluate(word_records(records)),
            "granularity": "human_sp_word_group",
        },
        "word_spelling_accuracy_measured": False,
        "mapping_ambiguity": "ER unsupported; stressless AH uses canonical US ʌ, not guessed schwa.",
        "wall_seconds_after_load": time.monotonic() - started,
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "mps_driver_bytes": torch.mps.driver_allocated_memory(),
    }
    write(output / "private-records.json", records)
    write(output / "summary.json", summary)
    print(
        json.dumps(
            {
                key: summary[key]
                for key in [
                    "songs",
                    "wall_seconds_after_load",
                    "process_peak_rss_bytes",
                ]
            }
        )
    )


if __name__ == "__main__":
    main()
