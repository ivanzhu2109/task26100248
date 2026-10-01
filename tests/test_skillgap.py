"""Correctness tests for SkillGapTracker."""

import random
from fractions import Fraction

import pytest

from skillgap import SkillGapTracker


def brute_force_gaps(evals, rep_team, scope, target):
    """Recompute bottom-2 directly from the definition."""
    if scope == "rep":
        reps = [target]
    else:
        reps = [r for r, t in rep_team.items() if t == target]
    if scope == "rep" and target not in rep_team:
        raise KeyError(target)
    if scope == "team" and not reps:
        raise KeyError(target)
    per_rep = {}
    for rep in reps:
        totals = {}
        for ev_rep, scores in evals.values():
            if ev_rep != rep:
                continue
            for comp, score in scores.items():
                total, count = totals.get(comp, (0, 0))
                totals[comp] = (total + score, count + 1)
        per_rep[rep] = {c: Fraction(s, n) for c, (s, n) in totals.items()}
    if scope == "rep":
        means = per_rep[target]
    else:
        sums = {}
        counts = {}
        for rep in reps:
            for comp, mean in per_rep[rep].items():
                sums[comp] = sums.get(comp, Fraction(0)) + mean
                counts[comp] = counts.get(comp, 0) + 1
        means = {c: sums[c] / counts[c] for c in sums}
    return sorted(means.items(), key=lambda kv: (kv[1], kv[0]))[:2]


class TestTeamWeighting:
    def test_team_is_mean_of_member_means_not_pooled(self):
        t = SkillGapTracker()
        t.move_rep(1, 100)
        t.move_rep(2, 100)
        # rep 1: many evaluations, low scores on comp 1
        for i in range(9):
            t.set_evaluation(1000 + i, 1, {1: 1, 2: 10, 3: 10})
        # rep 2: single evaluation, high score on comp 1
        t.set_evaluation(2000, 2, {1: 10, 2: 1, 4: 5})
        # pooled flat average of comp 1 would be (9*1 + 10)/10 = 19/10
        # member-equal mean is (1 + 10)/2 = 11/2
        gaps = t.gaps("team", 100)
        # comp 4 (only rep 2) = 5; comps 1 and 2 both 11/2, tie -> lower id
        assert gaps == [(4, Fraction(5, 1)), (1, Fraction(11, 2))]
        assert Fraction(19, 10) not in [m for _, m in gaps]

    def test_members_without_competency_excluded_from_denominator(self):
        t = SkillGapTracker()
        t.move_rep(1, 100)
        t.move_rep(2, 100)
        t.move_rep(3, 100)
        t.set_evaluation(1, 1, {7: 6, 8: 8, 9: 9})
        t.set_evaluation(2, 2, {8: 2, 9: 3, 10: 4})
        t.set_evaluation(3, 3, {8: 4, 9: 6, 10: 8})
        # comp 7 only from rep 1 -> mean 6, not 6/3
        assert t.gaps("team", 100)[0] == (8, Fraction(14, 3))
        team_means = dict(brute_force_gaps({1: (1, {7: 6, 8: 8, 9: 9})}, {1: 100}, "team", 100))
        assert team_means[7] == 6

    def test_exact_tie_broken_by_competency_id(self):
        t = SkillGapTracker()
        t.move_rep(1, 100)
        t.set_evaluation(1, 1, {9: 1, 3: 2, 5: 8})
        t.set_evaluation(2, 1, {9: 1, 3: 1, 5: 8})
        t.set_evaluation(3, 1, {9: 2, 3: 1, 5: 8})
        # comp 9 mean = 4/3, comp 3 mean = 4/3 -> exact tie, lower id first
        assert t.gaps("rep", 1) == [(3, Fraction(4, 3)), (9, Fraction(4, 3))]

    def test_fraction_means_not_rounded(self):
        t = SkillGapTracker()
        t.move_rep(1, 100)
        # comp 1 mean = 4/3 = 1.3333..., comp 2 mean = 17/13 = 1.3077...
        # rounding to 1dp would tie them at 1.3 and misorder by id
        for i in range(13):
            scores = {2: 1, 3: 10, 4: 10}
            if i < 2:
                scores[1] = 1
            elif i == 2:
                scores[1] = 2
            if i == 12:
                scores[2] = 5
            t.set_evaluation(100 + i, 1, scores)
        assert t.gaps("rep", 1) == [(2, Fraction(17, 13)), (1, Fraction(4, 3))]


