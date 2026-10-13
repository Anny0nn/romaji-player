"""Replay the app's reading policy on explicit local evidence; never write app data.

Manifest: mms_vocabulary, independent_vocabulary, songs. Each song supplies input,
crops (JSON [occurrence, first_sample, last_sample, targets]), two mms_views arrays
of NPZ paths, independent NPZ paths, and two transcripts JSON paths. Paths resolve
relative to the manifest. Inputs/proposals can contain private lyrics: keep them local.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa"), str(ROOT / "tifa/vendor")]
from reading_repair import Converter, corrected_crops, propose


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--romanizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    folder = args.manifest.resolve().parent

    def load(path):
        return json.loads((folder / path).read_text())

    def posterior(path):
        with np.load(folder / path, allow_pickle=False) as value:
            return value["logp"].copy(), int(value["blank"])

    dataset = load(args.manifest.resolve())
    vocabulary = load(dataset["mms_vocabulary"])
    independent_vocabulary = load(dataset["independent_vocabulary"])
    results = []
    converter = Converter(args.romanizer.resolve())
    try:
        for song in dataset["songs"]:
            inputs, crops = load(song["input"]), load(song["crops"])
            views = [[posterior(p) for p in paths] for paths in song["mms_views"]]
            independent = [posterior(p) for p in song["independent"]]
            if len(views) != 2 or any(len(v) != len(crops) for v in views):
                raise ValueError("Replay views do not match source crops.")
            if len(independent) != len(crops):
                raise ValueError("Replay independent evidence is incomplete.")
            readings, text = propose(
                inputs,
                crops,
                converter,
                views,
                independent,
                vocabulary,
                independent_vocabulary,
                [load(p) for p in song["transcripts"]],
            )
            corrected, counts = corrected_crops(
                inputs, crops, converter, readings, text
            )
            results.append(
                {
                    "track": inputs["track"],
                    "readings": readings,
                    "text_repairs": text,
                    "corrected_crops": corrected,
                    "source_counts": counts,
                }
            )
            print(
                json.dumps(
                    {
                        "songs": len(results),
                        "reading_repairs": len(readings),
                        "text_repairs": len(text),
                    }
                ),
                flush=True,
            )
    finally:
        converter.close()
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as file:
        json.dump(results, file, ensure_ascii=False, allow_nan=False)


if __name__ == "__main__":
    main()
