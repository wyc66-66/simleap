"""SimLeapX — the MotriX port of the SimLeap fidelity protocol.

This is the third generation of the protocol. The 2D analytic ``simleap``
proved the protocol on a hand-written contact model; ``simleap3d`` re-ran it on
MuJoCo's rigid-body contact engine (the engine DISCOVERSE builds on); this
module re-runs the *same protocol* on **MotriX**, the velocity-impulse physics
engine inside GS-Playground (RSS 2026) — a parallel constraint-island engine
that claims better contact stability than MuJoCo.

Every push, bounce and skid is resolved by MotriX's contact solver instead of
MuJoCo's LCP solver or a hand-written equation. The five fidelity knobs act on
engine parameters and control-loop parameters exactly as in ``simleap3d``:

- ``dt`` — the *control period*. Physics advances at a fixed 2 ms substep while
  the policy re-decides every ``dt`` seconds. The actuator is a critically
  damped second-order system whose bandwidth equals the control rate (1/dt);
- ground friction ``mu`` — the block's Coulomb friction against the floor;
- contact rigidity ``k`` — scales the contact constraint's time constant
  (``solref``) on the block geom;
- observation noise ``noise`` — *colored* Gaussian perturbation (Ornstein-
  Uhlenbeck, tracker-like correlation time) on the block read-out;
- observation latency ``delay`` — the state the policy sees is this many
  seconds old.

A policy calibrated at the reference configuration is replayed, unchanged, at
every degraded configuration; the success rate is the *transfer reliability*
at that fidelity budget. Degradation is a property of the simulator, never the
policy — exactly as in the two predecessors.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

H = 0.002  # fixed physics substep (s)

_BASE_XML = """
<mujoco model="push3d">
  <compiler angle="radian"/>
  <option timestep="{h}" gravity="0 0 -9.81"/>
  <worldbody>
    <geom name="floor" type="plane" size="4 4 0.1" friction="{mu} 0.005 0.0001"/>
    <body name="pusher" pos="0 0 0.16">
      <geom name="pusher_g" type="cylinder" size="0.30 0.08" density="300"
            friction="0.8 0.005 0.0001"/>
      <joint name="px" type="slide" axis="1 0 0"/>
      <joint name="py" type="slide" axis="0 1 0"/>
      <joint name="pz" type="slide" axis="0 0 1" limited="true" range="0 0.0001"/>
    </body>
    <body name="block" pos="0 0 0.05">
      <geom name="block_g" type="box" size="0.20 0.20 0.05" density="300"
            friction="0.1 0.005 0.0001" solref="{timeconst} 1"/>
      <joint name="bx" type="slide" axis="1 0 0"/>
      <joint name="by" type="slide" axis="0 1 0"/>
      <joint name="bz" type="slide" axis="0 0 1" limited="true" range="0 0.0001"/>
      <joint name="brot" type="hinge" axis="0 0 1" damping="0.3"/>
    </body>
  </worldbody>
  <actuator>
    <motor name="mx" joint="px" ctrlrange="-3000 3000"/>
    <motor name="my" joint="py" ctrlrange="-3000 3000"/>
  </actuator>
