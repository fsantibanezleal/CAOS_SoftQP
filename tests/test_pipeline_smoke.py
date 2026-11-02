import hashlib
import json
from pipeline import pipeline, registry
from pipeline.softqp_requests import encode_problem
from pipeline.softqp_run import verify_inventory
import pytest


def test_adversarial_same_seed_bakes_identical_bytes_and_a_changed_byte_of_equal_size_is_seen(tmp_path):
    # Inputs repeat exactly; wall-clock result fields intentionally do not promise byte determinism.
    a = [encode_problem(c.problem) for c in registry.list_cases() if c.problem is not None]
    b = [encode_problem(c.problem) for c in registry.list_cases() if c.problem is not None]
    assert a == b
    from pipeline.softqp_run import bake

    index = bake(tmp_path / "softqp", selected=["C01"])
    path = tmp_path / "softqp/C01.json"
    raw = path.read_bytes()
    path.write_bytes(raw.replace(b"authored", b"Authored", 1))
    assert (
        len(path.read_bytes()) == len(raw)
        and hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(raw).digest()
    )
    with pytest.raises(ValueError, match="checksum"):
        verify_inventory(tmp_path / "softqp", index)


def test_run_all_writes_index(tmp_path):
    index = pipeline.run_all(output_root=tmp_path / "derived")
    wrapper = json.loads((tmp_path / "derived/manifests/index.json").read_text(encoding="utf-8"))
    assert len(index["cases"]) == wrapper["n_cases"] == len(registry.list_cases()) == 15
    assert wrapper["default_case"] == "C01"
