"""Human word timing stays attached to its exact corpus word and line."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jamendo_reference import word_lines


class JamendoReference(unittest.TestCase):
    def test_line_end_is_separate_from_word_end_and_source_bytes_are_exact(self):
        rows = word_lines(
            "blue\nsky\n空\n",
            "word_start,word_end,line_end\n1,2,nan\n2.1,3,3.5\n4,5,5.5\n",
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["raw_line"], "blue sky")
        self.assertEqual(rows[0]["targets"][1]["raw_span"], [5, 8])
        self.assertEqual(rows[0]["reference"][1]["end_ms"], 3000)
        self.assertEqual(rows[0]["line_end_ms"], 3500)
        self.assertEqual(rows[1]["targets"][0]["raw_span"], [0, 3])

    def test_mismatch_unfinished_line_nonfinite_or_bad_clocks_reject(self):
        for labels in (
            "word_start,word_end,line_end\n1,2,nan\n",
            "word_start,word_end,line_end\n1,2,1.5\n",
            "word_start,word_end,line_end\ninf,2,3\n",
            "word_start,word_end,line_end\n2,1,3\n",
            "word_start,word_end,line_end\n1,2,3\n4,5,6\n",
        ):
            with self.assertRaises(ValueError):
                word_lines("word\n", labels)
