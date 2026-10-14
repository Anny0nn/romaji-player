"""Pinned TIFA inference, source-anchored word protocol, and verified model assets.

No playback, lyric lookup, text generation or timestamp interpolation happens here.
"""

import contextlib
import hashlib
import io
import itertools
import json
import os
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor"))
ARCHIVE_SHA = "6da6832cd2cb981aae1ccc2d9330f8f7c085ce7977d1eb13bff63531d038a88b"
PROTOCOL = 3


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def prepare_model(archive):
    """Extract only pinned files; never unpickle an unverified checkpoint."""
    from filelock import FileLock

    if digest(archive) != ARCHIVE_SHA:
        raise ValueError("Timing model integrity check failed.")
    folder = archive.parent / f"tifa-{ARCHIVE_SHA}"
    folder.mkdir(exist_ok=True)
    assets = json.loads((ROOT / "model-files.json").read_text())
    with (
        FileLock(str(folder / "setup.lock"), timeout=60),
        zipfile.ZipFile(archive) as zip,
    ):
        for name, expected in assets.items():
            target = folder / name
            if (
                target.is_file()
                and target.stat().st_size == expected["size"]
                and digest(target) == expected["sha256"]
            ):
                continue
            data = zip.read(f"TIFA-1.0-ST/{name}")
            if (
                len(data) != expected["size"]
                or hashlib.sha256(data).hexdigest() != expected["sha256"]
            ):
                raise ValueError("Timing model asset integrity check failed.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as file:
                temporary = Path(file.name)
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            try:
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
    return folder


def read_manifest(path, sample_count):
    data = memoryview(path.read_bytes())
    if len(data) > 8 * 1024 * 1024:
        raise ValueError("Timing manifest too large.")
    position = 0

    def integer():
        nonlocal position
        value = struct.unpack_from("<I", data, position)[0]
        position += 4
        return value

    def string():
        nonlocal position
        length = integer()
        if length > 4096 or position + length > len(data):
            raise ValueError("Invalid timing word.")
        value = bytes(data[position : position + length]).decode("utf-8")
        position += length
        return value

    if integer() != PROTOCOL:
        raise ValueError("Unsupported timing protocol.")
    count = integer()
    if not 0 < count <= 1000:
        raise ValueError("Invalid crop count.")
    crops, seen = [], set()
    for _ in range(count):
        occurrence, start, end, words = (integer() for _ in range(4))
        if (
            occurrence in seen
            or not 0 <= start < end <= sample_count
            or end - start > 480000
            or not 0 < words <= 1000
        ):
            raise ValueError("Invalid timing crop.")
        seen.add(occurrence)
        targets = []
        for _ in range(words):
            span = [integer(), integer()]
            text, romaji = string(), string()
            if span[0] >= span[1] or not text or not romaji:
                raise ValueError("Invalid timing target.")
            targets.append({"raw_span": span, "text": text, "romaji": romaji})
        crops.append((occurrence, start, end, targets))
    if position != len(data):
        raise ValueError("Trailing timing manifest data.")
    return crops


def pronunciation(text, romaji):
    if text == "は" and romaji == "wa":
        return "わ", "ja"
    if text == "へ" and romaji == "e":
        return "え", "ja"
    if all("ぁ" <= ch <= "ヿ" or ch.isspace() for ch in text):
        return text, "ja"
    if all(ch.isascii() and (ch.isalpha() or ch in " '\u2019") for ch in text):
        return text.lower(), "en"
    # An unresolved kanji reading is not an English pronunciation.
    return text, None


def retain_interval(spans, indices, similarity, agreement, length_ms):
    """Reject incomplete/negative paths and obvious mismatches, not a confidence score."""
    import numpy as np

    if not indices.size or not np.isfinite(agreement) or agreement < 0.99:
        return -1, -1
    found = spans[indices]
    if np.any(found[:, 1] <= found[:, 0]):
        return -1, -1
    start, end = int(found[0, 0] * 10), int(found[-1, 1] * 10)
    if start < 0 or end > length_ms or end - start < 80:
        return -1, -1
    scores = [similarity[a:b, i].mean() for i, (a, b) in zip(indices, found)]
    if not np.isfinite(scores).all() or np.mean(scores) <= 0:
        return -1, -1
    return start, end


def vowel_extensions(text):
    """Expand only same-vowel small-kana elongation, never contracted digraphs.

    This is a phonetic input fallback; source text, displayed reading and byte spans
    remain intact. Unknown small vowels and script mixtures remain unsupported.
    """
    pairs = dict(zip("ぁぃぅぇぉァィゥェォ", "あいうえおアイウエオ", strict=True))
    result = []
    for char in text:
        large = pairs.get(char)
        if result and large == result[-1]:
            result.append(large)
        else:
            result.append(char)
    return "".join(result)


class Aligner:
    def __init__(self, folder):
        import torch
        from g2p.converters.japanese import JapaneseKanaConverter
        from g2p.converters.lstm import LSTMConverter
        from inference.backend import ForcedAlignmentInferenceModel
        from lib.config.io import load_raw_config
        from lib.config.schema import InferenceConfig, ModelConfig
        from lib.vocabulary import Vocabulary

        if not torch.backends.mps.is_available():
            raise RuntimeError("TIFA requires Apple Silicon Metal support.")
        torch.set_num_threads(4)
        torch.manual_seed(0)
        config = load_raw_config(folder / "config.yaml", inherit=True)
        model_config = ModelConfig.model_validate(config["model"], scope=1)
        inference_config = InferenceConfig.model_validate(config["inference"], scope=1)
        model_config.check(scope_mask=1)
        inference_config.check(scope_mask=1)
        self.vocabulary = Vocabulary.from_file(folder / "vocabulary.json")
        self.backend = ForcedAlignmentInferenceModel(model_config, inference_config)
        checkpoint = torch.load(
            folder / "model.pt", map_location="cpu", weights_only=True
        )
        self.backend.load_state_dict(checkpoint["state_dict"], strict=True)
        self.backend.eval()
        self.backend.model.to("mps")
        self.converters = {
            "ja": JapaneseKanaConverter(
                str(folder / "dictionaries/japanese_dict_full.txt")
            ),
            "en": LSTMConverter(
                dict_path=str(folder / "dictionaries/ds_cmudict-07b.txt"),
                model_path=str(folder / "assets/LstmG2p-Eng"),
                beam_size=4,
            ),
        }

    def words(self, targets, *, expand_vowels=False, phonetic_aliases=None):
        from g2p.converters.base import (
            G2PConversionError,
            G2PGroup,
            G2PReading,
            G2PWord,
        )
        from g2p.encoding import G2PEncodingError, encode_paths

        words, target_indices = [], []
        if phonetic_aliases is not None and any(
            type(i) is not int or not 0 <= i < len(targets) for i in phonetic_aliases
        ):
            raise ValueError("Pronunciation aliases changed source-word ownership.")
        for index, target in enumerate(targets):
            text, language = pronunciation(target["text"], target["romaji"])
            if language is None:
                continue
            if phonetic_aliases and phonetic_aliases.get(index):
                word = G2PWord(
                    text=text,
                    language="ja",
                    readings=[
                        G2PReading(
                            paths=[
                                [
                                    G2PGroup(
                                        script=text, phonemes=phonetic_aliases[index]
                                    )
                                ]
                            ]
                        )
                    ],
                )
                try:
                    encode_paths(
                        [word], self.vocabulary, "raise", languages=["ja", "en"]
                    )
                except (ValueError, G2PEncodingError):
                    continue
                words.append(word)
                target_indices.append(index)
                continue
            try:
                parts = self.converters[language].convert(text)
            except (G2PConversionError, KeyError):
                # The kana converter raises KeyError for spellings absent from its
                # phoneme dictionary (for example あぁ). Keep other source words.
                normalized = (
                    vowel_extensions(text)
                    if expand_vowels and language == "ja"
                    else text
                )
                if normalized == text:
                    continue
                try:
                    parts = self.converters[language].convert(normalized)
                except (G2PConversionError, KeyError):
                    continue
            if not parts:
                continue
            paths = [
                list(itertools.chain.from_iterable(path))
                for path in itertools.islice(
                    itertools.product(*(p.readings[0].paths for p in parts)), 32
                )
            ]
            word = G2PWord(
                text=text, language=language, readings=[G2PReading(paths=paths)]
            )
            try:
                encode_paths([word], self.vocabulary, "raise", languages=["ja", "en"])
            except (ValueError, G2PEncodingError):
                continue
            words.append(word)
            target_indices.append(index)
        return words, target_indices

    def pronunciation_choices(self, spec, tensors, score_pronunciations):
        from lib.path_traversal import first_choices

        if not score_pronunciations:
            return first_choices(tensors["candidates"])
        return self.backend.score(
            spec,
            paths=tensors["paths"],
            words=tensors["words"],
            candidates=tensors["candidates"],
            unit="levenshtein",
        ).choices

    def align(
        self,
        samples,
        targets,
        diagnostics=None,
        *,
        score_pronunciations=False,
        expand_vowels=False,
        phonetic_aliases=None,
    ):
        import numpy as np
        import torch
        from g2p.encoding import encode_paths
        from inference.backend import SpectrogramContext
        from lib.path_traversal import materialize_paths
        from scipy.signal import resample_poly

        units = [
            {**{k: t[k] for k in ("raw_span", "text")}, "start_ms": -1, "end_ms": -1}
            for t in targets
        ]
        if diagnostics is not None:
            diagnostics.extend(
                {
                    "raw_span": t["raw_span"],
                    "start_ms": -1,
                    "end_ms": -1,
                    "reason": "unsupported",
                }
                for t in targets
            )
        if not np.isfinite(samples).all() or np.sqrt(np.mean(samples**2)) < 0.0001:
            return units
        options = {"expand_vowels": expand_vowels}
        if phonetic_aliases is not None:
            options["phonetic_aliases"] = phonetic_aliases
        words, target_indices = self.words(targets, **options)
        if not words:
            return units
        encoded, _, _ = encode_paths(
            words, self.vocabulary, "raise", languages=["ja", "en"]
        )
        tensors = {k: torch.from_numpy(v)[None].to("mps") for k, v in encoded.items()}
        resampled = resample_poly(samples, 3, 1).astype(np.float32)
        with torch.inference_mode():
            spec = self.backend.spectrogram(
                torch.from_numpy(resampled.copy())[None],
                torch.tensor([len(resampled) / 48000]),
            )
            spec = SpectrogramContext(spec.features.to("mps"), spec.mask.to("mps"))
            choices = self.pronunciation_choices(spec, tensors, score_pronunciations)
            tokens, owners, groups = materialize_paths(
                tensors["paths"], tensors["words"], tensors["groups"], choices
            )
            result = self.backend.align(
                spec, tokens=tokens, groups=groups, unit="frame", skip_penalty=0.5
            )
        spans, owners = result.spans[0].cpu().numpy(), owners[0].cpu().numpy()
        similarity, probability = (
            result.similarity[0].cpu().numpy(),
            result.token_probability[0].cpu().numpy(),
        )
        for index, target_index in enumerate(target_indices):
            indices = np.flatnonzero(owners == index + 1)
            start, end = retain_interval(
                spans,
                indices,
                similarity,
                float(np.mean(probability[indices])) if indices.size else 0.0,
                len(samples) // 16,
            )
            units[target_index].update(start_ms=start, end_ms=end)
            if diagnostics is not None:
                found = spans[indices]
                valid = bool(indices.size and np.all(found[:, 1] > found[:, 0]))
                scores = (
                    [
                        float(similarity[a:b, i].mean())
                        for i, (a, b) in zip(indices, found)
                    ]
                    if valid
                    else []
                )
                mean = float(np.mean(scores)) if scores else None
                raw_start = int(found[0, 0] * 10) if valid else -1
                raw_end = int(found[-1, 1] * 10) if valid else -1
                agreement = (
                    float(np.mean(probability[indices])) if indices.size else 0.0
                )
                reason = (
                    "retained"
                    if start >= 0
                    else "incomplete"
                    if not valid
                    else "token_agreement"
                    if not np.isfinite(agreement) or agreement < 0.99
                    else "duration"
                    if raw_end - raw_start < 80
                    else "bounds"
                    if raw_start < 0 or raw_end > len(samples) // 16
                    else "similarity"
                )
                diagnostics[target_index].update(
                    start_ms=raw_start,
                    end_ms=raw_end,
                    reason=reason,
                    agreement=agreement,
                    mean_similarity=mean
                    if mean is not None and np.isfinite(mean)
                    else None,
                )
        return units


def main():
    # Keep the JIT cache out of the signed, read-only app bundle.
    cache = Path(tempfile.gettempdir()) / "RomajiTIFA-numba-v1"
    cache.mkdir(exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(cache)
    if sys.argv[1:] == ["--self-test"]:
        import torch

        value = (torch.ones(2, device="mps") + 1).cpu().tolist()
        assert value == [2, 2]
        print(json.dumps({"protocol": PROTOCOL, "self_test": True, "device": "mps"}))
        return
    import numpy as np

    archive, pcm, manifest = map(Path, sys.argv[1:])
    if pcm.stat().st_size > 600 * 16000 * 4 or pcm.stat().st_size % 4:
        raise ValueError("Invalid audio size.")
    samples = np.memmap(pcm, dtype="<f4", mode="r")
    crops = read_manifest(manifest, len(samples))
    with contextlib.redirect_stdout(io.StringIO()):
        aligner = Aligner(prepare_model(archive))
    for occurrence, start, end, targets in crops:
        print(
            result_line(aligner, occurrence, np.asarray(samples[start:end]), targets),
            flush=True,
        )


def result_line(aligner, occurrence, samples, targets):
    # Upstream mel code prints amplitude diagnostics for real-song resampling overshoot.
    # Keep all library diagnostics out of the JSONL protocol and private logs.
    with contextlib.redirect_stdout(io.StringIO()):
        units = aligner.align(samples, targets)
    return json.dumps({"occurrence": occurrence, "units": units})


if __name__ == "__main__":
    # Never log private lyrics/audio or checkpoint contents on failure.
    sys.excepthook = lambda *_: print("Local TIFA timing failed.", file=sys.stderr)
    main()
