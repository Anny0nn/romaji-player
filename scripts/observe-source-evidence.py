"""Private source-conditioned acoustic contrasts and word ablations, not app timings.

Original audio, silence and another verse use identical decoder tokens. Word masks
use model-observed boundaries, never human reference times. Scores and attention
are conditional observations, not independently recognized lyrics. No promotion here.
"""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import os
import resource
import time
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path
from whisper_source_evidence import SourceScorer

spec = importlib.util.spec_from_file_location(
    "blind_audio_runner", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)
checkpoint_spec = importlib.util.spec_from_file_location(
    "source_checkpoints", ROOT / "scripts/benchmark-hubertfa.py"
)
checkpoints = importlib.util.module_from_spec(checkpoint_spec)
checkpoint_spec.loader.exec_module(checkpoints)


def mask_controls(length, first, last):
    """Same-sized counterfactual masks, disjoint from the candidate audio."""
    if (
        not all(type(x) is int for x in (length, first, last))
        or not 0 <= first < last <= length
    ):
        raise ValueError("Invalid acoustic ablation bounds.")
    width = last - first
    starts = (0, (length - width) // 2, length - width)
    return list(
        dict.fromkeys((a, a + width) for a in starts if a + width <= first or a >= last)
    )[:2]


def source_scores(observation):
    return observation["source_mean_log_probabilities"]


def main():
    import mlx.core as mx
    import numpy as np

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ablations", action="store_true")
    args = parser.parse_args()
    args.manifest, args.models, args.output = map(
        private_path, (args.manifest, args.models, args.output)
    )
    manifest = json.loads(args.manifest.read_text())
    cases = manifest["cases"]
    if not cases or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Invalid unique source candidate set.")
    os.umask(0o077)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    mx.set_memory_limit(10 * 1024**3)
    mx.set_cache_limit(512 * 1024**2)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    signature = {
        "manifest_sha256": digest(args.manifest),
        "model_manifest_sha256": digest(
            ROOT / "refinement/refinement-model-files.json"
        ),
        "code": {
            name: digest(Path(__file__).with_name(name))
            for name in (
                "observe-source-evidence.py",
                "whisper_source_evidence.py",
                "audio_first_models.py",
                "recognize-singing-phones.py",
                "benchmark-hubertfa.py",
            )
        },
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("mlx", "mlx-whisper", "numpy", "tiktoken")
        },
        "ablations": args.ablations,
        "mask": "zero original observed interval; up to two disjoint equal-length control intervals",
        "role": "source-conditioned observation; human labels unused; no app acceptance",
    }
    identity = args.output / "identity.json"
    if identity.exists():
        if json.loads(identity.read_text()) != signature:
            raise ValueError(
                "Changed observation recipe; choose another output directory."
            )
    else:
        blind.write(identity, signature)
    identity_sha = digest(identity)
    start = time.monotonic()
    scorer = SourceScorer(args.models)
    loaded_seconds = time.monotonic() - start
    cache, records = {}, []
    for number, case in enumerate(cases, 1):
        filename = hashlib.sha256(case["id"].encode()).hexdigest() + ".json"
        path = args.output / filename
        if path.exists():
            row = checkpoints.read_checkpoint(path, signature)
            if row["identity_sha256"] != identity_sha or row["id"] != case["id"]:
                raise ValueError("Changed observation checkpoint.")
        else:
            samples = blind.load_samples(
                {"id": case["id"], **case["audio"]}, args.manifest.parent, cache
            )
            began = time.monotonic()
            base = scorer.observe(
                samples, case["raw_line"], case["language"], case["targets"]
            )
            silence = scorer.observe(
                np.zeros_like(samples),
                case["raw_line"],
                case["language"],
                case["targets"],
                boundaries=False,
            )
            wrong = None
            if "wrong_audio" in case:
                alternate = blind.load_samples(
                    {"id": case["id"] + ":wrong", **case["wrong_audio"]},
                    args.manifest.parent,
                    cache,
                )
                if len(alternate) != len(samples):
                    raise ValueError(
                        "Contrast must use the same original sample count."
                    )
                wrong = scorer.observe(
                    alternate,
                    case["raw_line"],
                    case["language"],
                    case["targets"],
                    boundaries=False,
                )
            words = []
            boundaries = case.get("mask_boundary_units", base["source_units"])
            if [u["raw_span"] for u in boundaries] != [
                u["raw_span"] for u in case["targets"]
            ]:
                raise ValueError("Mask boundaries changed original group ownership.")
            for index, unit in enumerate(base["source_units"]):
                score = source_scores(base)[index]
                unit = {
                    **unit,
                    "start_ms": boundaries[index]["start_ms"],
                    "end_ms": boundaries[index]["end_ms"],
                    "boundary_kind": case.get(
                        "mask_boundary_kind", "Whisper conditional attention"
                    ),
                    "source_mean_log_probability": score,
                }
                for name, observation in (("silence", silence), ("wrong_verse", wrong)):
                    other = source_scores(observation)[index] if observation else None
                    unit[name + "_contrast_nats"] = (
                        score - other
                        if score is not None and other is not None
                        else None
                    )
                unit["own_mask_drop_nats"] = unit["localized_excess_nats"] = None
                if (
                    args.ablations
                    and score is not None
                    and 0 < unit["start_ms"] < unit["end_ms"] < len(samples) / 16
                    and unit["end_ms"] - unit["start_ms"] >= 80
                ):
                    first, last = (
                        math.floor(unit["start_ms"] * 16),
                        math.ceil(unit["end_ms"] * 16),
                    )
                    controls = mask_controls(len(samples), first, last)
                    drops = []
                    for a, b in [(first, last), *controls]:
                        masked = samples.copy()
                        masked[a:b] = 0
                        observation = scorer.observe(
                            masked,
                            case["raw_line"],
                            case["language"],
                            case["targets"],
                            boundaries=False,
                        )
                        drops.append(score - source_scores(observation)[index])
                    unit.update(
                        mask_samples=[first, last],
                        control_mask_samples=controls,
                        mask_drops_nats=drops,
                        own_mask_drop_nats=drops[0],
                        localized_excess_nats=drops[0] - max(drops[1:])
                        if controls
                        else None,
                    )
                words.append(unit)
            row = {
                "id": case["id"],
                "song": case.get("song"),
                "identity_sha256": identity_sha,
                "crop_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
                "original": base,
                "silence": silence,
                "wrong_verse": wrong,
                "words": words,
                "seconds": time.monotonic() - began,
            }
            checkpoints.write_checkpoint(path, row, signature)
        records.append({"file": filename, "sha256": digest(path)})
        print(
            json.dumps(
                {"completed": number, "total": len(cases), "seconds": row["seconds"]}
            ),
            flush=True,
        )
    blind.write(
        args.output / "complete.json",
        {
            "identity_sha256": identity_sha,
            "records": records,
            "load_seconds": loaded_seconds,
            "seconds": time.monotonic() - start,
            "mlx_peak_bytes": mx.get_peak_memory(),
            "process_peak_rss_bytes": resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss,
        },
    )


if __name__ == "__main__":
    main()
