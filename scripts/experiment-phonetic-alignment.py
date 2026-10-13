"""Private, offline trials of vocal isolation and phonetic Japanese alignment.

No stage writes app data. Inputs reuse the pinned source/audio/crop identities of
experiment-lyric-ensemble.py. Models are loaded one at a time, never by test hooks.
"""

import argparse
import contextlib
import difflib
import hashlib
import importlib.util
import io
import json
import math
import os
import resource
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "ensemble", ROOT / "scripts/experiment-lyric-ensemble.py"
)
ensemble = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ensemble)
policy_spec = importlib.util.spec_from_file_location(
    "refinement_policy", ROOT / "refinement/refinement_policy.py"
)
policy = importlib.util.module_from_spec(policy_spec)
policy_spec.loader.exec_module(policy)
agree = policy.agree
chunk_windows = policy.chunk_windows
coherent_line = policy.coherent_line
ctc_path = policy.ctc_path
phonetic_support = policy.phonetic_support
recover_gaps = policy.recover_gaps
repair_regions = policy.repair_regions
supported_raw = policy.supported_raw
KANA_SHA = "1c8d97f2c01560da21df4095cea800f0b6f12dd1269c8e2233e6db659b502e14"
KIM_SHA = "312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5"
KIM_CONFIG_SHA = "3300eacac960ab46933ef6df6b838eb35de1f0321db9242c1b06e6d2a6a62b58"


def identity(case):
    result = {
        k: case[k]
        for k in ("id", "pcm", "audio_sha256", "snapshot", "start_ms", "end_ms")
    }
    for key in ("mix_pcm", "mix_sha256", "stereo_sha256"):
        if key in case:
            result[key] = case[key]
    return result


def controls(cases, directory):
    # This recording has a verified instrumental intro for the negative control.
    target = next(
        c
        for c in cases
        if c["track"] == "4cH6RfZ1qIuz6sumRoDEGK"
        and any(w["expected_text"] == "地球" for w in c["words"])
    )
    silent = directory / "silence.pcm"
    silent.write_bytes(bytes(6 * 16000 * 4))
    silent.chmod(0o600)
    return [
        *cases,
        {
            **target,
            "id": "control:silence",
            "pcm": str(silent),
            "audio_sha256": hashlib.sha256(silent.read_bytes()).hexdigest(),
            "start_ms": 1000,
            "end_ms": 6000,
        },
        {**target, "id": "control:instrumental", "start_ms": 1000, "end_ms": 6000},
    ]


def wrong_controls(cases, baseline, vocals, stems):
    baseline = ensemble.evidence_by_id(baseline)
    vocals = ensemble.evidence_by_id(vocals)
    result = []
    for track in sorted(
        {c["track"] for c in cases if not c["id"].startswith("control:")}
    ):
        group = [
            c
            for c in cases
            if c["track"] == track
            and not c["id"].startswith("control:")
            and len(c["words"]) >= 5
            and all(
                all("ぁ" <= ch <= "ゖ" or ch in "ー " for ch in w["hiragana"])
                for w in c["words"]
            )
        ]
        for case in group:
            validate_result(case, baseline[case["id"]])
            validate_result(case, vocals[case["id"]])
        target = next(
            (
                c
                for c in group
                if all(u["start_ms"] >= 0 for u in baseline[c["id"]]["units"])
                and all(u["start_ms"] >= 0 for u in vocals[c["id"]]["units"])
            ),
            None,
        )
        if target is None:
            print(
                json.dumps(
                    {
                        "control_unavailable": track,
                        "reason": "No fully retained Japanese target with five words.",
                    }
                ),
                flush=True,
            )
            continue

        def pronunciation(case):
            return "".join(w["hiragana"] for w in case["words"])

        def similarity(case, target=target):
            return difflib.SequenceMatcher(
                None, pronunciation(target), pronunciation(case)
            ).ratio()

        source = min(
            (c for c in group if abs(c["start_ms"] - target["start_ms"]) > 30000),
            key=similarity,
            default=None,
        )
        if source is None or similarity(source) >= 0.4:
            print(
                json.dumps(
                    {
                        "control_unavailable": track,
                        "reason": "No sufficiently different distant Japanese vocal crop.",
                    }
                ),
                flush=True,
            )
            continue
        case = {
            **target,
            "id": "control:wrong-vocal-" + track,
            "start_ms": source["start_ms"],
            "end_ms": source["end_ms"],
        }
        if stems:
            v = vocals[source["id"]]
            case.update(
                mix_pcm=case["pcm"],
                mix_sha256=case["audio_sha256"],
                pcm=v["pcm"],
                audio_sha256=v["audio_sha256"],
                stereo_sha256=v["stereo_sha256"],
            )
        result.append(case)
    return result


