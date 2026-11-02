"""Deterministic development generators for the prospective coupled-peak study.

These synthetic problems are not operational building measurements. No heldout
generation is authorized until the independent protocol/source freeze passes.
"""

from dataclasses import dataclass

import numpy as np
from scipy import sparse


@dataclass(frozen=True)
class PeakBatch:
    problem: object
    updates: tuple
    units: dict
    description: str


def generated_batch(spec, frames=32):
    """Create fixed-matrix forecasts, without importing the old frozen campaign."""
    if not isinstance(frames, int) or isinstance(frames, bool) or frames < 1:
        raise ValueError("frames must be a positive integer")
    if spec['family'] == 'sparse':
        return _sparse_batch(spec, frames)
    if spec['family'] == 'thermal':
        return _thermal_batch(spec, frames)
    raise ValueError("unknown coupled study family")


def _curvature(kind, values):
    diagonal = np.array(values, dtype=float)
    if kind == 'semidefinite':
        diagonal[::2] = 0
    elif kind == 'zero-hessian':
        diagonal[:] = 0
    elif kind != 'positive-definite':
        raise ValueError("unknown curvature")
    return diagonal


def _sparse_batch(spec, frames):
    from softqp.peak import PeakGroup, PeakProblem

    n, size = spec['n'], spec['group_size']
    if n < 1 or size < 1 or (2*n) % size:
        raise ValueError("group size must divide the soft-row count")
    rng = np.random.default_rng(np.random.SeedSequence([spec['seed'], n, size, 731]))
    matrix = sparse.random(2*n, n, density=.1, format='lil', random_state=rng,
                           data_rvs=lambda count: rng.normal(size=count))
    for row in range(2*n):
        if not matrix.rows[row]:
            matrix[row, row % n] = 1
    matrix = matrix.tocsr()
    lengths = np.sqrt(np.asarray(matrix.multiply(matrix).sum(axis=1)).ravel())
    matrix = sparse.diags(1/lengths) @ matrix
    A = sparse.vstack([sparse.eye(n), matrix], format='csc')
    diagonal = _curvature(spec['curvature'], np.geomspace(1, spec['condition'], n))
    P = sparse.diags(diagonal, format='csc')
    q = rng.normal(size=n)*3
    lower, upper = np.r_[np.full(n, -2.), np.full(2*n, -.3)], np.r_[np.full(n, 2.), np.full(2*n, .4)]
    groups = tuple(PeakGroup(np.arange(n+start, n+start+size),
                             np.exp(rng.uniform(-1, 1, size)), np.exp(rng.uniform(-1, 1, size)),
                             linear=float(rng.uniform(.5, 1.5)), quadratic=spec['quadratic'])
                   for start in range(0, 2*n, size))
    problem = PeakProblem(P, q, A, lower, upper, groups)
    q_direction, phases = rng.normal(size=n), rng.uniform(0, 2*np.pi, 2*n)
    updates = []
    for step in range(frames):
        phase = 2*np.pi*step/frames
        shift = .05*np.sin(phase+phases)
        updates.append(dict(q=q+.2*np.sin(phase)*q_direction,
                            lower=np.r_[lower[:n], lower[n:]+shift],
                            upper=np.r_[upper[:n], upper[n:]+shift]))
    return PeakBatch(problem, tuple(updates),
                     dict(variable=['dimensionless']*n, row=['dimensionless']*(3*n), objective='dimensionless',
                          q=['dimensionless']*n, P_diagonal=['dimensionless']*n,
                          group_linear='dimensionless', group_quadratic='dimensionless',
                          lower_upper_scale='dimensionless'),
                     'Synthetic sparse bounded QP; hard coordinate bounds retain bounded PSD/LP objectives.')


