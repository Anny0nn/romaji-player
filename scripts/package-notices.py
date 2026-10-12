"""Retain license notices from locked Rust packages in the distributed app."""

import json
import shutil
import subprocess
from pathlib import Path


def main():
    metadata = subprocess.run(
        [
            "cargo",
            "metadata",
            "--manifest-path",
            "Cargo.toml",
            "--locked",
            "--offline",
            "--no-default-features",
            "--filter-platform",
            "aarch64-apple-darwin",
            "--format-version",
            "1",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    destination = Path("dist/RomajiPlayer.app/Contents/Resources/Notices/Rust")
    destination.mkdir(parents=True, exist_ok=True)
    index = []
    for package in json.loads(metadata.stdout)["packages"]:
        if package["name"] == "spotifast":
            continue
        folder = Path(package["manifest_path"]).parent
        found = set()
        # Workspace packages sometimes keep their license at the repository root.
        for parent in [folder, *list(folder.parents)[:3]]:
            for candidate in parent.iterdir():
                if candidate.is_file() and candidate.name.upper().startswith(
                    ("LICENSE", "COPYING", "NOTICE", "COPYRIGHT")
                ):
                    found.add(candidate)
            if found:
                break
        title = package["name"] + "-" + package["version"]
        target = destination / title
        target.mkdir(exist_ok=True)
        for source in sorted(found):
            shutil.copy2(source, target / source.name)
        index.append(
            {
                "package": title,
                "license": package.get("license"),
                "repository": package.get("repository"),
                "notices": [p.name for p in sorted(found)],
            }
        )
    (destination / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    print("Retained notices for", len(index), "locked Rust packages.")


if __name__ == "__main__":
    main()