def validate_result(case, result):
    for key in ("id", "snapshot", "start_ms", "end_ms"):
        if case[key] != result[key]:
            raise ValueError("Changed source or crop identity.")
    if "mix_pcm" in result:
        if (
            result["mix_pcm"] != case["pcm"]
            or result["mix_sha256"] != case["audio_sha256"]
        ):
            raise ValueError("Separated audio belongs to another recording.")
    else:
        ensemble.same_evidence(case, result)
    if [u["raw_span"] for u in result["units"]] != [
        w["raw_span"] for w in case["words"]
    ]:
        raise ValueError("Changed original word denominator or source anchors.")


def fallback(
    cases,
    baseline,
    vocals,
    phonetic=None,
    regional=False,
    raw_supported=False,
    coherent=False,
):
    baseline = ensemble.evidence_by_id(baseline)
    vocals = ensemble.evidence_by_id(vocals)
    phonetic = ensemble.evidence_by_id(phonetic) if phonetic is not None else None
    if set(baseline) != set(vocals) or set(vocals) != {c["id"] for c in cases}:
        raise ValueError("Missing or extra fallback cases.")
    results = []
    for case in cases:
        b, v = baseline[case["id"]], vocals[case["id"]]
        validate_result(case, b)
        validate_result(case, v)
        evidence = None
        if phonetic is not None:
            p = phonetic[case["id"]]
            ensemble.same_evidence(v, p)
            validate_result(case, p)
            evidence = p["units"]
        if (regional or raw_supported or coherent) and evidence is None:
            raise ValueError("Extended repair requires independent phonetic evidence.")
        recover = repair_regions if regional else recover_gaps
        candidates = (
            supported_raw(v, evidence, case["end_ms"] - case["start_ms"])
            if raw_supported
            else v["units"]
        )
        units = (
            recover(b["units"], candidates, evidence)
            if not coherent or coherent_line(candidates, evidence)
            else [dict(u) for u in b["units"]]
        )
        results.append({**identity(case), "units": units})
    return results


def compare(cases, baseline, trial):
    baseline = ensemble.evidence_by_id(baseline)
    trial = ensemble.evidence_by_id(trial)
    if set(baseline) != set(trial) or set(trial) != {c["id"] for c in cases}:
        raise ValueError("Missing or extra comparison cases.")
    totals = defaultdict(Counter)
    for case in cases:
        b, r = baseline[case["id"]], trial[case["id"]]
        validate_result(case, b)
        validate_result(case, r)
        track = (
            case["id"].split(":")[0]
            if not case["id"].startswith("control:")
            else case["id"]
        )
        counts = totals[track]
        for old, new in zip(b["units"], r["units"], strict=True):
            before = 0 <= old["start_ms"] < old["end_ms"]
            after = 0 <= new["start_ms"] < new["end_ms"]
            counts["source_words"] += 1
            counts["baseline_retained"] += before
            counts["trial_raw_intervals"] += after
            counts["trial_retained"] += after and new.get("mean_probability", 1) >= 0.3
            counts["gained_raw"] += after and not before
            counts["lost_raw"] += before and not after
            counts["shared_raw"] += before and after
            counts["changed_baseline_intervals"] += (
                before
                and after
                and (
                    old["start_ms"] != new["start_ms"] or old["end_ms"] != new["end_ms"]
                )
            )
            counts["both_boundaries_within_200ms"] += agree(old, new)
        for raw in r.get("raw_units", []):
            counts["reason_" + raw["reason"]] += 1
    return dict(totals)


