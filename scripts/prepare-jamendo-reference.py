"""Collect two pinned CC BY singing references outside git for private calibration.

All selected examples are development, not a new heldout accuracy claim. Lyrics are
normalized corpus text, not original orthography. Neither audio nor text is published.
"""

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path
from jamendo_reference import word_lines


def main():
    import numpy as np

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--lines-per-song", type=int, default=8)
    args = parser.parse_args()
    args.assets, args.output = map(private_path, (args.assets, args.output))
    if not 1 <= args.lines_per_song <= 12:
        parser.error(
            "development pilot is bounded to 1–12 first eligible lines per song"
        )
    binary = shutil.which("ffmpeg")
    if not binary:
        raise RuntimeError("Private reference preparation requires installed FFmpeg.")
    os.umask(0o077)
    pin_path = Path(__file__).with_name("jamendo-reference-files.json")
    pin = json.loads(pin_path.read_text())
    for row in pin["files"]:
        path = args.assets / row["path"]
        if not path.exists() and args.download:
            path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            with (
                urllib.request.urlopen(row["url"], timeout=60) as source,
                path.open("xb") as output,
            ):
                shutil.copyfileobj(source, output)
        if (
            not path.is_file()
            or path.stat().st_size != row["size"]
            or digest(path) != row["sha256"]
        ):
            raise ValueError("Reference artifact differs from pinned source.")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    cases = []
    for basename in ("Cortez_-_Feel__Stripped_", "Rxbyn_-_Bad_Side"):
        decoded = subprocess.run(
            [
                binary,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(args.assets / "mp3" / (basename + ".mp3")),
                "-f",
                "f32le",
                "-ar",
                "16000",
                "-ac",
                "1",
                "pipe:1",
            ],
            capture_output=True,
            check=True,
        ).stdout
        samples = np.frombuffer(decoded, dtype="<f4")
        if not len(samples) or not np.isfinite(samples).all():
            raise ValueError("Invalid original reference audio.")
        pcm = args.output / (basename + ".pcm")
        pcm.write_bytes(decoded)
        lines = word_lines(
            (args.assets / "lyrics" / (basename + ".words.txt")).read_text(),
            (args.assets / "annotations/words" / (basename + ".csv")).read_text(),
        )
        selected = [
            (i, line) for i, line in enumerate(lines) if 3 <= len(line["targets"]) <= 15
        ][: args.lines_per_song]
        for number, line in selected:
            first = max(0, math.floor(line["reference"][0]["start_ms"] * 16) - 8000)
            last = min(len(samples), math.ceil(line["line_end_ms"] * 16) + 4800)
            if not first < last or last - first > 480000:
                raise ValueError("Reference line exceeds bounded original crop.")
            cases.append(
                {
                    "id": basename + ":" + str(number),
                    "song": basename,
                    "partition": "development",
                    "language": "en",
                    "audio": {
                        "path": str(pcm),
                        "sha256": digest(pcm),
                        "encoding": "pcm",
                        "first_sample": first,
                        "last_sample": last,
                    },
                    "raw_line": line["raw_line"],
                    "targets": line["targets"],
                    "reference": [
                        {
                            **u,
                            "start_ms": u["start_ms"] - first / 16,
                            "end_ms": u["end_ms"] - first / 16,
                        }
                        for u in line["reference"]
                    ],
                }
            )
    identity = {
        "assets": digest(pin_path),
        "runner": digest(Path(__file__)),
        "parser": digest(ROOT / "scripts/jamendo_reference.py"),
        "ffmpeg": digest(Path(binary).resolve()),
        "lines_per_song": args.lines_per_song,
        "partition": "development",
        "attribution": pin["attribution"],
        "normalization": "exact original word transcript, joined with ASCII spaces",
    }
    manifest = {"identity": identity, "cases": cases}
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False)
    )
    print(
        json.dumps(
            {
                "cases": len(cases),
                "reference_words": sum(len(c["targets"]) for c in cases),
                "manifest_sha256": hashlib.sha256(
                    (args.output / "manifest.json").read_bytes()
                ).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
