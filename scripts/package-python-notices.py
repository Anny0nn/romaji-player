"""Preserve the inference environment's wheel license notices in the app."""

import importlib.metadata
import json
import sys
from pathlib import Path


def main():
    destination = Path("dist/RomajiPlayer.app/Contents/Resources/Notices") / (
        sys.argv[1] if len(sys.argv) == 2 else "TIFAPython"
    )
    destination.mkdir(parents=True, exist_ok=True)
    index = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        target = destination / f"{name}-{distribution.version}"
        notices = []
        for file in distribution.files or []:
            if (
                Path(file)
                .name.upper()
                .startswith(("LICENSE", "COPYING", "NOTICE", "COPYRIGHT"))
            ):
                source = distribution.locate_file(file)
                if source.is_file():
                    relative = Path(file)
                    output = target / relative
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(source.read_bytes())
                    notices.append(str(relative))
        index.append(
            {
                "package": name,
                "version": distribution.version,
                "license": distribution.metadata.get("License"),
                "notices": notices,
            }
        )
    (destination / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    print("Retained Python dependency notices for", len(index), "distributions.")


if __name__ == "__main__":
    main()
