"""Export and execute bounded edits of the committed scientific case catalog."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import numpy as np
from softqp.problem import Penalty
from .softqp_cases import cases
from .softqp_run import run_case, validate_document

ROOT = Path(__file__).resolve().parents[2]


def encode_problem(problem):
    def matrix(value):
        value = value.tocsc()
        return dict(
            shape=list(value.shape),
            data=value.data.tolist(),
            indices=value.indices.tolist(),
            indptr=value.indptr.tolist(),
        )

    def bounds(value):
        return [float(x) if np.isfinite(x) else None for x in value]

    return dict(
        P=matrix(problem.P),
        q=problem.q.tolist(),
        A=matrix(problem.A),
        lower=bounds(problem.lower),
        upper=bounds(problem.upper),
        penalty={
            name: getattr(problem.penalty, name).tolist()
            for name in ("lower_linear", "upper_linear", "lower_quadratic", "upper_quadratic", "soft")
        },
    )


def execute_request(request, *, derived=ROOT / "data/derived/softqp"):
    validate_document(request, "softqp-run-request")
    path = Path(derived) / f"{request['case_id']}.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != request["base_sha256"]:
        raise ValueError("base artifact checksum mismatch; use the same committed scientific inventory")
    baseline = validate_document(json.loads(raw), "softqp-case-result")
    case = next(c for c in cases() if c.id == request["case_id"])
    if case.problem is None:
        raise ValueError("cost editing supports separable cases only; grouped penalties are not converted")
    if baseline.get("problem") != encode_problem(case.problem):
        raise ValueError(
            "base artifact inputs differ from this source catalog; use the matching source revision"
        )
    p = case.problem.penalty
    lower, upper, quadratic = (
        request[k] for k in ("lower_multiplier", "upper_multiplier", "quadratic_multiplier")
    )
    penalty = Penalty(
        p.lower_linear * lower,
        p.upper_linear * upper,
        p.lower_quadratic * lower * quadratic,
        p.upper_quadratic * upper * quadratic,
        p.soft.copy(),
    )
    case = replace(case, problem=replace(case.problem, penalty=penalty))
    result = run_case(case)
    result["source"] = "local native execution of declared cost edits; authored synthetic case"
    envelope = dict(schema_version="softqp.local-export/v1", request=request, result=result)
    return validate_document(envelope, "softqp-local-export")
