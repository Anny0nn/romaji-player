"""Free Qwen word confidence and exact lexical correspondence, without word clocks."""

import math
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

from source_contrast_policy import overlay_original_groups
from whisper_source_evidence import owned_token_indices

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "refinement"))
from english_timing import english_key


class DecoderTextMismatch(ValueError):
    """Parsed/repetition-cleaned text no longer owns the actual decoder bytes."""


def decoder_words(tokenizer, ids, logp, transcription):
    """Complete UTF-8 decoder pieces own scores; a BPE piece is never split."""
    if len(ids) != len(logp) or any(
        not isinstance(p, (int, float))
        or isinstance(p, bool)
        or not math.isfinite(p)
        or p > 0
        for p in logp
    ):
        raise ValueError("Invalid free-decoder token probabilities.")
    kwargs = {"skip_special_tokens": True, "clean_up_tokenization_spaces": False}
    raw = tokenizer.decode(ids, **kwargs)
    marker = "<asr_text>"
    after = raw.find(marker) + len(marker) if marker in raw else 0
    first = raw.find(transcription, after)
    if not transcription:
        return []
    if first < 0 or raw[first:].strip() != transcription:
        raise DecoderTextMismatch(
            "ASR transcript does not reconstruct its actual decoder bytes."
        )
    offset, pieces, owners, pending = 0, [], [], []
    data = raw.encode()
    for index, token in enumerate(ids):
        if token in tokenizer.all_special_ids:
            continue
        pending.append(index)
        prefix = tokenizer.decode(ids[: index + 1], **kwargs)
        last = len(prefix.encode())
        if raw.startswith(prefix) and last > offset:
            pieces.append(data[offset:last])
            owners.append(pending)
            offset, pending = last, []
    if offset != len(data) or pending:
        raise ValueError("Incomplete or unstable decoder byte ownership.")
    spans = []
    words = []
    for match in re.finditer(r"\S+", transcription):
        start = len(raw[: first + match.start()].encode())
        end = len(raw[: first + match.end()].encode())
        spans.append({"raw_span": [start, end]})
        words.append(match.group())
    mapped = owned_token_indices(raw, spans, pieces)
    result = []
    for word, indices in zip(words, mapped, strict=True):
        tokens = [i for piece in indices for i in owners[piece]] if indices else []
        mean = sum(logp[i] for i in tokens) / len(tokens) if tokens else None
        result.append(
            {
                "word": word,
                "decoder_token_indices": tokens,
                "mean_token_log_probability": mean,
                "probability": math.exp(mean) if mean is not None else None,
                "confidence_kind": "qwen-free-decoder-geometric-mean",
                "source_conditioned": False,
            }
        )
    return result


def recognition_words(tokenizer, row, forced_language):
    """Withhold a complete rewritten view; never transfer its old token scores."""
    if row["budget_exhausted"]:
        return [], "token_budget"
    detected = row["decoded"].get("language")
    if detected != "English" and not (forced_language == "en" and detected is None):
        return [], "other_language"
    try:
        return decoder_words(
            tokenizer,
            row["decoded_tokens"],
            row["token_log_probabilities"],
            row["decoded"]["transcription"],
        ), None
    except DecoderTextMismatch:
        return [], "unreconstructible_transcript"


