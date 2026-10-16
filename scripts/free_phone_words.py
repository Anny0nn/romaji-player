"""Whole source words witnessed by an already decoded, source-blind phone stream.

Only exact unique phone contexts qualify. Context size and minimum word length
are explicit research parameters, not a promoted app policy. Observed mora tokens
cannot be split between source words; timestamps bound complete observed tokens.
Phonetic correspondence cannot distinguish homophones or establish kanji spelling.
"""

from difflib import SequenceMatcher

from audio_first_ctc import greedy


def observe_words(
    logp,
    blank,
    words,
    vocabulary_phones,
    *,
    frame_ms,
    receptive_ms,
    context_phones=2,
    minimum_word_phones=1,
):
    import numpy as np

    if (
        logp.ndim != 2
        or not np.isfinite(logp).all()
        or not np.allclose(np.logaddexp.reduce(logp, axis=1), 0, atol=1e-4)
        or any(
            type(k) is not int or not 0 <= k < logp.shape[1] for k in vocabulary_phones
        )
        or not np.isfinite([frame_ms, receptive_ms]).all()
        or min(frame_ms, receptive_ms) <= 0
        or type(context_phones) is not int
        or context_phones < 0
        or type(minimum_word_phones) is not int
        or minimum_word_phones < 1
    ):
        raise ValueError("Invalid source-blind CTC clock or probabilities.")
    # Source text has no influence on this decode or these token probabilities.
    decoded = greedy(logp, blank)
    observed, token_bounds, probabilities, frame_bounds = [], {0: 0}, [], []
    for token, (first, last) in zip(
        decoded["token_ids"], decoded["emission_frames"], strict=True
    ):
        phones = vocabulary_phones.get(token) or ["observed-unknown:" + str(token)]
        probability = float(np.exp(logp[first : last + 1, token]).mean())
        observed.extend(phones)
        probabilities.append(probability)
        frame_bounds.append((first, last))
        token_bounds[len(observed)] = len(probabilities)
    source, source_bounds = [], [0]
    for index, word in enumerate(words):
        source.extend(word["phones"] or ["source-unknown:" + str(index)])
        source_bounds.append(len(source))
    blocks = SequenceMatcher(
        None, source, observed, autojunk=False
    ).get_matching_blocks()
    correspondence = {
        block.a + n: block.b + n for block in blocks for n in range(block.size)
    }
    output = []
    for index, word in enumerate(words):
        unit = {
            "raw_span": word["raw_span"],
            "source_match": False,
            "confidence_kind": "free-ctc-mean-phone-probability",
            "source_conditioned": False,
            "probability": None,
            "minimum_token_probability": None,
            "start_ms": -1,
            "end_ms": -1,
            "observed_token_span": None,
        }
        output.append(unit)
        first, last = source_bounds[index], source_bounds[index + 1]
        if (
            not word["phones"]
            or last - first < minimum_word_phones
            or first < context_phones
            or last + context_phones > len(source)
        ):
            continue
        mapping = [
            correspondence.get(i)
            for i in range(first - context_phones, last + context_phones)
        ]
        if any(i is None for i in mapping) or mapping != list(
            range(mapping[0], mapping[0] + len(mapping))
        ):
            continue
        context = source[first - context_phones : last + context_phones]
        if any(
            sum(
                sequence[i : i + len(context)] == context
                for i in range(len(sequence) - len(context) + 1)
            )
            != 1
            for sequence in (source, observed)
        ):
            continue
        a, b = correspondence[first], correspondence[last - 1] + 1
        if a not in token_bounds or b not in token_bounds:
            continue
        start, end = token_bounds[a], token_bounds[b]
        token_widths = [
            len(vocabulary_phones[decoded["token_ids"][i]]) for i in range(start, end)
        ]
        probability = sum(
            p * width
            for p, width in zip(probabilities[start:end], token_widths, strict=True)
        ) / (b - a)
        unit.update(
            source_match=True,
            probability=probability,
            minimum_token_probability=min(probabilities[start:end]),
            start_ms=frame_bounds[start][0] * frame_ms,
            end_ms=frame_bounds[end - 1][1] * frame_ms + receptive_ms,
            observed_token_span=[start, end],
        )
    return output
