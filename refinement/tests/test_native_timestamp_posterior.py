import itertools
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from native_timestamp_posterior import (
    decode_all_eight_frozen_conditions,
    decode_timestamp_classes,
    full_vocab_log_softmax,
    read_QWTLOG02,
)


def owners(n):
    return [
        {
            "owner_id": "original:" + str(i),
            "owner_index": i,
            "raw_span": [i * 3, (i + 1) * 3],
        }
        for i in range(n)
    ]


def metadata(n, classes, step=80):
    return {
        "original_owner_count": n,
        "classify_num": classes,
        "timestamp_segment_time_ms": step,
        "clip_relative_origin_ms": 0,
        "class_time_mapping": "class_index_times_timestamp_segment_time_ms",
        "all_timestamp_classes_known": True,
    }


def brute(logits, duration, step, cap, minimum=80):
    logp = full_vocab_log_softmax(logits.astype(np.float64))
    best, score = None, -math.inf
    for path in itertools.product(range(logp.shape[1]), repeat=logp.shape[0]):
        if any(
            not 0 < c * step < duration or not math.isfinite(logp[i, c])
            for i, c in enumerate(path)
        ):
            continue
        if any(
            (path[i + 1] - path[i]) * step < minimum for i in range(0, len(path), 2)
        ):
            continue
        if any(path[i] > path[i + 1] for i in range(1, len(path) - 1, 2)):
            continue
        if cap is not None and any(
            float(np.max(logp[i])) - logp[i, c] > cap for i, c in enumerate(path)
        ):
            continue
        value = float(sum(logp[i, c] for i, c in enumerate(path)))
        if value > score or (
            value == score
            and (best is None or tuple(reversed(path)) < tuple(reversed(best)))
        ):
            best, score = path, value
    return best, score