def spoken(word):
    text = word["hiragana"].strip()
    if text == "は" and word["romaji"] == "wa":
        return "わ"
    if text == "へ" and word["romaji"] == "e":
        return "え"
    if text == "を" and word["romaji"] == "o":
        return "お"
    return text


def output(value, path):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
    path.chmod(0o600)


def stem_path(directory, case):
    # A control may reuse a song's track ID with different audio. Key by verified
    # recording bytes so silence cannot overwrite the real song's stem.
    digest = case["audio_sha256"]
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Invalid recording digest.")
    return directory / f"{digest}.pcm"


def crop(case):
    return ensemble.read_pcm(case)


def tifa(
    cases,
    archive,
    penalty,
    double_sokuon,
    score_pronunciations=False,
    expand_vowels=False,
):
    import numpy as np

    sys.path.insert(0, str(ROOT / "tifa"))
    import tifa_helper
    from g2p.converters.japanese import JapaneseKanaConverter
    from tifa_helper import Aligner, prepare_model

    with contextlib.redirect_stdout(io.StringIO()):
        folder = prepare_model(archive)
        aligner = Aligner(folder)
        if double_sokuon:
            aligner.converters["ja"] = JapaneseKanaConverter(
                str(folder / "dictionaries/japanese_dict_full.txt"),
                double_written_sokuon=True,
            )
    original = aligner.backend.align
    captured = {}
    retain = tifa_helper.retain_interval

    def inspect_word(spans, indices, similarity, agreement, length_ms):
        result = retain(spans, indices, similarity, agreement, length_ms)
        found = spans[indices]
        valid = indices.size and np.all(found[:, 1] > found[:, 0])
        scores = (
            [float(similarity[a:b, i].mean()) for i, (a, b) in zip(indices, found)]
            if valid
            else []
        )
        mean = float(np.mean(scores)) if scores else None
        raw_start = int(found[0, 0] * 10) if valid else -1
        raw_end = int(found[-1, 1] * 10) if valid else -1
        reason = (
            "retained"
            if result[0] >= 0
            else "incomplete"
            if not valid
            else "token_agreement"
            if not math.isfinite(agreement) or agreement < 0.99
            else "duration"
            if raw_end - raw_start < 80
            else "bounds"
            if raw_start < 0 or raw_end > length_ms
            else "similarity"
        )
        captured.setdefault("words", []).append(
            {
                "start_ms": raw_start,
                "end_ms": raw_end,
                "agreement": agreement,
                "mean_similarity": mean
                if mean is not None and math.isfinite(mean)
                else None,
                "reason": reason,
            }
        )
        return result

    tifa_helper.retain_interval = inspect_word

    def inspect(*args, **kwargs):
        kwargs["skip_penalty"] = penalty
        value = original(*args, **kwargs)
        captured["spans"] = value.spans[0].cpu().numpy()
        captured["probability"] = value.token_probability[0].cpu().numpy()
        return value

    aligner.backend.align = inspect
    results = []
    for case in cases:
        samples = crop(case)
        start = time.perf_counter()
        targets = ensemble.alignment_targets(case["words"])
        with contextlib.redirect_stdout(io.StringIO()):
            units = aligner.align(
                samples,
                targets,
                score_pronunciations=score_pronunciations,
                expand_vowels=expand_vowels,
            )
            _, supported = aligner.words(targets, expand_vowels=expand_vowels)
        raw_units = [
            {
                "raw_span": u["raw_span"],
                "start_ms": -1,
                "end_ms": -1,
                "reason": "unsupported" if i not in supported else "silence",
            }
            for i, u in enumerate(units)
        ]
        for index, diagnostic in zip(supported, captured.get("words", [])):
            raw_units[index].update(diagnostic)
        results.append(
            {
                **identity(case),
                "units": units,
                "raw_units": raw_units,
                "unsupported_words": len(targets) - len(supported),
                "pronunciation_selection": "acoustic"
                if score_pronunciations
                else "first",
                "expand_vowels": expand_vowels,
                "skipped_phonemes": int(
                    np.sum(captured["spans"][:, 1] <= captured["spans"][:, 0])
                )
                if "spans" in captured
                else 0,
                "seconds": time.perf_counter() - start,
            }
        )
        captured.clear()
        print(
            json.dumps(
                {"case": case["id"], "timed": sum(u["start_ms"] >= 0 for u in units)}
            ),
            flush=True,
        )
    return results


