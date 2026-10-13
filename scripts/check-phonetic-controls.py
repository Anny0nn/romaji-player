"""Explicit local negative controls; never run models in hooks or change app data.

Synthetic silence/instrumental audio and an unrelated human singing clip exercise
the small-vowel fallback and offline context policy. Publish counts, never audio.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
from context_policy import apply_context, joint_crops
from refinement_helper import mms, repair, tifa, verify_assets


def main():
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--wrong-vocal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT == output or ROOT in output.parents:
        parser.error("Private evidence belongs outside the checkout.")
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.chmod(0o700)
    if (output / "summary.json").exists():
        parser.error("Use a fresh output directory.")
    verify_assets(args.assets)
    vocals, rate = sf.read(args.wrong_vocal, dtype="float32")
    if vocals.ndim != 1 or not np.isfinite(vocals).all():
        raise ValueError("Expected a finite mono control recording.")
    vocals = resample_poly(vocals, 16000, rate).astype(np.float32)
    length = min(len(vocals), 18 * 16000)
    if length < 8 * 16000:
        raise ValueError("Control clip is too short.")
    clock = np.arange(length) / 16000
    instrumental = (
        sum(
            np.sin(2 * np.pi * freq * clock)
            for freq in (110, 164.81, 220, 261.63, 329.63)
        )
        * 0.02
    )
    summary = {}
    for name, samples in (
        ("silence", np.zeros(length, dtype=np.float32)),
        ("synthetic_instrumental", instrumental.astype(np.float32)),
        ("wrong_verse", vocals[:length]),
    ):
        crops = []
        for occurrence, spellings in enumerate(
            (("あぁ", "きつね", "が"), ("さくら", "を", "わたる"))
        ):
            words, offset = [], 0
            for text, romaji in zip(
                spellings,
                (("aa", "kitsune", "ga"), ("sakura", "o", "wataru"))[occurrence],
                strict=True,
            ):
                last = offset + len(text.encode())
                words.append(
                    {"raw_span": [offset, last], "text": text, "romaji": romaji}
                )
                offset = last
            crops.append(
                (
                    occurrence,
                    0 if occurrence == 0 else 4 * 16000,
                    length - 16000 if occurrence == 0 else length,
                    words,
                )
            )
        trials = tifa(
            samples,
            crops,
            args.archive,
            output / "progress.txt",
            name,
            vowel_retry=True,
        )
        proof = mms(samples, crops, args.assets / "mms", output / "progress.txt", name)
        baseline = [row["units"] for row in trials]
        candidate = [
            repair(
                b,
                row["vowel_retry"],
                e,
                targets,
                (last - first) // 16,
                len(targets),
                eligible=row["vowel_retry"]["eligible"],
            )
            if "vowel_retry" in row
            else b
            for b, row, e, (_, first, last, targets) in zip(
                baseline, trials, proof, crops, strict=True
            )
        ]
        jobs = joint_crops(crops, baseline, {"0": 3, "1": 3})
        if jobs:
            joint = [job["crop"] for job in jobs]
            extended = tifa(samples, joint, args.archive, output / "progress.txt", name)
            independent = mms(
                samples, joint, args.assets / "mms", output / "progress.txt", name
            )
            context = apply_context(baseline, crops, jobs, extended, independent)
        else:
            context = baseline
        counts = {}
        for label, units in (("vowel", candidate), ("context", context)):
            counts[label + "_new_words"] = sum(
                old["start_ms"] < 0 <= new["start_ms"]
                for a, b in zip(baseline, units, strict=True)
                for old, new in zip(a, b, strict=True)
            )
        summary[name] = counts
    with (output / "summary.json").open("x") as handle:
        json.dump(summary, handle, indent=2)
    print(json.dumps(summary))
    if any(any(v for v in counts.values()) for counts in summary.values()):
        raise SystemExit("Negative control admitted a new word; do not promote.")


if __name__ == "__main__":
    main()
