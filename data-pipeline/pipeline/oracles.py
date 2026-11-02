"""Independent analytic branch oracle for unit-curvature scalar soft QPs."""

import math


def scalar_optimum(target, lower, upper, a_lower, b_lower, a_upper, b_upper):
    values = (target, lower, upper, a_lower, b_lower, a_upper, b_upper)
    if not all(math.isfinite(x) for x in values) or lower > upper or min(values[3:]) < 0:
        raise ValueError("invalid scalar oracle inputs")
    if target < lower:
        return min(lower, (target + a_lower + b_lower * lower) / (1 + b_lower))
    if target > upper:
        return max(upper, (target - a_upper + b_upper * upper) / (1 + b_upper))
    return target
