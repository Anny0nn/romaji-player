"""Derived vocal audio must retain the complete original Rust context identity."""

import copy
import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location(
    "vocal_context_evidence",
    Path(__file__).resolve().parents[1] / "evaluate-vocal-contexts.py",
)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class VocalContextEvidence(unittest.TestCase):
    def test_separator_metadata_does_not_change_the_audio_only_asr_case(self):
        output = {
            "path": "/private/lead.pcm",
            "sha256": "audio-identity",
            "encoding": "pcm",
            "first_sample": 0,
            "last_sample": 48000,
        }
        expected = {"id": "lead-context", **output}
        self.assertEqual(evidence.derived_audio_case("lead-context", output), expected)
        self.assertEqual(
            evidence.derived_audio_case(
                "lead-context", {**output, "sample_rate": 16000, "channels": 1}
            ),
            expected,
        )
        for extra in (
            {"sample_rate": 44100},
            {"channels": 2},
            {"channels": True},
            {"source_lyrics": "not audio-only"},
        ):
            with self.assertRaises(ValueError):
                evidence.derived_audio_case("lead-context", {**output, **extra})

    def fixture(self):
        window = {"first_sample": 16000, "last_sample": 64000, "occurrences": [4, 5]}
        job = {
            "context": copy.deepcopy(window),
            "original_stereo": {
                "path": "/private/recording.pcm",
                "sha256": "recording-identity",
                "sample_rate": 44100,
                "channels": 2,
                "encoding": "interleaved_f32le",
            },
        }
        output = {"first_sample": 0, "last_sample": 48000, "encoding": "pcm"}
        song = {"stereo": "/private/recording.pcm"}
        return job, output, window, song

    def test_zero_based_pcm_is_only_valid_with_exact_original_envelope(self):
        arguments = self.fixture()
        evidence.check_context(*arguments, "recording-identity")
        for field, replacement in (
            ("first_sample", 1),
            ("first_sample", False),
            ("last_sample", 47999),
            ("encoding", "wav"),
        ):
            job, output, window, song = self.fixture()
            output[field] = replacement
            with self.assertRaises(ValueError):
                evidence.check_context(job, output, window, song, "recording-identity")

    def test_changed_original_context_or_recording_is_not_an_extra_view(self):
        for change in (
            "occurrences",
            "bounds",
            "path",
            "hash",
            "sample_rate",
            "channels",
            "encoding",
        ):
            job, output, window, song = self.fixture()
            if change == "occurrences":
                job["context"]["occurrences"] = [4, 6]
            elif change == "bounds":
                job["context"].update(first_sample=16001, last_sample=64001)
            else:
                key = "sha256" if change == "hash" else change
                job["original_stereo"][key] = {"sample_rate": 16000, "channels": 1}.get(
                    change, "changed"
                )
            with self.assertRaises(ValueError):
                evidence.check_context(job, output, window, song, "recording-identity")

    def test_pcm_window_hash_is_source_authenticated_and_origin_sensitive(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.pcm"
            payload = bytes(range(24))
            source.write_bytes(payload)
            source_sha = hashlib.sha256(payload).hexdigest()
            cache = {}

            cropped = evidence.raw_pcm_window_sha(source, source_sha, 1, 4, cache)
            self.assertEqual(cropped, hashlib.sha256(payload[4:16]).hexdigest())
            self.assertNotEqual(cropped, source_sha)
            self.assertNotEqual(cropped, hashlib.sha256(payload[0:12]).hexdigest())
            self.assertEqual(
                evidence.raw_pcm_window_sha(source, source_sha, 2, 5, cache),
                hashlib.sha256(payload[8:20]).hexdigest(),
            )
            self.assertEqual(len(cache), 1)

            derived = Path(directory) / "derived.pcm"
            derived.write_bytes(payload[4:16])
            derived_sha = hashlib.sha256(payload[4:16]).hexdigest()
            self.assertEqual(
                evidence.verify_derived_pcm(derived, 3, derived_sha), derived_sha
            )
            with self.assertRaises(ValueError):
                evidence.reject_duplicate_waveform(derived_sha, [cropped])
            evidence.reject_duplicate_waveform("different-waveform", [cropped])

            derived.write_bytes(payload[4:15])
            with self.assertRaises(ValueError):
                evidence.verify_derived_pcm(
                    derived, 3, hashlib.sha256(payload[4:15]).hexdigest()
                )

            source.write_bytes(payload[:-1])
            with self.assertRaises(ValueError):
                evidence.raw_pcm_window_sha(
                    source,
                    hashlib.sha256(payload[:-1]).hexdigest(),
                    1,
                    4,
                    {},
                )
