"""Independent acoustic admission of controlled source-anchored reading proposals.

Compare source-blind proposals with Whisper using the same reconciler and the
current single-word dictionary/transcript proposal core. This is not app playback.
"""

import argparse
import importlib.util
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

from audio_first_evaluation import read_run
from audio_first_models import ROOT, digest, kana_sequence_phones
from audio_first_reconciliation import baseline_first, preserve_spelling

sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa")]
spec = importlib.util.spec_from_file_location(
    "reading_benchmark", ROOT / "scripts/benchmark-reading-reconciliation.py"
)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def load_evidence(directory, cases):
    import numpy as np

    recipe = json.loads((directory / "recipe.json").read_text())
    complete = json.loads((directory / "complete.json").read_text())
    if complete["recipe_sha256"] != digest(directory / "recipe.json") or recipe[
        "cases_sha256"
    ] != digest(cases):
        raise ValueError("Independent evidence belongs to other challenge inputs.")
    result = defaultdict(dict)
    for row in complete["records"]:
        name = row["file"]
        if Path(name).name != name or digest(directory / name) != row["sha256"]:
            raise ValueError("Independent evidence changed.")
        if row["view"] not in (0, 1) or row["view"] in result[row["id"]]:
            raise ValueError("Invalid or repeated acoustic view.")
        with np.load(directory / name, allow_pickle=False) as archive:
            result[row["id"]][row["view"]] = (
                archive["logp"].copy(),
                int(archive["blank"]),
            )
    if any(set(views) != {0, 1} for views in result.values()):
        raise ValueError("Independent verifier requires both real audio views.")
    return result, complete["vocabulary"]


