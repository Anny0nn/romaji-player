"""Bounded private repeat-window pilot with fresh target-audio verification.

Manifest is the context builder manifest plus assets and archive. Identical source
lyrics nominate repeats. DTW uses freshly computed MMS vocal posterior features;
RomajiASR on target audio verifies endpoints, and TIFA re-aligns the nominated crop.
No source interval is copied into the result and no app data is changed.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import resource
import sys
import time
from collections import Counter
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa"), str(ROOT / "scripts")]
from reading_repair import singing_evidence
from refinement_helper import mms, release, verify_assets
from singing_word_alignment import word_alignment
from tifa_helper import Aligner, prepare_model

spec = importlib.util.spec_from_file_location(
    "diagnostics", ROOT / "scripts/diagnose-song-suite.py"
)
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)
spec = importlib.util.spec_from_file_location(
    "ensemble", ROOT / "scripts/experiment-lyric-ensemble.py"
)
ensemble = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ensemble)


def targets(case):
    return [
        {
            "raw_span": w["raw_span"],
            "text": "".join(c for c in w["hiragana"] if c.isalnum())
            or w["expected_text"],
            "romaji": w["romaji"],
        }
        for w in case["words"]
    ]


def select(cases, results):
    rows, pairs = [], []
    for case in cases:
        if case["id"].startswith("control:"):
            continue
        saved = results[case["track"]]
        if (
            saved["base_snapshot"] != case["snapshot"]
            or saved["delay_ms"] != case["delay_ms"]
        ):
            raise ValueError("Changed repeated source or clock.")
        line = next(
            o for o in saved["snapshot"]["occurrences"] if o["id"] == case["occurrence"]
        )
        if line["raw_line"] != case["raw_line"]:
            raise ValueError("Changed repeated lyric text.")
        protected = {
            p["raw_line"]
            for p in (saved["snapshot"]["source"].get("derivation") or {}).get(
                "readings", []
            )
        }
        if case["raw_line"] in protected or any(
            any(c.isascii() and c.isalpha() for c in w["expected_text"])
            for w in case["words"]
        ):
            continue
        present = {tuple(f["raw_span"]): f["interval"] for f in line["fragments"]}
        missing = [
            i
            for i, w in enumerate(case["words"])
            if tuple(w["raw_span"]) not in present
        ]
        rows.append((case, present, missing))
    for target, present, missing in rows:
        if not missing:
            continue
        anchors = [
            (case, intervals)
            for case, intervals, gaps in rows
            if case["track"] == target["track"]
            and case["id"] != target["id"]
            and case["raw_line"] == target["raw_line"]
            and case["words"] == target["words"]
            and not gaps
        ]
        if anchors:
            source, intervals = min(
                anchors, key=lambda r: abs(r[0]["start_ms"] - target["start_ms"])
            )
            pairs.append((source, target, intervals, present, missing))
    return pairs


def proposal(path, interval, source_origin, source_frames, target_frames):
    import numpy as np

    first = max(0, int((interval["start_ms"] - source_origin) // 20))
    last = min(source_frames - 1, int((interval["end_ms"] - source_origin) // 20))
    if first >= last:
        return None
    a, b = path[path[:, 0] == first, 1], path[path[:, 0] == last, 1]
    if not len(a) or not len(b):
        return None
    start, end = int(np.min(a) * 20), int(np.max(b) * 20 + 25)
    ratio = (end - start) / (interval["end_ms"] - interval["start_ms"])
    if not 0.5 <= ratio <= 2 or not 0 <= start < end <= target_frames * 20 + 25:
        return None
    return start, end


def supported(new, observation, tolerance=150):
    return (
        all(
            math.isfinite(unit[k])
            for unit in (new, observation)
            for k in ("start_ms", "end_ms")
        )
        and 0 <= new["start_ms"] < new["end_ms"]
        and 0 <= observation["start_ms"] < observation["end_ms"]
        and 0.45 <= observation["mean_probability"] <= 1
        and all(
            abs(new[k] - observation[k]) <= tolerance for k in ("start_ms", "end_ms")
        )
    )


def reject_overlaps(rows, words, current, origin):
    """Reject every conflicting new observation; never trim or move an anchor."""
    candidates = {
        tuple(r["raw_span"]): r for r in rows if r["reason"] == "model_supported"
    }
    ordered = []
    for word in words:
        span = tuple(word["raw_span"])
        if span in current:
            interval = {k: current[span][k] - origin for k in ("start_ms", "end_ms")}
        elif span in candidates:
            interval = candidates[span]["prediction"]
        else:
            continue
        ordered.append((span, interval))
    rejected = set()
    for (left, a), (right, b) in pairwise(ordered):
        if a["end_ms"] > b["start_ms"]:
            rejected.update(s for s in (left, right) if s in candidates)
    for span in rejected:
        candidates[span]["reason"] = "overlap"


def main():
    import numpy as np
    from librosa.sequence import dtw

    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT == output or ROOT in output.parents:
        parser.error("Private evidence belongs outside the checkout.")
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.chmod(0o700)
    if (output / "summary.json").exists():
        parser.error("Use a fresh output directory.")
    config = json.loads(args.manifest.read_text())
    hashes = {}

    def load(path):
        p = Path(path)
        data = p.read_bytes()
        hashes[str(p)] = hashlib.sha256(data).hexdigest()
        return json.loads(data)

    cases = diagnostics.attach_rust_crops(
        load(config["mix_cases"]), [load(p) for p in config["rust_manifests"]]
    )
    results = {r["track"]: load(r["path"]) for r in config["results"]}
    stems = diagnostics.indexed(load(config["stem_cases"]))
    pairs = select(cases, results)
    assets, archive = Path(config["assets"]), Path(config["archive"])
    verify_assets(assets)
    data, features, evidence = {}, {}, {}
    for source, target, _, _, _ in pairs:
        for case in (source, target):
            if case["id"] in data:
                continue
            stem = stems[case["id"]]
            if (
                any(
                    stem[k] != case[k]
                    for k in ("snapshot", "start_ms", "end_ms", "words")
                )
                or stem["mix_sha256"] != case["audio_sha256"]
                or stem["mix_pcm"] != case["pcm"]
            ):
                raise ValueError("Repeat stem changed its source or crop identity.")
            data[case["id"]] = (case, stem)
    ensemble.verify_recordings([case for case, _ in data.values()])
    ensemble.verify_recordings([stem for _, stem in data.values()])
    for case, stem in data.values():
        first, last = case["rust_crop_samples"]
        if not 0 <= first < last <= Path(stem["pcm"]).stat().st_size // 4:
            raise ValueError("Repeat crop exceeds its recording.")
    started = time.monotonic()
    # Group by recording, loading each model sequentially. The pilot is bounded
    # to the exact eligible repeats; no whole-song relocation or chroma search.
    groups = {}
    for key, (case, stem) in data.items():
        groups.setdefault(stem["pcm"], []).append((key, case, stem))
    for pcm, rows in groups.items():
        samples = np.memmap(pcm, dtype="<f4", mode="r")
        crops = [
            (i, *case["rust_crop_samples"], targets(case))
            for i, (_, case, _) in enumerate(rows)
        ]
        posterior = mms(
            samples,
            crops,
            assets / "mms",
            output / "progress.txt",
            "Repeat features",
            posteriors=True,
        )
        independent, vocabulary = singing_evidence(
            samples, crops, assets, output / "progress.txt"
        )
        for (key, _, _), feature, proof, crop in zip(
            rows, posterior, independent, crops, strict=True
        ):
            features[key] = feature
            evidence[key] = word_alignment(*proof, crop[3], vocabulary)
    aligner = Aligner(prepare_model(archive))
    ledger, gained = [], {}
    for source, target, source_times, current, missing in pairs:
        (src, blank), (dst, target_blank) = (
            features[source["id"]],
            features[target["id"]],
        )
        if blank != target_blank or not 0 <= blank < src.shape[1] == dst.shape[1]:
            raise ValueError("Changed MMS feature inventory.")
        x, y = np.exp(src.astype(np.float64)), np.exp(dst.astype(np.float64))
        x[:, blank] = y[:, blank] = 0
        x, y = np.maximum(x, 1e-8), np.maximum(y, 1e-8)
        _, path = dtw(
            X=x.T, Y=y.T, metric="cosine", global_constraints=True, band_rad=0.25
        )
        observed = evidence[target["id"]]
        words = targets(target)
        origin, length = (
            target["lyric_origin_ms"],
            (target["rust_crop_samples"][1] - target["rust_crop_samples"][0]) // 16,
        )
        coherence = sum(
            o["start_ms"] >= 0 and o["mean_probability"] >= 0.45 for o in observed
        ) >= max(2, (target["source_word_count"] + 1) // 2)
        pcm = np.memmap(stems[target["id"]]["pcm"], dtype="<f4", mode="r")
        proposals = []
        for index in missing:
            word = words[index]
            proposed = proposal(
                path,
                source_times[tuple(word["raw_span"])],
                source["lyric_origin_ms"],
                len(src),
                len(dst),
            )
            reason, prediction = "dtw_distortion", None
            if proposed is not None:
                boundary = {"start_ms": proposed[0], "end_ms": proposed[1]}
                reason = "independent"
                if coherence and supported(boundary, observed[index]):
                    first, last = (
                        max(0, proposed[0] - 300),
                        min(length, proposed[1] + 300),
                    )
                    start = target["rust_crop_samples"][0]
                    prediction = aligner.align(
                        pcm[start + first * 16 : start + last * 16], [word]
                    )[0]
                    reason = "realignment"
                    if prediction["start_ms"] >= 0:
                        prediction = {
                            **prediction,
                            "start_ms": prediction["start_ms"] + first,
                            "end_ms": prediction["end_ms"] + first,
                        }
                        if (
                            supported(prediction, observed[index])
                            and supported(
                                prediction, {**boundary, "mean_probability": 1}
                            )
                            and 0
                            <= prediction["start_ms"]
                            < prediction["end_ms"]
                            <= length
                        ):
                            bounds = [current.get(tuple(w["raw_span"])) for w in words]
                            old = [
                                (
                                    {
                                        "start_ms": p["start_ms"] - origin,
                                        "end_ms": p["end_ms"] - origin,
                                    }
                                    if p
                                    else None
                                )
                                for p in bounds
                            ]
                            before = next(
                                (j for j in range(index - 1, -1, -1) if old[j]), None
                            )
                            after = next(
                                (j for j in range(index + 1, len(words)) if old[j]),
                                None,
                            )
                            anchored = all(
                                supported(old[j], observed[j])
                                for j in (before, after)
                                if j is not None
                            )
                            if (
                                anchored
                                and any(j is not None for j in (before, after))
                                and (
                                    before is None
                                    or old[before]["end_ms"] <= prediction["start_ms"]
                                )
                                and (
                                    after is None
                                    or prediction["end_ms"] <= old[after]["start_ms"]
                                )
                            ):
                                reason = "model_supported"
                            else:
                                reason = "outer_anchor"
            proposals.append(
                {
                    "source": source["id"],
                    "target": target["id"],
                    "raw_span": word["raw_span"],
                    "proposal": proposed,
                    "prediction": prediction,
                    "reason": reason,
                }
            )
        reject_overlaps(proposals, words, current, origin)
        gains = sum(r["reason"] == "model_supported" for r in proposals)
        if gains:
            gained[target["id"]] = gains
        ledger.extend(proposals)
    del aligner
    release()
    summary = {
        "eligible_repeats": len(pairs),
        "missing_words": len(ledger),
        "new_model_supported_words": sum(gained.values()),
        "gains_by_occurrence": gained,
        "reasons": dict(Counter(row["reason"] for row in ledger)),
        "processing_seconds": time.monotonic() - started,
        "lifetime_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "model_manifest_sha256": hashlib.sha256(
            (ROOT / "refinement/refinement-model-files.json").read_bytes()
        ).hexdigest(),
        "tifa_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "audio_sha256": {
            stem["pcm"]: stem["audio_sha256"] for _, stem in data.values()
        },
        "input_sha256": hashes,
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "boundary_decoder_sha256": hashlib.sha256(
            (ROOT / "scripts/singing_word_alignment.py").read_bytes()
        ).hexdigest(),
        "reference_accuracy_measured": False,
        "features": "MMS vocal token posteriors; blank removed; cosine DTW band 0.25",
        "verification": "Target RomajiASR complete mixed-token path, mean probability 0.45, endpoints 150 ms; fresh TIFA in proposed ±300 ms window; unchanged nearest anchors independently checked.",
    }
    diagnostics.write_private(output / "summary.json", summary)
    diagnostics.write_private(output / "ledger.json", ledger)
    print(
        json.dumps(
            {
                k: summary[k]
                for k in [
                    "eligible_repeats",
                    "missing_words",
                    "new_model_supported_words",
                ]
            }
        )
    )


if __name__ == "__main__":
    main()
