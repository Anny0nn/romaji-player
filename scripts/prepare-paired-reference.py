"""Fresh independent TIFA/HubertFA word clocks for private source-contrast fixtures.

Supplied source text is an alignment candidate. Human reference boundaries never
enter inference or mask placement. Paired clocks still need acoustic verification.
"""

import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys
from pathlib import Path

from hubertfa_research import ROOT, ResearchAligner, assets, digest, private_path

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
from english_boundaries import paired_boundary
from english_ctc_words import word_observations

spec = importlib.util.spec_from_file_location(
    "boundary_probe", ROOT / "scripts/probe-english-boundaries.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
audio_spec = importlib.util.spec_from_file_location(
    "blind_audio", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(audio_spec)
audio_spec.loader.exec_module(blind)


def main():
    import numpy as np
    from scipy.signal import resample_poly
    from tifa_helper import Aligner, prepare_model

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--hfa-models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--observe-ctc", action="store_true")
    args = parser.parse_args()
    args.manifest, args.archive, args.hfa_models, args.output = map(
        private_path, (args.manifest, args.archive, args.hfa_models, args.output)
    )
    manifest = json.loads(args.manifest.read_text())
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    identity = {
        "parent_manifest_sha256": digest(args.manifest),
        "tifa_archive_sha256": digest(args.archive),
        "hfa_assets": assets(args.hfa_models),
        "code": {
            name: digest(ROOT / name)
            for name in (
                "scripts/prepare-paired-reference.py",
                "scripts/probe-english-boundaries.py",
                "scripts/hubertfa_research.py",
                "scripts/english_ctc_words.py",
                "refinement/english_boundaries.py",
                "tifa/tifa_helper.py",
            )
        },
        "mask_source": "paired independently observed original-audio boundaries; no human boundary input",
        "observe_ctc": args.observe_ctc,
    }
    tifa = Aligner(prepare_model(args.archive))
    hfa = ResearchAligner(args.hfa_models, "mps")
    output, records, cache = [], [], {}
    for case in manifest["cases"]:
        if case["language"] != "en":
            raise ValueError(
                "English phone-pair prototype requires explicit source language."
            )
        targets = [{**u, "romaji": u["text"]} for u in case["targets"]]
        pronunciation = probe.english_phones(
            tifa.converters["en"], targets, hfa.vocab["vocab"], cmu_fallback=True
        )
        samples = blind.load_samples(
            {"id": case["id"], **case["audio"]}, args.manifest.parent, cache
        )
        clocks = [
            {"raw_span": t["raw_span"], "start_ms": -1, "end_ms": -1} for t in targets
        ]
        raw, envelopes, ctc_words = [], [], []
        if pronunciation:
            aliases, reference = pronunciation
            with contextlib.redirect_stdout(io.StringIO()):
                tifa.align(samples, targets, diagnostics=raw, phonetic_aliases=aliases)
            matrices = []
            phones, _ = hfa.infer(
                resample_poly(samples, 441, 160).astype(np.float32),
                reference,
                ctc_observer=matrices.append if args.observe_ctc else None,
            )
            if args.observe_ctc:
                ctc_words = word_observations(
                    matrices[0], reference, hfa.vocab["vocab"], targets
                )
            envelopes = probe.whole_word_envelopes(reference, phones, targets)
            clocks = [
                paired_boundary(a, b, len(samples) / 16) or empty
                for a, b, empty in zip(raw, envelopes, clocks, strict=True)
            ]
        output.append(
            {
                **case,
                "mask_boundary_units": clocks,
                "mask_boundary_kind": "original TIFA-HubertFA pair",
            }
        )
        records.append(
            {
                "id": case["id"],
                "tifa": raw,
                "hfa": envelopes,
                "paired": clocks,
                "ctc_words": ctc_words,
            }
        )
    (args.output / "private-observations.json").write_text(
        json.dumps(
            {"identity": identity, "records": records}, indent=2, allow_nan=False
        )
    )
    prepared = {
        "identity": {
            **identity,
            "private_observations_sha256": digest(
                args.output / "private-observations.json"
            ),
        },
        "cases": output,
    }
    (args.output / "manifest.json").write_text(
        json.dumps(prepared, indent=2, allow_nan=False)
    )
    print(
        json.dumps(
            {
                "cases": len(output),
                "original_groups": sum(len(c["targets"]) for c in output),
                "paired_clocks": sum(
                    u["start_ms"] >= 0 for c in output for u in c["mask_boundary_units"]
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
