"""Private cap trial: blind lexical evidence plus independent English boundaries.

Whole English cues only. Neither source-script detection nor conditioned alignment
establishes language. Every added word still needs both blind recognition views.
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
from collections import Counter
from itertools import pairwise
from pathlib import Path

from english_ctc_words import verified_phone_views, word_observations
from hubertfa_research import ROOT, ResearchAligner, assets, digest, private_path

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa"), str(ROOT / "tifa/vendor")]
from english_boundaries import paired_boundary, recover_verified_boundaries
from english_timing import english_key

spec = importlib.util.spec_from_file_location(
    "hfa_benchmark", Path(__file__).with_name("benchmark-hubertfa.py")
)
checkpoints = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checkpoints)


def english_phones(converter, targets, vocabulary, *, cmu_fallback=False):
    """Complete spelling coverage; optional independently generated CMU hypothesis.

    Extended dictionary phones are never mapped or dropped. The fallback predicts
    a complete new pronunciation from spelling only, retaining its distinct role.
    """
    aliases, reference = {}, []
    for index, target in enumerate(targets):
        text = target.get("expected_text", target["text"])
        if not english_key(text):
            return None
        parts = converter.convert(text)
        if not parts or english_key("".join(p.text for p in parts)) != english_key(
            text
        ):
            return None
        phones = []
        for part in parts:
            piece = [p for group in part.readings[0].paths[0] for p in group.phonemes]
            if cmu_fallback and any(
                p not in vocabulary or vocabulary[p] == 0 for p in piece
            ):
                choices = converter.infer_oov(part.text.lower())
                piece = choices[0] if choices else []
            if not piece:
                return None
            phones.extend(piece)
        if not phones or any(p not in vocabulary or vocabulary[p] == 0 for p in phones):
            return None
        aliases[index] = {"language": "en", "phones": phones}
        reference.extend({"word": index, "phone": p} for p in phones)
    return aliases, reference


def whole_word_envelopes(reference, predicted, targets):
    """A whole supplied phone path defines one envelope, never new subword clocks."""
    if len(reference) != len(predicted) or any(
        (a["word"], a["phone"]) != (b["word"], b["phone"])
        for a, b in zip(reference, predicted, strict=True)
    ):
        raise ValueError("Changed English phone ownership.")
    result = []
    for index, target in enumerate(targets):
        units = [p for r, p in zip(reference, predicted) if r["word"] == index]
        complete = (
            bool(units)
            and all(0 <= p["start_ms"] < p["end_ms"] for p in units)
            and all(a["end_ms"] <= b["start_ms"] for a, b in pairwise(units))
        )
        result.append(
            {
                "raw_span": target["raw_span"],
                "start_ms": units[0]["start_ms"] if complete else -1,
                "end_ms": units[-1]["end_ms"] if complete else -1,
                "complete": complete,
            }
        )
    return result


def main():
    import numpy as np
    from g2p.converters.base import G2PConversionError
    from scipy.signal import resample_poly
    from tifa_helper import Aligner, prepare_model

    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--lexical", type=Path, required=True)
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--pronunciation", choices=("dictionary", "cmu-fallback"), default="dictionary"
    )
    parser.add_argument(
        "--lexical-mode", choices=("whisper", "singing-ctc"), default="whisper"
    )
    args = parser.parse_args()
    for name in vars(args):
        if isinstance(getattr(args, name), Path):
            setattr(args, name, private_path(getattr(args, name)))
    suite = json.loads(args.suite.read_text())
    context = json.loads((args.contexts / "suite-contexts.json").read_text())
    signature = json.loads((args.lexical / "identity.json").read_text())
    if (
        signature["suite"] != digest(args.suite)
        or signature["contexts"] != digest(args.contexts / "suite-contexts.json")
        or signature["lexical_policy"]
        != digest(ROOT / "refinement/english_boundaries.py")
        or signature["recognition"]["partial"]
        or context["identity_sha256"] != digest(args.contexts / "identity.json")
        or signature["records_sha256"] != digest(args.lexical / "private-records.json")
    ):
        raise ValueError("Changed/incomplete source-owned lexical observations.")
    recipes = {
        "lexical_identity": digest(args.lexical / "identity.json"),
        "lexical_records": digest(args.lexical / "private-records.json"),
        "suite": digest(args.suite),
        "models": assets(args.model_directory),
        "archive": digest(args.archive),
        "runner": digest(Path(__file__)),
        "hfa_adapter": digest(Path(__file__).with_name("hubertfa_research.py")),
        "tifa": digest(ROOT / "tifa/tifa_helper.py"),
        "policy": digest(ROOT / "refinement/english_boundaries.py"),
        "pronunciation": args.pronunciation,
        "lexical_mode": args.lexical_mode,
        "ctc_policy": digest(ROOT / "scripts/english_ctc_words.py"),
    }
    args.output.mkdir(parents=True, mode=0o700, exist_ok=True)
    identity_path = args.output / "identity.json"
    if identity_path.exists():
        if json.loads(identity_path.read_text()) != recipes:
            raise ValueError("Changed completed boundary trial identity.")
    else:
        checkpoints.write(identity_path, recipes)
    tifa = Aligner(prepare_model(args.archive))
    singing = ResearchAligner(args.model_directory, "mps")
    songs = {r["track"]: r for r in suite["songs"]}
    cached = {r["track"]: r for r in context["songs"]}
    waveforms, counts, output = {}, {}, []
    for track, song in songs.items():
        for field, expected in (("path", "sha256"), ("result_path", "result_sha256")):
            if digest(Path(song[field])) != song[expected]:
                raise ValueError("Changed immutable Rust input/source result.")
        saved = json.loads(Path(song["result_path"]).read_text())
        counts[track] = Counter(
            original_timed=saved["timed_words"], original_words=saved["total_words"]
        )
        if not cached[track]["eligible"]:
            continue
        receipt = args.contexts / track / "stem.json"
        stem = json.loads(receipt.read_text())
        if (
            digest(receipt) != cached[track]["stem_receipt_sha256"]
            or digest(Path(song["pcm"])) != stem["original_pcm_sha256"]
            or digest(Path(stem["path"])) != stem["sha256"]
        ):
            raise ValueError("Changed private vocals or original audio.")
        waveforms[track] = {
            "kim": np.memmap(stem["path"], dtype="<f4", mode="r"),
            "mix": np.memmap(song["pcm"], dtype="<f4", mode="r"),
        }
    started = time.monotonic()
    for record in json.loads((args.lexical / "private-records.json").read_text()):
        track, targets, crop = record["track"], record["targets"], record["crop"]
        count = counts[track]
        if not any(
            old["start_ms"] < 0
            and (
                args.lexical_mode == "singing-ctc"
                or a["source_match"]
                and b["source_match"]
            )
            for old, a, b in zip(record["baseline"], *record["views"], strict=True)
        ):
            continue
        if not all(english_key(t.get("expected_text", t["text"])) for t in targets):
            count["mixed_cue_withheld"] += 1
            continue
        try:
            pronunciation = english_phones(
                tifa.converters["en"],
                targets,
                singing.vocab["vocab"],
                cmu_fallback=args.pronunciation == "cmu-fallback",
            )
        except (G2PConversionError, KeyError):
            pronunciation = None
        if pronunciation is None:
            count["incomplete_english_pronunciation"] += 1
            continue
        aliases, reference = pronunciation
        path = args.output / f"{track}-{record['occurrence']}.json"
        if path.exists():
            row = checkpoints.read_checkpoint(path, recipes)
        else:
            samples = np.asarray(
                waveforms[track]["kim"][crop["start_sample"] : crop["end_sample"]]
            )
            raw = []
            with contextlib.redirect_stdout(io.StringIO()):
                tifa.align(samples, targets, diagnostics=raw, phonetic_aliases=aliases)
            matrices = []
            phones, diagnostics = singing.infer(
                resample_poly(samples, 441, 160).astype(np.float32),
                reference,
                ctc_observer=matrices.append
                if args.lexical_mode == "singing-ctc"
                else None,
            )
            envelopes = whole_word_envelopes(reference, phones, targets)
            length_ms = len(samples) / 16
            views = record["views"]
            if args.lexical_mode == "singing-ctc":
                ctc_units = [
                    word_observations(
                        matrices[0], reference, singing.vocab["vocab"], targets
                    )
                ]
                original = np.asarray(
                    waveforms[track]["mix"][crop["start_sample"] : crop["end_sample"]]
                )
                singing.infer(
                    resample_poly(original, 441, 160).astype(np.float32),
                    reference,
                    ctc_observer=matrices.append,
                )
                ctc_units.append(
                    word_observations(
                        matrices[1], reference, singing.vocab["vocab"], targets
                    )
                )
                views = [
                    verified_phone_views(units, length_ms=length_ms)
                    for units in ctc_units
                ]
            result = recover_verified_boundaries(
                record["baseline"],
                targets,
                raw,
                envelopes,
                views,
                length_ms,
                source_words=record["source_word_count"],
            )
            row = {
                "track": track,
                "occurrence": record["occurrence"],
                "tifa": raw,
                "hfa": envelopes,
                "hfa_diagnostics": diagnostics,
                "recognition_views": views,
                "result": result,
            }
            checkpoints.write_checkpoint(path, row, recipes)
        for old, new, a, b in zip(
            record["baseline"], row["result"], row["tifa"], row["hfa"], strict=True
        ):
            if old["start_ms"] >= 0:
                count["moved"] += new != old
                count["lost"] += new["start_ms"] < 0
                continue
            count["paired_boundary_gaps"] += (
                paired_boundary(a, b, (crop["end_sample"] - crop["start_sample"]) / 16)
                is not None
            )
            count["added"] += new["start_ms"] >= 0
        count["tested_cues"] += 1
        output.append(row)
        print(
            json.dumps(
                {
                    "track": track,
                    "tested_cues": count["tested_cues"],
                    "added": count["added"],
                }
            ),
            flush=True,
        )
    summary = {
        "per_track": counts,
        "added": sum(c["added"] for c in counts.values()),
        "lost": sum(c["lost"] for c in counts.values()),
        "moved": sum(c["moved"] for c in counts.values()),
        "seconds": time.monotonic() - started,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "app_data_changed": False,
        "accuracy_certified": False,
    }
    checkpoints.write(args.output / "summary.json", summary)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
