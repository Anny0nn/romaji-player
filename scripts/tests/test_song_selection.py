"""Offline selection checks: compare frozen ratios, never infer or contact Spotify."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "selection", Path(__file__).resolve().parents[1] / "select-song-suite.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def measured(number, timed, total=100):
    return {
        "track": f"{number:022d}",
        "status": "measured",
        "engine": "frozen-recipe",
        "model_sha256": "b" * 64,
        "base_snapshot": "source-snapshot",
        "timed_words": timed,
        "total_words": total,
        "result_sha256": "a" * 64,
    }


class SelectionTests(unittest.TestCase):
    def test_pending_baselines_cannot_freeze_an_early_biased_set(self):
        for status in ("pending", "unmeasured", "captured", "running"):
            with self.assertRaisesRegex(ValueError, "initial baseline"):
                module.select(
                    [measured(1, 30), {"track": f"{2:022d}", "status": status}]
                )

    def test_seven_worst_three_best_incomplete_with_no_overlap(self):
        rows = [measured(i, i * 5) for i in range(1, 20)]
        rows += [
            measured(20, 100),
            {"track": f"{21:022d}", "status": "source_unavailable"},
        ]
        result = module.select(rows)
        self.assertEqual(
            [r["timed_words"] for r in result["low"]], [5, 10, 15, 20, 25, 30, 35]
        )
        self.assertEqual([r["timed_words"] for r in result["high"]], [95, 90, 85])
        ids = [r["track"] for r in result["low"] + result["high"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            {r["reason"] for r in result["excluded"]},
            {"fully_covered", "source_unavailable"},
        )

    def test_ratio_ordering_and_ties_do_not_depend_on_input_order(self):
        rows = [measured(3, 50), measured(2, 1, 2), measured(1, 4, 10), measured(4, 99)]
        self.assertEqual(module.select(rows, 3), module.select(list(reversed(rows)), 3))
        self.assertEqual(
            [r["track"] for r in module.select(rows, 3)["low"]],
            [f"{1:022d}", f"{2:022d}"],
        )

    def test_small_pool_reports_shortfall_and_keeps_the_cap(self):
        result = module.select([measured(i, i * 10) for i in range(1, 6)])
        self.assertEqual((result["effective_cap"], result["shortfall"]), (5, 5))
        self.assertEqual((len(result["low"]), len(result["high"])), (4, 1))
        empty = module.select([measured(1, 100)])
        self.assertEqual((empty["effective_cap"], empty["shortfall"]), (0, 10))

    def test_bad_or_conflicting_measurements_cannot_select_a_set(self):
        for timed, total in [(2, 1), (-1, 100), (0, 0), (True, 100), (1, 2.0)]:
            with self.assertRaises(ValueError):
                module.select([measured(1, timed, total)])
        with self.assertRaises(ValueError):
            module.select([measured(1, 5), measured(1, 10)])
        other = measured(2, 10)
        other["engine"] = "different-recipe"
        with self.assertRaises(ValueError):
            module.select([measured(1, 5), other])
        other["engine"] = "frozen-recipe"
        other["model_sha256"] = "c" * 64
        with self.assertRaises(ValueError):
            module.select([measured(1, 5), other])
        with self.assertRaises(ValueError):
            module.select([], 0)

    def test_command_never_overwrites_an_existing_frozen_set(self):
        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch) / "frozen.json"
            measurements = Path(scratch) / "measurements.json"
            measurements.write_text('{"schema_version":1,"songs":[]}')
            output.write_text("earlier frozen comparison")
            run = subprocess.run(
                [
                    sys.executable,
                    str(module.__file__),
                    str(measurements),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(output.read_text(), "earlier frozen comparison")


if __name__ == "__main__":
    unittest.main()
