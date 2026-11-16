"""Bounded Google audio research transport. Never imports local inference models."""

import base64
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

MODELS = (
    "gemini-3.5-transcribe",
    "gemini-4-hydrogen",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
)
PROMPT = (
    "Transcribe only the audible sung words in their original languages. "
    "Preserve repetitions. Omit uncertain words. Do not identify the song, "
    "translate, complete lyrics from memory, or invent timestamps."
)
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def key_from_file(path):
    """Read only this credential; never execute an env file or print its contents."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key and path is not None:
        for line in path.read_text().splitlines():
            name, sep, value = line.strip().removeprefix("export ").partition("=")
            if sep and name.strip() == "GEMINI_API_KEY":
                key = value.strip().strip("\"'")
    if not key or any(c.isspace() for c in key):
        raise ValueError("GEMINI_API_KEY is absent or invalid.")
    return key


def request_body(model, audio, *, timestamps=False):
    if model not in MODELS or (timestamps and model != MODELS[0]):
        raise ValueError("Unsupported model or timestamp configuration.")
    body = {
        "model": model,
        "store": False,
        "input": [
            {
                "type": "audio",
                "data": base64.b64encode(audio).decode("ascii"),
                "mime_type": "audio/wav",
            }
        ],
    }
    if model == MODELS[0]:
        mode = {"type": "verbatim"}
        if timestamps:
            mode["timestamp_granularities"] = ["word"]
        body["generation_config"] = {"transcription_config": {"mode": mode}}
    else:
        body["input"].insert(0, {"type": "text", "text": PROMPT})
        body["generation_config"] = {"temperature": 0, "max_output_tokens": 4096}
    encoded = json.dumps(body, allow_nan=False).encode()
    if len(encoded) > 19_000_000:
        raise ValueError("Inline request exceeds the bounded payload size.")
    return encoded


def post(encoded, key, *, retry=True):
    request = urllib.request.Request(
        ENDPOINT,
        data=encoded,
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                return {"status": "oversized_response"}
            # Error echoes and payloads must never persist a credential.
            safe = raw.decode("utf-8").replace(key, "[REDACTED]")
            return {"status": "received", "response": json.loads(safe)}
    except urllib.error.HTTPError as error:
        # Deliberately omit arbitrary provider error text and request headers.
        result = {
            "status": "http_error",
            "http_status": error.code,
            "retry_after": (error.headers.get("Retry-After") or "").replace(
                key, "[REDACTED]"
            ),
        }
        error.close()
        if retry and error.code in (500, 502, 503, 504):
            try:
                delay = float(result["retry_after"] or 5)
            except ValueError:
                return result
            if math.isfinite(delay) and 0 <= delay <= 30:
                time.sleep(delay)
                return {**post(encoded, key, retry=False), "retried_after": result}
        return result
    except (OSError, ValueError):
        return {"status": "transport_or_decode_error"}


def seconds(value):
    if isinstance(value, str) and value.endswith("s"):
        value = value[:-1]
    if isinstance(value, bool):
        raise TypeError("Invalid word offset.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite word offset.")
    return number


def candidates(response, duration):
    """Normalize observed annotations only. Missing confidence stays absent."""
    if not isinstance(response, dict) or response.get("status") != "completed":
        raise ValueError("Incomplete or blocked interaction.")
    steps = response.get("steps", [])
    if not isinstance(steps, list):
        raise TypeError("Malformed interaction steps.")
    texts, words = [], []
    previous_end = 0
    for step in steps:
        if not isinstance(step, dict):
            raise TypeError("Malformed interaction step.")
        if step.get("finish_reason") not in (None, "STOP", "stop", "end_turn"):
            raise ValueError("Generation did not finish normally.")
        if step.get("type") != "model_output":
            continue
        contents = step.get("content", [])
        if not isinstance(contents, list):
            raise TypeError("Malformed model content.")
        for content in contents:
            if not isinstance(content, dict):
                raise TypeError("Malformed model content.")
            if content.get("type") == "text":
                texts.append(content.get("text", ""))
            annotations = content.get("annotations", [])
            if not isinstance(annotations, list):
                raise TypeError("Malformed annotations.")
            for annotation in annotations:
                if not isinstance(annotation, dict):
                    raise TypeError("Malformed annotation.")
                if annotation.get("type") != "word_info":
                    continue
                start = seconds(annotation["start_offset"])
                end = seconds(annotation["end_offset"])
                text = annotation.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("Missing observed word text.")
                if not previous_end <= start < end <= duration:
                    raise ValueError("Invalid word interval.")
                words.append({"text": text, "start": start, "end": end})
                previous_end = end
    return {"text": "\n".join(texts), "words": words, "confidence": None}


def save(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(value, handle, ensure_ascii=False, allow_nan=False)


def utc_now():
    return datetime.now(UTC).isoformat()
