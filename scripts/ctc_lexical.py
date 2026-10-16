"""Exact source-owned word correspondence for closed, source-blind CTC evidence.

Matching is separate from token confidence, acoustic localization and physical
word clocks. Unsupported source words remain barriers; a completely supported
English source must still be matched.
"""


def _occurrences(sequence, pattern):
    return [
        i
        for i in range(len(sequence) - len(pattern) + 1)
        if sequence[i : i + len(pattern)] == pattern
    ]


def unique_word_matches(source, observed):
    """Return uniquely owned, complete multiword matches without splitting a token.

    The tokenizer supplies canonical keys, invalid source indices, and observed
    word validity. Returned values are the original observed records, retaining
    their token ownership; this function creates no scores or timestamps.
    """
    words = source["words"]
    invalid = set(source["invalid"])
    if any(type(i) is not int or not 0 <= i < len(words) for i in invalid):
        raise ValueError("Invalid original source ownership index.")
    left = [None if i in invalid else w["key"] for i, w in enumerate(words)]
    right = [w["key"] for w in observed["words"]]
    if any(
        key is not None and (not isinstance(key, str) or not key)
        for key in left + right
    ):
        raise ValueError("Invalid canonical lexical key.")
    mappings = [set() for _ in left]
    # Always match, including invalid == set(). Testing for unsupported words
    # here used to invert the eligibility of wholly valid English contexts.
    for first in range(len(left)):
        if left[first] is None:
            continue
        for last in range(first + 2, len(left) + 1):
            block = left[first:last]
            if None in block:
                break
            if len(_occurrences(left, block)) != 1:
                continue
            positions = _occurrences(right, block)
            if len(positions) != 1:
                continue
            position = positions[0]
            if not all(
                observed["words"][position + i]["valid"] is True
                for i in range(len(block))
            ):
                continue
            for i in range(len(block)):
                mappings[first + i].add(position + i)
    return {
        i: observed["words"][next(iter(positions))]
        for i, positions in enumerate(mappings)
        if len(positions) == 1
    }
