"""NUS development boundary agreement: fresh TIFA versus pinned HubertFA observations.

Provided human phones test boundary quality, not lyric recognition. This tool
cannot open a heldout partition or publish the corpus. No app timings are saved.
"""

import argparse
import contextlib
import importlib.util
import io
import json
import os
import resource
import sys
import time
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path
from singing_reference import evaluate

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
from english_boundaries import paired_boundary

spec = importlib.util.spec_from_file_location(
    "hfa_benchmark", Path(__file__).with_name("benchmark-hubertfa.py")
)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def paired_words(row, raw):
    words = benchmark.word_records([row], supported=False)[0]
    if len(words["reference"]) != len(raw):
        raise ValueError("Boundary observations changed human word grouping.")
    predicted = []
    for index, unit in enumerate(words["predicted"]):
        target_span = [index * 2, index * 2 + 1]
        singing = {**unit, "raw_span": target_span, "complete": unit["start_ms"] >= 0}
        candidate = paired_boundary(raw[index], singing, row["length_ms"])
        predicted.append(
            {
                **unit,
                "start_ms": candidate["start_ms"] if candidate else -1,
                "end_ms": candidate["end_ms"] if candidate else -1,
            }
        )
    return {"id": row["id"], "reference": words["reference"], "predicted": predicted}


def main():
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    from tifa_helper import Aligner, prepare_model

    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for name in ("observations", "manifest", "archive", "output"):
        setattr(args, name, private_path(getattr(args, name)))
    identity = json.loads((args.observations / "identity.json").read_text())
    if identity["partition"] != "development" or identity["manifest"] != digest(
        args.manifest
    ):
        raise ValueError("Expected authenticated development observations.")
    for name, sha in identity["code"].items():
        if digest(Path(__file__).with_name(name)) != sha:
            raise ValueError("HubertFA inference or evaluation code changed.")
    manifest = json.loads(args.manifest.read_text())
    songs = {row["id"]: row for row in manifest["songs"]}
    selected = manifest["development"]
    if set(selected) & set(manifest["heldout"]) or set(selected) != set(
        identity["inputs"]
    ):
        raise ValueError("Changed or overlapping development selection.")
    signatures = {
        "parent": digest(args.observations / "identity.json"),
        "manifest": digest(args.manifest),
        "archive": digest(args.archive),
        "runner": digest(Path(__file__)),
        "policy": digest(ROOT / "refinement/english_boundaries.py"),
        "tifa": digest(ROOT / "tifa/tifa_helper.py"),
    }
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    benchmark.write(args.output / "identity.json", signatures)
    aligner = Aligner(prepare_model(args.archive))
    records, tifa_only = [], []
    started = time.monotonic()
    for name in selected:
        song = songs[name]
        if digest(private_path(song["audio"])) != identity["inputs"][name]["audio"]:
            raise ValueError("Development audio changed.")
        waveform, rate = sf.read(song["audio"], dtype="float32")
        if rate != 44100 or waveform.ndim != 1 or not np.isfinite(waveform).all():
            raise ValueError("Expected original mono 44.1kHz development recording.")
        paths = sorted(args.observations.glob(f"{name}-*.json"))
        for path in paths:
            row = benchmark.read_checkpoint(path, identity)
            if not row["id"].startswith(name + ":"):
                raise ValueError("Development observation identity changed.")
            first, last = row["crop_samples"]
            samples = resample_poly(waveform[first:last], 160, 441).astype(np.float32)
            owners = list(dict.fromkeys(ref["word"] for ref in row["reference"]))
            targets = [
                {"raw_span": [i * 2, i * 2 + 1], "text": "word", "romaji": "word"}
                for i in range(len(owners))
            ]
            aliases = {
                i: {
                    "language": "en",
                    "phones": [
                        ref["phone"] for ref in row["reference"] if ref["word"] == owner
                    ],
                }
                for i, owner in enumerate(owners)
            }
            raw = []
            with contextlib.redirect_stdout(io.StringIO()):
                units = aligner.align(
                    samples, targets, diagnostics=raw, phonetic_aliases=aliases
                )
            row["length_ms"] = len(samples) / 16
            pair = paired_words(row, raw)
            reference = pair["reference"]
            tifa_only.append(
                {
                    "id": row["id"],
                    "reference": reference,
                    "predicted": [
                        {**ref, "start_ms": u["start_ms"], "end_ms": u["end_ms"]}
                        for ref, u in zip(reference, units, strict=True)
                    ],
                }
            )
            records.append(pair)
            benchmark.write_checkpoint(
                args.output / path.name,
                {"pair": pair, "tifa": units, "raw": raw},
                signatures,
            )
    summary = {
        "boundary_only": True,
        "lexical_verification_evaluated": False,
        "tifa": {**evaluate(tifa_only), "granularity": "human_sp_word_group"},
        "paired": {**evaluate(records), "granularity": "human_sp_word_group"},
        "seconds": time.monotonic() - started,
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    benchmark.write(args.output / "summary.json", summary)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
