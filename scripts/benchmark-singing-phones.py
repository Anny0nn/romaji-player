"""Private PJS human phone-boundary benchmark, not a word or recognition score.

PJS audio and CC BY-SA human relabels stay outside git. Run development first;
freeze receipts before heldout. A heldout run publishes no partial per-song results.
Recipes currently compare raw TIFA skip penalties; production word gates are unchanged.
"""

import argparse
import contextlib
import hashlib
import io
import json
import resource
import sys
import time
from pathlib import Path

from singing_reference import SILENCE, evaluate, htk_labels, selected_ids

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tifa"), str(ROOT / "tifa/vendor")]


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_private(path, data):
    import os

    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(data, handle, indent=2, allow_nan=False)


def provenance(corpus, archive, recipes):
    # Asset archives are hashed, without opening any reserved labels.
    sources = {
        "audio": corpus / "audio.zip",
        "labels": corpus / "labels.zip",
        "split": corpus / "split.json",
        "archive": archive,
        "recipes": recipes,
        "runner": Path(__file__),
        "metrics": ROOT / "scripts/singing_reference.py",
        "helper": ROOT / "tifa/tifa_helper.py",
        "vendor": ROOT / "tifa/vendor/local-sha256.json",
    }
    return {name: digest(path) for name, path in sources.items()}


def raw_tifa(aligner, samples, references, penalty):
    import numpy as np
    import torch
    from inference.backend import SpectrogramContext
    from scipy.signal import resample_poly

    result = [{**r, "start_ms": -1, "end_ms": -1} for r in references]
    phones = [
        (i, r["phone"]) for i, r in enumerate(references) if r["phone"] not in SILENCE
    ]
    # Never discard an unknown phone or silently collapse uppercase vowel labels.
    symbols = aligner.vocabulary.symbol_to_id
    if not phones or any(f"ja/{p}" not in symbols for _, p in phones):
        return result, "unsupported_phone_inventory"
    tokens = torch.tensor([[symbols[f"ja/{p}"] for _, p in phones]], device="mps")
    waveform = resample_poly(samples, 3, 1).astype(np.float32)
    with torch.inference_mode():
        spec = aligner.backend.spectrogram(
            torch.from_numpy(waveform.copy())[None],
            torch.tensor([len(waveform) / 48000]),
        )
        spec = SpectrogramContext(spec.features.to("mps"), spec.mask.to("mps"))
        alignment = aligner.backend.align(
            spec, tokens=tokens, unit="frame", skip_penalty=penalty
        )
    spans = alignment.spans[0].cpu().numpy()
    for (index, _), (first, last) in zip(phones, spans, strict=True):
        if 0 <= first < last and last * 10 <= len(samples) / 16:
            result[index].update(start_ms=int(first * 10), end_ms=int(last * 10))
    return result, "raw_forced_boundaries"


def main():
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    from tifa_helper import Aligner, prepare_model

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["freeze", "run"])
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--recipes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--partition", choices=["development", "heldout"], default="development"
    )
    parser.add_argument("--receipt", type=Path)
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
    signature = provenance(corpus, args.archive, args.recipes)
    recipes = json.loads(args.recipes.read_text())
    if not recipes or any(
        not isinstance(v, (int, float)) or not 0 <= v <= 2 for v in recipes.values()
    ):
        parser.error("Recipes map names to finite TIFA skip penalties in [0, 2].")
    if args.operation == "freeze":
        write_private(output / "frozen.json", signature)
        print("Exact recipe and reference receipt frozen; no labels opened.")
        return
    receipt = json.loads(args.receipt.read_text()) if args.receipt else None
    ids = selected_ids(
        json.loads((corpus / "split.json").read_text()),
        args.partition,
        receipt,
        signature,
    )
    if any(not name.startswith("pjs") or not name[3:].isdigit() for name in ids):
        parser.error("Invalid PJS song ID.")
    with contextlib.redirect_stdout(io.StringIO()):
        aligner = Aligner(prepare_model(args.archive))
    records = {key: [] for key in recipes}
    started = time.perf_counter()
    for name in ids:
        audio, labels = (
            corpus / "audio" / f"{name}_song.wav",
            corpus / "labels" / f"{name}.lab",
        )
        samples, rate = sf.read(audio, dtype="float32")
        if (
            samples.ndim != 1
            or not len(samples)
            or not np.isfinite(samples).all()
            or rate != 48000
        ):
            raise ValueError("Expected original mono 48 kHz PJS recording.")
        # Confirm extracted files match the hashed archives, not just their filenames.
        import zipfile

        for path, archive_name in ((audio, "audio.zip"), (labels, "labels.zip")):
            with zipfile.ZipFile(corpus / archive_name) as archive:
                members = [
                    entry
                    for entry in archive.namelist()
                    if Path(entry).name == path.name
                ]
                if len(members) != 1 or hashlib.sha256(
                    archive.read(members[0])
                ).hexdigest() != digest(path):
                    raise ValueError(
                        "Extracted reference changed from its frozen archive."
                    )
        references = htk_labels(labels.read_text(), len(samples) * 1000 / rate)
        samples = resample_poly(samples, 1, 3).astype(np.float32)
        for recipe, penalty in recipes.items():
            with contextlib.redirect_stdout(io.StringIO()):
                predicted, status = raw_tifa(aligner, samples, references, penalty)
            records[recipe].append(
                {
                    "id": name,
                    "recording_sha256": digest(audio),
                    "annotation_sha256": digest(labels),
                    "provenance": "PJS audio + UtaUtaUtau human HTK monophone relabels; CC BY-SA 4.0",
                    "status": status,
                    "language": "ja",
                    "reference": references,
                    "predicted": predicted,
                }
            )
        if args.partition == "development":
            print(json.dumps({"completed": name}), flush=True)
    # Release per-unit evidence only after the entire frozen partition finishes.
    summary = {
        "partition": args.partition,
        "signature": signature,
        "seconds": time.perf_counter() - started,
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "recipes": {key: evaluate(value) for key, value in records.items()},
    }
    write_private(output / "summary.json", summary)
    write_private(output / "private-records.json", records)
    print(json.dumps(summary, allow_nan=False))


if __name__ == "__main__":
    main()
