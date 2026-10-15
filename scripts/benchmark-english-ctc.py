"""Opened NUS development only: acoustic CTC veto and paired word boundaries.

No orthographic gold exists in these labels. Unknown spelling and the unopened
reserve stay untouched. Wrong-phone controls test the veto, not a full new recipe.
"""

import argparse
import contextlib
import importlib.util
import io
import json
import os
import resource
import sys
import time
from pathlib import Path

from english_ctc_words import verified_phone_views, word_observations
from english_phone_reference import labels, phrase_groups
from hubertfa_research import ROOT, ResearchAligner, assets, digest, private_path
from singing_reference import evaluate

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
from english_boundaries import lexical_support, paired_boundary


def load_tool(name):
    spec = importlib.util.spec_from_file_location(
        name.replace("-", "_"), ROOT / f"scripts/{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checkpoints = load_tool("benchmark-hubertfa")
envelopes = load_tool("probe-english-boundaries").whole_word_envelopes


def admitted(candidate, unit, view):
    return (
        candidate is not None
        and view["source_match"]
        and lexical_support(view)
        and all(abs(candidate[k] - unit[k]) <= 150 for k in ("start_ms", "end_ms"))
    )


def main():
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    from tifa_helper import Aligner, prepare_model

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for name in vars(args):
        setattr(args, name, private_path(getattr(args, name)))
    os.umask(0o077)
    manifest = json.loads(args.manifest.read_text())
    dev, reserve = manifest["development"], manifest["heldout"]
    if not dev or not reserve or len(set(dev + reserve)) != len(dev + reserve):
        raise ValueError("Overlapping development/reserve selection.")
    songs = {s["id"]: s for s in manifest["songs"]}
    signature = {
        "manifest": digest(args.manifest),
        "partition": "development",
        "assets": assets(args.model_directory),
        "archive": digest(args.archive),
        "english_policy": digest(ROOT / "refinement/english_boundaries.py"),
        "tifa_helper": digest(ROOT / "tifa/tifa_helper.py"),
        "code": {
            name: digest(ROOT / f"scripts/{name}.py")
            for name in (
                "benchmark-english-ctc",
                "hubertfa_research",
                "english_ctc_words",
                "probe-english-boundaries",
                "benchmark-hubertfa",
                "english_phone_reference",
            )
        },
        "inputs": {
            name: {
                field: digest(private_path(songs[name][field]))
                for field in ("audio", "annotation")
            }
            for name in dev
        },
        "gates": {
            "minimum_phone_probability": 0.45,
            "confidence_kind": "singing-ctc; no Whisper word-confidence threshold",
            "greedy_agreement": 0.90,
            "boundary_tolerance_ms": 150,
        },
    }
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    checkpoints.write(args.output / "identity.json", signature)
    tifa = Aligner(prepare_model(args.archive))
    backend = ResearchAligner(args.model_directory, "mps")
    result, ctc_only = [], []
    wrong_checked = wrong_admitted = 0
    started = time.monotonic()
    for name in dev:
        song = songs[name]
        waveform, rate = sf.read(song["audio"], dtype="float32")
        if rate != 44100 or waveform.ndim != 1 or not np.isfinite(waveform).all():
            raise ValueError("Changed development waveform clock.")
        refs = labels(Path(song["annotation"]).read_text(), len(waveform) / 44.1)
        for index, phrase in enumerate(phrase_groups(refs)):
            first = max(0, int((phrase[0]["start_ms"] - 500) * 44.1))
            last = min(len(waveform), int((phrase[-1]["end_ms"] + 300) * 44.1))
            if last - first > 44100 * 30:
                raise ValueError("Unexpected overlong development phrase.")
            reference = [
                {
                    **r,
                    "start_ms": r["start_ms"] - first / 44.1,
                    "end_ms": r["end_ms"] - first / 44.1,
                }
                for r in phrase
            ]
            owners = list(dict.fromkeys(r["word"] for r in reference))
            source = [
                {"word": owners.index(r["word"]), "phone": r["phone"]}
                for r in reference
            ]
            targets = [
                {"raw_span": [i * 2, i * 2 + 1], "text": "word", "romaji": "word"}
                for i in range(len(owners))
            ]
            matrices = []
            pred, diagnostic = backend.infer(
                waveform[first:last], source, ctc_observer=matrices.append
            )
            singing = envelopes(source, pred, targets)
            units = word_observations(
                matrices[0], source, backend.vocab["vocab"], targets
            )
            length_ms = (last - first) / 44.1
            views = verified_phone_views(units, length_ms=length_ms)
            aliases = {
                i: {
                    "language": "en",
                    "phones": [r["phone"] for r in source if r["word"] == i],
                }
                for i in range(len(targets))
            }
            raw = []
            with contextlib.redirect_stdout(io.StringIO()):
                tifa.align(
                    resample_poly(waveform[first:last], 160, 441).astype(np.float32),
                    targets,
                    diagnostics=raw,
                    phonetic_aliases=aliases,
                )
            gold = checkpoints.word_records(
                [
                    {
                        "id": f"{name}:{index}",
                        "reference": reference,
                        "predicted": reference,
                    }
                ],
                supported=False,
            )[0]["reference"]
            predicted = []
            for ref, a, b, c, v in zip(gold, raw, singing, units, views, strict=True):
                pair = paired_boundary(a, b, length_ms)
                okay = admitted(pair, c, v)
                predicted.append(
                    {
                        **ref,
                        "start_ms": pair["start_ms"] if okay else -1,
                        "end_ms": pair["end_ms"] if okay else -1,
                    }
                )
            result.append(
                {"id": f"{name}:{index}", "reference": gold, "predicted": predicted}
            )
            ctc_only.append(
                {
                    "id": f"{name}:{index}",
                    "reference": gold,
                    "predicted": [
                        {
                            **ref,
                            "start_ms": u["start_ms"]
                            if v["source_match"] and lexical_support(v)
                            else -1,
                            "end_ms": u["end_ms"]
                            if v["source_match"] and lexical_support(v)
                            else -1,
                        }
                        for ref, u, v in zip(gold, units, views, strict=True)
                    ],
                }
            )
            # Three deterministic substitutions per word; unchanged audio/frames.
            vocabulary = backend.vocab["vocab"]
            inventory = [p for p in vocabulary if vocabulary[p] != 0]
            for owner in range(len(targets)):
                location = next(i for i, r in enumerate(source) if r["word"] == owner)
                for delta in (1, 7, 19):
                    changed = [dict(r) for r in source]
                    old = inventory.index(changed[location]["phone"])
                    changed[location]["phone"] = inventory[
                        (old + delta) % len(inventory)
                    ]
                    alternative = word_observations(
                        matrices[0], changed, vocabulary, targets
                    )
                    view = verified_phone_views(alternative, length_ms=length_ms)[owner]
                    wrong_checked += 1
                    wrong_admitted += view["source_match"] and lexical_support(view)
            checkpoints.write_checkpoint(
                args.output / f"{name}-{index}.json",
                {"ctc": units, "pair": result[-1], "diagnostic": diagnostic},
                signature,
            )
            print(
                json.dumps(
                    {
                        "phrase": index,
                        "wrong_checked": wrong_checked,
                        "wrong_admitted": wrong_admitted,
                    }
                ),
                flush=True,
            )
    summary = {
        "boundary_only": True,
        "orthographic_gold": False,
        "ctc_only": {**evaluate(ctc_only), "granularity": "human_sp_word_group"},
        "paired": {**evaluate(result), "granularity": "human_sp_word_group"},
        "wrong_phone_veto_controls": {
            "checked": wrong_checked,
            "admitted": wrong_admitted,
        },
        "seconds": time.monotonic() - started,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "heldout_opened": False,
    }
    checkpoints.write(args.output / "summary.json", summary)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
