"""Offline Google lyric candidates + local TIFA timing, with separate source owners.

Research only: no API calls, Keychain, playback, downloads or app writes.
Run prepare before align/verify; proposals are closed before acoustic observations.
"""

import argparse
import hashlib
import json
import os
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa"), str(ROOT / "tifa/vendor")]

from google_audio_api import candidates, request_body
from reading_repair import Converter, alignment_target


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False)


def normalized_candidate(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Empty lyric candidate.")
    value = " ".join(text.splitlines()).strip()
    if len(value.encode()) > 8192:
        raise ValueError("Oversized lyric candidate.")
    return value


def targets_for(text, converter, track, occurrence):
    request = {
        "protocol_version": 2,
        "request_id": occurrence + 1,
        "track_id": track,
        "snapshot_id": hashlib.sha256(text.encode()).hexdigest(),
        "occurrence_id": occurrence,
        "override_revision": 0,
        "expected_conversion_signature": converter.signature,
        "raw_line": text,
        "overrides": [],
    }
    converted = converter.convert(request)
    targets = [
        target
        for word in converted["words"]
        if (target := alignment_target(text, converted, word)) is not None
    ]
    return {
        "source_text": text,
        "snapshot_sha256": request["snapshot_id"],
        "source_groups": len(converted["words"]),
        "targets": targets,
        "unmapped_groups": len(converted["words"]) - len(targets),
        "conversion_signature": converter.signature,
    }


def validate_source_targets(source, crop):
    targets = [
        {k: t[k] for k in ("raw_span", "text", "romaji")} for t in source["targets"]
    ]
    if (
        targets != crop["targets"]
        or source["source_groups"] != crop["source_word_count"]
        or source["conversion_signature"] != crop["conversion_signature"]
    ):
        raise ValueError("Baseline source ownership or converter changed.")


def dependencies():
    return {
        name: sha(ROOT / name)
        for name in (
            "tifa/tifa_helper.py",
            "refinement/reading_repair.py",
            "refinement/singing_timing.py",
            "refinement/singing_phonemes.py",
            "refinement/refinement_policy.py",
            "scripts/google_audio_api.py",
        )
    }


def prepare(args):
    ledger_path = args.pilot / "source-ledger.json"
    ledger = json.loads(ledger_path.read_text())
    manifest = json.loads((args.pilot / "manifest.json").read_text())
    cases = {c["id"]: c for c in manifest["cases"]}
    converter = Converter(args.romanizer)
    proposals = []
    try:
        for row in ledger:
            track, crop = row["track"], row["source_crop"]
            case = cases[track]
            wav = args.pilot / case["path"]
            if sha(wav) != case["sha256"]:
                raise ValueError("Changed API waveform.")
            receipt = (
                args.pilot
                / "hydrogen"
                / (hashlib.sha256(track.encode()).hexdigest() + ".json")
            )
            value = json.loads(receipt.read_text())
            payload = request_body("gemini-4-hydrogen", wav.read_bytes())
            if (
                value["case"] != case
                or value["status"] != "received"
                or value["request_sha256"] != hashlib.sha256(payload).hexdigest()
            ):
                raise ValueError("API request identity differs from the selected crop.")
            duration = (crop["end_sample"] - crop["start_sample"]) / 16000
            observed = candidates(value["response"], duration)
            if observed != value["candidates"]:
                raise ValueError("Cached transcript normalization changed.")
            pcm = args.captures / track / "audio.pcm"
            rust = args.captures / track / "rust-export/rust-crops.json"
            document = args.captures / track / "document.json"
            if (
                sha(pcm) != row["audio_sha256"]
                or sha(rust) != row["rust_manifest_sha256"]
                or sha(document) != row["source_document_sha256"]
                or case["origin_sample"] != crop["start_sample"]
            ):
                raise ValueError("Changed recording/source provenance.")
            native = json.loads(rust.read_text())
            if crop not in native["crops"] or native["track"] != track:
                raise ValueError("Selected crop is not an authenticated Rust export.")
            baseline = targets_for(
                crop["raw_line"], converter, track, crop["occurrence"]
            )
            validate_source_targets(baseline, crop)
            proposals.append(
                {
                    "track": track,
                    "pcm": str(pcm.resolve()),
                    "pcm_sha256": row["audio_sha256"],
                    "first_sample": crop["start_sample"],
                    "last_sample": crop["end_sample"],
                    "api_receipt_sha256": sha(receipt),
                    "source": baseline,
                    "google": targets_for(
                        normalized_candidate(observed["text"]),
                        converter,
                        track,
                        crop["occurrence"],
                    ),
                }
            )
    finally:
        converter.close()
    write(
        args.output / "proposals.json",
        {
            "version": 1,
            "runner_sha256": sha(Path(__file__)),
            "dependencies": dependencies(),
            "romanizer_sha256": sha(args.romanizer),
            "source_ledger_sha256": sha(ledger_path),
            "policy": "Separate candidate snapshots; no timing/source transplants or app admission.",
            "cases": proposals,
        },
    )


def load_proposals(args):
    path = args.output / "proposals.json"
    data = json.loads(path.read_text())
    if (
        data["runner_sha256"] != sha(Path(__file__))
        or data["dependencies"] != dependencies()
    ):
        raise ValueError("Closed hybrid runner changed.")
    return path, data["cases"]


def samples(case):
    import numpy as np

    path = Path(case["pcm"])
    if sha(path) != case["pcm_sha256"]:
        raise ValueError("Changed local waveform.")
    data = np.memmap(path, dtype="<f4", mode="r")
    first, last = case["first_sample"], case["last_sample"]
    if not 0 <= first < last <= len(data):
        raise ValueError("Invalid original sample bounds.")
    result = data[first:last].copy()
    if not np.isfinite(result).all():
        raise ValueError("Invalid original samples.")
    return result


def align(args):
    from tifa_helper import Aligner

    proposal_path, cases = load_proposals(args)
    assets = json.loads((ROOT / "tifa/model-files.json").read_text())
    for name, asset in assets.items():
        if sha(args.tifa_model / name) != asset["sha256"]:
            raise ValueError("Changed TIFA model asset.")
    aligner = Aligner(args.tifa_model)
    rows = []
    for case in cases:
        audio = samples(case)
        for arm in ("source", "google"):
            raw = []
            began = time.monotonic()
            units = aligner.align(audio, case[arm]["targets"], diagnostics=raw)
            rows.append(
                {
                    "track": case["track"],
                    "arm": arm,
                    "units": units,
                    "diagnostics": raw,
                    "seconds": time.monotonic() - began,
                }
            )
        print(json.dumps({"aligned": case["track"]}), flush=True)
    write(
        args.output / "alignment.json",
        {
            "proposals_sha256": sha(proposal_path),
            "rows": rows,
            "max_rss_platform_units": resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss,
        },
    )


def verify(args):
    import torch
    from reading_repair import singing_model
    from singing_timing import word_alignment

    proposal_path, cases = load_proposals(args)
    timing_path = args.output / "alignment.json"
    timings = json.loads(timing_path.read_text())
    if timings["proposals_sha256"] != sha(proposal_path):
        raise ValueError("Timing proposals changed.")
    model, vocabulary = singing_model(args.refinement_model)
    rows = []
    for case in cases:
        audio = samples(case)
        with torch.inference_mode():
            logp = (
                model(torch.from_numpy(audio)[None].to("mps"))
                .logits[0]
                .float()
                .log_softmax(-1)
                .cpu()
                .numpy()
            )
        for arm in ("source", "google"):
            words = case[arm]["targets"]
            evidence = word_alignment(
                logp, model.config.pad_token_id, words, vocabulary
            )
            timing = next(
                r
                for r in timings["rows"]
                if r["track"] == case["track"] and r["arm"] == arm
            )
            qualified = []
            for unit, proof in zip(timing["units"], evidence, strict=True):
                qualified.append(
                    unit["start_ms"] >= 0
                    and unit["end_ms"] - unit["start_ms"] >= 80
                    and proof["mean_probability"] >= 0.45
                    and abs(unit["start_ms"] - proof["start_ms"]) <= 150
                    and abs(unit["end_ms"] - proof["end_ms"]) <= 150
                )
            rows.append(
                {
                    "track": case["track"],
                    "arm": arm,
                    "evidence": evidence,
                    "endpoint_supported": qualified,
                    "source_groups": case[arm]["source_groups"],
                    "unmapped_groups": case[arm]["unmapped_groups"],
                }
            )
        print(json.dumps({"verified": case["track"]}), flush=True)
    write(
        args.output / "verification.json",
        {
            "proposals_sha256": sha(proposal_path),
            "alignment_sha256": sha(timing_path),
            "rows": rows,
            "policy": "Endpoint diagnostic only; independent model is Japanese-only; phrase/reading admission unproven.",
            "max_rss_platform_units": resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "align", "verify"))
    parser.add_argument("--pilot", type=Path)
    parser.add_argument("--captures", type=Path)
    parser.add_argument("--romanizer", type=Path)
    parser.add_argument("--tifa-model", type=Path)
    parser.add_argument("--refinement-model", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    os.environ.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        NUMBA_CACHE_DIR="/private/tmp/romaji-hybrid-numba",
    )
    if args.output.resolve().is_relative_to(ROOT):
        parser.error("Private results must be outside the checkout.")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    if args.output.stat().st_mode & 0o077:
        parser.error("Output directory must be private.")
    {"prepare": prepare, "align": align, "verify": verify}[args.stage](args)


if __name__ == "__main__":
    main()
