"""Reject local credentials, agent configuration and generated artifacts in git."""

import subprocess
from pathlib import PurePosixPath

LOCAL_DIRECTORIES = {
    ".agents",
    ".claude",
    ".codex",
    ".cache",
    ".venv",
    ".venv-tifa",
    ".venv-experimental",
    "__pycache__",
    "target",
    "dist",
    "build",
}
LOCAL_FILES = {"AGENTS.md", "CLAUDE.md", ".DS_Store"}
MODEL_SUFFIXES = {".safetensors", ".gguf", ".ckpt", ".pth", ".onnx"}


def forbidden(path):
    item = PurePosixPath(path)
    return (
        any(part in LOCAL_DIRECTORIES for part in item.parts)
        or item.name in LOCAL_FILES
        or (item.name.startswith(".env") and item.name != ".env.example")
        or item.suffix in MODEL_SUFFIXES
        or item.parts[0] == "data"
    )


def git(*args):
    return subprocess.check_output(["git", *args]).decode().split("\0")


def main():
    rejected = set()
    for entry in git("ls-files", "--stage", "-z"):
        if not entry:
            continue
        metadata, path = entry.split("\t", 1)
        mode, _, stage = metadata.split()
        if forbidden(path) or mode == "120000" or stage != "0":
            rejected.add(path)
    # Check every outgoing commit, so deleting a local file later cannot hide a leak.
    commits = (
        subprocess.check_output(["git", "rev-list", "origin/main..HEAD"])
        .decode()
        .splitlines()
    )
    for commit in commits:
        for path in git(
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "--diff-filter=AM",
            "-r",
            "-z",
            commit,
        ):
            if path and forbidden(path):
                rejected.add(path)
    if rejected:
        raise SystemExit(
            "Local-only files found in git: " + ", ".join(sorted(rejected))
        )
    print("Export paths and outgoing history contain no local-only files.")


if __name__ == "__main__":
    main()
