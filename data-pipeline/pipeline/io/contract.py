"""Strict sparse original-space problem ingestion."""

import numpy as np
from scipy import sparse
from softqp.problem import Problem, Penalty


def decode_problem(document):
    from ..softqp_run import validate_document

    validate_document(document, "softqp-case-spec")

    def matrix(value):
        m, n = value["shape"]
        data = value["data"]
        rows = value["indices"]
        offset = value["indptr"]
        if len(offset) != n + 1 or len(rows) != len(data) or offset[0] != 0 or offset[-1] != len(data):
            raise ValueError("invalid CSC lengths")
        if any(a > b for a, b in zip(offset, offset[1:])) or any(i >= m for i in rows):
            raise ValueError("invalid CSC indices")
        for a, b in zip(offset, offset[1:]):
            if any(i >= j for i, j in zip(rows[a:b], rows[a + 1 : b])):
                raise ValueError("CSC row indices must be sorted and unique")
        return sparse.csc_matrix(
            (np.array(data, float), np.array(rows, np.int32), np.array(offset, np.int32)), shape=(m, n)
        )

    p = document["penalty"]
    result = Problem(
        matrix(document["P"]),
        np.array(document["q"], float),
        matrix(document["A"]),
        np.array([-np.inf if x is None else x for x in document["lower"]], float),
        np.array([np.inf if x is None else x for x in document["upper"]], float),
        Penalty(
            *(
                np.array(p[name], float)
                for name in ("lower_linear", "upper_linear", "lower_quadratic", "upper_quadratic")
            ),
            np.array(p["soft"], bool),
        ),
    )
    result.validate()
    return result