def kim_separator(folder):
    import mlx.core as mx
    import numpy as np
    from mlx_audio.sts.models.mel_roformer import MelRoFormer, MelRoFormerConfig

    for name, expected in (
        ("model.safetensors", KIM_SHA),
        ("config.json", KIM_CONFIG_SHA),
    ):
        with (folder / name).open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() != expected:
                raise ValueError("Unverified RoFormer checkpoint or config.")
    config = MelRoFormerConfig.kim_vocal_2()
    backend = MelRoFormer(config)
    weights = backend.sanitize(dict(mx.load(str(folder / "model.safetensors"))))
    backend.load_weights(list(weights.items()), strict=True)
    mx.eval(backend.parameters())
    backend.eval()
    del weights

    def separate_audio(samples):
        size = config.chunk_size
        weight = np.hanning(size).astype(np.float32)
        result = np.zeros_like(samples, dtype=np.float32)
        denominator = np.zeros(samples.shape[-1], dtype=np.float32)
        for start, first, last in chunk_windows(samples.shape[-1], size):
            block = np.zeros((2, size), dtype=np.float32)
            local = first - start
            block[:, local : local + last - first] = samples[:, first:last]
            prediction = backend(mx.array(block[None]))
            mx.eval(prediction)
            prediction = np.asarray(prediction[0], dtype=np.float32)
            if prediction.shape != block.shape or not np.isfinite(prediction).all():
                raise ValueError("Nonfinite or wrong-sized RoFormer output.")
            weights = weight[local : local + last - first]
            result[:, first:last] += (
                prediction[:, local : local + last - first] * weights
            )
            denominator[first:last] += weights
            del prediction, block
        if np.any(denominator <= 0):
            raise ValueError("Separation did not cover every original sample.")
        return result / denominator

    return separate_audio


