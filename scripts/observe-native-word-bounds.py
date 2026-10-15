"""Private original-source timing benchmark using the existing native Qwen helper.

No helper rebuild, source-clock repair, interpolation or app writes. This is forced
alignment of exact word candidates, not independent lexical recognition.
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path
from native_word_reference import request, validate_reply

MODEL_SHA256 = "5de69a8cfc49c95a6520f50f2f15cfce9af35bc4723a10c56fc64e51dc966b3a"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument(
        "--helper", type=Path, default=ROOT / "aligner/build/RomajiAligner"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.manifest, args.model, args.output = map(
        private_path, (args.manifest, args.model, args.output)
    )
    if args.model.stat().st_size != 994404608 or digest(args.model) != MODEL_SHA256:
        raise ValueError("Different native alignment checkpoint.")
    manifest = json.loads(args.manifest.read_text())
    groups = {}
    for case in manifest["cases"]:
        audio = case["audio"]
        if audio["encoding"] != "pcm" or digest(Path(audio["path"])) != audio["sha256"]:
            raise ValueError("Changed original PCM identity.")
        groups.setdefault(audio["path"], []).append(case)
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    identity = {
        "manifest_sha256": digest(args.manifest),
        "model_sha256": MODEL_SHA256,
        "helper_sha256": digest(args.helper),
        "code": {
            name: digest(ROOT / "scripts" / name)
            for name in ("observe-native-word-bounds.py", "native_word_reference.py")
        },
        "adapter_cpp_sha256": digest(ROOT / "aligner/main.cpp"),
        "role": "raw forced source-word observations; no lexical verification or clock repair",
    }
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2))
    rows = []
    started = time.monotonic()
    for number, (pcm, cases) in enumerate(groups.items()):
        path = args.output / (str(number) + ".bin")
        path.write_bytes(request(cases))
        result = subprocess.run(
            [str(args.helper), str(args.model), pcm, str(path)],
            capture_output=True,
            check=False,
            text=True,
            timeout=300,
        )
        (args.output / (str(number) + "-stderr.txt")).write_text(result.stderr)
        if result.returncode:
            raise RuntimeError("Native inference failed; stderr saved privately.")
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        if len(replies) != len(cases) or [r["occurrence"] for r in replies] != list(
            range(len(cases))
        ):
            raise ValueError("Native inference changed occurrence identities.")
        rows.extend(
            {"id": c["id"], "units": validate_reply(c, r)}
            for c, r in zip(cases, replies, strict=True)
        )
        print(
            json.dumps({"completed_cases": len(rows), "total": len(manifest["cases"])}),
            flush=True,
        )
    (args.output / "private-records.json").write_text(
        json.dumps(rows, indent=2, allow_nan=False)
    )
    summary = {
        "identity_sha256": digest(args.output / "identity.json"),
        "records_sha256": digest(args.output / "private-records.json"),
        "seconds": time.monotonic() - started,
        "cases": len(rows),
        "observed_words": sum(u["start_ms"] >= 0 for r in rows for u in r["units"]),
    }
    (args.output / "complete.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
