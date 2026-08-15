"""simleap: how simulation fidelity budgets decide transfer reliability.

A policy is calibrated in a reference (high-fidelity) simulator and then
deployed, unchanged, into simulators whose physical fidelity is degraded one
axis at a time — integration step, contact friction, contact stiffness,
sensor noise, and control delay. The deliverable is the fidelity-budget →
success-rate map: which axes are safe to sacrifice, where the cliff sits, and
how far a fixed budget can be stretched before the policy stops transferring.

This mirrors the Real2Sim2Real loop behind GS-Playground-class simulators,
where the *fidelity budget* of the simulator is the thing being traded
against deployment reliability.
"""