def separate(cases, model, directory, stereo, name="htdemucs"):
    import mlx.core as mx
    import numpy as np
    from scipy.signal import resample_poly

    os.environ["DEMUCS_MLX_CACHE_DIR"] = str(model)
    os.environ["DEMUCS_MLX_OFFLINE"] = "1"
    if name == "kim-vocal-2":
        if not stereo:
            raise ValueError(
                "RoFormer comparison requires the original stereo capture."
            )
        predict = kim_separator(model)
    else:
        from demucs_mlx.api import Separator

        separator = Separator(model="htdemucs", shifts=1, seed=0, batch_size=1)
        predict = lambda samples: separator.separate_tensor(samples)[1]["vocals"]
    directory.mkdir(parents=True, exist_ok=True)
    stems, results = {}, []
    for case in cases:
        path = Path(case["pcm"])
        if path not in stems:
            samples = np.memmap(path, dtype="<f4", mode="r")
            start = time.perf_counter()
            stereo_sha = None
            if stereo and case["id"] != "control:silence":
                source = path.with_name("stereo.pcm")
                stereo_sha = hashlib.sha256(source.read_bytes()).hexdigest()
                decoded = np.memmap(source, dtype="<f4", mode="r")
                if (
                    len(decoded) % 2
                    or abs(len(decoded) / 2 / 44100 - len(samples) / 16000) > 0.001
                ):
                    raise ValueError("Stereo capture has a different duration.")
                resampled = np.asarray(decoded.reshape(-1, 2).T)
            else:
                # A mono-only trial cannot recover discarded stereo/HF information.
                resampled = resample_poly(samples, 441, 160).astype(np.float32)[None, :]
            if name == "kim-vocal-2" and resampled.shape[0] == 1:
                resampled = np.repeat(resampled, 2, axis=0)
            vocals = resample_poly(predict(resampled).mean(axis=0), 160, 441)
            if len(vocals) < len(samples) or len(vocals) - len(samples) > 1:
                raise ValueError("Separation changed the recording duration.")
            vocals = vocals[: len(samples)].astype("<f4")
            if not np.isfinite(vocals).all():
                raise ValueError("Nonfinite separated audio.")
            destination = stem_path(directory, case)
            vocals.tofile(destination)
            destination.chmod(0o600)
            stems[path] = (
                destination,
                hashlib.sha256(destination.read_bytes()).hexdigest(),
                stereo_sha,
            )
            print(
                json.dumps(
                    {
                        "track": case["track"],
                        "separator": name,
                        "separation_seconds": time.perf_counter() - start,
                        "peak_mlx_bytes": mx.get_peak_memory(),
                    }
                ),
                flush=True,
            )
        destination, digest, stereo_sha = stems[path]
        results.append(
            {
                **case,
                "mix_pcm": str(path),
                "mix_sha256": case["audio_sha256"],
                "pcm": str(destination),
                "audio_sha256": digest,
                "stereo_sha256": stereo_sha,
            }
        )
    return results


def kana(cases, model, source):
    import numpy as np
    import torch
    from transformers import Wav2Vec2Config, Wav2Vec2FeatureExtractor, Wav2Vec2Model

    sys.path.insert(0, str(source))
    from src.asr.kana_vocab import KanaVocab
    from src.asr.model import DualCTCModel
    from src.asr.phoneme_vocab import PhonemeVocab

    checkpoint = model / "best-medium-ep5-inference.pt"
    with checkpoint.open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != KANA_SHA:
            raise ValueError("Unverified kana checkpoint.")
    config = Wav2Vec2Config.from_pretrained(model / "backbone", local_files_only=True)
    config._attn_implementation = "eager"
    kv, pv = KanaVocab(), PhonemeVocab()
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if (
        state["pretrained"] != "reazon-research/japanese-wav2vec2-large"
        or state["inter_ctc_layer"] != 12
    ):
        raise ValueError("Wrong kana model architecture.")
    backend = DualCTCModel(
        Wav2Vec2Model(config), kv.size, pv.size, config.hidden_size, 12
    )
    backend.load_state_dict(state["model_state_dict"], strict=True)
    del state
    # FP16 produced nonfinite activations on real singing in the MPS smoke run.
    backend.float().to("mps").eval()
    extractor = Wav2Vec2FeatureExtractor(
        sampling_rate=16000, do_normalize=True, return_attention_mask=True
    )
    results = []
    for case in cases:
        samples = crop(case)
        start = time.perf_counter()
        inputs = extractor(
            samples,
            sampling_rate=16000,
            return_tensors="pt",
            return_attention_mask=True,
        )
        with torch.inference_mode():
            logits = backend(
                inputs.input_values.to("mps", torch.float32),
                attention_mask=inputs.attention_mask.to("mps"),
            )
        probabilities = logits["kana_logits"].float().log_softmax(-1)[0].cpu().numpy()
        syllables = [list(spoken(word).replace(" ", "")) for word in case["words"]]
        supported = all(
            chars and all(c in kv.stoi for c in chars) for chars in syllables
        )
        units = [
            {
                "raw_span": w["raw_span"],
                "start_ms": -1,
                "end_ms": -1,
                "mean_probability": 0.0,
            }
            for w in case["words"]
        ]
        if supported:
            labels = [kv.stoi[c] for chars in syllables for c in chars]
            path = ctc_path(probabilities.tolist(), labels)
            if path is not None:
                path = np.array(path)
                # Wav2Vec2's convolution consumes 400 samples, strides 320 samples.
                # Use its observed sample grid, not crop-duration/frame-count scaling.
                token = 0
                for unit, chars in zip(units, syllables, strict=True):
                    frames = [
                        np.flatnonzero(path == 2 * i + 1)
                        for i in range(token, token + len(chars))
                    ]
                    if all(len(f) for f in frames):
                        scores = [
                            float(np.exp(probabilities[f, labels[i]]).mean())
                            for f, i in zip(
                                frames, range(token, token + len(chars)), strict=True
                            )
                        ]
                        unit.update(
                            start_ms=int(frames[0][0] * 20),
                            end_ms=int(frames[-1][-1] * 20 + 25),
                            mean_probability=sum(scores) / len(scores),
                        )
                    token += len(chars)
        results.append(
            {
                **identity(case),
                "kana": kv.decode(logits["kana_logits"][0].argmax(-1).cpu().tolist()),
                "phonemes": pv.decode(
                    logits["phoneme_logits"][0].argmax(-1).cpu().tolist()
                ),
                "units": units,
                "supported": supported,
                "seconds": time.perf_counter() - start,
                "peak_mps_bytes": torch.mps.driver_allocated_memory(),
            }
        )
        print(json.dumps({"case": case["id"], "kana_trial": "complete"}), flush=True)
    return results


