"""Coarse probe: five fidelity axes on MotriX, N=50 per cell."""
import sys
sys.path.insert(0, "src")
import numpy as np
from simleapx.sim import Fidelity, Task
from simleapx.policy import run_episode

task = Task(goal=np.array([1.0, 0.0]), goal_radius=0.18, t_max=12.0)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 50

ok = sum(run_episode(task, Fidelity(), seed=s)[0] for s in range(N))
print(f"reference: {ok}/{N}", flush=True)

for name, values in [
    ("mu",  [1.00, 0.80, 0.60, 0.50, 0.40, 0.30, 0.25, 0.20, 0.18, 0.15, 0.12, 0.10, 0.08]),
    ("dt",  [0.004, 0.010, 0.015, 0.020, 0.025, 0.030, 0.035, 0.040, 0.050, 0.060, 0.080, 0.100]),
    ("k",   [1.00, 0.60, 0.40, 0.30, 0.20, 0.15, 0.12, 0.10, 0.08, 0.06, 0.05, 0.03]),
    ("noise", [0.00, 0.01, 0.02, 0.03, 0.04, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20]),
    ("delay", [0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]),
]:
    print(f"\n=== {name} ===", flush=True)
    for v in values:
        fid = Fidelity()
        setattr(fid, name, v)
        ok = sum(run_episode(task, fid, seed=s)[0] for s in range(N))
        print(f"  {name}={v:5.3f}  rate={ok/N:5.2f}  ({ok}/{N})", flush=True)
