"""Private pinned-reference Kim vocals with original sample positions preserved.

Separation sees full original stereo audio only. Source text and human clocks are
unused. The derived audio-only manifest is suitable for blind recognition.
"""

import argparse
import importlib.metadata
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]


def main():
    import numpy as np
    from refinement_helper import separate, verify_assets

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--reference-assets", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.manifest, args.reference_assets, args.models, args.output = map(
        private_path, (args.manifest, args.reference_assets, args.models, args.output)
    )
    manifest = json.loads(args.manifest.read_text())
    pin = json.loads((ROOT / "scripts/jamendo-reference-files.json").read_text())
    binary = shutil.which("ffmpeg")
    if not binary:
        raise RuntimeError("Private fixture preparation requires installed FFmpeg.")
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    verify_assets(args.models)
    receipts = {}
    for case in manifest["cases"]:
        basename = case["song"]
        if basename in receipts:
            continue
        name = "mp3/" + basename + ".mp3"
        expected = next(a for a in pin["files"] if a["path"] == name)
        mp3 = args.reference_assets / name
        if (
            digest(mp3) != expected["sha256"]
            or digest(Path(case["audio"]["path"])) != case["audio"]["sha256"]
        ):
            raise ValueError("Original stereo or mono reference changed.")
        decoded = subprocess.run(
            [
                binary,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(mp3),
                "-f",
                "f32le",
                "-ar",
                "44100",
                "-ac",
                "2",
                "pipe:1",
            ],
            capture_output=True,
            check=True,
        ).stdout
        stereo = np.frombuffer(decoded, dtype="<f4").reshape(-1, 2).T
        length = Path(case["audio"]["path"]).stat().st_size // 4
        if (
            not np.isfinite(stereo).all()
            or abs(math.ceil(stereo.shape[1] * 160 / 441) - length) > 1
        ):
            raise ValueError("Stereo source does not preserve mono reference duration.")
        samples = separate(
            stereo, length, args.models, "Kim", args.output / "progress.json"
        )
        path = args.output / (basename + ".pcm")
        samples.astype("<f4").tofile(path)
        receipts[basename] = {
            "path": str(path),
            "sha256": digest(path),
            "original_mp3_sha256": expected["sha256"],
            "original_mono_sha256": case["audio"]["sha256"],
            "samples": len(samples),
        }
        print(json.dumps({"completed_songs": len(receipts)}), flush=True)
    cases = [
        {
            "id": c["id"] + ":kim",
            **c["audio"],
            "path": receipts[c["song"]]["path"],
            "sha256": receipts[c["song"]]["sha256"],
        }
        for c in manifest["cases"]
    ]
    (args.output / "audio-only.json").write_text(
        json.dumps({"version": 1, "cases": cases}, indent=2)
    )
    identity = {
        "manifest_sha256": digest(args.manifest),
        "runner_sha256": digest(Path(__file__)),
        "separator_sha256": digest(ROOT / "refinement/refinement_helper.py"),
        "model_manifest_sha256": digest(
            ROOT / "refinement/refinement-model-files.json"
        ),
        "ffmpeg_sha256": digest(Path(binary).resolve()),
        "versions": {
            name: importlib.metadata.version(name) for name in ("mlx", "numpy", "scipy")
        },
        "receipts": receipts,
        "audio_only_manifest_sha256": digest(args.output / "audio-only.json"),
        "original_clock_preserved": True,
    }
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2))


if __name__ == "__main__":
    main()
