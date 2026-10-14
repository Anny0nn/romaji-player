"""Research-only dictionary pronunciation shadows; written lyrics stay intact."""

from difflib import SequenceMatcher

from audio_first_models import kana_sequence_phones, source_word_phones
from audio_first_reconciliation import kana_candidates


def pronunciation_boundaries(written, spoken):
    """Map complete written mora boundaries to dictionary phone boundaries.

    Equal runs and edit endpoints are exact; interiors of substitutions are not.
    This describes a dictionary mapping, never timing or an acoustic observation.
    """
    old, new = kana_sequence_phones(written), kana_sequence_phones(spoken)
    if any(p.startswith("unsupported:") for p in [*old, *new]):
        return []
    mapping = {}
    for kind, a, b, c, d in SequenceMatcher(
        None, old, new, autojunk=False
    ).get_opcodes():
        pairs = [(a, c), (b, d)]
        if kind == "equal":
            pairs.extend((a + i, c + i) for i in range(b - a + 1))
        for first, last in pairs:
            mapping.setdefault(first, set()).add(last)
    result = []
    for index in range(len(written) + 1):
        # Do not split digraphs such as きゃ. Prefix+suffix must reconstruct phones.
        prefix = kana_sequence_phones(written[:index])
        suffix = kana_sequence_phones(written[index:])
        if prefix + suffix != old:
            continue
        candidates = mapping.get(len(prefix), set())
        if len(candidates) == 1:
            result.append([index, next(iter(candidates))])
    return result


def spelling_candidates(phones, inventory, word, limit=8):
    """Retain a dictionary-mapped unchanged prefix/suffix of an observed reading.

    For example, observed y-u-k-o-o may retain written こう from いこう/いこー.
    No global ou→oo rule is introduced. Every retained piece matches the supplied
    dictionary pronunciation exactly; the changed piece comes from audio phones.
    These are proposals only and still require independent acoustic admission.
    """
    result = set(kana_candidates(phones, inventory, limit))
    spoken = word.get("pronunciation_phones")
    if not spoken:
        return sorted(result)
    written = word["hiragana"]
    for character, boundary in word["pronunciation_boundaries"]:
        if character in (0, len(written)) or boundary in (0, len(spoken)):
            continue
        tail = spoken[boundary:]
        if len(phones) > len(tail) and phones[-len(tail) :] == tail:
            for prefix in kana_candidates(phones[: -len(tail)], inventory, limit):
                result.add(prefix + written[character:])
        head = spoken[:boundary]
        if len(phones) > len(head) and phones[: len(head)] == head:
            for suffix in kana_candidates(phones[len(head) :], inventory, limit):
                result.add(written[:character] + suffix)
    return sorted(result) if len(result) <= limit else []


def attach_shadow(words, record):
    """Reject changed conversion/mapping rather than reattach by substring."""
    if len(words) != len(record["words"]):
        raise ValueError("Dictionary shadow has different displayed words.")
    result = []
    for word, shadow in zip(words, record["words"], strict=True):
        if any(
            word[k] != shadow[k]
            for k in ("raw_span", "expected_text", "hiragana", "romaji")
        ):
            raise ValueError("Dictionary shadow belongs to another source conversion.")
        spoken = shadow["pronunciation_kana"]
        result.append(
            {
                **word,
                **shadow,
                "pronunciation_phones": kana_sequence_phones(spoken)
                if spoken
                else source_word_phones(word),
                "pronunciation_boundaries": pronunciation_boundaries(
                    word["hiragana"], spoken
                )
                if spoken
                else [],
            }
        )
    return result
