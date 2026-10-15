"""Source-blind MOSS-Music pilot, pinned private weights and fixed local MLX code.

Output is an unverified lyric proposal, never gold text, a word clock, or a vote
for changing saved lyrics. The app's dependencies and model cache are untouched.
"""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import resource
import sys
import time
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path
from singing_asr_runtime import verify_runtime

MODEL_REPO = "mlx-community/MOSS-Music-8B-Thinking-4bit"
MODEL_REVISION = "b14123a419b6254b92d9e55b8a5b6f7285e05c70"
RUNTIME_COMMIT = "70f4add32911bab6f869b824864ad9f1e24dcb97"
PROMPT = "Transcribe the lyrics of this song."
DIRECT_PROMPT = (
    "<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n"
    "<|im_start|>user\n<|audio_bos|><|AUDIO|><|audio_eos|>\n"
    "Transcribe the lyrics with timestamps of this song.<|im_end|>\n"
    "<|im_start|>assistant\n<think>\n\n</think>\n\n"
)
KNOWN_ASSETS = {
    "model.safetensors": (
        6017835521,
        "17560d5e601103ec84981673692f69602ed78ffeea07b522d731649cc9711a44",
    ),
    "tokenizer.json": (
        11423404,
        "fe09df9d0df539ba3c7c8812750bda67907c889d0fbcc500454ba7037cc34466",
    ),
}

spec = importlib.util.spec_from_file_location(
    "blind_audio_runner", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)


