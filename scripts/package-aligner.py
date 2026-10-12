"""Build the pinned native aligner and relocate its ARM64 libraries together."""

import os
import shutil
import subprocess
from pathlib import Path


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    root = Path(__file__).resolve().parent.parent
    source = root / ".cache/aligner-source/qwen3-asr.cpp"
    if not (source / "SOURCE.sha").is_file():
        raise SystemExit("Run python3 scripts/fetch-aligner-source.py first.")
    build = root / "aligner/build"
    # Exported dependencies have no .git; do not report our application's SHA.
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(source))
    run(
        "cmake",
        "-S",
        str(root / "aligner"),
        "-B",
        str(build),
        "-DCMAKE_BUILD_TYPE=Release",
        env=env,
    )
    run("cmake", "--build", str(build), "--target", "RomajiAligner", "-j", "4", env=env)
    destination = root / "dist/RomajiAligner"
    destination.mkdir(parents=True, exist_ok=True)
    names = ["RomajiAligner", "libqwen3-asr.dylib"] + [
        f"libggml{part}.0.dylib" for part in ("", "-base", "-cpu", "-blas", "-metal")
    ]
    for name in names:
        target = destination / name
        shutil.copy2(build / name, target)
        if target.suffix == ".dylib":
            run("/usr/bin/install_name_tool", "-id", f"@rpath/{name}", str(target))
        loads = run(
            "/usr/bin/otool", "-l", str(target), capture_output=True, text=True
        ).stdout.splitlines()
        for index, line in enumerate(loads):
            if line.strip() == "cmd LC_RPATH":
                path = loads[index + 2].strip().split("path ", 1)[1].split(" (", 1)[0]
                if path != "@loader_path":
                    run(
                        "/usr/bin/install_name_tool", "-delete_rpath", path, str(target)
                    )
        if "path @loader_path (" not in "\n".join(loads):
            run("/usr/bin/install_name_tool", "-add_rpath", "@loader_path", str(target))
        run("/usr/bin/codesign", "--force", "--sign", "-", str(target))
    run(
        str(destination / "RomajiAligner"),
        "--self-test",
        cwd="/private/tmp",
        env={"PATH": "/usr/bin:/bin"},
    )
    print("Bundled ARM64 aligner; model downloads on first use.")


if __name__ == "__main__":
    main()
