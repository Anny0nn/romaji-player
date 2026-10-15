"""Replay closed kana-reading observations privately; never update app lyrics.

The input is a candidate manifest plus a closed SourceScorer observation directory.
An optional supplement adds only previously missing wrong-verse observations.
Audio/model inference and reference labels are deliberately outside this replay.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path
from kana_reading_contrast import nominate_reading


def read_closed(folder):
    folder = folder.resolve()
    identity_path, complete_path = folder / "identity.json", folder / "complete.json"
    complete = json.loads(complete_path.read_text())
    identity = json.loads(identity_path.read_text())
    if digest(identity_path) != complete["identity_sha256"]:
        raise ValueError("Changed closed observation identity.")
    if identity.get("reference_labels_read") is not False:
        raise ValueError("Observations must close without reading reference labels.")
    rows = {}
    for record in complete["records"]:
        path = (folder / record["file"]).resolve()
        if path.parent != folder or digest(path) != record["sha256"]:
            raise ValueError("Changed or external closed observation file.")
        row = json.loads(path.read_text())
        if row["id"] != record["id"] or row["id"] in rows:
            raise ValueError("Duplicate or mismatched closed observation.")
        rows[row["id"]] = row
    if not rows:
        raise ValueError("No closed observations.")
    return identity, rows


def source_group(case, jobs):
    path = Path(case["source_job"]).resolve()
    if path not in jobs:
        jobs[path] = (digest(path), json.loads(path.read_text()))
    signature, job = jobs[path]
    if (
        signature != case["source_job_sha256"]
        or job["track"] != case["source_track"]
        or job["snapshot"] != case["source_snapshot"]
    ):
        raise ValueError("Changed original Rust source job.")
    crops = [c for c in job["crops"] if c["occurrence"] == case["source_occurrence"]]
    if len(crops) != 1:
        raise ValueError("Ambiguous original line occurrence.")
    crop = crops[0]
    targets = [t for t in crop["targets"] if t["raw_span"] == case["source_raw_span"]]
    if len(targets) != 1:
        raise ValueError("Reading target is not an original source group.")
    first, last = case["source_raw_span"]
    raw = crop["raw_line"].encode()[first:last].decode()
    if case.get("source_expected_text", raw) != raw:
        raise ValueError("Changed original source spelling.")
    if (
        case["audio"]["first_sample"] != crop["start_sample"]
        or case["audio"]["last_sample"] != crop["end_sample"]
    ):
        raise ValueError("Candidate changed the original Rust audio crop.")
    return (signature, case["source_occurrence"], first, last)


def replay(manifest, observations, supplement_cases=None, supplement=None):
    cases = manifest["cases"]
    if len({c["id"] for c in cases}) != len(cases) or set(observations) != {
        c["id"] for c in cases
    }:
        raise ValueError("Observation IDs do not match the complete candidate set.")
    supplement_cases, supplement = supplement_cases or {}, supplement or {}
    if set(supplement_cases) != set(supplement) or not set(supplement) <= set(
        observations
    ):
        raise ValueError("Wrong-verse supplement is incomplete.")
    grouped, contexts, jobs = defaultdict(list), {}, {}
    for case in cases:
        key = source_group(case, jobs)
        text = case["text"].encode()
        if len(case["targets"]) != 1:
            raise ValueError("Each hypothesis must score one complete original word.")
        first, last = case["targets"][0]["raw_span"]
        if (
            type(first) is not int
            or type(last) is not int
            or not 0 <= first < last <= len(text)
            or text[first:last].decode() != case["candidate_kana"]
            or case["targets"][0]["text"] != case["candidate_kana"]
        ):
            raise ValueError("Candidate lost exact kana token ownership.")
        row = observations[case["id"]]
        observed = dict(row["observations"])
        wrong_audio = case["wrong_audio"]
        if case["id"] in supplement:
            newer = supplement_cases[case["id"]]
            if set(newer) != set(case) or any(
                newer[k] != case[k] for k in case if k != "wrong_audio"
            ):
                raise ValueError("Wrong-only supplement changed a reading candidate.")
            if "wrong_verse" in observed:
                raise ValueError("Supplement would overwrite an observed condition.")
            observed["wrong_verse"] = supplement[case["id"]]["wrong_condition"]
            wrong_audio = newer["wrong_audio"]
        if wrong_audio.get("status", "available") == "available" and (
            wrong_audio["last_sample"] - wrong_audio["first_sample"]
            != case["audio"]["last_sample"] - case["audio"]["first_sample"]
        ):
            raise ValueError("Wrong-verse control changed the sample count.")
        context = (
            text[:first].decode(),
            text[last:].decode(),
            case["selected_dictionary_kana"],
            json.dumps(case["audio"], sort_keys=True),
            json.dumps(wrong_audio, sort_keys=True),
        )
        if contexts.setdefault(key, context) != context:
            raise ValueError("A reading alternative changed another word or waveform.")
        grouped[key].append(
            {
                "id": case["id"],
                "kana": case["candidate_kana"],
                "current": case["candidate_kana"] == case["selected_dictionary_kana"],
                "observations": observed,
            }
        )
    decisions = [
        {"source_group": list(key), **nominate_reading(candidates)}
        for key, candidates in grouped.items()
    ]
    return {
        "groups": len(grouped),
        "hypotheses": len(cases),
        "counts": dict(Counter(d["reason"] for d in decisions)),
        "decisions": decisions,
        "role": "conditional research nominations; not recognition, accuracy or timing",
        "saved_app_data_changed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("observations", type=Path)
    parser.add_argument("--supplement-manifest", type=Path)
    parser.add_argument("--supplement-observations", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest_path, folder, output = map(
        private_path, (args.manifest, args.observations, args.output)
    )
    manifest = json.loads(manifest_path.read_text())
    identity, observations = read_closed(folder)
    manifest_sha = digest(manifest_path)
    if identity["manifest_sha256"] != manifest_sha or any(
        row["manifest_sha256"] != manifest_sha for row in observations.values()
    ):
        raise ValueError("Closed run belongs to another candidate manifest.")
    artifacts = {str(p): digest(p) for p in (manifest_path, folder / "complete.json")}
    extra_cases, extra_rows = {}, {}
    if bool(args.supplement_manifest) != bool(args.supplement_observations):
        parser.error("Provide both supplement manifest and observations.")
    if args.supplement_manifest:
        supplement_path, supplement_folder = map(
            private_path, (args.supplement_manifest, args.supplement_observations)
        )
        extra_manifest = json.loads(supplement_path.read_text())
        extra_identity, extra_rows = read_closed(supplement_folder)
        if (
            extra_manifest["base_manifest_sha256"] != manifest_sha
            or extra_identity["base_manifest_sha256"] != manifest_sha
            or extra_identity["supplement_manifest_sha256"] != digest(supplement_path)
            or extra_identity["old_closed_complete_sha256"]
            != digest(folder / "complete.json")
            or extra_identity["assets"] != identity["assets"]
            or extra_identity["source_scorer_sha256"]
            != identity["source_scorer_sha256"]
            or any(
                row["supplement_manifest_sha256"] != digest(supplement_path)
                for row in extra_rows.values()
            )
        ):
            raise ValueError(
                "Wrong-only observations changed the original run or model."
            )
        extra_cases = {c["id"]: c for c in extra_manifest["cases"]}
        if len(extra_cases) != len(extra_manifest["cases"]):
            raise ValueError("Duplicate supplemental candidate.")
        artifacts.update(
            {
                str(p): digest(p)
                for p in (supplement_path, supplement_folder / "complete.json")
            }
        )
    report = replay(manifest, observations, extra_cases, extra_rows)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    recipe = {
        "artifacts": artifacts,
        "code": {
            name: digest(ROOT / "scripts" / name)
            for name in ("evaluate-reading-contrasts.py", "kana_reading_contrast.py")
        },
        "reference_labels_read": False,
        "model_inference_run": False,
    }
    for filename, value in (("identity.json", recipe), ("report.json", report)):
        (output / filename).write_text(
            json.dumps(value, indent=2, allow_nan=False) + "\n"
        )
    print(json.dumps({"groups": report["groups"], "counts": report["counts"]}))


if __name__ == "__main__":
    main()
