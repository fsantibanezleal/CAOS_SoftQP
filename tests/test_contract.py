import copy
import numpy as np
import pytest
from pipeline.io.contract import decode_problem
from pipeline.softqp_cases import cases
from pipeline.softqp_requests import encode_problem


@pytest.mark.parametrize("case", [c for c in cases() if c.problem is not None], ids=lambda c: c.id)
def test_good_rows_accepted(case):
    reconstructed = decode_problem(encode_problem(case.problem))
    point = np.linspace(-0.2, 0.3, reconstructed.q.size)
    assert reconstructed.evaluate(point) == case.problem.evaluate(point)


def test_adversarial_bad_rows_rejected_not_coerced():
    original = encode_problem(cases()[0].problem)
    changes = [
        lambda d: d["q"].__setitem__(0, True),
        lambda d: d["P"]["indptr"].__setitem__(-1, 2),
        lambda d: d["A"]["indices"].__setitem__(0, 1),
        lambda d: d["penalty"]["soft"].append(False),
        lambda d: d["q"].__setitem__(0, float("nan")),
    ]
    for change in changes:
        doc = copy.deepcopy(original)
        change(doc)
        with pytest.raises(Exception):
            decode_problem(doc)


def test_outlier_flagged_but_accepted():
    # Large finite physical coefficients retain their declared value; no silent clipping.
    doc = encode_problem(cases()[0].problem)
    doc["penalty"]["upper_linear"][0] = 1e8
    assert decode_problem(doc).penalty.upper_linear[0] == 1e8
