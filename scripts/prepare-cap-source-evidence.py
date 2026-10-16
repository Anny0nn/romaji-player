"""Bounded source-contrast pilot from authenticated frozen Rust crops and pair clocks.

Select up to three cues per low song by existing paired gaps before new inference.
Keep every original word identity and baseline. No recording, downloading, reranking
of the song set, reference labels or saved app writes.
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path

spec = importlib.util.spec_from_file_location(
    "english_boundary_probe", ROOT / "scripts/probe-english-boundaries.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--lexical", type=Path, required=True)
    parser.add_argument("--paired", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cues-per-song", type=int, default=2)
    args = parser.parse_args()
    for key in ("suite", "contexts", "lexical", "paired", "output"):
        setattr(args, key, private_path(getattr(args, key)))
    if not 1 <= args.cues_per_song <= 3:
        parser.error("pilot uses 1–3 cues per song, selected before contrast inference")
    suite = json.loads(args.suite.read_text())
    lexical_id = json.loads((args.lexical / "identity.json").read_text())
    pairs_id = json.loads((args.paired / "identity.json").read_text())
    if (
        lexical_id["suite"] != digest(args.suite)
        or lexical_id["records_sha256"] != digest(args.lexical / "private-records.json")
        or pairs_id["suite"] != digest(args.suite)
        or pairs_id["lexical_records"] != digest(args.lexical / "private-records.json")
        or pairs_id["lexical_identity"] != digest(args.lexical / "identity.json")
    ):
        raise ValueError("Changed frozen source or pair inputs.")
    contexts = json.loads((args.contexts / "suite-contexts.json").read_text())
    if lexical_id["contexts"] != digest(
        args.contexts / "suite-contexts.json"
    ) or contexts["identity_sha256"] != digest(args.contexts / "identity.json"):
        raise ValueError("Changed authenticated context cache.")
    by_track, pair_hashes = {}, {}
    for row in json.loads((args.lexical / "private-records.json").read_text()):
        path = args.paired / f"{row['track']}-{row['occurrence']}.json"
        if not path.exists():
            continue
        paired = probe.checkpoints.read_checkpoint(path, pairs_id)
        if (paired["track"], paired["occurrence"]) != (row["track"], row["occurrence"]):
            raise ValueError("Pair evidence belongs to another occurrence.")
        length_ms = (row["crop"]["end_sample"] - row["crop"]["start_sample"]) / 16
        seeds = [
            probe.paired_boundary(a, b, length_ms)
            or {"raw_span": t["raw_span"], "start_ms": -1, "end_ms": -1}
            for a, b, t in zip(
                paired["tifa"], paired["hfa"], row["targets"], strict=True
            )
        ]
        gaps = sum(
            u["start_ms"] >= 0 and old["start_ms"] < 0
            for u, old in zip(seeds, row["baseline"], strict=True)
        )
        if gaps:
            by_track.setdefault(row["track"], []).append((gaps, row, seeds))
            pair_hashes[str(path)] = digest(path)
    cases, groups, summaries = [], [], []
    songs = {s["track"]: s for s in suite["songs"]}
    for track, candidates in by_track.items():
        song = songs[track]
        for key, expected in (("path", "sha256"), ("result_path", "result_sha256")):
            if digest(Path(song[key])) != song[expected]:
                raise ValueError("Changed frozen Rust job/result.")
        job = json.loads(Path(song["path"]).read_text())
        stem = json.loads((args.contexts / track / "stem.json").read_text())
        receipt = next(s for s in contexts["songs"] if s["track"] == track)
        if (
            digest(args.contexts / track / "stem.json")
            != receipt["stem_receipt_sha256"]
            or digest(Path(stem["path"])) != stem["sha256"]
            or digest(Path(song["pcm"])) != job["mono_pcm_sha256"]
            or stem["original_pcm_sha256"] != job["mono_pcm_sha256"]
        ):
            raise ValueError("Changed original or isolated waveform.")
        chosen = sorted(candidates, key=lambda x: (-x[0], x[1]["occurrence"]))[
            : args.cues_per_song
        ]
        summaries.append(
            {
                "track": track,
                "selected_cues": len(chosen),
                "paired_gaps": sum(x[0] for x in chosen),
            }
        )
        for _, row, seeds in chosen:
            crop = row["crop"]
            if crop not in job["crops"]:
                raise ValueError("Candidate crop is not an original Rust export.")
            # Keep pair clocks only for a missing group or its immediate anchor.
            needed = {
                i
                for i, u in enumerate(row["baseline"])
                if u["start_ms"] < 0 and seeds[i]["start_ms"] >= 0
            }
            needed |= {j for i in needed for j in (i - 1, i + 1) if 0 <= j < len(seeds)}
            masks = [
                u
                if i in needed
                else {"raw_span": u["raw_span"], "start_ms": -1, "end_ms": -1}
                for i, u in enumerate(seeds)
            ]
            length = crop["end_sample"] - crop["start_sample"]
            alternate = next(
                (
                    c
                    for c in job["crops"]
                    if c["raw_line"] != crop["raw_line"]
                    and c["start_sample"] >= crop["end_sample"] + 16000
                    and c["start_sample"] + length <= job["recording_samples"]
                ),
                None,
            )
            if alternate is None:
                continue
            ids = []
            for role, path, sha in (
                ("mix", song["pcm"], job["mono_pcm_sha256"]),
                ("kim", stem["path"], stem["sha256"]),
            ):
                ident = f"{track}:{row['occurrence']}:{role}"
                ids.append(ident)
                audio = {
                    "path": path,
                    "sha256": sha,
                    "encoding": "pcm",
                    "first_sample": crop["start_sample"],
                    "last_sample": crop["end_sample"],
                }
                cases.append(
                    {
                        "id": ident,
                        "song": track,
                        "language": "en",
                        "raw_line": crop["raw_line"],
                        "targets": row["targets"],
                        "mask_boundary_units": masks,
                        "mask_boundary_kind": "authenticated original TIFA-HubertFA pair",
                        "audio": audio,
                        "wrong_audio": {
                            **audio,
                            "first_sample": alternate["start_sample"],
                            "last_sample": alternate["start_sample"] + length,
                        },
                    }
                )
            groups.append(
                {
                    "track": track,
                    "occurrence": row["occurrence"],
                    "ids": ids,
                    "baseline": row["baseline"],
                    "source_word_count": row["source_word_count"],
                    "length_ms": length / 16,
                }
            )
    identity = {
        "suite_sha256": digest(args.suite),
        "context_identity_sha256": digest(args.contexts / "identity.json"),
        "pair_identity_sha256": digest(args.paired / "identity.json"),
        "pair_records": pair_hashes,
        "lexical_identity_sha256": digest(args.lexical / "identity.json"),
        "runner_sha256": digest(Path(__file__)),
        "cues_per_song": args.cues_per_song,
        "selection": "descending original paired missing-group count, then occurrence; frozen before acoustic contrast",
    }
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (args.output / "manifest.json").write_text(
        json.dumps(
            {"identity": identity, "cases": cases, "groups": groups},
            indent=2,
            allow_nan=False,
        )
    )
    (args.output / "selection.json").write_text(json.dumps(summaries, indent=2))
    print(
        json.dumps(
            {
                "cue_pairs": len(groups),
                "audio_cases": len(cases),
                "songs": len({g["track"] for g in groups}),
                "masked_groups_per_view": sum(
                    u["start_ms"] >= 0
                    for c in cases[::2]
                    for u in c["mask_boundary_units"]
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