def exact_matches(targets, words, *, probability_floor=0.7):
    """Unique multiword blocks; no provided text enters recognition or its score."""
    source = [english_key(t.get("expected_text", t["text"])) for t in targets]
    observed = [english_key(u["word"]) for u in words]
    left = [key or "source-unknown:" + str(i) for i, key in enumerate(source)]
    right = [key or "observed-unknown:" + str(i) for i, key in enumerate(observed)]
    result = [
        {
            "raw_span": t["raw_span"],
            "source_match": False,
            "probability": None,
            "confidence_kind": "qwen-free-decoder-geometric-mean",
            "source_conditioned": False,
            "matched_words": 0,
        }
        for t in targets
    ]
    for block in SequenceMatcher(
        None, left, right, autojunk=False
    ).get_matching_blocks():
        context = left[block.a : block.a + block.size]
        if block.size < 2 or any(
            key is None for key in source[block.a : block.a + block.size]
        ):
            continue
        if (
            sum(
                left[i : i + block.size] == context
                for i in range(len(left) - block.size + 1)
            )
            != 1
            or sum(
                right[i : i + block.size] == context
                for i in range(len(right) - block.size + 1)
            )
            != 1
        ):
            continue
        for offset in range(block.size):
            unit = words[block.b + offset]
            p = unit.get("probability")
            if (
                unit.get("confidence_kind") != "qwen-free-decoder-geometric-mean"
                or unit.get("source_conditioned") is not False
                or not isinstance(p, (int, float))
                or isinstance(p, bool)
                or not math.isfinite(p)
                or not probability_floor <= p <= 1
            ):
                continue
            result[block.a + offset].update(
                source_match=True, probability=p, matched_words=block.size
            )
    return result


def context_matches(crops, words):
    """Match the complete source context before returning occurrence-owned words.

    Repeated phrases in neighboring cues must be visible to the uniqueness check.
    UTF-8 spans are local to their original line and never identify an occurrence.
    """
    if len({c["occurrence"] for c in crops}) != len(crops):
        raise ValueError("Duplicate source occurrence in recognition context.")
    targets, owners = [], []
    for crop in crops:
        raw = crop["raw_line"].encode()
        previous = 0
        for index, target in enumerate(crop["targets"]):
            first, last = target["raw_span"]
            if not previous <= first < last <= len(raw):
                raise ValueError("Invalid original UTF-8 word span.")
            text = raw[first:last].decode()
            targets.append({**target, "expected_text": text})
            owners.append((crop["occurrence"], index))
            previous = last
    flags = exact_matches(targets, words)
    result = {c["occurrence"]: [] for c in crops}
    for (occurrence, _), flag in zip(owners, flags, strict=True):
        result[occurrence].append(flag)
    return result


def recover_recognized_pairs(baseline, clocks, views, length_ms, source_words):
    """Typed free-word recognition plus prevalidated pair clocks, without ASR times."""
    if len(views) != 2:
        raise ValueError("Expected two original recognition views.")
    return recover_recognized_views(baseline, clocks, views, length_ms, source_words)


def recover_recognized_views(baseline, clocks, views, length_ms, source_words):
    """Research ablation with two or three fixed, separately decoded waveforms.

    Two qualifying views must witness each word. A third vocal estimate can
    recover words masked in one earlier waveform; these correlated observations
    are not independent recognizers. The caller authenticates distinct audio
    views and full-context occurrence ownership before this word-level check.
    Physical clocks, adjacency and the old-interval overlay remain unchanged.
    """
    if (
        len(views) not in (2, 3)
        or any(len(v) != len(baseline) for v in views)
        or [u["raw_span"] for u in clocks] != [u["raw_span"] for u in baseline]
        or any(
            [u["raw_span"] for u in v] != [u["raw_span"] for u in baseline]
            for v in views
        )
    ):
        raise ValueError("Recognition changed original source group ownership.")
    eligible = set()
    for index, (clock, *witnesses) in enumerate(zip(clocks, *views, strict=True)):
        if (
            not all(
                isinstance(clock.get(k), (int, float))
                and not isinstance(clock[k], bool)
                and math.isfinite(clock[k])
                for k in ("start_ms", "end_ms")
            )
            or not 0 < clock["start_ms"] < clock["end_ms"] < length_ms
            or clock["end_ms"] - clock["start_ms"] < 80
        ):
            continue
        if (
            sum(
                u["confidence_kind"] == "qwen-free-decoder-geometric-mean"
                and u.get("source_conditioned") is False
                and u["source_match"]
                and u["matched_words"] >= 2
                and isinstance(u["probability"], (int, float))
                and not isinstance(u["probability"], bool)
                and math.isfinite(u["probability"])
                and 0.7 <= u["probability"] <= 1
                for u in witnesses
            )
            >= 2
        ):
            eligible.add(index)
    return overlay_original_groups(baseline, clocks, eligible, source_words)
