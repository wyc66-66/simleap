# SimLeapX

**The SimLeap fidelity protocol, ported to GS-Playground's MotriX engine — and
compared cliff-for-cliff against MuJoCo.**

The [SimLeap](../simleap) protocol answers one question: *how wrong can a
physical parameter of a simulator be before a policy trained in it stops
transferring?* Calibrate a policy once in a reference-fidelity simulator,
replay it unchanged as physical knobs degrade, and read off the fidelity
cliffs. [SimLeap3D](../simleap3d) ran the protocol on MuJoCo's LCP contact
solver. SimLeapX runs the **same protocol** on **MotriX**, the
velocity-impulse contact engine inside [GS-Playground](../gs_playground-main)
(RSS 2026) — a parallel constraint-island solver that claims better contact
stability than MuJoCo.

Same task, same policy (transcribed verbatim), same five fidelity knobs, same
200-seed Wilson-CI measurement. Only the contact engine changed.

## What the two engines agree on

| Axis | MuJoCo | MotriX | Agreement |
|---|---|---|---|
| Control period `dt` | 100% until 25 ms, 0% at 35 ms | 100% until 25 ms, 0% at 35 ms | **identical gate: 0.03 s** |
| Observation delay `tau` | 93% at 0.20 s, 0% at 0.30 s | 100% until 0.25 s, 0% at 0.30 s | **identical gate: 0.25 s** |
| Ground friction `mu` | 100% until 0.15, 2% at 0.12 | 100% until 0.18, 0.5% at 0.15 | sharpest cliff; MotriX collapses first (gate 0.18 vs 0.15) |
| Sensor noise `sigma` | graceful, gate 0.04 m | graceful, gate 0.25 m | graceful in both; MotriX tolerates ~6x |
| Contact rigidity `k` | **hard cliff** — 0% at 0.06 | **no cliff** — 100% down to 0.005 | the engine difference |

## The engine difference

**Contact stiffness is a hard cliff in MuJoCo and a non-issue in MotriX.**
In MuJoCo, softening the contact constraint's time-constant (`solref`) strangles
force transmission — below k ≈ 0.08 the contact can no longer transmit the
push and the task dies. In MotriX, the velocity-impulse solver projects the
contact constraint by momentum instead of relaxing a soft spring, so a soft
contact still transmits the push: **100% reliability all the way to k = 0.005**
(the floor of the grid), ten times below MuJoCo's collapse point. This is the
first quantitative, task-level confirmation of the engine's contact-stability
claim.

**The shape distinction is engine-agnostic.** Amplitude perturbations on the
observation channel (noise) erode reliability *gracefully* in both engines;
phase/dynamics perturbations on the closed loop (`dt`, `delay`) kill the task
at a *critical point* in both engines. A protocol that measures only cliffs
would miss this; the SimLeap protocol's graceful-vs-critical taxonomy survives
the engine switch.

**Scope of the engine comparison.** Of the five knobs, only `mu` and `k`
exercise the engines' contact solvers. `dt`, `noise` and `delay` act on the
Python-side control loop and observation pipeline, identical across engines —
those cliffs describe the *task+policy*, and their cross-engine agreement is a
reproducibility check of the protocol rather than a solver property. The
engine-specific conclusions rest on `mu` and `k`.

**Failures are diagnostic.** Every cliff leaves a signature: the block stops
1.5–4 cm past the goal edge (friction / control-rate / latency budget), ends
far from the goal (contact rigidity / control rate), or the trajectory becomes
erratic (stale state). `scripts/analyze_failure_modes.py` produces the
inversion table — look at how the policy failed, read back which fidelity knob
ran out.

## Reproduce

```bash
# in WSL (MotriX is linux-only)
python3 -m venv .venv_mx
pip install "motrixsim_core==0.7.1.dev97295" \
    --index-url https://pypi.motphys.com/simple/ --extra-index-url https://pypi.org/simple/
pip install -e . numpy matplotlib
python scripts/analysis_sweep.py 200   # -> results/sweep.json
python scripts/analysis_plot.py        # -> results/simleapx_engine_comparison.png
python scripts/analyze_failure_modes.py  # -> results/failure_modes.json
python scripts/plot_failure_modes.py     # -> results/failure_modes.png
python -m pytest -q
```

## Layout

```
simleapx/
├── src/simleapx/
│   ├── sim.py          # MotriX MJCF task + the five fidelity knobs
│   └── policy.py       # the calibrated PD push policy (verbatim port)
├── scripts/
│   ├── analysis_sweep.py   # N-seed sweep, Wilson CI, deployment gates
│   ├── analysis_plot.py    # MuJoCo-vs-MotriX comparison figure
│   ├── analyze_failure_modes.py  # failure signatures -> knob inversion table
│   ├── plot_failure_modes.py     # stacked-bar figure of the signatures
│   ├── verify_friction_rule.py  # proves max-of-pair friction combination
│   ├── verify_k_mechanism.py    # mechanism probe behind the k-axis finding
│   └── probe_*.py          # development probes
└── results/
    ├── sweep.json              # every measured cell (MotriX)
    ├── failure_modes.json      # per-cliff failure classification (N=200)
    ├── failure_modes.png       # failure-signature figure
    └── simleapx_engine_comparison.png
```
