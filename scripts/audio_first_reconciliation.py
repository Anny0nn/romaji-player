"""Source attachment of blind phonetic hypotheses; proposals are not admission."""

from difflib import SequenceMatcher

from audio_first_ctc import edit_counts


def envelopes(raw_line, words, observed, readings):
    """Interior whole-word replacements with unique unchanged two-phone anchors.

    `readings` supplies the canonical phones for each source word. The acoustic
    decoder has already finished; this function never calls it or changes its output.
    Line edges and inserted/deleted lyric words remain diagnostic. Internal phone
    edits can combine into one complete nonempty source-word reading replacement.
    """
    if len(words) != len(readings) or not readings or any(not r for r in readings):
        return []
    raw = raw_line.encode()
    old, bounds = [], [0]
    previous = 0
    for word, phones in zip(words, readings, strict=True):
        a, b = word["raw_span"]
        if (
            type(a) is not int
            or type(b) is not int
            or not previous <= a < b <= len(raw)
            or raw[a:b].decode() != word["expected_text"]
        ):
            raise ValueError("Changed or overlapping original UTF-8 word envelope.")
        previous = b
        old.extend(phones)
        bounds.append(len(old))
    if any(p.startswith("unsupported:") for p in [*old, *observed]):
        return []
    matcher = SequenceMatcher(None, old, observed, autojunk=False)
    blocks = matcher.get_matching_blocks()
    if sum(block.size for block in blocks) / max(len(old), len(observed)) < 0.65:
        return []
    correspondence = {
        block.a + i: block.b + i for block in blocks for i in range(block.size)
    }
    result, seen = [], set()
    for kind, first, last, _, _ in matcher.get_opcodes():
        if kind not in ("replace", "delete"):
            continue
        a = next(
            (i for i in range(len(words)) if bounds[i] <= first < bounds[i + 1]), None
        )
        b = next(
            (i + 1 for i in range(len(words)) if bounds[i] < last <= bounds[i + 1]),
            None,
        )
        if a is None or b is None or a == 0 or b == len(words) or b - a > 4:
            continue
        left, right = bounds[a], bounds[b]
        if (
            left < 2
            or right + 1 >= len(old)
            or any(
                p not in correspondence for p in (left - 2, left - 1, right, right + 1)
            )
        ):
            continue
        start, end = correspondence[left - 1] + 1, correspondence[right]
        if start >= end or observed[start:end] == old[left:right]:
            continue
        context = old[left - 2 : left] + observed[start:end] + old[right : right + 2]
        if (
            sum(
                observed[i : i + len(context)] == context
                for i in range(len(observed) - len(context) + 1)
            )
            != 1
        ):
            continue
        if (a, b) in seen:
            continue
        seen.add((a, b))
        span = [words[a]["raw_span"][0], words[b - 1]["raw_span"][1]]
        # A grouped correction cannot swallow punctuation or another unowned span.
        if any(
            not raw[words[i]["raw_span"][1] : words[i + 1]["raw_span"][0]]
            .decode()
            .isspace()
            and words[i]["raw_span"][1] != words[i + 1]["raw_span"][0]
            for i in range(a, b - 1)
        ):
            continue
        result.append(
            {
                "raw_span": span,
                "expected_text": raw[span[0] : span[1]].decode(),
                "first_word": a,
                "last_word": b,
                "observed_phone_span": [start, end],
                "phones": observed[start:end],
            }
        )
    return result


def kana_candidates(phones, inventory, limit=8):
    """Bounded inverse G2P; preserve ambiguous spellings as separate candidates."""
    paths = {0: [""]}
    for first in range(len(phones)):
        if first not in paths:
            continue
        for sequence, spellings in inventory.items():
            last = first + len(sequence)
            if tuple(phones[first:last]) != sequence:
                continue
            target = paths.setdefault(last, [])
            for prefix in paths[first]:
                for spelling in spellings:
                    candidate = prefix + spelling
                    if candidate not in target:
                        target.append(candidate)
                        if len(target) > limit:
                            return []
    return sorted(paths.get(len(phones), []))


def preserve_spelling(candidates, original):
    """Choose a unique closest source spelling among phonetic equivalents only.

    The audio cannot distinguish じ/ぢ or お/を. Preserve existing kana where
    possible; equal minimum edit distances remain unresolved, never a vote.
    """
    if not candidates:
        return None
    distances = [
        (edit_counts(list(original), list(kana))["errors"], kana) for kana in candidates
    ]
    minimum = min(d for d, _ in distances)
    nearest = {kana for distance, kana in distances if distance == minimum}
    return next(iter(nearest)) if len(nearest) == 1 else None


def baseline_first(rows):
    """Fixed offline fallback priority; never choose using reference correctness.

    The caller supplies admitted candidates. Existing core admission wins; blind
    proposals fill only its abstentions. This is not app persistence or a vote.
    """
    groups = {}
    for row in rows:
        if row["method"] not in ("current-core", "romaji-beam"):
            continue
        key = (row["case"], row["condition"])
        methods = groups.setdefault(key, {})
        if row["method"] in methods:
            raise ValueError("Duplicate admitted reading for a method/case.")
        methods[row["method"]] = row
    return [
        {
            **methods.get("current-core", methods.get("romaji-beam")),
            "method": "core-then-blind",
        }
        for _, methods in sorted(groups.items())
    ]
