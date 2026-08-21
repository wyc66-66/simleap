"""Failure-mode figure from results/failure_modes.json.

Stacked bars per cliff cell: how the failed episodes die, split into
edge-fail / in-goal / stalled / runaway. Reused by the report (Section 3.4).
"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CELL_LABELS = {
    "mu_f0.15": "mu 0.15\n(friction)",
    "dt_0.035": "dt 35ms\n(control)",
    "delay_0.30": "delay .30s\n(latency)",
    "noise_0.30": "noise .30m",
    "noise_0.60": "noise .60m",
    "k_0.005": "k 0.005\n(no cliff)",
}
CLASSES = ["edge-fail", "in-goal-fail", "stalled", "runaway"]
COLORS = {"edge-fail": "#d1495b", "in-goal-fail": "#f79256",
          "stalled": "#80a1d4", "runaway": "#3e7c59"}


def main() -> None:
    with open("results/failure_modes.json") as f:
        data = json.load(f)
    cells = [c for c in data["cells"] if c in CELL_LABELS]
    n = data["N"]

    fig, ax = plt.subplots(figsize=(7.0, 3.6), dpi=200)
    bottoms = [0.0] * len(cells)
    for cls in CLASSES:
        vals = [data["cells"][c]["class"][cls] for c in cells]
        ax.bar(range(len(cells)), vals, bottom=bottoms,
               color=COLORS[cls], label=cls.replace("-", " "), width=0.62)
        bottoms = [b + v for b, v in zip(bottoms, vals)]

    rates = [data["cells"][c]["ok"] / n for c in cells]
    for i, (c, r) in enumerate(zip(cells, rates)):
        ax.text(i, bottoms[i] + 4, f"{r * 100:.0f}%", ha="center",
                va="bottom", fontsize=9, color="#333333")
        med = data["cells"][c]["median_dist"]
        if med == med:  # not NaN
            ax.text(i, -0.02 * n, f"med {med * 1000:.0f} mm", ha="center",
                    va="top", fontsize=7.5, color="#777777")

    ax.set_xticks(range(len(cells)))
    ax.set_xticklabels([CELL_LABELS[c] for c in cells], fontsize=9)
    ax.set_ylabel(f"failed episodes (of N={n})", fontsize=9)
    ax.set_ylim(0, n * 1.18)
    ax.legend(loc="upper right", fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Failure signatures at each cliff (MotriX)",
                 fontsize=11, y=0.98)
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))

    out = "results/failure_modes.png"
    fig.savefig(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
