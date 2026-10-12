"""Tentative, source-anchored reading repairs; Rust owns final admission/storage."""

import copy
import gc
import hashlib
import json
import os
import subprocess
import zipfile

from reading_policy import rank, verify
from singing_phonemes import kana_phones

SINGING_FILES = {
    "config.json": "a7c43dcd9857c9ad1e2c1591932eeac781b918865a5c2657f208b5c04c4ad7a2",
    "model.safetensors": "f8c271f0149df02d7bdb70916f530633462d65ee2bbf0c0d9c59cc7ded12abc0",
    "phoneme_vocab.json": "4e96b35f058685aa1ac63b1c9e1cc386fa75d85ede5d55997fbbac6e7ec932bb",
}
LIMIT = 65536


class ConversionRejected(ValueError):
    """The helper rejected this input; optional ASR proposals may be withheld."""


def source_text(text, span):
    a, b = span
    if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(text.encode()):
        raise ValueError("Invalid reading source boundary.")
    return text.encode()[a:b].decode()


class Converter:
    def __init__(self, executable):
        environment = os.environ.copy()
        environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        self.process = subprocess.Popen(
            [str(executable)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
        )
        try:
            self.signature = self.exchange(
                {"protocol_version": 1, "command": "hello", "request_id": 0}
            )["conversion_signature"]
        except Exception:
            self.close()
            raise

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process.stdout.close()

    def exchange(self, request):
        data = json.dumps(request, ensure_ascii=False).encode() + b"\n"
        if len(data) > LIMIT:
            raise ValueError("Reading conversion request exceeds limit.")
        self.process.stdin.write(data)
        self.process.stdin.flush()
        data = self.process.stdout.readline(LIMIT + 1)
        if not data.endswith(b"\n") or len(data) > LIMIT:
            raise ValueError("Reading converter exceeded reply limit.")
        response = json.loads(data)
        # Rejections deliberately omit lyric text and most identity fields. Only
        # a matching protocol/request ID can classify one as an input rejection.
        if response.get("error") == "invalid_request":
            if response.get("protocol_version") != 1 or response.get(
                "request_id"
            ) != request.get("request_id"):
                raise ValueError("Unmatched reading conversion rejection.")
            raise ConversionRejected("Reading converter rejected the input.")
        for key in (
            "request_id",
            "track_id",
            "snapshot_id",
            "occurrence_id",
            "override_revision",
        ):
            if key in request and response.get(key) != request[key]:
                raise ValueError("Stale reading conversion.")
        if response.get("error") or response.get("protocol_version") != 1:
            raise ValueError("Reading converter failed.")
        if response.get("conversion_signature") != request.get(
            "expected_conversion_signature", response.get("conversion_signature")
        ):
            raise ValueError("Reading converter changed.")
        return response

    def canonical(self, kana, template):
        request = {
            **template,
            "command": "canonical",
            "track_id": "independent-transcript",
            "raw_line": kana,
            "overrides": [],
        }
        return self.exchange(request)["canonical_reading"]

    def convert(self, request, candidates=False):
        request = {**request, "command": "candidates" if candidates else "convert"}
        if request["expected_conversion_signature"] != self.signature:
            raise ValueError("Frozen converter is incompatible.")
        return self.exchange(request)


def singing_model(folder):
    from filelock import FileLock
    from transformers import HubertForCTC

    archive = folder / "singing/model_safetensors.zip"
    target = folder / "singing/verified-v1"
    target.mkdir(parents=True, exist_ok=True)
    with (
        FileLock(str(target / "setup.lock"), timeout=60),
        zipfile.ZipFile(archive) as zip,
    ):
        for name, expected in SINGING_FILES.items():
            path = target / name
            if path.is_file():
                with path.open("rb") as file:
                    if hashlib.file_digest(file, "sha256").hexdigest() == expected:
                        continue
            data = zip.read(name)
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError("Singing recognizer integrity check failed.")
            temporary = path.with_suffix(".part")
            temporary.write_bytes(data)
            os.replace(temporary, path)
    config = json.loads((target / "config.json").read_text())
    # This pinned release adds ambiguity-aware TRAINING loss only. No adapters,
    # layer mixing, pitch features or LoRA modify its inference graph.
    if config.get("singing_hubert") != {
        "ambiguity_ctc": {"alt_weight": 0.35, "enable": True}
    } or config.get("use_weighted_layer_sum"):
        raise ValueError("Unsupported singing recognizer architecture.")
    model, info = HubertForCTC.from_pretrained(
        target, local_files_only=True, output_loading_info=True
    )
    if info["missing_keys"] or info["unexpected_keys"] or info.get("mismatched_keys"):
        raise ValueError("Incomplete singing recognizer checkpoint.")
    return model.to("mps").eval(), json.loads(
        (target / "phoneme_vocab.json").read_text()
    )


def singing_evidence(samples, crops, folder, progress_path):
    import torch
    from refinement_helper import progress, release

    progress(progress_path, "Checking sung pronunciation · independent model")
    model, vocabulary = singing_model(folder)
    result = []
    for n, (_, first, last, _) in enumerate(crops):
        progress(progress_path, f"Checking pronunciation · line {n + 1}/{len(crops)}")
        with torch.inference_mode():
            logp = (
                model(torch.from_numpy(samples[first:last].copy())[None].to("mps"))
                .logits[0]
                .float()
                .log_softmax(-1)
                .cpu()
                .numpy()
            )
        result.append((logp, model.config.pad_token_id))
    del model
    release()
    return result, vocabulary


def transcribe(samples, folder, progress_path, name):
    import mlx.core as mx
    import mlx_whisper
    import numpy as np
    from mlx_whisper.transcribe import ModelHolder
    from refinement_helper import progress, release

    if np.sqrt(np.mean(np.square(samples.astype(np.float64)))) < 0.0001:
        return []
    progress(progress_path, f"Checking lyric text · {name}")
    mx.set_memory_limit(10 * 1024**3)
    mx.set_cache_limit(512 * 1024**2)
    try:
        value = mlx_whisper.transcribe(
            samples,
            path_or_hf_repo=str(folder / "whisper"),
            language="ja",
            task="transcribe",
            temperature=0.0,
            condition_on_previous_text=False,
            initial_prompt=None,
            verbose=None,
            word_timestamps=True,
        )
        return value["segments"]
    finally:
        ModelHolder.model = None
        ModelHolder.model_path = None
        gc.collect()
        release()


def transcript_for_crop(segments, first, last):
    words = [
        w
        for s in segments
        for w in s.get("words", [])
        if first / 16000 <= (w["start"] + w["end"]) / 2 < last / 16000
        and w.get("probability", 0) >= 0.5
    ]
    return "".join(w["word"] for w in words).strip()


def mapped_candidates(words, observed):
    """Align phonemes through exact neighboring envelopes, tolerating token splits.

    Ambiguous repeats, edges and incomplete envelopes are withheld. The source
    and transcript can have different token counts; one correction can group up
    to four complete original words, with its kana highlighted atomically.
    """
    from difflib import SequenceMatcher

    def stream(values):
        phones, boundaries = [], [0]
        for value in values:
            part = kana_phones(value["text"], value["romaji"])
            if not part:
                return None, None
            phones.extend(part)
            boundaries.append(len(phones))
        return phones, boundaries

    old, old_bounds = stream(words)
    new, new_bounds = stream(observed)
    if not old or not new:
        return []
    matcher = SequenceMatcher(None, old, new, autojunk=False)
    blocks = matcher.get_matching_blocks()
    if sum(b.size for b in blocks) / max(len(old), len(new)) < 0.65:
        return []
    correspondence = {b.a + i: b.b + i for b in blocks for i in range(b.size)}
    proposals, seen = [], set()
    for kind, first, last, _, _ in matcher.get_opcodes():
        if kind != "replace" or last - first > 16:
            continue
        a = next(
            (
                i
                for i in range(len(words))
                if old_bounds[i] <= first < old_bounds[i + 1]
            ),
            None,
        )
        b = next(
            (
                i + 1
                for i in range(len(words))
                if old_bounds[i] < last <= old_bounds[i + 1]
            ),
            None,
        )
        if a is None or b is None or a == 0 or b == len(words) or b - a > 4:
            continue
        left, right = old_bounds[a], old_bounds[b]
        # Two stable phones immediately on BOTH sides prevent wrong-verse matches.
        if (
            left < 2
            or right + 1 >= len(old)
            or any(
                i not in correspondence for i in [left - 2, left - 1, right, right + 1]
            )
        ):
            continue
        start, end = correspondence[left - 1] + 1, correspondence[right]
        if start not in new_bounds or end not in new_bounds or start >= end:
            continue
        x, y = new_bounds.index(start), new_bounds.index(end)
        if y - x > 4 or new[start:end] == old[left:right]:
            continue
        # The same surrounding phonemes appearing twice make attachment ambiguous.
        context = old[left - 2 : left] + new[start:end] + old[right : right + 2]
        hits = sum(
            new[i : i + len(context)] == context
            for i in range(len(new) - len(context) + 1)
        )
        if hits != 1 or (a, b) in seen:
            continue
        seen.add((a, b))
        proposals.append(
            {
                "first": a,
                "last": b,
                "hiragana": " ".join(w["text"] for w in observed[x:y]),
                "romaji": " ".join(w["romaji"] for w in observed[x:y]),
            }
        )
    return proposals


def output_words(value):
    result = []
    for word in value["words"]:
        if word["raw_span"] and word["hiragana_span"]:
            result.append(
                {
                    "raw_span": word["raw_span"],
                    "text": source_text(value["hiragana"], word["hiragana_span"]),
                    "romaji": source_text(value["romaji"], word["output_span"]),
                    "protected": word["override_id"] is not None,
                }
            )
    return result


def measurements(views):
    return [
        {
            "gain_milli": round(v["gain"] * 1000),
            "margin_milli": round(v["margin"] * 1000),
            "probability_ppm": round(v["probability"] * 1_000_000),
            "context_ppm": round(v["context"] * 1_000_000),
        }
        for v in views
    ]


def complete_envelope(original, converted, span):
    selected = [
        w
        for w in converted["words"]
        if w["raw_span"] and w["raw_span"][0] < span[1] and w["raw_span"][1] > span[0]
    ]
    if (
        not 1 <= len(selected) <= 4
        or selected[0]["raw_span"][0] != span[0]
        or selected[-1]["raw_span"][1] != span[1]
    ):
        return False
    cursor = span[0]
    for word in selected:
        a, b = word["raw_span"]
        if (
            word["mapping_status"] != "mapped"
            or word["override_id"] is not None
            or a < cursor
            or b > span[1]
        ):
            return False
        if a > cursor and not source_text(original, [cursor, a]).isspace():
            return False
        cursor = b
    return True


def transcript_matches(segments, first, last, targets, request, converter):
    """Unconvertible ASR data cannot abort timing of the selected source lyrics."""
    text = transcript_for_crop(segments, first, last)
    if not text or len(text.encode()) > 8192:
        return []
    query = {
        **request,
        "track_id": "independent-transcript",
        "raw_line": text,
        "overrides": [],
    }
    try:
        observed = output_words(converter.convert(query))
    except ConversionRejected:
        return []
    matches = []
    for match in mapped_candidates(targets, observed):
        try:
            match.update(converter.canonical(match["hiragana"], request))
        except ConversionRejected:
            continue
        matches.append(match)
    return matches


def propose(
    inputs,
    crops,
    converter,
    mms_views,
    independent,
    vocabulary,
    independent_vocabulary,
    transcripts,
):
    requests = {r["occurrence_id"]: r for r in inputs["requests"]}
    protected = inputs["protected"]
    rows = []
    conflicts = set()
    baseline_choices = {}
    for line_index, (occurrence, first, last, targets) in enumerate(crops):
        request = requests[occurrence]
        value = converter.convert(request, candidates=True)
        original = request["raw_line"]
        groups = {
            tuple(g["raw_span"]): g["candidates"]
            for g in value.get("reading_candidates", [])
        }
        observations = []
        for segments in transcripts:
            observations.append(
                transcript_matches(segments, first, last, targets, request, converter)
            )
        observed = observations[0] if observations else []
        units = []
        for i, target in enumerate(targets):
            key = tuple(target["raw_span"])
            alternatives = list(groups.get(key, []))
            match = next(
                (p for p in observed if p["first"] == i and p["last"] == i + 1), None
            )
            if match and not any(
                c["hiragana"] == match["hiragana"] for c in alternatives
            ):
                alternatives.append({k: match[k] for k in ("hiragana", "romaji")})
            if alternatives:
                units.append((i, i + 1, targets, alternatives, match is not None))
        for match in observed:
            a, b = match["first"], match["last"]
            if b - a <= 1:
                continue
            group = {
                "raw_span": [targets[a]["raw_span"][0], targets[b - 1]["raw_span"][1]],
                "text": " ".join(w["text"] for w in targets[a:b]),
                "romaji": " ".join(w["romaji"] for w in targets[a:b]),
            }
            merged = [*targets[:a], group, *targets[b:]]
            units.append(
                (a, b, merged, [{k: match[k] for k in ("hiragana", "romaji")}], True)
            )
        for a, b, words, alternatives, grounded in units:
            target = words[a]
            raw_span = target["raw_span"]
            if not complete_envelope(original, value, raw_span):
                continue
            if any(
                p["occurrence_id"] == occurrence
                and p["raw_span"][0] < raw_span[1]
                and p["raw_span"][1] > raw_span[0]
                for p in protected
            ):
                continue
            if any(
                w["override_id"] is not None
                and w["raw_span"]
                and w["raw_span"][0] < raw_span[1]
                and w["raw_span"][1] > raw_span[0]
                for w in value["words"]
            ):
                continue
            selected = rank(
                words,
                a,
                alternatives,
                [v[line_index] for v in mms_views],
                vocabulary,
                include_baseline=True,
            )
            if not selected:
                continue
            key = original, tuple(raw_span)
            if selected["baseline"] and all(
                v["margin"] >= 8 and v["probability"] >= 0.45 and v["context"] >= 0.5
                for v in selected["views"]
            ):
                baseline_choices[key] = selected["hiragana"]
            if not selected["acoustic_pass"]:
                continue
            matching = next(
                (
                    p
                    for p in observed
                    if p["first"] == a
                    and p["last"] == b
                    and p["hiragana"] == selected["hiragana"]
                ),
                None,
            )
            verification = verify(
                words,
                a,
                selected,
                alternatives,
                *independent[line_index],
                independent_vocabulary,
                transcript_supported=grounded and matching is not None,
            )
            if not verification or not verification.pop("supported"):
                continue
            expected = source_text(original, raw_span)
            entry = {
                "occurrence_id": occurrence,
                "raw_line": original,
                "raw_span": raw_span,
                "expected_text": expected,
                "hiragana": selected["hiragana"],
                "romaji": selected["romaji"],
                "views": measurements(selected["views"]),
                "verification": verification,
            }
            same = [
                r
                for r in rows
                if r["raw_line"] == original and r["raw_span"] == raw_span
            ]
            if any(r["hiragana"] != entry["hiragana"] for r in same):
                conflicts.add((original, tuple(raw_span)))
            rows.append(entry)
    # Conflicting or overlapping envelopes never get shared to repeated lines.
    result, seen = [], set()
    for row in rows:
        key = row["raw_line"], tuple(row["raw_span"])
        overlap = any(
            r["raw_line"] == row["raw_line"]
            and r["raw_span"] != row["raw_span"]
            and r["raw_span"][0] < row["raw_span"][1]
            and r["raw_span"][1] > row["raw_span"][0]
            for r in rows
        )
        protected_repeat = any(
            r["raw_line"] == row["raw_line"]
            and (
                any(
                    o["raw_span"][0] < row["raw_span"][1]
                    and o["raw_span"][1] > row["raw_span"][0]
                    for o in r["overrides"]
                )
                or any(
                    p["occurrence_id"] == r["occurrence_id"]
                    and p["raw_span"][0] < row["raw_span"][1]
                    and p["raw_span"][1] > row["raw_span"][0]
                    for p in protected
                )
            )
            for r in requests.values()
        )
        if (
            not protected_repeat
            and key not in conflicts
            and key not in seen
            and not overlap
            and baseline_choices.get(key, row["hiragana"]) == row["hiragana"]
        ):
            seen.add(key)
            result.append(row)
    # Kanji can carry poetic readings. This first recipe preserves their written
    # forms. Kana-only text repairs require BOTH independent transcription views.
    readings, text_repairs = [], []
    for row in result:
        expected = row["expected_text"]
        is_kana = expected and all("ぁ" <= c <= "ゖ" or c in "ー " for c in expected)
        if is_kana:
            # Text conversion is conservative: a full transcript match in both
            # views and no existing correction anywhere on that original line.
            request = requests[row["occurrence_id"]]
            line_index = next(
                i for i, c in enumerate(crops) if c[0] == row["occurrence_id"]
            )
            first, last = crops[line_index][1:3]
            supported = True
            for segments in transcripts:
                choices = transcript_matches(
                    segments, first, last, crops[line_index][3], request, converter
                )
                supported &= any(
                    p["hiragana"] == row["hiragana"]
                    and crops[line_index][3][p["first"]]["raw_span"][0]
                    == row["raw_span"][0]
                    and crops[line_index][3][p["last"] - 1]["raw_span"][1]
                    == row["raw_span"][1]
                    for p in choices
                )
            if (
                not supported
                or len(transcripts) != 2
                or any(p["occurrence_id"] == row["occurrence_id"] for p in protected)
                or request["overrides"]
            ):
                continue
            if any(r["raw_line"] == row["raw_line"] and r is not row for r in result):
                continue
            start, end = row["raw_span"]
            line = row["raw_line"].encode()
            replacement = row["hiragana"]
            changed = (line[:start] + replacement.encode() + line[end:]).decode()
            text_repairs.append(
                {
                    "occurrence_id": row["occurrence_id"],
                    "original_line": row["raw_line"],
                    "original_span": row["raw_span"],
                    "expected_text": expected,
                    "replacement": replacement,
                    "result_line": changed,
                    "result_span": [start, start + len(replacement.encode())],
                    "views": row["views"],
                    "verification": {
                        **row["verification"],
                        "transcript_supported": True,
                    },
                }
            )
        else:
            readings.append(row)
    return readings, text_repairs


def corrected_crops(inputs, crops, converter, readings, text_repairs):
    requests = {r["occurrence_id"]: r for r in inputs["requests"]}
    result, counts = [], {}
    for occurrence, first, last, _ in crops:
        request = copy.deepcopy(requests[occurrence])
        original = request["raw_line"]
        changes = [r for r in text_repairs if r["original_line"] == original]
        for row in sorted(changes, key=lambda p: p["original_span"][0], reverse=True):
            a, b = row["original_span"]
            data = request["raw_line"].encode()
            request["raw_line"] = (
                data[:a] + row["replacement"].encode() + data[b:]
            ).decode()
        for index, row in enumerate(readings):
            if row["raw_line"] == original:
                request["overrides"].append(
                    {
                        "id": f"proposal:{index}",
                        "kind": "mapping_kana",
                        "raw_span": row["raw_span"],
                        "expected_text": row["expected_text"],
                        "replacement": row["romaji"],
                        "hiragana": row["hiragana"],
                    }
                )
        converted = converter.convert(request)
        if converted["pending_overrides"]:
            raise ValueError("A verified correction could not be grouped.")
        targets = []
        for word in converted["words"]:
            if not word["raw_span"]:
                continue
            raw = source_text(request["raw_line"], word["raw_span"])
            reading = (
                source_text(converted["hiragana"], word["hiragana_span"])
                if word["hiragana_span"]
                else raw
            )
            text = "".join(
                c for c in (raw if "？" in reading else reading) if c.isalnum()
            )
            if text:
                targets.append(
                    {
                        "raw_span": word["raw_span"],
                        "text": text,
                        "romaji": source_text(converted["romaji"], word["output_span"]),
                    }
                )
        result.append((occurrence, first, last, targets))
        counts[str(occurrence)] = len(converted["words"])
    return result, counts
