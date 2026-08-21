"""The 3D pushing policy (MotriX port — identical to the MuJoCo version).

Push phase: a target-speed profile along the push line (block → goal) — the
block's desired speed is v_max while far from the goal and is ramped linearly
to a low speed at the goal edge. The block speed is estimated by the pusher's
motor encoders (odometry), so sensor noise and latency on the block tracker
feed only the latch decision, not the speed loop.

Termination phase: the block is *not* actively stopped — once it crosses the
goal radius the pusher brakes and the block coasts to a stop on the table's
own friction. This is the deliberate design of the SimLeap protocol: the
fidelity question is whether a policy that trusts the physics still succeeds
when a simulator's friction, contact stiffness, control period, sensor noise
or sensor latency is wrong.

Gains are calibrated once in the reference-fidelity simulator and then
deployed, unchanged, at every degraded fidelity — this is the sim-to-real-style
transfer that the sweep measures.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .sim import PushSimX, Task


@dataclass
class Gains:
    kp: float = 150.0       # sideward alignment gain
    kd: float = 30.0        # sideward velocity damping
    kv: float = 5.0         # speed-error gain along the push line
    amax: float = 100.0     # pusher acceleration limit
    v_max: float = 5.0      # cruising push speed
    ease_zone: float = 0.57 # ramp v_max to ~0 over this distance to the goal
    contact_gap: float = 0.45  # align just inside the contact distance
    brake: float = 80.0     # braking gain once the block is inside the goal


def reference_gains() -> Gains:
    """The gains calibrated on the reference (highest-fidelity) simulator."""
    return Gains()


def push_policy(sim: PushSimX, gains: Gains | None = None) -> np.ndarray:
    """Compute the pusher acceleration for the current state."""
    g = gains or reference_gains()
    p_obs, t_obs = sim.observe()

    # latch direction: locked to the goal bearing from the first observation,
    # used only to detect when the block has crossed the goal plane.
    if sim._push_dir0 is None:
        d0 = sim.task.goal - t_obs
        n0 = float(np.linalg.norm(d0))
        sim._push_dir0 = d0 / (n0 + 1e-12) if n0 > 1e-9 else np.array([1.0, 0.0])
    dir0 = sim._push_dir0

    # push direction: fixed at the initial goal bearing. A real-time bearing
    # that tracks the drifting block amplifies the drift (the pusher chases the
    # block sideways and slams into it); with a fixed bearing the block simply
    # keeps its initial small lateral offset and the push stays straight.
    push_dir = sim._push_dir0

    # the latch uses the *fixed* bearing, so a lateral drift of the block can
    # never fool it into missing the goal plane. A 0.75 margin gives the block
    # enough room to coast to a stop inside the goal under the worst-case
    # observation error, without latching so late that low-friction blocks
    # skid through the far side.
    proj = float(np.dot(sim.task.goal - t_obs, dir0))
    dist_goal = max(0.0, proj)

    if dist_goal <= 0.75 * sim.task.goal_radius:
        sim._brake_latched = True
    if sim._brake_latched:
        accel = -g.brake * sim.vp
        return np.clip(accel, -g.amax, g.amax)

    # pusher speed along the push line, read from the motor encoders
    # (essentially noiseless in a real system). The block speed is not
    # finite-differenced from the block observations: that would inject the
    # full observation noise into the speed loop and make the controller
    # pathologically sensitive to it.
    v_block_along = float(np.dot(sim.vp, push_dir))

    # speed ramp: estimated from the *pusher's* odometry, not the block
    # read-out. The pusher presses at a fixed standoff (contact_gap) ahead of
    # the block, so the block's remaining distance to the goal is the pusher's
    # remaining distance plus the standoff. Reading the ramp from the encoders
    # keeps the speed profile immune to the block tracker's noise and latency —
    # only the latch decision (whether the block has actually entered the goal)
    # remains anchored to the block observation, which is the honest place for
    # the noise knob to bite.
    proj_p = float(np.dot(sim.task.goal - p_obs, push_dir))
    dist_block = max(0.0, proj_p + g.contact_gap)
    v_des = min(g.v_max, g.v_max * dist_block / g.ease_zone)
    a_along = g.kv * (v_des - v_block_along)

    # sideward alignment: stand on the *goal line* at the block's along-line
    # projection (not at the block's raw lateral position). Chasing the block's
    # lateral drift would slam the pusher sideways into it and amplify the
    # drift; standing on the line makes the contact force itself pull the block
    # back onto the goal line.
    proj_now = float(np.dot(sim.task.goal - t_obs, dir0))
    t_proj = sim.task.goal - dir0 * proj_now
    desired = t_proj - push_dir * g.contact_gap
    err = desired - p_obs
    perp = push_dir * np.dot(err, push_dir)
    side = err - perp
    v_side = sim.vp - push_dir * np.dot(sim.vp, push_dir)
    accel = push_dir * a_along + g.kp * side - g.kd * v_side
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
    sim = PushSimX(task, fid, seed=seed)
    n_sub = max(1, int(round(fid.dt / PushSimX.H)))
    for _ in range(horizon):
        status = sim.status()
        if status["success"] or status["escaped"] or status["timed_out"]:
            return status["success"], status
        a = push_policy(sim, g)
        sim.step(a, n_sub)
    return sim.status()["success"], sim.status()
