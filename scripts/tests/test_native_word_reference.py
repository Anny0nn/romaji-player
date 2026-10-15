"""No source remapping or manufactured clock when raw native predictions are bad."""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_word_reference import request, validate_reply


class NativeWordReference(unittest.TestCase):
    def fixture(self):
        return {
            "audio": {"first_sample": 16000, "last_sample": 32000},
            "targets": [
                {"raw_span": [0, 3], "text": "空"},
                {"raw_span": [3, 6], "text": "青"},
            ],
        }

    def test_original_utf8_word_spans_are_the_binary_protocol_owners(self):
        data = request([self.fixture()])
        self.assertEqual(
            struct.unpack("<IIIIII", data[:24]), (2, 1, 0, 16000, 32000, 2)
        )
        self.assertEqual(struct.unpack("<III", data[24:36]), (0, 3, 3))
        self.assertEqual(data[36:39].decode(), "空")
        case = self.fixture()
        case["targets"][0]["text"] = "a b"
        with self.assertRaises(ValueError):
            request([case])

    def test_bad_one_word_is_withheld_without_repairing_its_neighbor(self):
        case = self.fixture()
        reply = {
            "units": [
                {**case["targets"][0], "start_ms": 100, "end_ms": 400},
                {**case["targets"][1], "start_ms": 0, "end_ms": 0},
            ]
        }
        result = validate_reply(case, reply)
        self.assertEqual((result[0]["start_ms"], result[0]["end_ms"]), (100, 400))
        self.assertEqual(result[1]["start_ms"], -1)
        reply["units"][0]["raw_span"] = [1, 3]
        with self.assertRaises(ValueError):
            validate_reply(case, reply)
