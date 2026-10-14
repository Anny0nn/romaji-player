"""Private TIFA + singing CTC replay of English pronunciation alternatives."""

import argparse
import contextlib
import io
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from audio_first_evaluation import read_run
from audio_first_models import ROOT, digest
from english_singing_phones import japanese_hypothesis
from mac_completeness_inputs import load_suite
from singing_word_alignment import word_alignment

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]


def main():
    import numpy as np
    from english_timing import english_key
    from refinement_policy import agree, coherent_line, recover_gaps, supported_raw
    from singing_phonemes import kana_phones
    from tifa_helper import Aligner, prepare_model

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--recognition", type=Path, required=True)
    parser.add_argument("--audio-manifest", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--mode", choices=("direct", "loan"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if ROOT in args.output.resolve().parents:
        parser.error("Private source and timings must stay outside the checkout.")
    _, suite, hashes = load_suite(args.manifest)
    recipe, recognition, _ = read_run(args.recognition, args.audio_manifest)
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.umask(0o077)
    aligner = Aligner(prepare_model(args.archive))
    began, totals, records, cache = time.monotonic(), defaultdict(Counter), [], {}
    for number, row in enumerate(suite, 1):
        case, words, baseline = row["kim"], row["words"], row["baseline"]
        counts = totals[case["track"]]
        counts["words"] += len(words)
        counts["baseline"] += sum(u["start_ms"] >= 0 for u in baseline)
        nominated = [
            i
            for i, (w, b) in enumerate(zip(words, baseline, strict=True))
            if b["start_ms"] < 0 and english_key(w["expected_text"])
        ]
        if not nominated:
            continue
        targets = [
            {"raw_span": w["raw_span"], "text": w["hiragana"], "romaji": w["romaji"]}
            for w in words
        ]
        aliases, source_phones = {}, []
        for index, target in enumerate(targets):
            if english_key(words[index]["expected_text"]):
                converted = aligner.converters["en"].convert(
                    words[index]["expected_text"]
                )
                phonemes = (
                    [
                        phone
                        for part in converted
                        for group in part.readings[0].paths[0]
                        for phone in group.phonemes
                    ]
                    if converted
                    else []
                )
                phones = japanese_hypothesis(phonemes, args.mode)
                aliases[index] = phones
                source_phones.append(phones)
            else:
                source_phones.append(kana_phones(target["text"], target["romaji"]))

        path = Path(case["pcm"])
        if path not in cache:
            if digest(path) != case["audio_sha256"]:
                raise ValueError("Vocal audio changed.")
            cache = {path: np.memmap(path, dtype="<f4", mode="r")}
        samples = np.array(
            cache[path][case["start_ms"] * 16 : case["end_ms"] * 16], copy=True
        )
        raw = []
        with contextlib.redirect_stdout(io.StringIO()):
            trial = aligner.align(
                samples, targets, diagnostics=raw, phonetic_aliases=aliases
            )
        acoustic = recognition[row["id"]]
        if (
            acoustic["case"]["sha256"] != case["audio_sha256"]
            or acoustic["case"]["first_sample"] != case["start_ms"] * 16
            or acoustic["case"]["last_sample"] != case["end_ms"] * 16
        ):
            raise ValueError("Independent evidence uses another vocal window.")
        posterior = acoustic["heads"]["romaji"]["posterior"]
        with np.load(args.recognition / posterior, allow_pickle=False) as archive:
            independent = word_alignment(
                archive["logp"],
                int(archive["blank"]),
                targets,
                recipe["model"]["heads"]["romaji"],
                word_phones=source_phones,
            )
        candidates = supported_raw(
            {"units": trial, "raw_units": raw}, independent, len(samples) // 16
        )
        for i in range(len(candidates)):
            if (
                i not in nominated
                or independent[i]["mean_probability"] < 0.45
                or not agree(candidates[i], independent[i], 150)
            ):
                candidates[i] = {**candidates[i], "start_ms": -1, "end_ms": -1}
        combined = [
            trial[i] if baseline[i]["start_ms"] >= 0 else candidates[i]
            for i in range(len(words))
        ]
        coherent = coherent_line(combined, independent, len(words))
        repaired = (
            recover_gaps(baseline, candidates, independent) if coherent else baseline
        )
        for i in nominated:
            gained = baseline[i]["start_ms"] < 0 <= repaired[i]["start_ms"]
            counts["nominated"] += 1
            counts["supported"] += candidates[i]["start_ms"] >= 0
            counts["gains"] += gained
            records.append(
                {
                    "id": row["id"],
                    "track": case["track"],
                    "raw_span": targets[i]["raw_span"],
                    "phones": aliases.get(i),
                    "before": baseline[i],
                    "after": repaired[i],
                    "diagnostic": raw[i],
                    "independent": independent[i],
                    "coherent": coherent,
                    "gained": gained,
                }
            )
        if number % 50 == 0:
            print(json.dumps({"processed": number, "total": len(suite)}), flush=True)
    result = {
        "input_hashes": hashes,
        "recognition_receipt_sha256": digest(args.recognition / "complete.json"),
        "mode": args.mode,
        "implementation_sha256": digest(Path(__file__)),
        "mapping_sha256": digest(ROOT / "refinement/english_singing_phones.py"),
        "tifa_archive_sha256": digest(args.archive),
        "per_track": dict(totals),
        "seconds": time.monotonic() - began,
    }
    (args.output / "records.json").write_text(json.dumps(records, ensure_ascii=False))
    (args.output / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"per_track": dict(totals), "seconds": result["seconds"]}))


if __name__ == "__main__":
    main()
