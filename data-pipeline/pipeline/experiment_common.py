"""Shared experimental acceptance and dispatch, with original-space evaluation."""

import time
import numpy as np
from softqp.solvers import solve, UnsupportedProblemError
from softqp.flex import solve_flex
from softqp.elasti import solve_elastiqp

SETTINGS = dict(eps_abs=1e-7, eps_rel=1e-7, max_iter=200000, adaptive_rho_interval=25)
METHODS = ["lifted", "generalized", "asymmetric", "daqp", "flex", "elastiqp"]


def acceptance(problem, result, objective):
    """Recompute all primal metrics; never trust a backend's objective field."""
    good = result["status_code"] == 1 or (
        result["method"] == "daqp" and result["status_code"] == 2
    )
    if not good or result.get("x") is None:
        return dict(state="failed", reason=result["status"], metrics=None, normalized_gap=None)
    metrics = problem.evaluate(np.asarray(result["x"]))
    gap = abs(metrics["objective"] - objective) / max(1.0, abs(objective))
    accepted = gap <= 1e-6 and metrics["hard_violation"] <= 1e-6
    # Dual stationarity is diagnostic; the preregistered acceptance thresholds are primal.
    y = result.get("y")
    metrics["stationarity_residual"] = (
        float(np.max(np.abs(problem.P @ result["x"] + problem.q + problem.A.T @ y), initial=0))
        if y is not None else None
    )
    return dict(
        state="accepted" if accepted else "accuracy-rejected",
        reason=None if accepted else "Original-space objective gap or hard-row threshold exceeded.",
        metrics=metrics,
        normalized_gap=float(gap),
    )


def execute(problem, method):
    if method == "flex":
        return solve_flex(problem, **{k: SETTINGS[k] for k in ("eps_abs", "eps_rel", "max_iter")})
    if method == "elastiqp":
        return solve_elastiqp(problem, **{k: SETTINGS[k] for k in ("eps_abs", "eps_rel", "max_iter")})
    return solve(problem, method, reference_backend="native", **SETTINGS)


def cold_observation(problem, method, objective):
    start = time.perf_counter()
    try:
        result = execute(problem, method)
        check = acceptance(problem, result, objective)
        elapsed = time.perf_counter() - start
        return dict(
            **check, elapsed_seconds=elapsed, result=result,
            update_seconds=None, workspace_setup_seconds=None,
        )
    except UnsupportedProblemError as error:
        return dict(state="incompatible", reason=str(error), metrics=None, normalized_gap=None,
                    elapsed_seconds=time.perf_counter() - start, result=None,
                    update_seconds=None, workspace_setup_seconds=None)
    except Exception as error:
        return dict(state="failed", reason=f"{type(error).__name__}: {error}", metrics=None,
                    normalized_gap=None, elapsed_seconds=time.perf_counter() - start, result=None,
                    update_seconds=None, workspace_setup_seconds=None)


def oracle(problem):
    result = solve(problem, "lifted", reference_backend="stock", eps_abs=1e-9, eps_rel=1e-9,
                   max_iter=200000, adaptive_rho_interval=25)
    if result["status_code"] != 1 or result.get("x") is None:
        raise RuntimeError(f"Independent oracle did not solve: {result['status']}")
    metrics = problem.evaluate(np.asarray(result["x"]))
    if metrics["hard_violation"] > 1e-6:
        raise RuntimeError("Independent oracle violated a hard row")
    return result, metrics["objective"]
