# SimLeap

**How much simulation fidelity can you afford to give up before the policy
stops transferring?**

A quantitative map of the *fidelity budget → sim-to-real transfer reliability*
boundary for a contact-rich manipulation policy. We build a deterministic 2D
pushing task, calibrate one policy in a reference (high-fidelity) simulator,
then replay it — unchanged — as five physical knobs are degraded one at a time.
The result is a set of **fidelity cliffs**: for every knob, the exact budget at
which reliability collapses.

This is the same trade-off every Real2Sim2Real loop faces — and the specific
question the DISCOVERSE / GS-Playground line of simulators (Tsinghua AIR DISCOVER
Lab) is built on. Both platforms deliver photorealistic digital twins that
transfer to a real robot with zero fine-tuning; that promise holds *only up to*
the fidelity the digital twin actually preserves. This project quantifies where
that point is: which knobs a sim2real pipeline must hold at reference fidelity,
which tolerate aggressive degradation, and which announce their failure through
a diagnosable failure mode.

> **Scope.** This is a within-simulator protocol — we measure the policy's
> reliability boundary *inside* the simulator as fidelity degrades, not
> transfer to physical hardware. The cliffs are a prediction about what a
> sim2real pipeline would experience; the numbers themselves are simulator
> measurements.

**Scale:** 5 fidelity axes × 16–18 grid points = 84 budget cells × 300
deterministic seeds each = **25,200 episodes**, all in pure Python (minutes on a
laptop). Every cliff carries a 95% bootstrap confidence interval.

## The five budgets

| Axis | Budget knob | What degrades | Cliff (measured) |
|---|---|---|---|
| Control period | `dt` | the policy re-decides less and less often; the actuator's bandwidth shrinks | **critical point** (width 0.08) |
| Ground friction | `mu` | the block cannot be stopped and coasts through the goal | **critical point** (width 0.02, sharpest) |
| Contact rigidity | `k` | the push transmits less force; the block crawls and times out | **critical point** (width 0.03) |
| Sensor noise | `noise` | positional observations become unreliable | **graceful** (no cliff, floor 12–17%) |
| Observation delay | `delay` | the policy acts on a stale world model | **critical point** (width 0.10) |

Headline result: **four of the five fidelity budgets collapse at a critical
point; only sensor noise degrades gracefully.** `mu`, `k`, `dt` and `delay`
each hold reliability at or above 90% until a sharp physical threshold and then
drop to near-zero within a few percent of budget; `noise` erodes reliability
continuously over a wide budget range and never fully kills it — a 12–17%
residual floor survives even total budget exhaustion. The *shape* of the cliff
is diagnostic: it separates amplitude perturbations on the observation channel
(graceful) from phase and dynamics perturbations on the closed loop (critical).

## Repository layout

```
simleap/
├── src/simleap/
│   ├── sim.py          # deterministic 2D pushing physics + fidelity knobs
│   ├── policy.py       # the calibrated PD push policy (never re-tuned)
│   ├── analysis.py     # cliffs, failure modes, monotonicity
│   ├── check.py        # sanity checks (reference 100%, monotonicity, cliffs)
│   └── ui/app.py       # FastAPI dashboard
├── scripts/
│   ├── run_sweep.py    # the fidelity-budget sweep (300 seeds / cell)
│   ├── paper_facts.py  # every number the paper quotes, from sweep.json
│   ├── render_figures.py
│   └── render_paper.py
├── ui/static/index.html
├── docs/paper/report.md
└── results/sweep.json
```

## Reproduce

```bash
pip install -e .          # installs numpy; tests need pytest
pip install pytest

# full sweep (84 budget cells × 300 seeds)
python scripts/run_sweep.py --seeds 300 --out results/sweep.json

# verify, analyse, render
python -m simleap.check
python scripts/paper_facts.py --sweep results/sweep.json
python scripts/render_figures.py --sweep results/sweep.json
python scripts/render_paper.py
```

## Tests

```bash
python -m pytest -q        # 17 tests: Wilson CI, cliff detection, determinism
```

CI (`.github/workflows/ci.yml`) runs the suite on every push to `main`.

## Dashboard

```bash
python -m simleap ui --port 8739
# open http://localhost:8739
```

## Method

- **Task:** a circular pusher drives a block from a jittered start to a goal
  (4 m away, radius 0.18 m) within 15 s. Success = the block reaches the goal
  *and* comes to rest.
- **Policy:** a PD position controller aimed at a standoff behind the block,
  with a hard brake in the goal. Gains are calibrated once at the reference
  fidelity and frozen; every degraded run replays the identical controller.
- **Degradation is a property of the simulator, never the policy.** A coarse
  control period is a critically-damped second-order actuator whose bandwidth
  equals the control rate; low friction lets the block coast; a soft contact
  transmits only a fraction of the push; noise rescales a fixed per-episode
  perturbation; delay serves the policy a stale state.
- **Sweep:** 84 cells (5 axes × 16–18 grid points), 300 seeds each,
  deterministic per seed (25,200 episodes, minutes on a laptop).

The code, the figures, and every number in the report are produced by these
scripts alone — no manual curation of results.
---

## Live report

The technical report, figures and every number are served at **[https://wyc66-66.github.io/simleap/](https://wyc66-66.github.io/simleap/)**.
