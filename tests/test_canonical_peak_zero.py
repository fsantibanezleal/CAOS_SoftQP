"""Valid physical zero bounds must not create forbidden signed-zero artifacts."""

from copy import deepcopy
import math

import pytest

from pipeline.learned_comparison import contracts as c
from test_learned_contracts import make_problem


@pytest.mark.parametrize("scale", [1, 1.5])
def test_adversarial_peak_lower_positive_zero_survives_canonical_artifact_checks(scale):
    original = deepcopy(make_problem()["original"])
    original.update(
        formulation="peak", lower=[0.0], upper=[2],
        lower_finite=[True], upper_finite=[True],
        groups=[dict(group_id=0, rows=[0], lower_scale=[scale], upper_scale=[1],
                     linear=1, quadratic=1)],
    )
    original["penalty"] = {key: [key == "soft"] for key in original["penalty"]}
    original["units"].update(peak=["dimensionless"], D_t=[1])
    c.finite_tree(original)
    transformed = c.canonical_transform(original)
    c.finite_tree(transformed)
    row = transformed["row_order"].index("lower:0")
    assert transformed["upper"][row] == 0
    assert math.copysign(1, transformed["upper"][row]) == 1
