"""Source-blind CTC decoding and pronunciation metrics; no timestamps are invented."""

import math
from collections import defaultdict


def logadd(a, b):
    if a == -math.inf:
        return b
    if b == -math.inf:
        return a
    high, low = max(a, b), min(a, b)
    return high + math.log1p(math.exp(low - high))


def validate(logp, blank):
    if not len(logp) or not len(logp[0]) or not 0 <= blank < len(logp[0]):
        raise ValueError("Invalid CTC dimensions or blank.")
    width = len(logp[0])
    for row in logp:
        if len(row) != width or any(math.isnan(v) or v > 0 for v in row):
            raise ValueError("CTC scores must be nonpositive log probabilities.")
        if all(v == -math.inf for v in row):
            raise ValueError("CTC frame has no possible label.")


def greedy(logp, blank):
    validate(logp, blank)
    tokens, frames, previous, score = [], [], None, 0.0
    for index, row in enumerate(logp):
        label = max(range(len(row)), key=lambda k: (row[k], -k))
        score += float(row[label])
        if label != blank:
            if label == previous:
                frames[-1][1] = index
            else:
                tokens.append(label)
                frames.append([index, index])
        previous = label
    return {"token_ids": tokens, "emission_frames": frames, "path_score": score}


def beam(logp, blank, *, width=32, nbest=8, token_prune=16):
    """CTC prefix sum; kept token sequences are pruned, never constrained by lyrics."""
    validate(logp, blank)
    if not 1 <= nbest <= width <= 256 or token_prune < 0:
        raise ValueError("Invalid beam limits.")
    prefixes = {(): (0.0, -math.inf)}
    for row in logp:
        order = sorted(range(len(row)), key=lambda k: (-row[k], k))
        labels = set(order[:token_prune] if token_prune else order)
        labels.discard(blank)
        following = defaultdict(lambda: [-math.inf, -math.inf])
        for prefix, (pb, pn) in prefixes.items():
            total = logadd(pb, pn)
            same = following[prefix]
            same[0] = logadd(same[0], total + float(row[blank]))
            # Preserve the CTC self-loop even when token pruning excludes it.
            if prefix:
                label = prefix[-1]
                same[1] = logadd(same[1], pn + float(row[label]))
            for label in labels:
                parent = pb if prefix and prefix[-1] == label else total
                value = parent + float(row[label])
                if value != -math.inf:
                    child = following[(*prefix, label)]
                    child[1] = logadd(child[1], value)
        ranked = sorted(
            ((p, v) for p, v in following.items() if logadd(*v) != -math.inf),
            key=lambda item: (-logadd(*item[1]), item[0]),
        )[:width]
        prefixes = dict(ranked)
    return [
        {"token_ids": list(prefix), "approximate_sequence_score": logadd(*scores)}
        for prefix, scores in list(prefixes.items())[:nbest]
    ]


def phone_hypotheses(hypotheses, expand):
    """Merge equivalent tokenizations; finite N-best sums are still approximate."""
    unique = {}
    for hypothesis in hypotheses:
        phones = tuple(expand(hypothesis["token_ids"]))
        score = hypothesis["approximate_sequence_score"]
        if phones in unique:
            old = unique[phones]
            old["approximate_sequence_score"] = logadd(
                old["approximate_sequence_score"], score
            )
            old["tokenizations"] += 1
        else:
            unique[phones] = {
                **hypothesis,
                "phones": list(phones),
                "tokenizations": 1,
            }
    return sorted(
        unique.values(), key=lambda h: (-h["approximate_sequence_score"], h["phones"])
    )


def edit_counts(reference, predicted):
    """Levenshtein counts; substitutions win ties, then deletions, then insertions."""
    row = [(j, 0, 0, j) for j in range(len(predicted) + 1)]
    for i, expected in enumerate(reference, 1):
        following = [(i, 0, i, 0)]
        for j, observed in enumerate(predicted, 1):
            distance, subs, dels, ins = row[j - 1]
            substitution = expected != observed
            choices = [
                (distance + substitution, subs + substitution, dels, ins),
                (row[j][0] + 1, row[j][1], row[j][2] + 1, row[j][3]),
                (
                    following[j - 1][0] + 1,
                    following[j - 1][1],
                    following[j - 1][2],
                    following[j - 1][3] + 1,
                ),
            ]
            following.append(min(choices, key=lambda c: c[0]))
        row = following
    distance, subs, dels, ins = row[-1]
    return {
        "reference_phones": len(reference),
        "errors": distance,
        "substitutions": subs,
        "deletions": dels,
        "insertions": ins,
        "exact": reference == predicted,
    }
