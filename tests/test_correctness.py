"""Deterministic checks: team weighting semantics and exact tie ordering."""

import unittest
from fractions import Fraction

from skill_gaps import SkillGapTracker


class TeamWeightingTest(unittest.TestCase):
    """Two reps, same team, wildly different evaluation frequency and
    coverage. Proves the team mean is the equal-weight average of member
    means, not a pooled average over all evaluations."""

    def setUp(self):
        self.t = SkillGapTracker()
        self.t.move_rep("busy", "T")
        self.t.move_rep("quiet", "T")
        # busy: 50 evaluations, all scoring comp 1 = 10
        for i in range(50):
            self.t.set_evaluation(f"b{i}", "busy", {1: 10, 2: 10, 3: 10})
        # quiet: 1 evaluation, scoring comp 1 = 2
        self.t.set_evaluation("q0", "quiet", {1: 2, 2: 2, 3: 2})

    def test_team_mean_is_member_mean_average(self):
        gaps = dict(self.t.gaps("team", "T"))
        # Pooled-over-evaluations mean for comp 1 would be
        # (50*10 + 1*2) / 51 = 502/51 ~ 9.84. The defined team mean is
        # (10 + 2) / 2 = 6 exactly, because each member weighs equally.
        self.assertEqual(gaps[1], Fraction(6, 1))
        self.assertNotEqual(gaps[1], Fraction(502, 51))

    def test_evaluation_count_gives_no_extra_weight(self):
        # quiet's single evaluation pulls the team mean halfway to 2
        # despite busy having 50x more evaluations.
        self.assertEqual(self.t.gaps("team", "T")[0], (1, Fraction(6, 1)))

    def test_coverage_difference(self):
        self.t.set_evaluation("q1", "quiet", {4: 3, 5: 9, 6: 9})
        # comp 4 has data only from quiet; team mean equals quiet's mean.
        gaps = dict(self.t.gaps("team", "T"))
        self.assertEqual(gaps[4], Fraction(3, 1))


class ExactOrderingTest(unittest.TestCase):
    """Ordering uses exact rational comparison; ties break by
    competency_id ascending. No rounding, no epsilon."""

    def _tracker(self):
        t = SkillGapTracker()
        t.move_rep("r", "T")
        return t

    def test_exact_tie_breaks_by_competency_id(self):
        t = self._tracker()
        # comp 5 mean = (1+2)/2 = 3/2; comp 9 mean = (1+2)/2 = 3/2.
        t.set_evaluation("e1", "r", {5: 1, 3: 3, 4: 10})
        t.set_evaluation("e2", "r", {5: 2, 3: 3, 4: 10})
        t.set_evaluation("e3", "r", {9: 1, 3: 3, 4: 10})
        t.set_evaluation("e4", "r", {9: 2, 3: 3, 4: 10})
        self.assertEqual(
            t.gaps("rep", "r"),
            [(5, Fraction(3, 2)), (9, Fraction(3, 2))],
        )

    def test_tie_across_different_denominators(self):
        t = self._tracker()
        # comp 2 mean = 3/2; comp 7 mean = 6/4 = 3/2. Same rational,
        # different (sum, count); must tie and break by id.
        t.set_evaluation("e1", "r", {2: 1, 8: 10, 9: 10})
        t.set_evaluation("e2", "r", {2: 2, 8: 10, 9: 10})
        t.set_evaluation("e3", "r", {7: 1, 8: 10, 9: 10})
        t.set_evaluation("e4", "r", {7: 1, 8: 10, 9: 10})
        t.set_evaluation("e5", "r", {7: 2, 8: 10, 9: 10})
        t.set_evaluation("e6", "r", {7: 2, 8: 10, 9: 10})
        self.assertEqual(
            t.gaps("rep", "r"),
            [(2, Fraction(3, 2)), (7, Fraction(3, 2))],
        )

    def test_close_but_distinct_means_not_merged(self):
        t = self._tracker()
        # comp 1: 100 evals of 3 -> mean 300/100 = 3
        # comp 2: 99 evals of 3 + 1 eval of 4 -> mean 301/100 = 3.01
        # A float-epsilon comparison could merge these; exact math must not.
        for i in range(100):
            self.t_id = f"e{i}"
            t.set_evaluation(self.t_id, "r", {1: 3, 2: 3 if i else 4, 8: 10})
        self.assertEqual(
            t.gaps("rep", "r"),
            [(1, Fraction(3, 1)), (2, Fraction(301, 100))],
        )

    def test_team_tie_breaks_by_competency_id(self):
        t = SkillGapTracker()
        t.move_rep("r1", "T")
        t.move_rep("r2", "T")
        # Team mean for comp 6: (1 + 2)/2 = 3/2; comp 4: (2+1)/2 = 3/2.
        t.set_evaluation("e1", "r1", {6: 1, 4: 2, 9: 10})
        t.set_evaluation("e2", "r2", {6: 2, 4: 1, 9: 10})
        self.assertEqual(
            t.gaps("team", "T"),
            [(4, Fraction(3, 2)), (6, Fraction(3, 2))],
        )


if __name__ == "__main__":
    unittest.main()
