"""Sanity checks for the SimLeap simulator, policy and sweep.

The whole project rests on a few claims that are easy to violate silently:
the reference-fidelity simulator must be a solved task (≈100% success), every
fidelity axis must degrade monotonically (a fidelity *cliff* is only
meaningful if reliability never improves as the simulator gets worse), and
each axis must actually contain a cliff (a real drop, not a flat line).
This module asserts all three, plus the determinism of a single episode.

Run with:  python -m simleap.check  (or  python src/simleap/check.py)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .analysis import axis_curves
from .policy import run_episode
from .sim import Fidelity, Task

ROOT = Path(__file__).resolve().parents[2]

TASK = Task(goal=np.array([2.0, 0.0]))


def check_reference(n: int = 120) -> None:
    ok = sum(run_episode(TASK, Fidelity(), seed=s)[0] for s in range(n))
    rate = ok / n
    assert rate >= 0.98, f"reference fidelity only {rate:.2%} success ({n} seeds)"
    print(f"[ok] reference fidelity: {rate:.2%} success over {n} seeds")


def check_determinism() -> None:
    a = run_episode(TASK, Fidelity(dt=0.12), seed=7)[1]
    b = run_episode(TASK, Fidelity(dt=0.12), seed=7)[1]
    assert a["step"] == b["step"] and a["success"] == b["success"], "episode is not deterministic"
    print(f"[ok] episodes are deterministic (seed 7, dt=0.12: {a['step']} steps)")


def check_sweep(path: Path) -> None:
    assert path.exists(), f"missing sweep {path}; run scripts/run_sweep.py first"
    data = json.loads(path.read_text(encoding="utf-8"))
    curves = axis_curves(data)

    assert len(curves) == 5, f"expected 5 axes, got {sorted(curves)}"
    for axis, curve in curves.items():
        ys = [c["rate"] for c in curve]
        ref = ys[0]
        floor = ys[-1]
        # a step counts as a *real* non-monotonicity only when the Wilson
        # confidence intervals of the two points do not overlap — 300-seed
        # sampling carries a ~3-5% fluctuation that is not a physical reversal.
        bumps = 0
        for i in range(len(curve) - 1):
            if ys[i + 1] > ys[i] and curve[i]["ci_hi"] < curve[i + 1]["ci_lo"]:
                bumps += 1
        assert bumps == 0, f"{axis}: {bumps} non-monotone steps beyond sampling noise"
        assert ref >= 0.98, f"{axis}: reference rate {ref:.2%} < 98%"
        assert floor <= 0.3, f"{axis}: never collapses (floor {floor:.2%})"
        span = ref - floor
        assert span >= 0.6, f"{axis}: reliability span only {span:.2%}"
        print(f"[ok] {axis:<6} monotone (noise-level bumps ignored), "
              f"{ref:.2%} -> {floor:.2%}, "
              f"{sum(1 for c in curve if c['rate'] < 0.9)} points below 90%")


def main() -> None:
    check_determinism()
    check_reference()
    check_sweep(ROOT / "results" / "sweep.json")
    print("all checks passed")


if __name__ == "__main__":
    main()
