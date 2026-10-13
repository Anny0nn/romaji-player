"""Source-anchored audit of completed commercial-song blind recognition.

No listening labels are inferred. Six maintainer-verified Tabi occurrences are
scored separately from unverified proposals across the fourteen development songs.
"""

import argparse
import importlib.util
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from audio_first_evaluation import read_run
from audio_first_models import ROOT, digest
from audio_first_pronunciation import attach_shadow

spec = importlib.util.spec_from_file_location(
    "reading_benchmark", ROOT / "scripts/benchmark-reading-reconciliation.py"
)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def main():
    from reading_repair import Converter

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--recognition", type=Path, required=True)
    parser.add_argument("--romanizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--shadow", type=Path)
    parser.add_argument("--hypotheses", type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.hypotheses <= 8:
        parser.error("Use one to eight already decoded hypotheses.")
    if ROOT in args.output.resolve().parents:
        parser.error("Full lyrics and predictions must remain outside git.")
    _, rows, _ = read_run(args.recognition, args.manifest)
    sources = {
        c["id"]: c
        for c in json.loads(args.sources.read_text())
        if not c["id"].startswith("control:")
    }
    if set(sources) != set(rows):
        raise ValueError("Source/recognition occurrence identities differ.")
    converter = Converter(args.romanizer.resolve())
    shadow = json.loads(args.shadow.read_text()) if args.shadow else None
    if shadow and shadow["conversion_signature"] != converter.signature:
        raise ValueError("Pronunciation dictionary changed.")
    inventory = benchmark.inverse_inventory()
    totals = defaultdict(Counter)
    proposals = []
    verified = []
    known = {"闇夜": "やみよ", "行こう": "ゆこう", "ハッカ色": "はっかいろ"}
    try:
        for number, (name, row) in enumerate(rows.items(), 1):
            source = sources[name]
            if row["case"]["sha256"] != source["audio_sha256"] or (
                row["case"]["first_sample"] != source["start_ms"] * 16
                or row["case"]["last_sample"] != source["end_ms"] * 16
            ):
                raise ValueError("Source and audio bounds changed.")
            words = benchmark.source_words(
                converter, source["raw_line"], number, source["snapshot"]
            )
            counts = totals[source["track"]]
            counts["crops"] += 1
            counts["cached_source_words"] += len(source["words"])
            if not words:
                counts["unmapped_crops"] += 1
                continue
            if shadow:
                record = shadow["records"][name]
                if record["raw_line"] != source["raw_line"]:
                    raise ValueError("Pronunciation shadow has different lyrics.")
                words = attach_shadow(words, record)
            counts["canonical_display_words"] += len(words)
            recognized = row["heads"]["romaji"]
            variants = {
                "greedy": [recognized["greedy"]["phones"]],
                "beam": [h["phones"] for h in recognized["nbest"][: args.hypotheses]],
            }
            by_decoder = {}
            for decoder, hypotheses in variants.items():
                changes = []
                for phones in hypotheses:
                    for change in benchmark.proposals(
                        source["raw_line"], words, phones, inventory
                    ):
                        if change not in changes:
                            changes.append(change)
                counts[decoder + "_source_envelopes"] += len(changes)
                proposals.append(
                    {
                        "id": name,
                        "track": source["track"],
                        "decoder": decoder,
                        "proposals": changes,
                    }
                )
                by_decoder[decoder] = changes
            if source["track"] == "6KeWalxT7jDYdNfwiBtBzt":
                for match in re.finditer("闇夜|行こう|ハッカ色", source["raw_line"]):
                    span = [
                        len(source["raw_line"][: match.start()].encode()),
                        len(source["raw_line"][: match.end()].encode()),
                    ]
                    expected = known[match.group()]
                    scores = {
                        decoder: any(
                            p["raw_span"] == span and expected in p["kana_candidates"]
                            for p in changes
                        )
                        for decoder, changes in by_decoder.items()
                    }
                    verified.append(
                        {
                            "id": name,
                            "source_span": span,
                            "source_text": match.group(),
                            "verified_reading": expected,
                            "anchored_candidate": scores,
                        }
                    )
    finally:
        converter.close()
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    (output / "proposals.json").write_text(json.dumps(proposals, ensure_ascii=False))
    result = {
        "manifest_sha256": digest(args.manifest),
        "sources_sha256": digest(args.sources),
        "recognition_receipt_sha256": digest(args.recognition / "complete.json"),
        "implementation_sha256": digest(Path(__file__)),
        "conversion_signature": converter.signature,
        "hypotheses": args.hypotheses,
        "shadow_sha256": digest(args.shadow) if args.shadow else None,
        "totals": dict(totals),
        "verified_tabi_occurrences": verified,
        "acoustic_admission_evaluated": False,
        "unverified_reading_accuracy_measured": False,
    }
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )
    print(
        json.dumps(
            {
                "tracks": len(totals),
                "totals": dict(totals),
                "verified_tabi_occurrences": len(verified),
                "tabi_beam_anchored_candidates": sum(
                    v["anchored_candidate"]["beam"] for v in verified
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
