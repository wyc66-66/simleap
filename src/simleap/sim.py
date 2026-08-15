"""Deterministic 2D pushing-physics simulator with tunable fidelity.

A circular pusher (agent) drives a block (target) from a start pose to a
goal. The model is deliberately *quasi-static and analytic* so that each
fidelity knob has a clean, interpretable effect on behaviour:

- ``dt`` — the *control period*: physics advances on a fixed high-resolution
  substep (1 ms) while the policy re-decides every ``dt`` seconds. The actuator
  is a critically-damped second-order system whose bandwidth equals the control
  rate (1/dt), so coarse control periods cannot execute high-frequency commands
  and the pusher acts on progressively staler, more sluggish authority;
- ground friction ``mu`` — how quickly the block stops sliding once released;
  low friction lets it coast through the goal;
- contact response ``k`` — how fast the block picks up the pusher's push
  velocity (1 = rigid, << 1 = soft/soggy contact that cannot transmit force);
- observation noise ``noise`` — positional noise injected into the policy's
  observations;
- observation latency ``delay`` — the state the policy sees is this many
  seconds old (a stale world model).

A policy calibrated at the reference configuration is replayed, unchanged,
at every degraded configuration; the success rate is the *transfer
reliability* at that fidelity budget. Sweeping each knob reveals a fidelity
cliff: a critical budget below which reliability collapses.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Fidelity:
    dt: float = 0.01           # control period (s); physics substep is fixed
    mu: float = 0.8            # target-ground kinetic friction
    k: float = 1.0             # contact response rate (0..1)
    noise: float = 0.0         # observation noise std (metres)
    delay: float = 0.0         # observation latency (s)


@dataclass
class Task:
    goal: np.ndarray
    goal_radius: float = 0.18
    t_max: float = 15.0
    bound: float = 6.0


class PushSim:
    """A single episode of the pushing task under a given fidelity config."""

    R_A = 0.35                 # pusher radius
    R_T = 0.25                 # block radius (disc approximation)
    H = 0.002                  # fixed physics substep (s)

    def __init__(
        self,
        task: Task,
        fid: Fidelity,
        seed: int = 0,
        *,
        start_p: np.ndarray | None = None,
        start_t: np.ndarray | None = None,
    ):
        self.task = task
        self.fid = fid
        rng = np.random.default_rng(seed)
        if start_t is None:
            start_t = np.array([-2.0 + rng.uniform(-0.15, 0.15),
                                rng.uniform(-0.3, 0.3)])
        if start_p is None:
            block = np.array(start_t, dtype=float)
            d = task.goal - block
            d = d / (np.linalg.norm(d) + 1e-12)
            start_p = block - d * (self.R_A + self.R_T + 0.25)
        self.p = np.array(start_p, dtype=float)
        self.t = np.array(start_t, dtype=float)
        self.vp = np.zeros(2)
        self.vt = np.zeros(2)
        self.step_n = 0
        self.hist: list[tuple[np.ndarray, np.ndarray]] = []
        self._a_filt = np.zeros(2)
        self._da_filt = np.zeros(2)
        # two fixed unit-noise trajectories per episode (pusher & block obs);
        # the fidelity knob merely rescales them, so reliability is a smooth
        # function of the noise budget instead of a fresh random draw each step
        n = int(round(task.t_max / self.H)) + 10
        self._np_p = np.random.default_rng(1000 + seed).standard_normal((n, 2))
        self._np_t = np.random.default_rng(2000 + seed).standard_normal((n, 2))
        # per-episode contact skid: the softer the contact (k < 1) the more the
        # block squirms sideways during the push, so low-rigidity reliability is
        # a *distribution* over drift paths rather than a deterministic step.
        self._skid = float(rng.normal(0.0, 0.05) * (1.0 - fid.k))

    def observe(self) -> tuple[np.ndarray, np.ndarray]:
        # observation latency: the policy sees the world as it was `delay`
        # seconds ago
        lat = int(round(self.fid.delay / self.H))
        idx = max(0, len(self.hist) - 1 - lat)
        p = self.hist[idx][0] if self.hist else self.p
        t = self.hist[idx][1] if self.hist else self.t
        if self.fid.noise > 0:
            i = min(self.step_n, len(self._np_p) - 1)
            return (p + self.fid.noise * self._np_p[i],
                    t + self.fid.noise * self._np_t[i])
        return p.copy(), t.copy()

    def step(self, accel: np.ndarray, n_steps: int = 1) -> dict:
        """Advance `n_steps` physics substeps (one control period)."""
        for _ in range(n_steps):
            self._substep(accel)
        return self.status()

    def _substep(self, accel: np.ndarray) -> None:
        h = self.H
        fid = self.fid

        # --- pusher: double integrator driven by a critically-damped
        #     second-order actuator. The actuator's bandwidth equals the
        #     control rate (1/dt), so a coarse sim cannot execute
        #     high-frequency commands; critical damping (zeta = 1) gives an
        #     overshoot-free, monotone response to every command, which keeps
        #     the transfer-reliability curve clean as dt grows instead of
        #     resonating at discrete control periods. ---
        tau = max(fid.dt, 4.0 * h)
        omega = 1.0 / tau
        a_ddot = omega * omega * (accel - self._a_filt) - 2.0 * omega * self._da_filt
        self._da_filt += a_ddot * h
        self._a_filt += self._da_filt * h
        self.vp += self._a_filt * h
        self.vp = np.clip(self.vp, -1.2, 1.2)
        self.p += self.vp * h

        # --- contact: the block absorbs a fraction ``k`` of the pusher's normal
        #     velocity (k = 1 rigid: the block tracks the pusher exactly; k << 1
        #     soggy: the block crawls at a fraction of the push speed and the
        #     push times out or drifts off-line). The pusher is clamped to the
        #     contact surface so it cannot tunnel through. ---
        diff = self.t - self.p
        dist = float(np.linalg.norm(diff))
        sweep = float(np.linalg.norm(self.vp)) * h
        if dist < (self.R_A + self.R_T + sweep) and dist > 1e-9:
            push_dir = diff / dist
            proj = float(np.dot(self.vp, push_dir))
            if proj > 0:
                # a soft contact lets the block skid sideways off the push line
                c, s = float(np.cos(self._skid)), float(np.sin(self._skid))
                skid_dir = np.array([c * push_dir[0] - s * push_dir[1],
                                     s * push_dir[0] + c * push_dir[1]])
                target_v = proj * skid_dir * fid.k
                gain = min(1.0, 30.0 * h)
                self.vt += (target_v - self.vt) * gain
            # un-penetrate the pusher, leaving it on the contact surface
            pen = (self.R_A + self.R_T) - dist
            if pen > 0:
                self.p -= pen * push_dir

        # --- ground friction on the block ---
        sp = float(np.linalg.norm(self.vt))
        if sp > 1e-9:
            dec = min(sp, fid.mu * 9.81 * h)
            self.vt -= (self.vt / sp) * dec

        # --- integrate positions (semi-implicit: new velocity) ---
        self.t += self.vt * h

        self.step_n += 1
        self.hist.append((self.p.copy(), self.t.copy()))

    def status(self) -> dict:
        g = self.task.goal
        in_goal = float(np.linalg.norm(self.t - g) <= self.task.goal_radius)
        stopped = float(np.linalg.norm(self.vt) < 0.05)
        escaped = bool(np.max(np.abs(self.t)) > self.task.bound)
        timed_out = self.step_n * self.H >= self.task.t_max
        return {
            "in_goal": in_goal,
            "stopped": stopped,
            "escaped": escaped,
            "timed_out": timed_out,
            "success": bool(in_goal and stopped),
            "dist_to_goal": float(np.linalg.norm(self.t - g)),
            "step": self.step_n,
        }
