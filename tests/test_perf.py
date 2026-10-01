"""Scale and churn test: 200k live evaluations, then 100k corrections.

Run directly (``python3 tests/test_perf.py``) or via pytest. Takes a few
minutes; it is excluded from the default correctness run via the
``perf`` marker.
"""

import gc
import random
import resource
import sys
import time

import pytest

from skillgap import SkillGapTracker

# ru_maxrss is KiB on Linux, bytes on macOS
_RSS_DIV = 1024 if sys.platform.startswith("linux") else 1024 * 1024

N_REPS = 20_000
N_TEAMS = 200
N_COMPS = 2_000
EVALS_PER_REP = 10  # 200k live evaluations
COMPS_PER_EVAL = 12
N_SURVIVOR_REPS = 200
N_CHURN_OPS = 100_000


def _index_sizes(t):
    return {
        "evals": len(t._evals),
        "reps": len(t._rep_team),
        "teams": len(t._team_members),
        "rep_comp_entries": sum(len(h) for h in t._rep_heaps.values()),
        "team_comp_entries": sum(len(h) for h in t._team_heaps.values()),
        "rep_stat_entries": sum(len(s) for s in t._rep_stats.values()),
        "team_stat_entries": sum(len(s) for s in t._team_stats.values()),
    }


def run_perf():
    rng = random.Random(42)
    t = SkillGapTracker()

    for r in range(N_REPS):
        t.move_rep(r, r % N_TEAMS)

    # ---- load 200k evaluations ----
    start = time.perf_counter()
    eid = 0
    for r in range(N_REPS):
        for _ in range(EVALS_PER_REP):
            comps = rng.sample(range(N_COMPS), COMPS_PER_EVAL)
            t.set_evaluation(eid, r, {c: rng.randint(1, 10) for c in comps})
            eid += 1
    load_s = time.perf_counter() - start
    n_evals = eid

    # ---- query timing at full scale ----
    start = time.perf_counter()
    n_queries = 10_000
    for i in range(n_queries):
        if i % 2:
            t.gaps("rep", rng.randrange(N_REPS))
        else:
            t.gaps("team", rng.randrange(N_TEAMS))
    query_s = time.perf_counter() - start

    sizes_full = _index_sizes(t)

    # ---- shrink to a small surviving set ----
    survivor_reps = list(range(N_SURVIVOR_REPS))
    survivor_evals = []
    for r in survivor_reps:
        survivor_evals.extend(range(r * EVALS_PER_REP, r * EVALS_PER_REP + 5))
    survivor_set = set(survivor_evals)
    start = time.perf_counter()
    for e in range(n_evals):
        if e not in survivor_set:
            t.remove_evaluation(e)
    shrink_s = time.perf_counter() - start

    sizes_shrunk = _index_sizes(t)

    # ---- 100k corrections / moves on the surviving set ----
    gc.collect()
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    start = time.perf_counter()
    for i in range(N_CHURN_OPS):
        op = rng.random()
        if op < 0.7:
            e = rng.choice(survivor_evals)
            r = e // EVALS_PER_REP
            comps = rng.sample(range(N_COMPS), COMPS_PER_EVAL)
            t.set_evaluation(e, r, {c: rng.randint(1, 10) for c in comps})
        else:
            r = rng.choice(survivor_reps)
            t.move_rep(r, rng.randrange(N_TEAMS))
        if i % 10 == 0:
            t.gaps("team", rng.randrange(N_TEAMS))
    churn_s = time.perf_counter() - start
    gc.collect()
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    sizes_after = _index_sizes(t)

    print(f"\nloaded {n_evals} evals in {load_s:.1f}s "
          f"({n_evals / load_s:,.0f} evals/s)")
    print(f"{n_queries} gap queries at full scale in {query_s:.3f}s "
          f"({query_s / n_queries * 1e6:.1f} us/query)")
    print(f"removed {n_evals - len(survivor_set)} evals in {shrink_s:.1f}s")
    print(f"{N_CHURN_OPS} churn ops in {churn_s:.1f}s "
          f"({churn_s / N_CHURN_OPS * 1e6:.1f} us/op)")
    print(f"index sizes at full scale : {sizes_full}")
    print(f"index sizes after shrink  : {sizes_shrunk}")
    print(f"index sizes after churn   : {sizes_after}")
    print(f"peak rss before/after churn: {rss_before / _RSS_DIV:.0f} MiB / "
          f"{rss_after / _RSS_DIV:.0f} MiB (high-water mark incl. full scale)")

    # no accumulated history garbage: after churn, index sizes must match
    # the live data, not the cumulative operation count
    assert sizes_after["evals"] == len(survivor_set)
    assert sizes_after["rep_comp_entries"] == sizes_after["rep_stat_entries"]
    assert sizes_after["team_comp_entries"] == sizes_after["team_stat_entries"]
    live_comps_per_rep = COMPS_PER_EVAL * 5  # up to 60 distinct per rep
    assert sizes_after["rep_comp_entries"] <= N_SURVIVOR_REPS * live_comps_per_rep
    assert sizes_after["teams"] <= N_TEAMS
    return {
        "load_s": load_s,
        "query_us": query_s / n_queries * 1e6,
        "churn_us": churn_s / N_CHURN_OPS * 1e6,
    }


@pytest.mark.perf
def test_perf():
    run_perf()


if __name__ == "__main__":
    run_perf()
