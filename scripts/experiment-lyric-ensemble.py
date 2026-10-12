"""Local-only ensemble experiment. Private outputs never modify app lyric documents."""

import argparse
import contextlib
import hashlib
import io
import json
import math
import os
import re
import resource
import subprocess
import sys
import time
from pathlib import Path


def canonical(text):
    return re.sub(r"[^a-zぁ-ゖー]", "", text.lower())


def ctc_labels(words, vocabulary):
    if any(
        c.isalpha() and c not in vocabulary
        for word in words
        for c in word["romaji"].lower()
    ):
        return None
    spellings = [
        "".join(c for c in w["romaji"].lower() if c in vocabulary and c.isalpha())
        for w in words
    ]
    if not spellings or not all(spellings) or "|" not in vocabulary:
        return None
    return [vocabulary[c] for c in "|".join(spellings)]


def choose_candidate(candidates):
    """Require independent transcript consensus plus acoustic support for replacement."""
    baseline = candidates[0]
    eligible = [
        c
        for c in candidates[1:]
        if (
            len(set(c["asr_models"])) >= 2
            and c["unsupported_words"] == 0
            # Padding can include the next sung word. A longer transcript is not
            # extra coverage of the original line; boundary repair needs separate proof.
            and c["total_words"] == baseline["total_words"]
            and c["ctc_log_probability"] is not None
            and baseline["ctc_log_probability"] is not None
            and math.isfinite(c["ctc_log_probability"])
            and math.isfinite(baseline["ctc_log_probability"])
            and c["ctc_log_probability"] > baseline["ctc_log_probability"] + 5
            and c["timed_words"] >= baseline["timed_words"]
            and c["timed_words"] / max(1, c["total_words"]) >= 0.9
            and c["rms"] >= 0.0001
        )
    ]
    return max(eligible, key=lambda c: c["ctc_log_probability"], default=baseline)


