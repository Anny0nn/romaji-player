"""Collect private Google audio observations from a frozen WAV-only manifest.

Manifest: {version: 1, cases: [{id, path, sha256, origin_sample}]}.
Each file is an already exported mono 16 kHz PCM16 crop, at most 30 seconds.
No lyric text, source clocks or reference labels enter a request.
"""

import argparse
import io
import json
import os
import resource
import time
import wave
from pathlib import Path

from google_audio_api import (
    ENDPOINT,
    MODELS,
    candidates,
    digest,
    key_from_file,
    post,
    request_body,
    save,
    utc_now,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--timestamps", action="store_true")
    parser.add_argument("--free-project-confirmed", action="store_true", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    root = Path(__file__).resolve().parents[1]
    if args.output.resolve().is_relative_to(root):
        parser.error("Private results must remain outside the checkout.")
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    if set(manifest) != {"version", "cases"} or manifest["version"] != 1:
        parser.error("Expected an audio-only version-1 manifest.")
    if not 1 <= len(manifest["cases"]) <= 40:
        parser.error("A run is bounded to 40 crops and 1,200 seconds.")
    key = key_from_file(args.env_file)
    prepared, ids = [], set()
    for case in manifest["cases"]:
        if set(case) != {"id", "path", "sha256", "origin_sample"}:
            parser.error("Unexpected manifest fields.")
        if (
            not isinstance(case["id"], str)
            or not case["id"]
            or case["id"] in ids
            or type(case["origin_sample"]) is not int
            or case["origin_sample"] < 0
        ):
            parser.error("Invalid crop identity.")
        ids.add(case["id"])
        path = (args.manifest.parent / case["path"]).resolve()
        if path.stat().st_size > 1_000_000:
            parser.error("Oversized audio crop.")
        audio = path.read_bytes()
        if digest(audio) != case["sha256"]:
            parser.error("Changed audio bytes.")
        with wave.open(io.BytesIO(audio)) as wav:
            if (wav.getnchannels(), wav.getframerate(), wav.getsampwidth()) != (
                1,
                16000,
                2,
            ) or not 0 < wav.getnframes() <= 480000:
                parser.error("Expected mono 16 kHz PCM16, at most 30 seconds.")
            duration = wav.getnframes() / 16000
            if len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2:
                parser.error("Truncated audio data.")
        encoded = request_body(args.model, audio, timestamps=args.timestamps)
        prepared.append((case, encoded, duration))
    recipe = {
        "endpoint": ENDPOINT,
        "manifest_sha256": digest(manifest_bytes),
        "model": args.model,
        "timestamps": args.timestamps,
        "runner_sha256": digest(Path(__file__).read_bytes()),
        "transport_sha256": digest((root / "scripts/google_audio_api.py").read_bytes()),
        "requests": [digest(encoded) for _, encoded, _ in prepared],
        "max_attempts_per_case": 2,
    }
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.output.stat().st_mode & 0o077:
        parser.error("Output directory must have private permissions (0700).")
    receipt = args.output / "recipe.json"
    if receipt.exists():
        if json.loads(receipt.read_text()) != recipe:
            parser.error("Resume recipe identity changed.")
    else:
        save(receipt, recipe)
    for name in ("transcribe-google-audio.py", "google_audio_api.py"):
        source_copy = args.output / name
        original = (root / "scripts" / name).read_bytes()
        if source_copy.exists():
            if source_copy.read_bytes() != original:
                parser.error("Collector source snapshot changed.")
        else:
            fd = os.open(source_copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(original)
    for case, encoded, duration in prepared:
        target = args.output / (digest(case["id"].encode()) + ".json")
        if target.exists():
            cached = json.loads(target.read_text())
            if cached.get("case") != case or cached.get("request_sha256") != digest(
                encoded
            ):
                raise SystemExit("Cached observation identity changed.")
            if cached["status"] not in ("received", "invalid_or_incomplete_response"):
                raise SystemExit(
                    "Prior failed observation requires an explicit new trial."
                )
            continue
        began = time.monotonic()
        result = post(encoded, key)
        if result["status"] == "received":
            try:
                result["candidates"] = candidates(result["response"], duration)
            except (ValueError, TypeError, KeyError) as error:
                result["status"] = "invalid_or_incomplete_response"
                result["validation_error"] = str(error).replace(key, "[REDACTED]")[:200]
        save(
            target,
            {
                "case": case,
                "request_sha256": digest(encoded),
                "utc": utc_now(),
                "elapsed_seconds": time.monotonic() - began,
                "client_max_rss_platform_units": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
                **result,
            },
        )
        print(
            json.dumps({"status": result["status"], "completed": target.name}),
            flush=True,
        )
        if result["status"] not in ("received", "invalid_or_incomplete_response"):
            raise SystemExit(
                "Collection stopped; inspect private receipt before retry."
            )


if __name__ == "__main__":
    main()
