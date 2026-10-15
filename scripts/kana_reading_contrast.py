"""Research-only kana minimal pairs; nominations never authorize saved repairs.

Changing a reading changes only one original source group. Compare the complete
cue as well as its owned decoder tokens: scoring only the latter can reward a
reading that absorbs the following word. Both remain conditioned observations,
not free recognition, calibrated confidence, or word boundaries.
"""

import math
import re

KANA = re.compile(r"[ぁ-ゖー]+")
CONDITIONS = ("real", "silence", "wrong_verse")
EXPLORATORY_MARGIN = math.log(10)


def substitute_kana(raw_line, groups, index, kana):
    """Return exact kana ownership without changing any original Japanese span."""
    if type(index) is not int or not 0 <= index < len(groups):
        raise ValueError("Invalid source group index.")
    if not isinstance(kana, str) or not KANA.fullmatch(kana):
        raise ValueError("Reading must be nonempty hiragana, without spaces.")
    raw = raw_line.encode()
    pieces, targets, last, offset = [], [], 0, 0
    for i, group in enumerate(groups):
        first, end = group["raw_span"]
        if (
            type(first) is not int
            or type(end) is not int
            or not last <= first < end <= len(raw)
            or raw[first:end].decode() != group["expected_text"]
            or any(c.isalnum() for c in raw[last:first].decode())
        ):
            raise ValueError("Missing, overlapping or changed original source group.")
        selected = group["kana"]
        if not isinstance(selected, str) or not KANA.fullmatch(selected):
            raise ValueError("Unsupported source pronunciation; withhold the cue.")
        piece = kana if i == index else selected
        size = len(piece.encode())
        pieces.append(piece)
        targets.append({"raw_span": [offset, offset + size], "text": piece})
        last, offset = end, offset + size
    if any(c.isalnum() for c in raw[last:].decode()):
        raise ValueError("Unowned source text after the final group.")
    return {
        "text": "".join(pieces),
        "targets": targets,
        "source_group_index": index,
        "source_raw_span": list(groups[index]["raw_span"]),
        "source_expected_text": groups[index]["expected_text"],
    }


def observation_scores(observation):
    """Whole-cue and exact-word full-vocabulary sums, or a BPE abstention."""
    tokens = observation["token_log_probabilities"]
    owners = observation["source_token_indices"]
    if (
        not tokens
        or any(
            not isinstance(x, (int, float))
            or isinstance(x, bool)
            or not math.isfinite(x)
            or x > 0
            for x in tokens
        )
        or len(owners) != 1
    ):
        raise ValueError("Invalid full-vocabulary reading observation.")
    indices = owners[0]
    if indices is None:
        return None
    if (
        not indices
        or any(type(i) is not int or not 0 <= i < len(tokens) for i in indices)
        or indices != sorted(set(indices))
    ):
        raise ValueError("Invalid complete token ownership.")
    return {
        "word": math.fsum(tokens[i] for i in indices),
        "cue": math.fsum(tokens),
    }


def nominate_reading(candidates, *, margin=EXPLORATORY_MARGIN):
    """Require one winner in all four contrasts; return a hypothesis, never an edit.

    Candidates have unique id/kana/current plus observations for real, silence
    and wrong_verse. The caller authenticates original source and audio identity.
    A missing competitor/control withholds the entire comparison. The exploratory
    margin is uncalibrated; this function supplies no probability or timestamps.
    """
    if (
        not candidates
        or not isinstance(margin, (int, float))
        or isinstance(margin, bool)
        or not math.isfinite(margin)
        or margin <= 0
        or len({c["id"] for c in candidates}) != len(candidates)
        or len({c["kana"] for c in candidates}) != len(candidates)
        or any(type(c["current"]) is not bool for c in candidates)
        or sum(c["current"] for c in candidates) != 1
    ):
        raise ValueError("Invalid complete reading competition.")
    if len(candidates) < 2:
        return {"reason": "no_alternative", "candidate_id": None}
    contrasts = {}
    for candidate in candidates:
        observations = candidate["observations"]
        if set(observations) != set(CONDITIONS):
            return {"reason": "missing_condition", "candidate_id": None}
        real = observations["real"]
        if any(
            len(other["token_log_probabilities"])
            != len(real["token_log_probabilities"])
            or other["source_token_indices"] != real["source_token_indices"]
            for other in observations.values()
        ):
            raise ValueError("Audio counterfactual changed decoder token ownership.")
        scores = {k: observation_scores(observations[k]) for k in CONDITIONS}
        if any(s is None for s in scores.values()):
            return {"reason": "unowned_competitor", "candidate_id": None}
        contrasts[candidate["id"]] = {
            (unit, condition): scores["real"][unit] - scores[condition][unit]
            for unit in ("word", "cue")
            for condition in ("silence", "wrong_verse")
        }
    keys = list(next(iter(contrasts.values())))
    winners = {
        max(contrasts, key=lambda candidate: contrasts[candidate][key]) for key in keys
    }
    if len(winners) != 1:
        return {"reason": "word_cue_or_control_disagreement", "candidate_id": None}
    winner = winners.pop()
    margins = {
        f"{unit}_{condition}": contrasts[winner][unit, condition]
        - max(s[unit, condition] for c, s in contrasts.items() if c != winner)
        for unit, condition in keys
    }
    if min(contrasts[winner].values()) <= 0 or min(margins.values()) < margin:
        return {"reason": "weak_contrast", "candidate_id": None, "margins": margins}
    current = next(c for c in candidates if c["id"] == winner)["current"]
    return {
        "reason": "current_reading" if current else "conditional_hypothesis",
        "candidate_id": winner,
        "margins": margins,
    }
