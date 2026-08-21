"""Verify MotriX combines contact friction as the max of the pair (as MuJoCo).

Protocol knob: floor geom friction = `mu`, block geom friction pinned at 0.1.
This only behaves as an honest friction knob if the effective contact friction
is driven by the *larger* member of the pair. Test: with the floor pinned high
(1.0), sweeping the block's own friction must have no effect on the task; if it
did, the effective friction would be following the smaller member and the `mu`
axis would not be measuring what it claims to.

Prints a table of task reliability vs block friction (expect all 100%).
"""
import sys
sys.path.insert(0, "src")
import numpy as np
from motrixsim import load_mjcf_str
from simleapx.sim import Fidelity, Task, PushSimX, _BASE_XML
from simleapx.policy import push_policy, reference_gains, run_episode

N = 40
task = Task(goal=np.array([1.0, 0.0]), goal_radius=0.18, t_max=12.0)


def build_with_block_friction(block_mu: float):
    """Same MJCF as sim.py but with a configurable block-geom friction."""
    timeconst = 0.02 / 1.0
    xml = _BASE_XML.format(h=f"{PushSimX.H:.6f}", mu="1.0000",
                           timeconst=f"{timeconst:.4f}")
    xml = xml.replace('friction="0.1 0.005 0.0001" solref=',
                      f'friction="{block_mu:.4f} 0.005 0.0001" solref=')
    return load_mjcf_str(xml)


def run_model(model, seed):
    sim = PushSimX(task, Fidelity(), seed=seed, model=model)
    g = reference_gains()
    n_sub = max(1, int(round(Fidelity().dt / PushSimX.H)))
    for _ in range(1_000_000):
        st = sim.status()
        if st["success"] or st["escaped"] or st["timed_out"]:
            return st["success"]
        a = push_policy(sim, g)
        sim.step(a, n_sub)
    return sim.status()["success"]


print("block-friction sweep with floor pinned at 1.0 "
      "(max-of-pair => no effect expected):")
for bm in [1.00, 0.50, 0.30, 0.20, 0.15, 0.12, 0.10, 0.08, 0.05]:
    model = build_with_block_friction(bm)
    ok = sum(run_model(model, s) for s in range(N))
    print(f"  block_mu={bm:5.2f}  rate={ok/N:5.2f}  ({ok}/{N})", flush=True)

assert ok == N, "block friction sweep changed the task -> not max-of-pair"
print("\nOK: MotriX combines contact friction as the max of the pair.")
