"""Regression cases for kana hypotheses crossing original word boundaries."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kana_reading_contrast import nominate_reading, observation_scores, substitute_kana


def observation(word, suffix):
    return {
        "token_log_probabilities": [word, suffix],
        "source_token_indices": [[0]],
    }


def candidate(identity, current, real, control):
    return {
        "id": identity,
        "kana": "あ" if current else "い",
        "current": current,
        "observations": {
            "real": observation(*real),
            "silence": observation(*control),
            "wrong_verse": observation(*control),
        },
    }


class KanaMinimalPairs(unittest.TestCase):
    def test_replacement_keeps_following_word_and_original_utf8_ownership(self):
        groups = [
            {"raw_span": [0, 3], "expected_text": "天", "kana": "てん"},
            {"raw_span": [3, 6], "expected_text": "の", "kana": "の"},
            {"raw_span": [7, 13], "expected_text": "存在", "kana": "そんざい"},
        ]
        before = copy.deepcopy(groups)
        result = substitute_kana("天の 存在！", groups, 0, "あま")
        self.assertEqual(result["text"], "あまのそんざい")
        self.assertEqual(result["source_raw_span"], [0, 3])
        self.assertEqual(result["targets"][1], {"raw_span": [6, 9], "text": "の"})
        self.assertEqual(groups, before)

    def test_unmapped_alphanumeric_source_cannot_silently_disappear(self):
        group = {"raw_span": [3, 6], "expected_text": "の", "kana": "の"}
        with self.assertRaises(ValueError):
            substitute_kana("天の", [group], 0, "の")
        with self.assertRaises(ValueError):
            substitute_kana("の天", [{**group, "raw_span": [0, 3]}], 0, "の")

    def test_changed_partial_utf8_and_unsupported_reading_fail(self):
        group = {"raw_span": [0, 3], "expected_text": "天", "kana": "てん"}
        for bad in ("ama", "あ ま", "", "？"):
            with self.assertRaises(ValueError):
                substitute_kana("天", [group], 0, bad)
        with self.assertRaises(ValueError):
            substitute_kana("私", [group], 0, "わたし")
        with self.assertRaises(UnicodeDecodeError):
            substitute_kana("天", [{**group, "raw_span": [0, 1]}], 0, "あま")

    def test_good_word_score_cannot_absorb_the_next_word(self):
        current = candidate("current", True, (-5, -1), (-10, -1))
        swallowed = candidate("swallowed", False, (-1, -10), (-10, -1))
        result = nominate_reading([current, swallowed])
        self.assertEqual(result["reason"], "word_cue_or_control_disagreement")
        self.assertIsNone(result["candidate_id"])

    def test_language_prior_without_local_acoustic_contrast_is_withheld(self):
        current = candidate("current", True, (-10, -2), (-12, -2))
        plausible = candidate("plausible", False, (-1, -2), (-2, -2))
        self.assertIsNone(nominate_reading([current, plausible])["candidate_id"])

    def test_missing_counterfactual_or_unowned_competitor_withholds_entire_word(self):
        current = candidate("current", True, (-10, -1), (-11, -1))
        proposed = candidate("proposed", False, (-1, -1), (-10, -1))
        missing = copy.deepcopy(current)
        del missing["observations"]["wrong_verse"]
        self.assertEqual(
            nominate_reading([missing, proposed])["reason"], "missing_condition"
        )
        for row in current["observations"].values():
            row["source_token_indices"] = [None]
        self.assertEqual(
            nominate_reading([current, proposed])["reason"], "unowned_competitor"
        )

    def test_consistent_contrast_nominates_only_a_hypothesis_without_timestamps(self):
        current = candidate("current", True, (-10, -1), (-11, -1))
        proposed = candidate("proposed", False, (-1, -1), (-10, -1))
        result = nominate_reading([current, proposed])
        self.assertEqual(result["reason"], "conditional_hypothesis")
        self.assertEqual(result["candidate_id"], "proposed")
        self.assertEqual(set(result), {"reason", "candidate_id", "margins"})
        for value in (float("nan"), float("inf"), True, 0.1):
            bad = observation(value, -1)
            with self.assertRaises(ValueError):
                observation_scores(bad)

    def test_counterfactual_cannot_change_the_scored_tokens(self):
        current = candidate("current", True, (-10, -1), (-11, -1))
        proposed = candidate("proposed", False, (-1, -1), (-10, -1))
        current["observations"]["wrong_verse"]["source_token_indices"] = [[0, 1]]
        with self.assertRaises(ValueError):
            nominate_reading([current, proposed])


if __name__ == "__main__":
    unittest.main()
