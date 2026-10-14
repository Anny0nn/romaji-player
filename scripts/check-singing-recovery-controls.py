"""Run timing recovery on privately prepared silence/instrumental/wrong-verse controls."""

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path

from audio_first_models import ROOT, digest, load_romaji

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]


def main():
    import numpy as np
    from singing_recovery import recover
    from tifa_helper import Aligner, prepare_model

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if ROOT in args.output.resolve().parents:
        parser.error("Private inputs/results stay outside git.")
    cases = json.loads(args.cases.read_text())
    if not cases or any(not c["id"].startswith("control:") for c in cases):
        raise ValueError("Use a control-only case manifest.")
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.umask(0o077)
    infer, meta = load_romaji(args.models)
    evidence, cache = {}, {}
    for n, case in enumerate(cases):
        path = Path(case["pcm"])
        if path not in cache:
            if digest(path) != case["audio_sha256"]:
                raise ValueError("Control audio changed.")
            cache = {path: np.memmap(path, dtype="<f4", mode="r")}
        samples = np.array(
            cache[path][case["start_ms"] * 16 : case["end_ms"] * 16], copy=True
        )
        matrix = infer(samples)["romaji"]
        if not np.isfinite(matrix).all():
            raise ValueError("Nonfinite singing control output.")
        filename = f"{n}.npz"
        np.savez_compressed(args.output / filename, logp=matrix)
        evidence[case["id"]] = filename
    del infer
    from refinement_helper import release

    release()
    aligner = Aligner(prepare_model(args.archive))
    rows = []
    for case in cases:
        path = Path(case["pcm"])
        samples = np.array(
            np.memmap(path, dtype="<f4", mode="r")[
                case["start_ms"] * 16 : case["end_ms"] * 16
            ],
            copy=True,
        )
        targets = [
            {
                "raw_span": w["raw_span"],
                "text": "".join(c for c in w["hiragana"] if c.isalnum()),
                "romaji": w["romaji"],
            }
            for w in case["words"]
        ]
        baseline = [
            {"raw_span": t["raw_span"], "start_ms": -1, "end_ms": -1} for t in targets
        ]
        with (
            np.load(args.output / evidence[case["id"]], allow_pickle=False) as saved,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = recover(
                samples,
                [(0, 0, len(samples), targets)],
                aligner,
                [(saved["logp"], meta["blank"])],
                meta["heads"]["romaji"],
                [baseline],
                {"0": len(targets)},
                lambda _: None,
            )[0]
        rows.append(
            {
                "id": case["id"],
                "words": len(targets),
                "admitted": sum(u["start_ms"] >= 0 for u in result),
            }
        )
    (args.output / "results.json").write_text(json.dumps(rows))
    summary = {
        "cases": len(rows),
        "words": sum(r["words"] for r in rows),
        "admitted": sum(r["admitted"] for r in rows),
        "cases_sha256": digest(args.cases),
        "model": meta,
    }
    (args.output / "summary.json").write_text(json.dumps(summary))
    print(json.dumps({k: summary[k] for k in ("cases", "words", "admitted")}))
    if summary["admitted"]:
        raise SystemExit(
            "Unexpected control admission; review privately before adoption."
        )


if __name__ == "__main__":
    main()
