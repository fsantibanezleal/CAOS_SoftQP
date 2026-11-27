"""Teaching inputs have independent sign and solution checks."""

import pytest
from softqp.solvers import solve

from pipeline.notebook_method_examples import shared_peak_example, signed_row_example


@pytest.mark.parametrize(
    ("target", "lower", "upper", "expected_x", "expected_y"),
    [(-2.0, -1.0, 1.0, -1.0, -1.0), (2.0, -1.0, 1.0, 1.0, 1.0), (2.0, 0.5, 0.5, 0.5, 1.5)],
)
def test_native_lift_recovers_analytic_signed_row(target, lower, upper, expected_x, expected_y):
    observed = solve(signed_row_example(target, lower, upper), "lifted", reference_backend="stock")
    assert observed["x"] == pytest.approx([expected_x], abs=1e-5)
    assert observed["y"] == pytest.approx([expected_y], abs=1e-5)


@pytest.mark.parametrize(
    ("method", "module", "version"),
    [("clarabel", "clarabel", "0.11.1"), ("proxqp", "proxsuite", "0.7.2"), ("piqp", "piqp", "0.6.4")],
)
def test_official_sparse_backend_matches_stock_on_authored_peak(method, module, version):
    pytest.importorskip(module, reason="Official comparator is installed in the notebook profile")
    from softqp.comparators.vertical import ComparatorSession
    from softqp.peak import solve_peak

    problem = shared_peak_example(target=2.0)
    expected = solve_peak(problem, method="epigraph")
    observed = ComparatorSession(problem, method).solve()
    assert observed["backend_version"] == version
    assert observed["status"] == "candidate", observed
    assert observed["metrics"]["epigraph"]["accepted"]
    assert sum(observed["x"]) == pytest.approx(0.5, abs=1e-7)
    assert observed["x"] == pytest.approx(expected["x"], abs=1e-6)
    assert observed["metrics"]["objective"] == pytest.approx(expected["metrics"]["objective"], abs=1e-6)
