"""Paired singing boundaries retain every supplied phone and source owner."""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location(
    "english_boundary_probe",
    Path(__file__).resolve().parents[1] / "probe-english-boundaries.py",
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class EnglishBoundaryProbe(unittest.TestCase):
    def test_incomplete_phone_word_stays_unavailable(self):
        reference = [{"word": 0, "phone": p} for p in ("k", "aa")]
        units = [
            {**r, "start_ms": a, "end_ms": b}
            for r, a, b in zip(reference, (10, -1), (60, -1))
        ]
        target = [{"raw_span": [7, 11]}]
        self.assertEqual(
            probe.whole_word_envelopes(reference, units, target),
            [{"raw_span": [7, 11], "start_ms": -1, "end_ms": -1, "complete": False}],
        )
        units[1].update(start_ms=60, end_ms=180)
        self.assertEqual(
            probe.whole_word_envelopes(reference, units, target)[0]["end_ms"], 180
        )
        units[1]["start_ms"] = 50
        self.assertFalse(
            probe.whole_word_envelopes(reference, units, target)[0]["complete"]
        )

    def test_reordered_or_relabelled_phones_cannot_reattach(self):
        reference = [{"word": 0, "phone": p} for p in ("k", "aa")]
        units = [{**r, "start_ms": 10, "end_ms": 80} for r in reference]
        for changed in (units[::-1], [{**u, "word": 2} for u in units], units[:1]):
            with self.assertRaises(ValueError):
                probe.whole_word_envelopes(reference, changed, [{"raw_span": [0, 1]}])

    def test_first_path_requires_complete_spelling_and_inventory(self):
        def converter(text):
            return [
                SimpleNamespace(
                    text=text,
                    readings=[
                        SimpleNamespace(
                            paths=[
                                [SimpleNamespace(phonemes=["k", "aa"])],
                                [SimpleNamespace(phonemes=["bad"])],
                            ]
                        )
                    ],
                )
            ]

        fake = SimpleNamespace(convert=converter)
        targets = [{"raw_span": [9, 10], "text": "car", "romaji": "car"}]
        aliases, reference = probe.english_phones(
            fake, targets, {"SP": 0, "k": 1, "aa": 2}
        )
        self.assertEqual(aliases, {0: {"language": "en", "phones": ["k", "aa"]}})
        self.assertEqual(reference, [{"word": 0, "phone": p} for p in ("k", "aa")])
        self.assertIsNone(probe.english_phones(fake, targets, {"SP": 0, "k": 1}))
        fake.infer_oov = lambda _: [["k", "ah"]]
        fallback, _ = probe.english_phones(
            fake, targets, {"SP": 0, "k": 1, "ah": 2}, cmu_fallback=True
        )
        self.assertEqual(fallback[0]["phones"], ["k", "ah"])
        fake.infer_oov = lambda _: []
        self.assertIsNone(
            probe.english_phones(fake, targets, {"SP": 0, "k": 1}, cmu_fallback=True)
        )
        self.assertIsNone(
            probe.english_phones(
                fake, [{**targets[0], "expected_text": "かな"}], {"k": 1, "aa": 2}
            )
        )
        fake.convert = lambda _: converter("different")
        self.assertIsNone(probe.english_phones(fake, targets, {"k": 1, "aa": 2}))
