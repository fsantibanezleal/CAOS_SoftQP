"""Original-space acceptance checks, independent of backend success labels."""

import math


class ExpectationError(ValueError):
    pass


def check(case_id, expect, result):
    if not expect:
        raise ExpectationError(f"{case_id}: no expected range declared")
    ranges = {}
    for name, (lower, upper) in expect.items():
        if name not in result:
            raise ExpectationError(f"{case_id}: unknown expected metric {name!r}")
        value = result[name]
        if lower > upper:
            raise ExpectationError(f"{case_id}: empty range for {name}")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not lower <= value <= upper
        ):
            raise ExpectationError(f"{case_id}: {name}={value} outside [{lower}, {upper}]")
        ranges[name] = [float(lower), float(upper)]
    return ranges


def check_document(document):
    for run in document["runs"]:
        if run["state"] != "available":
            continue
        metrics = run["result"]["metrics"]
        band = {"hard_violation": (0, 1e-6)}
        gap = metrics.get("objective_gap_against_lifted")
        if gap is not None:
            band["objective_gap_against_lifted"] = (0, 1e-6 * max(1, abs(metrics["objective"])))
        check(document["case_id"] + "/" + run["method"], band, metrics)
    return document
