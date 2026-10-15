"""Cache TIFA's original raw source-word observations on authenticated samples.

Supplied text is an alignment candidate, never independent lexical truth. Human
clocks, generative timestamps, source regrouping and app writes are not used.
"""

import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys
import time
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path

sys.path[:0] = [str(ROOT / "tifa")]
spec = importlib.util.spec_from_file_location(
    "blind_audio", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)


def main():
    from tifa_helper import Aligner, prepare_model

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.manifest, args.archive, args.output = map(
        private_path, (args.manifest, args.archive, args.output)
    )
    manifest = json.loads(args.manifest.read_text())
    if len({c["id"] for c in manifest["cases"]}) != len(manifest["cases"]):
        raise ValueError("Duplicate source/audio candidate identity.")
    identity = {
        "manifest_sha256": digest(args.manifest),
        "archive_sha256": digest(args.archive),
        "code": {
            name: digest(ROOT / name)
            for name in (
                "scripts/observe-tifa-source.py",
                "scripts/recognize-singing-phones.py",
                "tifa/tifa_helper.py",
            )
        },
        "role": "original raw TIFA source-word observations, not lexical verification",
    }
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2))
    started = time.monotonic()
    model = Aligner(prepare_model(args.archive))
    cache, rows = {}, []
    for case in manifest["cases"]:
        samples = blind.load_samples(
            {"id": case["id"], **case["audio"]}, args.manifest.parent, cache
        )
        if len(samples) > 480000:
            raise ValueError("TIFA pilot exceeds 30 seconds.")
        raw = []
        with contextlib.redirect_stdout(io.StringIO()):
            units = model.align(samples, case["targets"], diagnostics=raw)
        rows.append({"id": case["id"], "units": units, "raw_units": raw})
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
        "retained_words": sum(u["start_ms"] >= 0 for r in rows for u in r["units"]),
    }
    (args.output / "complete.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
