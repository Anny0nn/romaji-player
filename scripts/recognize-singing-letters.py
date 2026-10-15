"""Blind private CTC letter recognition on bounded audio-only crop manifests.

No lyric prompts, lexicon, hotwords or source text. Original lead and secondary
heads share their encoder and are correlated evidence, never independent votes.
"""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import resource
import time
from pathlib import Path

from audio_first_ctc import greedy
from hubertfa_research import ROOT, digest, private_path
from singing_letters import decode_letters, load

spec = importlib.util.spec_from_file_location(
    "blind_audio", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)


def main():
    import numpy as np
    import torch

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.manifest, args.model_directory, args.output = map(
        private_path, (args.manifest, args.model_directory, args.output)
    )
    cases = blind.manifest_cases(json.loads(args.manifest.read_text()))
    os.umask(0o077)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    torch.set_num_threads(4)
    started = time.monotonic()
    infer, model = load(args.model_directory)
    load_seconds = time.monotonic() - started
    identity = {
        "manifest_sha256": digest(args.manifest),
        "model": model,
        "code": {
            name: digest(ROOT / "scripts" / name)
            for name in (
                "recognize-singing-letters.py",
                "singing_letters.py",
                "audio_first_ctc.py",
                "recognize-singing-phones.py",
            )
        },
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("torch", "transformers", "safetensors", "numpy")
        },
        "decoder": "unmasked audio-only greedy CTC; no lexicon or source input",
    }
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    blind.write(args.output / "identity.json", identity)
    identity_sha = digest(args.output / "identity.json")
    records, cache = [], {}
    for number, case in enumerate(cases, 1):
        began = time.monotonic()
        samples = blind.load_samples(case, args.manifest.parent, cache)
        if len(samples) > 480000:
            raise ValueError("Singing letter pilot exceeds30seconds.")
        stem = hashlib.sha256(case["id"].encode()).hexdigest()
        heads = {}
        for name, logp in infer(samples).items():
            if (
                logp.ndim != 2
                or logp.shape[1] != 32
                or not np.isfinite(logp).all()
                or not np.allclose(np.logaddexp.reduce(logp, axis=-1), 0, atol=1e-4)
            ):
                raise ValueError("Invalid unmasked letter probabilities.")
            filename = stem + "-" + name + ".npz"
            np.savez_compressed(args.output / filename, logp=logp, blank=model["blank"])
            hypothesis = greedy(logp, model["blank"])
            heads[name] = {
                "greedy": hypothesis,
                "text": decode_letters(hypothesis["token_ids"], model["vocabulary"]),
                "posterior": filename,
                "posterior_sha256": digest(args.output / filename),
            }
        row = {
            "id": case["id"],
            "case": case,
            "identity_sha256": identity_sha,
            "crop_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
            "heads": heads,
            "seconds": time.monotonic() - began,
        }
        path = args.output / (stem + ".json")
        blind.write(path, row)
        records.append({"file": path.name, "sha256": digest(path)})
        torch.mps.empty_cache()
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
            "load_seconds": load_seconds,
            "seconds": time.monotonic() - started,
            "process_peak_rss_bytes": resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss,
            "mps_current_allocated_bytes": torch.mps.current_allocated_memory(),
            "mps_driver_allocated_bytes": torch.mps.driver_allocated_memory(),
        },
    )


if __name__ == "__main__":
    main()
