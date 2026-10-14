"""Bounded CMU→Japanese acoustic hypotheses; no lyric rewriting or learned votes."""

VOWELS = {
    "aa": ["a"],
    "ae": ["a"],
    "ah": ["a"],
    "ao": ["o"],
    "ax": ["a"],
    "aw": ["a", "u"],
    "ay": ["a", "i"],
    "eh": ["e"],
    "er": ["a", "a"],
    "ey": ["e", "i"],
    "ih": ["i"],
    "iy": ["i", "i"],
    "ow": ["o", "u"],
    "oy": ["o", "i"],
    "uh": ["u"],
    "uw": ["u", "u"],
}
CONSONANTS = {
    "b": "b",
    "ch": "ch",
    "d": "d",
    "dh": "d",
    "f": "f",
    "g": "g",
    "hh": "h",
    "jh": "j",
    "k": "k",
    "l": "r",
    "m": "m",
    "n": "n",
    "p": "p",
    "r": "r",
    "s": "s",
    "sh": "sh",
    "t": "t",
    "th": "s",
    "v": "b",
    "w": "w",
    "y": "y",
    "z": "z",
    "zh": "j",
}


def japanese_hypothesis(phones, mode):
    """Two fixed phonetic approximations, requiring independent acoustic checks.

    `direct` keeps consonant clusters; `loan` inserts conventional Japanese coda
    vowels and drops post-vocalic r into vowel length. Neither is a true reading.
    """
    if mode not in ("direct", "loan"):
        raise ValueError("Unknown pronunciation hypothesis.")
    result = []
    for index, phone in enumerate(phones):
        following = phones[index + 1] if index + 1 < len(phones) else None
        if phone in VOWELS:
            result.extend(VOWELS[phone])
        elif phone == "ng" or phone == "n" and following not in VOWELS:
            result.append("N")
        elif phone in CONSONANTS:
            consonant = CONSONANTS[phone]
            if (
                mode == "loan"
                and phone == "r"
                and result
                and result[-1] in "aiueo"
                and following not in VOWELS
            ):
                result.append(result[-1])
                continue
            result.append(consonant)
            if mode == "loan" and following not in VOWELS and following != "y":
                result.append("o" if consonant in ("t", "d") else "u")
        else:
            return None
    # Japanese palatalized onsets are atomic phones in the singing inventory.
    merged, index = [], 0
    while index < len(result):
        if (
            index + 2 < len(result)
            and result[index + 1] == "y"
            and result[index + 2] in "aiueo"
            and result[index] in ("k", "g", "n", "h", "b", "p", "m", "r")
        ):
            merged.append(result[index] + "y")
            index += 2
        else:
            merged.append(result[index])
            index += 1
    return merged or None
