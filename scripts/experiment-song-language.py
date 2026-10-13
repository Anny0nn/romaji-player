"""Blind full-song Whisper language comparison on explicit private recordings.

Manifest: model_directory, songs [{id, pcm, audio_sha256}]. Audio is mono 16kHz
float32 LE (original or cached vocals). Outputs never alter app documents.
"""

import argparse
import hashlib
import json
import os
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa"), str(ROOT / "tifa/vendor")]


def main():
    import numpy as np
    from reading_repair import transcribe
    from refinement_helper import verify_assets

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--language", choices=["ja", "en", "auto"], required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT == output or ROOT in output.parents:
        parser.error("Private transcription output must be outside the checkout.")
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    output.chmod(0o700)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    manifest = args.manifest.resolve()
    data = json.loads(manifest.read_text())
    model = (manifest.parent / data["model_directory"]).resolve()
    verify_assets(model)
    provenance = {
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "model_manifest_sha256": hashlib.sha256(
            (ROOT / "refinement/refinement-model-files.json").read_bytes()
        ).hexdigest(),
        "decoder_sha256": hashlib.sha256(
            (ROOT / "refinement/reading_repair.py").read_bytes()
        ).hexdigest(),
    }
    for song in data["songs"]:
        # IDs are filenames as well as provenance; never allow path traversal.
        name = song["id"]
        if not name or not all(
            c.isascii() and (c.isalnum() or c in "-_") for c in name
        ):
            raise ValueError("Invalid recording ID.")
        pcm = (manifest.parent / song["pcm"]).resolve()
        with pcm.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != song["audio_sha256"] or pcm.stat().st_size % 4:
            raise ValueError("Recording bytes changed.")
        result_path = output / f"{name}.json"
        if result_path.exists():
            raise ValueError(
                "Use a fresh output directory; do not reuse another recipe."
            )
        samples = np.memmap(pcm, dtype="<f4", mode="r")
        if not 0 < len(samples) <= 600 * 16000 or not np.isfinite(samples).all():
            raise ValueError("Invalid recording samples.")
        diagnostics = {}
        started = time.monotonic()
        segments = transcribe(
            samples,
            model,
            output / "progress.txt",
            name,
            language=None if args.language == "auto" else args.language,
            diagnostics=diagnostics,
        )
        row = {
            **provenance,
            "id": name,
            "audio_sha256": digest,
            "language_setting": args.language,
            **diagnostics,
            "segments": segments,
            "seconds": time.monotonic() - started,
            # macOS reports bytes; this is the process lifetime peak, not song RAM.
            "process_peak_rss_bytes": resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss,
        }
        descriptor = os.open(result_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            json.dump(row, handle, ensure_ascii=False, allow_nan=False)
        # No transcript, private path or lyric text in the progress log.
        print(
            json.dumps({k: row[k] for k in ("id", "seconds", "detected_language")}),
            flush=True,
        )


if __name__ == "__main__":
    main()
