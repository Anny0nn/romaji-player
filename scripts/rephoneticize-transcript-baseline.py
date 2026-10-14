"""Dictionary-pronunciation ablation of a completed, authenticated Whisper run.

No model is called and no human phones or source lyrics enter this conversion.
Input shadows must describe exactly the already-saved audio-only transcripts.
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path

from audio_first_evaluation import read_run
from audio_first_models import ROOT, digest, kana_sequence_phones, source_word_phones

spec = importlib.util.spec_from_file_location(
    "blind_runner", ROOT / "scripts/recognize-singing-phones.py"
)
blind = importlib.util.module_from_spec(spec)
spec.loader.exec_module(blind)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--shadow", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if ROOT in args.output.resolve().parents:
        parser.error("Transcript-bearing results stay outside the checkout.")
    recipe, rows, complete = read_run(args.run, args.manifest)
    shadow = json.loads(args.shadow.read_text())
    if (
        recipe["engine"] != "whisper"
        or recipe["conversion_signature"] != shadow["conversion_signature"]
    ):
        raise ValueError("Shadow and transcription converter differ.")
    derived = {
        **recipe,
        "derivation": {
            "parent_receipt_sha256": digest(args.run / "complete.json"),
            "shadow_sha256": digest(args.shadow),
            "implementation_sha256": digest(Path(__file__)),
            "pronunciation": "UniDic feature.pron; written display preserved",
        },
    }
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    blind.write(args.output / "recipe.json", derived)
    receipt = []
    for original in complete["records"]:
        row = rows[json.loads((args.run / original["file"]).read_text())["case"]["id"]]
        if not row.get("transcript"):
            raise ValueError(
                "Re-run the legacy baseline to authenticate raw transcripts."
            )
        raw = json.loads((args.run / row["transcript"]).read_text())
        record = shadow["records"][row["case"]["id"]]
        if record["raw_line"] != raw["text"].replace("\n", " ").strip():
            raise ValueError("Shadow describes another transcript.")
        phones = []
        for word in record["words"]:
            spoken = word["pronunciation_kana"]
            phones.extend(
                kana_sequence_phones(spoken) if spoken else source_word_phones(word)
            )
        if record["failure"]:
            phones = ["unsupported:unmapped-transcript"]
        blind.write(args.output / row["transcript"], raw)
        updated = {
            **row,
            "recipe_sha256": digest(args.output / "recipe.json"),
            "heads": {"whisper": {"greedy": {"phones": phones}, "nbest": []}},
        }
        blind.write(args.output / original["file"], updated)
        receipt.append(
            {"file": original["file"], "sha256": digest(args.output / original["file"])}
        )
    blind.write(
        args.output / "complete.json",
        {
            "recipe_sha256": digest(args.output / "recipe.json"),
            "records": receipt,
            "parent_inference_seconds": complete["total_seconds"],
        },
    )
    print(json.dumps({"cases": len(receipt)}))


if __name__ == "__main__":
    main()
