"""Research-only source-conditioned Whisper observations, never lexical truth.

Score the same candidate on original, wrong-verse and silence audio to separate
acoustic evidence from the decoder's language prior. Do not promote raw confidence.
"""

import json
import math
from itertools import pairwise
from types import SimpleNamespace

from audio_first_models import ROOT, verify


def owned_token_indices(text, targets, token_bytes):
    """Exact BPE ownership, including split UTF-8 bytes, without splitting tokens."""
    raw = text.encode()
    if b"".join(token_bytes) != raw:
        raise ValueError("Decoder bytes do not reconstruct original source.")
    pieces, offset = [], 0
    for index, data in enumerate(token_bytes):
        first = offset + len(data) - len(data.lstrip(b" \t\r\n"))
        last = offset + len(data.rstrip(b" \t\r\n"))
        if first < last:
            pieces.append((first, last, index))
        offset += len(data)
    result = []
    for target in targets:
        first, last = target["raw_span"]
        if (
            type(first) is not int
            or type(last) is not int
            or not 0 <= first < last <= len(raw)
        ):
            raise ValueError("Invalid original source span.")
        raw[first:last].decode()
        chosen = [(a, b, i) for a, b, i in pieces if a < last and first < b]
        exact = (
            bool(chosen)
            and chosen[0][0] == first
            and chosen[-1][1] == last
            and all(first <= a < b <= last for a, b, _ in chosen)
            and all(not raw[b:c].strip() for (_, b, _), (c, _, _) in pairwise(chosen))
        )
        result.append([i for _, _, i in chosen] if exact else None)
    return result


def owned_envelopes(text, targets, observations, length_ms):
    """Merge complete observed pieces; a piece spanning source words is withheld."""
    raw = text.encode()
    offset = 0
    pieces = []
    for unit in observations:
        word = unit["word"]
        data = word.encode()
        if raw[offset : offset + len(data)] != data:
            raise ValueError("Attention words fail exact source reconstruction.")
        leading = len(data) - len(data.lstrip(b" \t\r\n"))
        trailing = len(data.rstrip(b" \t\r\n"))
        if trailing > leading:
            pieces.append((offset + leading, offset + trailing, unit))
        offset += len(data)
    if offset != len(raw):
        raise ValueError("Incomplete attention source reconstruction.")
    result = []
    for target in targets:
        first, last = target["raw_span"]
        if (
            type(first) is not int
            or type(last) is not int
            or not 0 <= first < last <= len(raw)
        ):
            raise ValueError("Invalid original source span.")
        raw[first:last].decode()
        chosen = [(a, b, u) for a, b, u in pieces if a < last and first < b]
        exact = (
            bool(chosen)
            and chosen[0][0] == first
            and chosen[-1][1] == last
            and all(first <= a < b <= last for a, b, _ in chosen)
            and all(not raw[b:c].strip() for (_, b, _), (c, _, _) in pairwise(chosen))
        )
        start, end = (
            (chosen[0][2]["start_ms"], chosen[-1][2]["end_ms"]) if exact else (-1, -1)
        )
        exact = (
            exact
            and all(
                isinstance(u[k], (int, float))
                and not isinstance(u[k], bool)
                and math.isfinite(u[k])
                for _, _, u in chosen
                for k in ("start_ms", "end_ms", "probability")
            )
            and all(0 <= u["start_ms"] < u["end_ms"] <= length_ms for _, _, u in chosen)
            and all(0 <= u["probability"] <= 1 for _, _, u in chosen)
            and all(a[2]["end_ms"] <= b[2]["start_ms"] for a, b in pairwise(chosen))
        )
        result.append(
            {
                "raw_span": target["raw_span"],
                "start_ms": start if exact else -1,
                "end_ms": end if exact else -1,
                "conditional_probability": sum(u["probability"] for _, _, u in chosen)
                / len(chosen)
                if exact
                else None,
                "source_conditioned": True,
            }
        )
    return result


