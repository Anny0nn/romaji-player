"""Private source-blind tempo/pitch pilots; transformed clocks cannot be saved.

Use recognized text only. All boundary verification must return to original audio.
FFmpeg is a research prerequisite, never a new shipped application dependency.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path

PROFILES = {
    "tempo075": "atempo=0.75",
    "pitch-down-four": "asetrate=12699,aresample=16000,atempo=1.2599210498948732",
}
spec = importlib.util.spec_from_file_location(
    "blind_audio_runner", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.manifest, args.output = map(private_path, (args.manifest, args.output))
    cases = blind.manifest_cases(json.loads(args.manifest.read_text()))
    binary = shutil.which("ffmpeg")
    if not binary:
        raise RuntimeError("This private pilot requires an installed FFmpeg.")
    import numpy as np

    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    signature = {
        "source_manifest": digest(args.manifest),
        "runner": digest(Path(__file__)),
        "ffmpeg_binary": digest(Path(binary).resolve()),
        "profiles": PROFILES,
        "sample_rate": 16000,
        "evidence_role": "text-only; transformed timestamps cannot support saved timing",
    }
    blind.write(args.output / "identity.json", signature)
    cache = {}
    output = []
    receipts = []
    for case in cases:
        samples = blind.load_samples(case, args.manifest.parent, cache)
        for profile, chain in PROFILES.items():
            result = subprocess.run(
                [
                    binary,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "f32le",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-i",
                    "pipe:0",
                    "-af",
                    chain,
                    "-f",
                    "f32le",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "pipe:1",
                ],
                input=samples.astype("<f4").tobytes(),
                capture_output=True,
                check=True,
            )
            audio = np.frombuffer(result.stdout, dtype="<f4")
            if not len(audio) or not np.isfinite(audio).all():
                raise ValueError("Invalid transformed recognition waveform.")
            ident = case["id"] + ":" + profile
            name = hashlib.sha256(ident.encode()).hexdigest() + ".pcm"
            path = args.output / name
            with path.open("xb") as handle:
                handle.write(result.stdout)
            output.append(
                {
                    "id": ident,
                    "path": str(path),
                    "sha256": digest(path),
                    "encoding": "pcm",
                    "first_sample": 0,
                    "last_sample": len(audio),
                }
            )
            receipts.append(
                {
                    "case": case,
                    "original_crop_sha256": hashlib.sha256(
                        samples.tobytes()
                    ).hexdigest(),
                    "profile": profile,
                    "derived_case": output[-1],
                    "timestamps_usable": False,
                }
            )
    blind.write(args.output / "audio-only.json", {"version": 1, "cases": output})
    blind.write(
        args.output / "private-origins.json",
        {"identity_sha256": digest(args.output / "identity.json"), "records": receipts},
    )
    print(
        json.dumps(
            {
                "cases": len(output),
                "source_cases": len(cases),
                "original_audio_changed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
