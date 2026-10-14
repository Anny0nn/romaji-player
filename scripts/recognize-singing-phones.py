"""Blind private pronunciation recognition. Manifest contains audio identity only.

Schema: {version: 1, cases: [{id, path, sha256, encoding: pcm|wav,
first_sample, last_sample}]}. Bounds refer to the 16 kHz resampled waveform.
Writes acoustic outputs before any reference/scoring/source reconciliation step.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import resource
import time
from pathlib import Path

from audio_first_ctc import beam, greedy, phone_hypotheses
from audio_first_models import (
    ROOT,
    digest,
    expanded_phones,
    kana_sequence_phones,
    load_kana,
    load_romaji,
)


def manifest_cases(data):
    if set(data) != {"version", "cases"} or data["version"] != 1:
        raise ValueError("Expected an audio-only manifest.")
    ids = set()
    for case in data["cases"]:
        if set(case) != {
            "id",
            "path",
            "sha256",
            "encoding",
            "first_sample",
            "last_sample",
        }:
            raise ValueError(
                "Recognition manifest must not include source/reference text."
            )
        first, last = case["first_sample"], case["last_sample"]
        if (
            not isinstance(case["id"], str)
            or not case["id"]
            or case["id"] in ids
            or type(first) is not int
            or type(last) is not int
            or not 0 <= first < last
            or last - first > 16000 * 120
            or case["encoding"] not in ("pcm", "wav")
        ):
            raise ValueError("Invalid recording identity or bounds.")
        ids.add(case["id"])
    if not ids:
        raise ValueError("No audio cases.")
    return data["cases"]


def write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False)


def load_samples(case, base, cache):
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    path = (base / case["path"]).resolve()
    if path not in cache:
        if digest(path) != case["sha256"]:
            raise ValueError("Recording bytes changed.")
        if case["encoding"] == "pcm":
            if path.stat().st_size % 4:
                raise ValueError("Invalid float32 recording bytes.")
            samples = np.memmap(path, dtype="<f4", mode="r")
        else:
            samples, rate = sf.read(path, dtype="float32")
            if samples.ndim != 1 or rate not in (16000, 48000):
                raise ValueError("Expected mono 16/48 kHz vocals.")
            if rate == 48000:
                samples = resample_poly(samples, 1, 3).astype(np.float32)
        if not np.isfinite(samples).all():
            raise ValueError("Nonfinite recording samples.")
        cache.clear()  # One recording resident; suites never accumulate whole songs.
        cache[path] = (samples, case["sha256"], case["encoding"])
    samples, sha, encoding = cache[path]
    if sha != case["sha256"] or encoding != case["encoding"]:
        raise ValueError("Conflicting recording identity.")
    if case["last_sample"] > len(samples):
        raise ValueError("Crop is outside recording.")
    return np.array(samples[case["first_sample"] : case["last_sample"]], copy=True)


def main():
    import numpy as np
    import torch

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--engine", choices=["romaji", "kana"], required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--kana-source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--precision", choices=["float32", "float16"], default="float32"
    )
    parser.add_argument("--greedy-only", action="store_true")
    parser.add_argument("--beam-width", type=int, default=32)
    parser.add_argument("--nbest", type=int, default=8)
    parser.add_argument("--token-prune", type=int, default=16)
    args = parser.parse_args()
    source, output = args.manifest.resolve(), args.output.resolve()
    if ROOT == output or ROOT in output.parents or ROOT in source.parents:
        parser.error("Private manifests/results must stay outside the checkout.")
    if args.engine == "kana" and args.kana_source is None:
        parser.error("Provide the pinned kana source checkout.")
    if args.engine == "romaji" and args.precision != "float32":
        parser.error("The shipped RomajiASR adapter uses FP32.")
    cases = manifest_cases(json.loads(source.read_text()))
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    torch.set_num_threads(4)
    began = time.monotonic()
    infer, meta = (
        load_romaji(args.models.resolve())
        if args.engine == "romaji"
        else load_kana(
            args.models.resolve(), args.kana_source.resolve(), args.precision
        )
    )
    provenance = {
        "manifest_sha256": digest(source),
        "engine": args.engine,
        "model": meta,
        "implementation": {
            name: digest(ROOT / name)
            for name in (
                "scripts/recognize-singing-phones.py",
                "scripts/audio_first_ctc.py",
                "scripts/audio_first_models.py",
                "refinement/reading_repair.py",
                "refinement/singing_phonemes.py",
                "tifa/vendor/g2p/converters/japanese.py",
            )
        },
        "torch_version": torch.__version__,
        "library_versions": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "transformers", "scipy")
        },
        "decoder": {
            "beam_width": args.beam_width,
            "nbest": args.nbest,
            "token_prune": args.token_prune,
            "greedy_only": args.greedy_only,
            "language_model": None,
        },
    }
    write(output / "recipe.json", provenance)
    recipe = digest(output / "recipe.json")
    completed, cache = [], {}
    for number, case in enumerate(cases, 1):
        samples = load_samples(case, source.parent, cache)
        started = time.monotonic()
        matrices = infer(samples)
        inference_seconds = time.monotonic() - started
        heads, failure = {}, None
        if any(not np.isfinite(matrix).all() for matrix in matrices.values()):
            failure = "nonfinite_acoustic_output"
        else:
            for name, matrix in matrices.items():
                vocabulary = meta["heads"][name]
                inverse = {v: k for k, v in vocabulary.items()}

                def expand(ids, name=name, vocabulary=vocabulary, inverse=inverse):
                    if name == "kana":
                        return kana_sequence_phones("".join(inverse[i] for i in ids))
                    if name == "kana-phone":
                        return [inverse[i] for i in ids]
                    return expanded_phones(ids, vocabulary)

                result = greedy(matrix, meta["blank"])
                result["phones"] = expand(result["token_ids"])
                result["tokens"] = [inverse[i] for i in result["token_ids"]]
                hypotheses = []
                if not args.greedy_only:
                    hypotheses = phone_hypotheses(
                        beam(
                            matrix,
                            meta["blank"],
                            width=args.beam_width,
                            nbest=args.nbest,
                            token_prune=args.token_prune,
                        ),
                        expand,
                    )
                    for hypothesis in hypotheses:
                        hypothesis["tokens"] = [
                            inverse[i] for i in hypothesis["token_ids"]
                        ]
                stem = hashlib.sha256(case["id"].encode()).hexdigest()
                posterior = output / f"{stem}-{name}.npz"
                np.savez(posterior, logp=matrix, blank=meta["blank"])
                heads[name] = {
                    "greedy": result,
                    "nbest": hypotheses,
                    "posterior": posterior.name,
                    "posterior_sha256": digest(posterior),
                    "frames": len(matrix),
                }
        row = {
            "case": case,
            "resampled_crop_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
            "recipe_sha256": recipe,
            "heads": heads,
            "failure": failure,
            "inference_seconds": inference_seconds,
            "decode_and_write_seconds": time.monotonic() - started - inference_seconds,
            "process_lifetime_peak_rss_bytes": resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss,
            "mps_driver_bytes_sample": torch.mps.driver_allocated_memory(),
        }
        filename = hashlib.sha256(case["id"].encode()).hexdigest() + ".json"
        write(output / filename, row)
        completed.append({"file": filename, "sha256": digest(output / filename)})
        print(
            json.dumps({"completed": number, "total": len(cases), "failure": failure}),
            flush=True,
        )
    write(
        output / "complete.json",
        {
            "recipe_sha256": recipe,
            "records": completed,
            "total_seconds": time.monotonic() - began,
        },
    )


if __name__ == "__main__":
    main()
