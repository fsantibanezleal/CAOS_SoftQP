"""Original-space KKT diagnostics for separable convex interval penalties."""

import numpy as np


def kkt(problem, x, y):
    """Distance from stationarity and z=prox_g(z+y), in original row coordinates.

    The prox uses unit numerical rho. This is a diagnostic fixed point, independent
    of the numerical ADMM penalty chosen by a solver. The zero set is the original
    interval-penalty subgradient relation, including hard rows and kinks.
    """
    x, y = np.asarray(x), np.asarray(y)
    if x.shape != problem.q.shape or y.shape != problem.lower.shape:
        raise ValueError("KKT vectors must match original variable and row dimensions")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("KKT vectors must be finite")
    z = problem.A @ x
    v = z + y
    prox = np.clip(v, problem.lower, problem.upper)
    p = problem.penalty
    upper = p.soft & np.isfinite(problem.upper) & (v > problem.upper)
    lower = p.soft & np.isfinite(problem.lower) & (v < problem.lower)
    prox[upper] = problem.upper[upper] + np.maximum(
        v[upper] - problem.upper[upper] - p.upper_linear[upper], 0
    ) / (1 + p.upper_quadratic[upper])
    prox[lower] = problem.lower[lower] - np.maximum(
        problem.lower[lower] - v[lower] - p.lower_linear[lower], 0
    ) / (1 + p.lower_quadratic[lower])
    px, aty = problem.P @ x, problem.A.T @ y
    gradient = px + problem.q + aty
    stationarity = float(np.max(np.abs(gradient), initial=0))
    defect = np.abs(z - prox)
    scale = max(1.0, float(np.max(np.abs(px), initial=0)),
                float(np.max(np.abs(problem.q), initial=0)), float(np.max(np.abs(aty), initial=0)))
    return dict(stationarity_residual=stationarity, normalized_stationarity=stationarity / scale,
                proximal_defect=defect.tolist(),
                max_proximal_defect=float(np.max(defect, initial=0)),
                normalized_proximal_defect=float(np.max(defect / np.maximum(1, np.abs(z)), initial=0)),
                hard_violation=problem.evaluate(x)["hard_violation"])
