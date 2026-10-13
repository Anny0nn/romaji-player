"""Private controlled reading faults on labelled PJS source-word envelopes.

Only completed source-blind recognition is consumed. These are injected reading
errors, not newly listening-verified mistakes in commercial lyrics. No app writes.
"""

import argparse
import copy
import json
import os
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from audio_first_evaluation import read_run
from audio_first_models import ROOT, digest, kana_sequence_phones, source_word_phones
from audio_first_pronunciation import attach_shadow, spelling_candidates
from audio_first_reconciliation import envelopes, kana_candidates
from singing_reference import SILENCE, htk_labels, verify_extracted

sys.path.insert(0, str(ROOT / "refinement"))


def inverse_inventory():
    from g2p.converters.japanese import _KANA_TO_ROMAJI

    mapping = defaultdict(list)
    for kana in [*_KANA_TO_ROMAJI, "ん"]:
        phones = kana_sequence_phones(kana)
        if not any(p.startswith("unsupported:") for p in phones):
            mapping[tuple(phones)].append(kana)
    return dict(mapping)


def parse_sentences(text):
    lines = text.splitlines()
    if not lines or lines[0].split() != [
        "sentence_id",
        "sentence",
        "yomi",
        "monophone",
    ]:
        raise ValueError("Expected official sentence columns, not musical metadata.")
    records = {}
    for line in lines[1:]:
        fields = line.split()
        if len(fields) != 4 or len(fields[0]) != 3 or not fields[0].isdigit():
            raise ValueError("Invalid official sentence row.")
        name = "pjs" + fields[0]
        if name in records:
            raise ValueError("Duplicate corpus sentence.")
        records[name] = fields[1]
    return records


def source_sentences(path):
    # Archive pjsNNN.txt files describe key/tempo/artists, NOT lyric text.
    if (
        digest(path)
        != "1ed75aba2a0d3548f548ee4a8afd00cfd4cff37de5620424112f745d9e4e31a6"
    ):
        raise ValueError("Pinned source-sentence file changed.")
    records = parse_sentences(path.read_text())
    if len(records) != 100:
        raise ValueError("Incomplete official sentence set.")
    return records


def eligible_words(readings, reference):
    """Exact, unique manual-phone ownership; no endpoints inferred from syllables."""
    old = [p for phones in readings for p in phones]
    matcher = SequenceMatcher(None, old, reference, autojunk=False)
    correspondence = {
        b.a + i: b.b + i for b in matcher.get_matching_blocks() for i in range(b.size)
    }
    first, result = 0, []
    for index, phones in enumerate(readings):
        last = first + len(phones)
        if index not in (0, len(readings) - 1) and first >= 2 and last + 1 < len(old):
            source = list(range(first - 2, last + 2))
            mapped = [correspondence.get(p) for p in source]
            if all(p is not None for p in mapped) and mapped == list(
                range(mapped[0], mapped[0] + len(mapped))
            ):
                context = old[first - 2 : last + 2]
                if (
                    sum(
                        reference[i : i + len(context)] == context
                        for i in range(len(reference) - len(context) + 1)
                    )
                    == 1
                ):
                    result.append(
                        (index, correspondence[first], correspondence[last - 1] + 1)
                    )
        first = last
    return result


def source_words(converter, text, number, snapshot):
    response = converter.convert(
        {
            "protocol_version": 1,
            "request_id": number,
            "track_id": "pjs-source",
            "snapshot_id": snapshot,
            "occurrence_id": 0,
            "override_revision": 0,
            "expected_conversion_signature": converter.signature,
            "raw_line": text,
            "overrides": [],
        }
    )
    words = []
    for word in response["words"]:
        if word["raw_span"] is None or word["hiragana_span"] is None:
            return None
        a, b = word["hiragana_span"]
        kana = response["hiragana"].encode()[a:b].decode()
        a, b = word["output_span"]
        roman = response["romaji"].encode()[a:b].decode()
        words.append(
            {
                "raw_span": word["raw_span"],
                "expected_text": word["expected_text"],
                "hiragana": kana,
                "romaji": roman,
            }
        )
    return words


def proposals(text, words, observed, inventory):
    readings = [w.get("pronunciation_phones", source_word_phones(w)) for w in words]
    result = []
    for patch in envelopes(text, words, observed, readings):
        candidates = (
            spelling_candidates(patch["phones"], inventory, words[patch["first_word"]])
            if patch["last_word"] == patch["first_word"] + 1
            else kana_candidates(patch["phones"], inventory)
        )
        if candidates:
            result.append({**patch, "kana_candidates": candidates})
    return result


