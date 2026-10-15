"""Whole-cue acoustic minimal pairs, without assigning BPE scores to a word.

The caller authenticates a single changed source reading and identical neighbors
and audio. These are conditional research nominations, not word probabilities,
verified corrections or boundaries. The original word-and-cue rule is separate.
"""

import math

from kana_reading_contrast import CONDITIONS, EXPLORATORY_MARGIN


def nominate_cue_reading(candidates, *, margin=EXPLORATORY_MARGIN):
    """Compare complete sequences against the same silence and wrong-verse controls."""
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
        raise ValueError("Invalid complete cue-reading competition.")
    if len(candidates) < 2:
        return {"reason": "no_alternative", "candidate_id": None}
    contrasts = {}
    for candidate in candidates:
        observations = candidate["observations"]
        if set(observations) != set(CONDITIONS):
            return {"reason": "missing_condition", "candidate_id": None}
        real = observations["real"]
        scores = {}
        for condition, observation in observations.items():
            tokens = observation["token_log_probabilities"]
            if (
                not tokens
                or any(
                    not isinstance(x, (int, float))
                    or isinstance(x, bool)
                    or not math.isfinite(x)
                    or x > 0
                    for x in tokens
                )
                or len(tokens) != len(real["token_log_probabilities"])
                or observation.get("source_token_indices")
                != real.get("source_token_indices")
            ):
                raise ValueError("Invalid or changed complete-cue token observation.")
            scores[condition] = math.fsum(tokens)
        contrasts[candidate["id"]] = {
            condition: scores["real"] - scores[condition]
            for condition in ("silence", "wrong_verse")
        }
    winners = {
        max(contrasts, key=lambda key: contrasts[key][condition])
        for condition in ("silence", "wrong_verse")
    }
    if len(winners) != 1:
        return {"reason": "cue_control_disagreement", "candidate_id": None}
    winner = winners.pop()
    margins = {
        condition: contrasts[winner][condition]
        - max(values[condition] for key, values in contrasts.items() if key != winner)
        for condition in ("silence", "wrong_verse")
    }
    if min(contrasts[winner].values()) <= 0 or min(margins.values()) < margin:
        return {"reason": "weak_cue_contrast", "candidate_id": None, "margins": margins}
    current = next(c["current"] for c in candidates if c["id"] == winner)
    return {
        "reason": "current_reading" if current else "whole_cue_hypothesis",
        "candidate_id": winner,
        "margins": margins,
    }
