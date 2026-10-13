"""Source-anchored sung-reading evidence. Coverage never authorizes a repair."""

import math
import re

from refinement_policy import ctc_labels

RECIPE = "sung-reading-v1"
MIN_GAIN = 8.0
MIN_MARGIN = 8.0
MIN_PROBABILITY = 0.45


def spelling(text):
    return re.sub(r"[ '\-]", "", text.lower())


def score(logp, blank, words, vocabulary):
    """Full-line CTC likelihood; compare candidates on identical audio frames."""
    import torch

    if any(
        not spelling(w["romaji"])
        or any(c not in vocabulary for c in spelling(w["romaji"]))
        for w in words
    ):
        return None
    labels = ctc_labels(words, vocabulary)
    if not labels or blank in labels:
        return None
    rows = torch.tensor(logp, dtype=torch.float32)[:, None, :]
    value = -torch.nn.functional.ctc_loss(
        rows,
        torch.tensor(labels),
        torch.tensor([len(logp)]),
        torch.tensor([len(labels)]),
        blank=blank,
        reduction="sum",
        zero_infinity=False,
    ).item()
    return value if math.isfinite(value) else None


def decision(views):
    """Two correlated views must agree; neither replaces an independent check."""
    if len(views) != 2:
        return False
    return all(
        all(
            math.isfinite(v.get(k, math.nan))
            for k in ("gain", "margin", "probability", "context")
        )
        and v["gain"] >= MIN_GAIN
        and v["margin"] >= MIN_MARGIN
        and MIN_PROBABILITY <= v["probability"] <= 1
        and 0.5 <= v["context"] <= 1
        for v in views
    )


def rank(words, index, candidates, views, vocabulary, include_baseline=False):
    """Return winner and measurements, not a persistence instruction."""
    from refinement_helper import phonetic_units

    baseline = {"hiragana": words[index]["text"], "romaji": words[index]["romaji"]}
    unique = {spelling(baseline["romaji"]): baseline}
    for candidate in candidates:
        unique.setdefault(spelling(candidate["romaji"]), candidate)
    if len(unique) < 2:
        return None
    winners, measurements = [], []
    for logp, blank in views:
        ranked = []
        for key, candidate in unique.items():
            trial = [dict(w) for w in words]
            trial[index].update(text=candidate["hiragana"], romaji=candidate["romaji"])
            value = score(logp, blank, trial, vocabulary)
            if value is not None:
                ranked.append((value, key, trial))
        ranked.sort(key=lambda row: row[0], reverse=True)
        old = next((r[0] for r in ranked if r[1] == spelling(baseline["romaji"])), None)
        if (
            len(ranked) < 2
            or old is None
            or (not include_baseline and ranked[0][1] == spelling(baseline["romaji"]))
        ):
            return None
        best, key, trial = ranked[0]
        evidence = phonetic_units(logp, blank, trial, vocabulary)
        neighbors = [u for n, u in enumerate(evidence) if n != index]
        context = sum(u["mean_probability"] >= 0.30 for u in neighbors) / max(
            1, len(neighbors)
        )
        winners.append(key)
        measurements.append(
            {
                "gain": best - old,
                "margin": best - ranked[1][0],
                "probability": evidence[index]["mean_probability"],
                "context": context,
            }
        )
    if len(set(winners)) != 1:
        return None
    return {
        **unique[winners[0]],
        "views": measurements,
        "acoustic_pass": decision(measurements),
        "baseline": winners[0] == spelling(baseline["romaji"]),
    }


def verify(
    words,
    index,
    candidate,
    alternatives,
    logp,
    blank,
    vocabulary,
    transcript_supported=False,
):
    """A separately trained singing recognizer vetoes confident contradictions.

    A small likelihood difference (within two log units) is treated as uncertain,
    not as a confirming vote. MMS must still pass every strong acoustic gate.
    """
    from singing_phonemes import kana_phones, phrase_score

    old = phrase_score(logp, blank, words, vocabulary)
    trial = [dict(w) for w in words]
    trial[index].update(text=candidate["hiragana"], romaji=candidate["romaji"])
    new = phrase_score(logp, blank, trial, vocabulary)
    other_scores = [old] if old is not None else []
    for other in alternatives:
        if spelling(other["romaji"]) == spelling(candidate["romaji"]):
            continue
        trial[index].update(text=other["hiragana"], romaji=other["romaji"])
        value = phrase_score(logp, blank, trial, vocabulary)
        if value is not None:
            other_scores.append(value)
    before = kana_phones(words[index]["text"], words[index]["romaji"])
    after = kana_phones(candidate["hiragana"], candidate["romaji"])
    if old is None or new is None or not before or not after or not other_scores:
        return None
    ratio = len(after) / len(before)
    evidence = {
        "gain_milli": round((new - old) * 1000),
        "margin_milli": round((new - max(other_scores)) * 1000),
        "phone_ratio_ppm": round(ratio * 1_000_000),
        "transcript_supported": transcript_supported,
    }
    accepted = (
        evidence["gain_milli"] >= -2000
        and evidence["margin_milli"] >= -2000
        and (ratio >= 0.75 or transcript_supported)
        and ratio <= 4
    )
    return {**evidence, "supported": accepted}