def main():
    from reading_repair import Converter

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--pjs", type=Path, required=True)
    parser.add_argument("--sentences", type=Path, required=True)
    parser.add_argument("--romaji", type=Path, required=True)
    parser.add_argument("--whisper", type=Path, required=True)
    parser.add_argument("--romanizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hypotheses", type=int, default=1)
    parser.add_argument("--reuse-cases", type=Path)
    parser.add_argument("--shadow", type=Path)
    args = parser.parse_args()
    if not 1 <= args.hypotheses <= 8:
        parser.error("Use one to eight already decoded audio hypotheses.")
    if ROOT in args.output.resolve().parents:
        parser.error("Private references/results must stay outside the checkout.")
    _, recognized, _ = read_run(args.romaji, args.manifest)
    _, baseline, _ = read_run(args.whisper, args.manifest)
    inventory = inverse_inventory()
    sentences = source_sentences(args.sentences)
    converter = Converter(args.romanizer.resolve())
    shadow = json.loads(args.shadow.read_text()) if args.shadow else None
    if shadow and shadow["conversion_signature"] != converter.signature:
        raise ValueError("Pronunciation dictionary changed.")
    cases = []
    try:
        if args.reuse_cases:
            frozen = json.loads(args.reuse_cases.read_text())
            if frozen["provenance"]["converter_signature"] != converter.signature:
                raise ValueError("Frozen canonical reading inputs changed.")
            cases = frozen["cases"]
        for number, (name, row) in enumerate(recognized.items(), 1):
            if args.reuse_cases:
                break
            text = sentences[name]
            words = source_words(converter, text, number, row["case"]["sha256"])
            if not words:
                continue
            readings = [source_word_phones(w) for w in words]
            if any(p.startswith("unsupported:") for phones in readings for p in phones):
                continue
            label = args.pjs / "labels" / f"{name}.lab"
            verify_extracted(args.pjs / "labels.zip", label)
            refs = htk_labels(label.read_text(), row["case"]["last_sample"] / 16)
            reference = [r["phone"] for r in refs if r["phone"] not in SILENCE]
            if any(p in ("I", "U", "O") for p in reference):
                continue
            for index, first, last in eligible_words(readings, reference):
                # Fixed deterministic vowel fault, never selected by model outcomes.
                phones = readings[index].copy()
                at = next((i for i, p in enumerate(phones) if p in "aiueo"), None)
                if at is None:
                    continue
                phones[at] = {"a": "i", "i": "u", "u": "e", "e": "o", "o": "a"}[
                    phones[at]
                ]
                fault = kana_candidates(phones, inventory)
                if not fault:
                    continue
                cases.append(
                    {
                        "id": f"{name}:{index}",
                        "recording": name,
                        "raw_line": text,
                        "words": words,
                        "word": index,
                        "reference_phone_span": [first, last],
                        "reference_phones": readings[index],
                        "fault_kana": fault[0],
                    }
                )
    finally:
        converter.close()
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.umask(0o077)
    signature = {
        "audio_archive_sha256": digest(args.pjs / "audio.zip"),
        "labels_archive_sha256": digest(args.pjs / "labels.zip"),
        "sentences_sha256": digest(args.sentences),
        "sentences_revision": "22923912010c358a4a044702e78b343f3ba8123f",
        "romaji_receipt_sha256": digest(args.romaji / "complete.json"),
        "whisper_receipt_sha256": digest(args.whisper / "complete.json"),
        "implementation_sha256": digest(Path(__file__)),
        "mapping_sha256": digest(ROOT / "scripts/audio_first_reconciliation.py"),
        "converter_signature": converter.signature,
        "fault_rule": "first-vowel-cycle-v1",
        "hypotheses": args.hypotheses,
        "reused_cases_sha256": digest(args.reuse_cases) if args.reuse_cases else None,
        "pronunciation_shadow_sha256": digest(args.shadow) if args.shadow else None,
    }
    (output / "frozen-cases.json").write_text(
        json.dumps({"provenance": signature, "cases": cases}, ensure_ascii=False)
    )
    totals = defaultdict(Counter)
    details = []
    for case in cases:
        name, index = case["recording"], case["word"]
        record = recognized[name]["heads"]["romaji"]
        observed = {
            "romaji-beam": [h["phones"] for h in record["nbest"][: args.hypotheses]],
            "romaji-greedy": [record["greedy"]["phones"]],
            "whisper": [baseline[name]["heads"]["whisper"]["greedy"]["phones"]],
        }
        for condition in ("unchanged", "injected"):
            words = copy.deepcopy(case["words"])
            if shadow:
                record = shadow["records"][name]
                if record["raw_line"] != case["raw_line"]:
                    raise ValueError("Pronunciation shadow has different lyrics.")
                words = attach_shadow(words, record)
            if condition == "injected":
                words[index]["hiragana"] = case["fault_kana"]
                # The injected faulty reading is a copied candidate, not a new
                # dictionary lookup of the unchanged original Japanese.
                for key in (
                    "pronunciation_phones",
                    "pronunciation_boundaries",
                    "pronunciation_kana",
                ):
                    words[index].pop(key, None)
            for recipe, hypotheses in observed.items():
                unique = {}
                for hypothesis_rank, phones in enumerate(hypotheses):
                    for patch in proposals(case["raw_line"], words, phones, inventory):
                        key = (
                            patch["first_word"],
                            patch["last_word"],
                            tuple(patch["phones"]),
                        )
                        unique.setdefault(
                            key, {**patch, "hypothesis_rank": hypothesis_rank}
                        )
                patches = list(unique.values())
                touching = [
                    p for p in patches if p["first_word"] <= index < p["last_word"]
                ]
                key = recipe + "-" + condition
                totals[key]["eligible"] += 1
                totals[key]["proposed"] += bool(touching)
                correct = bool(touching) and any(
                    p["first_word"] == index
                    and p["last_word"] == index + 1
                    and p["phones"] == case["reference_phones"]
                    for p in touching
                )
                totals[key]["exact_single_word_recovery"] += correct
                totals[key]["other_proposal"] += bool(touching) and not correct
                details.append(
                    {
                        "case": case["id"],
                        "recipe": recipe,
                        "condition": condition,
                        "proposals": touching,
                    }
                )
    (output / "proposals.json").write_text(json.dumps(details, ensure_ascii=False))
    result = {
        "provenance": signature,
        "cases": len(cases),
        "songs": len({c["recording"] for c in cases}),
        "metrics": dict(totals),
        "verified_acoustic_admission": False,
        "natural_commercial_repairs_measured": False,
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("cases", "songs", "metrics")}))


if __name__ == "__main__":
    main()
