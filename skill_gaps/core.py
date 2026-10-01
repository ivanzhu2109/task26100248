"""SkillGapTracker: incremental, exact skill-gap computation.

Public result representation: gaps returns a list of
(competency_id, fractions.Fraction) tuples, ordered by exact mean
ascending, ties broken by competency_id ascending. Fractions are exact
and lossless; no rounding is ever applied to comparisons.
"""

from fractions import Fraction

from skill_gaps.treap import Treap

__all__ = ["SkillGapTracker"]

_MIN_COMPETENCIES = 3
_MAX_COMPETENCIES = 12
_MIN_SCORE = 1
_MAX_SCORE = 10


class _Rep:
    __slots__ = ("team_id", "evals", "comp", "tree")

    def __init__(self, team_id):
        self.team_id = team_id
        self.evals = {}          # evaluation_id -> {competency_id: score}
        self.comp = {}           # competency_id -> [total_score, eval_count]
        self.tree = Treap()      # keys: (Fraction mean, competency_id)


class _Team:
    __slots__ = ("members", "comp", "tree")

    def __init__(self):
        self.members = 0
        self.comp = {}           # competency_id -> [Fraction sum_of_rep_means, rep_count]
        self.tree = Treap()      # keys: (Fraction team_mean, competency_id)


def _validate_scores(scores):
    if not isinstance(scores, dict):
        raise ValueError("scores must be a dict of competency_id -> score")
    if not (_MIN_COMPETENCIES <= len(scores) <= _MAX_COMPETENCIES):
        raise ValueError("scores must contain 3 to 12 competencies")
    for comp_id, score in scores.items():
        if not isinstance(comp_id, int) or isinstance(comp_id, bool):
            raise ValueError("competency_id must be an int")
        if not isinstance(score, int) or isinstance(score, bool):
            raise ValueError("score must be an int")
        if not (_MIN_SCORE <= score <= _MAX_SCORE):
            raise ValueError("score must be between 1 and 10")


class SkillGapTracker:
    """Tracks reps, teams and evaluations; answers bottom-2 gap queries.

    All arithmetic on means is exact (fractions.Fraction). Per-rep and
    per-team rankings are maintained incrementally in treaps keyed by
    (mean, competency_id), so queries never scan evaluations or members.
    """

    def __init__(self):
        self._reps = {}          # rep_id -> _Rep
        self._teams = {}         # team_id -> _Team
        self._eval_owner = {}    # evaluation_id -> rep_id

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _team(self, team_id):
        team = self._teams.get(team_id)
        if team is None:
            team = self._teams[team_id] = _Team()
        return team

    def _team_comp_remove(self, team, comp_id, rep_mean):
        """Remove one member's mean from a team aggregate."""
        entry = team.comp[comp_id]
        team.tree.discard((entry[0] / entry[1], comp_id))
        entry[0] -= rep_mean
        entry[1] -= 1
        if entry[1] == 0:
            del team.comp[comp_id]
        else:
            team.tree.insert((entry[0] / entry[1], comp_id))

    def _team_comp_add(self, team, comp_id, rep_mean):
        """Add one member's mean to a team aggregate."""
        entry = team.comp.get(comp_id)
        if entry is not None:
            team.tree.discard((entry[0] / entry[1], comp_id))
            entry[0] += rep_mean
            entry[1] += 1
            team.tree.insert((entry[0] / entry[1], comp_id))
        else:
            team.comp[comp_id] = [Fraction(rep_mean), 1]
            team.tree.insert((Fraction(rep_mean), comp_id))

    def _rep_comp_add_scores(self, rep, scores, sign):
        """Apply (+1)/(-1) times an evaluation's scores to a rep."""
        team = self._teams[rep.team_id]
        for comp_id, score in scores.items():
            entry = rep.comp.get(comp_id)
            old_mean = None
            if entry is not None:
                old_mean = Fraction(entry[0], entry[1])
                self._team_comp_remove(team, comp_id, old_mean)
                rep.tree.discard((old_mean, comp_id))
            if entry is None:
                entry = rep.comp[comp_id] = [0, 0]
            entry[0] += sign * score
            entry[1] += sign
            if entry[1] == 0:
                del rep.comp[comp_id]
            else:
                new_mean = Fraction(entry[0], entry[1])
                rep.tree.insert((new_mean, comp_id))
                self._team_comp_add(team, comp_id, new_mean)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def move_rep(self, rep_id, team_id):
        """Register a rep on first call; transfer teams afterwards."""
        rep = self._reps.get(rep_id)
        if rep is None:
            self._reps[rep_id] = _Rep(team_id)
            self._team(team_id).members += 1
            return
        if rep.team_id == team_id:
            return
        old_team_id = rep.team_id
        old_team = self._teams[rep.team_id]
        new_team = self._team(team_id)
        for comp_id, (total, count) in rep.comp.items():
            mean = Fraction(total, count)
            self._team_comp_remove(old_team, comp_id, mean)
            self._team_comp_add(new_team, comp_id, mean)
        old_team.members -= 1
        new_team.members += 1
        rep.team_id = team_id
        if old_team.members == 0:
            del self._teams[old_team_id]

    def set_evaluation(self, evaluation_id, rep_id, scores):
        """Insert or fully replace one evaluation."""
        rep = self._reps.get(rep_id)
        if rep is None:
            raise KeyError("unknown rep_id: %r" % (rep_id,))
        _validate_scores(scores)
        owner = self._eval_owner.get(evaluation_id)
        if owner is not None:
            if owner != rep_id:
                raise ValueError("evaluation %r already belongs to another rep" % (evaluation_id,))
            self._rep_comp_add_scores(rep, rep.evals[evaluation_id], -1)
        else:
            self._eval_owner[evaluation_id] = rep_id
        rep.evals[evaluation_id] = dict(scores)
        self._rep_comp_add_scores(rep, scores, +1)

    def remove_evaluation(self, evaluation_id):
        """Remove an evaluation; removing twice is a no-op."""
        owner = self._eval_owner.pop(evaluation_id, None)
        if owner is None:
            return
        rep = self._reps[owner]
        scores = rep.evals.pop(evaluation_id)
        self._rep_comp_add_scores(rep, scores, -1)

    def gaps(self, scope, id):
        """Return the up-to-two lowest-mean competencies for a rep/team.

        Returns a list of (competency_id, Fraction mean), ordered by exact
        mean ascending, ties by competency_id ascending.
        """
        if scope == "rep":
            state = self._reps.get(id)
            if state is None:
                raise KeyError("unknown rep_id: %r" % (id,))
        elif scope == "team":
            state = self._teams.get(id)
            if state is None:
                raise KeyError("unknown team_id: %r" % (id,))
        else:
            raise ValueError("scope must be 'rep' or 'team'")
        return [(comp_id, mean) for mean, comp_id in state.tree.smallest(2)]
