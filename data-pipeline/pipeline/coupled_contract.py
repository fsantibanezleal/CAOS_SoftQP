"""Versioned JSON boundary for canonical coupled forecast batches."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy import sparse

from .coupled_cases import PeakBatch

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT/'docs/contracts/schemas/softqp-coupled-batch.schema.json'


def _matrix_document(matrix):
    value = sparse.csc_matrix(matrix, copy=True)
    value.sum_duplicates()
    value.sort_indices()
    return dict(shape=list(value.shape), data=value.data.tolist(),
                indices=value.indices.tolist(), indptr=value.indptr.tolist())


def _bounds(values, *, lower):
    if np.isnan(values).any() or (np.isposinf(values).any() if lower else np.isneginf(values).any()):
        raise ValueError('invalid nonfinite interval endpoint')
    return [float(value) if np.isfinite(value) else None for value in values]


def encode_batch(batch):
    problem = batch.problem
    problem.validate()
    _validate_updates(problem, batch.updates)
    groups = []
    for group in problem.groups:
        rows = np.asarray(group.rows)
        groups.append(dict(rows=rows.tolist(), lower_scale=np.broadcast_to(group.lower_scale, rows.shape).tolist(),
                           upper_scale=np.broadcast_to(group.upper_scale, rows.shape).tolist(),
                           linear=float(group.linear), quadratic=float(group.quadratic)))
    document = dict(schema_version='1.0.0', kind='directional-coupled-peak-batch',
                    problem=dict(P=_matrix_document(problem.P), A=_matrix_document(problem.A),
                                 q=problem.q.tolist(), lower=_bounds(problem.lower, lower=True), upper=_bounds(problem.upper, lower=False),
                                 groups=groups),
                    updates=[dict(q=update['q'].tolist(), lower=_bounds(update['lower'], lower=True), upper=_bounds(update['upper'], lower=False))
                             for update in batch.updates], units=batch.units, description=batch.description)
    # JSON itself cannot carry NaN/Infinity; null has an explicit side meaning.
    json.dumps(document, allow_nan=False)
    return document


def _read_matrix(document):
    rows, columns = document['shape']
    data, indices, indptr = document['data'], document['indices'], document['indptr']
    if (len(indptr) != columns+1 or indptr[0] != 0 or indptr[-1] != len(data)
            or len(indices) != len(data) or any(a>b for a, b in zip(indptr, indptr[1:]))
            or any(value < 0 or value >= rows for value in indices)):
        raise ValueError('invalid CSC lengths, pointers or row indices')
    for start, stop in zip(indptr, indptr[1:]):
        if any(a >= b for a, b in zip(indices[start:stop], indices[start+1:stop])):
            raise ValueError('CSC row indices must be unique and sorted within each column')
    return sparse.csc_matrix((np.array(data, dtype=float), np.array(indices, dtype=np.int32),
                              np.array(indptr, dtype=np.int32)), shape=(rows, columns))


def decode_batch(document):
    from jsonschema import Draft202012Validator
    from softqp.peak import PeakGroup, PeakProblem

    # Reject non-JSON numeric extensions before the schema's numeric checks.
    json.dumps(document, allow_nan=False)
    Draft202012Validator(json.loads(SCHEMA.read_text(encoding='utf-8'))).validate(document)
    raw = document['problem']
    n, m = len(raw['q']), len(raw['lower'])
    if raw['P']['shape'] != [n, n] or raw['A']['shape'] != [m, n] or len(raw['upper']) != m:
        raise ValueError('original matrix/vector dimensions disagree')
    lower = np.array([-np.inf if value is None else value for value in raw['lower']])
    upper = np.array([np.inf if value is None else value for value in raw['upper']])
    groups = tuple(PeakGroup(np.array(group['rows'], dtype=int), np.array(group['lower_scale']),
                             np.array(group['upper_scale']), group['linear'], group['quadratic'])
                   for group in raw['groups'])
    problem = PeakProblem(_read_matrix(raw['P']), np.array(raw['q'], dtype=float), _read_matrix(raw['A']),
                          lower, upper, groups)
    problem.validate()
    updates = []
    for raw_update in document['updates']:
        if len(raw_update['q']) != n or len(raw_update['lower']) != m or len(raw_update['upper']) != m:
            raise ValueError('forecast update dimensions disagree')
        update = dict(q=np.array(raw_update['q'], dtype=float),
                      lower=np.array([-np.inf if value is None else value for value in raw_update['lower']]),
                      upper=np.array([np.inf if value is None else value for value in raw_update['upper']]))
        updates.append(update)
    _validate_updates(problem, updates)
    units = document['units']
    if any(len(units[key]) != count for key, count in [('variable', n), ('row', m), ('q', n), ('P_diagonal', n)]):
        raise ValueError('physical unit map dimensions disagree')
    return PeakBatch(problem, tuple(updates), units, document['description'])


def _validate_updates(problem, updates):
    from softqp.interface import constant

    hard = problem.layout()[0] < 0
    tolerance = constant('OSQP_RHO_TOL')
    for update in updates:
        current = replace(problem, **update)
        current.validate()
        if (not np.array_equal(np.isfinite(current.lower), np.isfinite(problem.lower))
                or not np.array_equal(np.isfinite(current.upper), np.isfinite(problem.upper))):
            raise ValueError('forecast finite-side pattern must remain fixed')
        if not np.array_equal(((current.upper-current.lower) < tolerance)[hard],
                               ((problem.upper-problem.lower) < tolerance)[hard]):
            raise ValueError('forecast hard equality classification must remain fixed')
