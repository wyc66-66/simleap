"""Run the fidelity-budget sweep for SimLeap.

For every axis (control period ``dt``, friction ``mu``, contact ``k``,
sensor noise, observation delay) the policy calibrated at the reference
fidelity is replayed, unchanged, across a monotone degradation grid. The
success rate at each grid point is the *transfer reliability* at that budget.

Results are checkpointed to ``results/sweep.json`` after every grid cell so
an interrupted run can be resumed with ``--resume``.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from simleap.policy import run_episode
from simleap.sim import Fidelity, Task

ROOT = Path(__file__).resolve().parents[1]

# monotone degradation grids. The first entry of every axis is the reference.
GRIDS = {
    "dt": [0.010, 0.020, 0.040, 0.060, 0.080, 0.100, 0.110, 0.120, 0.130,
           0.140, 0.150, 0.160, 0.170, 0.180, 0.200, 0.250],
    "mu": [0.80, 0.60, 0.50, 0.45, 0.40, 0.35, 0.30, 0.27, 0.25, 0.23,
           0.21, 0.20, 0.19, 0.185, 0.18, 0.175, 0.17, 0.15],
    "k": [1.00, 0.85, 0.70, 0.60, 0.55, 0.50, 0.47, 0.455, 0.45, 0.445,
          0.44, 0.435, 0.43, 0.425, 0.41, 0.38, 0.34, 0.30],
    "noise": [0.00, 0.05, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.22, 0.24,
              0.28, 0.32, 0.40, 0.50, 0.65, 0.80],
    "delay": [0.00, 0.05, 0.10, 0.14, 0.18, 0.20, 0.22, 0.24, 0.26, 0.27,
              0.28, 0.29, 0.30, 0.35, 0.40, 0.50],
}
N_SEEDS = 300


def _worker(args: tuple) -> dict:
    axis, value, seed, task = args
    fid = Fidelity()
    setattr(fid, axis, value)
    ok, status = run_episode(task, fid, seed=seed)
    return {
        "ok": ok,
        "in_goal": status["in_goal"],
        "stopped": status["stopped"],
        "escaped": status["escaped"],
        "timed_out": status["timed_out"],
        "dist": round(status["dist_to_goal"], 4),
        "steps": status["step"],
    }


def run_cell(axis: str, value: float, task: Task, n_proc: int) -> dict:
    jobs = [(axis, value, s, task) for s in range(N_SEEDS)]
    with mp.Pool(n_proc) as pool:
        rows = pool.map(_worker, jobs, chunksize=8)
    ok = sum(r["ok"] for r in rows)
    return {
        "axis": axis,
        "value": float(value),
        "n": len(rows),
        "success": ok,
        "rate": ok / len(rows),
        "in_goal_rate": sum(r["in_goal"] for r in rows) / len(rows),
        "timeout_rate": sum(r["timed_out"] for r in rows) / len(rows),
        "escaped_rate": sum(r["escaped"] for r in rows) / len(rows),
        "mean_dist": round(np.mean([r["dist"] for r in rows]), 4),
        "mean_steps": round(np.mean([r["steps"] for r in rows]), 1),
        "steps": [r["steps"] for r in rows],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "sweep.json")
    ap.add_argument("--n-proc", type=int, default=min(4, mp.cpu_count()))
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--cool-down", type=float, default=1.0,
                    help="seconds to idle between grid cells (keeps the laptop cool)")
    args = ap.parse_args()

    global N_SEEDS
    N_SEEDS = args.seeds

    task = Task(goal=np.array([2.0, 0.0]))

    cells: list[dict] = []
    meta = {"reference": asdict(Fidelity()), "grids": GRIDS, "n_seeds": N_SEEDS}

    if args.resume and args.out.exists():
        prev = json.loads(args.out.read_text(encoding="utf-8"))
        cells = [c for c in prev["cells"] if c["n"] >= N_SEEDS]
        meta["grids"] = prev["meta"]["grids"]
        print(f"[simleap] resumed with {len(cells)} cells", flush=True)

    # normalize axis values to a 0..1 budget where 1 = reference fidelity.
    # Axes degrade in *different directions* (dt/noise/delay grow, mu/k shrink),
    # so budget is the distance from the reference, not a global hi-lo map.
    budget_of = {}
    for axis, vals in GRIDS.items():
        ref = vals[0]
        span = abs(vals[-1] - ref) + 1e-12
        budget_of[axis] = {round(v, 6): round(1.0 - abs(v - ref) / span, 4)
                           for v in vals}

    done = set((c["axis"], c["value"]) for c in cells)
    all_cells = [(a, v) for a, vals in GRIDS.items() for v in vals]
    total = len(all_cells)
    n_ok = 0
    for i, (axis, value) in enumerate(all_cells):
        if (axis, value) in done:
            n_ok += 1
            continue
        rec = run_cell(axis, value, task, args.n_proc)
        rec["budget"] = budget_of[axis][round(value, 6)]
        cells.append(rec)
        n_ok += 1
        rate = rec["rate"]
        print(f"[simleap] {i + 1}/{total} {axis}={value:.3f} "
              f"budget={rec['budget']:.2f} rate={rate:.3f}", flush=True)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"meta": meta, "cells": cells}, indent=1), encoding="utf-8"
        )
        tmp.replace(args.out)
        if args.cool_down > 0:
            time.sleep(args.cool_down)
    print(f"[simleap] done: {n_ok}/{total} cells -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
