"""Private PJS contextual timing benchmark, with frozen nonlexical phone groups.

Uses human phone endpoints, not lyric cues, as the scoring reference. Synthesized
two-line splits exercise the actual TIFA/MMS repair functions. Correct kana are
provided to both recipes; this cannot establish reading-selection accuracy.
No per-phrase outputs are written until the entire chosen partition completes.
"""

import argparse
import contextlib
import hashlib
import io
import json
import os
import resource
import sys
import time
from pathlib import Path

from singing_groups import groups, phrases
from singing_reference import evaluate, htk_labels, selected_ids, verify_extracted

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
from context_policy import apply_context, joint_crops
from refinement_helper import mms, repair, tifa, verify_assets
from singing_phonemes import kana_phones


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write(path, value):
    import os

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)


def inventory():
    from g2p.converters.japanese import _KANA_TO_ROMAJI

    result = {("N",): "ん"}
    for kana in sorted(_KANA_TO_ROMAJI, key=lambda k: (len(k), k)):
        if not all("ぁ" <= c <= "ゖ" for c in kana):
            continue
        value = kana_phones(kana)
        if value and "cl" not in value:
            result.setdefault(tuple(value), kana)
    return result


def prepare(corpus, ids):
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    mapping = inventory()
    chunks, crops, references, counts, owners = [], [], [], {}, []
    total = unsupported = short = offset = 0
    for name in ids:
        for subdir, filename, archive in (
            ("audio", f"{name}_song.wav", "audio.zip"),
            ("labels", f"{name}.lab", "labels.zip"),
        ):
            verify_extracted(corpus / archive, corpus / subdir / filename)
        waveform, rate = sf.read(corpus / "audio" / f"{name}_song.wav", dtype="float32")
        if waveform.ndim != 1 or rate != 48000:
            raise ValueError("Unexpected PJS audio format.")
        samples = resample_poly(waveform, 1, 3).astype(np.float32)
        labels = htk_labels(
            (corpus / "labels" / f"{name}.lab").read_text(), len(samples) / 16
        )
        for occurrence, phone_sequence in enumerate(phrases(labels)):
            # A denominator independent of whether inventory conversion succeeds.
            total += sum(
                p["phone"] in ("a", "i", "u", "e", "o", "I", "U", "O", "N")
                for p in phone_sequence
            )
            grouped = groups(phone_sequence, mapping)
            if grouped is None:
                unsupported += 1
                continue
            if len(grouped) < 4:
                short += 1
                continue
            first = max(0, int(grouped[0]["start_ms"] - 500)) * 16
            last = min(len(samples), int(grouped[-1]["end_ms"] + 300) * 16)
            if last - first > 480000:
                short += 1
                continue
            clip = samples[first:last]
            midpoint = len(grouped) // 2
            cue = int(grouped[midpoint]["start_ms"]) * 16
            for side, indices in enumerate(
                (range(midpoint), range(midpoint, len(grouped)))
            ):
                begin = 0 if side == 0 else max(0, cue - first - 8000)
                end = min(len(clip), cue - first + 4800) if side == 0 else len(clip)
                target = []
                ref = []
                for index in indices:
                    group = grouped[index]
                    target.append(
                        {
                            "raw_span": group["raw_span"],
                            "text": group["text"],
                            "romaji": "reference",
                        }
                    )
                    ref.append(
                        {
                            **group,
                            "start_ms": group["start_ms"] - first / 16 + offset / 16,
                            "end_ms": group["end_ms"] - first / 16 + offset / 16,
                        }
                    )
                identity = len(crops)
                crops.append((identity, offset + begin, offset + end, target))
                counts[str(identity)] = len(target)
                references.append(ref)
                owners.append(f"{name}:{occurrence}")
            padding = (-len(clip)) % 16
            chunks.extend((clip, np.zeros(padding, dtype=np.float32)))
            offset += len(clip) + padding
    if not chunks:
        raise ValueError("No eligible voiced reference phrases.")
    return (
        np.concatenate(chunks),
        crops,
        counts,
        references,
        owners,
        {
            "vowel_n_units_before_grouping": total,
            "unsupported_phrases": unsupported,
            "short_or_long_phrases": short,
        },
    )