def converter_signature(executable):
    hello = {"protocol_version": 1, "request_id": 0, "command": "hello"}
    value = json.loads(
        subprocess.run(
            [str(executable)],
            input=json.dumps(hello) + "\n",
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
    )
    if value.get("protocol_version") != 1 or value.get("request_id") != 0:
        raise ValueError("Invalid converter handshake.")
    return value["conversion_signature"]


def conversion_requests(requests, executable):
    if not requests:
        return []
    output = subprocess.run(
        [str(executable)],
        input="\n".join(json.dumps(r) for r in requests) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    values = [json.loads(s) for s in output.stdout.splitlines()]
    if len(values) != len(requests):
        raise ValueError("Missing or extra converter responses.")
    for request, value in zip(requests, values, strict=True):
        for key in (
            "protocol_version",
            "request_id",
            "track_id",
            "snapshot_id",
            "occurrence_id",
            "override_revision",
        ):
            if request[key] != value.get(key):
                raise ValueError("Mismatched converter response identity.")
        if (
            value.get("conversion_signature")
            != request["expected_conversion_signature"]
        ):
            raise ValueError("Changed converter signature.")
    return values


def converted_words(value):
    if any(
        not w["raw_span"]
        and any(
            c.isalnum()
            for c in value["romaji"]
            .encode()[w["output_span"][0] : w["output_span"][1]]
            .decode()
        )
        for w in value["words"]
    ):
        raise ValueError(
            "Unmapped lexical word would make the comparison denominator incomplete."
        )
    return [
        {
            "raw_span": w["raw_span"],
            "expected_text": w["expected_text"],
            "hiragana": (
                value["hiragana"]
                .encode()[w["hiragana_span"][0] : w["hiragana_span"][1]]
                .decode()
                if w["hiragana_span"]
                else "？"
            ),
            "romaji": value["romaji"]
            .encode()[w["output_span"][0] : w["output_span"][1]]
            .decode(),
        }
        for w in value["words"]
        if w["raw_span"]
    ]


def prepare_cases(recordings, executable):
    """Use the captured, pinned source and recording zero; skip instrumental lines."""
    signature = converter_signature(executable)
    cases, requests = [], []
    for document_path in sorted(recordings.glob("*/document.json")):
        document = json.loads(document_path.read_text())
        source = document["bundles"][document["active"]]["snapshot"]
        pcm = document_path.with_name("audio.pcm")
        digest = hashlib.sha256(pcm.read_bytes()).hexdigest()
        duration = pcm.stat().st_size // 64
        occurrences = source["occurrences"]
        for i, line in enumerate(occurrences):
            if not any(c.isalnum() for c in line["raw_line"]):
                continue
            start, end = cue_crop(line, occurrences, document["delay_ms"], duration)
            cases.append(
                {
                    "id": f"{document['track_id']}:{line['id']}",
                    "track": document["track_id"],
                    "occurrence": line["id"],
                    "pcm": str(pcm),
                    "audio_sha256": digest,
                    "snapshot": source["id"],
                    "start_ms": start,
                    "end_ms": end,
                    "raw_line": line["raw_line"],
                }
            )
            requests.append(
                {
                    "protocol_version": 1,
                    "request_id": len(requests) + 1,
                    "track_id": document["track_id"],
                    "snapshot_id": source["id"],
                    "occurrence_id": line["id"],
                    "override_revision": document["revision"],
                    "expected_conversion_signature": signature,
                    "raw_line": line["raw_line"],
                    "overrides": [],
                }
            )
    for case, value in zip(
        cases, conversion_requests(requests, executable), strict=True
    ):
        case["words"] = converted_words(value)
    return cases


def cue_crop(line, occurrences, delay, duration):
    """Mirror Rust crops: same-time repeats use the next strictly later cue."""
    if line["start_ms"] is None:
        raise ValueError(
            "Untimed lyric source; obtain a timed candidate before comparing line crops."
        )
    cue = line["start_ms"] + delay
    next_ms = min(
        (
            other["start_ms"] + delay
            for other in occurrences
            if other["start_ms"] is not None and other["start_ms"] + delay > cue
        ),
        default=duration,
    )
    start = max(0, cue - 500)
    end = min(duration, next_ms + 300, start + 30000)
    if end <= start:
        raise ValueError("Invalid source cue crop.")
    return start, end


def evidence_by_id(cases):
    result = {c["id"]: c for c in cases}
    if len(result) != len(cases):
        raise ValueError("Duplicate evidence IDs.")
    return result


def same_evidence(case, value):
    for key in ("pcm", "audio_sha256", "snapshot", "start_ms", "end_ms"):
        if value[key] != case[key]:
            raise ValueError("Mismatched audio or lyric evidence.")


def verify_recordings(cases):
    checked = {}
    for case in cases:
        path = Path(case["pcm"])
        if path not in checked:
            with path.open("rb") as stream:
                checked[path] = hashlib.file_digest(stream, "sha256").hexdigest()
        if checked[path] != case["audio_sha256"]:
            raise ValueError("Recording changed after evidence was captured.")


def alignment_targets(words):
    # Preserve unknown kana as unsupported words rather than silently inflating coverage.
    return [
        {
            "raw_span": w["raw_span"],
            "text": "".join(ch for ch in w["hiragana"] if ch.isalnum())
            or w["expected_text"],
            "romaji": w["romaji"],
        }
        for w in words
    ]


def read_pcm(case):
    import numpy as np

    data = np.memmap(case["pcm"], dtype="<f4", mode="r")
    start, end = case["start_ms"] * 16, case["end_ms"] * 16
    if not 0 <= start < end <= len(data) or end - start > 480000:
        raise ValueError("Invalid recording crop.")
    samples = np.array(data[start:end])
    if case.get("silence"):
        samples[:] = 0
    return samples


def qwen(cases, model):
    import torch
    from transformers import AutoProcessor, Qwen3ASRForConditionalGeneration

    torch.set_num_threads(4)
    torch.manual_seed(0)
    processor = AutoProcessor.from_pretrained(model, local_files_only=True)
    network = (
        Qwen3ASRForConditionalGeneration.from_pretrained(
            model,
            dtype=torch.float16,
            attn_implementation="eager",
            local_files_only=True,
        )
        .to("mps")
        .eval()
    )
    results = []
    peak = 0
    for case in cases:
        started = time.monotonic()
        inputs = processor.apply_transcription_request(
            audio=read_pcm(case),
            language="ja",
            processor_kwargs={"sampling_rate": 16000},
        ).to("mps", torch.float16)
        with torch.inference_mode():
            generated = network.generate(**inputs, max_new_tokens=256, do_sample=False)
        tokens = generated[0, inputs["input_ids"].shape[1] :]
        eos = network.generation_config.eos_token_id
        eos = eos if isinstance(eos, list) else [eos]
        truncated = int(tokens[-1]) not in eos
        text = processor.decode(tokens, return_format="transcription_only")
        result = {
            **case,
            "transcript": text,
            "truncated": truncated,
            "asr_seconds": time.monotonic() - started,
        }
        results.append(result)
        peak = max(peak, torch.mps.driver_allocated_memory())
        print(
            json.dumps(
                {
                    "case": case["id"],
                    "seconds": result["asr_seconds"],
                    "truncated": truncated,
                }
            ),
            flush=True,
        )
    print(
        json.dumps(
            {
                "mps_observed_peak_bytes": peak,
                "process_peak_rss_bytes": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
            }
        )
    )
    return results


def mms(cases, model, posterior_dir):
    import numpy as np
    import torch
    from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC

    torch.set_num_threads(4)
    config = json.loads((model / "processor_config.json").read_text())
    processor = Wav2Vec2FeatureExtractor(**config["feature_extractor"])
    network = (
        Wav2Vec2ForCTC.from_pretrained(model, local_files_only=True).to("mps").eval()
    )
    vocabulary = json.loads((model / "vocab.json").read_text())
    inv = {i: c for c, i in vocabulary.items()}
    blank = network.config.pad_token_id
    posterior_dir.mkdir(exist_ok=True, parents=True)
    results, peak = [], 0
    for case in cases:
        started = time.monotonic()
        inputs = processor(read_pcm(case), sampling_rate=16000, return_tensors="pt").to(
            "mps"
        )
        with torch.inference_mode():
            logp = network(**inputs).logits[0].float().log_softmax(-1).cpu().numpy()
        greedy = logp.argmax(-1).tolist()
        collapsed = [n for i, n in enumerate(greedy) if i == 0 or n != greedy[i - 1]]
        text = "".join(inv[n] for n in collapsed if n != blank).replace("|", " ")
        filename = hashlib.sha256(case["id"].encode()).hexdigest() + ".npz"
        np.savez_compressed(posterior_dir / filename, logp=logp, blank=blank)
        results.append(
            {
                **{
                    k: case[k]
                    for k in (
                        "id",
                        "pcm",
                        "audio_sha256",
                        "snapshot",
                        "start_ms",
                        "end_ms",
                    )
                },
                "romaji": text,
                "posterior": str(posterior_dir / filename),
            }
        )
        peak = max(peak, torch.mps.driver_allocated_memory())
        print(
            json.dumps({"case": case["id"], "seconds": time.monotonic() - started}),
            flush=True,
        )
    print(
        json.dumps(
            {
                "mps_observed_peak_bytes": peak,
                "process_peak_rss_bytes": resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
            }
        )
    )
    return results


def convert_variants(cases, whisper, qwen_results, executable):
    # Exact audio/source/crop identity is required before combining model evidence.
    by_model = {
        "whisper": evidence_by_id(whisper),
        "qwen": evidence_by_id(qwen_results),
    }
    rows, requests = [], []
    sig = converter_signature(executable)
    for case in cases:
        row = {
            **case,
            "candidates": [
                {"text": case["raw_line"], "words": case["words"], "asr_models": []}
            ],
        }
        for model, values in by_model.items():
            value = values[case["id"]]
            same_evidence(case, value)
            if value.get("truncated") or not value["transcript"].strip():
                continue
            row["candidates"].append(
                {"text": value["transcript"], "asr_models": [model]}
            )
            requests.append(
                {
                    "protocol_version": 1,
                    "request_id": len(requests) + 1,
                    "track_id": "synthetic",
                    "snapshot_id": "ensemble",
                    "occurrence_id": 0,
                    "override_revision": 0,
                    "expected_conversion_signature": sig,
                    "raw_line": value["transcript"],
                    "overrides": [],
                }
            )
        rows.append(row)
    converted = iter(conversion_requests(requests, executable))
    for row in rows:
        unique = {
            canonical(
                " ".join(w["hiragana"] for w in row["candidates"][0]["words"])
            ): row["candidates"][0]
        }
        for c in row["candidates"][1:]:
            value = next(converted)
            c["words"] = converted_words(value)
            key = canonical(" ".join(w["hiragana"] for w in c["words"]))
            if key in unique:
                unique[key]["asr_models"] += c["asr_models"]
            elif key:
                unique[key] = c
        row["candidates"] = list(unique.values())
    return rows


def acoustics(rows, mms_results, archive, mms_model):
    import numpy as np
    import torch

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tifa"))
    import tifa_helper

    with contextlib.redirect_stdout(io.StringIO()):
        aligner = tifa_helper.Aligner(tifa_helper.prepare_model(archive))
    vocabulary = json.loads((mms_model / "vocab.json").read_text())
    posteriors = evidence_by_id(mms_results)
    results = []
    for row in rows:
        samples = read_pcm(row)
        same_evidence(row, posteriors[row["id"]])
        posterior = np.load(posteriors[row["id"]]["posterior"])
        logp = torch.from_numpy(posterior["logp"][:, None, :].copy())
        blank = int(posterior["blank"])
        rms = float(np.sqrt(np.mean(samples**2)))
        for c in row["candidates"]:
            targets = alignment_targets(c["words"])
            with contextlib.redirect_stdout(io.StringIO()):
                _, indices = aligner.words(targets)
                units = aligner.align(samples, targets)
            c["units"] = units
            c["unsupported_words"] = len(targets) - len(indices)
            c["total_words"] = len(targets)
            c["timed_words"] = sum(u["start_ms"] >= 0 for u in units)
            c["rms"] = rms
            labels = ctc_labels(c["words"], vocabulary)
            if labels:
                loss = torch.nn.functional.ctc_loss(
                    logp,
                    torch.tensor(labels, dtype=torch.long),
                    input_lengths=torch.tensor([len(logp)]),
                    target_lengths=torch.tensor([len(labels)]),
                    blank=blank,
                    reduction="none",
                    zero_infinity=False,
                )
                score = -float(loss[0])
                c["ctc_log_probability"] = score if np.isfinite(score) else None
            else:
                c["ctc_log_probability"] = None
        winner = choose_candidate(row["candidates"])
        result = {**row, "selected": row["candidates"].index(winner)}
        results.append(result)
        print(
            json.dumps(
                {
                    "case": row["id"],
                    "candidates": len(row["candidates"]),
                    "selected": result["selected"],
                    "timed": winner["timed_words"],
                    "words": winner["total_words"],
                }
            ),
            flush=True,
        )
    return results


def score_readings(cases, archive):
    """Compare supplied pronunciation alternatives without rewriting source boundaries."""
    import numpy as np
    import torch

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tifa"))
    import tifa_helper
    from g2p.encoding import encode_paths
    from inference.backend import SpectrogramContext
    from scipy.signal import resample_poly

    with contextlib.redirect_stdout(io.StringIO()):
        aligner = tifa_helper.Aligner(tifa_helper.prepare_model(archive))
    results = []
    for case in cases:
        samples = read_pcm(case)
        if float(np.sqrt(np.mean(samples**2))) < 0.0001:
            results.append({"id": case["id"], "withheld": "silence"})
            continue
        words, indices = aligner.words(alignment_targets(case["words"]))
        if indices != list(range(len(case["words"]))):
            raise ValueError("Reading experiment contains unsupported source words.")
        for alternative in case["reading_alternatives"]:
            index = alternative["word"]
            source = case["words"][index]
            if alternative["raw_span"] != source["raw_span"]:
                raise ValueError("Alternative changed its original-word anchor.")
            proposed, supported = aligner.words(
                [
                    {
                        **source,
                        "text": alternative["hiragana"],
                        "romaji": alternative["romaji"],
                    }
                ]
            )
            if supported != [0] or proposed[0].language != words[index].language:
                raise ValueError("Unsupported pronunciation alternative.")
            words[index].readings.extend(proposed[0].readings)
        encoded, _, _ = encode_paths(
            words, aligner.vocabulary, "raise", languages=["ja", "en"]
        )
        tensors = {k: torch.from_numpy(v)[None].to("mps") for k, v in encoded.items()}
        resampled = resample_poly(samples, 3, 1).astype(np.float32)
        with torch.inference_mode(), contextlib.redirect_stdout(io.StringIO()):
            spec = aligner.backend.spectrogram(
                torch.from_numpy(resampled.copy())[None],
                torch.tensor([len(resampled) / 48000]),
            )
            spec = SpectrogramContext(spec.features.to("mps"), spec.mask.to("mps"))
            score = aligner.backend.score(
                spec,
                paths=tensors["paths"],
                words=tensors["words"],
                candidates=tensors["candidates"],
                unit="word",
            )
        results.append(
            {
                "id": case["id"],
                "choices": score.choices[0].cpu().tolist(),
                "scores": score.scores[0].cpu().tolist(),
            }
        )
        print(
            json.dumps({"case": case["id"], "reading_comparison": "complete"}),
            flush=True,
        )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage", choices=["prepare", "qwen", "mms", "compare", "acoustics", "readings"]
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--whisper", type=Path)
    parser.add_argument("--qwen", type=Path)
    parser.add_argument("--romanizer", type=Path)
    parser.add_argument("--posteriors", type=Path)
    parser.add_argument("--mms", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["NUMBA_CACHE_DIR"] = str(Path("/private/tmp/RomajiTIFA-numba-v1"))
    cases = [] if args.stage == "prepare" else json.loads(args.input.read_text())
    verify_recordings(cases)
    if args.stage == "prepare":
        result = prepare_cases(args.input, args.romanizer)
    elif args.stage == "qwen":
        result = qwen(cases, args.model)
    elif args.stage == "mms":
        result = mms(cases, args.model, args.posteriors)
    elif args.stage == "compare":
        result = convert_variants(
            cases,
            json.loads(args.whisper.read_text()),
            json.loads(args.qwen.read_text()),
            args.romanizer,
        )
    elif args.stage == "readings":
        result = score_readings(cases, args.archive)
    else:
        result = acoustics(
            cases, json.loads(args.mms.read_text()), args.archive, args.model
        )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    args.output.chmod(0o600)


if __name__ == "__main__":
    main()
