"""Incremental skill-gap tracker.

Maintains, per rep and per team, exact rational means per competency so
that bottom-2 gap queries are answered from small indexed heaps without
scanning evaluations, members, or the full competency space.
"""

from fractions import Fraction
from typing import Dict, List, Mapping, Tuple

from .heap import IndexedMinHeap

MIN_COMPETENCIES = 3
MAX_COMPETENCIES = 12
MIN_SCORE = 1
MAX_SCORE = 10

SCOPE_REP = "rep"
SCOPE_TEAM = "team"


class SkillGapTracker:
    """Tracks rep evaluations and answers bottom-2 gap queries exactly.

    Public means are returned as ``fractions.Fraction`` so results are
    lossless and comparisons never involve rounding or float tolerance.
    """

    def __init__(self) -> None:
        self._rep_team: Dict[int, int] = {}
        self._team_members: Dict[int, set] = {}
        self._evals: Dict[int, Tuple[int, Dict[int, int]]] = {}
        # rep_id -> {competency_id: [total_score, eval_count]}
        self._rep_stats: Dict[int, Dict[int, List[int]]] = {}
        self._rep_heaps: Dict[int, IndexedMinHeap] = {}
        # team_id -> {competency_id: [sum_of_member_means (Fraction), member_count]}
        self._team_stats: Dict[int, Dict[int, List]] = {}
        self._team_heaps: Dict[int, IndexedMinHeap] = {}

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def move_rep(self, rep_id: int, team_id: int) -> None:
        """Register a rep on first call; transfer teams afterwards."""
        old_team = self._rep_team.get(rep_id)
        if old_team is None:
            self._rep_team[rep_id] = team_id
            self._team_members.setdefault(team_id, set()).add(rep_id)
            return
        if old_team == team_id:
            return
        self._team_members[old_team].discard(rep_id)
        self._team_members.setdefault(team_id, set()).add(rep_id)
        self._rep_team[rep_id] = team_id
        stats = self._rep_stats.get(rep_id)
        if stats:
            for competency_id, (total, count) in list(stats.items()):
                mean = Fraction(total, count)
                self._team_contribute(old_team, competency_id, -mean, -1)
                self._team_contribute(team_id, competency_id, mean, 1)
        if not self._team_members[old_team]:
            del self._team_members[old_team]
            self._team_stats.pop(old_team, None)
            self._team_heaps.pop(old_team, None)

    def set_evaluation(
        self, evaluation_id: int, rep_id: int, scores: Mapping[int, int]
    ) -> None:
        """Insert or fully replace an evaluation."""
        self._validate_scores(scores)
        if rep_id not in self._rep_team:
            raise KeyError(f"unregistered rep: {rep_id!r}")
        existing = self._evals.get(evaluation_id)
        if existing is not None:
            old_rep, old_scores = existing
            if old_rep != rep_id:
                raise ValueError("an evaluation cannot change rep")
            for competency_id, score in old_scores.items():
                self._change_rep_comp(rep_id, competency_id, -score, -1)
        new_scores = dict(scores)
        for competency_id, score in new_scores.items():
            self._change_rep_comp(rep_id, competency_id, score, 1)
        self._evals[evaluation_id] = (rep_id, new_scores)

    def remove_evaluation(self, evaluation_id: int) -> None:
        """Remove an evaluation; repeated removal is a no-op."""
        existing = self._evals.pop(evaluation_id, None)
        if existing is None:
            return
        rep_id, scores = existing
        for competency_id, score in scores.items():
            self._change_rep_comp(rep_id, competency_id, -score, -1)

    def gaps(self, scope: str, id: int) -> List[Tuple[int, Fraction]]:
        """Return up to two (competency_id, exact mean) pairs, ascending."""
        if scope == SCOPE_REP:
            if id not in self._rep_team:
                raise KeyError(f"unregistered rep: {id!r}")
            heap = self._rep_heaps.get(id)
        elif scope == SCOPE_TEAM:
            if id not in self._team_members:
                raise KeyError(f"unknown team: {id!r}")
            heap = self._team_heaps.get(id)
        else:
            raise ValueError(f"unknown scope: {scope!r}")
        if heap is None:
            return []
        return heap.smallest(2)

    # ------------------------------------------------------------------
    # internal maintenance
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_scores(scores: Mapping[int, int]) -> None:
        n = len(scores)
        if not (MIN_COMPETENCIES <= n <= MAX_COMPETENCIES):
            raise ValueError(
                f"scores must cover {MIN_COMPETENCIES}..{MAX_COMPETENCIES} competencies"
            )
        for competency_id, score in scores.items():
            if not isinstance(competency_id, int) or isinstance(competency_id, bool):
                raise ValueError("competency ids must be integers")
            if (
                not isinstance(score, int)
                or isinstance(score, bool)
                or not (MIN_SCORE <= score <= MAX_SCORE)
            ):
                raise ValueError(f"score for {competency_id!r} must be 1..10")

    def _change_rep_comp(
        self, rep_id: int, competency_id: int, delta_sum: int, delta_count: int
    ) -> None:
        stats = self._rep_stats.setdefault(rep_id, {})
        old_sum, old_count = stats.get(competency_id, (0, 0))
        new_sum, new_count = old_sum + delta_sum, old_count + delta_count
        heap = self._rep_heaps.setdefault(rep_id, IndexedMinHeap())
        if new_count == 0:
            stats.pop(competency_id, None)
            heap.discard(competency_id)
        else:
            stats[competency_id] = [new_sum, new_count]
            heap.set(competency_id, Fraction(new_sum, new_count))
        team_id = self._rep_team[rep_id]
        if old_count:
            self._team_contribute(
                team_id, competency_id, -Fraction(old_sum, old_count), -1
            )
        if new_count:
            self._team_contribute(
                team_id, competency_id, Fraction(new_sum, new_count), 1
            )

    def _team_contribute(
        self, team_id: int, competency_id: int, delta_mean: Fraction, delta_members: int
    ) -> None:
        stats = self._team_stats.setdefault(team_id, {})
        old_sum, old_members = stats.get(competency_id, (Fraction(0), 0))
        new_sum = old_sum + delta_mean
        new_members = old_members + delta_members
        heap = self._team_heaps.setdefault(team_id, IndexedMinHeap())
        if new_members == 0:
            stats.pop(competency_id, None)
            heap.discard(competency_id)
        else:
            stats[competency_id] = [new_sum, new_members]
            heap.set(competency_id, new_sum / new_members)
