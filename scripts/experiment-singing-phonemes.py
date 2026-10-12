"""Pinned, private Phonsa Japanese singing posterior/alignment experiment.

No application data is changed. Replays upstream's trained phoneme inventory,
silence probabilities and Viterbi decoder; no Whisper text decoding is used.
Adapted Phonsa code is MIT licensed; see third-party/Phonsa-LICENSE.
"""

import argparse
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
import resource
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "phonetic", ROOT / "scripts/experiment-phonetic-alignment.py"
)
phonetic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phonetic)
MODEL_SHA = "888f76e58ac8a1466f3969bf04b7c99e4d09feaf26bb5176a1e69103f07959dd"
CONFIG_SHA = "a291bd87f2a957b965d30fc97d9c7ba62c598624907eda84d8648d368a405d6f"
SOURCE_HASHES = {
    "phonsa/module/align_model.py": "78d18821d8d9b583de123535d26704ad4ac640e32ab57a03b4ab404e8bc4ef73",
    "phonsa/utils/alignment.py": "be568f291de7a611399c46cc137133f8369ecf973c879726ce69704a632b288b",
    "phonsa/phoneme_dict/roma_dict.json": "9912a9ef47857f0ddf10a099190ebf2d603f8ff57aae3b364df2f83112481060",
}


def verified(path, expected):
    with path.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != expected:
            raise ValueError(
                "Unverified singing model, vocabulary or inference source."
            )


def syllables(text, to_roma):
    """Upstream Japanese katakana2roma/split_roma, on already reviewed readings.

    Adapted from MIT Phonsa's japanese.py at 8c6abaa. This bypasses its MeCab
    kanji interpretation so the experiment preserves the original displayed words.
    """
    if not text or any(not ("ぁ" <= ch <= "ゖ" or ch in "ー ") for ch in text):
        return None
    spellings = []
    for ch in text.replace(" ", ""):
        if ch == "っ":
            spellings.append("cl")
        elif ch == "ん":
            spellings.append("N")
        elif ch == "ー":
            continue
        else:
            spelling = to_roma(chr(ord(ch) + 0x60))
            if spelling.startswith("x"):
                if not spellings:
                    return None
                spellings[-1] = spellings[-1][:-1] + spelling[1:]
            else:
                spellings.append(spelling)
    result = []
    for spelling in spellings:
        if spelling in ("cl", "N", "O", "I", "a", "i", "u", "e", "o"):
            result.append([spelling])
        elif spelling.endswith(("a", "i", "u", "e", "o")):
            consonant = spelling[:-1]
            if consonant in ("jy", "shy", "chy"):
                consonant = consonant[:-1]
            result.append([consonant, spelling[-1]])
        else:
            return None
    return result or None


def targets(words, vocabulary, to_roma):
    labels, owners, flat = [], [], []
    for owner, word in enumerate(words):
        groups = syllables(phonetic.spoken(word), to_roma)
        if not groups or any(
            p not in vocabulary or vocabulary[p] == 0 for g in groups for p in g
        ):
            return None
        for group in groups:
            tokens = [vocabulary[p] for p in group]
            # Upstream inserts its learned boundary between repeated phones
            # across syllables, not across every displayed word.
            if flat and flat[-1] == tokens[0]:
                tokens.insert(0, 39)
                owners.append(None)
                flat.append(39)
            labels.append(tokens)
            owners.extend([owner] * len(group))
            flat.extend(vocabulary[p] for p in group)
    return labels, owners, flat


def decoder(source):
    """Load only reviewed decoder functions, avoiding unrelated MIDI/ASR imports."""
    path = source / "phonsa/utils/alignment.py"
    verified(path, SOURCE_HASHES["phonsa/utils/alignment.py"])
    names = {
        "logits_to_prob",
        "perform_viterbi_ctc",
        "run_viterbi_core",
        "viterbi_loop",
    }
    parsed = ast.parse(path.read_text())
    functions = [
        n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name in names
    ]
    if {n.name for n in functions} != names:
        raise ValueError("Changed upstream decoder functions.")
    header = ast.parse(
        "from copy import deepcopy\nfrom typing import Tuple\nimport numpy as np\nimport torch\nimport torch.nn.functional as F\nfrom numba import jit\nHOP_SIZE_SECOND = 0.02\nCTC_PAD_VALUE = -100\nhparams = {}\n"
    )
    code = ast.unparse(ast.Module(body=[*header.body, *functions], type_ignores=[]))
    # Import a minimal module copied from the verified public source. No other
    # upstream statements or imports (MIDI, text ASR, Chinese dictionaries) run.
    with tempfile.TemporaryDirectory(prefix="RomajiPhonsa-decoder-") as folder:
        destination = Path(folder) / "decoder.py"
        destination.write_text(code)
        destination.chmod(0o600)
        module_spec = importlib.util.spec_from_file_location(
            "phonsa_decoder", destination
        )
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    return vars(module)


