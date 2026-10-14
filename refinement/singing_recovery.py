"""Timing-only missing-word recovery with TIFA and an independent singing model."""

from english_singing_phones import japanese_hypothesis
from singing_phonemes import kana_phones
from singing_timing import recover_singing_gaps, word_alignment
from tifa_helper import pronunciation


def pronunciation_targets(aligner, targets, mode):
    """Keep source ownership and displayed text; change acoustic hypotheses only."""
    from g2p.converters.base import G2PConversionError

    aliases, phones = {}, []
    for index, target in enumerate(targets):
        text, language = pronunciation(target["text"], target["romaji"])
        if language == "en" and mode is not None:
            try:
                converted = aligner.converters["en"].convert(text)
            except (G2PConversionError, KeyError):
                converted = []
            sequence = (
                [
                    phone
                    for part in converted
                    for group in part.readings[0].paths[0]
                    for phone in group.phonemes
                ]
                if converted
                else []
            )
            candidate = japanese_hypothesis(sequence, mode)
            if candidate:
                aliases[index] = candidate
            phones.append(candidate)
        else:
            phones.append(kana_phones(target["text"], target["romaji"]))
    return aliases, phones


def recover(samples, crops, aligner, posteriors, vocabulary, baseline, counts, update):
    """Reuse captured singing posteriors; every occurrence is timed independently."""
    if not len(crops) == len(posteriors) == len(baseline):
        raise ValueError("Singing timing evidence has another crop sequence.")
    result = []
    for number, ((occurrence, first, last, targets), evidence, units) in enumerate(
        zip(crops, posteriors, baseline, strict=True), 1
    ):
        current = [dict(u) for u in units]
        if any(u["start_ms"] < 0 for u in current):
            update(f"Recovering sung word timings · line {number}/{len(crops)}")
            for mode in (None, "direct", "loan"):
                if all(u["start_ms"] >= 0 for u in current):
                    break
                aliases, phones = pronunciation_targets(aligner, targets, mode)
                if mode is not None and not aliases:
                    continue
                independent = word_alignment(
                    *evidence, targets, vocabulary, word_phones=phones
                )
                if not any(u["mean_probability"] >= 0.45 for u in independent):
                    continue
                raw = []
                trial = aligner.align(
                    samples[first:last],
                    targets,
                    diagnostics=raw,
                    phonetic_aliases=aliases or None,
                )
                current = recover_singing_gaps(
                    current,
                    {"units": trial, "raw_units": raw},
                    independent,
                    (last - first) // 16,
                    counts[str(occurrence)],
                )
            if any(
                u["start_ms"] < 0
                and t.get("pronunciation")
                and t["pronunciation"] != t["text"]
                for t, u in zip(targets, current, strict=True)
            ):
                # Same source groups and selected written readings. The dictionary's
                # inflected spoken form is an acoustic hypothesis only, never a repair.
                spoken = [
                    {**t, "text": t.get("pronunciation") or t["text"]} for t in targets
                ]
                independent = word_alignment(*evidence, spoken, vocabulary)
                raw = []
                trial = aligner.align(samples[first:last], spoken, diagnostics=raw)
                current = recover_singing_gaps(
                    current,
                    {"units": trial, "raw_units": raw},
                    independent,
                    (last - first) // 16,
                    counts[str(occurrence)],
                )
        result.append(current)
    return result
