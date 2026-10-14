"""Replay audio-only English timestamps plus independent TIFA on saved Mac gaps."""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

from audio_first_models import ROOT, digest
from mac_completeness_inputs import load_suite

sys.path.insert(0, str(ROOT / "refinement"))
from english_timing import observed_words, recover_english


def read_timing_run(directory, manifest):
    recipe = json.loads((directory / "recipe.json").read_text())
    complete = json.loads((directory / "complete.json").read_text())
    if complete["recipe_sha256"] != digest(directory / "recipe.json") or recipe[
        "manifest_sha256"
    ] != digest(manifest):
        raise ValueError("Transcription recipe or audio manifest changed.")
    cases = json.loads(manifest.read_text())["cases"]
    if len(cases) != len(complete["records"]):
        raise ValueError("English recognition is incomplete.")
    result = {}
    for case, entry in zip(cases, complete["records"], strict=True):
        path = entry["file"]
        if Path(path).name != path or digest(directory / path) != entry["sha256"]:
            raise ValueError("Word observations changed.")
        row = json.loads((directory / path).read_text())
        if (
            row["case"] != case
            or row["recipe_sha256"] != complete["recipe_sha256"]
            or case["id"] in result
        ):
            raise ValueError("Word observations have another audio identity.")
        result[case["id"]] = row
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--recognition", type=Path, required=True)
    parser.add_argument("--audio-manifest", type=Path, required=True)
    parser.add_argument("--tifa-mix", type=Path, required=True)
    parser.add_argument("--tifa-kim", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if ROOT in args.output.resolve().parents:
        parser.error("Source-word results stay outside the checkout.")
    _, suite, hashes = load_suite(args.manifest)
    recognition = read_timing_run(args.recognition, args.audio_manifest)
    tifa = [
        {r["id"]: r for r in json.loads(path.read_text())}
        for path in (args.tifa_mix, args.tifa_kim)
    ]
    totals, records = defaultdict(Counter), []
    for row in suite:
        case, words, baseline = row["mix"], row["words"], row["baseline"]
        counts = totals[case["track"]]
        counts["words"] += len(words)
        counts["baseline"] += sum(u["start_ms"] >= 0 for u in baseline)
        if row["id"] + ":mix" not in recognition:
            continue
        targets = [
            {
                "raw_span": w["raw_span"],
                "text": w["hiragana"],
                "romaji": w["romaji"],
                "expected_text": w["expected_text"],
            }
            for w in words
        ]
        views, trials = [], []
        length_ms = case["end_ms"] - case["start_ms"]
        for index, name in enumerate(("mix", "kim")):
            audio = row[name]
            recognized = recognition[row["id"] + ":" + name]
            r = recognized["case"]
            if r["sha256"] != audio["audio_sha256"] or [
                r["first_sample"],
                r["last_sample"],
            ] != [audio["start_ms"] * 16, audio["end_ms"] * 16]:
                raise ValueError("English observations use another source crop.")
            trial = tifa[index][row["id"]]
            if any(
                trial[k] != audio[k]
                for k in ("pcm", "audio_sha256", "snapshot", "start_ms", "end_ms")
            ):
                raise ValueError("TIFA evidence uses another source crop.")
            views.append(observed_words(targets, recognized["segments"], length_ms))
            trials.append(trial["raw_units"])
        repaired = recover_english(baseline, targets, trials, views, length_ms)
        for word, before, after, mix, kim in zip(
            words, baseline, repaired, *views, strict=True
        ):
            if before["start_ms"] < 0:
                counts["mix_observed"] += mix["start_ms"] >= 0
                counts["kim_observed"] += kim["start_ms"] >= 0
                counts["both_observed"] += mix["start_ms"] >= 0 and kim["start_ms"] >= 0
            gained = before["start_ms"] < 0 <= after["start_ms"]
            counts["gains"] += gained
            if gained:
                records.append(
                    {
                        "id": row["id"],
                        "track": case["track"],
                        "raw_span": word["raw_span"],
                        "before": before,
                        "after": after,
                        "whisper_mix": mix,
                        "whisper_kim": kim,
                    }
                )
            if before["start_ms"] >= 0 and before != after:
                raise ValueError("Moved a previously retained interval.")
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.umask(0o077)
    (args.output / "records.json").write_text(json.dumps(records, ensure_ascii=False))
    result = {
        "inputs_sha256": hashes,
        "recognition_receipt_sha256": digest(args.recognition / "complete.json"),
        "tifa_inputs_sha256": [digest(p) for p in (args.tifa_mix, args.tifa_kim)],
        "policy_sha256": digest(ROOT / "refinement/english_timing.py"),
        "per_track": dict(totals),
        "gains": sum(c["gains"] for c in totals.values()),
    }
    (args.output / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"per_track": dict(totals), "gains": result["gains"]}))


if __name__ == "__main__":
    main()
