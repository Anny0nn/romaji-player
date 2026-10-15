"""Pinned normalized English lyrics with human word clocks; private development only."""

import csv
import io
import math


def word_lines(words_text, labels_text):
    """The last word carries a line-end time, not a boolean or word duration."""
    words = words_text.splitlines()
    reader = csv.DictReader(io.StringIO(labels_text))
    if reader.fieldnames != ["word_start", "word_end", "line_end"]:
        raise ValueError("Unknown Jamendo word-annotation schema.")
    rows = list(reader)
    if (
        not words
        or len(words) != len(rows)
        or any(not w or w.strip() != w for w in words)
    ):
        raise ValueError("Word text and annotations do not have exact ownership.")
    result, group, previous = [], [], -1
    for word, row in zip(words, rows, strict=True):
        first, last, line_end = (
            float(row[k]) for k in ("word_start", "word_end", "line_end")
        )
        if (
            not all(math.isfinite(x) for x in (first, last))
            or not previous <= first < last
        ):
            raise ValueError("Invalid or unordered human word clock.")
        previous = first
        group.append({"text": word, "start_ms": first * 1000, "end_ms": last * 1000})
        if math.isfinite(line_end):
            if line_end < last:
                raise ValueError("Line ends before its last human word.")
            raw, targets, references = " ".join(u["text"] for u in group), [], []
            offset = 0
            for index, unit in enumerate(group):
                size = len(unit["text"].encode())
                span = [offset, offset + size]
                targets.append({"raw_span": span, "text": unit["text"]})
                references.append({**unit, "raw_span": span, "unit": index})
                offset += size + 1
            result.append(
                {
                    "raw_line": raw,
                    "targets": targets,
                    "reference": references,
                    "line_end_ms": line_end * 1000,
                }
            )
            group = []
        elif row["line_end"].lower() != "nan":
            raise ValueError("Unknown missing line-end marker.")
    if group:
        raise ValueError("Unterminated human annotation line.")
    return result
