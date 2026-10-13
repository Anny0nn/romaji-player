"""Independent MMS evidence on original PJS vocals and a real Kim-derived view.

This stage consumes waveform identities only; no reference phones enter inference.
Models run sequentially. Private evidence is for research, not an app document.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import resource
import sys
import time
from pathlib import Path

from audio_first_models import ROOT, digest

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
spec = importlib.util.spec_from_file_location(
    "blind_runner", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)


def main():
    import numpy as np
    import soundfile as sf
    import torch
    from refinement_helper import mms, separate, verify_assets
    from scipy.signal import resample_poly

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output, manifest = args.output.resolve(), args.manifest.resolve()
    if ROOT in output.parents or ROOT in manifest.parents:
        parser.error("Private waveforms and evidence must remain outside the checkout.")
    cases = blind.manifest_cases(json.loads(manifest.read_text()))
    selected = {c["recording"] for c in json.loads(args.cases.read_text())["cases"]}
    cases = [c for c in cases if c["id"] in selected]
    if {c["id"] for c in cases} != selected:
        raise ValueError("Challenge audio is incomplete.")
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.umask(0o077)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    torch.set_num_threads(4)
    verify_assets(args.models)
    provenance = {
        "manifest_sha256": digest(manifest),
        "cases_sha256": digest(args.cases),
        "model_manifest_sha256": digest(
            ROOT / "refinement/refinement-model-files.json"
        ),
        "implementation_sha256": digest(Path(__file__)),
        "mms_adapter_sha256": digest(ROOT / "refinement/refinement_helper.py"),
        "view_contract": "original mono vocals and Kim-derived stereo-duplicated mono; correlated views",
    }
    blind.write(output / "recipe.json", provenance)
    began = time.monotonic()
    views, source_hashes, cache = [[], []], {}, {}
    for number, case in enumerate(cases, 1):
        original = blind.load_samples(case, manifest.parent, cache)
        path = (manifest.parent / case["path"]).resolve()
        # PJS is one complete mono recording per case, with original 48 kHz vocals.
        waveform, rate = sf.read(path, dtype="float32")
        if rate != 48000 or waveform.ndim != 1 or case["first_sample"] != 0:
            raise ValueError("Unexpected full-recording PJS separation input.")
        stereo = np.repeat(resample_poly(waveform, 147, 160)[None, :], 2, axis=0)
        start = time.monotonic()
        kim = separate(
            stereo, len(original), args.models, "Kim", output / "progress.txt"
        )
        source_hashes[case["id"]] = {
            "audio_sha256": case["sha256"],
            "original_crop_sha256": hashlib.sha256(original.tobytes()).hexdigest(),
            "kim_sha256": hashlib.sha256(kim.tobytes()).hexdigest(),
            "separation_seconds": time.monotonic() - start,
        }
        views[0].append(original)
        views[1].append(kim)
        print(json.dumps({"separated": number, "total": len(cases)}), flush=True)
    records = []
    for view, clips in enumerate(views):
        chunks, crops, offset = [], [], 0
        for case, samples in zip(cases, clips, strict=True):
            crops.append((case["id"], offset, offset + len(samples), []))
            padding = (-len(samples)) % 16
            chunks.extend([samples, np.zeros(padding, dtype=np.float32)])
            offset += len(samples) + padding
        started = time.monotonic()
        evidence = mms(
            np.concatenate(chunks),
            crops,
            args.models / "mms",
            output / "progress.txt",
            f"PJS verifier view {view}",
            posteriors=True,
        )
        for case, (logp, blank) in zip(cases, evidence, strict=True):
            name = f"{case['id']}-view{view}.npz"
            np.savez(output / name, logp=logp, blank=blank)
            records.append(
                {
                    "id": case["id"],
                    "view": view,
                    "file": name,
                    "sha256": digest(output / name),
                }
            )
        print(
            json.dumps({"completed_view": view, "seconds": time.monotonic() - started}),
            flush=True,
        )
        del evidence
    blind.write(
        output / "complete.json",
        {
            "recipe_sha256": digest(output / "recipe.json"),
            "records": records,
            "audio": source_hashes,
            "vocabulary": json.loads((args.models / "mms/vocab.json").read_text()),
            "total_seconds": time.monotonic() - began,
            "process_lifetime_peak_rss_bytes": resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss,
        },
    )


if __name__ == "__main__":
    main()
