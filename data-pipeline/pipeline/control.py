"""Physical predictions for the authored double-integrator control cases."""

import numpy as np


def predict_states(initial, controls, dt=0.2):
    """Return the post-control states; do not clip or alter a proposed input."""
    state = np.asarray(initial, dtype=float)
    u = np.asarray(controls, dtype=float)
    if state.shape != (2,) or u.ndim != 1 or not np.isfinite(state).all() or not np.isfinite(u).all():
        raise ValueError("Expected one finite position/velocity pair and a finite control vector")
    if isinstance(dt, bool) or not np.isfinite(dt) or dt <= 0:
        raise ValueError("dt must be positive and finite")
    F = np.array([[1.0, dt], [0.0, 1.0]])
    B = np.array([dt**2 / 2, dt])
    states = []
    for control in u:
        state = F @ state + B * control
        states.append(state.copy())
    return np.asarray(states).reshape((-1, 2))
