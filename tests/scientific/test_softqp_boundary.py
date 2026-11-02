import copy
import pytest
from pipeline import softqp_run
from pipeline.softqp_cases import cases


def test_adversarial_duplicate_case_id_blocks_bake(tmp_path, monkeypatch):
    catalog = cases()
    catalog[1].id = catalog[0].id
    monkeypatch.setattr(softqp_run, "cases", lambda: catalog)
    with pytest.raises(ValueError, match="exactly once"):
        softqp_run.bake(tmp_path)


def test_adversarial_semantics_mismatch_is_incompatible():
    result = softqp_run.run_case(next(c for c in cases() if c.id == "C03"))
    row = next(r for r in result["runs"] if r["method"] == "generalized")
    assert row["state"] == "incompatible" and row["result"] is None


def test_adversarial_inconsistent_group_weights_fail_native():
    case = copy.deepcopy(next(c for c in cases() if c.id == "C05"))
    case.reference[-1].alpha1[0] *= 2.0
    result = softqp_run.run_case(case)
    row = next(r for r in result["runs"] if r["method"] == "generalized")
    assert row["state"] == "failed" and row["reason"]


def test_adversarial_changed_artifact_byte_breaks_inventory(tmp_path):
    index = softqp_run.bake(tmp_path, selected=["C01"])
    path = tmp_path / "C01.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        softqp_run.verify_inventory(tmp_path, index)
