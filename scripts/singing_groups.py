"""Frozen, nonlexical PJS phone grouping for contextual timing evaluation.

Each reference unit contains at most two canonical morae. Unknown/devoiced
vowels and ambiguous glottal/geminate `cl` reject the whole voiced phrase.
These units are phone groups, never dictionary words or recognition labels.
"""

from singing_reference import SILENCE


def groups(phones, inventory):
    """Map complete CV/N sequences without dropping or replacing any phone."""
    morae, index = [], 0
    while index < len(phones):
        key = (phones[index]["phone"],)
        if key not in inventory and index + 1 < len(phones):
            key += (phones[index + 1]["phone"],)
        kana = inventory.get(key)
        if kana is None:
            return None
        piece = phones[index : index + len(key)]
        morae.append((kana, piece))
        index += len(key)
    result, offset = [], 0
    for index in range(0, len(morae), 2):
        pair = morae[index : index + 2]
        text = "".join(kana for kana, _ in pair)
        source = [phone for _, sequence in pair for phone in sequence]
        length = len(text.encode())
        result.append(
            {
                "unit": len(result),
                "phone": " ".join(p["phone"] for p in source),
                "text": text,
                "raw_span": [offset, offset + length],
                "start_ms": source[0]["start_ms"],
                "end_ms": source[-1]["end_ms"],
                "uncertainty_ms": None,
            }
        )
        offset += length
    return result


def phrases(labels):
    current = []
    for label in labels:
        if label["phone"] in SILENCE:
            if current:
                yield current
                current = []
        else:
            current.append(label)
    if current:
        yield current
