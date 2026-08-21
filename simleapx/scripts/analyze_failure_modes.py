"""Failure-mode classification for the fidelity cliffs (MotriX).

For each axis's cliff-adjacent cells, classify every failed episode by *how*
it failed, so a digital-twin engineer can look at a failure and invert it back
to the offending fidelity knob:

- runaway:     the block escaped the table (|pos| > bound) — stale world model;
- edge-fail:   the block stopped within a radius of the goal but never entered
               it — the whole push succeeded, only the *endgame* was wrong
               (too little friction / coarse control / stale state -> the block
               coasts past the goal edge or stops just short);
- in-goal-fail: the block entered the goal but never came to rest (coasting
               through the far edge, or timed out inside the goal);
- stalled:     the block ended far from the goal — the push itself failed
               (contact too soft to transmit, or control unable to track).
"""
import sys
import json
import os

sys.path.insert(0, "src")
import numpy as np
from simleapx.sim import Fidelity, Task
from simleapx.policy import run_episode

N = 200
task = Task(goal=np.array([1.0, 0.0]), goal_radius=0.18, t_max=12.0)

CELLS = {
    "mu_f0.18":   Fidelity(mu=0.18),
    "mu_f0.15":   Fidelity(mu=0.15),
    "dt_0.030":   Fidelity(dt=0.030),
    "dt_0.035":   Fidelity(dt=0.035),
    "k_0.005":    Fidelity(k=0.005),
    "noise_0.30": Fidelity(noise=0.30),
    "noise_0.60": Fidelity(noise=0.60),
    "delay_0.25": Fidelity(delay=0.25),
    "delay_0.30": Fidelity(delay=0.30),
}

EDGE = 0.6  # "near the goal": within 60 cm of it


def classify(st: dict) -> str:
    if st["escaped"]:
        return "runaway"
    if st["in_goal"]:
        return "in-goal-fail"      # inside the goal but never came to rest
    if st["dist_to_goal"] < EDGE:
        return "edge-fail"         # push succeeded, endgame failed
    return "stalled"               # push itself failed


def main() -> None:
    out = {}
    print(f"failure-mode distribution, N={N} seeds, MotriX "
          f"(edge = dist_to_goal < {EDGE} m):")
    print(f"  {'cell':<12} {'rate':>5}  {'edge-fail':>9} {'in-goal':>7} "
          f"{'stalled':>7} {'runaway':>7}  {'med_dist':>8}")
    for key, fid in CELLS.items():
        c = {"edge-fail": 0, "in-goal-fail": 0, "stalled": 0, "runaway": 0}
        dists = []
        ok = 0
        for s in range(N):
            s_ok, st = run_episode(task, fid, seed=s)
            if s_ok:
                ok += 1
            else:
                c[classify(st)] += 1
                dists.append(st["dist_to_goal"])
        med = np.median(dists) if dists else float("nan")
        out[key] = {"axis": fid, "ok": ok, "class": c, "median_dist": med}
        print(f"  {key:<12} {ok/N:5.2f}  {c['edge-fail']:9d} "
              f"{c['in-goal-fail']:7d} {c['stalled']:7d} {c['runaway']:7d}  "
              f"{med:8.3f}", flush=True)

    with open("results/failure_modes.json", "w") as f:
        json.dump({"N": N, "edge_radius": EDGE,
                   "cells": {k: {"ok": v["ok"],
                                 "class": v["class"],
                                 "median_dist": v["median_dist"]}
                             for k, v in out.items()}}, f, indent=2)
    print("wrote results/failure_modes.json")


if __name__ == "__main__":
    main()
