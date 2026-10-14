"""Bounded Japanese-romaji hypotheses, never a language detector or reading vote."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "refinement"), str(ROOT / "tifa/vendor")]
from singing_phonemes import token_phones

MACRONS = str.maketrans({"ā": "aa", "ī": "ii", "ū": "uu", "ē": "ee", "ō": "oo"})


def acoustic_spelling(text):
    if not isinstance(text, str) or not re.fullmatch(
        r"[A-Za-zāīūēōĀĪŪĒŌ']{1,96}", text
    ):
        return None
    return text.lower().translate(MACRONS)


def japanese_romaji_phones(text):
    from g2p.converters.japanese import _KANA_TO_ROMAJI

    text = acoustic_spelling(text)
    if text is None:
        return None
    table = {
        roman: token_phones(roman)
        for kana, roman in _KANA_TO_ROMAJI.items()
        if kana not in ("ん", "っ")
    }
    keys = sorted(table, key=lambda value: (-len(value), value))
    result = []
    while text:
        if text.startswith("n'"):
            result.append("N")
            text = text[2:]
            continue
        if (
            len(text) > 1
            and text[0] == text[1]
            and text[0] in "bcdfghjkmprstvwxyz"
            or text.startswith("tch")
        ):
            result.append("cl")
            text = text[1:]
            continue
        key = next((key for key in keys if text.startswith(key)), None)
        if key:
            result.extend(table[key])
            text = text[len(key) :]
        elif text[0] == "n":
            result.append("N")
            text = text[1:]
        else:
            return None
    return result or None
