"""Audio-only local Whisper word timestamps for a nominated crop manifest."""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import resource
import time
from pathlib import Path

from audio_first_models import ROOT, digest, verify

spec = importlib.util.spec_from_file_location(
    "blind_runner", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)


def finite_json(value):
    """Undefined model statistics/timestamps stay undefined, never become zero."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: finite_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [finite_json(item) for item in value]
    return value


def main():
    import mlx.core as mx
    import mlx_whisper
    from mlx_whisper.transcribe import ModelHolder

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--language", choices=("en", "ja"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-run", type=Path)
    args = parser.parse_args()
    if ROOT in args.output.resolve().parents:
        parser.error("Private audio/text results stay outside the checkout.")
    cases = blind.manifest_cases(json.loads(args.manifest.read_text()))
    assets = [
        a
        for a in json.loads(
            (ROOT / "refinement/refinement-model-files.json").read_text()
        )
        if a["path"].startswith("whisper/")
    ]
    for asset in assets:
        verify(args.models / asset["path"], asset["sha256"])
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    mx.set_memory_limit(10 * 1024**3)
    mx.set_cache_limit(512 * 1024**2)
    recipe = {
        "manifest_sha256": digest(args.manifest),
        "model_assets": assets,
        "implementation_sha256": digest(Path(__file__)),
        "language": args.language,
        "temperature": 0,
        "condition_on_previous_text": False,
        "initial_prompt": None,
        "word_timestamps": True,
        "nonfinite_contract": "undefined statistics and word observations become null; no invented times",
    }
    parent_sha = None
    if args.reuse_run:
        parent = json.loads((args.reuse_run / "recipe.json").read_text())
        if any(
            parent[k] != recipe[k]
            for k in (
                "manifest_sha256",
                "model_assets",
                "language",
                "temperature",
                "condition_on_previous_text",
                "initial_prompt",
                "word_timestamps",
            )
        ):
            raise ValueError("Prior run belongs to another recording or decoder.")
        parent_sha = digest(args.reuse_run / "recipe.json")
        recipe["recovered_parent_recipe_sha256"] = parent_sha
    blind.write(args.output / "recipe.json", recipe)
    recipe_sha, began, cache, records = (
        digest(args.output / "recipe.json"),
        time.monotonic(),
        {},
        [],
    )
    try:
        for number, case in enumerate(cases, 1):
            samples = blind.load_samples(case, args.manifest.parent, cache)
            filename = hashlib.sha256(case["id"].encode()).hexdigest() + ".json"
            previous = None
            if args.reuse_run and (args.reuse_run / filename).is_file():
                try:
                    previous = json.loads((args.reuse_run / filename).read_text())
                except json.JSONDecodeError:
                    pass  # An interrupted write is not a successful observation.
            if previous is not None:
                if (
                    previous["case"] != case
                    or previous["recipe_sha256"] != parent_sha
                    or previous["crop_sha256"]
                    != hashlib.sha256(samples.tobytes()).hexdigest()
                ):
                    raise ValueError(
                        "Recovered word observations have another audio identity."
                    )
                row = {
                    **finite_json(previous),
                    "recipe_sha256": recipe_sha,
                    "recovered_parent_record_sha256": digest(args.reuse_run / filename),
                }
                blind.write(args.output / filename, row)
                records.append(
                    {"file": filename, "sha256": digest(args.output / filename)}
                )
                continue
            start = time.monotonic()
            value = mlx_whisper.transcribe(
                samples,
                path_or_hf_repo=str(args.models / "whisper"),
                language=args.language,
                task="transcribe",
                temperature=0.0,
                condition_on_previous_text=False,
                initial_prompt=None,
                verbose=None,
                word_timestamps=True,
            )
            row = {
                "case": case,
                "recipe_sha256": recipe_sha,
                "crop_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
                "segments": finite_json(value["segments"]),
                "seconds": time.monotonic() - start,
                "process_peak_rss_bytes": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
                "mlx_peak_bytes": mx.get_peak_memory(),
            }
            blind.write(args.output / filename, row)
            records.append({"file": filename, "sha256": digest(args.output / filename)})
            print(json.dumps({"completed": number, "total": len(cases)}), flush=True)
    finally:
        ModelHolder.model = ModelHolder.model_path = None
        mx.clear_cache()
    blind.write(
        args.output / "complete.json",
        {
            "recipe_sha256": recipe_sha,
            "records": records,
            "total_seconds": time.monotonic() - began,
        },
    )


if __name__ == "__main__":
    main()
