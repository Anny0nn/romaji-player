"""Closed reading evidence must retain its source word and counterfactual identity."""

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "reading_replay", SCRIPTS / "evaluate-reading-contrasts.py"
)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def score(word):
    return {
        "token_log_probabilities": [word, -1],
        "source_token_indices": [[0]],
    }


class ClosedReadingReplay(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        job = {
            "track": "example",
            "snapshot": "frozen-source",
            "crops": [
                {
                    "occurrence": 2,
                    "raw_line": "天の",
                    "start_sample": 0,
                    "end_sample": 16000,
                    "targets": [{"raw_span": [0, 3]}, {"raw_span": [3, 6]}],
                }
            ],
        }
        job_path = self.root / "job.json"
        job_path.write_text(json.dumps(job))
        common = {
            "source_job": str(job_path),
            "source_job_sha256": replay.digest(job_path),
            "source_track": "example",
            "source_snapshot": "frozen-source",
            "source_occurrence": 2,
            "source_raw_span": [0, 3],
            "source_expected_text": "天",
            "selected_dictionary_kana": "てん",
            "audio": {"first_sample": 0, "last_sample": 16000},
            "wrong_audio": {
                "status": "available",
                "first_sample": 16000,
                "last_sample": 32000,
            },
            "targets": [{"raw_span": [0, 6], "text": "てん"}],
        }
        self.cases = [
            {**common, "id": "current", "candidate_kana": "てん", "text": "てんの"},
            {
                **common,
                "id": "alternative",
                "candidate_kana": "あま",
                "text": "あまの",
                "targets": [{"raw_span": [0, 6], "text": "あま"}],
            },
        ]
        self.rows = {
            c["id"]: {
                "observations": {
                    "real": score(-10 if c["id"] == "current" else -1),
                    "silence": score(-11),
                    "wrong_verse": score(-11),
                }
            }
            for c in self.cases
        }

    def run_replay(self):
        return replay.replay({"cases": self.cases}, self.rows)

    def test_authentic_source_group_produces_only_private_nomination(self):
        result = self.run_replay()
        self.assertEqual(result["counts"], {"conditional_hypothesis": 1})
        self.assertFalse(result["saved_app_data_changed"])

    def test_adjacent_word_cannot_change_between_alternatives(self):
        self.cases[1]["text"] = "あまが"
        with self.assertRaisesRegex(ValueError, "another word"):
            self.run_replay()

    def test_cue_unit_preserves_source_checks_without_assigning_a_word_score(self):
        for row in self.rows.values():
            for observation in row["observations"].values():
                observation["source_token_indices"] = [None]
        self.assertEqual(self.run_replay()["counts"], {"unowned_competitor": 1})
        result = replay.replay({"cases": self.cases}, self.rows, unit="cue")
        self.assertEqual(result["counts"], {"whole_cue_hypothesis": 1})
        self.assertEqual(result["verification_unit"], "cue")
        self.cases[1]["text"] = "あまが"
        with self.assertRaisesRegex(ValueError, "another word"):
            replay.replay({"cases": self.cases}, self.rows, unit="cue")

    def test_wrong_verse_is_identical_for_every_competing_reading(self):
        self.cases[1]["wrong_audio"] = {
            "first_sample": 32000,
            "last_sample": 48000,
        }
        with self.assertRaisesRegex(ValueError, "waveform"):
            self.run_replay()

    def test_changed_original_source_and_crop_fail_before_ranking(self):
        old = copy.deepcopy(self.cases)
        self.cases[1]["source_snapshot"] = "refreshed-source"
        with self.assertRaisesRegex(ValueError, "source job"):
            self.run_replay()
        self.cases = old
        self.cases[1]["audio"] = {"first_sample": 100, "last_sample": 16100}
        with self.assertRaisesRegex(ValueError, "audio crop"):
            self.run_replay()

    def test_closed_output_tampering_is_detected(self):
        identity = self.root / "identity.json"
        identity.write_text(json.dumps({"reference_labels_read": False}))
        row = self.root / "case.json"
        row.write_text(json.dumps({"id": "word"}))
        closed = {
            "identity_sha256": replay.digest(identity),
            "records": [{"id": "word", "file": row.name, "sha256": replay.digest(row)}],
        }
        (self.root / "complete.json").write_text(json.dumps(closed))
        self.assertEqual(set(replay.read_closed(self.root)[1]), {"word"})
        row.write_text(json.dumps({"id": "changed"}))
        with self.assertRaisesRegex(ValueError, "Changed or external"):
            replay.read_closed(self.root)


if __name__ == "__main__":
    unittest.main()
