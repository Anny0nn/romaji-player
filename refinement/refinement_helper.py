"""Sequential experimental singing alignment, using verified local model assets.

Same source-word protocol as TIFA. Audio never leaves this process. Repairs require
independent MMS evidence; old source snapshots and baseline intervals stay intact.
"""

import contextlib
import gc
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import multiprocessing
import os
import sys
import tempfile
import traceback
from pathlib import Path

from refinement_policy import (
    chunk_windows,
    coherent_line,
    ctc_labels,
    ctc_path,
    repair_regions,
    supported_raw,
)
from tifa_helper import Aligner, prepare_model, read_manifest, vowel_extensions

ROOT = Path(__file__).resolve().parent


def kim_classes():
    # Load only the pinned separation module, avoiding unrelated TTS/ASR models
    # eagerly imported by mlx-audio's broad models package initializer.
    if "romaji_mel_roformer" not in sys.modules:
        folder = ROOT / "mel_roformer"
        if not folder.is_dir():
            folder = Path(
                importlib.metadata.distribution("mlx-audio").locate_file(
                    "mlx_audio/sts/models/mel_roformer"
                )
            )
        spec = importlib.util.spec_from_file_location(
            "romaji_mel_roformer",
            folder / "__init__.py",
            submodule_search_locations=[str(folder)],
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    module = sys.modules["romaji_mel_roformer"]
    return module.MelRoFormer, module.MelRoFormerConfig


def verify_assets(folder):
    for asset in json.loads((ROOT / "refinement-model-files.json").read_text()):
        path = folder / asset["path"]
        with path.open("rb") as file:
            if (
                path.stat().st_size != asset["size"]
                or hashlib.file_digest(file, "sha256").hexdigest() != asset["sha256"]
            ):
                raise ValueError("Experimental model integrity check failed.")


def progress(path, message):
    temporary = path.with_suffix(".part")
    temporary.write_text(message)
    os.replace(temporary, path)


def release():
    import mlx.core as mx
    import torch

    gc.collect()
    torch.mps.empty_cache()
    mx.clear_cache()


def tifa(samples, crops, archive, progress_path, stage, *, vowel_retry=False):
    aligner = Aligner(prepare_model(archive))
    result = []
    for n, (_, first, last, targets) in enumerate(crops):
        progress(progress_path, f"{stage} · line {n + 1}/{len(crops)}")
        raw = []
        units = aligner.align(samples[first:last], targets, diagnostics=raw)
        row = {"units": units, "raw_units": raw}
        if vowel_retry and any(
            vowel_extensions(t["text"]) != t["text"] for t in targets
        ):
            _, original = aligner.words(targets)
            _, expanded = aligner.words(targets, expand_vowels=True)
            eligible = sorted(set(expanded) - set(original))
            if eligible:
                extra = []
                trial = aligner.align(
                    samples[first:last], targets, diagnostics=extra, expand_vowels=True
                )
                row["vowel_retry"] = {
                    "units": trial,
                    "raw_units": extra,
                    "eligible": [targets[i]["raw_span"] for i in eligible],
                }
        result.append(row)
    del aligner
    release()
    return result


def separate(stereo, length, folder, name, progress_path):
    import mlx.core as mx
    import numpy as np
    from scipy.signal import resample_poly

    progress(progress_path, f"Isolating vocals · {name}")
    if name == "Demucs":
        from demucs_mlx.api import Separator

        os.environ["DEMUCS_MLX_CACHE_DIR"] = str(folder / "demucs")
        os.environ["DEMUCS_MLX_OFFLINE"] = "1"
        backend = Separator(model="htdemucs", shifts=1, seed=0, batch_size=1)
        output = backend.separate_tensor(stereo)[1]["vocals"]
    else:
        MelRoFormer, MelRoFormerConfig = kim_classes()

        config = MelRoFormerConfig.kim_vocal_2()
        backend = MelRoFormer(config)
        weights = backend.sanitize(dict(mx.load(str(folder / "kim/model.safetensors"))))
        backend.load_weights(list(weights.items()), strict=True)
        mx.eval(backend.parameters())
        backend.eval()
        del weights
        size = config.chunk_size
        weight = np.hanning(size).astype(np.float32)
        output = np.zeros_like(stereo, dtype=np.float32)
        denominator = np.zeros(stereo.shape[-1], dtype=np.float32)
        windows = list(chunk_windows(stereo.shape[-1], size))
        for n, (start, first, last) in enumerate(windows):
            progress(progress_path, f"Isolating vocals · Kim · {n + 1}/{len(windows)}")
            block = np.zeros((2, size), dtype=np.float32)
            local = first - start
            block[:, local : local + last - first] = stereo[:, first:last]
            prediction = backend(mx.array(block[None]))
            mx.eval(prediction)
            prediction = np.asarray(prediction[0], dtype=np.float32)
            if prediction.shape != block.shape or not np.isfinite(prediction).all():
                raise ValueError("Invalid separated audio.")
            weights = weight[local : local + last - first]
            output[:, first:last] += (
                prediction[:, local : local + last - first] * weights
            )
            denominator[first:last] += weights
            del prediction, block
        if np.any(denominator <= 0):
            raise ValueError("Incomplete audio separation.")
        output /= denominator
    if output.shape != stereo.shape or not np.isfinite(output).all():
        raise ValueError("Separation changed original sample positions.")
    samples = resample_poly(output.mean(axis=0), 160, 441).astype(np.float32)
    if not length <= len(samples) <= length + 1 or not np.isfinite(samples).all():
        raise ValueError("Separation changed recording duration.")
    del backend, output
    release()
    return samples[:length]


def phonetic_units(logp, blank, targets, vocabulary):
    import numpy as np

    units = [
        {
            "raw_span": t["raw_span"],
            "start_ms": -1,
            "end_ms": -1,
            "mean_probability": 0.0,
        }
        for t in targets
    ]
    labels = ctc_labels(targets, vocabulary)
    path = ctc_path(logp.tolist(), labels, blank) if labels else None
    if path is None:
        return units
    path, token = np.array(path), 0
    for target, unit in zip(targets, units, strict=True):
        spelling = [
            c for c in target["romaji"].lower() if c in vocabulary and c.isalpha()
        ]
        frames = [
            np.flatnonzero(path == 2 * i + 1)
            for i in range(token, token + len(spelling))
        ]
        if frames and all(len(f) for f in frames):
            scores = [
                float(np.exp(logp[f, labels[i]]).mean())
                for f, i in zip(
                    frames, range(token, token + len(spelling)), strict=True
                )
            ]
            unit.update(
                start_ms=int(frames[0][0] * 20),
                end_ms=int(frames[-1][-1] * 20 + 25),
                mean_probability=sum(scores) / len(scores),
            )
        token += len(spelling) + 1
    return units


def mms(samples, crops, folder, progress_path, stage, posteriors=False):
    import torch
    from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

    config = json.loads((folder / "processor_config.json").read_text())
    processor = Wav2Vec2FeatureExtractor(**config["feature_extractor"])
    backend = (
        Wav2Vec2ForCTC.from_pretrained(folder, local_files_only=True).to("mps").eval()
    )
    vocabulary = json.loads((folder / "vocab.json").read_text())
    result = []
    for n, (_, first, last, targets) in enumerate(crops):
        progress(progress_path, f"{stage} · line {n + 1}/{len(crops)}")
        inputs = processor(
            samples[first:last], sampling_rate=16000, return_tensors="pt"
        ).to("mps")
        with torch.inference_mode():
            logp = backend(**inputs).logits[0].float().log_softmax(-1).cpu().numpy()
        result.append(
            (logp, backend.config.pad_token_id)
            if posteriors
            else phonetic_units(logp, backend.config.pad_token_id, targets, vocabulary)
        )
    del backend, inputs
    release()
    return result


def repair(
    baseline, trial, evidence, targets, length_ms, source_words=None, *, eligible=None
):
    candidates = supported_raw(trial, evidence, length_ms)
    coherent = coherent_line(candidates, evidence, source_words)
    if eligible is not None:
        nominated = {tuple(s) for s in eligible}
        if not nominated <= {tuple(t["raw_span"]) for t in targets}:
            raise ValueError("Vowel retry changed its source anchors.")
        # A pronunciation fallback cannot authorize unrelated missing words.
        # Retained neighbors may move only through the existing bounded region gate.
        candidates = [
            {**new, "start_ms": -1, "end_ms": -1}
            if old["start_ms"] < 0 and tuple(new["raw_span"]) not in nominated
            else new
            for old, new in zip(baseline, candidates, strict=True)
        ]
    repaired = repair_regions(baseline, candidates, evidence) if coherent else baseline
    return [
        {
            "raw_span": t["raw_span"],
            "text": t["text"],
            "start_ms": u["start_ms"],
            "end_ms": u["end_ms"],
        }
        for t, u in zip(targets, repaired, strict=True)
    ]


def run(archive, folder, pcm, stereo_path, manifest, progress_path, romanizer=None):
    import numpy as np

    verify_assets(folder)
    samples = np.memmap(pcm, dtype="<f4", mode="r")
    stereo = np.memmap(stereo_path, dtype="<f4", mode="r")
    if not 0 < len(samples) <= 600 * 16000 or len(stereo) % 2:
        raise ValueError("Invalid experimental recording size.")
    if abs(len(stereo) / 2 / 44100 - len(samples) / 16000) > 0.001:
        raise ValueError("Stereo recording has a different origin or duration.")
    stereo = np.asarray(stereo.reshape(-1, 2).T)
    if not np.isfinite(samples).all() or not np.isfinite(stereo).all():
        raise ValueError("Invalid recording samples.")
    crops = read_manifest(manifest, len(samples))
    counts_path = manifest.with_suffix(".counts.json")
    if counts_path.stat().st_size > 64 * 1024:
        raise ValueError("Source word counts exceed limit.")
    counts = json.loads(counts_path.read_text())
    if set(counts) != {str(c[0]) for c in crops} or any(
        not isinstance(counts[str(c[0])], int)
        or not len(c[3]) <= counts[str(c[0])] <= 1000
        for c in crops
    ):
        raise ValueError("Original source word counts changed.")
    if romanizer is not None:
        return run_readings(
            archive,
            folder,
            samples,
            stereo,
            pcm,
            stereo_path,
            crops,
            manifest,
            progress_path,
            romanizer,
        )
    result = [
        r["units"]
        for r in tifa(samples, crops, archive, progress_path, "TIFA baseline")
    ]
    for name in ("Demucs", "Kim"):
        vocals = separate(stereo, len(samples), folder, name, progress_path)
        trial = tifa(vocals, crops, archive, progress_path, f"TIFA · {name}")
        evidence = mms(
            vocals, crops, folder / "mms", progress_path, f"Checking · {name}"
        )
        result = [
            repair(b, v, e, targets, (last - first) // 16, counts[str(occurrence)])
            for b, v, e, (occurrence, first, last, targets) in zip(
                result, trial, evidence, crops, strict=True
            )
        ]
        del vocals, trial, evidence
        release()
    return [
        {"occurrence": occurrence, "units": units}
        for (occurrence, _, _, _), units in zip(crops, result, strict=True)
    ]


def run_readings(
    archive,
    folder,
    samples,
    stereo,
    pcm,
    stereo_path,
    crops,
    manifest,
    progress_path,
    romanizer,
):
    from reading_repair import (
        Converter,
        corrected_crops,
        propose,
        singing_evidence,
        transcribe,
    )

    input_path = manifest.with_suffix(".readings.json")
    if input_path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Reading request exceeds limit.")
    inputs = json.loads(input_path.read_text())
    if inputs["protocol_version"] != 1 or inputs["recipe"] != "sung-reading-v1":
        raise ValueError("Unsupported reading recipe.")
    digest = hashlib.sha256()
    for path in (pcm, stereo_path):
        with path.open("rb") as file:
            while block := file.read(1024 * 1024):
                digest.update(block)
    if digest.hexdigest() != inputs["audio_sha256"]:
        raise ValueError("Reading evidence uses different audio.")
    stems, views = [], []
    for name in ("Demucs", "Kim"):
        vocals = separate(stereo, len(samples), folder, name, progress_path)
        views.append(
            mms(
                vocals,
                crops,
                folder / "mms",
                progress_path,
                f"Checking readings · {name}",
                posteriors=True,
            )
        )
        stems.append(vocals)
    independent, independent_vocabulary = singing_evidence(
        stems[-1], crops, folder, progress_path
    )
    transcripts = [
        transcribe(stems[-1], folder, progress_path, "vocals"),
        transcribe(samples, folder, progress_path, "original mix"),
    ]
    vocabulary = json.loads((folder / "mms/vocab.json").read_text())
    converter = Converter(romanizer)
    try:
        progress(progress_path, "Selecting supported sung readings…")
        readings, text_repairs = propose(
            inputs,
            crops,
            converter,
            views,
            independent,
            vocabulary,
            independent_vocabulary,
            transcripts,
        )
        if len(readings) + len(text_repairs) > 256:
            raise ValueError("Too many automatic reading repairs.")
        corrected, counts = corrected_crops(
            inputs, crops, converter, readings, text_repairs
        )
    finally:
        converter.close()
    result = [
        r["units"]
        for r in tifa(
            samples, corrected, archive, progress_path, "Timing checked lyrics"
        )
    ]
    for name, vocals, posterior in zip(("Demucs", "Kim"), stems, views, strict=True):
        trial = tifa(
            vocals,
            corrected,
            archive,
            progress_path,
            f"Timing checked lyrics · {name}",
            vowel_retry=True,
        )
        evidence = [
            phonetic_units(logp, blank, targets, vocabulary)
            for (logp, blank), (_, _, _, targets) in zip(
                posterior, corrected, strict=True
            )
        ]
        result = [
            repair(b, v, e, targets, (last - first) // 16, counts[str(occurrence)])
            for b, v, e, (occurrence, first, last, targets) in zip(
                result, trial, evidence, corrected, strict=True
            )
        ]
        result = [
            repair(
                b,
                v["vowel_retry"],
                e,
                targets,
                (last - first) // 16,
                counts[str(occurrence)],
                eligible=v["vowel_retry"]["eligible"],
            )
            if "vowel_retry" in v
            else b
            for b, v, e, (occurrence, first, last, targets) in zip(
                result, trial, evidence, corrected, strict=True
            )
        ]
    from singing_recovery import recover

    aligner = Aligner(prepare_model(archive))
    try:
        result = recover(
            stems[-1],
            corrected,
            aligner,
            independent,
            independent_vocabulary,
            result,
            counts,
            lambda message: progress(progress_path, message),
        )
    finally:
        del aligner
        release()
    # Complete tentative version only. Rust independently checks identity, gates,
    # original spans and reconversion before admitting any correction or timing.
    identity = {
        k: inputs[k]
        for k in (
            "protocol_version",
            "track",
            "snapshot",
            "revision",
            "delay_ms",
            "model_sha256",
            "audio_sha256",
            "recipe",
        )
    }
    return [
        {
            "kind": "repairs",
            **identity,
            "readings": readings,
            "text_repairs": text_repairs,
        },
        *[
            {"occurrence": occurrence, "units": units}
            for (occurrence, _, _, _), units in zip(corrected, result, strict=True)
        ],
    ]


def main():
    cache = Path(tempfile.gettempdir()) / "RomajiExperimental-numba-v1"
    cache.mkdir(exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(cache)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    if len(sys.argv) == 3 and sys.argv[1] == "--check-converter":
        from reading_repair import Converter

        converter = Converter(Path(sys.argv[2]))
        try:
            request = {
                "protocol_version": 2,
                "request_id": 1,
                "track_id": "synthetic",
                "snapshot_id": "check",
                "occurrence_id": 0,
                "override_revision": 0,
                "expected_conversion_signature": converter.signature,
                "raw_line": "行こう",
                "overrides": [],
            }
            assert any(
                c["hiragana"] == "ゆこう"
                for g in converter.convert(request, True)["reading_candidates"]
                for c in g["candidates"]
            )
            assert converter.canonical("ゆこう", request)["romaji"] == "yukou"
            print(json.dumps({"protocol": 1, "converter_check": True}))
        finally:
            converter.close()
        return
    if sys.argv[1:] == ["--self-test"]:
        import mlx.core as mx
        import torch
        from demucs_mlx.api import Separator  # noqa: F401

        kim_classes()
        import mlx_whisper  # noqa: F401
        from mlx_audio.dsp import mel_filters
        from transformers import (
            HubertForCTC,  # noqa: F401
            Wav2Vec2ForCTC,  # noqa: F401
        )

        if not torch.backends.mps.is_available():
            raise RuntimeError("Metal unavailable.")
        assert torch.ones(2, device="mps").sum().item() == 2
        assert mx.sum(mx.ones((2,))).item() == 2
        assert mel_filters(
            sample_rate=44100, n_fft=2048, n_mels=60, mel_scale="slaney"
        ).shape == (60, 1025)
        print(json.dumps({"protocol": 3, "self_test": True, "device": "mps+mlx"}))
        return
    if len(sys.argv) not in (7, 8):
        raise ValueError(
            "Expected verified models, mono/stereo audio, manifest and progress path."
        )
    with contextlib.redirect_stdout(io.StringIO()):
        result = run(*(Path(arg) for arg in sys.argv[1:]))
    for line in result:
        print(json.dumps(line, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        main()
    except Exception as error:  # noqa: BLE001 -- never emit private lyric/audio contents
        print(
            "Experimental timing failed. Existing saved lyrics are preserved.",
            file=sys.stderr,
        )
        # Function/line coordinates and exception types locate packaging failures
        # without printing exception messages, source snippets, lyrics or paths.
        print(type(error).__name__, file=sys.stderr)
        for frame in traceback.extract_tb(error.__traceback__):
            print(
                f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}",
                file=sys.stderr,
            )
        if (
            isinstance(error, ModuleNotFoundError)
            and error.name
            and all(c.isalnum() or c in "._" for c in error.name)
        ):
            print(f"Missing runtime module: {error.name}", file=sys.stderr)
        raise SystemExit(1) from None