def _thermal_batch(spec, frames):
    """Original hourly RC forecast model: T[k+1]=a*T[k]+b*heat[k]+(1-a)*outside[k]."""
    from softqp.peak import PeakGroup, PeakProblem

    horizon, zones = spec['horizon'], spec.get('zones', 2)
    rng = np.random.default_rng(np.random.SeedSequence([spec['seed'], horizon, zones, 947]))
    nt = zones*(horizon+1)
    nu, n = zones*horizon, zones*(2*horizon+1)
    retention = rng.uniform(.88, .94, zones)
    gain = rng.uniform(.22, .3, zones)  # degrees Celsius per kWh at hourly resolution
    rows, cols, values = [], [], []
    for zone in range(zones):
        offset = zone*(horizon+1)
        rows.append(zone)
        cols.append(offset)
        values.append(1.)
        for step in range(horizon):
            row = zones+zone*horizon+step
            rows.extend([row]*3)
            cols.extend([offset+step+1, offset+step, nt+zone*horizon+step])
            values.extend([1., -retention[zone], -gain[zone]])
    dynamics = sparse.csc_matrix((values, (rows, cols)), shape=(zones+nu, n))
    inputs = sparse.hstack([sparse.csc_matrix((nu, nt)), sparse.eye(nu)], format='csc')
    comfort_columns = np.array([z*(horizon+1)+k for z in range(zones) for k in range(1, horizon+1)])
    comfort = sparse.csc_matrix((np.ones(nu), (np.arange(nu), comfort_columns)), shape=(nu, n))
    A = sparse.vstack([dynamics, inputs, comfort], format='csc')
    first_soft = dynamics.shape[0]+nu
    groups = tuple(PeakGroup(np.arange(first_soft+z*horizon, first_soft+(z+1)*horizon),
                             lower_scale=1., upper_scale=1.5,
                             linear=5., quadratic=spec['quadratic']) for z in range(zones))
    diagonal = _curvature(spec['curvature'], np.r_[np.full(nt, .002), np.full(nu, .04)])
    P = sparse.diags(diagonal, format='csc')
    phases = rng.uniform(0, 2*np.pi, zones)
    updates = []
    for step in range(frames):
        phase = 2*np.pi*step/frames
        hour = np.arange(horizon)+step
        outside = 8.+3.*np.sin(2*np.pi*hour/24)
        initial = 21.5+.5*np.sin(phase+phases)
        equality = np.r_[initial, np.concatenate([(1-a)*outside for a in retention])]
        price = .2+.08*np.sin(2*np.pi*hour/24)
        q = np.r_[-22.*diagonal[:nt], np.tile(price, zones)]
        lower = np.r_[equality, np.zeros(nu), np.full(nu, 21.)]
        upper = np.r_[equality, np.full(nu, 6.), np.full(nu, 23.)]
        updates.append(dict(q=q, lower=lower, upper=upper))
    problem = PeakProblem(P, updates[0]['q'], A, updates[0]['lower'], updates[0]['upper'], groups)
    return PeakBatch(problem, tuple(updates),
                     dict(variable=['degree Celsius']*nt+['kWh']*nu,
                          row=['degree Celsius']*(zones+nu)+['kWh']*nu+['degree Celsius']*nu,
                          q=['synthetic currency/degree Celsius']*nt+['synthetic currency/kWh']*nu,
                          P_diagonal=['synthetic currency/degree Celsius^2']*nt+['synthetic currency/kWh^2']*nu,
                          temperature='degree Celsius', heat='kWh per one-hour interval',
                          price='synthetic currency per kWh', objective='synthetic currency',
                          peak='degree Celsius', lower_upper_scale='dimensionless directional severity',
                          group_linear='synthetic currency/degree Celsius',
                          group_quadratic='synthetic currency/degree Celsius^2',
                          retention='dimensionless', heat_gain='degree Celsius/kWh'),
                     'Synthetic independent-zone RC forecasts with hard dynamics and heater limits; '
                     'one comfort peak per zone over the horizon. Repeated forecasts are not a closed-loop simulation.')
