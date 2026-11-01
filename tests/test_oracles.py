import pytest
from pipeline.oracles import scalar_optimum
from pipeline.softqp_cases import scalar
from softqp.solvers import solve


@pytest.mark.parametrize("target", [-3.0, -1.0, 0.0, 1.0, 3.0])
@pytest.mark.parametrize("asymmetric", [False, True])
def test_scalar_oracle_matches_lifted_and_native(target, asymmetric):
    problem = scalar(target, asymmetric=asymmetric)
    p = problem.penalty
    oracle = scalar_optimum(
        target, -1, 1, p.lower_linear[0], p.lower_quadratic[0], p.upper_linear[0], p.upper_quadratic[0]
    )
    for method in ["lifted", "asymmetric", "daqp"]:
        assert solve(problem, method)["x"][0] == pytest.approx(oracle, abs=2e-6)


def test_the_oracle_shares_no_code_with_the_engine():
    import ast
    from pathlib import Path

    tree = ast.parse(
        (Path(__file__).parents[1] / "data-pipeline/pipeline/oracles.py").read_text(encoding="utf-8-sig")
    )
    names = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(name and ("softqp" in name or "pipeline" in name) for name in names)
