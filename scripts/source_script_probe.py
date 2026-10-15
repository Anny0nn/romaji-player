"""Native-script candidates retain original word ownership and spelling.

Original kanji is an acoustic candidate, not a second dictionary's reading vote.
No spelling or source text is rewritten, and the selected kana remains a separate
input so the same native model can be compared on the same recording.
"""


def source_targets(raw_line, targets, mode):
    if mode not in ("source", "selected-reading"):
        raise ValueError("Unknown source representation.")
    data, previous, result = raw_line.encode(), 0, []
    for target in targets:
        first, last = target["raw_span"]
        if (
            type(first) is not int
            or type(last) is not int
            or not previous <= first < last <= len(data)
        ):
            raise ValueError("Changed original UTF-8 source ownership.")
        try:
            original = data[first:last].decode()
        except UnicodeDecodeError as error:
            raise ValueError("Source group splits UTF-8.") from error
        text = original if mode == "source" else target["text"]
        if not text or any(c.isspace() for c in text):
            return None
        result.append({**target, "text": text, "expected_text": original})
        previous = last
    return result