class SourceScorer:
    def __init__(self, models):
        import mlx.core as mx
        from mlx_whisper.transcribe import ModelHolder

        self.assets = [
            a
            for a in json.loads(
                (ROOT / "refinement/refinement-model-files.json").read_text()
            )
            if a["path"].startswith("whisper/")
        ]
        for a in self.assets:
            verify(models / a["path"], a["sha256"])
        self.model = ModelHolder.get_model(str(models / "whisper"), mx.float16)

    def observe(self, samples, text, language, targets, *, boundaries=True):
        import mlx.core as mx
        import numpy as np
        from mlx_whisper.audio import (
            HOP_LENGTH,
            N_FRAMES,
            N_SAMPLES,
            log_mel_spectrogram,
            pad_or_trim,
        )
        from mlx_whisper.timing import find_alignment
        from mlx_whisper.tokenizer import get_tokenizer

        if (
            language not in ("ja", "en")
            or samples.ndim != 1
            or not np.isfinite(samples).all()
            or not 160 <= len(samples) <= N_SAMPLES
        ):
            raise ValueError("Invalid bounded source/audio candidate.")
        tokenizer = get_tokenizer(
            self.model.is_multilingual,
            num_languages=self.model.num_languages,
            language=language,
            task="transcribe",
        )
        text_tokens = tokenizer.encode(text)
        prefix = [*tokenizer.sot_sequence, tokenizer.no_timestamps]
        if (
            not text_tokens
            or len(prefix) + len(text_tokens) + 1 > self.model.dims.n_text_ctx
            or tokenizer.decode(text_tokens) != text
        ):
            raise ValueError(
                "Source candidate does not fit/reconstruct exact decoder tokens."
            )
        inputs = mx.array([*prefix, *text_tokens, tokenizer.eot])
        mel = pad_or_trim(
            log_mel_spectrogram(
                samples, n_mels=self.model.dims.n_mels, padding=N_SAMPLES
            ),
            N_FRAMES,
            axis=-2,
        ).astype(mx.float16)
        logits, cross = self.model.forward_with_cross_qk(mel[None, :], inputs[None, :])
        # Full vocabulary, including EOS: no target-token mask inflates likelihood.
        selected = logits[
            0, len(prefix) - 1 : len(prefix) - 1 + len(text_tokens), :
        ].astype(mx.float32)
        logp = selected - mx.logsumexp(selected, axis=-1, keepdims=True)
        token_scores = np.array(
            mx.take_along_axis(logp, mx.array(text_tokens)[:, None], axis=1).squeeze(1)
        )
        if not np.isfinite(token_scores).all():
            raise ValueError("Undefined source-conditioned token scores.")
        ownership = owned_token_indices(
            text,
            targets,
            [tokenizer.encoding.decode_single_token_bytes(t) for t in text_tokens],
        )

        def cached_forward(_mel, tokens):
            if not np.array_equal(np.array(tokens), np.array(inputs[None, :])):
                raise ValueError("Attention request changed candidate tokens.")
            return logits, cross

        proxy = SimpleNamespace(
            alignment_heads=self.model.alignment_heads,
            forward_with_cross_qk=cached_forward,
        )
        alignment = (
            find_alignment(
                proxy, tokenizer, text_tokens, mel, len(samples) // HOP_LENGTH
            )
            if boundaries
            else []
        )
        observations = [
            {
                "word": u.word,
                "start_ms": float(u.start) * 1000,
                "end_ms": float(u.end) * 1000,
                "probability": float(u.probability),
            }
            for u in alignment
        ]
        units = (
            owned_envelopes(text, targets, observations, len(samples) / 16)
            if boundaries
            else None
        )
        mx.clear_cache()
        return {
            "tokens": len(text_tokens),
            "characters": len(text),
            "utf8_bytes": len(text.encode()),
            "sum_log_probability": float(token_scores.sum()),
            "mean_token_log_probability": float(token_scores.mean()),
            "token_log_probabilities": token_scores.tolist(),
            "source_token_indices": ownership,
            "source_mean_log_probabilities": [
                float(token_scores[indices].mean()) if indices else None
                for indices in ownership
            ],
            "attention_words": observations,
            "source_units": units,
            "role": "source-conditioned observation, not independent recognition or verification",
        }
