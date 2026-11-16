import importlib.util
import io
import json
import sys
import tempfile
import unittest
import urllib.error
import wave
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location(
    "google_audio_api", Path(__file__).resolve().parents[1] / "google_audio_api.py"
)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
MODELS, candidates, post, request_body = (
    api.MODELS,
    api.candidates,
    api.post,
    api.request_body,
)

collector_spec = importlib.util.spec_from_file_location(
    "google_collector",
    Path(__file__).resolve().parents[1] / "transcribe-google-audio.py",
)
collector = importlib.util.module_from_spec(collector_spec)
with patch.dict(sys.modules, {"google_audio_api": api}):
    collector_spec.loader.exec_module(collector)


class GoogleAudioTests(unittest.TestCase):
    def test_resume_reuses_success_and_rejects_changed_audio(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            audio = root / "audio.wav"
            with wave.open(str(audio), "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                wav.writeframes(bytes(3200))
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "cases": [
                            {
                                "id": "synthetic",
                                "path": "audio.wav",
                                "sha256": api.digest(audio.read_bytes()),
                                "origin_sample": 0,
                            }
                        ],
                    }
                )
            )
            argv = [
                "collector",
                str(manifest),
                "--output",
                str(root / "output"),
                "--model",
                MODELS[0],
                "--free-project-confirmed",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.dict(api.os.environ, {"GEMINI_API_KEY": "synthetic-key"}),
                patch.object(
                    collector,
                    "post",
                    return_value={
                        "status": "received",
                        "response": self.response(),
                    },
                ) as send,
                redirect_stdout(io.StringIO()),
            ):
                collector.main()
                collector.main()
                self.assertEqual(send.call_count, 1)
                argv[3] = str(root / "rejected")
                send.return_value = {
                    "status": "received",
                    "response": self.response(status="incomplete"),
                }
                collector.main()
                collector.main()
                rejected = root / "rejected" / (api.digest(b"synthetic") + ".json")
                self.assertEqual(
                    json.loads(rejected.read_text())["status"],
                    "invalid_or_incomplete_response",
                )
                self.assertEqual(send.call_count, 2)
                audio.write_bytes(b"changed audio")
                with (
                    patch.object(sys, "stderr", io.StringIO()),
                    self.assertRaises(SystemExit),
                ):
                    collector.main()
                self.assertEqual(send.call_count, 2)

    def response(self, annotations=None, status="completed"):
        return {
            "status": status,
            "steps": [
                {
                    "type": "model_output",
                    "content": [
                        {
                            "type": "text",
                            "text": "あ",
                            "annotations": [] if annotations is None else annotations,
                        }
                    ],
                }
            ],
        }

    def test_text_does_not_acquire_confidence_or_word_clocks(self):
        self.assertEqual(
            candidates(self.response(), 2),
            {"text": "あ", "words": [], "confidence": None},
        )

    def test_only_observed_word_annotations_supply_clocks(self):
        observed = {
            "type": "word_info",
            "text": "あ",
            "start_offset": "0s",
            "end_offset": "1.25s",
        }
        self.assertEqual(
            candidates(self.response([observed]), 2)["words"],
            [{"text": "あ", "start": 0, "end": 1.25}],
        )
        for end in ("NaNs", "infs", "0s", "3s", True):
            with self.subTest(end=end), self.assertRaises((ValueError, TypeError)):
                candidates(self.response([{**observed, "end_offset": end}]), 2)

    def test_refusal_or_partial_output_is_not_a_transcript(self):
        for status in ("failed", "in_progress", "cancelled", "incomplete"):
            with self.subTest(status=status), self.assertRaises(ValueError):
                candidates(self.response(status=status), 2)
        response = self.response()
        response["steps"][0]["finish_reason"] = "MAX_TOKENS"
        with self.assertRaises(ValueError):
            candidates(response, 2)

    def test_malformed_provider_shapes_remain_explicit_failures(self):
        for response in (
            [],
            {"status": "completed", "steps": "invalid"},
            {"status": "completed", "steps": [None]},
            {
                "status": "completed",
                "steps": [{"type": "model_output", "content": None}],
            },
            self.response(annotations="invalid"),
        ):
            with (
                self.subTest(response=response),
                self.assertRaises((ValueError, TypeError)),
            ):
                candidates(response, 2)

    def test_no_unknown_or_paid_model_and_no_invented_clock_prompt(self):
        with self.assertRaises(ValueError):
            request_body("gemini-4-carbon", b"audio")
        with self.assertRaises(ValueError):
            request_body(MODELS[1], b"audio", timestamps=True)
        self.assertNotIn(b"Transcribe only", request_body(MODELS[0], b"audio"))
        self.assertIn(b'"store": false', request_body(MODELS[1], b"audio"))

    def test_response_echo_cannot_persist_the_credential(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"echo":"test-secret"}'
        with patch.object(api.urllib.request, "urlopen", return_value=response):
            self.assertEqual(
                post(b"{}", "test-secret")["response"], {"echo": "[REDACTED]"}
            )

    def test_daily_quota_stops_without_retry(self):
        error = urllib.error.HTTPError(
            "https://example.invalid", 429, "quota", {}, None
        )
        with (
            patch.object(api.urllib.request, "urlopen", side_effect=error) as send,
            patch.object(api.time, "sleep") as sleep,
        ):
            self.assertEqual(post(b"{}", "test-secret")["http_status"], 429)
            self.assertEqual(send.call_count, 1)
            sleep.assert_not_called()

    def test_service_failure_has_one_bounded_retry(self):
        error = urllib.error.HTTPError(
            "https://example.invalid", 503, "busy", {"Retry-After": "30"}, None
        )
        with (
            patch.object(api.urllib.request, "urlopen", side_effect=error) as send,
            patch.object(api.time, "sleep") as sleep,
        ):
            self.assertEqual(post(b"{}", "test-secret")["http_status"], 503)
            self.assertEqual(send.call_count, 2)
            sleep.assert_called_once_with(30)
