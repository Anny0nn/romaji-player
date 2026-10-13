"""Join explicit cached word diagnostics to saved results, without model inference.

Manifest: cases, diagnostics, results [{track, path}], crop_provenance. Paths are
relative to the manifest. The output directory must be outside the checkout.
The private ledger contains source spans and must not be published.
"""

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = ("id", "pcm", "audio_sha256", "snapshot", "start_ms", "end_ms")
REASONS = {
    "retained",
    "unsupported",
    "incomplete",
    "token_agreement",
    "duration",
    "bounds",
    "similarity",
}


def indexed(rows):
    result = {}
    for row in rows:
        if row["id"] in result:
            raise ValueError("Duplicate case identity.")
        result[row["id"]] = row
    return result


def analyze(cases, diagnostics, results):
    """Historical reasons are not the final recipe's rejection explanations."""
    evidence = indexed(diagnostics)
    indexed(cases)
    totals, reasons, per_track, ledger = Counter(), Counter(), defaultdict(Counter), []
    seen_occurrences = set()
    for case in cases:
        if case["id"].startswith("control:"):
            continue
        track, occurrence = case["track"], case["occurrence"]
        if (track, occurrence) in seen_occurrences:
            raise ValueError("Duplicate lyric occurrence.")
        seen_occurrences.add((track, occurrence))
        trial, saved = evidence[case["id"]], results[track]
        if any(trial[k] != case[k] for k in IDENTITY):
            raise ValueError("Diagnostic source/audio/crop identity changed.")
        if saved["track"] != track or saved["base_snapshot"] != case["snapshot"]:
            raise ValueError("Saved result uses another source.")
        lines = [o for o in saved["snapshot"]["occurrences"] if o["id"] == occurrence]
        if len(lines) != 1 or lines[0]["raw_line"] != case["raw_line"]:
            raise ValueError("Lyric text or occurrence changed; reconversion required.")
        raw = case["raw_line"].encode()
        units = {tuple(u["raw_span"]): u for u in trial["raw_units"]}
        if len(units) != len(trial["raw_units"]) or len(units) != len(case["words"]):
            raise ValueError("Diagnostic word mapping is incomplete.")
        totals["crops"] += 1
        totals["crops_at_30s"] += case["end_ms"] - case["start_ms"] == 30_000
        previous = 0
        for word in case["words"]:
            a, b = word["raw_span"]
            if not 0 <= previous <= a < b <= len(raw):
                raise ValueError("Invalid or overlapping source word.")
            if raw[a:b].decode() != word["expected_text"]:
                raise ValueError("Word text does not match its original UTF-8 span.")
            previous = b
            unit = units[(a, b)]
            if unit["reason"] not in REASONS:
                raise ValueError("Unknown diagnostic rejection reason.")
            fragments = [f for f in lines[0]["fragments"] if f["raw_span"] == [a, b]]
            if any(
                f["raw_span"][0] < b
                and f["raw_span"][1] > a
                and f["raw_span"] != [a, b]
                for f in lines[0]["fragments"]
            ):
                raise ValueError("Saved timing uses a different word grouping.")
            retained = bool(fragments)
            text = word["expected_text"]
            latin = any("a" <= c.lower() <= "z" for c in text)
            for counts in (totals, per_track[track]):
                counts["words"] += 1
                counts["retained"] += retained
                counts["missing"] += not retained
                counts["missing_latin"] += latin and not retained
                counts["missing_latin_ascii_only"] += (
                    latin and text.isascii() and not retained
                )
            if not retained:
                reasons[unit["reason"]] += 1
            ledger.append(
                {
                    "case": case["id"],
                    "track": track,
                    "occurrence": occurrence,
                    "snapshot": case["snapshot"],
                    "audio_sha256": case["audio_sha256"],
                    "conversion_signature": case.get("conversion_signature"),
                    "rust_crop_samples": case.get("rust_crop_samples"),
                    "saved_recipe": {
                        key: saved.get(key)
                        for key in (
                            "engine",
                            "model_sha256",
                            "audio_sha256",
                            "base_revision",
                            "delay_ms",
                        )
                    },
                    "raw_span": [a, b],
                    "crop_ms": [case["start_ms"], case["end_ms"]],
                    "retained": retained,
                    "latin_source": latin,
                    "historical_tifa_mix": unit,
                }
            )
    if set(per_track) != set(results):
        raise ValueError("Result suite and diagnostic suite contain different tracks.")
    for track, counts in per_track.items():
        if (counts["words"], counts["retained"]) != (
            results[track]["total_words"],
            results[track]["timed_words"],
        ):
            raise ValueError("Saved coverage does not match exact source-span join.")
    return {
        "totals": totals,
        "historical_mix_reasons_for_missing": reasons,
        "per_track": dict(per_track),
    }, ledger


