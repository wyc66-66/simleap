"""Engine-comparison figure: MuJoCo vs MotriX fidelity cliffs.

Loads results/sweep.json from both simleap3d and simleapx and plots, for each
of the five fidelity axes, transfer reliability vs the fidelity value, with
Wilson 95% confidence intervals and deployment gates marked for both engines.
"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MX_JSON = os.path.join(ROOT, "results", "sweep.json")
MJ_JSON = os.path.join(
    os.path.dirname(ROOT), "simleap3d", "results", "sweep.json")
OUT = os.path.join(ROOT, "results", "simleapx_engine_comparison.png")

AXIS_META = {
    "mu":    ("ground friction $\\mu$", "Friction budget"),
    "dt":    ("control period $dt$ (s)", "Control-rate budget"),
    "k":     ("contact rigidity $k$", "Contact-stiffness budget"),
    "noise": ("observation noise $\\sigma$ (m)", "Perception budget"),
    "delay": ("observation delay $\\tau$ (s)", "Perception budget"),
}
ORDER = ["mu", "dt", "k", "noise", "delay"]
MX_COLOR = "#0b5e8a"
MJ_COLOR = "#b23a48"

with open(MX_JSON) as f:
    mx = json.load(f)

ENGINES = [("MotriX", mx, MX_COLOR)]
if os.path.exists(MJ_JSON):
    with open(MJ_JSON) as f:
        mj = json.load(f)
    ENGINES.append(("MuJoCo", mj, MJ_COLOR))

DATA = {eng: d for eng, d, _ in ENGINES}

NROW = len(ENGINES)
fig, axes = plt.subplots(NROW, 6, figsize=(19.5, 3.9 * NROW))
if NROW == 1:
    axes = axes[None, :]

gate_rows = []
for row, (eng, _j, _c) in enumerate(ENGINES):
    d = DATA[eng]
    ref = d["reference"]
    for col, name in enumerate(ORDER):
        ax = axes[row, col]
        pts = d["axes"][name]
        xs = [p["value"] for p in pts]
        ys = [p["rate"] for p in pts]
        lo = [p["ci"][0] for p in pts]
        hi = [p["ci"][1] for p in pts]
        ax.fill_between(xs, lo, hi, color=_c, alpha=0.14, lw=0)
        ax.plot(xs, ys, color=_c, lw=2.0, marker="o", ms=4,
                markerfacecolor="white", markeredgewidth=1.3, zorder=3)
        ax.axhline(0.5, color="0.45", lw=0.9, ls="--", zorder=1)
        ax.axhline(ref["rate"], color="0.3", lw=0.7, ls=":", zorder=1)

        gate = d["deployment_gates"].get(name)
        if gate is not None:
            ax.axvline(gate, color="0.55", lw=1.0, ls="--", zorder=1)
            ax.annotate(f"gate {gate:.2g}", (gate, 0.52), xytext=(3, 3),
                        textcoords="offset points", fontsize=8, color="0.35",
                        rotation=90, va="bottom", ha="right")

        refv = {"mu": 1.0, "dt": 0.004, "k": 1.0, "noise": 0.0, "delay": 0.0}[name]
        ax.scatter([refv], [ref["rate"]], marker="*", s=130, color=_c,
                   edgecolor="white", linewidth=0.8, zorder=4)

        ax.set_ylim(-0.02, 1.08)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.grid(axis="both", color="0.9", lw=0.6)
        ax.set_axisbelow(True)
        for s in ax.spines.values():
            s.set_color("0.75")
        if row == 0:
            ax.set_title(AXIS_META[name][0], fontsize=12)
        ax.set_xlabel(AXIS_META[name][1], fontsize=9)
        if col == 0:
            ax.set_ylabel(f"success rate ({d['N']} seeds)", fontsize=10)

    # gate summary in the dedicated right-hand panel
    ax = axes[row, 5]
    ax.axis("off")
    nocliff = d.get("no_cliff", {})
    gate_str = {
        "mu":    lambda g: f"$\\mu$   friction      {g:.2f}",
        "dt":    lambda g: f"$dt$   control       {g:.3f} s",
        "k":     lambda g: f"$k$    rigidity      {g:.2f}",
        "noise": lambda g: f"$\\sigma$  noise   {g:.3f} m",
        "delay": lambda g: f"$\\tau$  delay    {g:.3f} s",
    }
    ax.text(0.03, 0.97,
            f"{eng} — deployment gates",
            fontsize=12, fontweight="bold", va="top", transform=ax.transAxes)
    ax.text(0.03, 0.87,
            f"reference: {ref['ok']}/{d['N']} = {ref['rate']:.3f}",
            fontsize=9.5, va="top", transform=ax.transAxes, color="0.3")
    for i, name in enumerate(ORDER):
        g = d["deployment_gates"].get(name)
        if nocliff.get(name):
            txt = f"$k$    rigidity      no cliff\n              (100% to {g:.3f})"
        else:
            txt = gate_str[name](g)
        ax.text(0.03, 0.70 - 0.11 * i, txt, fontsize=10, va="top",
                transform=ax.transAxes, color=_c)

handles = [
    Line2D([], [], color=MX_COLOR, lw=2.0, label="MotriX (GS-Playground)"),
    Line2D([], [], color=MJ_COLOR, lw=2.0, label="MuJoCo"),
    Line2D([], [], color="0.45", lw=0.9, ls="--", label="50% reliability"),
    Line2D([], [], color="0.3", lw=0.7, ls=":", label="reference rate"),
    Line2D([], [], color="0.5", marker="*", lw=0, ms=10,
           markeredgecolor="white", label="reference point"),
]
fig.legend(handles=handles, loc="lower center", fontsize=9,
           frameon=False, ncol=5)

fig.suptitle("SimLeap protocol on two contact engines — fidelity cliffs and "
             "deployment gates (MuJoCo LCP vs MotriX velocity-impulse)",
             fontsize=14.5, y=0.995)
fig.tight_layout(rect=(0, 0.06, 1, 0.96))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
fig.savefig(OUT, dpi=200)
print("wrote", OUT)
