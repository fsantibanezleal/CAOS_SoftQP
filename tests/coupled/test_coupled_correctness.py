"""Development-only generator/oracle/acceptance controls; never heldout seeds."""

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'data-pipeline'))
HAS_PEAK = importlib.util.find_spec('softqp.peak') is not None
pytestmark = pytest.mark.skipif(not HAS_PEAK, reason='Coupled validation requires the separate public softqp0.2 environment')


@pytest.mark.parametrize('family', ['sparse', 'thermal'])
@pytest.mark.parametrize('curvature', ['positive-definite', 'semidefinite', 'zero-hessian'])
@pytest.mark.parametrize('quadratic', [0., 1.])
def test_adversarial_synthetic_forecasts_have_same_semantics_and_native_oracle_accuracy(family, curvature, quadratic):
    from pipeline.coupled_accuracy import accept
    from pipeline.coupled_cases import generated_batch
    from softqp.peak import PreparedPeakSolver, solve_peak

    spec = dict(family=family, n=8, group_size=4, condition=1000, horizon=4, zones=2,
                curvature=curvature, quadratic=quadratic, seed=20261104)
    batch = generated_batch(spec, frames=4)
    copied = generated_batch(spec, frames=4)
    assert np.array_equal(batch.problem.P.data, copied.problem.P.data)
    assert np.array_equal(batch.problem.A.data, copied.problem.A.data)
    assert len(batch.updates) == 4
    workspace = PreparedPeakSolver(batch.problem)
    for update in batch.updates:
        problem = replace(batch.problem, **update)
        oracle = solve_peak(problem, 'epigraph', eps_abs=1e-10, eps_rel=1e-10,
                            adaptive_rho=True, scaling=10)
        oracle_check = accept(problem, oracle, tolerance=1e-7)
        assert oracle_check['state'] == 'accepted'
        workspace.update(**update)
        actual = workspace.solve()
        check = accept(problem, actual, oracle_check['metrics']['objective'])
        assert check['state'] == 'accepted', check
        assert np.array_equal(problem.P.data, batch.problem.P.data)
        if family == 'thermal':
            nt = 2*5
            temperatures = np.asarray(actual['x'][:nt]).reshape(2, 5)
            inputs = np.asarray(actual['x'][nt:])
            assert np.all((inputs >= -1e-6) & (inputs <= 6.+1e-6))
            assert np.max(np.abs(temperatures[:, 0]-update['lower'][:2])) <= 1e-6
        bad = dict(actual, x=(np.asarray(actual['x'])+10).tolist())
        assert accept(problem, bad, oracle_check['metrics']['objective'])['state'] != 'accepted'


def test_adversarial_independent_gate_rejects_joint_dual_and_raw_stationarity_counterexamples():
    from pipeline.coupled_accuracy import original_metrics, accept
    from softqp.peak import PeakGroup, PeakProblem

    problem = PeakProblem(sparse.eye(2, format='csc'), np.zeros(2), sparse.eye(2, format='csc'),
                          np.zeros(2), np.zeros(2), (PeakGroup([0, 1]),))
    metrics = original_metrics(problem, np.zeros(2), np.array([.75, .75]))
    assert metrics['dual_domain'] > 0 and metrics['dual_repair'] > 0
    result = dict(method='native', status_code=1, x=[0., 0.], y=[.75, .75])
    assert accept(problem, result, 0.)['state'] == 'accuracy-rejected'
    unbounded_side = PeakProblem(sparse.eye(1, format='csc'), np.zeros(1), sparse.csc_matrix([[1e14]]),
                                 np.array([-np.inf]), np.array([np.inf]), (PeakGroup([0]),))
    metrics = original_metrics(unbounded_side, [0.], [1e-12])
    assert metrics['stationarity'] == pytest.approx(1.)
    assert metrics['dual_repair'] < 1e-7
    cancellation = PeakProblem(sparse.csc_matrix((2, 2)), np.array([2e7, 1.]),
                               sparse.eye(2, format='csc'), np.zeros(2), np.array([np.inf, 0.]),
                               (PeakGroup([1]),))
    result = dict(method='native', status_code=1, x=[-1e-7, 1.], y=[-2e7, -1.])
    checked = accept(cancellation, result, 0.)
    assert checked['state'] == 'accuracy-rejected'
    assert checked['metrics']['aggregate_fenchel'] == 0
    assert checked['metrics']['fenchel'] >= 1
    overflow = PeakProblem(sparse.csc_matrix((1, 1)), np.zeros(1), sparse.csc_matrix([[1e308]]),
                           np.zeros(1), np.zeros(1), (PeakGroup([0], linear=1e308),))
    with pytest.raises((ArithmeticError, FloatingPointError)):
        accept(overflow, dict(method='native', status_code=1, x=[0.], y=[1e308]), 0.)


def test_inventory_and_draft_block_before_any_heldout_generation():
    import json
    from pipeline.coupled_campaign import inventory, verify_freeze

    protocol = json.loads((ROOT/'docs/design/coupled-experiments-v1.json').read_text())
    for split, count in protocol['generation']['counts'].items():
        # Inventory contains only identifiers; no heldout RNG/problem generation occurs.
        assert len(inventory(protocol, [split])) == count
    assert len({cell['id'] for cell in inventory(protocol, ['development', 'heldout', 'robustness'])}) == 210
    if not (ROOT/'docs/design/coupled-experiments-v1.registration.json').is_file():
        with pytest.raises(RuntimeError, match='registration'):
            verify_freeze(protocol, 'heldout')
