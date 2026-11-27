"""Small authored inputs for solver-comparison teaching exercises."""

import numpy as np
from scipy import sparse
from softqp.problem import Penalty, Problem


def signed_row_example(target, lower, upper):
    """Minimize x²/2 - target*x subject to an exact hard interval."""
    return Problem(
        sparse.eye(1, format="csc"),
        np.array([-target], dtype=np.float64),
        sparse.eye(1, format="csc"),
        np.array([lower], dtype=np.float64),
        np.array([upper], dtype=np.float64),
        Penalty.uniform(1, linear=0.0, quadratic=0.0, soft=False),
    )


def shared_peak_example(target):
    """Two soft rows share one asymmetric peak, with a separate hard equality."""
    from softqp.peak import PeakGroup, PeakProblem

    return PeakProblem(
        sparse.eye(2, format="csc"),
        np.array([-target, -0.25]),
        sparse.csc_matrix([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]),
        np.array([-0.5, -0.5, 0.5]),
        np.array([0.5, 0.5, 0.5]),
        (
            PeakGroup(
                rows=(0, 1), lower_scale=(1.0, 2.0), upper_scale=(2.0, 1.0),
                linear=0.25, quadratic=0.5,
            ),
        ),
    )
