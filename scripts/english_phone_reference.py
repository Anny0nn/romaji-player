"""Strict NUS CMU-to-IPA crosswalk and human phone/word-marker import.

Canonical en-US symbols follow cmusphinx/cmudict-tools accents/en-US.csv.
NUS supplies no stress distinction for AH and no orthographic word labels.
ER's r-coloured vowel is absent from this checkpoint; it stays unsupported.
"""

import math

IPA = dict(
    zip(
        [
            "aa",
            "ae",
            "ah",
            "ao",
            "aw",
            "ay",
            "b",
            "ch",
            "d",
            "dh",
            "eh",
            "ey",
            "f",
            "g",
            "hh",
            "ih",
            "iy",
            "jh",
            "k",
            "l",
            "m",
            "n",
            "ng",
            "ow",
            "oy",
            "p",
            "r",
            "s",
            "sh",
            "t",
            "th",
            "uh",
            "uw",
            "v",
            "w",
            "y",
            "z",
            "zh",
        ],
        [
            "ɑ",
            "æ",
            "ʌ",
            "ɔ",
            "aʊ",
            "aɪ",
            "b",
            "tʃ",
            "d",
            "ð",
            "ɛ",
            "eɪ",
            "f",
            "ɡ",
            "h",
            "ɪ",
            "i",
            "dʒ",
            "k",
            "l",
            "m",
            "n",
            "ŋ",
            "oʊ",
            "ɔɪ",
            "p",
            "ɹ",
            "s",
            "ʃ",
            "t",
            "θ",
            "ʊ",
            "u",
            "v",
            "w",
            "j",
            "z",
            "ʒ",
        ],
        strict=True,
    )
)


def labels(text, duration_ms):
    result, previous, word = [], 0, 0
    for row in text.splitlines():
        if not row.strip():
            continue
        fields = row.split()
        if len(fields) != 3:
            raise ValueError("Expected human sung-phone timestamps and symbol.")
        first, last = float(fields[0]) * 1000, float(fields[1]) * 1000
        phone = fields[2]
        if (
            not all(math.isfinite(v) for v in (first, last))
            or not previous <= first <= last <= duration_ms + 1
        ):
            raise ValueError("Invalid human phone clock.")
        if phone == "sp":
            if first != last:
                raise ValueError("NUS sp must be a zero-duration word marker.")
            word += 1
        elif first == last:
            raise ValueError("An audible phone needs a positive interval.")
        else:
            result.append(
                {
                    "unit": len(result),
                    "phone": phone,
                    "word": word,
                    "start_ms": first,
                    "end_ms": last,
                    "uncertainty_ms": None,
                }
            )
        previous = last
    if not result:
        raise ValueError("Empty human annotation.")
    return result


def phrase_groups(reference):
    """Breaths delimit phrases; sil/sp never become target phones."""
    current = []
    for ref in reference:
        if ref["phone"] == "sil":
            if current:
                yield current
                current = []
        else:
            current.append(ref)
    if current:
        yield current


def tokens(reference, vocabulary):
    # Reject the complete phrase rather than collapsing ER or silently erasing it.
    values = [IPA.get(r["phone"]) for r in reference]
    if not values or any(v not in vocabulary for v in values):
        return None
    return [vocabulary[v] for v in values]
