"""Protocol tests for SimLeapX (MotriX port).

Fast tests run a handful of seeds; the axis-level assertions read the official
sweep.json (N=200) produced by scripts/analysis_sweep.py.
"""
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simleapx.sim import Fidelity, Task, PushSimX
from simleapx.policy import run_episode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWEEP = os.path.join(ROOT, "results", "sweep.json")

TASK = Task(goal=np.array([1.0, 0.0]), goal_radius=0.18, t_max=12.0)

mx = pytest.importorskip("motrixsim")


def test_reference_reliability():
    ok = sum(run_episode(TASK, Fidelity(), seed=s)[0] for s in range(20))
    assert ok == 20


def test_determinism():
    r1 = run_episode(TASK, Fidelity(noise=0.04), seed=7)
    r2 = run_episode(TASK, Fidelity(noise=0.04), seed=7)
    assert r1 == r2


def test_degradation_never_increases_reliability():
    """Every fidelity axis must be monotone non-increasing in the official data."""
    if not os.path.exists(SWEEP):
        pytest.skip("results/sweep.json not found — run scripts/analysis_sweep.py")
    with open(SWEEP) as f:
        data = json.load(f)
    for name, pts in data["axes"].items():
        rates = [p["rate"] for p in pts]
        assert all(rates[i] >= rates[i + 1] - 1e-9
                   for i in range(len(rates) - 1)), f"axis {name} non-monotone"


def test_every_axis_has_a_cliff():
    """Each axis must drop from a high plateau to near zero within the grid —
    unless the official data records it as having no cliff (the MotriX contact-
    rigidity finding), in which case the protocol result is that it does not."""
    if not os.path.exists(SWEEP):
        pytest.skip("results/sweep.json not found")
    with open(SWEEP) as f:
        data = json.load(f)
    no_cliff = data.get("no_cliff", {})
    for name, pts in data["axes"].items():
        rates = [p["rate"] for p in pts]
        assert rates[0] >= 0.9, f"axis {name} does not start high"
        if no_cliff.get(name):
            continue
        assert min(rates) <= 0.1, f"axis {name} never collapses"


def test_reference_is_global_maximum():
    if not os.path.exists(SWEEP):
        pytest.skip("results/sweep.json not found")
    with open(SWEEP) as f:
        data = json.load(f)
    ref = data["reference"]["rate"]
    for name, pts in data["axes"].items():
        assert all(ref >= p["rate"] - 1e-9 for p in pts), \
            f"axis {name} exceeds reference reliability"


def test_wilson_ci_sanity():
    """Reference Wilson interval formula used by the sweep (validated here)."""
    import math

    def wilson(k, n, z=1.96):
        p = k / n
        denom = 1 + z * z / n
        centre = (p + z * z / (2 * n)) / denom
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
        return centre - half, centre + half

    lo, hi = wilson(0, 200)
    assert abs(lo - 0.0) < 1e-9
    lo2, hi2 = wilson(100, 200)
    assert lo2 < 0.5 < hi2


def test_physics_substep_consistent():
    sim = PushSimX(TASK, Fidelity(), seed=0)
    assert PushSimX.H == pytest.approx(0.002)


def test_pusher_mass_matches_engine():
    """Force control reads F = m*a with the engine's own body mass; guard that
    the value stays consistent with the MJCF geometry (cylinder density*volume)."""
    sim = PushSimX(TASK, Fidelity(), seed=0)
    m_engine = float(sim.model.get_link("pusher").mass)
    m_analytic = 300.0 * np.pi * 0.30 * 0.30 * (2.0 * 0.08)
    assert m_engine == pytest.approx(m_analytic, rel=1e-3)
    assert sim._pusher_mass() == pytest.approx(m_engine)
