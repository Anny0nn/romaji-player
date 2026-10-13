"""Independent Japanese singing CTC scoring, including mixed mora/phone tokens.

The released recognizer can emit either a mora (such as `kya`) or its phones
(`ky`, `a`). Sum all legal CTC paths rather than dropping one token family.
"""

import math
import re


def token_phones(token):
    if token in ("N", "cl"):
        return [token]
    if not re.fullmatch(r"[a-z]+", token):
        return []
    return re.findall(r"[bcdfghjkmnprstvwxyz]+|[aeiou]", token)


def kana_phones(text, romaji=""):
    from g2p.converters.japanese import _KANA_TO_ROMAJI

    if text == "は" and romaji == "wa":
        text = "わ"
    if text == "へ" and romaji == "e":
        text = "え"
    result, i = [], 0
    while i < len(text):
        if text[i] == " ":
            i += 1
            continue
        if text[i] == "ー":
            if not result or result[-1] not in "aeiou":
                return None
            result.append(result[-1])
            i += 1
            continue
        if text[i] == "ん":
            result.append("N")
            i += 1
            continue
        length = 2 if text[i : i + 2] in _KANA_TO_ROMAJI else 1
        value = _KANA_TO_ROMAJI.get(text[i : i + length])
        if value is None:
            return None
        result.extend(token_phones(value))
        i += length
    return result or None


def lattice_score(logp, blank, phones, vocabulary):
    """Exact forward sum over expanded tokens, with ordinary CTC repeat rules."""
    import numpy as np

    if not phones or len(phones) > 1024 or len(logp) > 1600:
        return None
    if logp.ndim != 2 or not np.isfinite(logp).all() or not 0 <= blank < logp.shape[1]:
        raise ValueError("Invalid singing phoneme matrix.")
    boundary_count = len(phones) + 1
    states, ending = [], [[] for _ in range(boundary_count)]
    for start in range(len(phones)):
        for token, label in vocabulary.items():
            expansion = token_phones(token)
            end = start + len(expansion)
            if label != blank and expansion and phones[start:end] == expansion:
                if not 0 <= label < logp.shape[1]:
                    raise ValueError("Invalid singing phoneme vocabulary.")
                index = boundary_count + len(states)
                states.append((start, end, label, index))
                ending[end].append((label, index))
    if not ending[-1]:
        return None
    parents = [[p, *(index for _, index in ending[p])] for p in range(boundary_count)]
    for start, _, label, index in states:
        parents.append(
            [index, start, *(i for other, i in ending[start] if other != label)]
        )
    width = max(map(len, parents))
    missing = len(parents)
    indices = np.array([p + [missing] * (width - len(p)) for p in parents])
    emissions = np.array([blank] * boundary_count + [s[2] for s in states])
    previous = np.full(missing + 1, -np.inf, dtype=np.float64)
    previous[0] = 0
    for row in logp:
        previous[:missing] = (
            np.logaddexp.reduce(previous[indices], axis=1) + row[emissions]
        )
    value = float(
        np.logaddexp.reduce(previous[[len(phones), *(i for _, i in ending[-1])]])
    )
    return value if math.isfinite(value) else None


def phrase_score(logp, blank, words, vocabulary):
    phones = []
    for word in words:
        value = kana_phones(word["text"], word.get("romaji", ""))
        if value is None:
            return None
        phones.extend(value)
    return lattice_score(logp, blank, phones, vocabulary)
