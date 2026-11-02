"""Scientific readiness: every applicable state and the standard-library guard."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
from pipeline.core import readiness
from pipeline.io.formats import write_json
import contract_schemas as cs

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def repo(tmp_path):
    target = tmp_path / "repo"
    (target / "docs/contracts").mkdir(parents=True)
    shutil.copy2(ROOT / "docs/contracts/catalog.md", target / "docs/contracts/catalog.md")
    shutil.copytree(ROOT / "data/derived", target / "data/derived")
    # The isolated positive fixture deliberately matches its copied bake.
    # The real checkout's older-bake state is checked independently below.
    inventory = json.loads((target / "data/derived/manifests/index.json").read_text(encoding="utf-8"))
    (target / "VERSION").write_text(inventory["engine_version"] + "\n", encoding="utf-8")
    return target


def compute(root):
    return readiness.compute(repo_root=root, derived_root=root / "data/derived")


def row(doc, rid):
    return next(r for r in doc["contracts"] if r["id"] == rid)


def test_committed_readiness_is_current():
    fresh = compute(ROOT)
    assert cs.errors("readiness", fresh) == []
    assert (ROOT / "data/derived/readiness.json").read_bytes() == json.dumps(
        fresh, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def test_catalog_rows_in_order_without_readiness():
    catalog = readiness.parse_catalog((ROOT / "docs/contracts/catalog.md").read_text(encoding="utf-8"))
    assert [r["id"] for r in compute(ROOT)["contracts"]] == [
        r["id"] for r in catalog if r["id"] != "readiness"
    ]


def test_state_available(repo):
    assert row(compute(repo), "softqp-case-result")["state"] == "available"


def test_adversarial_state_partial_manifests(repo):
    (repo / "data/derived/manifests/C01.json").unlink()
    entry = row(compute(repo), "case-manifest")
    assert entry["state"] == "partial" and entry["missing"] == ["manifests/C01.json"]


def test_state_partial_results(repo):
    (repo / "data/derived/softqp/C01.json").unlink()
    entry = row(compute(repo), "softqp-case-result")
    assert entry["state"] == "partial" and entry["missing"] == ["softqp/C01.json"]


def test_adversarial_state_stale(repo):
    path = repo / "data/derived/manifests/index.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    version = (repo / "VERSION").read_text(encoding="utf-8").strip().split(".")
    version[-1] = str(int(version[-1]) + 1).zfill(3)
    doc["engine_version"] = ".".join(version)
    write_json(path, doc)
    assert row(compute(repo), "softqp-case-result")["state"] == "stale"


def test_adversarial_state_missing_without_an_index(repo):
    (repo / "data/derived/softqp/index.json").unlink()
    entry = row(compute(repo), "softqp-index")
    assert entry["state"] == "missing" and entry["provenance"] is None


def test_adversarial_state_provider_through_a_catalog_copy(repo):
    path = repo / "docs/contracts/catalog.md"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    inside = False
    for i, line in enumerate(lines):
        if line == "## Contracts":
            inside = True
        elif line.startswith("## "):
            inside = False
        if inside and line.startswith("| softqp-index |"):
            lines[i] = line.rsplit("| real |", 1)[0] + "| active |"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    entry = row(compute(repo), "softqp-index")
    assert entry["state"] == "provider" and entry["provenance"] == "fixture"


def test_a_status_other_than_real_or_active_fails(repo):
    path = repo / "docs/contracts/catalog.md"
    text = path.read_text(encoding="utf-8").replace("| real |", "| invalid |", 1)
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="invalid status"):
        compute(repo)


def test_determinism_and_normalised_hash(repo):
    first = compute(repo)
    path = repo / "docs/contracts/catalog.md"
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert compute(repo) == first


def test_adversarial_check_readiness_runs_without_numpy():
    proc = subprocess.run(
        [sys.executable, "-S", str(ROOT / "scripts/check_readiness.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_adversarial_check_readiness_fails_on_a_changed_catalog(repo):
    path = repo / "docs/contracts/catalog.md"
    path.write_bytes(path.read_bytes() + b"\nChanged catalog description.\n")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_readiness.py"), str(repo)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1 and "catalog_sha256" in proc.stdout


def test_adversarial_check_readiness_reports_an_unknown_status(repo):
    path = repo / "docs/contracts/catalog.md"
    path.write_text(path.read_text(encoding="utf-8").replace("| real |", "| done |", 1), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_readiness.py"), str(repo)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1 and "invalid status" in proc.stdout


@pytest.mark.parametrize("rid", [
    "softqp-coupled-batch", "softqp-coupled-observation", "softqp-coupled-campaign", "softqp-coupled-lesson",
])
def test_adversarial_coupled_examples_do_not_establish_deployed_evidence(tmp_path, rid):
    """An implemented offline exchange is not a deployed research-data source."""
    for derived in (ROOT / "data/derived", tmp_path / "absent-derived"):
        entry = row(readiness.compute(repo_root=ROOT, derived_root=derived), rid)
        assert entry["state"] == "missing"
        assert entry["provenance"] is None
        assert "offline" in entry["reason"]["en"].lower()


@pytest.mark.parametrize("payload", ["{}", "not-json", '{"state":"accepted"}'])
def test_adversarial_undeclared_coupled_payload_cannot_become_available(tmp_path, payload):
    """Planting a file cannot admit an undeclared or unvalidated replay lane."""
    target = tmp_path / "coupled"
    target.mkdir()
    (target / "campaign.json").write_text(payload, encoding="utf-8")
    document = readiness.compute(repo_root=ROOT, derived_root=tmp_path)
    for rid in ("softqp-coupled-batch", "softqp-coupled-observation", "softqp-coupled-campaign", "softqp-coupled-lesson"):
        assert row(document, rid)["state"] == "missing"


def test_adversarial_fixture_coupled_rows_remain_labelled_providers(tmp_path):
    document = readiness.compute(
        repo_root=ROOT, derived_root=tmp_path,
        catalog_path=ROOT / "docs/contracts/fixtures/catalog.md",
    )
    for rid in ("softqp-coupled-batch", "softqp-coupled-observation", "softqp-coupled-campaign", "softqp-coupled-lesson"):
        entry = row(document, rid)
        assert entry["state"] == "provider"
        assert entry["provenance"] == "fixture"
        assert entry["reason"] is not None
