"""Replay a third vocal waveform against frozen source-owned timing proposals.

No inference, clock estimation or app writes. Separation and source-blind Qwen
must already be closed. Original mix/Kim evidence and TIFA/HFA clocks are reused.
The same recognizer on different waveforms is correlated evidence, not three
independent models. Lyric-bearing output must remain outside the checkout.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from collections import Counter
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path
from qwen_lexical import (
    context_matches,
    recognition_words,
    recover_recognized_pairs,
    recover_recognized_views,
)

spec = importlib.util.spec_from_file_location(
    "closed_qwen_collector", ROOT / "scripts/collect-qwen-lexical.py"
)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def check_context(job, output, window, song, stereo_sha256):
    """A derived PCM starts at zero but owns one exact original Rust context."""
    if (
        job["context"] != window
        or type(output["first_sample"]) is not int
        or type(output["last_sample"]) is not int
        or job["original_stereo"]["path"] != song["stereo"]
        or job["original_stereo"]["sha256"] != stereo_sha256
        or job["original_stereo"]["sample_rate"] != 44100
        or job["original_stereo"]["channels"] != 2
        or job["original_stereo"]["encoding"] != "interleaved_f32le"
        or output["first_sample"] != 0
        or output["last_sample"] != window["last_sample"] - window["first_sample"]
        or output["encoding"] != "pcm"
    ):
        raise ValueError("Vocal waveform changed source ownership or context bounds.")


def raw_pcm_window_sha(path, expected_sha256, first_sample, last_sample, cache):
    """Hash exact float32-PCM window bytes after authenticating the full source once."""
    if (
        type(first_sample) is not int
        or type(last_sample) is not int
        or not 0 <= first_sample < last_sample
        or not isinstance(expected_sha256, str)
    ):
        raise ValueError("Invalid source PCM window identity.")
    path = Path(path).resolve()
    stat = path.stat()
    signature = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    if stat.st_size % 4:
        raise ValueError("Source PCM is not complete little-endian float32 data.")
    previous = cache.get(path)
    with path.open("rb") as handle:
        if previous is None:
            whole = hashlib.sha256()
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                whole.update(block)
            actual = whole.hexdigest()
            if actual != expected_sha256:
                raise ValueError("Changed source PCM bytes.")
            cache[path] = (actual, signature)
        elif previous != (expected_sha256, signature):
            raise ValueError("Source PCM changed after its first verification.")
        byte_count = (last_sample - first_sample) * 4
        if last_sample * 4 > stat.st_size:
            raise ValueError("Source PCM window is outside its file.")
        handle.seek(first_sample * 4)
        window = handle.read(byte_count)
        if len(window) != byte_count:
            raise ValueError("Source PCM window is truncated.")
    current = path.stat()
    if (current.st_size, current.st_mtime_ns, current.st_ctime_ns) != signature:
        raise ValueError("Source PCM changed while its window was being verified.")
    return hashlib.sha256(window).hexdigest()


def verify_derived_pcm(path, sample_count, expected_sha256):
    """Require the separator output to be one complete zero-based PCM window."""
    if type(sample_count) is not int or sample_count <= 0:
        raise ValueError("Invalid derived PCM sample count.")
    path = Path(path)
    if path.stat().st_size != sample_count * 4:
        raise ValueError("Derived PCM byte length differs from its context window.")
    actual = digest(path)
    if actual != expected_sha256:
        raise ValueError("Changed derived PCM bytes.")
    return actual


def reject_duplicate_waveform(extra_sha256, original_window_sha256s):
    """A third observation must come from audio bytes distinct from both originals."""
    if extra_sha256 in original_window_sha256s:
        raise ValueError("Third vocal view duplicates an original waveform.")


def derived_audio_case(identifier, output):
    """Project a mono/16 kHz separator receipt onto the audio-only ASR contract."""
    fields = {"path", "sha256", "encoding", "first_sample", "last_sample"}
    if (
        not fields <= output.keys()
        or output.keys() - fields - {"sample_rate", "channels"}
        or type(output.get("sample_rate", 16000)) is not int
        or output.get("sample_rate", 16000) != 16000
        or type(output.get("channels", 1)) is not int
        or output.get("channels", 1) != 1
    ):
        raise ValueError("Derived audio is not the expected mono/16 kHz waveform.")
    return {"id": identifier, **{key: output[key] for key in fields}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("suite", "contexts", "baseline", "model-directory", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--separation", type=Path, action="append", required=True)
    parser.add_argument("--recognition", type=Path, action="append", required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        setattr(
            args,
            name,
            [private_path(p) for p in value]
            if isinstance(value, list)
            else private_path(value),
        )
    if len(args.separation) != len(args.recognition):
        raise ValueError("Each separator batch needs its own closed recognition run.")
    suite = json.loads(args.suite.read_text())
    metadata = json.loads((args.contexts / "suite-contexts.json").read_text())
    audio_manifest_path = args.contexts / "audio-contexts.json"
    if metadata["identity_sha256"] != digest(
        args.contexts / "identity.json"
    ) or metadata["audio_manifest_sha256"] != digest(audio_manifest_path):
        raise ValueError("Changed original source contexts.")
    audio_manifest = json.loads(audio_manifest_path.read_text())
    if set(audio_manifest) != {"version", "cases"} or audio_manifest["version"] != 1:
        raise ValueError("Expected the frozen audio-only context manifest.")
    audio_cases = {}
    for case in audio_manifest["cases"]:
        if (
            set(case)
            != {
                "id",
                "path",
                "sha256",
                "encoding",
                "first_sample",
                "last_sample",
            }
            or case["id"] in audio_cases
        ):
            raise ValueError("Invalid or duplicate original audio context.")
        audio_cases[case["id"]] = case
    by_track = {s["track"]: s for s in metadata["songs"]}
    songs = {s["track"]: s for s in suite["songs"]}
    crops, stereo_hashes, evidence, stats, records = {}, {}, {}, Counter(), []
    source_pcm_cache = {}
    fields = (
        "original_groups",
        "original_timed",
        "cues",
        "selected_new_view_cues",
        "original_gaps",
        "old_recipe_added",
        "new_recipe_added",
        "incremental",
        "lost",
        "moved",
    )
    counts = {}
    inputs = [
        args.suite,
        args.contexts / "suite-contexts.json",
        audio_manifest_path,
    ]
    baseline_path = args.baseline / "private-records.json"
    baseline_id = json.loads((args.baseline / "identity.json").read_text())
    if (
        baseline_id["records_sha256"] != digest(baseline_path)
        or baseline_id["suite_sha256"] != digest(args.suite)
        or baseline_id["context_sha256"]
        != digest(args.contexts / "suite-contexts.json")
    ):
        raise ValueError("Changed original baseline evidence.")
    inputs += [baseline_path, args.baseline / "identity.json"]
    for track, song in songs.items():
        if any(
            digest(Path(song[key])) != song[sha]
            for key, sha in (("path", "sha256"), ("result_path", "result_sha256"))
        ):
            raise ValueError("Changed frozen original source or saved result.")
        job = json.loads(Path(song["path"]).read_text())
        original = by_track[track]
        if original["eligible"] and (
            original["job_sha256"] != song["sha256"]
            or original["result_sha256"] != song["result_sha256"]
        ):
            raise ValueError("Context belongs to another original source snapshot.")
        if digest(Path(song["pcm"])) != job["mono_pcm_sha256"]:
            raise ValueError("Changed original recording.")
        crops[track] = {c["occurrence"]: c for c in job["crops"]}
        stereo_hashes[track] = digest(Path(song["stereo"]))
        saved = json.loads(Path(song["result_path"]).read_text())
        counts[track] = Counter(dict.fromkeys(fields, 0))
        counts[track].update(
            original_groups=saved["total_words"], original_timed=saved["timed_words"]
        )
    baseline_records = json.loads(baseline_path.read_text())
    seen_occurrences = set()
    for record in baseline_records:
        track, occurrence = record.get("track"), record.get("occurrence")
        key = (track, occurrence)
        if (
            track not in crops
            or type(occurrence) is not int
            or occurrence not in crops[track]
            or key in seen_occurrences
        ):
            raise ValueError("Duplicate or invalid baseline cue occurrence.")
        seen_occurrences.add(key)
    for separation, recognition in zip(args.separation, args.recognition, strict=True):
        complete = json.loads((separation / "complete.json").read_text())
        if complete["identity_sha256"] != digest(
            separation / "identity.json"
        ) or complete["jobs_sha256"] != digest(separation / "jobs.json"):
            raise ValueError("Changed completed separator run.")
        identity = json.loads((separation / "identity.json").read_text())
        strict = identity["strict_loading"]
        if any(strict[key] for key in ("missing", "unexpected", "shape_mismatch")):
            raise ValueError("Incomplete separator model graph.")
        for path, expected in identity["sources"].items():
            if digest(Path(path)) != expected:
                raise ValueError("Changed pinned separator artifact or input.")
        recipe, observed, tokenizer = collector.closed_observations(
            recognition, args.model_directory
        )
        manifest = separation / "audio-only.json"
        cases = json.loads(manifest.read_text())["cases"]
        if recipe["manifest_sha256"] != digest(manifest) or {
            c["id"]: c for c in cases
        } != {key: row["case"] for key, row in observed.items()}:
            raise ValueError("Recognition changed derived audio ownership.")
        outputs = {r["id"]: r["output"] for r in complete["records"]}
        jobs = json.loads((separation / "jobs.json").read_text())
        if (
            len(outputs) != len(jobs)
            or {j["id"] for j in jobs} != set(outputs)
            or set(outputs) != set(observed)
        ):
            raise ValueError("Incomplete separator/recognizer context set.")
        for job in jobs:
            track, index = job["track"], job["window"]
            if type(index) is not int or not 0 <= index < len(
                by_track[track]["windows"]
            ):
                raise ValueError("Invalid original context index.")
            key = track, index
            if key in evidence:
                raise ValueError("More than one extra vocal estimate for a context.")
            window = by_track[track]["windows"][index]
            output = outputs[job["id"]]
            check_context(job, output, window, songs[track], stereo_hashes[track])
            sample_count = window["last_sample"] - window["first_sample"]
            extra_sha256 = verify_derived_pcm(
                output["path"], sample_count, output["sha256"]
            )
            original_hashes = []
            for role in ("mix", "kim"):
                case_id = f"{track}:{index}:{role}"
                original_case = audio_cases.get(case_id)
                if (
                    original_case is None
                    or original_case["encoding"] != "pcm"
                    or type(original_case["first_sample"]) is not int
                    or type(original_case["last_sample"]) is not int
                    or (
                        original_case["first_sample"],
                        original_case["last_sample"],
                    )
                    != (window["first_sample"], window["last_sample"])
                ):
                    raise ValueError(
                        "Original mix/Kim case differs from its selected window."
                    )
                original_hashes.append(
                    raw_pcm_window_sha(
                        original_case["path"],
                        original_case["sha256"],
                        original_case["first_sample"],
                        original_case["last_sample"],
                        source_pcm_cache,
                    )
                )
            reject_duplicate_waveform(extra_sha256, original_hashes)
            if observed[job["id"]]["case"] != derived_audio_case(job["id"], output):
                raise ValueError("Changed derived vocal waveform.")
            words, rejection = recognition_words(
                tokenizer, observed[job["id"]], recipe["language"]
            )
            evidence[key] = context_matches(
                [crops[track][n] for n in window["occurrences"]], words
            )
            stats.update(new_views=1, withheld_views=rejection is not None)
        inputs += [
            separation / name
            for name in (
                "complete.json",
                "jobs.json",
                "identity.json",
                "audio-only.json",
            )
        ] + [recognition / name for name in ("complete.json", "identity.json")]
    for record in baseline_records:
        track, occurrence = record["track"], record["occurrence"]
        crop = crops[track][occurrence]
        length = (crop["end_sample"] - crop["start_sample"]) / 16
        arguments = length, crop["source_word_count"]
        before = recover_recognized_pairs(
            record["baseline"], record["clocks"], record["views"], *arguments
        )
        if before != record["result"]:
            raise ValueError("Original two-view replay did not reproduce its receipt.")
        selected = by_track[track]["cue_context"][str(occurrence)]
        extra = evidence.get((track, selected), {}).get(occurrence)
        after = (
            recover_recognized_views(
                record["baseline"],
                record["clocks"],
                [*record["views"], extra],
                *arguments,
            )
            if extra is not None
            else before
        )
        count = counts[track]
        count.update(cues=1, selected_new_view_cues=extra is not None)
        for original, old, new in zip(record["baseline"], before, after, strict=True):
            gap = not original.get("protected", False) and original["start_ms"] < 0
            count["original_gaps"] += gap
            count["old_recipe_added"] += gap and old["start_ms"] >= 0
            count["new_recipe_added"] += gap and new["start_ms"] >= 0
            count["incremental"] += old["start_ms"] < 0 <= new["start_ms"]
            count["lost"] += old["start_ms"] >= 0 > new["start_ms"]
            count["moved"] += not gap and original != new
        records.append({**record, "extra_view": extra, "new_result": after})
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    output = args.output / "private-records.json"
    output.write_text(json.dumps(records, allow_nan=False))
    identity = {
        "inputs": {str(p): digest(p) for p in inputs},
        "code": {
            name: digest(ROOT / "scripts" / name)
            for name in (
                Path(__file__).name,
                "qwen_lexical.py",
                "source_contrast_policy.py",
            )
        },
        "records_sha256": digest(output),
    }
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2))
    summary = {
        "per_track": counts,
        "counts": {key: sum(c[key] for c in counts.values()) for key in fields},
        "recognition": stats,
        "promoted": False,
        "saved_app_data_changed": False,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