def word_intervals(words, intervals, owners, flat, probabilities, duration):
    """Keep every source word; learned boundaries never acquire a word owner."""
    units = [
        {
            "raw_span": w["raw_span"],
            "start_ms": -1,
            "end_ms": -1,
            "mean_probability": 0.0,
        }
        for w in words
    ]
    if len(intervals) != len(owners) or len(flat) != len(owners):
        return units
    for owner, unit in enumerate(units):
        indices = [i for i, value in enumerate(owners) if value == owner]
        if not indices:
            continue
        first, last = intervals[indices[0]][0], intervals[indices[-1]][1]
        if not (
            math.isfinite(first)
            and math.isfinite(last)
            and 0 <= first < last <= duration
        ):
            continue
        scores = []
        for i in indices:
            start, end = intervals[i]
            if not (math.isfinite(start) and math.isfinite(end)):
                break
            a, b = round(start / 0.02), round(end / 0.02)
            if not 0 <= a < b <= len(probabilities):
                break
            values = [float(row[flat[i]]) for row in probabilities[a:b]]
            if any(not math.isfinite(v) or not 0 <= v <= 1 for v in values):
                break
            scores.append(sum(values) / len(values))
        if len(scores) == len(indices):
            unit.update(
                start_ms=round(first * 1000),
                end_ms=round(last * 1000),
                mean_probability=sum(scores) / len(scores),
            )
    return units


def run(cases, model, source):
    import romkan
    import torch
    import yaml

    verified(model / "best_model.pt", MODEL_SHA)
    verified(model / "config.yaml", CONFIG_SHA)
    for name, digest in SOURCE_HASHES.items():
        verified(source / name, digest)
    config = yaml.safe_load((model / "config.yaml").read_text())
    if (
        config["language"] != "ja"
        or config["output_dim"] != 41
        or config["whisper_model"] != "medium"
    ):
        raise ValueError("Changed Japanese singing architecture.")
    sys.path.insert(0, str(source))
    from phonsa.module.align_model import get_model

    with contextlib.redirect_stdout(io.StringIO()):
        backend = get_model(config, device="cpu")
    state = torch.load(model / "best_model.pt", map_location="cpu", weights_only=True)
    backend.load_state_dict(state["model_state_dict"], strict=True)
    del state
    # Alignment uses only the trained encoder and phoneme head. Drop the unused
    # text decoder and sparse attention-head buffer before moving to Metal.
    backend.whisper_model.decoder = None
    backend.whisper_model.register_buffer(
        "alignment_heads", torch.empty(0), persistent=False
    )
    backend.device = "mps"
    backend.float().to("mps").eval()
    functions = decoder(source)
    vocabulary = json.loads(
        (source / "phonsa/phoneme_dict/roma_dict.json").read_text()
    )["phone_set"]
    inverse = {v: k for k, v in vocabulary.items() if k not in ("", "I", "#")}
    inverse.update({0: "#", 39: "|"})
    results = []
    for case in cases:
        samples = phonetic.crop(case)
        start = time.perf_counter()
        units = [
            {
                "raw_span": w["raw_span"],
                "start_ms": -1,
                "end_ms": -1,
                "mean_probability": 0.0,
            }
            for w in case["words"]
        ]
        target = targets(case["words"], vocabulary, romkan.to_roma)
        greedy, mean_silence = [], None
        if target is not None:
            with torch.inference_mode():
                logits, _ = backend.frame_manual_forward([samples])
            logits = logits.float().cpu()
            if not torch.isfinite(logits).all():
                raise ValueError("Nonfinite singing posteriors.")
            phone_logp, silence_logp = functions["logits_to_prob"](logits, 1.0)
            probabilities = (
                torch.cat((silence_logp, phone_logp), dim=-1).exp()[0].numpy()
            )
            mean_silence = float(probabilities[:, 0].mean())
            choices = probabilities.argmax(axis=-1)
            for i, choice in enumerate(choices):
                if i == 0 or choice != choices[i - 1]:
                    greedy.append(inverse[int(choice)])
            labels, owners, flat = target
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    intervals, _ = functions["perform_viterbi_ctc"](
                        logits, [labels], silence_alpha=1.0
                    )
                    intervals = intervals[0]
                except ValueError:
                    intervals = []
            units = word_intervals(
                case["words"],
                intervals,
                owners,
                flat,
                probabilities,
                len(samples) / 16000,
            )
        results.append(
            {
                **phonetic.identity(case),
                "units": units,
                "phonemes": greedy,
                "mean_silence": mean_silence,
                "supported": target is not None,
                "seconds": time.perf_counter() - start,
            }
        )
        print(
            json.dumps(
                {
                    "case": case["id"],
                    "supported": sum(u["mean_probability"] >= 0.3 for u in units),
                    "peak_mps_driver_bytes": torch.mps.driver_allocated_memory(),
                }
            ),
            flush=True,
        )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    os.environ.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        NUMBA_CACHE_DIR="/private/tmp/RomajiPhonsa-numba-v1",
    )
    cases = json.loads(args.input.read_text())
    phonetic.ensemble.verify_recordings(cases)
    start = time.perf_counter()
    result = run(cases, args.model, args.source)
    phonetic.output(result, args.output)
    print(
        json.dumps(
            {
                "seconds": time.perf_counter() - start,
                "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
