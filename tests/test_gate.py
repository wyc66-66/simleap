"""Tests for the SimLeap deployment gate."""
from __future__ import annotations

import json

import pytest

from simleap.gate import DeploymentGate, gate_audit


def _sweep_json(tmp_path, cells):
    data = {
        "meta": {"reference": {"dt": 0.01, "mu": 0.8, "k": 1.0,
                               "noise": 0.0, "delay": 0.0}},
        "cells": cells,
    }
    p = tmp_path / "sweep.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _cell(axis, value, rate, budget=1.0, n=300):
    return {"axis": axis, "value": value, "rate": rate, "budget": budget,
            "n": n, "success": int(rate * n), "timeout_rate": 0.0,
            "escaped_rate": 0.0}


def _ref_config(extra):
    """A complete digital-twin config at reference fidelity, with one axis
    overridden — the gate requires every axis to be present."""
    cfg = {"dt": 0.01, "mu": 0.8, "k": 1.0, "noise": 0.0, "delay": 0.0}
    cfg.update(extra)
    return cfg


class TestThresholds:
    def test_grows_axis_threshold(self, tmp_path):
        # dt grows: reference 0.01 (100%), safe through 0.14, collapse after
        cells = [
            _cell("dt", 0.01, 1.0, budget=1.0),
            _cell("dt", 0.10, 1.0, budget=0.7),
            _cell("dt", 0.14, 1.0, budget=0.5),
            _cell("dt", 0.16, 0.4, budget=0.3),
            _cell("dt", 0.20, 0.0, budget=0.0),
            _cell("noise", 0.0, 1.0, budget=1.0),
            _cell("noise", 0.8, 0.1, budget=0.0),
            _cell("delay", 0.0, 1.0, budget=1.0),
            _cell("delay", 0.5, 0.0, budget=0.0),
            _cell("mu", 0.8, 1.0, budget=1.0),
            _cell("mu", 0.15, 0.0, budget=0.0),
            _cell("k", 1.0, 1.0, budget=1.0),
            _cell("k", 0.3, 0.0, budget=0.0),
        ]
        g = DeploymentGate(_sweep_json(tmp_path, cells))
        assert g.axes["dt"].threshold_value == 0.14
        assert g.approve(_ref_config({"dt": 0.13})) is True
        assert g.approve(_ref_config({"dt": 0.15})) is False

    def test_shrinks_axis_threshold(self, tmp_path):
        # mu shrinks: reference 0.8, safe down to 0.4, then collapse
        cells = [
            _cell("mu", 0.8, 1.0, budget=1.0),
            _cell("mu", 0.5, 1.0, budget=0.5),
            _cell("mu", 0.4, 1.0, budget=0.3),
            _cell("mu", 0.3, 0.3, budget=0.1),
            _cell("mu", 0.2, 0.0, budget=0.0),
            _cell("dt", 0.01, 1.0, budget=1.0),
            _cell("dt", 0.2, 0.0, budget=0.0),
            _cell("noise", 0.0, 1.0, budget=1.0),
            _cell("noise", 0.8, 0.1, budget=0.0),
            _cell("delay", 0.0, 1.0, budget=1.0),
            _cell("delay", 0.5, 0.0, budget=0.0),
            _cell("k", 1.0, 1.0, budget=1.0),
            _cell("k", 0.3, 0.0, budget=0.0),
        ]
        g = DeploymentGate(_sweep_json(tmp_path, cells))
        assert g.axes["mu"].threshold_value == 0.4
        assert g.approve(_ref_config({"mu": 0.45})) is True
        assert g.approve(_ref_config({"mu": 0.35})) is False

    def test_missing_axis_fails(self, tmp_path):
        cells = [_cell(a, v, r, budget=b) for a, v, r, b in [
            ("dt", 0.01, 1.0, 1.0), ("dt", 0.2, 0.0, 0.0),
            ("mu", 0.8, 1.0, 1.0), ("mu", 0.15, 0.0, 0.0),
            ("k", 1.0, 1.0, 1.0), ("k", 0.3, 0.0, 0.0),
            ("noise", 0.0, 1.0, 1.0), ("noise", 0.8, 0.1, 0.0),
            ("delay", 0.0, 1.0, 1.0), ("delay", 0.5, 0.0, 0.0),
        ]]
        g = DeploymentGate(_sweep_json(tmp_path, cells))
        # a config that omits an axis entirely must be rejected
        assert g.approve({"dt": 0.01, "mu": 0.8, "k": 1.0, "noise": 0.0}) is False


class TestNonMonotone:
    def test_recovery_island_rejected(self, tmp_path):
        # delay dips to 0.85 at 0.22 then recovers to 0.95 at 0.24: the gate
        # must NOT accept the recovery island (it is not a contiguous safe run)
        cells = [
            _cell("delay", 0.00, 1.0, budget=1.0),
            _cell("delay", 0.18, 1.0, budget=0.6),
            _cell("delay", 0.20, 1.0, budget=0.56),
            _cell("delay", 0.22, 0.85, budget=0.52),
            _cell("delay", 0.24, 0.95, budget=0.48),
            _cell("delay", 0.30, 0.3, budget=0.3),
            _cell("delay", 0.50, 0.0, budget=0.0),
            _cell("dt", 0.01, 1.0, budget=1.0), _cell("dt", 0.2, 0.0, budget=0.0),
            _cell("mu", 0.8, 1.0, budget=1.0), _cell("mu", 0.15, 0.0, budget=0.0),
            _cell("k", 1.0, 1.0, budget=1.0), _cell("k", 0.3, 0.0, budget=0.0),
            _cell("noise", 0.0, 1.0, budget=1.0), _cell("noise", 0.8, 0.1, budget=0.0),
        ]
        g = DeploymentGate(_sweep_json(tmp_path, cells))
        assert g.approve(_ref_config({"delay": 0.18})) is True
        # threshold is the last point of the contiguous safe run (0.20)
        assert g.axes["delay"].threshold_value == 0.20
        assert g.approve(_ref_config({"delay": 0.22})) is False
        assert g.approve(_ref_config({"delay": 0.24})) is False

    def test_audit_classifies_island_as_conservative(self, tmp_path):
        cells = [
            _cell("delay", 0.00, 1.0, budget=1.0),
            _cell("delay", 0.20, 1.0, budget=0.56),
            _cell("delay", 0.22, 0.85, budget=0.52),
            _cell("delay", 0.24, 0.95, budget=0.48),
            _cell("delay", 0.30, 0.3, budget=0.3),
            _cell("delay", 0.50, 0.0, budget=0.0),
            _cell("dt", 0.01, 1.0, budget=1.0), _cell("dt", 0.2, 0.0, budget=0.0),
            _cell("mu", 0.8, 1.0, budget=1.0), _cell("mu", 0.15, 0.0, budget=0.0),
            _cell("k", 1.0, 1.0, budget=1.0), _cell("k", 0.3, 0.0, budget=0.0),
            _cell("noise", 0.0, 1.0, budget=1.0), _cell("noise", 0.8, 0.1, budget=0.0),
        ]
        p = _sweep_json(tmp_path, cells)
        a = gate_audit(p)
        assert a["false_accept"] == []
        assert a["sustained_reject"] == []
        assert any(c[0] == "delay" for c in a["conservative_reject"])
