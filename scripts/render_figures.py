#!/usr/bin/env python3
"""Render the SimLeap paper figures from results/sweep.json.

Figure 1 — The fidelity cliff. One panel per axis: transfer reliability vs
the normalised fidelity budget (1.0 = the reference simulator). The critical
budget b* (50% crossing) is marked, the >=90% region shaded, and the
90%/10% thresholds drawn so graceful axes (wide cliffs) and critical axes
(narrow cliffs) are visually distinct.

Figure 2 — Failure modes. For each axis the failed episodes are decomposed
into *timeout* (the push never finishes) and *escape* (the block is lost
off-workspace), revealing the mechanism behind each cliff.

Figure 3 — Budget stretch. How much of each fidelity budget can be sacrificed
while keeping >=90% reliability (the safe budget) vs the critical budget b*.
This is the engineering answer: the cheapest simulator that still transfers.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from simleap.analysis import axis_curves

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
})

PALETTE = ["#1a5276", "#1e8449", "#b03a2e", "#6c3483", "#ca6f1e"]
FAIL = {"timeout": "#e8c4c0", "escape": "#d6eaf8"}
REF = "#145a32"

AXIS_LABELS = {
    "dt": "control period dt",
    "mu": "ground friction mu",
    "k": "contact rigidity k",
    "noise": "sensor noise",
    "delay": "observation delay",
}
AXIS_UNITS = {"dt": "s", "mu": "", "k": "", "noise": "m", "delay": "s"}


def _panel(ax, axis, curve, cliff):
    curve = sorted(curve, key=lambda c: c["budget"])
    xs = np.array([c["budget"] for c in curve])
    ys = np.array([c["rate"] for c in curve])
    ci_lo = np.array([c["ci_lo"] for c in curve])
    ci_hi = np.array([c["ci_hi"] for c in curve])

    ax.fill_between(xs, ci_lo * 100, ci_hi * 100, alpha=0.18, color=PALETTE[0])
    ax.plot(xs, ys * 100, "-o", ms=4, lw=2.0, color=PALETTE[0], zorder=3)

    # safe region (budget >= safe_budget) shaded green
    if cliff["safe_budget"] is not None:
        ax.axvspan(cliff["safe_budget"], 1.02, color="#e9f3ee", zorder=0)
    ax.axhline(90, color="#7f8c8d", lw=0.9, ls="--", zorder=2)
    ax.axhline(10, color="#7f8c8d", lw=0.9, ls=":", zorder=2)
    ax.axvline(cliff["critical_budget"], color="#b03a2e", lw=1.3, ls="--", zorder=4)
    ax.text(cliff["critical_budget"], 4, f"b*={cliff['critical_budget']:.2f}",
            color="#b03a2e", fontsize=9, ha="center", va="bottom")
    ax.text(0.99, 93, "safe \u2265 90%", fontsize=8.5, color="#145a32", ha="right", va="top")
    ax.set_title(AXIS_LABELS[axis], fontsize=11)
    ax.set_xlim(0, 1.03)
    ax.set_ylim(-4, 108)
    ax.set_xlabel("fidelity budget (1 = reference)", fontsize=9)
    ax.set_ylabel("success (%)", fontsize=9)
    ax.tick_params(labelsize=8)


def fig1_cliffs(curves, cliffs, out: Path) -> None:
    order = ["dt", "mu", "k", "noise", "delay"]
    fig, axes = plt.subplots(1, 5, figsize=(16.0, 3.4), sharey=True)
    for ax, axis in zip(axes, order):
        _panel(ax, axis, curves[axis], cliffs[axis])
    fig.suptitle("The fidelity cliff: reliability vs simulator fidelity budget\n"
                 "(shaded = safe region, dashed = critical budget b*)",
                 fontsize=12, y=1.02)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def fig2_failure_modes(curves, cliffs, out: Path) -> None:
    order = ["dt", "mu", "k", "noise", "delay"]
    fig, axes = plt.subplots(1, 5, figsize=(16.0, 3.6), sharey=True)
    for ax, axis in zip(axes, order):
        curve = curves[axis]
        xs = [c["value"] for c in curve]
        succ = [c["rate"] * 100 for c in curve]
        to = [c["timeout_rate"] * 100 for c in curve]
        esc = [c["escaped_rate"] * 100 for c in curve]
        ax.bar(xs, succ, width=0.06, color="#27ae60", label="success")
        ax.bar(xs, to, bottom=succ, width=0.06, color=FAIL["timeout"], label="timeout")
        ax.bar(xs, esc, bottom=[s + t for s, t in zip(succ, to)], width=0.06,
               color=FAIL["escape"], label="escape")
        ax.axvline(cliffs[axis]["critical_value"], color="#b03a2e", lw=1.2, ls="--")
        ax.set_title(AXIS_LABELS[axis], fontsize=11)
        ax.set_xlabel(f"value [{AXIS_UNITS[axis]}]" if AXIS_UNITS[axis] else "value", fontsize=9)
        ax.set_ylabel("episodes (%)", fontsize=9)
        ax.tick_params(labelsize=8, rotation=45)
        if axis == "dt":
            ax.legend(frameon=False, fontsize=8, loc="lower left")
    fig.suptitle("What each cliff is made of: success / timeout / escape at every budget",
                 fontsize=12, y=1.04)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def fig3_budget_stretch(curves, cliffs, out: Path) -> None:
    order = ["dt", "mu", "k", "noise", "delay"]
    labels = [AXIS_LABELS[a] for a in order]
    safe = [cliffs[a]["safe_budget"] for a in order]
    collapse = [cliffs[a]["collapse_budget"] for a in order]
    widths = [cliffs[a]["cliff_width"] for a in order]

    x = np.arange(len(order))
    fig, ax = plt.subplots(figsize=(9.0, 4.2))
    ax.barh(x, collapse, 0.52, color="#aab7c4", label="dead (reliability gone)")
    ax.barh(x, [s - c for s, c in zip(safe, collapse)], 0.52, left=collapse,
            color="#b03a2e", alpha=0.85, label="cliff (90% \u2192 10%)")
    ax.barh(x, [1.0 - s for s in safe], 0.52, left=safe, color="#1e8449",
            label="safe (\u226590%)")
    for yi, w in zip(x, widths):
        ax.text(0.02, yi, f"w={w:.2f}", fontsize=8, va="center", color="white")
    ax.set_yticks(x)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlim(0, 1.06)
    ax.set_xlabel("fidelity budget (1 = reference)", fontsize=10)
    ax.set_title("Budget stretch: how much fidelity each axis can sacrifice\n"
                 "before reliability collapses (cliff width w)", fontsize=12)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    ax.axvline(1.0, color="#7f8c8d", lw=0.8, ls=":")
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", default="results/sweep.json", type=Path)
    ap.add_argument("--out", default="docs/figures", type=Path)
    args = ap.parse_args()

    data = args.sweep
    from simleap.analysis import load, find_cliff

    sweep = load(data)
    curves = axis_curves(sweep)
    cliffs = {a: find_cliff(c) for a, c in curves.items()}

    args.out.mkdir(parents=True, exist_ok=True)
    fig1_cliffs(curves, cliffs, args.out / "fig1_fidelity_cliff.png")
    fig2_failure_modes(curves, cliffs, args.out / "fig2_failure_modes.png")
    fig3_budget_stretch(curves, cliffs, args.out / "fig3_budget_stretch.png")
    print(f"[figures] wrote 3 figures -> {args.out}")


if __name__ == "__main__":
    main()
