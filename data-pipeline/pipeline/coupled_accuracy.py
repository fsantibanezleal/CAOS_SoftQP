"""Independent original-space acceptance; does not call PeakProblem.evaluate."""

import numpy as np


def original_metrics(problem, x, y):
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        return _original_metrics(problem, x, y)


def _original_metrics(problem, x, y):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if x.shape != problem.q.shape or y.shape != problem.lower.shape:
        raise ValueError('solution dimensions differ from original data')
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('nonfinite solution')
    z, px = np.asarray(problem.A @ x), np.asarray(problem.P @ x)
    if not np.isfinite(z).all() or not np.isfinite(px).all() or not np.isfinite(problem.q).all():
        raise ArithmeticError('nonfinite original primal data or matrix products')
    if np.isnan(problem.lower).any() or np.isnan(problem.upper).any():
        raise ValueError('NaN interval endpoint')
    lower_error, upper_error = np.maximum(problem.lower-z, 0), np.maximum(z-problem.upper, 0)
    hard = np.ones(len(z), dtype=bool)
    repaired = y.copy()
    repaired[(~np.isfinite(problem.upper) & (y > 0)) | (~np.isfinite(problem.lower) & (y < 0))] = 0
    penalty, conjugate, budget_error, local_gap = 0., 0., 0., 0.
    peaks = []
    for group in problem.groups:
        rows = np.asarray(group.rows)
        hard[rows] = False
        cl, cu = np.broadcast_to(group.lower_scale, rows.shape), np.broadcast_to(group.upper_scale, rows.shape)
        peak = max(float(np.max(cl*lower_error[rows])), float(np.max(cu*upper_error[rows])))
        peaks.append(peak)
        cost = group.linear*peak+.5*group.quadratic*peak**2
        penalty += cost
        polar = float(np.sum(np.maximum(y[rows], 0)/cu+np.maximum(-y[rows], 0)/cl))
        group_conjugate = 0.
        if group.quadratic == 0:
            budget_error = max(budget_error, max(polar-group.linear, 0)/max(1., polar, group.linear))
            repaired_polar = float(np.sum(np.maximum(repaired[rows], 0)/cu+np.maximum(-repaired[rows], 0)/cl))
            if repaired_polar > group.linear:
                repaired[rows] *= group.linear/repaired_polar
        else:
            repaired_polar = float(np.sum(np.maximum(repaired[rows], 0)/cu+np.maximum(-repaired[rows], 0)/cl))
            group_conjugate = max(repaired_polar-group.linear, 0)**2/(2*group.quadratic)
            conjugate += group_conjugate
        group_support = sum(float(repaired[i]*(problem.upper[i] if repaired[i] > 0 else problem.lower[i]))
                            for i in rows if repaired[i] != 0)
        inner = float(repaired[rows] @ z[rows])
        local_gap = max(local_gap, abs(cost+group_support+group_conjugate-inner)/
                        max(1., abs(cost), abs(group_support), abs(inner)))
    for i in np.flatnonzero(hard):
        if repaired[i] != 0:
            product = float(repaired[i]*(problem.upper[i] if repaired[i] > 0 else problem.lower[i]))
            inner = float(repaired[i]*z[i])
            local_gap = max(local_gap, abs(product-inner)/max(1., abs(product), abs(inner)))
    support = sum(float(yi*(problem.upper[i] if yi > 0 else problem.lower[i]))
                  for i, yi in enumerate(repaired) if yi != 0)
    stationarity = 0.
    for multiplier in (y, repaired):
        aty = np.asarray(problem.A.T @ multiplier)
        if not np.isfinite(aty).all():
            raise ArithmeticError('nonfinite original dual matrix product')
        stationarity = max(stationarity, float(np.max(np.abs(px+problem.q+aty), initial=0))/max(
            1., float(np.max(np.abs(px), initial=0)), float(np.max(np.abs(problem.q), initial=0)),
            float(np.max(np.abs(aty), initial=0))))
    inner = float(repaired @ z)
    result = dict(objective=float(.5*x @ px+problem.q @ x+penalty), peaks=peaks,
                  hard_violation=float(np.max(np.maximum(lower_error[hard], upper_error[hard]), initial=0)),
                  stationarity=stationarity, dual_domain=budget_error,
                  dual_repair=float(np.max(np.abs(y-repaired), initial=0))/max(1., float(np.max(np.abs(y), initial=0))),
                  fenchel=float(local_gap),
                  aggregate_fenchel=abs(penalty+support+conjugate-inner)/max(1., abs(penalty), abs(support), abs(inner)))
    if not all(np.isfinite(value) for key, value in result.items() if key != 'peaks'):
        raise ArithmeticError('nonfinite independent original metrics')
    return result


def accept(problem, result, oracle_objective=None, tolerance=1e-6):
    """Backend status is a candidate flag only; every accepted frame passes KKT."""
    if result.get('x') is None or result.get('y') is None:
        return dict(state='failed', reason=result.get('status', 'no solution'), metrics=None)
    method = result.get('method', '')
    allowed = (1, 2, 4, 5) if method.startswith('epigraph-daqp') else (1, 2)
    if result.get('status_code') not in allowed:
        return dict(state='failed', reason='backend status is not a solution candidate', metrics=None)
    metrics = original_metrics(problem, result['x'], result['y'])
    metrics['objective_gap'] = (abs(metrics['objective']-oracle_objective)/max(1., abs(oracle_objective))
                                if oracle_objective is not None else 0.)
    accepted = (metrics['hard_violation'] <= tolerance and metrics['stationarity'] <= tolerance
                and metrics['fenchel'] <= tolerance and metrics['dual_domain'] <= tolerance
                and metrics['dual_repair'] <= 1e-7 and metrics['objective_gap'] <= tolerance)
    return dict(state='accepted' if accepted else 'accuracy-rejected',
                reason=None if accepted else 'independent original objective/KKT gate failed', metrics=metrics)
