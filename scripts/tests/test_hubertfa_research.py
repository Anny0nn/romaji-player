"""Research adapters must keep exact clocks, inventories and source ownership."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hubertfa_research as research

spec = importlib.util.spec_from_file_location(
    "benchmark_hubertfa", Path(research.__file__).with_name("benchmark-hubertfa.py")
)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class HubertFAContracts(unittest.TestCase):
    def test_completed_observations_bind_recipe_and_detect_changed_records(self):
        identity = {"model": "pinned", "code": "frozen"}
        row = {"id": "synthetic:0", "predicted": [{"start_ms": 80, "end_ms": 160}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "checkpoint.json"
            benchmark.write_checkpoint(path, row, identity)
            self.assertEqual(benchmark.read_checkpoint(path, identity), row)
            with self.assertRaises(ValueError):
                benchmark.read_checkpoint(path, {**identity, "code": "changed"})
            value = json.loads(path.read_text())
            value["record"]["predicted"][0]["end_ms"] = 180
            path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                benchmark.read_checkpoint(path, identity)

    def test_nearest_feature_clock_uses_ties_to_even_without_stretching(self):
        self.assertEqual(
            research.feature_indices(4410, 4), [0, 0, 1, 2, 2, 2, 3, 3, 3, 3, 3]
        )
        for count, frames in ((1102, 10), (4410, 0), (4410, True)):
            with (
                self.subTest(count=count, frames=frames),
                self.assertRaises(ValueError),
            ):
                research.feature_indices(count, frames)

    def test_word_markers_allow_silence_without_erasing_lexical_phones(self):
        rows = [
            {"word": 2, "phone": "k"},
            {"word": 2, "phone": "er"},
            {"word": 3, "phone": "aa"},
        ]
        phones, owners = research.phone_sequence(
            rows, {"SP": 0, "k": 1, "er": 2, "aa": 3}
        )
        self.assertEqual(phones, ["SP", "k", "er", "SP", "aa", "SP"])
        self.assertEqual(owners, [-1, 0, 1, -1, 2, -1])
        for invalid in (
            [],
            [{"word": 1, "phone": "SP"}],
            [{"word": 1, "phone": "unknown"}],
            [{"word": w, "phone": "k"} for w in (1, 2, 1)],
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                research.phone_sequence(invalid, {"SP": 0, "k": 1})

    def test_only_exact_documented_training_buffers_are_removed(self):
        state = {
            k: SimpleNamespace(shape=shape)
            for k, shape in research.TRAINING_BUFFERS.items()
        }
        state["head.weight"] = SimpleNamespace(shape=[42, 192, 1])
        self.assertEqual(list(research.inference_state(state)), ["head.weight"])
        for changed in (
            {**state, "CTC_GHM_loss_fn.ema": SimpleNamespace(shape=[11])},
            {k: v for k, v in state.items() if k != "CTC_GHM_loss_fn.ema"},
        ):
            with self.assertRaisesRegex(ValueError, "training buffers"):
                research.inference_state(changed)

    def test_changed_asset_is_refused_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model = root / "cache"
            model.mkdir()
            path = model / "a.bin"
            path.write_bytes(b"valid")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "files": {
                            "a.bin": {
                                "size": 5,
                                "sha256": research.digest(path),
                                "url": "https://example.invalid/never",
                            }
                        }
                    }
                )
            )
            with (
                patch.object(research, "ASSETS", manifest),
                patch.object(
                    research.urllib.request,
                    "urlopen",
                    side_effect=AssertionError("network"),
                ),
            ):
                research.assets(model)
                path.write_bytes(b"wrong")
                with self.assertRaisesRegex(ValueError, "Unverified"):
                    research.assets(model)

    def test_repository_output_and_symlink_back_into_git_are_refused(self):
        with self.assertRaisesRegex(ValueError, "outside git"):
            research.private_path(research.ROOT / ".cache/model")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "linked"
            path.symlink_to(research.ROOT)
            with self.assertRaises(ValueError):
                research.private_path(path / "model")

    def test_partial_word_is_an_abstention_and_raw_is_not_supported(self):
        reference = [
            {"word": 0, "phone": "k", "start_ms": 10, "end_ms": 40},
            {"word": 0, "phone": "aa", "start_ms": 40, "end_ms": 100},
        ]
        units = [{**r, "mean_probability": 0.2} for r in reference]
        rows = [{"id": "synthetic", "reference": reference, "predicted": units}]
        self.assertEqual(
            benchmark.word_records(rows, supported=False)[0]["predicted"][0]["end_ms"],
            100,
        )
        self.assertEqual(
            benchmark.word_records(rows, supported=True)[0]["predicted"][0]["start_ms"],
            -1,
        )
        units[1].update(start_ms=-1, end_ms=-1)
        self.assertEqual(
            benchmark.word_records(rows, supported=False)[0]["predicted"][0][
                "start_ms"
            ],
            -1,
        )
