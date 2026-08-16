"""Statistical analysis of the SimLeap fidelity-budget sweep.

For every fidelity axis (control period ``dt``, friction ``mu``, contact
rigidity ``k``, sensor noise, observation delay) the sweep replays one
fixed policy at a monotone degradation grid and measures *transfer
reliability* (success rate) at each budget. This module extracts the
artefacts the paper and dashboard need:

1. **Reliability curves** — (value, budget, rate, failure-mode share) per axis.
2. **Cliff locations** — the critical fidelity budget b* where reliability
   crosses 50%, plus the safe / collapse budgets and the cliff width in
   budget units. A narrow cliff is a *critical-point* failure; a wide cliff is
   a *graceful* degradation.
3. **Failure-mode profiles** — whether the axis kills reliability by timeout
   (the push cannot finish) or by escape (the block is lost off-workspace).
4. **Monotonicity checks** — each axis must degrade monotonically for the
   cliff concept to be meaningful; the sweep asserts this.
"""
from __future__ import annotations

import json
from math import sqrt
from pathlib import Path

import numpy as np


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Two-sided Wilson score interval for a success rate."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def axis_curves(data: dict) -> dict[str, list[dict]]:
    """Group sweep cells into per-axis reliability curves."""
    curves: dict[str, list[dict]] = {}
    for cell in data["cells"]:
        axis = cell["axis"]
        lo, hi = wilson_interval(cell["success"], cell["n"])
        curves.setdefault(axis, []).append({
            "value": cell["value"],
            "budget": cell["budget"],
            "rate": cell["rate"],
            "ci_lo": lo,
            "ci_hi": hi,
            "timeout_rate": cell["timeout_rate"],
            "escaped_rate": cell["escaped_rate"],
        })
    for axis in curves:
        # order by budget descending: the reference (budget 1.0) is always
        # first, regardless of which physical direction the axis degrades in
        # (dt/noise/delay grow, mu/k shrink).
        curves[axis].sort(key=lambda c: -c["budget"])
    return curves


def find_cliff(curve: list[dict], safe: float = 0.9, collapse: float = 0.1,
               mid: float = 0.5, n_boot: int = 1000, seed: int = 0) -> dict:
    """Locate the fidelity cliff on a monotone degradation curve.

    ``safe_budget`` is the last budget with rate >= ``safe`` (the most
    degraded config that still transfers); ``collapse_budget`` is the first
    budget with rate <= ``collapse`` (reliability is gone). ``critical`` is
    the budget at which the curve crosses ``mid``, linearly interpolated.

    ``critical_ci`` bootstraps each point's success count (binomial draws of
    ``rate*n`` from ``n`` seeds), re-runs the same crossing detector on every
    draw, and reports the 2.5/97.5 percentile of the crossing location. With
    n=300 per cell the interval is tight; it is the honest answer to "how much
    would b* move if you redrew the seeds".
    """
    xs = np.array([c["budget"] for c in curve])
    ys = np.array([c["rate"] for c in curve])
    ns = np.array([c.get("n", 300) for c in curve])

    def cross_on(yv: np.ndarray, target: float) -> float:
        for i in range(len(xv) - 1):
            a, b = yv[i], yv[i + 1]
            if (a - target) * (b - target) <= 0:
                t = (target - a) / (b - a) if b != a else 0.0
                return float(xv[i] + t * (xv[i + 1] - xv[i]))
        return float(xv[0] if yv[0] >= target else xv[-1])

    xv = xs
    safe_budget = next((c["budget"] for c in reversed(curve) if c["rate"] >= safe),
                       curve[0]["budget"] if curve[0]["rate"] >= safe else None)
    collapse_budget = next((c["budget"] for c in curve if c["rate"] <= collapse),
                           None)
    reaches_collapse = collapse_budget is not None
    if collapse_budget is None:
        # the axis never reaches the collapse threshold (a reliability floor):
        # treat the minimum-rate point as the effective collapse so the width
        # stays comparable across axes.
        min_pt = min(curve, key=lambda c: c["rate"])
        if min_pt["rate"] < 0.5:
            collapse_budget = min_pt["budget"]
    critical = cross_on(ys, mid)

    rng = np.random.default_rng(seed)
    successes = np.round(ys * ns).astype(int)
    crossings: list[float] = []
    for _ in range(n_boot):
        boot = np.array([
            rng.binomial(n, k / n) / n if n > 0 else 0.0
            for k, n in zip(successes, ns)
        ])
        crossings.append(cross_on(boot, mid))
    arr = np.asarray(crossings)
    critical_ci = (
        [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))]
        if len(arr) else None
    )

    # dominant failure mode around the cliff
    near = min(curve, key=lambda c: abs(c["budget"] - critical))
    dominant = "timeout" if near["timeout_rate"] >= near["escaped_rate"] else "escape"

    return {
        "safe_budget": safe_budget,
        "collapse_budget": collapse_budget,
        "reaches_collapse": reaches_collapse,
        "critical_budget": critical,
        "critical_ci": critical_ci,
        "cliff_width": (safe_budget - collapse_budget) if (safe_budget is not None
                                                          and collapse_budget is not None) else None,
        "dominant_failure": dominant,
        "critical_value": float(np.interp(critical, xs[::-1], [c["value"] for c in curve][::-1])),
    }


def monotonicity(curve: list[dict]) -> dict:
    """How cleanly the axis degrades (should be monotonically non-increasing)."""
    ys = [c["rate"] for c in curve]
    bumps = sum(1 for i in range(len(ys) - 1) if ys[i + 1] > ys[i] + 1e-9)
    max_jump = max((ys[i] - ys[i + 1] for i in range(len(ys) - 1)), default=0.0)
    return {"non_monotone_steps": bumps, "max_drop_step": round(float(max_jump), 3)}


def summarize(path: Path) -> dict:
    data = load(path)
    curves = axis_curves(data)

    per_axis = {}
    for axis, curve in curves.items():
        per_axis[axis] = {
            "points": curve,
            "cliff": find_cliff(curve),
            "monotonicity": monotonicity(curve),
            "reference_rate": curve[0]["rate"],
        }

    return {
        "meta": data["meta"],
        "axes": per_axis,
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", default="results/sweep.json", type=Path)
    ap.add_argument("--out", default="results/summary.json", type=Path)
    args = ap.parse_args()

    summary = summarize(args.sweep)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("fidelity cliffs (budget axis: 1.0 = reference fidelity):")
    names = {"dt": "control period dt", "mu": "ground friction mu",
             "k": "contact rigidity k", "noise": "sensor noise",
             "delay": "observation delay"}
    for axis, a in summary["axes"].items():
        c = a["cliff"]
        m = a["monotonicity"]
        print(f"  {names.get(axis, axis):<22} ref={a['reference_rate']:.2f} "
              f"critical b*={c['critical_budget']:.3f} "
              f"safe={c['safe_budget']} collapse={c['collapse_budget']} "
              f"width={c['cliff_width']} failure={c['dominant_failure']} "
              f"bumps={m['non_monotone_steps']}")
