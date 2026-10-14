"""Verify the distribution zip, including the Rust-to-bundled-helper boundary."""

import json
import os
import plistlib
import re
import subprocess
import tempfile
from pathlib import Path


def main():
    archive = Path("dist/RomajiPlayer.zip").resolve()
    # Compare public build inputs without printing them or reading other .env keys.
    expected = os.environ.get("SPOTIFY_CLIENT_ID", "")
    if not expected and Path(".env").is_file():
        for line in Path(".env").read_text().splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "SPOTIFY_CLIENT_ID":
                expected = value.strip().strip("\"'")
    if not re.fullmatch(r"[a-fA-F0-9]{32}", expected):
        raise SystemExit(
            "Set the expected public SPOTIFY_CLIENT_ID before checking the app."
        )

    with tempfile.TemporaryDirectory(
        prefix="Romaji distribution with spaces "
    ) as scratch:
        subprocess.run(
            ["/usr/bin/ditto", "-x", "-k", str(archive), scratch], check=True
        )
        app = Path(scratch) / "RomajiPlayer.app"
        contents = app / "Contents"
        metadata = plistlib.loads((contents / "Info.plist").read_bytes())
        assert metadata["CFBundleIdentifier"] == "io.github.Anny0nn.RomajiPlayer"
        assert metadata["LSMinimumSystemVersion"] == "15.0"
        executable = contents / "MacOS" / metadata["CFBundleExecutable"]
        subprocess.run(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)],
            check=True,
        )
        architecture = subprocess.run(
            ["/usr/bin/file", str(executable)],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "arm64" in architecture.stdout
        files = [path for path in app.rglob("*") if path.is_file()]
        assert not any(
            path.name in {".env", "credentials.json", "token.json", "settings.json"}
            or path.suffix in {".log", ".cookie"}
            for path in files
        )
        # Absolute library loads must be macOS system libraries. Runtime resources
        # are inside the signed bundle; developer Homebrew paths are not usable.
        binaries = [executable, contents / "Resources/RomajiRomanizer/RomajiRomanizer"]
        aligner = contents / "Resources/RomajiAligner/RomajiAligner"
        binaries.append(aligner)
        tifa = contents / "Resources/RomajiTIFA/RomajiTIFA"
        binaries.append(tifa)
        experimental = contents / "Resources/RomajiExperimental/RomajiExperimental"
        binaries.append(experimental)
        binaries.extend(path for path in files if path.suffix in {".so", ".dylib"})
        binaries.extend(path for path in files if path.name == "Python")
        for binary in set(binaries):
            linked = subprocess.run(
                ["/usr/bin/otool", "-L", str(binary)],
                capture_output=True,
                text=True,
                check=True,
            )
            for line in linked.stdout.splitlines()[1:]:
                library = line.strip().split(" (", 1)[0]
                assert library.startswith(("@", "/usr/lib/", "/System/Library/")), (
                    library
                )

        def run(flag):
            result = subprocess.run(
                [str(executable), flag],
                capture_output=True,
                text=True,
                check=True,
                timeout=20,
                cwd=scratch,
                env={"PATH": "/usr/bin:/bin"},
            )
            assert not result.stderr
            return json.loads(result.stdout)

        public = run("--public-config")
        assert public["client_id"] == expected
        assert public["redirect_uri"] == "http://127.0.0.1:8989/login"
        assert public["bundle_id"] == metadata["CFBundleIdentifier"]
        conversion = run("--check-romaji")
        aligned = subprocess.run(
            [str(aligner), "--self-test"],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
            cwd=scratch,
            env={"PATH": "/usr/bin:/bin"},
        )
        assert json.loads(aligned.stdout) == {"protocol": 2, "self_test": True}
        timing = subprocess.run(
            [str(tifa), "--self-test"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
            cwd=scratch,
            env={"PATH": "/usr/bin:/bin"},
        )
        assert json.loads(timing.stdout) == {
            "protocol": 3,
            "self_test": True,
            "device": "mps",
        }
        refined = subprocess.run(
            [str(experimental), "--self-test"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
            cwd=scratch,
            env={"PATH": "/usr/bin:/bin"},
        )
        assert json.loads(refined.stdout) == {
            "protocol": 3,
            "self_test": True,
            "device": "mps+mlx",
        }
        checked = subprocess.run(
            [
                str(experimental),
                "--check-converter",
                str(contents / "Resources/RomajiRomanizer/RomajiRomanizer"),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
            cwd=scratch,
            env={"PATH": "/usr/bin:/bin"},
        )
        assert json.loads(checked.stdout) == {"protocol": 1, "converter_check": True}

        assert conversion == {
            "romaji": "ga tabeta o",
            "hiragana": "が たべた を",
            "katakana": "ガ タベタ ヲ",
            "raw_spans": [[0, 6], [7, 16], [17, 20]],
        }
        notices = contents / "Resources/Notices"
        assert (notices / "Spotifast-MIT.txt").is_file()
        assert (notices / "Python-LICENSE.txt").is_file()
        assert (notices / "QwenCPP-MIT.txt").is_file()
        assert (notices / "GGML-MIT.txt").is_file()
        assert (notices / "QwenModel-Apache-2.0.txt").is_file()
        assert (notices / "TIFA-MIT.txt").is_file()
        assert (notices / "TIFA-Model-CC-BY-NC-SA-4.0.txt").is_file()
        assert (notices / "CMUdict-LICENSE.txt").is_file()
        assert (notices / "LstmG2p-Apache-2.0.txt").is_file()
        assert (notices / "TIFA-ATTRIBUTION.txt").is_file()
        assert any(
            entry["package"] == "torch" and entry["notices"]
            for entry in json.loads((notices / "TIFAPython/index.json").read_text())
        )
        assert (notices / "ExperimentalModels.txt").is_file()
        assert any(
            entry["package"] == "mlx-audio" and entry["notices"]
            for entry in json.loads(
                (notices / "ExperimentalPython/index.json").read_text()
            )
        )
        assert len(json.loads((notices / "Rust/index.json").read_text())) > 100
        assert any(path.name == "LICENSE.unidic" for path in files)
    print(
        "App zip passed: ARM64, signed resources, personal configuration, bundled conversion, notices, clean environment and path with spaces."
    )


if __name__ == "__main__":
    main()
