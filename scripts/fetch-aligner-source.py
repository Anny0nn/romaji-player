"""Export pinned alignment dependencies, excluding their repository instructions."""

import subprocess
import tarfile
import tempfile
from pathlib import Path

PIN = "6dcc586e5073fd6e85ee5728e75f0903d6c70c6c"
GGML = "9be313313c8ecb9488911bd64550190e3ed80f38"


def export(repo, revision, destination, paths=()):
    with tempfile.TemporaryDirectory(prefix="Romaji aligner source ") as scratch:
        checkout = Path(scratch) / "source.git"
        subprocess.run(
            ["git", "init", "--bare", str(checkout)], check=True, capture_output=True
        )
        subprocess.run(
            [
                "git",
                "--git-dir",
                str(checkout),
                "fetch",
                "--depth",
                "1",
                repo,
                revision,
            ],
            check=True,
        )
        archive = Path(scratch) / "source.tar"
        subprocess.run(
            [
                "git",
                "--git-dir",
                str(checkout),
                "archive",
                "--output",
                str(archive),
                revision,
                *paths,
            ],
            check=True,
        )
        destination.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as source:
            members = [
                member
                for member in source.getmembers()
                if Path(member.name).name not in {"AGENTS.md", "CLAUDE.md"}
                and not any(
                    part in {".agents", ".claude", ".codex", ".github"}
                    for part in Path(member.name).parts
                )
            ]
            source.extractall(destination, members=members, filter="data")
        (destination / "SOURCE.sha").write_text(revision + "\n")


def main():
    root = (
        Path(__file__).resolve().parent.parent / ".cache/aligner-source/qwen3-asr.cpp"
    )
    export(
        "https://github.com/predict-woo/qwen3-asr.cpp.git",
        PIN,
        root,
        ("CMakeLists.txt", "LICENSE", "src", "include", "cli", "third_party"),
    )
    export("https://github.com/ggml-org/ggml.git", GGML, root / "ggml")
    # Keep raw model predictions: no missing-time defaults, interpolation or clamping.
    path = root / "src/forced_aligner.cpp"
    source = path.read_text()
    old = "    std::vector<int32_t> fixed_classes = fix_timestamp_classes(timestamp_classes);\n    \n    std::vector<float> timestamps = classes_to_timestamps(fixed_classes);\n    \n    for (size_t i = 0; i < timestamps.size(); ++i) {\n        if (timestamps[i] > audio_duration) {\n            timestamps[i] = audio_duration;\n        }\n    }\n"
    new = """    if (timestamp_classes.size() != words.size() * 2) {
        result.error_msg = "Incomplete model timestamps";
        return result;
    }
    std::vector<float> timestamps = classes_to_timestamps(timestamp_classes);
"""
    if source.count(old) != 1:
        raise RuntimeError("Pinned aligner timestamp adapter no longer matches")
    path.write_text(source.replace(old, new))
    print(
        "Exported pinned Qwen/GGML source without upstream instructions; raw timestamps enabled."
    )


if __name__ == "__main__":
    main()
