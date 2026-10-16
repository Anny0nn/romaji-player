"""Research-only CTC lexical evidence with TIFA/native-Qwen word clocks.

CTC emission statistics do not supply word boundaries. These functions return
measured TIFA intervals or abstain; they do not load models or change app state.
Agreement and coherent context are experimental qualification, not correctness.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

RawSpan = tuple[int, int]


@dataclass(frozen=True)
class SourceContext:
    """Caller-authenticated original text/groups and exact waveform crop.

    source_id binds the original text and group map; audio_id binds waveform
    bytes and sample bounds. Model output must never supply either identity.
    """

    source_id: str
    audio_id: str
    raw_text: str
    group_spans: tuple[RawSpan, ...]
    duration_ms: float


@dataclass(frozen=True)
class WordOwner:
    source_id: str
    audio_id: str
    group_index: int
    raw_span: RawSpan


@dataclass(frozen=True)
class CTCLexicalEvidence:
    """Actual CTC nonblank emission mean, never word or phone confidence."""

    owner: WordOwner
    union_margin_nats: float | None
    blank_margin_nats: float | None
    mean_ctc_emission_probability: float | None
    eligible: bool = True


@dataclass(frozen=True)
class WordObservation:
    """Caller-validated measured word interval from the named model family.

    TIFA inputs must be retained observations from its unchanged frontend, not
    rejected raw paths. This policy replaces the physical corroborator only;
    it does not relax TIFA's completeness, similarity or agreement filtering.
    """

    owner: WordOwner
    family: str
    start_ms: float
    end_ms: float


@dataclass(frozen=True)
class WordEvidence:
    lexical: CTCLexicalEvidence | None
    tifa: WordObservation | None
    native_qwen: WordObservation | None


@dataclass(frozen=True)
class SavedWord:
    owner: WordOwner
    start_ms: float | None = None
    end_ms: float | None = None
    protected: bool = False


def _finite(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate_context(context: SourceContext) -> None:
    """Require complete, ordered original UTF-8 groups, including unsupported ones."""
    if (
        not isinstance(context, SourceContext)
        or not isinstance(context.source_id, str)
        or not context.source_id
        or not isinstance(context.audio_id, str)
        or not context.audio_id
        or not isinstance(context.raw_text, str)
        or not context.group_spans
        or not _finite(context.duration_ms)
        or context.duration_ms <= 0
    ):
        raise ValueError("Invalid original source context.")
    raw = context.raw_text.encode()
    previous = 0
    for span in context.group_spans:
        if (
            not isinstance(span, tuple)
            or len(span) != 2
            or any(type(v) is not int for v in span)
            or not previous <= span[0] < span[1] <= len(raw)
        ):
            raise ValueError("Invalid original source group span.")
        try:
            gap = raw[previous : span[0]].decode()
            raw[span[0] : span[1]].decode()
        except UnicodeDecodeError as error:
            raise ValueError("Source group splits UTF-8.") from error
        if any(c.isalnum() for c in gap):
            raise ValueError("Original source words are missing from context.")
        previous = span[1]
    if any(c.isalnum() for c in raw[previous:].decode()):
        raise ValueError("Original source words are missing from context.")


def owner_for(context: SourceContext, index: int) -> WordOwner:
    validate_context(context)
    if type(index) is not int or not 0 <= index < len(context.group_spans):
        raise ValueError("Invalid original source group index.")
    return WordOwner(
        context.source_id, context.audio_id, index, context.group_spans[index]
    )


def _owner_matches(context, owner):
    return (
        isinstance(owner, WordOwner)
        and type(owner.group_index) is int
        and 0 <= owner.group_index < len(context.group_spans)
        and owner == owner_for(context, owner.group_index)
    )


def _interval_valid(observation, duration):
    return (
        _finite(observation.start_ms)
        and _finite(observation.end_ms)
        and 0 < observation.start_ms < observation.end_ms < duration
        and observation.end_ms - observation.start_ms >= 80
    )


def qualify_word(
    context: SourceContext, evidence: WordEvidence | None
) -> WordObservation | None:
    """Return the complete measured TIFA interval; no CTC clock is accepted."""
    validate_context(context)
    if not isinstance(evidence, WordEvidence):
        return None
    lexical, tifa, native = evidence.lexical, evidence.tifa, evidence.native_qwen
    if (
        not isinstance(lexical, CTCLexicalEvidence)
        or not isinstance(tifa, WordObservation)
        or not isinstance(native, WordObservation)
        or not _owner_matches(context, lexical.owner)
        or lexical.owner != tifa.owner
        or lexical.owner != native.owner
        or tifa.family != "tifa"
        or native.family != "native_qwen"
        or lexical.eligible is not True
        or not all(
            _finite(v)
            for v in (
                lexical.union_margin_nats,
                lexical.blank_margin_nats,
                lexical.mean_ctc_emission_probability,
            )
        )
        or lexical.union_margin_nats <= 0
        or lexical.blank_margin_nats <= 0
        or not 0.45 <= lexical.mean_ctc_emission_probability <= 1
        or not _interval_valid(tifa, context.duration_ms)
        or not _interval_valid(native, context.duration_ms)
        or abs(tifa.start_ms - native.start_ms) > 150
        or abs(tifa.end_ms - native.end_ms) > 150
    ):
        return None
    return tifa


def qualify_context(
    context: SourceContext, words: Sequence[WordEvidence | None]
) -> tuple[WordObservation | None, ...]:
    """Require >=2 AND >=half of ALL original groups; one-word cues abstain."""
    validate_context(context)
    count = len(context.group_spans)
    if len(words) != count:
        raise ValueError("Context changed the original source group denominator.")
    qualified = []
    for i, evidence in enumerate(words):
        if evidence is not None:
            if not isinstance(evidence, WordEvidence):
                raise ValueError("Invalid source word evidence.")
            for observation, expected_type in (
                (evidence.lexical, CTCLexicalEvidence),
                (evidence.tifa, WordObservation),
                (evidence.native_qwen, WordObservation),
            ):
                if observation is not None and (
                    not isinstance(observation, expected_type)
                    or observation.owner != owner_for(context, i)
                ):
                    raise ValueError(
                        "Context evidence changed original word ownership."
                    )
        qualified.append(qualify_word(context, evidence))
    if sum(word is not None for word in qualified) < max(2, math.ceil(count / 2)):
        return (None,) * count
    return tuple(qualified)


def overlay_candidates(
    context: SourceContext,
    baseline: Sequence[SavedWord],
    words: Sequence[WordEvidence | None],
) -> tuple[WordObservation | None, ...]:
    """Return ordered gap candidates; every existing/protected clock stays fixed.

    Match the existing research overlay: an eligible neighbor is required; a
    completely unanchored cue also requires >=70% eligible original groups.
    The return value contains candidates only and never modifies the baseline.
    """
    candidates = qualify_context(context, words)
    count = len(context.group_spans)
    if len(baseline) != count:
        raise ValueError("Baseline changed original source group denominator.")
    for i, word in enumerate(baseline):
        if (
            not isinstance(word, SavedWord)
            or word.owner != owner_for(context, i)
            or type(word.protected) is not bool
        ):
            raise ValueError("Baseline changed original source word ownership.")
        if (
            (word.protected and word.start_ms is None)
            or ((word.start_ms is None) != (word.end_ms is None))
            or (
                word.start_ms is not None
                and not (
                    _finite(word.start_ms)
                    and _finite(word.end_ms)
                    and 0 <= word.start_ms < word.end_ms <= context.duration_ms
                )
            )
        ):
            raise ValueError("Invalid existing source clock.")
    eligible = {i for i, word in enumerate(candidates) if word is not None}
    if not any(w.start_ms is not None or w.protected for w in baseline) and len(
        eligible
    ) < math.ceil(0.7 * count):
        return (None,) * count
    chosen: list[WordObservation | None] = [None] * count
    for i in sorted(eligible):
        if (
            baseline[i].start_ms is not None
            or baseline[i].protected
            or not ({i - 1, i + 1} & eligible)
        ):
            continue
        trial = [*chosen]
        trial[i] = candidates[i]
        timed = [
            candidate if candidate is not None else old
            for candidate, old in zip(trial, baseline, strict=True)
            if candidate is not None or old.start_ms is not None
        ]
        if all(a.end_ms <= b.start_ms for a, b in pairwise(timed)):
            chosen[i] = candidates[i]
    return tuple(chosen)
