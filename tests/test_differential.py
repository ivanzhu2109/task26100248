"""Differential testing: randomized op sequences checked against a
naive from-scratch recomputation of the formal definition."""

import random
import unittest
from fractions import Fraction

from skill_gaps import SkillGapTracker


class Naive:
    """Reference model: recomputes everything from the definition."""

    def __init__(self):
        self.rep_team = {}
        self.evals = {}  # eval_id -> (rep_id, scores)

    def move_rep(self, rep_id, team_id):
        self.rep_team[rep_id] = team_id

    def set_evaluation(self, evaluation_id, rep_id, scores):
        self.evals[evaluation_id] = (rep_id, dict(scores))

    def remove_evaluation(self, evaluation_id):
        self.evals.pop(evaluation_id, None)

    def _rep_means(self, rep_id):
        totals = {}
        counts = {}
        for owner, scores in self.evals.values():
            if owner != rep_id:
                continue
            for comp_id, score in scores.items():
                totals[comp_id] = totals.get(comp_id, 0) + score
                counts[comp_id] = counts.get(comp_id, 0) + 1
        return {c: Fraction(totals[c], counts[c]) for c in totals}

    def _team_means(self, team_id):
        sums = {}
        counts = {}
        for rep_id, rep_team in self.rep_team.items():
            if rep_team != team_id:
                continue
            for comp_id, mean in self._rep_means(rep_id).items():
                sums[comp_id] = sums.get(comp_id, Fraction(0)) + mean
                counts[comp_id] = counts.get(comp_id, 0) + 1
        return {c: sums[c] / counts[c] for c in sums}

    def gaps(self, scope, id):
        means = (
            self._rep_means(id) if scope == "rep" else self._team_means(id)
        )
        ordered = sorted(means.items(), key=lambda kv: (kv[1], kv[0]))
        return ordered[:2]

    def candidate_comps(self, scope, id):
        means = (
            self._rep_means(id) if scope == "rep" else self._team_means(id)
        )
        return set(means)


def _random_scores(rng, comp_ids):
    k = rng.randint(3, min(12, len(comp_ids)))
    return {c: rng.randint(1, 10) for c in rng.sample(comp_ids, k)}


class DirectedScenarioTest(unittest.TestCase):
    def test_single_move_changes_both_teams_bottom_two(self):
        t = SkillGapTracker()
        t.move_rep("mover", "A")
        t.move_rep("stayer", "A")
        t.move_rep("other", "B")
        t.set_evaluation("e1", "mover", {1: 1, 2: 2, 3: 3})
        t.set_evaluation("e2", "stayer", {4: 8, 5: 9, 6: 10})
        t.set_evaluation("e3", "other", {7: 8, 8: 9, 9: 10})
        before_a = t.gaps("team", "A")
        before_b = t.gaps("team", "B")
        t.move_rep("mover", "B")
        after_a = t.gaps("team", "A")
        after_b = t.gaps("team", "B")
        self.assertNotEqual(before_a, after_a)
        self.assertNotEqual(before_b, after_b)
        self.assertEqual(after_a, [(4, Fraction(8)), (5, Fraction(9))])
        self.assertEqual(after_b, [(1, Fraction(1)), (2, Fraction(2))])

    def test_competency_disappears_with_last_contribution(self):
        t = SkillGapTracker()
        t.move_rep("r", "A")
        t.set_evaluation("e1", "r", {7: 1, 8: 5, 9: 9})
        self.assertEqual(t.gaps("team", "A")[0], (7, Fraction(1)))
        # Replacement drops comp 7 entirely: it must vanish as a candidate.
        t.set_evaluation("e1", "r", {1: 4, 8: 5, 9: 9})
        comp_ids = [c for c, _ in t.gaps("team", "A")]
        self.assertNotIn(7, comp_ids)
        self.assertEqual(t.gaps("team", "A")[0], (1, Fraction(4)))
        # And via removal of the only contributing evaluation.
        t.set_evaluation("e2", "r", {7: 2, 8: 5, 9: 9})
        self.assertEqual(t.gaps("rep", "r")[0], (7, Fraction(2)))
        t.remove_evaluation("e2")
        comp_ids = [c for c, _ in t.gaps("rep", "r")]
        self.assertNotIn(7, comp_ids)


class RandomizedDifferentialTest(unittest.TestCase):
    def test_matches_naive_over_random_history(self):
        rng = random.Random(20261002)
        tracker = SkillGapTracker()
        naive = Naive()
        reps = [f"r{i}" for i in range(8)]
        teams = [f"T{i}" for i in range(3)]
        comp_ids = list(range(1, 11))
        live_evals = []
        next_eval = 0
        for rep in reps:
            team = rng.choice(teams)
            tracker.move_rep(rep, team)
            naive.move_rep(rep, team)

        saw_both_teams_change = False
        saw_last_contribution_lost = False

        for step in range(4000):
            op = rng.random()
            before = {tm: naive.gaps("team", tm) for tm in teams}
            before_cands = {tm: naive.candidate_comps("team", tm) for tm in teams}
            if op < 0.45 or not live_evals:
                eval_id = f"e{next_eval}"
                next_eval += 1
                rep = rng.choice(reps)
                scores = _random_scores(rng, comp_ids)
                tracker.set_evaluation(eval_id, rep, scores)
                naive.set_evaluation(eval_id, rep, scores)
                live_evals.append(eval_id)
            elif op < 0.70:
                eval_id = rng.choice(live_evals)
                rep = naive.evals[eval_id][0]
                scores = _random_scores(rng, comp_ids)
                tracker.set_evaluation(eval_id, rep, scores)
                naive.set_evaluation(eval_id, rep, scores)
            elif op < 0.90:
                eval_id = rng.choice(live_evals)
                tracker.remove_evaluation(eval_id)
                naive.remove_evaluation(eval_id)
                live_evals.remove(eval_id)
                if rng.random() < 0.1:
                    tracker.remove_evaluation(eval_id)  # duplicate: no-op
                    naive.remove_evaluation(eval_id)
            else:
                rep = rng.choice(reps)
                team = rng.choice(teams)
                tracker.move_rep(rep, team)
                naive.move_rep(rep, team)
            after = {tm: naive.gaps("team", tm) for tm in teams}
            changed = [tm for tm in teams if before[tm] != after[tm]]
            if len(changed) >= 2:
                saw_both_teams_change = True
            after_cands = {tm: naive.candidate_comps("team", tm) for tm in teams}
            for tm in teams:
                if before_cands[tm] - after_cands[tm]:
                    saw_last_contribution_lost = True

            if step % 7 == 0:
                for rep in reps:
                    self.assertEqual(
                        tracker.gaps("rep", rep), naive.gaps("rep", rep),
                        f"rep {rep} mismatch at step {step}")
                for tm in teams:
                    try:
                        got = tracker.gaps("team", tm)
                    except KeyError:
                        got = []
                    self.assertEqual(
                        got, naive.gaps("team", tm),
                        f"team {tm} mismatch at step {step}")

        self.assertTrue(saw_both_teams_change,
                        "scenario missing: one op changed two teams' bottom two")
        self.assertTrue(saw_last_contribution_lost,
                        "scenario missing: competency lost its last contribution")


if __name__ == "__main__":
    unittest.main()
