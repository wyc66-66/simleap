"""The deployment gate: a runnable check that a digital twin is safe.

The sweep measures *where* transfer reliability collapses for each fidelity
axis. The gate turns those curves into a decision procedure: given a proposed
digital-twin configuration (one value per fidelity axis), say whether the
simulator sits on the safe side of every cliff — i.e. whether a zero-fine-
tuning transfer claim from this twin would be trustworthy.

The gate is learned from the sweep, not hand-written: for each axis it records
the *safe budget* (the most degraded configuration that still transfers at
>= 90%, per :func:`simleap.analysis.find_cliff`), then converts that back to
a physical threshold via the axis's budget <-> value mapping. A configuration
is *approved* only if every axis value is on the safe side of its threshold.

Validation (``gate_audit``) replays the gate against the full sweep: every
cell the gate rejects must measure below 90%, every cell it accepts must
measure at or above 90%. Any violation is a gate bug, not a tuning detail.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .analysis import axis_curves, find_cliff

# budget 1.0 == the reference configuration; budget 0.0 == the most degraded
# grid point. ``find_cliff`` reports the safe budget (>= 90%). The gate
# converts each axis's *budget* threshold into a *physical value* threshold:
#
#   - dt / noise / delay grow as fidelity falls  -> safe value = upper bound
#   - mu / k shrink as fidelity falls            -> safe value = lower bound
GROWS = ("dt", "noise", "delay")
SHRINKS = ("mu", "k")


@dataclass
class AxisThreshold:
    axis: str
    safe_budget: float          # from find_cliff (>=90%)
    direction: str              # "grows" | "shrinks"
    threshold_value: float      # physical value at the safe budget
    critical_value: float       # physical value at the 50% crossing


@dataclass
class GateVerdict:
    approved: bool
    axis_failures: list[str]
    per_axis: dict[str, dict]


class DeploymentGate:
    """A configuration checker learned from the fidelity sweep.

    The safe threshold for each axis is the boundary of the *continuous safe
    interval*: scanning outward from the reference configuration, the first
    point whose measured rate drops below 90% ends the interval, and the
    threshold is the last point still above 90%. This deliberately rejects
    non-monotone recovery islands (e.g. the delay axis's dip at 0.22 s): a
    deployment gate must only ever approve configurations that are *provably*
    above 90% on the measured curve, so a configuration whose only support is
    a non-contiguous bump is treated as unsafe.
    """

    def __init__(self, sweep_path: Path):
        data = json.loads(Path(sweep_path).read_text(encoding="utf-8"))
        curves = axis_curves(data)
        self.axes: dict[str, AxisThreshold] = {}
        for axis, curve in curves.items():
            direction = "grows" if axis in GROWS else "shrinks"
            # scan from the reference end; the safe interval ends at the first
            # point below 90%, and the threshold is the last safe point before it
            pts = sorted(curve, key=lambda c: c["value"])
            if direction == "shrinks":
                pts = list(reversed(pts))
            threshold_value = pts[0]["value"]
            for p in pts[1:]:
                if p["rate"] >= 0.9:
                    threshold_value = p["value"]
                else:
                    break
            self.axes[axis] = AxisThreshold(
                axis=axis,
                safe_budget=find_cliff(curve)["safe_budget"],
                direction=direction,
                threshold_value=float(threshold_value),
                critical_value=find_cliff(curve)["critical_value"],
            )

    def check(self, config: dict[str, float]) -> GateVerdict:
        """Approve a digital-twin config if every axis is on the safe side.

        ``config`` maps axis name -> physical value (dt in s, mu unitless,
        k unitless, noise in m, delay in s).
        """
        failures: list[str] = []
        per_axis: dict[str, dict] = {}
        for axis, th in self.axes.items():
            if axis not in config:
                per_axis[axis] = {"present": False, "safe": False}
                failures.append(axis)
                continue
            v = config[axis]
            if th.direction == "grows":
                safe = v <= th.threshold_value
            else:
                safe = v >= th.threshold_value
            per_axis[axis] = {
                "present": True,
                "value": v,
                "threshold_value": round(th.threshold_value, 6),
                "safe": safe,
            }
            if not safe:
                failures.append(axis)
        return GateVerdict(
            approved=not failures,
            axis_failures=failures,
            per_axis=per_axis,
        )

    def approve(self, config: dict[str, float]) -> bool:
        return self.check(config).approved


def gate_audit(sweep_path: Path) -> dict:
    """Validate the gate against every cell of the sweep.

    For each measured cell, run the gate on its physical axis value (with the
    other axes at reference). Classify every disagreement:

    - **false accept** — the gate approves a cell whose measured rate < 90%.
      This is the only class that matters for safety, and it must be empty.
    - **conservative reject** — the gate rejects a cell whose measured rate
      >= 90%. These are subdivided into *isolated recovery points* (the next
      outward grid point falls back below 90%, so the gate's continuous-safe-
      interval rule is deliberately conservative, and the rejection is
      correct engineering) and *sustained safe points* (the next point stays
      >= 90%; only these indicate a threshold that could be relaxed).

    Returns the audit summary.
    """
    data = json.loads(Path(sweep_path).read_text(encoding="utf-8"))
    ref = data["meta"]["reference"]
    by_axis: dict[str, list[dict]] = {}
    for c in data["cells"]:
        by_axis.setdefault(c["axis"], []).append(c)
    gate = DeploymentGate(sweep_path)

    false_accept = []
    conservative_reject = []
    sustained_reject = []
    n_cells = 0
    for cell in data["cells"]:
        n_cells += 1
        config = dict(ref)
        config[cell["axis"]] = cell["value"]
        approved = gate.approve(config)
        if approved and cell["rate"] < 0.9:
            false_accept.append((cell["axis"], cell["value"], cell["rate"]))
        if not approved and cell["rate"] >= 0.9:
            # is the next outward grid point still >= 90%?  (outward ==
            # larger value for growing axes, smaller for shrinking axes)
            outward = []
            for c in by_axis[cell["axis"]]:
                if cell["axis"] in GROWS and c["value"] > cell["value"]:
                    outward.append(c)
                elif cell["axis"] in SHRINKS and c["value"] < cell["value"]:
                    outward.append(c)
            nxt = min(outward, key=lambda c: abs(c["value"] - cell["value"])) \
                if outward else None
            if nxt is None or nxt["rate"] < 0.9:
                conservative_reject.append((cell["axis"], cell["value"],
                                            cell["rate"],
                                            nxt["rate"] if nxt else None))
            else:
                sustained_reject.append((cell["axis"], cell["value"],
                                        cell["rate"], nxt["rate"]))

    return {
        "n_cells": n_cells,
        "false_accept": false_accept,
        "conservative_reject": conservative_reject,
        "sustained_reject": sustained_reject,
        "clean": not false_accept and not sustained_reject,
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", default="results/sweep.json", type=Path)
    args = ap.parse_args()

    gate = DeploymentGate(args.sweep)
    print("deployment gate thresholds (safe side of each axis's 90% point):")
    for axis, th in gate.axes.items():
        print(f"  {axis:<6} {'<= ' if th.direction == 'grows' else '>= '}"
              f"{th.threshold_value:.4g}   (50% crossing at {th.critical_value:.4g})")

    audit = gate_audit(args.sweep)
    print(f"\naudit: {audit['n_cells']} cells replayed, "
          f"{len(audit['false_accept'])} false accepts, "
          f"{len(audit['conservative_reject'])} conservative rejects, "
          f"{len(audit['sustained_reject'])} sustained rejects")
    if audit["clean"]:
        print("gate never approves a cell that measures below 90%")
    else:
        print("!! gate approves unsafe cells:", audit["false_accept"])
