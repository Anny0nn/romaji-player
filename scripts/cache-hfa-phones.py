"""Cache source-blind HubertFA CTC posteriors without a supplied phone path.

The phone and alignment heads share an encoder. These are observed probabilities,
not calibrated word confidence or evidence of orthographic spelling.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import time
from pathlib import Path

from hubertfa_research import ROOT, ResearchAligner, assets, digest, private_path

spec = importlib.util.spec_from_file_location(
    "blind_audio", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)


def main():
    import numpy as np
    from scipy.signal import resample_poly

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
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    identity = {
        "manifest_sha256": digest(args.manifest),
        "assets": assets(args.model_directory),
        "code": {
            name: digest(ROOT / "scripts" / name)
            for name in (
                "cache-hfa-phones.py",
                "hubertfa_research.py",
                "recognize-singing-phones.py",
            )
        },
        "input": "audio only; no supplied source or phoneme sequence",
        "blank": 0,
        "frame_ms": 10,
        "receptive_ms": 10,
    }
    model = ResearchAligner(args.model_directory, "mps")
    identity["vocabulary"] = model.vocab["vocab"]
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2))
    identity_sha = digest(args.output / "identity.json")
    cache = {}
    records = []
    started = time.monotonic()
    for case in cases:
        samples = blind.load_samples(case, args.manifest.parent, cache)
        if len(samples) > 480000:
            raise ValueError("CTC cache pilot exceeds 30 seconds.")
        matrices = []
        model.infer(
            resample_poly(samples, 441, 160).astype(np.float32),
            ctc_observer=matrices.append,
        )
        if (
            len(matrices) != 1
            or not np.isfinite(matrices[0]).all()
            or not np.allclose(np.logaddexp.reduce(matrices[0], axis=1), 0, atol=1e-4)
        ):
            raise ValueError("Invalid audio-only phone matrix.")
        stem = hashlib.sha256(case["id"].encode()).hexdigest()
        path = args.output / (stem + ".npz")
        np.savez_compressed(path, logp=matrices[0], blank=0)
        row = {
            "case": case,
            "identity_sha256": identity_sha,
            "posterior": path.name,
            "posterior_sha256": digest(path),
        }
        record = args.output / (stem + ".json")
        record.write_text(json.dumps(row, indent=2))
        records.append({"file": record.name, "sha256": digest(record)})
        print(json.dumps({"completed": len(records), "total": len(cases)}), flush=True)
    complete = {
        "identity_sha256": identity_sha,
        "records": records,
        "seconds": time.monotonic() - started,
    }
    (args.output / "complete.json").write_text(json.dumps(complete, indent=2))
    print(json.dumps({"cases": len(records), "seconds": complete["seconds"]}))


if __name__ == "__main__":
    main()
