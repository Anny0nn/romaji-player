"""Explicit private capture using an immutable helper, without rebuilding it.

Keep dist/RomajiCapture/{record_alignment_acceptance,sha256} from a helper
already authorized by the maintainer. Never download credentials or change ACLs.
"""

import argparse
import hashlib
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def track_ids(values):
    if (
        not values
        or len(set(values)) != len(values)
        or any(not re.fullmatch(r"[A-Za-z0-9]{22}", value) for value in values)
    ):
        raise ValueError("Provide unique Spotify track IDs, not URLs or paths.")
    return values


def authorized_helper(folder):
    executable = folder / "record_alignment_acceptance"
    digest = (folder / "sha256").read_text().strip()
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Invalid preserved-helper fingerprint.")
    with executable.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != digest or not os.access(executable, os.X_OK):
        raise ValueError(
            "The authorized capture helper changed; do not rebuild it to retry."
        )
    return executable


def capture(output, tracks, helper):
    output = output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError(
            "Keep commercial recordings and lyrics outside the repository."
        )
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.stat().st_mode & 0o077:
        raise ValueError("The recording directory must be private (chmod 700).")
    # Pass IDs explicitly: the suite can grow without recompiling signed code.
    subprocess.run(
        [str(helper), str(output), "--stereo", *track_ids(tracks)], check=True
    )


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("tracks", nargs="+")
    args = parser.parse_args()
    tracks = args.tracks
    try:
        helper = authorized_helper(ROOT / "dist/RomajiCapture")
        capture(args.output, tracks, helper)
    except (FileNotFoundError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