class TestOperations:
    def test_replace_changes_competency_set(self):
        t = SkillGapTracker()
        t.move_rep(1, 100)
        t.set_evaluation(1, 1, {1: 5, 2: 6, 3: 7})
        t.set_evaluation(1, 1, {4: 2, 5: 3, 6: 4})
        assert t.gaps("rep", 1) == [(4, 2), (5, 3)]
        assert t.gaps("team", 100) == [(4, 2), (5, 3)]

    def test_cannot_change_rep_of_evaluation(self):
        t = SkillGapTracker()
        t.move_rep(1, 100)
        t.move_rep(2, 100)
        t.set_evaluation(1, 1, {1: 5, 2: 6, 3: 7})
        with pytest.raises(ValueError):
            t.set_evaluation(1, 2, {1: 1, 2: 1, 3: 1})

    def test_remove_is_idempotent(self):
        t = SkillGapTracker()
        t.move_rep(1, 100)
        t.set_evaluation(1, 1, {1: 5, 2: 6, 3: 7})
        t.remove_evaluation(1)
        t.remove_evaluation(1)
        assert t.gaps("rep", 1) == []
        assert t.gaps("team", 100) == []

    def test_unregistered_rep_rejected(self):
        t = SkillGapTracker()
        with pytest.raises(KeyError):
            t.set_evaluation(1, 99, {1: 5, 2: 6, 3: 7})
        with pytest.raises(KeyError):
            t.gaps("rep", 99)
        with pytest.raises(KeyError):
            t.gaps("team", 99)

    def test_invalid_scores_rejected(self):
        t = SkillGapTracker()
        t.move_rep(1, 100)
        with pytest.raises(ValueError):
            t.set_evaluation(1, 1, {1: 5, 2: 6})
        with pytest.raises(ValueError):
            t.set_evaluation(1, 1, {i: 5 for i in range(13)})
        with pytest.raises(ValueError):
            t.set_evaluation(1, 1, {1: 0, 2: 6, 3: 7})
        with pytest.raises(ValueError):
            t.set_evaluation(1, 1, {1: 11, 2: 6, 3: 7})

    def test_move_rep_moves_all_contributions(self):
        t = SkillGapTracker()
        t.move_rep(1, 100)
        t.move_rep(2, 200)
        t.set_evaluation(1, 1, {1: 2, 2: 3, 3: 4})
        t.set_evaluation(2, 2, {1: 9, 2: 9, 3: 9})
        t.move_rep(1, 200)
        assert t.gaps("team", 200) == [(1, Fraction(11, 2)), (2, 6)]
        # team 100 has no members left and no longer exists
        with pytest.raises(KeyError):
            t.gaps("team", 100)


class TestDifferential:
    def test_random_ops_match_brute_force(self):
        rng = random.Random(20261002)
        tracker = SkillGapTracker()
        evals = {}
        rep_team = {}
        reps = list(range(8))
        teams = [10, 20, 30]
        for r in reps:
            team = rng.choice(teams)
            tracker.move_rep(r, team)
            rep_team[r] = team
        next_eval = [0]
        saw_double_team_change = False
        saw_competency_vanish = False

        def check():
            for r in reps:
                assert tracker.gaps("rep", r) == brute_force_gaps(
                    evals, rep_team, "rep", r
                )
            live_teams = {t for t in teams if t in {rep_team[r] for r in reps}}
            for tm in live_teams:
                assert tracker.gaps("team", tm) == brute_force_gaps(
                    evals, rep_team, "team", tm
                )

        for step in range(600):
            op = rng.random()
            if op < 0.45 or not evals:
                eid = next_eval[0]
                next_eval[0] += 1
                rep = rng.choice(reps)
                comps = rng.sample(range(15), rng.randint(3, 8))
                scores = {c: rng.randint(1, 10) for c in comps}
                tracker.set_evaluation(eid, rep, scores)
                evals[eid] = (rep, scores)
            elif op < 0.65:
                eid = rng.choice(list(evals))
                rep = evals[eid][0]
                comps = rng.sample(range(15), rng.randint(3, 8))
                scores = {c: rng.randint(1, 10) for c in comps}
                tracker.set_evaluation(eid, rep, scores)
                evals[eid] = (rep, scores)
            elif op < 0.8:
                eid = rng.choice(list(evals))
                tracker.remove_evaluation(eid)
                del evals[eid]
            else:
                rep = rng.choice(reps)
                new_team = rng.choice(teams)
                old_team = rep_team[rep]
                live_before = {rep_team[r] for r in reps}
                before = {
                    tm: tracker.gaps("team", tm)
                    for tm in (old_team, new_team)
                    if tm in live_before
                }
                tracker.move_rep(rep, new_team)
                rep_team[rep] = new_team
                live_after = {rep_team[r] for r in reps}
                after = {
                    tm: tracker.gaps("team", tm)
                    for tm in before
                    if tm in live_after
                }
                if old_team != new_team and len(after) == 2 and all(
                    before[tm] != after[tm] for tm in after
                ):
                    saw_double_team_change = True
            check()
        # dedicated scenario: competency vanishes after last contribution removed
        t2 = SkillGapTracker()
        t2.move_rep(1, 100)
        t2.set_evaluation(1, 1, {42: 5, 2: 6, 3: 7})
        assert 42 in dict(t2.gaps("rep", 1))
        t2.remove_evaluation(1)
        assert t2.gaps("rep", 1) == []
        assert t2.gaps("team", 100) == []
        saw_competency_vanish = True

        # dedicated scenario: one move changes both teams' bottom-2
        t3 = SkillGapTracker()
        t3.move_rep(1, 100)
        t3.move_rep(2, 100)
        t3.move_rep(3, 200)
        t3.set_evaluation(1, 1, {1: 1, 2: 2, 3: 3})
        t3.set_evaluation(2, 2, {1: 8, 2: 9, 3: 10})
        t3.set_evaluation(3, 3, {1: 5, 2: 5, 3: 5})
        b100 = t3.gaps("team", 100)
        b200 = t3.gaps("team", 200)
        t3.move_rep(1, 200)
        a100 = t3.gaps("team", 100)
        a200 = t3.gaps("team", 200)
        assert b100 != a100 and b200 != a200
        saw_double_team_change = True

        assert saw_double_team_change
        assert saw_competency_vanish
