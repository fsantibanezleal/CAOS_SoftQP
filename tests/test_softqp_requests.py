import copy
import hashlib
from pathlib import Path
import pytest
from pipeline.softqp_requests import execute_request
from pipeline.softqp_run import validate_document

ROOT = Path(__file__).resolve().parents[1]


def request(case="C01"):
    return dict(
        schema_version="softqp.run-request/v1",
        case_id=case,
        base_sha256=hashlib.sha256((ROOT / f"data/derived/softqp/{case}.json").read_bytes()).hexdigest(),
        lower_multiplier=2.0,
        upper_multiplier=3.0,
        quadratic_multiplier=1.5,
    )


def test_local_request_recomputes_a_changed_optimum():
    result = execute_request(request())
    validate_document(result, "softqp-local-export")
    row = next(r for r in result["result"]["runs"] if r["method"] == "asymmetric")
    # Lower branch: x+3 - .6 + 6*(x+1) = 0.
    assert row["result"]["x"] == pytest.approx([-8.4 / 7], abs=2e-6)
    assert row["result"]["metrics"]["objective_gap_against_lifted"] < 1e-7
    assert result["result"]["problem"]["penalty"]["lower_quadratic"] == [6.0]


@pytest.mark.parametrize(
    "field,value",
    [("lower_multiplier", True), ("upper_multiplier", 0), ("quadratic_multiplier", 101), ("extra", 1)],
)
def test_adversarial_request_rejects_unbounded_or_invalid_edits(field, value):
    doc = request()
    doc[field] = value
    with pytest.raises(Exception):
        execute_request(doc)


def test_adversarial_stale_and_grouped_requests_are_rejected():
    doc = request()
    doc["base_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        execute_request(doc)
    with pytest.raises(ValueError, match="separable"):
        execute_request(request("C05"))


def test_local_export_rejects_corrupted_result():
    result = execute_request(request())
    doc = copy.deepcopy(result)
    doc["result"]["runs"][0]["result"]["x"][0] = True
    with pytest.raises(Exception):
        validate_document(doc, "softqp-local-export")
