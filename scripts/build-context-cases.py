"""Build private phrase-context cases from verified Rust crop endpoints.

Manifest: mix_cases, stem_cases, rust_manifests, results [{track,path}], limit (0=all).
No models, source changes or app writes. Combined UTF-8 spans are an inference namespace;
owners retain each original occurrence/span. Output is private and never overwritten.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "song_diagnostics", ROOT / "scripts/diagnose-song-suite.py"
)
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


def build(mix, stems, manifests, results, limit=12):
    if not isinstance(limit, int) or limit < 0:
        raise ValueError("Invalid context limit.")
    verified = diagnostics.attach_rust_crops(mix, manifests)
    stems = diagnostics.indexed(stems)
    groups, output = {}, []
    for case in verified:
        if case["id"].startswith("control:"):
            continue
        saved, stem = results[case["track"]], stems[case["id"]]
        if (
            saved["track"] != case["track"]
            or saved["base_snapshot"] != case["snapshot"]
            or stem["mix_sha256"] != case["audio_sha256"]
            or stem["mix_pcm"] != case["pcm"]
            or any(stem[k] != case[k] for k in ("snapshot", "start_ms", "end_ms"))
            or stem["words"] != case["words"]
        ):
            raise ValueError("Source or recording changed before building context.")
        groups.setdefault(case["track"], []).append(case)
    for track, cases in groups.items():
        saved = results[track]
        lines = {line["id"]: line for line in saved["snapshot"]["occurrences"]}
        protected = {
            repair["raw_line"]
            for repair in (saved["snapshot"]["source"].get("derivation") or {}).get(
                "readings", []
            )
        }
        cases.sort(key=lambda c: (c["start_ms"], c["occurrence"]))
        used = 0
        for index, case in enumerate(cases):
            if limit and used >= limit:
                break
            line = lines[case["occurrence"]]
            if line["raw_line"] != case["raw_line"]:
                raise ValueError("Corrected lyric text requires a fresh Rust export.")
            raw = case["raw_line"].encode()
            for word in case["words"]:
                a, b = word["raw_span"]
                if raw[a:b].decode() != word["expected_text"]:
                    raise ValueError("Invalid original UTF-8 word ownership.")
            present = {tuple(f["raw_span"]) for f in line["fragments"]}
            missing = {
                tuple(w["raw_span"])
                for w in case["words"]
                if tuple(w["raw_span"]) not in present
                and not any("a" <= c.lower() <= "z" for c in w["expected_text"])
            }
            if not missing:
                continue
            pairs = []
            if index:
                pairs.append([cases[index - 1], case])
            if index + 1 < len(cases):
                pairs.append([case, cases[index + 1]])
            for pair in pairs:
                if limit and used >= limit:
                    break
                # Use endpoints already exported by Rust. Reject long or simultaneous
                # windows; never cut a joint phrase to manufacture a legal crop.
                if (
                    pair[1]["end_ms"] - pair[0]["start_ms"] > 30_000
                    or pair[0]["start_ms"] == pair[1]["start_ms"]
                ):
                    continue
                if any(part["raw_line"] in protected for part in pair):
                    continue
                words, owners, offset = [], [], 0
                for part in pair:
                    if lines[part["occurrence"]]["raw_line"] != part["raw_line"]:
                        raise ValueError("Context neighbor has changed source text.")
                    for word in part["words"]:
                        span = [v + offset for v in word["raw_span"]]
                        words.append(
                            {
                                **{
                                    k: word[k]
                                    for k in ("expected_text", "hiragana", "romaji")
                                },
                                "raw_span": span,
                            }
                        )
                        owners.append(
                            {
                                "joint_span": span,
                                "occurrence": part["occurrence"],
                                "raw_span": word["raw_span"],
                                "nominated": part["occurrence"] == case["occurrence"]
                                and tuple(word["raw_span"]) in missing,
                            }
                        )
                    offset += len(part["raw_line"].encode()) + 1
                raw_line = "\n".join(part["raw_line"] for part in pair)
                virtual = hashlib.sha256(
                    json.dumps(
                        [case["snapshot"], raw_line, owners], ensure_ascii=False
                    ).encode()
                ).hexdigest()
                output.append(
                    {
                        **stems[case["id"]],
                        "id": f"{track}:context:{case['occurrence']}:{pair[0]['occurrence']}",
                        "parent_snapshot": case["snapshot"],
                        "snapshot": virtual,
                        "start_ms": pair[0]["start_ms"],
                        "end_ms": pair[1]["end_ms"],
                        "rust_crop_samples": [
                            pair[0]["rust_crop_samples"][0],
                            pair[1]["rust_crop_samples"][1],
                        ],
                        "conversion_signatures": [
                            part["conversion_signature"] for part in pair
                        ],
                        "raw_line": raw_line,
                        "words": words,
                        "owners": owners,
                    }
                )
                used += 1
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = args.manifest.resolve()
    config = json.loads(manifest.read_text())
    hashes = {}

    def load(name):
        path = (manifest.parent / name).resolve()
        data = path.read_bytes()
        hashes[name] = hashlib.sha256(data).hexdigest()
        return json.loads(data)

    results = {}
    for row in config["results"]:
        if row["track"] in results:
            raise ValueError("Duplicate saved recording.")
        results[row["track"]] = load(row["path"])
    cases = build(
        load(config["mix_cases"]),
        load(config["stem_cases"]),
        [load(name) for name in config["rust_manifests"]],
        results,
        config.get("limit", 12),
    )
    output = diagnostics.private_output(args.output)
    diagnostics.write_private(output / "cases.json", cases)
    diagnostics.write_private(
        output / "provenance.json",
        {
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "input_sha256": hashes,
            "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
    )
    print(
        json.dumps(
            {
                "windows": len(cases),
                "nominated_occurrences": sum(
                    o["nominated"] for case in cases for o in case["owners"]
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