</mujoco>
"""


def build_model(mu: float, k: float):
    """Compile the MJCF for a given floor-friction and contact rigidity."""
    from motrixsim import load_mjcf_str

    timeconst = 0.02 / max(k, 0.01)  # k=1 -> stiff default (0.02 s)
    xml = _BASE_XML.format(h=f"{H:.6f}", mu=f"{mu:.4f}",
                           timeconst=f"{timeconst:.4f}")
    return load_mjcf_str(xml)


@dataclass
class Fidelity:
    dt: float = 0.004          # control period (s); physics substep fixed at H
    mu: float = 1.00           # block-floor kinetic friction
    k: float = 1.00            # contact rigidity (1 = stiff default)
    noise: float = 0.0         # observation noise std (metres)
    delay: float = 0.0         # observation latency (s)


@dataclass
class Task:
    goal: np.ndarray
    goal_radius: float = 0.18
    t_max: float = 12.0
    bound: float = 3.0


class PushSimX:
    """A single episode of the 3D pushing task on MotriX under a fidelity
    configuration. The public interface mirrors ``PushSim3D`` so the policy and
    sweep scripts are direct ports."""

    H = H  # physics substep (s), mirrored as a class attribute for the policy

    def __init__(
        self,
        task: Task,
        fid: Fidelity,
        seed: int = 0,
        *,
        model=None,
    ):
        self.task = task
        self.fid = fid
        self.model = model if model is not None else build_model(fid.mu, fid.k)
        from motrixsim import SceneData, forward_kinematic

        self.data = SceneData(self.model)
        self._names = list(self.model.joint_names)
        self._i_px = self._names.index("px")
        self._i_py = self._names.index("py")
        self._i_bx = self._names.index("bx")
        self._i_by = self._names.index("by")
        self._i_pusher = self.model.get_link_index("pusher")
        self._i_block = self.model.get_link_index("block")
        self._pusher_body = self.model.get_body("pusher")

        rng = np.random.default_rng(seed)
        # block starts ~1.0 m up the negative x-axis with a small lateral
        # jitter; the pusher starts on the goal line (lateral offset 0) so the
        # first contact does not shove the block sideways.
        start_t = np.array([-1.0 + rng.uniform(-0.05, 0.05),
                            rng.uniform(-0.005, 0.005)])
        d_vec = self.task.goal - start_t
        d_vec = d_vec / (np.linalg.norm(d_vec) + 1e-12)
        start_p = start_t - d_vec * (0.30 + 0.20 + 0.30)  # R_A+R_T+gap
        start_p[1] = 0.0  # stand on the goal line

        q = np.zeros(self.data.dof_pos.shape, dtype=np.float32)
        q[self._i_px] = start_p[0]
        q[self._i_py] = start_p[1]
        q[self._i_bx] = start_t[0]
        q[self._i_by] = start_t[1]
        self.data.set_dof_pos(q, self.model)
        forward_kinematic(self.model, self.data)

        self.vp = np.zeros(2)
        self.vt = np.zeros(2)
        self._a_filt = np.zeros(2)
        self._da_filt = np.zeros(2)
        self.step_n = 0
        self.hist: list[tuple[np.ndarray, np.ndarray]] = []
        self._brake_mode = False
        self._v_block = 0.0
        self._filt_init = False
        self._filt_p = np.zeros(2)
        self._filt_t = np.zeros(2)
        self._ou = np.zeros(2)
        self._last_t_obs = None
        self._brake_latched = False
        self._push_dir0 = None

        self._rng_p = np.random.default_rng(1000 + seed)
        self._rng_t = np.random.default_rng(2000 + seed)

    # -- observation -------------------------------------------------------
    def _raw_state(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        poses = self.model.get_link_poses(self.data)
        p = poses[self._i_pusher, :2].copy()
        t = poses[self._i_block, :2].copy()
        v = self.data.dof_vel
        vp = np.array([v[self._i_px], v[self._i_py]])
        vt = np.array([v[self._i_bx], v[self._i_by]])
        return p, t, vp, vt

    def observe(self) -> tuple[np.ndarray, np.ndarray]:
        # observation latency: serve the state as it was `delay` seconds ago
        lat = int(round(self.fid.delay / H))
        idx = max(0, len(self.hist) - 1 - lat)
        if self.hist:
            p, t = self.hist[idx]
        else:
            p, t, _, _ = self._raw_state()
        if self.fid.noise > 0:
            # *colored* Gaussian perturbation on the block read-out only: a
            # real visual tracker's error is time-correlated (it drifts, it
            # does not jump every frame), so we use an Ornstein-Uhlenbeck
            # process with fixed correlation time.
            theta = 4.0          # tracker bandwidth (1/s)
            sig2 = 2.0 * theta * self.fid.dt
            self._ou = self._ou * (1.0 - theta * self.fid.dt) \
                + self.fid.noise * np.sqrt(sig2) * self._rng_t.standard_normal(2)
            t = t + self._ou
        # one-pole low-pass on the sensor read-out (fixed controller bandwidth,
        # not a fidelity knob — the fidelity question is how raw noise degrades
        # reliability, not how well the controller could have filtered it).
        if not self._filt_init:
            self._filt_p = p.copy()
            self._filt_t = t.copy()
            self._filt_init = True
        else:
            alpha = 0.1
            self._filt_p = alpha * p + (1.0 - alpha) * self._filt_p
            self._filt_t = alpha * t + (1.0 - alpha) * self._filt_t
        return self._filt_p.copy(), self._filt_t.copy()

    # -- control -----------------------------------------------------------
    def step(self, accel: np.ndarray, n_steps: int = 1) -> dict:
        """Apply the policy's commanded acceleration over one control period."""
        from motrixsim import step as mstep

        model, data = self.model, self.data
        for _ in range(n_steps):
            # critically damped actuator with bandwidth = 1/dt (as in SimLeap)
            tau = max(self.fid.dt, 4.0 * H)
            omega = 1.0 / tau
            a_ddot = omega * omega * (accel - self._a_filt) \
                - 2.0 * omega * self._da_filt
            self._da_filt += a_ddot * H
            self._a_filt += self._da_filt * H
            # force control: F = m * a (mass read from the engine geometry)
            self._pusher_body.set_actuator_ctrls(
                data, self._a_filt * self._pusher_mass())
            mstep(model, data)
            # the pusher's drive has a finite max speed (as in real actuators
            # and the 2D predecessor); clamp its slide velocities
            v = data.dof_vel.copy()
            v[self._i_px] = float(np.clip(v[self._i_px], -0.8, 0.8))
            v[self._i_py] = float(np.clip(v[self._i_py], -0.8, 0.8))
            data.set_dof_vel(v)
            _, _, _, vt = self._raw_state()
            self._v_block = float(np.linalg.norm(vt))
            self.step_n += 1
            self._sync_velocities()
            p, t, _, _ = self._raw_state()
            self.hist.append((p.copy(), t.copy()))
        return self.status()

    def _pusher_mass(self) -> float:
        # the engine exposes the body mass computed from density*volume
        # (13.57 kg for the pusher); read it rather than re-derive it so the
        # force control stays consistent if the MJCF geometry ever changes.
        if not hasattr(self, "_mass"):
            self._mass = float(self.model.get_link("pusher").mass)
        return self._mass

    def _sync_velocities(self) -> None:
        _, _, vp, vt = self._raw_state()
        self.vp = vp
        self.vt = vt

    # -- termination -------------------------------------------------------
    def status(self) -> dict:
        _, t, _, vt = self._raw_state()
        g = self.task.goal
        in_goal = float(np.linalg.norm(t - g) <= self.task.goal_radius)
        stopped = float(np.linalg.norm(vt) < 0.05)
        escaped = bool(np.max(np.abs(t)) > self.task.bound)
        timed_out = self.step_n * H >= self.task.t_max
        return {
            "in_goal": in_goal,
            "stopped": stopped,
            "escaped": escaped,
            "timed_out": timed_out,
            "success": bool(in_goal and stopped),
            "dist_to_goal": float(np.linalg.norm(t - g)),
            "step": self.step_n,
        }
