"""Original lyric spans own source words; an English ASR tokenizer does not.

Only recognized output tokens need CTC token ownership. Encoding an entire mixed
Japanese/English source line with an English vocabulary unnecessarily discards its
supported English groups. Keep unsupported groups in place as lexical barriers.
"""

import re

WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*")


def source_context(crops):
    """Return source lexical keys and occurrence owners, without encoding source text."""
    seen, words, owners, invalid, reasons = set(), [], [], set(), {}
    for crop in crops:
        occurrence = crop["occurrence"]
        if type(occurrence) is not int or occurrence < 0 or occurrence in seen:
            raise ValueError("Invalid or duplicate source occurrence.")
        seen.add(occurrence)
        text = crop["raw_line"]
        raw = text.encode()
        lexemes = [
            (
                len(text[: match.start()].encode()),
                len(text[: match.end()].encode()),
                re.sub(r"[^a-z0-9]", "", match.group().lower()),
            )
            for match in WORD.finditer(text)
            if any(c.isalpha() for c in match.group())
        ]
        previous, missing, local = 0, False, []
        for index, target in enumerate(crop["targets"]):
            first, last = target["raw_span"]
            if (
                type(first) is not int
                or type(last) is not int
                or not previous <= first < last <= len(raw)
            ):
                raise ValueError("Invalid original UTF-8 source group.")
            surface = raw[first:last].decode()
            if target.get("expected_text", surface) != surface:
                raise ValueError("Changed original source spelling.")
            missing |= any(c.isalnum() for c in raw[previous:first].decode())
            hits = [(a, b, key) for a, b, key in lexemes if a < last and first < b]
            key, reason = None, "unsupported_source_group"
            if len(hits) == 1:
                a, b, value = hits[0]
                if first <= a < b <= last and not any(
                    c.isalnum() for c in (raw[first:a] + raw[b:last]).decode()
                ):
                    key, reason = value, None
            local.append((index, {"key": key, "raw_span": [first, last]}, reason))
            previous = last
        missing |= any(c.isalnum() for c in raw[previous:].decode())
        for index, word, reason in local:
            position = len(words)
            if missing:
                word["key"], reason = None, "unowned_source_text"
            if reason:
                invalid.add(position)
                reasons[position] = reason
            words.append(word)
            owners.append((occurrence, index))
    return {"words": words, "invalid": invalid, "reasons": reasons}, owners