def hsmm(cases, model):
    import pyshiro
    from pyshiro.labels import segments_to_phoneme_intervals
    from pyshiro.phonemes import kana_to_phonemes

    backend = pyshiro.load_hsmm(model / "checkpoint/pyshiro-jp-v2.hsmm")
    phonemap = pyshiro.load_phonemap(model / "checkpoint/pyshiro-jp-v2_phonemap.json")
    table = pyshiro.load_table()
    results = []
    for case in cases:
        samples = crop(case)
        start = time.perf_counter()
        units = [
            {"raw_span": w["raw_span"], "start_ms": -1, "end_ms": -1}
            for w in case["words"]
        ]
        with contextlib.redirect_stdout(io.StringIO()):
            spellings = [spoken(w).replace(" ", "") for w in case["words"]]
            # Do not let upstream silently discard unsupported characters/English.
            valid = all(
                s and all("ぁ" <= c <= "ゖ" or c == "ー" for c in s) for s in spellings
            )
            if valid:
                phones = [kana_to_phonemes(s, table) for s in spellings]
                flattened = ["pau", *(p for word in phones for p in word), "pau"]
                features = pyshiro.extract_mfcc(samples, 16000)
                states = pyshiro.build_state_sequence(
                    flattened, phonemap, len(features[0])
                )
                try:
                    segments, score = pyshiro.forced_align_2pass(
                        backend, features, states
                    )
                    intervals = segments_to_phoneme_intervals(flattened, segments)
                    index = 1
                    for unit, word in zip(units, phones, strict=True):
                        if word:
                            unit.update(
                                start_ms=intervals[index][0] * 5,
                                end_ms=intervals[index + len(word) - 1][1] * 5,
                            )
                        index += len(word)
                except RuntimeError:
                    valid, score = False, None
            else:
                score = None
        results.append(
            {
                **identity(case),
                "units": units,
                "supported": valid,
                "log_likelihood": float(score)
                if score is not None and math.isfinite(score)
                else None,
                "seconds": time.perf_counter() - start,
            }
        )
        print(json.dumps({"case": case["id"], "hsmm_trial": "complete"}), flush=True)
    return results


