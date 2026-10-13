"""Score completed blind PJS recognition against human phones, never forced labels."""

import argparse
import json
import os
from pathlib import Path

from audio_first_evaluation import read_run, score_sequences
from audio_first_models import ROOT, digest, expanded_phones, kana_sequence_phones
from singing_reference import SILENCE, htk_labels, verify_extracted


def represented(meta, head):
    vocabulary = meta["heads"][head]
    if head in ("kana-phone", "whisper"):
        return set(vocabulary) - {"<blank>"}
    if head == "kana":
        # Individual small/yoon chars are incomplete alone; valid pairs are explicit.
        from g2p.converters.japanese import _KANA_TO_ROMAJI

        return {
            phone
            for kana in [*_KANA_TO_ROMAJI, "ぁ", "ぃ", "ぅ", "ぇ", "ぉ", "ん"]
            if all(char in vocabulary for char in kana)
            for phone in kana_sequence_phones(kana)
            if not phone.startswith("unsupported:")
        }
    return {
        phone
        for label in vocabulary.values()
        for phone in expanded_phones([label], vocabulary)
        if not phone.startswith("unsupported:")
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--pjs", type=Path, required=True)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if ROOT in args.output.resolve().parents or ROOT in args.pjs.resolve().parents:
        parser.error("References/results must live outside the checkout.")
    runs = [read_run(path, args.manifest) for path in args.runs]
    inventory = set.intersection(
        *(
            represented(recipe["model"], head)
            for recipe, _, _ in runs
            for head in recipe["model"]["heads"]
        )
    )
    rows = runs[0][1]
    references, omitted, labels_hashes = {}, {}, {}
    for name, row in rows.items():
        if not name.startswith("pjs") or not name[3:].isdigit():
            raise ValueError("PJS evaluation cannot score commercial cases.")
        path = args.pjs / "labels" / f"{name}.lab"
        verify_extracted(args.pjs / "labels.zip", path)
        audio = args.pjs / "audio" / f"{name}_song.wav"
        verify_extracted(args.pjs / "audio.zip", audio)
        if row["case"]["sha256"] != digest(audio) or row["case"]["first_sample"] != 0:
            raise ValueError(
                "Recognition does not contain the complete reference recording."
            )
        labels = htk_labels(path.read_text(), row["case"]["last_sample"] / 16)
        phones = [r["phone"] for r in labels if r["phone"] not in SILENCE]
        labels_hashes[name] = digest(path)
        unknown = sorted(set(phones) - inventory)
        if unknown:
            omitted[name] = {"reference_phones": len(phones), "unsupported": unknown}
        else:
            references[name] = phones
    metrics = {}
    for recipe, predictions, _ in runs:
        for head in recipe["model"]["heads"]:
            for decoder in ("greedy", "beam"):
                if decoder == "beam" and recipe["decoder"]["greedy_only"]:
                    continue
                sequences = {}
                for name in references:
                    result = predictions[name]["heads"].get(head)
                    sequences[name] = (
                        []
                        if result is None
                        else result["greedy"]["phones"]
                        if decoder == "greedy"
                        else result["nbest"][0]["phones"]
                    )
                key = f"{head}-{decoder}"
                if key in metrics:
                    raise ValueError(
                        "Duplicate recipe name; evaluate variants separately."
                    )
                metrics[key] = score_sequences(references, sequences)
    result = {
        "granularity": "recognized_phone_sequence",
        "lexical_reading_accuracy_measured": False,
        "common_phone_inventory": sorted(inventory),
        "total_clips": len(rows),
        "omitted": omitted,
        "reference_hashes": labels_hashes,
        "manifest_sha256": digest(args.manifest),
        "runs": {str(p): digest(p / "complete.json") for p in args.runs},
        "metrics": metrics,
    }
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    print(
        json.dumps(
            {"clips": len(rows), "omitted_clips": len(omitted), "metrics": metrics}
        )
    )


if __name__ == "__main__":
    main()
