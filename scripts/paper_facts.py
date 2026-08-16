#!/usr/bin/env python3
"""Extract the factual claims the SimLeap paper makes, straight from the sweep.

Prints, per fidelity axis: the reference reliability, the critical budget
(where reliability crosses 50%), the safe budget (last point >= 90%), the
collapse budget (first point <= 10%), the cliff width, the dominant failure
mode, and the exact cliff value in physical units — every number the paper
quotes is read from here rather than typed by hand.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from simleap.analysis import summarize  # noqa: E402

LABELS = {
    "dt": "control period dt (s)",
    "mu": "ground friction mu",
    "k": "contact rigidity k",
    "noise": "sensor noise (m)",
    "delay": "observation delay (s)",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", default="results/sweep.json", type=Path)
    args = ap.parse_args()

    summary = summarize(args.sweep)

    print("== fidelity cliffs (budget 1.0 = reference fidelity) ==")
    rows = []
    for axis, a in summary["axes"].items():
        c = a["cliff"]
        pts = {p["value"]: p for p in a["points"]}
        crit_val = c["critical_value"]
        # find the two grid points straddling the 50% crossing
        below = [p for p in a["points"] if p["rate"] <= 0.5]
        above = [p for p in a["points"] if p["rate"] > 0.5]
        straddle = (below[-1] if below else None, above[-1] if above else None)
        rows.append({
            "axis": axis, "label": LABELS[axis], "ref": a["reference_rate"],
            "critical_budget": c["critical_budget"], "critical_value": crit_val,
            "critical_ci": c.get("critical_ci"),
            "safe_budget": c["safe_budget"], "collapse_budget": c["collapse_budget"],
            "reaches_collapse": c["reaches_collapse"],
            "cliff_width": c["cliff_width"], "failure": c["dominant_failure"],
            "bumps": a["monotonicity"]["non_monotone_steps"],
            "straddle": tuple((p["value"], p["rate"]) for p in straddle),
        })

    for r in rows:
        print(f"\n{r['label']}")
        print(f"  reference: {r['ref']:.2%}")
        ci = r.get("critical_ci")
        ci_txt = f"  [95% bootstrap CI {ci[0]:.3f}..{ci[1]:.3f}]" if ci else ""
        print(f"  critical b* = {r['critical_budget']:.3f}  (value {r['critical_value']:.3f}){ci_txt}")
        print(f"  safe (>=90%) at budget {r['safe_budget']:.3f}; "
              f"collapse (<=10%) at budget {r['collapse_budget']:.3f}"
              f"{'' if r['reaches_collapse'] else '  [floor, never <=10%]'}")
        print(f"  cliff width = {r['cliff_width']:.3f} budget units; "
              f"dominant failure = {r['failure']}; non-monotone steps = {r['bumps']}")
        print(f"  50% straddle: {r['straddle'][0][0]:.4g}->{r['straddle'][0][1]:.2f} "
              f"/ {r['straddle'][1][0]:.4g}->{r['straddle'][1][1]:.2f}")

    print("\n== headline numbers for the paper ==")
    ref_axes = ", ".join(f"{r['axis']}={r['ref']:.2%}" for r in rows)
    print(f"  reference reliability: {ref_axes}")
    for r in rows:
        print(f"  {r['axis']}: critical {r['critical_budget']:.2f}, width {r['cliff_width']:.2f}, {r['failure']}")
    widths = sorted((r["cliff_width"], r["axis"]) for r in rows)
    print(f"  widest (graceful): {widths[-1][1]} ({widths[-1][0]:.2f}); "
          f"narrowest (critical): {widths[0][1]} ({widths[0][0]:.2f})")


if __name__ == "__main__":
    main()
