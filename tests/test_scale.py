"""Scale and stability test: 200k live evaluations, then 100k
corrections/transfers over a small surviving set, with timing and
index-size evidence that no historical garbage accumulates."""

import random
import time
import tracemalloc
import unittest

from skill_gaps import SkillGapTracker

N_REPS = 20_000
N_TEAMS = 50
N_COMPS = 2_000
N_EVALS = 200_000
EVALS_PER_REP = N_EVALS // N_REPS  # 10, within the 100/rep limit
N_SURVIVORS = 200
N_CHURN_OPS = 100_000


def _index_sizes(tracker):
    """Sizes of every internal index, derived only from live data."""
    rep_comp_entries = sum(len(r.comp) for r in tracker._reps.values())
    rep_tree_nodes = sum(len(r.tree) for r in tracker._reps.values())
    rep_evals = sum(len(r.evals) for r in tracker._reps.values())
    team_comp_entries = sum(len(t.comp) for t in tracker._teams.values())
    team_tree_nodes = sum(len(t.tree) for t in tracker._teams.values())
    return {
        "reps": len(tracker._reps),
        "teams": len(tracker._teams),
        "eval_owner": len(tracker._eval_owner),
        "rep_evals": rep_evals,
        "rep_comp_entries": rep_comp_entries,
        "rep_tree_nodes": rep_tree_nodes,
        "team_comp_entries": team_comp_entries,
        "team_tree_nodes": team_tree_nodes,
    }


class ScaleTest(unittest.TestCase):
    def test_scale_and_churn(self):
        rng = random.Random(26100248)
        tracker = SkillGapTracker()

        # ---- phase 1: build 200k live evaluations ----
        t0 = time.perf_counter()
        for i in range(N_REPS):
            tracker.move_rep(f"rep{i}", f"team{i % N_TEAMS}")
        eval_no = 0
        for i in range(N_REPS):
            for j in range(EVALS_PER_REP):
                k = rng.randint(3, 12)
                scores = {c: rng.randint(1, 10)
                          for c in rng.sample(range(N_COMPS), k)}
                tracker.set_evaluation(f"ev{eval_no}", f"rep{i}", scores)
                eval_no += 1
        build_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        for i in range(1000):
            tracker.gaps("team", f"team{i % N_TEAMS}")
            tracker.gaps("rep", f"rep{i}")
        query_s = (time.perf_counter() - t0) / 2000

        sizes_full = _index_sizes(tracker)
        self.assertEqual(sizes_full["eval_owner"], N_EVALS)
        self.assertEqual(sizes_full["rep_evals"], N_EVALS)

        # ---- phase 2: shrink to a small surviving set ----
        survivors = [f"rep{i}" for i in range(0, N_REPS, N_REPS // N_SURVIVORS)]
        survivor_set = set(survivors)
        live_evals = []
        for i in range(N_REPS):
            rep = f"rep{i}"
            for j in range(EVALS_PER_REP):
                eval_id = f"ev{i * EVALS_PER_REP + j}"
                if rep in survivor_set and j == 0:
                    live_evals.append((eval_id, rep))
                else:
                    tracker.remove_evaluation(eval_id)
        self.assertEqual(len(tracker._eval_owner), len(live_evals))

        # ---- phase 3: 100k corrections/transfers over survivors ----
        tracemalloc.start()
        sizes_before = _index_sizes(tracker)
        mem_before = tracemalloc.take_snapshot()
        modify_s = 0.0
        query_total_s = 0.0
        n_queries = 0
        size_samples = []
        for step in range(N_CHURN_OPS):
            t0 = time.perf_counter()
            if step % 3 == 2:
                rep = rng.choice(survivors)
                tracker.move_rep(rep, f"team{rng.randrange(N_TEAMS)}")
            else:
                eval_id, rep = live_evals[rng.randrange(len(live_evals))]
                k = rng.randint(3, 12)
                scores = {c: rng.randint(1, 10)
                          for c in rng.sample(range(N_COMPS), k)}
                tracker.set_evaluation(eval_id, rep, scores)
            modify_s += time.perf_counter() - t0
            if step % 10 == 0:
                t0 = time.perf_counter()
                tracker.gaps("rep", rng.choice(survivors))
                tracker.gaps("team", f"team{rng.randrange(N_TEAMS)}")
                query_total_s += time.perf_counter() - t0
                n_queries += 2
            if step % (N_CHURN_OPS // 4) == 0:
                size_samples.append(_index_sizes(tracker))
        size_samples.append(_index_sizes(tracker))
        mem_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # ---- evidence report ----
        mem_diff = sum(
            stat.size_diff for stat in mem_after.compare_to(mem_before, "filename")
        )
        print()
        print(f"[scale] build {N_EVALS} evals: {build_s:.2f}s "
              f"({N_EVALS / build_s:,.0f} eval/s)")
        print(f"[scale] avg gaps() at full scale: {query_s * 1e6:.1f} us")
        print(f"[scale] churn {N_CHURN_OPS} mods: {modify_s:.2f}s "
              f"({N_CHURN_OPS / modify_s:,.0f} mod/s), "
              f"avg query {query_total_s / n_queries * 1e6:.1f} us")
        print(f"[scale] index sizes at full scale: {sizes_full}")
        print(f"[scale] index sizes before churn: {sizes_before}")
        for sample in size_samples:
            print(f"[scale]   churn sample: {sample}")
        print(f"[scale] tracemalloc net diff over churn: {mem_diff:+,} bytes")

        # ---- assertions: no growth with accumulated history ----
        # Structure-only indexes are exactly constant across the churn.
        for key in ("reps", "eval_owner", "rep_evals"):
            for sample in size_samples:
                self.assertEqual(sample[key], sizes_before[key], key)
        # Content-dependent indexes fluctuate with random score content,
        # but every index entry traces back to a live evaluation, so all
        # sizes are hard-bounded by the surviving data (200 evals x <=12
        # competencies), never by the 100k accumulated modifications.
        live_bound = N_SURVIVORS * 12
        for key in ("rep_comp_entries", "rep_tree_nodes"):
            for sample in size_samples:
                self.assertLessEqual(sample[key], live_bound, key)
        for key in ("team_comp_entries", "team_tree_nodes"):
            for sample in size_samples:
                self.assertLessEqual(sample[key], live_bound, key)
        for sample in size_samples:
            self.assertLessEqual(sample["teams"], N_TEAMS)
        self.assertLess(abs(mem_diff), 5_000_000,
                        "memory grew during churn: historical garbage?")


if __name__ == "__main__":
    unittest.main()