def main():
    import numpy as np
    import refinement_helper
    import torch
    from fast_ctc_path import ctc_path
    from reading_policy import rank, verify
    from reading_repair import Converter, mapped_candidates, output_words

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--romaji", type=Path, required=True)
    parser.add_argument("--whisper", type=Path, required=True)
    parser.add_argument("--romanizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proposer-margin", type=float)
    args = parser.parse_args()
    if args.proposer_margin is not None and not 0 <= args.proposer_margin <= 64:
        parser.error("Use a finite proposer margin between zero and 64 log units.")
    if ROOT in args.output.resolve().parents:
        parser.error("Private references and scores must remain outside git.")
    torch.set_num_threads(4)
    # Offline acceleration is regression-tested against the app's exact path.
    refinement_helper.ctc_path = ctc_path
    recipe, recognition, _ = read_run(args.romaji, args.manifest)
    _, whisper_rows, _ = read_run(args.whisper, args.manifest)
    if any(not row.get("transcript") for row in whisper_rows.values()):
        raise ValueError("Re-run the legacy Whisper baseline to authenticate raw text.")
    frozen = json.loads(args.cases.read_text())
    evidence, vocabulary = load_evidence(args.evidence, args.cases)
    proposals = {
        (p["case"], p["recipe"], p["condition"]): p["proposals"]
        for p in json.loads(args.proposals.read_text())
    }
    converter = Converter(args.romanizer.resolve())
    if converter.signature != frozen["provenance"]["converter_signature"]:
        raise ValueError("Frozen source conversion changed.")
    counts = defaultdict(Counter)
    source_cache = {}
    rows = []
    posteriors = {}
    try:
        for number, case in enumerate(frozen["cases"], 1):
            name, index = case["recording"], case["word"]
            if name not in source_cache:
                template = {
                    "protocol_version": 2,
                    "request_id": number,
                    "track_id": "pjs-source",
                    "snapshot_id": recognition[name]["case"]["sha256"],
                    "occurrence_id": 0,
                    "override_revision": 0,
                    "expected_conversion_signature": converter.signature,
                    "raw_line": case["raw_line"],
                    "overrides": [],
                }
                source = converter.convert(template, candidates=True)
                transcript = json.loads(
                    (args.whisper / whisper_rows[name]["transcript"]).read_text()
                )["text"]
                observation = output_words(
                    converter.convert(
                        {
                            **template,
                            "track_id": "independent-transcript",
                            "raw_line": transcript.replace("\n", " ").strip(),
                        }
                    )
                )
                source_cache[name] = (template, source, observation)
            template, source, observation = source_cache[name]
            for condition in ("unchanged", "injected"):
                words = [
                    {
                        "raw_span": w["raw_span"],
                        "text": w["hiragana"],
                        "romaji": w["romaji"],
                    }
                    for w in case["words"]
                ]
                if condition == "injected":
                    fault = converter.canonical(case["fault_kana"], template)
                    words[index].update(text=fault["hiragana"], romaji=fault["romaji"])
                for method in ("romaji-beam", "whisper", "current-core"):
                    key = method + "-" + condition
                    counts[key]["eligible"] += 1
                    alternatives = []
                    grounded = set()
                    if method == "current-core":
                        group = next(
                            (
                                g
                                for g in source.get("reading_candidates", [])
                                if g["raw_span"] == words[index]["raw_span"]
                            ),
                            None,
                        )
                        if group:
                            alternatives.extend(group["candidates"])
                        for match in mapped_candidates(words, observation):
                            if match["first"] == index and match["last"] == index + 1:
                                matched = converter.canonical(
                                    match["hiragana"], template
                                )
                                alternatives.append(matched)
                                grounded.add(matched["hiragana"])
                    else:
                        for patch in proposals[(case["id"], method, condition)]:
                            if (
                                patch["first_word"] != index
                                or patch["last_word"] != index + 1
                            ):
                                continue
                            kana = preserve_spelling(
                                patch["kana_candidates"], words[index]["text"]
                            )
                            if kana is None:
                                counts[key]["ambiguous_spelling"] += 1
                                continue
                            alternatives.append(converter.canonical(kana, template))
                    if not alternatives:
                        continue
                    counts[key]["candidate_available"] += 1
                    selected = rank(
                        words,
                        index,
                        alternatives,
                        [evidence[name][view] for view in (0, 1)],
                        vocabulary,
                    )
                    if not selected or not selected["acoustic_pass"]:
                        continue
                    counts[key]["paired_mms_pass"] += 1
                    verification = None
                    if method == "romaji-beam" and args.proposer_margin is not None:
                        from singing_phonemes import phrase_score

                        if name not in posteriors:
                            posterior = recognition[name]["heads"]["romaji"][
                                "posterior"
                            ]
                            with np.load(
                                args.romaji / posterior, allow_pickle=False
                            ) as archive:
                                posteriors[name] = (
                                    archive["logp"].copy(),
                                    int(archive["blank"]),
                                )
                        logp, blank = posteriors[name]
                        phone_vocabulary = recipe["model"]["heads"]["romaji"]
                        original = phrase_score(logp, blank, words, phone_vocabulary)
                        trial = [dict(w) for w in words]
                        trial[index].update(
                            text=selected["hiragana"], romaji=selected["romaji"]
                        )
                        candidate = phrase_score(logp, blank, trial, phone_vocabulary)
                        competing = [original] if original is not None else []
                        for alternative in alternatives:
                            if kana_sequence_phones(
                                alternative["hiragana"]
                            ) == kana_sequence_phones(selected["hiragana"]):
                                continue
                            trial[index].update(
                                text=alternative["hiragana"],
                                romaji=alternative["romaji"],
                            )
                            value = phrase_score(logp, blank, trial, phone_vocabulary)
                            if value is not None:
                                competing.append(value)
                        if (
                            candidate is None
                            or not competing
                            or candidate - max(competing) < args.proposer_margin
                        ):
                            counts[key]["proposer_uncertain"] += 1
                            continue
                    if method == "current-core":
                        posterior = recognition[name]["heads"]["romaji"]["posterior"]
                        with np.load(
                            args.romaji / posterior, allow_pickle=False
                        ) as archive:
                            verification = verify(
                                words,
                                index,
                                selected,
                                alternatives,
                                archive["logp"],
                                int(archive["blank"]),
                                recipe["model"]["heads"]["romaji"],
                                transcript_supported=selected["hiragana"] in grounded,
                            )
                        if not verification or not verification["supported"]:
                            continue
                    # Audio-first RomajiASR proposes. Its own score isn't another vote.
                    # The distinct MMS network provides the independent acoustic check.
                    correct = (
                        kana_sequence_phones(selected["hiragana"])
                        == case["reference_phones"]
                    )
                    counts[key]["accepted"] += 1
                    counts[key]["correct"] += correct
                    counts[key]["incorrect"] += not correct
                    rows.append(
                        {
                            "case": case["id"],
                            "method": method,
                            "condition": condition,
                            "selected": selected,
                            "verification": verification,
                            "correct": correct,
                        }
                    )
            if number % 25 == 0:
                print(
                    json.dumps({"scored": number, "total": len(frozen["cases"])}),
                    flush=True,
                )
    finally:
        converter.close()
    fallback = baseline_first(rows)
    for condition in ("unchanged", "injected"):
        key = "core-then-blind-" + condition
        counts[key]["eligible"] = len(frozen["cases"])
    for row in fallback:
        key = "core-then-blind-" + row["condition"]
        counts[key]["accepted"] += 1
        counts[key]["correct"] += row["correct"]
        counts[key]["incorrect"] += not row["correct"]
    rows.extend(fallback)
    output = args.output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.umask(0o077)
    provenance = {
        "cases_sha256": digest(args.cases),
        "proposals_sha256": digest(args.proposals),
        "evidence_sha256": digest(args.evidence / "complete.json"),
        "implementation_sha256": digest(Path(__file__)),
        "policy_sha256": digest(ROOT / "refinement/reading_policy.py"),
        "accelerator_sha256": digest(ROOT / "scripts/fast_ctc_path.py"),
        "proposer_margin": args.proposer_margin,
        "whisper_receipt_sha256": digest(args.whisper / "complete.json"),
        "romaji_receipt_sha256": digest(args.romaji / "complete.json"),
        "fallback_rule": "current-core admission first; blind admission on abstentions only",
    }
    (output / "accepted.json").write_text(json.dumps(rows, ensure_ascii=False))
    (output / "summary.json").write_text(
        json.dumps(
            {
                "provenance": provenance,
                "metrics": dict(counts),
                "current_core_independent_view": "original PJS vocals; full app integration not replayed",
                "timing_evaluated": False,
            },
            indent=2,
        )
    )
    print(json.dumps({"metrics": dict(counts)}))


if __name__ == "__main__":
    main()
