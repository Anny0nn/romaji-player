"""Promptless Parakeet English recognition on the frozen private audio pilot.

Predicted TDT durations are proposals, not word clocks. No confidence is minted
for a decoder which does not expose one. No lyrics enter recognition.
"""

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import os
import resource
import sys
import time
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path
from singing_asr_runtime import verify_runtime

REVISION = "b8e276dc1b4645dc90ddb6d7b22fa82e9773f685"
WEIGHTS_SHA = "b958c37a6baa6874a279108755c8f2818e27bf647d72d54800a234a421341dfe"
spec = importlib.util.spec_from_file_location(
    "blind_audio_runner", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--runtime-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--precision", choices=("float32", "bfloat16"), default="float32"
    )
    args = parser.parse_args()
    for name in vars(args):
        if isinstance(getattr(args, name), Path):
            setattr(args, name, private_path(getattr(args, name)))
    os.umask(0o077)
    os.environ.update(
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1"
    )
    cases = blind.manifest_cases(json.loads(args.manifest.read_text()))
    receipt = json.loads((args.model_directory / "assets.json").read_text())
    pinned = json.loads((ROOT / "scripts/parakeet-model-files.json").read_text())
    if any(
        receipt[k] != pinned[k] for k in ("repo", "revision", "runtime_commit", "files")
    ):
        raise ValueError("English-ASR assets differ from reviewed pin.")
    if (
        receipt["repo"] != "mlx-community/parakeet-tdt-0.6b-v2"
        or receipt["revision"] != REVISION
        or receipt["files"]["model.safetensors"]
        != {"sha256": WEIGHTS_SHA, "size": 2471559904}
    ):
        raise ValueError("Different English speech-ASR checkpoint.")
    for name, row in receipt["files"].items():
        path = args.model_directory / "model" / name
        if (
            Path(name).name != name
            or path.stat().st_size != row["size"]
            or digest(path) != row["sha256"]
        ):
            raise ValueError("Changed English-ASR asset bytes.")
    if {p.name for p in (args.model_directory / "model").iterdir()} != {
        "config.json",
        "model.safetensors",
        "tokenizer.model",
    }:
        raise ValueError("Unexpected model source/asset.")
    runtime = verify_runtime(args.runtime_directory)
    sys.path[:0] = [
        str(args.runtime_directory / "runtime"),
        str(args.runtime_directory / "dependencies"),
    ]
    import mlx.core as mx
    from mlx_audio.stt import load

    mx.set_memory_limit(8 * 1024**3)
    mx.set_cache_limit(256 * 1024**2)
    recipe = {
        "manifest_sha256": digest(args.manifest),
        "assets": receipt,
        "runtime": runtime,
        "runner": digest(Path(__file__)),
        "prompt": None,
        "strict": True,
        "decoder": "greedy TDT; no token confidence exposed",
        "precision": args.precision,
        "evidence_role": "unverified lexical proposal; duration predictions are not saved timings",
    }
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    blind.write(args.output / "recipe.json", recipe)
    signature = digest(args.output / "recipe.json")
    started = time.monotonic()
    model = load(args.model_directory / "model", strict=True, model_type="parakeet")
    load_seconds = time.monotonic() - started
    print(
        json.dumps(
            {
                "loaded": True,
                "seconds": load_seconds,
                "mlx_peak_bytes": mx.get_peak_memory(),
            }
        ),
        flush=True,
    )
    records = []
    cache = {}
    for i, case in enumerate(cases, 1):
        samples = blind.load_samples(case, args.manifest.parent, cache)
        if len(samples) > 30 * 16000:
            raise ValueError("Pilot exceeds30seconds.")
        began = time.monotonic()
        result = model.generate(
            mx.array(samples, dtype=mx.float32),
            dtype=getattr(mx, args.precision),
            verbose=False,
        )
        row = {
            "case": case,
            "recipe_sha256": signature,
            "crop_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
            "text": result.text,
            "predicted_tdt": dataclasses.asdict(result),
            "seconds": time.monotonic() - began,
            "mlx_peak_bytes": mx.get_peak_memory(),
            "process_peak_rss_bytes": resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss,
        }
        name = hashlib.sha256(case["id"].encode()).hexdigest() + ".json"
        blind.write(args.output / name, row)
        records.append({"file": name, "sha256": digest(args.output / name)})
        print(
            json.dumps(
                {
                    "completed": i,
                    "total": len(cases),
                    "seconds": row["seconds"],
                    "mlx_peak_bytes": row["mlx_peak_bytes"],
                }
            ),
            flush=True,
        )
        del result
        mx.clear_cache()
    blind.write(
        args.output / "complete.json",
        {
            "recipe_sha256": signature,
            "records": records,
            "load_seconds": load_seconds,
            "total_seconds": time.monotonic() - started,
        },
    )


if __name__ == "__main__":
    main()
