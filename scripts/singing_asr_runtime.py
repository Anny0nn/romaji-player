"""Shared pinned MLX source and dependency verification for blind ASR pilots."""

import hashlib
import json
from pathlib import Path

from hubertfa_research import ROOT, digest

RUNTIME_COMMIT = "70f4add32911bab6f869b824864ad9f1e24dcb97"


def verify_runtime(directory):
    pinned = json.loads((ROOT / "scripts/moss-model-files.json").read_text())
    if digest(directory / "runtime.tar.gz") != pinned["runtime_archive_sha256"]:
        raise ValueError("Changed pinned runtime archive.")
    # Compare every installed Python source with the immutable pinned archive.
    import tarfile

    expected_sources = {}
    with tarfile.open(directory / "runtime.tar.gz") as archive:
        for member in archive:
            parts = Path(member.name).parts
            if parts[0] != "mlx-audio-" + RUNTIME_COMMIT or ".." in parts:
                raise ValueError("Unsafe pinned runtime archive path.")
            relative = Path(*parts[1:])
            if member.isfile() and relative.suffix == ".py":
                expected_sources[str(relative)] = hashlib.sha256(
                    archive.extractfile(member).read()
                ).hexdigest()
    installed = {
        str(p.relative_to(directory / "runtime"))
        for p in (directory / "runtime").rglob("*.py")
    }
    if installed != set(expected_sources) or any(
        digest(directory / "runtime" / name) != sha
        for name, sha in expected_sources.items()
    ):
        raise ValueError("Installed runtime differs from pinned source.")
    wheels = {p.name: digest(p) for p in (directory / "wheels").glob("*.whl")}
    if wheels != pinned["wheel_sha256"]:
        raise ValueError("Missing isolated runtime dependency wheels.")
    return {
        "runtime_sources": expected_sources,
        "dependency_wheels": wheels,
    }