def mms_timing(cases, model, directory):
    """Independent singing-trained romaji CTC evidence, with exact sample grid."""
    import numpy as np

    records = ensemble.mms(cases, model, directory)
    vocabulary = json.loads((model / "vocab.json").read_text())
    results = []
    for case, record in zip(cases, records, strict=True):
        ensemble.same_evidence(case, record)
        with np.load(record["posterior"]) as data:
            logp, blank = data["logp"], int(data["blank"])
        labels = ensemble.ctc_labels(case["words"], vocabulary)
        units = [
            {
                "raw_span": w["raw_span"],
                "start_ms": -1,
                "end_ms": -1,
                "mean_probability": 0.0,
            }
            for w in case["words"]
        ]
        path = ctc_path(logp.tolist(), labels, blank) if labels else None
        if path is not None:
            path, token = np.array(path), 0
            for word, unit in zip(case["words"], units, strict=True):
                spelling = [
                    c for c in word["romaji"].lower() if c in vocabulary and c.isalpha()
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
                token += len(spelling) + 1  # The CTC word-delimiter has its own label.
        results.append({**identity(case), "units": units, "romaji": record["romaji"]})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=(
            "tifa",
            "separate",
            "kana",
            "hsmm",
            "mms",
            "compare",
            "fallback",
            "controls",
            "wrong-controls",
        ),
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--stem-directory", type=Path)
    parser.add_argument("--stereo", action="store_true")
    parser.add_argument(
        "--separator", choices=("htdemucs", "kim-vocal-2"), default="htdemucs"
    )
    parser.add_argument("--skip-penalty", type=float, default=0.5)
    parser.add_argument("--double-sokuon", action="store_true")
    parser.add_argument("--score-pronunciations", action="store_true")
    parser.add_argument("--expand-vowels", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--trial", type=Path)
    parser.add_argument("--posteriors", type=Path)
    parser.add_argument("--phonetic", type=Path)
    parser.add_argument("--stems", action="store_true")
    parser.add_argument("--regional", action="store_true")
    parser.add_argument("--raw-supported", action="store_true")
    parser.add_argument("--coherent", action="store_true")
    args = parser.parse_args()
    os.environ.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        NUMBA_CACHE_DIR="/private/tmp/RomajiTIFA-numba-v1",
    )
    cases = json.loads(args.input.read_text())
    ensemble.verify_recordings(cases)
    start = time.perf_counter()
    if args.stage == "controls":
        result = controls(cases, args.output.parent)
    elif args.stage == "wrong-controls":
        result = wrong_controls(
            cases,
            json.loads(args.baseline.read_text()),
            json.loads(args.trial.read_text()),
            args.stems,
        )
    elif args.stage == "tifa":
        result = tifa(
            cases,
            args.archive,
            args.skip_penalty,
            args.double_sokuon,
            args.score_pronunciations,
            args.expand_vowels,
        )
    elif args.stage == "separate":
        result = separate(
            cases, args.model, args.stem_directory, args.stereo, args.separator
        )
    elif args.stage == "kana":
        result = kana(cases, args.model, args.source)
    elif args.stage == "hsmm":
        result = hsmm(cases, args.model)
    elif args.stage == "mms":
        result = mms_timing(cases, args.model, args.posteriors)
    elif args.stage == "compare":
        result = compare(
            cases,
            json.loads(args.baseline.read_text()),
            json.loads(args.trial.read_text()),
        )
    else:
        result = fallback(
            cases,
            json.loads(args.baseline.read_text()),
            json.loads(args.trial.read_text()),
            json.loads(args.phonetic.read_text()) if args.phonetic else None,
            args.regional,
            args.raw_supported,
            args.coherent,
        )
    output(result, args.output)
    print(
        json.dumps(
            {
                "stage": args.stage,
                "seconds": time.perf_counter() - start,
                "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
