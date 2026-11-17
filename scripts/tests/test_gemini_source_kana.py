import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "source_kana", SCRIPTS / "gemini_source_kana.py"
)
kana = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kana)


class SourceKanaTests(unittest.TestCase):
    def case(self):
        return {
            "id": "request-one",
            "context": ["青い地球に"],
            "source_text": "地球",
            "words": [
                {
                    "id": "owner-one",
                    "text": "地球",
                    "raw_span": [0, 6],
                    "baseline_target": "ちきゅう",
                    "baseline_timing": {"start_ms": 12, "end_ms": 312},
                }
            ],
        }

    def reply(self, reading):
        return {
            "request_id": "request-one",
            "readings": [{"id": "owner-one", "text": "地球", "kana": reading}],
        }

    def test_changed_reading_requires_checks_without_changing_source_or_clocks(self):
        case = self.case()
        before = copy.deepcopy(case)
        row = kana.validate_readings(self.reply("ほし"), case)[0]
        self.assertTrue(row["requires_acoustic_check"])
        self.assertTrue(row["requires_phrase_realignment"])
        self.assertEqual(row["baseline_timing"], before["words"][0]["baseline_timing"])
        self.assertEqual(case, before)
        self.assertEqual(row["status"], "unverified_text_reading")

    def test_unchanged_or_abstained_reading_preserves_timing_target(self):
        for reading in (None, "ちきゅう"):
            with self.subTest(reading=reading):
                row = kana.validate_readings(self.reply(reading), self.case())[0]
                self.assertFalse(row["requires_phrase_realignment"])

    def test_new_acoustic_target_preserves_owner_and_removes_dictionary_shadow(self):
        original = [
            {
                "raw_span": [0, 6],
                "text": "ちきゅう",
                "romaji": "chikyuu",
                "pronunciation": "ちきゅー",
            }
        ]
        before = copy.deepcopy(original)
        reading = kana.validate_readings(self.reply("ほし"), self.case())
        targets, changed = kana.reading_targets(
            original, reading, lambda value: {"hiragana": value, "romaji": "hoshi"}
        )
        self.assertEqual(changed, 1)
        self.assertEqual(
            targets,
            [
                {
                    "raw_span": [0, 6],
                    "text": "ほし",
                    "romaji": "hoshi",
                    "pronunciation": None,
                }
            ],
        )
        self.assertEqual(original, before)
        reading[0]["raw_span"] = [0, 3]
        with self.assertRaises(ValueError):
            kana.reading_targets(
                original,
                reading,
                lambda _: self.fail("Must reject owner mismatch before conversion"),
            )

    def test_response_cannot_change_owner_text_count_or_inject_timing(self):
        wrongs = []
        for field, value in (
            ("id", "other-owner"),
            ("text", "世界"),
            ("start_ms", 100),
        ):
            reply = self.reply("ほし")
            reply["readings"][0][field] = value
            wrongs.append(reply)
        reply = self.reply("ほし")
        reply["readings"] *= 2
        wrongs.append(reply)
        wrongs.append({"request_id": "request-one", "readings": []})
        wrongs.append({**self.reply("ほし"), "confidence": 1})
        for reply in wrongs:
            with self.subTest(reply=reply), self.assertRaises(ValueError):
                kana.validate_readings(reply, self.case())

    def test_non_hiragana_and_empty_suggestions_are_rejected(self):
        for reading in ("ホシ", "星", "hoshi", "", True):
            with self.subTest(reading=reading), self.assertRaises(ValueError):
                kana.validate_readings(self.reply(reading), self.case())

    def test_stale_request_duplicate_owner_and_reordering_are_rejected(self):
        case = self.case()
        case["source_text"] = "地球に"
        case["words"].append(
            {
                "id": "owner-two",
                "text": "に",
                "raw_span": [6, 9],
                "baseline_target": "に",
            }
        )
        first = self.reply("ほし")["readings"][0]
        second = {"id": "owner-two", "text": "に", "kana": "に"}
        for request_id, readings in (
            ("stale", [first, second]),
            (case["id"], [first, first]),
            (case["id"], [second, first]),
        ):
            with (
                self.subTest(request_id=request_id, readings=readings),
                self.assertRaises(ValueError),
            ):
                kana.validate_readings(
                    {"request_id": request_id, "readings": readings}, case
                )

    def test_prompt_excludes_existing_reading_and_all_timing(self):
        body = json.loads(kana.request_bytes(self.case()))
        payload = json.loads(body["input"][1]["text"])
        self.assertEqual(payload["words"], [{"id": "owner-one", "text": "地球"}])
        self.assertNotIn("ちきゅう", body["input"][1]["text"])
        self.assertNotIn("start_ms", body["input"][1]["text"])
        self.assertEqual(payload["lyrics"], ["青い地球に"])

    def test_optional_hints_are_provisional_and_do_not_lock_a_reading(self):
        case = self.case()
        case["reading_hints"] = [
            {
                "id": "owner-one",
                "kana": "ちきゅう",
                "status": "provisional_local_acoustic_support",
            }
        ]
        plain = json.loads(kana.request_bytes(case))
        hinted = json.loads(kana.request_bytes(case, "gemini-3.5-flash-lite", True))
        self.assertNotIn(
            "provisional_reading_hints", json.loads(plain["input"][1]["text"])
        )
        self.assertEqual(
            json.loads(hinted["input"][1]["text"])["provisional_reading_hints"],
            case["reading_hints"],
        )
        self.assertIn("not ground truth", hinted["input"][0]["text"])
        self.assertTrue(
            kana.validate_readings(self.reply("ほし"), case)[0][
                "requires_acoustic_check"
            ]
        )
        with self.assertRaises(ValueError):
            kana.request_bytes(case, "gemini-4-carbon", True)

    def test_empty_hint_arm_has_identical_request_bytes(self):
        self.assertEqual(
            kana.request_bytes(self.case()),
            kana.request_bytes(self.case(), include_hints=True),
        )

    def test_quota_guard_runs_before_credentials_or_network(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            manifest = root / "requests.json"
            manifest.write_text(
                json.dumps({"not_before_utc": "2099-01-01T00:00:00+00:00"})
            )
            (root / "requests-fingerprint.json").write_text(
                json.dumps({"sha256": kana.sha(manifest)})
            )
            with (
                patch.object(kana, "post") as send,
                patch.object(kana, "key_from_file") as key,
            ):
                with self.assertRaisesRegex(ValueError, "retry window"):
                    kana.run(SimpleNamespace(output=root))
                send.assert_not_called()
                key.assert_not_called()
            manifest.write_text("{}")
            with self.assertRaisesRegex(ValueError, "manifest changed"):
                kana.run(SimpleNamespace(output=root))

    def test_quota_deadline_preserves_provider_wait(self):
        deadline = kana.quota_deadline(
            {
                "http_status": 429,
                "utc": "2026-11-17T00:00:00+00:00",
                "retry_after": "3600",
            }
        )
        self.assertEqual(deadline, datetime(2026, 11, 17, 1, tzinfo=UTC))
        with self.assertRaises(ValueError):
            kana.require_ready(
                deadline.isoformat(), datetime(2026, 11, 17, 0, tzinfo=UTC)
            )

    def test_completed_structured_reply_is_cached_without_a_second_api_call(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            case = self.case()
            case["request_sha256"] = kana.hashlib.sha256(
                kana.request_bytes(case)
            ).hexdigest()
            manifest = root / "requests.json"
            manifest.write_text(
                json.dumps(
                    {
                        "not_before_utc": "2000-01-01T00:00:00+00:00",
                        "model": kana.MODEL,
                        "runner_sha256": kana.sha(Path(kana.__file__)),
                        "transport_sha256": kana.sha(
                            Path(kana.__file__).with_name("google_audio_api.py")
                        ),
                        "cases": [case],
                    }
                )
            )
            (root / "requests-fingerprint.json").write_text(
                json.dumps({"sha256": kana.sha(manifest)})
            )
            response = {
                "status": "received",
                "response": {
                    "status": "completed",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [
                                {"type": "text", "text": json.dumps(self.reply("ほし"))}
                            ],
                        }
                    ],
                },
            }
            with (
                patch.object(kana, "post", return_value=response) as send,
                patch.object(kana, "key_from_file", return_value="synthetic-key"),
                patch("builtins.print"),
            ):
                args = SimpleNamespace(
                    output=root, free_project_confirmed=True, env_file=None
                )
                kana.run(args)
                kana.run(args)
                send.assert_called_once()
            receipt = json.loads((root / "request-one.json").read_text())
            self.assertEqual(receipt["status"], "received")
            self.assertTrue(receipt["readings"][0]["requires_phrase_realignment"])
            self.assertEqual(
                receipt["readings"][0]["baseline_timing"],
                case["words"][0]["baseline_timing"],
            )
            child = root / "hint-arm"
            child.mkdir(mode=0o700)
            data = json.loads(manifest.read_text())
            data["include_hints"] = True
            (child / "requests.json").write_text(json.dumps(data))
            (child / "requests-fingerprint.json").write_text(
                json.dumps({"sha256": kana.sha(child / "requests.json")})
            )
            with (
                patch.object(kana, "post") as send,
                patch.object(kana, "key_from_file", return_value="synthetic-key"),
                patch("builtins.print"),
            ):
                kana.run(
                    SimpleNamespace(
                        output=child,
                        free_project_confirmed=True,
                        env_file=None,
                        reuse_output=root,
                    )
                )
                send.assert_not_called()
            reused = json.loads((child / "request-one.json").read_text())
            self.assertEqual(
                reused["reused_observation_sha256"], kana.sha(root / "request-one.json")
            )
            self.assertEqual(reused["readings"], receipt["readings"])
            failure = {
                **receipt,
                "status": "http_error",
                "http_status": 429,
                "retry_after": "30",
                "utc": "2000-01-01T00:00:00+00:00",
            }
            (root / "request-one.json").write_text(json.dumps(failure))
            args = SimpleNamespace(
                output=root,
                free_project_confirmed=True,
                env_file=None,
                continue_service_errors=True,
            )
            with (
                patch.object(kana, "post") as send,
                patch.object(kana, "key_from_file", return_value="synthetic-key"),
            ):
                with self.assertRaises(ValueError):
                    kana.run(args)
                send.assert_not_called()
                failure["http_status"] = 503
                (root / "request-one.json").write_text(json.dumps(failure))
                kana.run(args)
                send.assert_not_called()
                self.assertEqual(
                    json.loads((root / "request-one.json").read_text())["status"],
                    "http_error",
                )
