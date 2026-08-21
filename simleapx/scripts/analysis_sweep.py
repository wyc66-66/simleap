"""Formal fidelity sweep for SimLeapX (MotriX): N seeds per config, saved JSON.

For each fidelity axis, the reference value is swept to the degraded side and
the policy (calibrated once at reference) is replayed unchanged. Success rates
are binomially distributed, so the 95% confidence interval is the Wilson
interval. The "deployment gate" is the largest degradation at which the lower
CI bound still exceeds 50%.
"""
import sys
import json
import time
import math

sys.path.insert(0, "src")
import numpy as np
from simleapx.sim import Fidelity, Task
from simleapx.policy import run_episode


N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
task = Task(goal=np.array([1.0, 0.0]), goal_radius=0.18, t_max=12.0)

AXES = {
    "mu":    [1.00, 0.80, 0.60, 0.50, 0.40, 0.30, 0.25, 0.20, 0.18, 0.15, 0.12, 0.10],
    "dt":    [0.004, 0.010, 0.015, 0.020, 0.025, 0.030, 0.035, 0.040, 0.060, 0.100],
    "k":     [1.00, 0.60, 0.40, 0.30, 0.20, 0.15, 0.12, 0.10, 0.08, 0.06, 0.05,
              0.03, 0.01, 0.005],
    "noise": [0.00, 0.01, 0.02, 0.03, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20,
              0.25, 0.30, 0.40, 0.50, 0.60],
    "delay": [0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40],
}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return centre - half, centre + half


def main() -> None:
    t0 = time.time()
    results = {"N": N, "engine": "MotriX (GS-Playground)",
               "task": {"goal": task.goal.tolist(),
                        "goal_radius": task.goal_radius, "t_max": task.t_max},
               "axes": {}}

    # reference
    ok = sum(run_episode(task, Fidelity(), seed=s)[0] for s in range(N))
    lo, hi = wilson(ok, N)
    results["reference"] = {"ok": ok, "rate": ok / N, "ci": [lo, hi]}
    print(f"reference: {ok}/{N}  rate={ok/N:.3f}", flush=True)

    for name, values in AXES.items():
        print(f"\n=== axis {name} ===", flush=True)
        results["axes"][name] = []
        for v in values:
            fid = Fidelity()
            setattr(fid, name, v)
            ok = sum(run_episode(task, fid, seed=s)[0] for s in range(N))
            lo, hi = wilson(ok, N)
            results["axes"][name].append(
                {"value": v, "ok": ok, "rate": ok / N, "ci": [lo, hi]})
            print(f"  {name}={v:6.3f}  rate={ok/N:5.3f}  ci=[{lo:.3f},{hi:.3f}]", flush=True)

    # deployment gate per axis (largest degradation whose lower CI still >= 0.5)
    results["deployment_gates"] = {}
    results["no_cliff"] = {}
    for name, pts in results["axes"].items():
        gate = None
        for pt in pts:
            if pt["ci"][0] >= 0.5:
                gate = pt["value"]
            else:
                break
        results["deployment_gates"][name] = gate
        # an axis that never drops below 90% inside the grid has no cliff in
        # the tested range — the "gate" is then the grid floor, not a cliff.
        results["no_cliff"][name] = min(p["rate"] for p in pts) >= 0.9
    print("\ndeployment gates:", results["deployment_gates"], flush=True)
    print("no_cliff:", results["no_cliff"], flush=True)

    out = "results/sweep.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nwrote {out}  ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
