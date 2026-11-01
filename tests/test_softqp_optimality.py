"""Subgradient diagnostics catch an apparently stationary but wrong soft optimum."""

from dataclasses import replace
import numpy as np
import pytest
from scipy import sparse
from softqp.problem import Penalty
from softqp.solvers import solve
from pipeline.optimality import kkt
from pipeline.softqp_cases import scalar, mpc


def test_adversarial_stationarity_alone_does_not_certify_soft_optimum():
    problem = scalar(3.0)
    wrong = kkt(problem, [3.0], [0.0])
    assert wrong["stationarity_residual"] == 0
    assert wrong["max_proximal_defect"] > 1


@pytest.mark.parametrize("method", ["lifted", "generalized", "asymmetric", "daqp"])
def test_original_kkt_on_solver_and_scaled_rows(method):
    problem = scalar(-3.0)
    for factor in (0.2, 1.0, 4.0):
        p = problem.penalty
        scaled = replace(problem, A=problem.A * factor, lower=problem.lower * factor,
                         upper=problem.upper * factor,
                         penalty=Penalty(p.lower_linear / factor, p.upper_linear / factor,
                                         p.lower_quadratic / factor**2, p.upper_quadratic / factor**2, p.soft))
        result = solve(scaled, method, eps_abs=1e-9, eps_rel=1e-9)
        diagnostic = kkt(scaled, result["x"], result["y"])
        assert diagnostic["normalized_stationarity"] < 1e-7
        assert diagnostic["normalized_proximal_defect"] < 1e-7


def test_hard_and_soft_mpc_subgradient_without_changing_policy():
    problem = mpc(True, True)
    result = solve(problem, "asymmetric", eps_abs=1e-9, eps_rel=1e-9)
    diagnostic = kkt(problem, result["x"], result["y"])
    assert diagnostic["normalized_stationarity"] < 1e-7
    assert diagnostic["normalized_proximal_defect"] < 1e-7
    assert diagnostic["hard_violation"] < 1e-7


def test_unbounded_sides_and_soft_equalities():
    problem = scalar(3.0, lower=-np.inf, upper=1.0)
    result = solve(problem, "asymmetric", eps_abs=1e-9, eps_rel=1e-9)
    assert kkt(problem, result["x"], result["y"])["max_proximal_defect"] < 1e-7
    equality = replace(problem, lower=np.array([1.0]), upper=np.array([1.0]), A=sparse.eye(1, format="csc"))
    result = solve(equality, "asymmetric", eps_abs=1e-9, eps_rel=1e-9)
    assert kkt(equality, result["x"], result["y"])["max_proximal_defect"] < 1e-7


def test_adversarial_kkt_dimensions_and_nonfinite_values():
    with pytest.raises(ValueError, match="dimensions"):
        kkt(scalar(3), [1, 2], [1])
    with pytest.raises(ValueError, match="finite"):
        kkt(scalar(3), [np.nan], [1])
