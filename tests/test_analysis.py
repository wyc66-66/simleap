"""Tests for SimLeap fidelity-budget analysis and the deterministic simulator."""
from __future__ import annotations

import json

import numpy as np
import pytest

from simleap.analysis import (
    axis_curves,
    find_cliff,
    load,
    monotonicity,
    summarize,
    wilson_interval,
)
from simleap.policy import run_episode
from simleap.sim import Fidelity, PushSim, Task

TASK = Task(goal=np.array([2.0, 0.0]))


# --------------------------------------------------------------------------- #
# Wilson interval
# --------------------------------------------------------------------------- #
class TestWilsonInterval:
    def test_bounds_at_zero(self):
        lo, hi = wilson_interval(0, 300)
        assert lo >= 0.0
        assert hi < 0.02

    def test_bounds_at_one(self):
        lo, hi = wilson_interval(300, 300)
        assert lo > 0.98
        assert hi <= 1.0

    def test_contains_p(self):
        lo, hi = wilson_interval(150, 300)
        assert lo <= 0.5 <= hi

    def test_zero_n(self):
        assert wilson_interval(0, 0) == (0.0, 0.0)


# --------------------------------------------------------------------------- #
# Cliff finding
# --------------------------------------------------------------------------- #
class TestFindCliff:
    def _curve(self, rates, budgets=None):
        if budgets is None:
            budgets = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4]
        return [
            {
                "value": float(b),
                "budget": float(b),
                "rate": float(r),
                "timeout_rate": 0.5,
                "escaped_rate": 0.5,
            }
            for b, r in zip(budgets, rates)
        ]

    def test_narrow_cliff_detected(self):
        # sharp drop between 0.8 and 0.7
        curve = self._curve([1.0, 0.98, 0.95, 0.05, 0.0, 0.0, 0.0])
        c = find_cliff(curve)
        assert c["safe_budget"] == pytest.approx(0.8)
        assert c["collapse_budget"] == pytest.approx(0.7)
        assert c["reaches_collapse"] is True
        assert c["critical_budget"] == pytest.approx(0.75, abs=0.05)
        assert c["cliff_width"] == pytest.approx(0.1)

    def test_reliability_floor_no_collapse(self):
        # sensor-noise-like axis: never reaches 10%
        curve = self._curve([1.0, 0.95, 0.85, 0.7, 0.6, 0.5, 0.4])
        c = find_cliff(curve)
        assert c["reaches_collapse"] is False
        assert c["collapse_budget"] is not None  # falls back to min-rate point

    def test_flat_curve_critical_at_edge(self):
        curve = self._curve([0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5])
        c = find_cliff(curve)
        assert c["critical_budget"] is not None

    def test_dominant_failure_escape(self):
        curve = self._curve([1.0, 0.9, 0.3, 0.0, 0.0, 0.0, 0.0])
        # near-cliff point (budget 0.8, rate 0.3) has escaped > timeout
        for p in curve:
            if p["budget"] == 0.8:
                p["timeout_rate"], p["escaped_rate"] = 0.2, 0.8
        c = find_cliff(curve)
        assert c["dominant_failure"] == "escape"


# --------------------------------------------------------------------------- #
# Curve grouping + monotonicity
# --------------------------------------------------------------------------- #
class TestCurves:
    def _sweep_data(self):
        cells = []
        for axis in ("dt", "mu", "k", "noise", "delay"):
            for i, budget in enumerate([1.0, 0.8, 0.6, 0.4, 0.2]):
                cells.append(
                    {
                        "axis": axis,
                        "value": budget,
                        "budget": budget,
                        "rate": 1.0 - 0.15 * i,
                        "success": 300 - 50 * i,
                        "n": 300,
                        "timeout_rate": 0.1 * i,
                        "escaped_rate": 0.05 * i,
                    }
                )
        return {"meta": {"name": "t"}, "cells": cells}

    def test_axis_curves_groups_and_sorts(self):
        curves = axis_curves(self._sweep_data())
        assert set(curves) == {"dt", "mu", "k", "noise", "delay"}
        for axis, curve in curves.items():
            assert [c["budget"] for c in curve] == [1.0, 0.8, 0.6, 0.4, 0.2]
            assert "ci_lo" in curve[0] and "ci_hi" in curve[0]

    def test_monotonicity_clean(self):
        curve = axis_curves(self._sweep_data())["dt"]
        m = monotonicity(curve)
        assert m["non_monotone_steps"] == 0
        assert m["max_drop_step"] == pytest.approx(0.15)

    def test_monotonicity_counts_bumps(self):
        curve = axis_curves(self._sweep_data())["dt"]
        curve[2]["rate"] = 0.95  # bump up
        m = monotonicity(curve)
        assert m["non_monotone_steps"] >= 1

    def test_summarize_shape(self, tmp_path):
        f = tmp_path / "sweep.json"
        f.write_text(json.dumps(self._sweep_data()), encoding="utf-8")
        s = summarize(f)
        assert set(s["axes"]) == {"dt", "mu", "k", "noise", "delay"}
        assert "cliff" in s["axes"]["mu"]
        assert s["axes"]["mu"]["reference_rate"] == pytest.approx(1.0)

    def test_load_json(self, tmp_path):
        f = tmp_path / "sweep.json"
        f.write_text(json.dumps(self._sweep_data()), encoding="utf-8")
        d = load(f)
        assert len(d["cells"]) == 25


# --------------------------------------------------------------------------- #
# Deterministic simulator + reference reliability
# --------------------------------------------------------------------------- #
class TestSimulator:
    def test_determinism_same_seed(self):
        a = run_episode(TASK, Fidelity(dt=0.12), seed=7)[1]
        b = run_episode(TASK, Fidelity(dt=0.12), seed=7)[1]
        assert a["step"] == b["step"]
        assert a["success"] == b["success"]

    def test_reference_solved(self):
        ok = sum(run_episode(TASK, Fidelity(), seed=s)[0] for s in range(60))
        assert ok / 60 >= 0.98

    def test_status_fields(self):
        sim = PushSim(TASK, Fidelity())
        st = sim.status()
        assert set(st) >= {"in_goal", "stopped", "escaped", "timed_out", "success", "step"}
        assert isinstance(st["success"], bool)

    def test_different_seeds_differ(self):
        a = run_episode(TASK, Fidelity(dt=0.12), seed=1)[1]
        b = run_episode(TASK, Fidelity(dt=0.12), seed=2)[1]
        # not guaranteed to differ but should not be identical trajectories
        assert a["step"] != b["step"] or a["dist_to_goal"] != b["dist_to_goal"]