class NativeTimestampTests(unittest.TestCase):
    def test_optional_metadata_marker_rows_must_match_actual2N(self):
        m = metadata(1, 4)
        m["marker_rows"] = 4
        with self.assertRaises(ValueError):
            decode_timestamp_classes(np.zeros((2, 4)), owners(1), m, 240)
        m["marker_rows"] = 2
        self.assertEqual(
            decode_timestamp_classes(np.zeros((2, 4)), owners(1), m, 240)[
                "marker_rows"
            ],
            2,
        )

    def test_exhaustive_all8_conditions(self):
        rng = np.random.default_rng(3)
        trials = 0
        for n, classes, step, duration in (
            (1, 6, 80, 400),
            (2, 6, 80, 400),
            (2, 6, 40, 200),
        ):
            arrays = [np.zeros((2 * n, classes), dtype=np.float32)]
            arrays.extend(
                rng.normal(size=(2 * n, classes)).astype(np.float32)
                for unused in range(5)
            )
            for logits in arrays:
                result = decode_all_eight_frozen_conditions(
                    logits, owners(n), metadata(n, classes, step), duration
                )
                self.assertEqual(len(result["conditions"]), 8)
                for condition in result["conditions"]:
                    path, score = brute(
                        logits,
                        duration,
                        step,
                        condition["max_per_marker_peak_relative_logp_drop"],
                        condition["source_slot_minimum_duration_ms"],
                    )
                    trials += 1
                    if path is None:
                        self.assertIsNone(condition["selected_classes"])
                        self.assertEqual(len(condition["words"]), n)
                        self.assertTrue(
                            all(
                                not w["word_timing_qualified"]
                                for w in condition["words"]
                            )
                        )
                    else:
                        self.assertEqual(condition["selected_classes"], list(path))
                        self.assertAlmostEqual(
                            condition["full_vocab_path_log_probability"],
                            score,
                            places=12,
                        )
                        for word in condition["words"]:
                            start, end = word["interval_ms"]
                            self.assertEqual(
                                word["word_timing_qualified"], end - start >= 80
                            )
                            if not word["word_timing_qualified"]:
                                self.assertIsNone(word["qualifying_word_interval_ms"])
        self.assertEqual(trials, 144)

    def test_source_point_preserved_invalid_while_other_word80ms_qualified(self):
        logits = np.full((4, 6), -20.0, dtype=np.float32)
        for marker, cls in enumerate((1, 1, 2, 3)):
            logits[marker, cls] = 0.0
        result = decode_timestamp_classes(
            logits, owners(2), metadata(2, 6), 400, min_source_word_ms=0
        )
        self.assertEqual(result["arms"][0]["selected_classes"], [1, 1, 2, 3])
        a, b = result["arms"][0]["words"]
        self.assertEqual(a["interval_ms"], [80.0, 80.0])
        self.assertFalse(a["word_timing_qualified"])
        self.assertIsNone(a["qualifying_word_interval_ms"])
        self.assertEqual(
            a["word_status"], "observed_timestamp_point_invalid_for_word_timing"
        )
        self.assertTrue(b["word_timing_qualified"])
        self.assertEqual(b["qualifying_word_interval_ms"], [160.0, 240.0])
        self.assertEqual(len(result["arms"][0]["marker_observations"]), 4)
        strict = decode_timestamp_classes(
            logits, owners(2), metadata(2, 6), 400, min_source_word_ms=80
        )
        self.assertIsNone(strict["arms"][1]["selected_classes"])

    def test_v2_ledger_runtime_metadata_and_origin_assertion(self):
        a = np.zeros((4, 5), dtype="<f4")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "observed.bin"
            path.write_bytes(
                b"QWTLOG02" + struct.pack("<IIIII", 2, 4, 5, 40, 0) + a.tobytes()
            )
            observed, m = read_QWTLOG02(path)
            np.testing.assert_array_equal(observed, a)
            self.assertEqual(m["timestamp_segment_time_ms"], 40)
            self.assertEqual(
                decode_timestamp_classes(
                    observed, owners(2), m, 160, min_source_word_ms=0
                )["metadata_derived_minimum_class_distance"],
                0,
            )
            path.write_bytes(
                b"QWTLOG02" + struct.pack("<IIIII", 2, 4, 5, 40, 80) + a.tobytes()
            )
            with self.assertRaises(ValueError):
                read_QWTLOG02(path)

    def test_exhaustive_bruteforce_score_and_feasibility_parity(self):
        random = np.random.default_rng(0)
        for n, classes, step, duration in (
            (1, 6, 80, 400),
            (2, 6, 80, 400),
            (2, 7, 40, 240),
        ):
            for unused in range(6):
                logits = random.normal(size=(2 * n, classes)).astype(np.float32)
                result = decode_timestamp_classes(
                    logits, owners(n), metadata(n, classes, step), duration
                )
                for arm, cap in zip(
                    result["arms"], (None, 0.0, math.log(2), math.log(10)), strict=True
                ):
                    path, score = brute(logits, duration, step, cap)
                    if path is None:
                        self.assertIsNone(arm["selected_classes"])
                        self.assertEqual(len(arm["words"]), n)
                    else:
                        self.assertAlmostEqual(
                            arm["full_vocab_path_log_probability"], score, places=12
                        )
                        self.assertEqual(arm["selected_classes"], list(path))

    def test_crossing_argmax_resolves_with_observed_second_peaks(self):
        logits = np.full((4, 8), -10.0, dtype=np.float32)
        for i, c in enumerate((1, 4, 3, 6)):
            logits[i, c] = 0.0
        logits[1, 2] = -0.5
        result = decode_timestamp_classes(logits, owners(2), metadata(2, 8), 560)
        self.assertEqual(result["raw_argmax"]["selected_classes"], [1, 4, 3, 6])
        self.assertEqual(result["arms"][0]["selected_classes"], [1, 2, 3, 6])
        self.assertIsNone(result["arms"][1]["selected_classes"])
        self.assertEqual(result["arms"][2]["selected_classes"], [1, 2, 3, 6])
        self.assertAlmostEqual(
            result["arms"][2]["marker_observations"][1]["peak_relative_logp_drop"], 0.5
        )

    def test_full_vocab_normalization_precedes_mask(self):
        logits = np.array(
            [[10.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 10.0]], dtype=np.float32
        )
        result = decode_timestamp_classes(logits, owners(1), metadata(1, 4), 240)
        arm = result["arms"][0]
        self.assertEqual(arm["selected_classes"], [1, 2])
        self.assertLess(
            arm["marker_observations"][0]["selected_full_vocabulary_probability"], 0.001
        )
        self.assertIsNone(result["arms"][3]["selected_classes"])

    def test_exact_tie_earliest_reverse_marker_order(self):
        logits = np.zeros((4, 7), dtype=np.float32)
        result = decode_timestamp_classes(logits, owners(2), metadata(2, 7), 480)
        for arm in result["arms"]:
            self.assertEqual(arm["selected_classes"], [1, 2, 2, 3])

    def test_min80ms_independent_of_metadata_step(self):
        result = decode_timestamp_classes(
            np.zeros((2, 8), dtype=np.float32), owners(1), metadata(1, 8, 40), 280
        )
        self.assertEqual(result["metadata_derived_minimum_class_distance"], 2)
        self.assertEqual(result["arms"][0]["selected_classes"], [1, 3])

    def test_impossible_full_context_withholds_every_owner(self):
        result = decode_timestamp_classes(
            np.zeros((4, 4), dtype=np.float32), owners(2), metadata(2, 4), 240
        )
        for arm in result["arms"]:
            self.assertIsNone(arm["selected_classes"])
            self.assertEqual(len(arm["words"]), 2)
            self.assertTrue(all(w["interval_ms"] is None for w in arm["words"]))

    def test_strict_crop_edges_excluded_and_zero_duration_impossible(self):
        logits = np.full((2, 3), -np.inf, dtype=np.float32)
        logits[:, 1] = 0.0
        result = decode_timestamp_classes(logits, owners(1), metadata(1, 3), 160)
        self.assertIsNone(result["arms"][0]["selected_classes"])
        self.assertFalse(result["raw_argmax"]["words"][0]["strict_interior_min80ms"])

    def test_nan_positive_inf_and_unknown_class_contract_rejected(self):
        for value in (np.nan, np.inf):
            a = np.zeros((2, 4), dtype=np.float32)
            a[0, 2] = value
            with self.assertRaises(ValueError):
                decode_timestamp_classes(a, owners(1), metadata(1, 4), 240)
        m = metadata(1, 4)
        m["all_timestamp_classes_known"] = False
        with self.assertRaises(ValueError):
            decode_timestamp_classes(np.zeros((2, 4)), owners(1), m, 240)

    def test_origin_owner_count_and_duplicate_owner_identity_rejected(self):
        for field, value in (
            ("clip_relative_origin_ms", 80),
            ("original_owner_count", 2),
            ("timestamp_segment_time_ms", None),
        ):
            m = metadata(1, 4)
            m[field] = value
            with self.assertRaises(ValueError):
                decode_timestamp_classes(np.zeros((2, 4)), owners(1), m, 240)
        own = owners(2)
        own[1]["owner_id"] = own[0]["owner_id"]
        with self.assertRaises(ValueError):
            decode_timestamp_classes(np.zeros((4, 6)), own, metadata(2, 6), 400)


if __name__ == "__main__":
    unittest.main()
