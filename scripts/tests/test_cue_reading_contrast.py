"""A sequence score must not silently become a source-word probability."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cue_reading_contrast import nominate_cue_reading
from kana_reading_contrast import nominate_reading


def candidate(identity, current, real, silence, wrong):
    return {
        "id": identity,
        "kana": "ひらく" if current else "あく",
        "current": current,
        "observations": {
            condition: {
                "token_log_probabilities": [score],
                "source_token_indices": [None],
            }
            for condition, score in zip(
                ("real", "silence", "wrong_verse"), (real, silence, wrong), strict=True
            )
        },
    }


class CompleteCueContrast(unittest.TestCase):
    def setUp(self):
        self.candidates = [
            candidate("current", True, -10, -11, -11),
            candidate("alternative", False, -1, -10, -10),
        ]

    def test_crossing_bpe_can_support_a_cue_without_allocating_it_to_a_word(self):
        before = copy.deepcopy(self.candidates)
        self.assertEqual(
            nominate_reading(self.candidates)["reason"], "unowned_competitor"
        )
        result = nominate_cue_reading(self.candidates)
        self.assertEqual(result["reason"], "whole_cue_hypothesis")
        self.assertEqual(result["candidate_id"], "alternative")
        self.assertEqual(set(result), {"reason", "candidate_id", "margins"})
        self.assertEqual(self.candidates, before)

    def test_current_metadata_does_not_choose_the_winner(self):
        original = nominate_cue_reading(self.candidates)
        for row in self.candidates:
            row["current"] = not row["current"]
        result = nominate_cue_reading(self.candidates)
        self.assertEqual(result["candidate_id"], original["candidate_id"])
        self.assertEqual(result["margins"], original["margins"])
        self.assertEqual(result["reason"], "current_reading")

    def test_silence_or_wrong_verse_can_veto_a_language_prior(self):
        self.candidates[1]["observations"]["silence"]["token_log_probabilities"] = [-1]
        self.assertEqual(
            nominate_cue_reading(self.candidates)["reason"], "cue_control_disagreement"
        )
        del self.candidates[1]["observations"]["wrong_verse"]
        self.assertEqual(
            nominate_cue_reading(self.candidates)["reason"], "missing_condition"
        )

    def test_changed_counterfactual_tokens_and_nonfinite_scores_are_rejected(self):
        observation = self.candidates[1]["observations"]["wrong_verse"]
        for scores in ([-1, -1], [float("nan")], [float("inf")], [True], [0.1]):
            observation["token_log_probabilities"] = scores
            with self.assertRaises(ValueError):
                nominate_cue_reading(self.candidates)

    def test_small_or_nonpositive_acoustic_difference_is_not_a_nomination(self):
        for row in self.candidates:
            for observation in row["observations"].values():
                observation["token_log_probabilities"] = [-1]
        self.assertIsNone(nominate_cue_reading(self.candidates)["candidate_id"])
        for margin in (0, -1, True, float("nan")):
            with self.assertRaises(ValueError):
                nominate_cue_reading(self.candidates, margin=margin)


if __name__ == "__main__":
    unittest.main()
