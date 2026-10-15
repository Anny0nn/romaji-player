"""Exact English correspondence from closed, source-blind Qwen observations.

No inference or word clocks. Budget exhaustion and non-English detections withhold
the complete view before scoring. Outputs contain lyrics and stay outside Git.
"""

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from hubertfa_research import ROOT, digest, private_path
from qwen_lexical import decoder_words, exact_matches


def main():
    from transformers import AutoTokenizer

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--model-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.manifest, args.observations, args.model_directory, args.output = map(
        private_path,
        (args.manifest, args.observations, args.model_directory, args.output),
    )
    manifest = json.loads(args.manifest.read_text())
    identity = json.loads((args.observations / "identity.json").read_text())
    complete = json.loads((args.observations / "complete.json").read_text())
    pin = json.loads((ROOT / "scripts/qwen-singing-files.json").read_text())
    if (
        identity["assets"] != pin
        or identity["source_prompt"] is not None
        or identity["do_sample"] is not False
        or complete["identity_sha256"] != digest(args.observations / "identity.json")
    ):
        raise ValueError("Expected completed source-blind pinned Qwen observations.")
    for name, expected in pin["files"].items():
        path = args.model_directory / name
        if (
            path.stat().st_size != expected["size"]
            or digest(path) != expected["sha256"]
        ):
            raise ValueError("Changed pinned tokenizer/model assets.")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_directory, local_files_only=True, trust_remote_code=False
    )
    observed = {}
    for entry in complete["records"]:
        path = args.observations / entry["file"]
        if Path(entry["file"]).name != entry["file"] or digest(path) != entry["sha256"]:
            raise ValueError("Changed closed recognition record.")
        row = json.loads(path.read_text())
        if (
            row["identity_sha256"] != complete["identity_sha256"]
            or row["id"] in observed
        ):
            raise ValueError("Changed/duplicate Qwen observation ownership.")
        observed[row["id"]] = row
    if len(manifest["cases"]) != len(observed) or set(observed) != {
        c["id"] for c in manifest["cases"]
    }:
        raise ValueError("Incomplete or duplicate source candidate set.")
    counts, records = Counter(), []
    for case in manifest["cases"]:
        row = observed[case["id"]]
        if row["case"] != {"id": case["id"], **case["audio"]}:
            raise ValueError("Source and audio observations use different crops.")
        exhausted = row["budget_exhausted"]
        detected = row["decoded"].get("language")
        # A forced language is a hypothesis, never detected-language evidence.
        language_ok = detected == "English" or (
            identity["language"] == "en" and detected is None
        )
        words = (
            decoder_words(
                tokenizer,
                row["decoded_tokens"],
                row["token_log_probabilities"],
                row["decoded"]["transcription"],
            )
            if not exhausted and language_ok
            else []
        )
        flags = exact_matches(case["targets"], words)
        counts.update(
            cases=1,
            original_groups=len(flags),
            exact_multiword_matches=sum(u["source_match"] for u in flags),
            exhausted_views=exhausted,
            other_language_views=not language_ok,
        )
        records.append(
            {
                "id": case["id"],
                "words": words,
                "source_views": flags,
                "detected_language": detected,
                "forced_language": identity["language"],
                "budget_exhausted": exhausted,
            }
        )
    recipe = {
        "manifest_sha256": digest(args.manifest),
        "recognition_complete_sha256": digest(args.observations / "complete.json"),
        "recognition_identity_sha256": digest(args.observations / "identity.json"),
        "code": {
            name: digest(ROOT / "scripts" / name)
            for name in ("collect-qwen-lexical.py", "qwen_lexical.py")
        },
        "confidence_kind": "qwen-free-decoder-geometric-mean",
        "word_probability_floor": 0.7,
        "minimum_unique_matching_block": 2,
        "supplies_word_timestamps": False,
        "language_routing_is_not_gold": True,
    }
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (args.output / "private-records.json").write_text(
        json.dumps(records, indent=2, allow_nan=False)
    )
    recipe["records_sha256"] = digest(args.output / "private-records.json")
    (args.output / "identity.json").write_text(json.dumps(recipe, indent=2))
    (args.output / "summary.json").write_text(json.dumps(counts, indent=2))
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