def score(crops, reference, owners, baseline, candidate):
    records = {"baseline": [], "candidate": [], "affected": []}
    gained = lost = regressed = changed = 0
    affected_phrases = set()
    for crop, refs, owner, old, new in zip(
        crops, reference, owners, baseline, candidate, strict=True
    ):
        for recipe, units in (("baseline", old), ("candidate", new)):
            prediction = [
                {
                    "unit": r["unit"],
                    "phone": r["phone"],
                    "start_ms": u["start_ms"] + crop[1] / 16
                    if u["start_ms"] >= 0
                    else -1,
                    "end_ms": u["end_ms"] + crop[1] / 16 if u["start_ms"] >= 0 else -1,
                }
                for r, u in zip(refs, units, strict=True)
            ]
            records[recipe].append(
                {"id": owner, "reference": refs, "predicted": prediction}
            )
        for ref, a, b in zip(refs, old, new, strict=True):
            if any(a[k] != b[k] for k in ("start_ms", "end_ms")):
                changed += 1
                affected_phrases.add(owner)
                prediction = {
                    "unit": ref["unit"],
                    "phone": ref["phone"],
                    "start_ms": b["start_ms"] + crop[1] / 16
                    if b["start_ms"] >= 0
                    else -1,
                    "end_ms": b["end_ms"] + crop[1] / 16 if b["start_ms"] >= 0 else -1,
                }
                records["affected"].append(
                    {"id": owner, "reference": [ref], "predicted": [prediction]}
                )
            gained += a["start_ms"] < 0 <= b["start_ms"]
            lost += b["start_ms"] < 0 <= a["start_ms"]

            def correct(unit, crop=crop, ref=ref):
                return (
                    unit["start_ms"] >= 0
                    and abs(unit["start_ms"] + crop[1] / 16 - ref["start_ms"]) <= 150
                    and abs(unit["end_ms"] + crop[1] / 16 - ref["end_ms"]) <= 200
                )

            regressed += correct(a) and not correct(b)
    metrics = {
        key: {**evaluate(value), "granularity": "two-mora_phone_group"}
        for key, value in records.items()
    }
    affected = metrics["affected"]
    fractions = affected["errors_ms"]
    enough = affected["aligned_units"] >= 50 and len(affected_phrases) >= 10
    gate = (
        enough
        and not lost
        and not regressed
        and fractions["onset"]["fractions_within"]["150"] >= 0.98
        and fractions["offset"]["fractions_within"]["200"] >= 0.95
    )
    return {
        "new_units": gained,
        "lost_units": lost,
        "regressed_correct_units": regressed,
        "changed_units": changed,
        "distinct_affected_phrases": len(affected_phrases),
        "metrics": metrics,
        "timing_reference_gate_passed": bool(gate),
    }, records


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["freeze", "run"])
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--partition", choices=["development", "heldout"], default="development"
    )
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--noise-snr-db", type=int, choices=[0, 10])
    args = parser.parse_args()
    corpus, output = args.corpus.resolve(), args.output.resolve()
    if (
        ROOT == corpus
        or ROOT in corpus.parents
        or ROOT == output
        or ROOT in output.parents
    ):
        parser.error("Reference inputs and outputs must live outside the checkout.")
    output.mkdir(parents=True, mode=0o700, exist_ok=True)
    output.chmod(0o700)
    if (output / "summary.json").exists() or (output / "private-records.json").exists():
        parser.error("Use a fresh output directory for each recipe run.")
    paths = {
        "audio": corpus / "audio.zip",
        "labels": corpus / "labels.zip",
        "split": corpus / "split.json",
        "archive": args.archive,
        "assets": ROOT / "refinement/refinement-model-files.json",
        "runner": Path(__file__),
        "grouping": ROOT / "scripts/singing_groups.py",
        "metrics": ROOT / "scripts/singing_reference.py",
        "policy": ROOT / "refinement/context_policy.py",
        "helper": ROOT / "refinement/refinement_helper.py",
        "regional_policy": ROOT / "refinement/refinement_policy.py",
        "tifa": ROOT / "tifa/tifa_helper.py",
        "vendor": ROOT / "tifa/vendor/local-sha256.json",
    }
    signature = {name: digest(path) for name, path in paths.items()}
    signature["noise_snr_db"] = args.noise_snr_db
    if args.operation == "freeze":
        write(output / "frozen.json", signature)
        print("Context recipe frozen; no reference labels opened.")
        return
    ids = selected_ids(
        json.loads((corpus / "split.json").read_text()),
        args.partition,
        json.loads(args.receipt.read_text()) if args.receipt else None,
        signature,
    )
    verify_assets(args.assets)
    start = time.monotonic()
    progress_path = output / "progress.txt"
    with contextlib.redirect_stdout(io.StringIO()):
        samples, crops, counts, refs, owners, preparation = prepare(corpus, ids)
        if args.noise_snr_db is not None:
            import numpy as np

            # A fixed synthetic stress condition preserves every human endpoint.
            # It is not a labelled commercial mix or a recognition benchmark.
            noise = np.random.default_rng(0).standard_normal(len(samples))
            spectrum = np.fft.rfft(noise)
            frequencies = np.fft.rfftfreq(len(noise), 1 / 16000)
            spectrum *= ((frequencies >= 80) & (frequencies <= 4000)) / np.sqrt(
                np.maximum(frequencies, 80)
            )
            noise = np.fft.irfft(spectrum, n=len(noise))
            scale = np.sqrt(
                np.mean(samples.astype(np.float64) ** 2) / np.mean(noise**2)
            ) / 10 ** (args.noise_snr_db / 20)
            samples = (samples + noise * scale).astype(np.float32)
        trials = tifa(samples, crops, args.archive, progress_path, "Reference baseline")
        proofs = mms(
            samples, crops, args.assets / "mms", progress_path, "Reference evidence"
        )
        baseline = [
            repair(
                row["units"],
                row,
                proof,
                targets,
                (last - first) // 16,
                counts[str(occurrence)],
            )
            for row, proof, (occurrence, first, last, targets) in zip(
                trials, proofs, crops, strict=True
            )
        ]
        # Keep only the two halves of each actual voiced phrase as neighbors.
        jobs = [
            job
            for job in joint_crops(crops, baseline, counts)
            if owners[job["owners"][0][0]] == owners[job["owners"][-1][0]]
        ]
        joint = [job["crop"] for job in jobs]
        if joint:
            new_tifa = tifa(
                samples, joint, args.archive, progress_path, "Reference contexts"
            )
            new_mms = mms(
                samples,
                joint,
                args.assets / "mms",
                progress_path,
                "Reference context evidence",
            )
            candidate = apply_context(baseline, crops, jobs, new_tifa, new_mms)
        else:
            candidate = baseline
    summary, records = score(crops, refs, owners, baseline, candidate)
    summary.update(
        {
            "partition": args.partition,
            "songs": len(ids),
            "prepared_phrases": len(set(owners)),
            "joint_jobs": len(jobs),
            "preparation": preparation,
            "receipt": signature,
            "wall_seconds": time.monotonic() - start,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "reading_accuracy_measured": False,
            "pretraining_disjointness_verified": False,
        }
    )
    write(output / "private-records.json", records)
    write(output / "summary.json", summary)
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "songs",
                    "prepared_phrases",
                    "joint_jobs",
                    "new_units",
                    "changed_units",
                    "regressed_correct_units",
                    "distinct_affected_phrases",
                    "wall_seconds",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
