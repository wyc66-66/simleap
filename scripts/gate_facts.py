#!/usr/bin/env python3
"""Extract the deployment-gate claims the SimLeap paper makes.

Prints the per-axis safe-side thresholds and the audit result, so every number
in the report's gate section (§6.1) is read from data rather than typed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from simleap.gate import DeploymentGate, gate_audit  # noqa: E402

GROW_LABEL = {"dt": "<= ", "noise": "<= ", "delay": "<= ",
              "mu": ">= ", "k": ">= "}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", default="results/sweep.json", type=Path)
    args = ap.parse_args()

    gate = DeploymentGate(args.sweep)
    print("deployment-gate thresholds (safe side of the continuous 90% run):")
    for axis, th in gate.axes.items():
        print(f"  {axis:<6} {GROW_LABEL[axis]}{th.threshold_value:.4g}   "
              f"(50% crossing at {th.critical_value:.4g})")

    audit = gate_audit(args.sweep)
    print(f"\naudit: {audit['n_cells']} cells replayed")
    print(f"  false accepts (approved but <90%): {len(audit['false_accept'])}")
    print(f"  conservative rejects (isolated recovery): {len(audit['conservative_reject'])}")
    print(f"  sustained rejects: {len(audit['sustained_reject'])}")
    for axis, v, rate, nxt in audit["conservative_reject"]:
        print(f"    {axis}={v}: {rate:.1%} (next point {nxt:.1%} < 90% -> island)")
    if not audit["clean"]:
        print("!! gate approves unsafe cells:", audit["false_accept"])


if __name__ == "__main__":
    main()