def verify_assets(directory):
    """Strict local allowlist: no remote tokenizer/processor or missing layers."""
    receipt = json.loads((directory / "assets.json").read_text())
    pinned = json.loads((ROOT / "scripts/moss-model-files.json").read_text())
    if any(
        receipt[key] != pinned[key]
        for key in (
            "repo",
            "revision",
            "runtime_commit",
            "runtime_archive_sha256",
            "files",
        )
    ):
        raise ValueError("Research receipt differs from the reviewed asset manifest.")
    if (receipt["repo"], receipt["revision"], receipt["runtime_commit"]) != (
        MODEL_REPO,
        MODEL_REVISION,
        RUNTIME_COMMIT,
    ):
        raise ValueError("Changed singing ASR model/runtime revision.")
    actual = {p.name for p in (directory / "model").iterdir() if p.is_file()}
    if actual != set(receipt["files"]) or any(
        name.endswith(".py") or Path(name).name != name for name in actual
    ):
        raise ValueError("Unexpected model source or incomplete local snapshot.")
    for name, expected in receipt["files"].items():
        path = directory / "model" / name
        if (path.stat().st_size, digest(path)) != (
            expected["size"],
            expected["sha256"],
        ):
            raise ValueError("Changed singing ASR asset bytes.")
        if (
            name in KNOWN_ASSETS
            and (expected["size"], expected["sha256"]) != KNOWN_ASSETS[name]
        ):
            raise ValueError("Model/tokenizer differs from pinned LFS hash.")
    if not set(KNOWN_ASSETS) <= actual:
        raise ValueError("Missing singing ASR weights/tokenizer.")
    tokenizer = json.loads((directory / "model/tokenizer_config.json").read_text())
    if tokenizer.get("tokenizer_class") not in (
        "Qwen2Tokenizer",
        "Qwen2TokenizerFast",
    ) or tokenizer.get("auto_map"):
        raise ValueError("Custom tokenizer code is not allowed.")
    return {"assets": receipt, **verify_runtime(directory)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--asset-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-run", type=Path)
    parser.add_argument(
        "--prompt-mode",
        choices=("original", "timestamp-no-thinking"),
        default="original",
    )
    parser.add_argument("--max-tokens", type=int, choices=(256, 1024), default=1024)
    args = parser.parse_args()
    for name in vars(args):
        if isinstance(getattr(args, name), Path):
            setattr(args, name, private_path(getattr(args, name)))
    os.umask(0o077)
    os.environ.update(
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1"
    )
    cases = blind.manifest_cases(json.loads(args.manifest.read_text()))
    assets = verify_assets(args.asset_directory)
    sys.path[:0] = [
        str(args.asset_directory / "runtime"),
        str(args.asset_directory / "dependencies"),
    ]
    import mlx.core as mx
    from mlx_audio.stt import load

    mx.set_memory_limit(10 * 1024**3)
    mx.set_cache_limit(256 * 1024**2)
    recipe = {
        "manifest_sha256": digest(args.manifest),
        "assets": assets,
        "runner": digest(Path(__file__)),
        "audio_loader": digest(ROOT / "scripts/recognize-singing-phones.py"),
        "prompt": PROMPT if args.prompt_mode == "original" else DIRECT_PROMPT,
        "temperature": 0,
        "max_tokens": args.max_tokens,
        "prefill_step_size": 512,
        "strip_thinking": True,
        "enable_time_marker": True,
        "strict_weights": True,
        "evidence_role": "unverified source-blind lyric proposal; generated timestamps are not word clocks",
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("mlx", "transformers", "numpy")
        },
    }
    parent_sha = None
    if args.reuse_run:
        old = json.loads((args.reuse_run / "recipe.json").read_text())
        if any(old[k] != value for k, value in recipe.items() if k != "runner"):
            raise ValueError("Different prior singing recognition recipe.")
        parent_sha = digest(args.reuse_run / "recipe.json")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    blind.write(args.output / "recipe.json", recipe)
    recipe_sha, records, cache = digest(args.output / "recipe.json"), [], {}
    began = time.monotonic()
    model = load(args.asset_directory / "model", strict=True)
    load_seconds = time.monotonic() - began
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
    for number, case in enumerate(cases, 1):
        samples = blind.load_samples(case, args.manifest.parent, cache)
        if len(samples) > 16000 * 30:
            raise ValueError("Pilot is bounded to 30-second audio contexts.")
        filename = hashlib.sha256(case["id"].encode()).hexdigest() + ".json"
        previous = None
        if args.reuse_run and (args.reuse_run / filename).exists():
            previous = json.loads((args.reuse_run / filename).read_text())
            if (
                previous["case"] != case
                or previous["recipe_sha256"] != parent_sha
                or previous["crop_sha256"]
                != hashlib.sha256(samples.tobytes()).hexdigest()
            ):
                raise ValueError(
                    "Prior completed observation belongs to different audio."
                )
        if previous:
            row = {
                **previous,
                "recipe_sha256": recipe_sha,
                "reused_parent_record_sha256": digest(args.reuse_run / filename),
            }
        else:
            started = time.monotonic()
            result = model.generate(
                samples,
                prompt=recipe["prompt"],
                temperature=0,
                max_tokens=args.max_tokens,
                prefill_step_size=512,
                strip_thinking=True,
                enable_time_marker=True,
            )
            row = {
                "case": case,
                "recipe_sha256": recipe_sha,
                "crop_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
                "text": result.text,
                "segments": result.segments,
                "generation_tokens": result.generation_tokens,
                "token_budget_exhausted": result.generation_tokens >= args.max_tokens,
                "seconds": time.monotonic() - started,
                "process_peak_rss_bytes": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
                "mlx_peak_bytes": mx.get_peak_memory(),
            }
            del result
        blind.write(args.output / filename, row)
        records.append({"file": filename, "sha256": digest(args.output / filename)})
        mx.clear_cache()
        print(
            json.dumps(
                {
                    "completed": number,
                    "total": len(cases),
                    "seconds": row["seconds"],
                    "generation_tokens": row["generation_tokens"],
                    "mlx_peak_bytes": row["mlx_peak_bytes"],
                }
            ),
            flush=True,
        )
    blind.write(
        args.output / "complete.json",
        {
            "recipe_sha256": recipe_sha,
            "records": records,
            "load_seconds": load_seconds,
            "total_seconds": time.monotonic() - began,
        },
    )


if __name__ == "__main__":
    main()
