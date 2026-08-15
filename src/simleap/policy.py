"""The calibrated pushing policy.

The policy is a PD position controller on the pusher whose reference point is
model-based: aim at a standoff behind the block along the push direction
(block → goal), brake hard once the block reaches the goal.

Gains are calibrated once in the reference-fidelity simulator and then
deployed, unchanged, at every degraded fidelity — this is the sim-to-real-style
transfer that the sweep measures. Degradation is entirely a property of the
*simulator* (see :mod:`simleap.sim`): a coarse control period smooths the
actuator's response, low friction lets the block coast, a soft contact cannot
transmit force, sensor noise corrupts the observations, and observation
latency makes the state stale.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .sim import PushSim, Task


@dataclass
class Gains:
    kp: float = 80.0        # positional gain
    kd: float = 15.0        # velocity damping
    amax: float = 60.0      # pusher acceleration limit
    standoff: float = 0.30  # aim 0.30 behind the block centre (< contact 0.60, so the PD keeps pressing)
    brake: float = 40.0     # braking gain once the block is inside the goal


def reference_gains() -> Gains:
    """The gains calibrated on the reference (highest-fidelity) simulator."""
    return Gains()


def push_policy(sim: PushSim, gains: Gains | None = None) -> np.ndarray:
    """Compute the pusher acceleration for the current state."""
    g = gains or reference_gains()
    p_obs, t_obs = sim.observe()

    push_dir = sim.task.goal - t_obs
    dist_goal = float(np.linalg.norm(push_dir))
    push_dir = push_dir / (dist_goal + 1e-12)

    if dist_goal <= sim.task.goal_radius:
        # block is at the goal: brake the pusher hard
        accel = -g.brake * sim.vp
        return np.clip(accel, -g.amax, g.amax)

    # aim at a standoff behind the block along the push direction
    desired = t_obs - push_dir * g.standoff
    err = desired - p_obs
    accel = g.kp * err - g.kd * sim.vp
    return np.clip(accel, -g.amax, g.amax)


def run_episode(
    task: Task,
    fid,
    seed: int = 0,
    *,
    gains: Gains | None = None,
    horizon: int = 1_000_000,
) -> tuple[bool, dict]:
    """Roll out the policy and return (success, final status)."""
    g = gains or reference_gains()
    sim = PushSim(task, fid, seed=seed)
    n_sub = max(1, int(round(fid.dt / PushSim.H)))
    for _ in range(horizon):
        status = sim.status()
        if status["success"] or status["escaped"] or status["timed_out"]:
            return status["success"], status
        a = push_policy(sim, g)
        sim.step(a, n_sub)
    return sim.status()["success"], sim.status()
