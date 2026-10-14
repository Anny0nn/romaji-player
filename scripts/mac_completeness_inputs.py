"""Join current saved Mac results to immutable recorded occurrence windows."""

import json
from pathlib import Path

from audio_first_models import digest


def load_suite(manifest):
    manifest = Path(manifest).resolve()
    config = json.loads(manifest.read_text())
    hashes = {"manifest": digest(manifest)}

    def load(path):
        resolved = (manifest.parent / path).resolve()
        hashes[str(resolved)] = digest(resolved)
        return json.loads(resolved.read_text())

    mix = {
        c["id"]: c
        for c in load(config["mix_cases"])
        if not c["id"].startswith("control:")
    }
    kim = {
        c["id"]: c
        for c in load(config["kim_cases"])
        if not c["id"].startswith("control:")
    }
    if set(mix) != set(kim):
        raise ValueError("Mix and vocal occurrences differ.")
    saved = {r["track"]: load(r["path"]) for r in config["results"]}
    if len(saved) != len(config["results"]):
        raise ValueError("Duplicate saved song.")
    result = []
    for name, case in mix.items():
        stem = kim[name]
        if any(
            case[k] != stem[k]
            for k in (
                "track",
                "snapshot",
                "occurrence",
                "start_ms",
                "end_ms",
                "raw_line",
                "words",
            )
        ):
            raise ValueError("Vocal source or crop changed.")
        document = saved[case["track"]]
        if document["base_snapshot"] != case["snapshot"] or document["delay_ms"] != 0:
            raise ValueError(
                "This recorded suite needs its frozen source and zero-delay clock."
            )
        line = next(
            l
            for l in document["snapshot"]["occurrences"]
            if l["id"] == case["occurrence"]
        )
        if line["raw_line"] != case["raw_line"]:
            raise ValueError("Saved lyric text changed.")
        repairs = (document["snapshot"]["source"].get("derivation") or {}).get(
            "readings", []
        )
        words = [dict(w) for w in case["words"]]
        baseline = []
        for word in words:
            a, b = word["raw_span"]
            if case["raw_line"].encode()[a:b].decode() != word["expected_text"]:
                raise ValueError("Changed original byte ownership.")
            edits = [
                r
                for r in repairs
                if r["raw_line"] == case["raw_line"]
                and r["raw_span"] == word["raw_span"]
            ]
            readings = {(r["hiragana"], r["romaji"]) for r in edits}
            if len(readings) > 1:
                raise ValueError("Conflicting saved readings.")
            word["protected_reading"] = bool(readings)
            if readings:
                word["hiragana"], word["romaji"] = next(iter(readings))
            fragments = [
                f for f in line["fragments"] if f["raw_span"] == word["raw_span"]
            ]
            if len(fragments) > 1:
                raise ValueError("Ambiguous saved word intervals.")
            baseline.append(
                {
                    "raw_span": word["raw_span"],
                    "start_ms": fragments[0]["interval"]["start_ms"] - case["start_ms"]
                    if fragments
                    else -1,
                    "end_ms": fragments[0]["interval"]["end_ms"] - case["start_ms"]
                    if fragments
                    else -1,
                }
            )
        result.append(
            {"id": name, "mix": case, "kim": stem, "words": words, "baseline": baseline}
        )
    for track, document in saved.items():
        rows = [r for r in result if r["mix"]["track"] == track]
        if (
            sum(len(r["words"]) for r in rows),
            sum(u["start_ms"] >= 0 for r in rows for u in r["baseline"]),
        ) != (document["total_words"], document["timed_words"]):
            raise ValueError(
                "Original source denominator or baseline coverage changed."
            )
    return config, result, hashes