def attach_rust_crops(cases, manifests):
    """Validate Rust's exact sample coordinates before adding fresh provenance."""
    rows = {}
    for manifest in manifests:
        if (
            manifest["schema_version"] != 1
            or manifest["producer"] != "Rust crop_targets"
            or manifest["sample_rate"] != 16000
        ):
            raise ValueError("Unknown Rust crop schema.")
        for crop in manifest["crops"]:
            key = manifest["track"], crop["occurrence"]
            if key in rows:
                raise ValueError("Duplicate Rust occurrence.")
            rows[key] = manifest, crop
    used = set()
    result = []
    for case in cases:
        if case["id"].startswith("control:"):
            result.append(case)
            continue
        key = case["track"], case["occurrence"]
        manifest, crop = rows[key]
        first, last = crop["start_sample"], crop["end_sample"]
        origin = manifest["recording_origin_ms"]
        if (
            not 0 <= first < last <= manifest["recording_samples"]
            or case["start_ms"] != origin + first / 16
            or case["end_ms"] != origin + last / 16
            or crop["lyric_origin_ms"] != case["start_ms"] - manifest["delay_ms"]
            or manifest["mono_pcm_sha256"] != case["audio_sha256"]
            or manifest["snapshot"] != case["snapshot"]
            or crop["raw_line"] != case["raw_line"]
            or [w["raw_span"] for w in case["words"]]
            != [t["raw_span"] for t in crop["targets"]]
            or not crop["conversion_signature"]
        ):
            raise ValueError(
                "Rust crop/source/audio identity differs from cached cases."
            )
        used.add(key)
        result.append(
            {
                **case,
                "conversion_signature": crop["conversion_signature"],
                "rust_crop_samples": [first, last],
            }
        )
    if used != set(rows):
        raise ValueError("Rust and diagnostic occurrence sets differ.")
    return result


def private_output(path):
    path = path.resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError("Diagnostic output must be outside the checkout.")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.chmod(0o700)
    return path


def write_private(path, value, jsonl=False):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        if jsonl:
            for row in value:
                handle.write(
                    json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n"
                )
        else:
            json.dump(value, handle, indent=2, allow_nan=False)
            handle.write("\n")


def run(manifest, output):
    manifest = manifest.resolve()
    data = json.loads(manifest.read_text())
    files = {}

    def load(name):
        path = (manifest.parent / name).resolve()
        content = path.read_bytes()
        files[name] = hashlib.sha256(content).hexdigest()
        return json.loads(content)

    results = {}
    for row in data["results"]:
        if row["track"] in results:
            raise ValueError("Duplicate result track.")
        results[row["track"]] = load(row["path"])
    cases = load(data["cases"])
    if data.get("rust_manifests"):
        cases = attach_rust_crops(
            cases, [load(name) for name in data["rust_manifests"]]
        )
    summary, ledger = analyze(cases, load(data["diagnostics"]), results)
    summary.update(
        schema_version=1,
        crop_provenance=data["crop_provenance"],
        input_sha256=files,
        manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
    )
    output = private_output(output)
    write_private(output / "ledger.jsonl", ledger, jsonl=True)
    write_private(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = run(args.manifest, args.output)
    except (ValueError, KeyError, OSError, UnicodeError):
        parser.exit(
            1, "Diagnostic inputs failed validation; no lyric details logged.\n"
        )
    print(json.dumps(summary["totals"]))


if __name__ == "__main__":
    main()
