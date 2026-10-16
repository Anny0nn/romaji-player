"""Fetch pinned MOSS/MLX research assets outside Git; never alter the app runtime.

Dependency wheels are pinned for this project's Apple Silicon Python 3.14 runtime.
This is an explicit network bootstrap; recognition subsequently runs fully offline.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path

MANIFEST = ROOT / "scripts/moss-model-files.json"


def fetch(path, url, expected):
    if not path.exists():
        partial = path.with_suffix(path.suffix + ".partial")
        with (
            urllib.request.urlopen(url, timeout=120) as source,
            partial.open("wb") as target,
        ):
            while chunk := source.read(4 * 1024 * 1024):
                target.write(chunk)
        if digest(partial) != expected:
            raise ValueError("Downloaded research artifact differs from pinned hash.")
        partial.rename(path)
    elif digest(path) != expected:
        raise ValueError("Existing research artifact differs from pinned hash.")


def extract_runtime(archive, directory, commit):
    """Extract only regular files with a fixed root and no links/path traversal."""
    with tarfile.open(archive) as source:
        for member in source:
            parts = Path(member.name).parts
            if not parts or parts[0] != "mlx-audio-" + commit or ".." in parts:
                raise ValueError("Unsafe pinned runtime archive path.")
            relative = Path(*parts[1:])
            if member.issym() or member.islnk() or relative.is_absolute():
                raise ValueError("Links are not permitted in the runtime archive.")
            if not member.isfile():
                continue
            path = directory / relative
            contents = source.extractfile(member).read()
            if path.exists():
                if (
                    hashlib.sha256(path.read_bytes()).digest()
                    != hashlib.sha256(contents).digest()
                ):
                    raise ValueError("Changed existing pinned runtime source.")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine", choices=("moss", "parakeet"), default="moss")
    args = parser.parse_args()
    root = private_path(args.output)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.umask(0o077)
    manifest = (
        MANIFEST
        if args.engine == "moss"
        else ROOT / "scripts/parakeet-model-files.json"
    )
    assets = json.loads(manifest.read_text())
    model = root / "model"
    model.mkdir(exist_ok=True)
    for name, row in assets["files"].items():
        fetch(
            model / name,
            f"https://huggingface.co/{assets['repo']}/resolve/{assets['revision']}/{name}",
            row["sha256"],
        )
        if (model / name).stat().st_size != row["size"]:
            raise ValueError("Wrong research model asset size.")
        print(json.dumps({"verified": name}), flush=True)
    archive = root / "runtime.tar.gz"
    fetch(
        archive,
        f"https://codeload.github.com/{assets['runtime_repo']}/tar.gz/{assets['runtime_commit']}",
        assets["runtime_archive_sha256"],
    )
    extract_runtime(archive, root / "runtime", assets["runtime_commit"])
    wheels = root / "wheels"
    wheels.mkdir(exist_ok=True)
    if not all((wheels / name).exists() for name in assets["wheel_sha256"]):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                "--no-deps",
                "--dest",
                str(wheels),
                *[
                    f"{name}=={version}"
                    for name, version in assets["dependencies"].items()
                ],
            ],
            check=True,
        )
    for name, sha in assets["wheel_sha256"].items():
        if digest(wheels / name) != sha:
            raise ValueError(
                "Dependency wheel differs from the pinned Apple Silicon build."
            )
    dependencies = root / "dependencies"
    if not dependencies.exists():
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--target",
                str(dependencies),
                *[str(wheels / name) for name in assets["wheel_sha256"]],
            ],
            check=True,
        )
    receipt = root / "assets.json"
    if receipt.exists():
        old = json.loads(receipt.read_text())
        if any(
            old[k] != assets[k]
            for k in (
                "repo",
                "revision",
                "runtime_commit",
                "runtime_archive_sha256",
                "files",
            )
        ):
            raise ValueError("Different previous research asset receipt.")
    else:
        receipt.write_text(json.dumps(assets, indent=2))
    print(json.dumps({"verified": True, "app_runtime_changed": False}))


if __name__ == "__main__":
    main()
