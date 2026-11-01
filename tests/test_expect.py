import json
from pathlib import Path
import pytest
from pipeline.core.expect import ExpectationError, check, check_document


def test_every_registered_case_meets_its_declared_range():
    root = Path(__file__).parents[1] / "data/derived/softqp"
    for path in root.glob("C*.json"):
        check_document(json.loads(path.read_text(encoding="utf-8")))


def test_a_value_outside_its_range_is_named():
    with pytest.raises(ExpectationError, match="hard_violation"):
        check("C01", {"hard_violation": (0, 1e-6)}, {"hard_violation": 1e-3})


def test_adversarial_a_case_without_expectations_or_with_an_unknown_metric_fails():
    with pytest.raises(ExpectationError, match="no expected range"):
        check("C01", {}, {})
    with pytest.raises(ExpectationError, match="unknown expected metric"):
        check("C01", {"unknown": (0, 1)}, {})
    with pytest.raises(ExpectationError):
        check("C01", {"objective": (0, 1)}, {"objective": True})
