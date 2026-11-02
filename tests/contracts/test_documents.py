"""Scientific deployment contracts on canonical, provider and fresh native outputs."""

import copy
import hashlib
import json
from pathlib import Path
import pytest
import contract_schemas as cs
from pipeline import pipeline

BAKE = cs.DERIVED_ROOTS["bake"]
FIXTURE = cs.DERIVED_ROOTS["fixture"]


def cross_field_errors(root):
    root = Path(root)
    errors = []
    index = cs.load_json(root / "manifests/index.json")
    errors += cs.errors("case-index", index)
    ids = [e["case_id"] for e in index["cases"]]
    if ids != sorted(set(ids)) or index["n_cases"] != len(ids) or index["default_case"] not in ids:
        errors.append("invalid case inventory")
    for entry in index["cases"]:
        manifest = cs.load_json(root / entry["manifest_path"])
        errors += cs.errors("case-manifest", manifest)
        if manifest["case_id"] != entry["case_id"] or manifest["lane"] != manifest["gate"]["lane"]:
            errors.append("manifest identity or gate drift")
        artifact = manifest["artifact"]
        raw = (root / artifact["path"]).read_bytes()
        if len(raw) != artifact["bytes"] or hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
            errors.append("artifact bytes or digest drift")
        doc = json.loads(raw)
        errors += cs.errors("softqp-case-result", doc)
        if doc["case_id"] != entry["case_id"]:
            errors.append("result identity drift")
        for run in doc["runs"]:
            if run["state"] == "available":
                metrics = run["result"]["metrics"]
                if any(
                    len(metrics[key]) != len(doc["rows"])
                    for key in ("lower_violation", "upper_violation", "slack")
                ):
                    errors.append("original row length drift")
    return errors


@pytest.fixture(scope="module")
def fresh_bake(tmp_path_factory):
    root = tmp_path_factory.mktemp("scientific-bake")
    pipeline.run_all(output_root=root)
    return root


def test_index_validates(fresh_bake):
    for root in [BAKE, FIXTURE, fresh_bake]:
        assert cs.errors("case-index", cs.load_json(root / "manifests/index.json")) == []


def test_manifests_validate(fresh_bake):
    for root in [BAKE, FIXTURE, fresh_bake]:
        assert cross_field_errors(root) == []


def test_every_root_passes_the_cross_field_rules(fresh_bake):
    for root in [BAKE, FIXTURE, fresh_bake]:
        assert cross_field_errors(root) == []


def test_fixture_tree_validates():
    assert cross_field_errors(FIXTURE) == []


def test_openapi_document_is_valid():
    from openapi_spec_validator import validate

    validate(cs.load_json(cs.OPENAPI), base_uri=cs.OPENAPI.as_uri())


def test_adversarial_drifted_documents_are_rejected():
    doc = cs.load_json(BAKE / "softqp/C01.json")
    bad = copy.deepcopy(doc)
    bad["runs"][0]["result"]["metrics"]["objective"] = True
    assert cs.errors("softqp-case-result", bad)
    manifest = cs.load_json(BAKE / "manifests/C01.json")
    manifest["lane"] = "live"
    assert cs.errors("case-manifest", manifest)


def test_adversarial_cross_field_rules_catch_what_the_schema_cannot(tmp_path):
    import shutil

    shutil.copytree(FIXTURE, tmp_path / "derived")
    root = tmp_path / "derived"
    path = root / "softqp/C01.json"
    doc = cs.load_json(path)
    doc["runs"][0]["result"]["metrics"]["lower_violation"].append(0.0)
    path.write_text(json.dumps(doc), encoding="utf-8")
    errors = cross_field_errors(root)
    assert "original row length drift" in errors and "artifact bytes or digest drift" in errors
