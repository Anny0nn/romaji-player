"""Export trusted Cutlet node pronunciations without altering displayed readings.

Run with the existing romanizer environment. Input is a private JSON id→text map;
no audio or reference labels enter this dictionary-only stage.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from audio_first_models import ROOT, digest

sys.path.insert(0, str(ROOT / "romanizer"))


def shadow(converter, text, number):
    import jaconv

    response = converter.convert(
        {
            "protocol_version": 1,
            "request_id": number,
            "track_id": "dictionary-shadow",
            "snapshot_id": "research",
            "occurrence_id": 0,
            "override_revision": 0,
            "expected_conversion_signature": converter.signature,
            "raw_line": text,
            "overrides": [],
        }
    )
    nodes, cursor = {}, 0
    for node in converter.cut.tagger(response["normalized_line"]):
        cursor += node.rlength
        span = (cursor - node.length, cursor)
        # pron is the inflected form; pronBase would incorrectly use the lemma.
        pronunciation = None if node.is_unk else node.feature.pron
        nodes[span] = jaconv.kata2hira(pronunciation) if pronunciation else None
    words = []
    for word in response["words"]:
        if word["raw_span"] is None or word["hiragana_span"] is None:
            return {"raw_line": text, "words": [], "failure": "unmapped_source"}
        a, b = word["hiragana_span"]
        written = response["hiragana"].encode()[a:b].decode()
        a, b = word["output_span"]
        roman = response["romaji"].encode()[a:b].decode()
        pieces = [nodes.get(tuple(span)) for span in word["constituent_nodes"]]
        spoken = "".join(pieces) if pieces and all(pieces) else None
        exported = {
            "raw_span": word["raw_span"],
            "expected_text": word["expected_text"],
            "hiragana": written,
            "romaji": roman,
            "pronunciation_kana": spoken,
        }
        words.append(exported)
    return {"raw_line": text, "words": words, "failure": None}


def main():
    from romanizer import Converter

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("texts", type=Path)
    parser.add_argument("--signature", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if ROOT in args.output.resolve().parents or args.output.exists():
        parser.error("Use a fresh private output outside the checkout.")
    converter = Converter()
    if converter.signature != args.signature:
        raise ValueError("Research dictionary differs from the bundled converter.")
    texts = json.loads(args.texts.read_text())
    if not isinstance(texts, dict) or any(
        not isinstance(v, str) for v in texts.values()
    ):
        raise ValueError("Expected private id→raw-text map.")
    value = {
        "texts_sha256": digest(args.texts),
        "conversion_signature": converter.signature,
        "implementation_sha256": digest(Path(__file__)),
        "mapping_sha256": digest(ROOT / "scripts/audio_first_pronunciation.py"),
        "records": {
            key: shadow(converter, text, n)
            for n, (key, text) in enumerate(texts.items(), 1)
        },
    }
    os.umask(0o077)
    args.output.write_text(json.dumps(value, ensure_ascii=False))
    print(
        json.dumps(
            {
                "records": len(texts),
                "failed": sum(
                    r["failure"] is not None for r in value["records"].values()
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
