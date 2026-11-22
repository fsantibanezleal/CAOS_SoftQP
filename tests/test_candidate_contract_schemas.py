"""Archived actual candidate metadata and independent shape/qualification attacks."""

from copy import deepcopy
import json
from pathlib import Path

import jsonschema
import pytest

from pipeline.learned_comparison import contracts as c

ROOT = Path(__file__).resolve().parents[1] / "docs/contracts"


def document(kind):
    raw = (ROOT / "schemas" / f"softqp-{kind}.schema.json").read_bytes()
    schema = json.loads(raw)
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = c._validator(raw)
    value = json.loads((ROOT / "examples" / f"softqp-{kind}-fixture.json").read_bytes())
    validator.validate(value)
    return validator, value


def test_real_excluded_candidate_projection_preserves_trial_ancestry_and_legacy_lane():
    validator, receipt = document("candidate-trial-receipt")
    _, index = document("candidate-export")
    assert index["fixture_only"] and not index["scientifically_qualified"]
    assert sum(index["counts"].values()) == index["statuses"]["rows"] == 36
    assert receipt["numeric"]["sha256"] == receipt["numeric_sha256"]
    assert receipt["numeric"]["path"] == receipt["numeric_sha256"] + ".json"
    assert receipt["full_cost_ns"] == receipt["observed_ns"] - receipt["released_ns"]
    assert all(receipt[k] == index[k] for k in ("request_sha256", "policy_sha256", "profile_sha256"))
    old = deepcopy(receipt)
    old["schema"] = "softqp.r4.heldout-trial-receipt/1"
    del old["numeric"], old["frame_id"]
    original_schema = (ROOT / "schemas/softqp-learning-heldout-trial-receipt.schema.json").read_bytes()
    c._validator(original_schema).validate(old)
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(old)


@pytest.mark.parametrize("attack", ["extra", "missing-payload", "path", "oversized", "late", "warmup", "seed", "non-temporal-frame", "non-temporal-previous"])
def test_adversarial_candidate_trial_shape_refuses_invalid_cross_boundary_data(attack):
    validator, receipt = document("candidate-trial-receipt")
    if attack == "extra":
        receipt["approved"] = True
    elif attack == "missing-payload":
        del receipt["numeric"]
    elif attack == "path":
        receipt["numeric"]["path"] = "../outside.json"
    elif attack == "oversized":
        receipt["numeric"]["bytes"] = 16 * 2**20 + 1
    elif attack == "late":
        receipt["full_cost_ns"] = 10_000_000_000
    elif attack == "warmup":
        receipt["key"][7] = 2
    elif attack == "seed":
        receipt["key"][1] = 41001
    elif attack == "non-temporal-frame":
        receipt["key"][5] = 1
    else:
        receipt["key"][0] = "previous_osqp"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(receipt)


@pytest.mark.parametrize("attack", ["fixture-success", "unknown", "negative-count", "point-only", "false-hypothesis", "partial-startup", "success-without-startup"])
def test_adversarial_candidate_index_preserves_undefined_and_fixture_boundaries(attack):
    validator, index = document("candidate-export")
    if attack == "fixture-success":
        index["scientifically_qualified"] = True
    elif attack == "unknown":
        index["display_only_success"] = True
    elif attack == "negative-count":
        index["counts"]["failed"] = -1
    elif attack == "point-only":
        index["hypotheses"]["learned_osqp"]["estimate"] = 0
    elif attack == "false-hypothesis":
        index["hypotheses"]["learned_daqp"]["qualified"] = True
    elif attack == "partial-startup":
        index["cohort_sha256"] = "0" * 64
    else:
        index.update(fixture_only=False, scientifically_qualified=True, matrix_complete=True,
                     diagnostics_complete=True)
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(index)


@pytest.mark.parametrize("method", ["learned_osqp", "learned_daqp"])
def test_adversarial_schema_cannot_swap_nested_bootstrap_hypothesis(method):
    validator, index = document("candidate-export")
    # This constructed shape control grants no output or execution authority.
    index["hypotheses"][method] = dict(
        estimate=0, interval=[-1, 0], qualified=False, failed_statuses=0,
        bootstrap={"method": method, "file": {"path": "shape-control.u8", "format": "raw-uint8",
                                               "sha256": "0" * 64, "byte_count": 1}},
    )
    validator.validate(index)
    index["hypotheses"][method]["bootstrap"]["method"] = (
        "learned_daqp" if method == "learned_osqp" else "learned_osqp"
    )
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(index)
