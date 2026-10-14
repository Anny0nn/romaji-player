"""Matched audio-only Whisper → bundled Cutlet → phones baseline, research only."""

import argparse
import hashlib
import importlib.util
import json
import os
import resource
import time
from pathlib import Path

from audio_first_models import ROOT, digest, kana_sequence_phones, verify

spec = importlib.util.spec_from_file_location(
    "blind_runner", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)


def main():
    import mlx.core as mx
    import mlx_whisper
    from g2p.converters.japanese import _KANA_TO_ROMAJI
    from mlx_whisper.transcribe import ModelHolder
    from reading_repair import Converter
    from singing_phonemes import kana_phones

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--romanizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output, manifest = args.output.resolve(), args.manifest.resolve()
    if ROOT in output.parents or ROOT in manifest.parents:
        parser.error("Private inputs/results must stay outside the checkout.")
    cases = blind.manifest_cases(json.loads(manifest.read_text()))
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.umask(0o077)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    assets = [
        a
        for a in json.loads(
            (ROOT / "refinement/refinement-model-files.json").read_text()
        )
        if a["path"].startswith("whisper/")
    ]
    for asset in assets:
        verify(args.models / asset["path"], asset["sha256"])
    started = time.monotonic()
    converter = Converter(args.romanizer.resolve())
    inventory = sorted(
        {
            p
            for k in _KANA_TO_ROMAJI
            for p in kana_sequence_phones(k)
            if not p.startswith("unsupported:")
        }
        | {"N"}
    )
    recipe = {
        "engine": "whisper",
        "manifest_sha256": digest(manifest),
        "model": {
            "assets": assets,
            "heads": {"whisper": {p: n for n, p in enumerate(inventory)}},
        },
        "conversion_signature": converter.signature,
        "romanizer_sha256": digest(args.romanizer),
        "implementation": {
            p.name: digest(p)
            for p in [
                Path(__file__),
                ROOT / "scripts/audio_first_models.py",
                ROOT / "scripts/recognize-singing-phones.py",
            ]
        },
        "decoder": {
            "greedy_only": True,
            "language": "ja",
            "temperature": 0,
            "condition_on_previous_text": False,
            "initial_prompt": None,
            "word_timestamps": True,
        },
    }
    blind.write(output / "recipe.json", recipe)
    recipe_sha = digest(output / "recipe.json")
    mx.set_memory_limit(10 * 1024**3)
    mx.set_cache_limit(512 * 1024**2)
    cache, complete = {}, []
    try:
        for number, case in enumerate(cases, 1):
            samples = blind.load_samples(case, manifest.parent, cache)
            begin = time.monotonic()
            value = mlx_whisper.transcribe(
                samples,
                path_or_hf_repo=str(args.models / "whisper"),
                language="ja",
                task="transcribe",
                temperature=0.0,
                condition_on_previous_text=False,
                initial_prompt=None,
                verbose=None,
                word_timestamps=True,
            )
            inference_seconds = time.monotonic() - begin
            stem = hashlib.sha256(case["id"].encode()).hexdigest()
            # Persist the raw audio-only text before dictionary conversion is invoked.
            blind.write(output / f"{stem}-transcript.json", {"text": value["text"]})
            response = converter.convert(
                {
                    "protocol_version": 2,
                    "command": "convert",
                    "request_id": number,
                    "track_id": "blind-transcript",
                    "snapshot_id": case["sha256"],
                    "occurrence_id": 0,
                    "override_revision": 0,
                    "expected_conversion_signature": converter.signature,
                    "raw_line": value["text"].replace("\n", " ").strip(),
                    "overrides": [],
                }
            )
            phones = []
            for word in response["words"]:
                span = word["hiragana_span"]
                if span is None:
                    phones.append("unsupported:unmapped-word")
                    continue
                kana = response["hiragana"].encode()[span[0] : span[1]].decode()
                roman = (
                    response["romaji"]
                    .encode()[word["output_span"][0] : word["output_span"][1]]
                    .decode()
                )
                phones.extend(kana_phones(kana, roman) or ["unsupported:word"])
            row = {
                "case": case,
                "resampled_crop_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
                "recipe_sha256": recipe_sha,
                "transcript": f"{stem}-transcript.json",
                "transcript_sha256": digest(output / f"{stem}-transcript.json"),
                "failure": None,
                "heads": {"whisper": {"greedy": {"phones": phones}, "nbest": []}},
                "inference_seconds": inference_seconds,
                "decode_and_write_seconds": time.monotonic()
                - begin
                - inference_seconds,
                "process_lifetime_peak_rss_bytes": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
                "mlx_active_bytes_sample": mx.get_active_memory(),
                "mlx_peak_bytes": mx.get_peak_memory(),
            }
            blind.write(output / f"{stem}.json", row)
            complete.append(
                {"file": f"{stem}.json", "sha256": digest(output / f"{stem}.json")}
            )
            print(json.dumps({"completed": number, "total": len(cases)}), flush=True)
    finally:
        converter.close()
        ModelHolder.model = ModelHolder.model_path = None
        mx.clear_cache()
    blind.write(
        output / "complete.json",
        {
            "recipe_sha256": recipe_sha,
            "records": complete,
            "total_seconds": time.monotonic() - started,
        },
    )


if __name__ == "__main__":
    main()
