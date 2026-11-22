"""A portable display summary cannot impersonate a historical raw approval."""
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("slug", ["soft-constraint-study", "coupled-peak-study"])
def test_public_sidecar_binds_the_current_projection_without_reissuing_approval(slug):
    folder = ROOT / "manuscripts" / slug
    record = json.loads((folder / "publication-gate.json").read_text(encoding="utf-8"))
    assert record["kind"] == "historical-publication-record/v1"
    assert record["current_admission_ready"] is False
    assert "release_ready" not in record
    projection = record["public_review_projection"]
    raw = (folder / projection["path"]).read_bytes()
    document = json.loads(raw)
    assert projection["sha256"] == hashlib.sha256(raw).hexdigest()
    assert projection["authoritative_for_admission"] is False
    assert document["decision"] == "PUBLIC_SUMMARY_ONLY"
    assert document["authoritative_for_admission"] is False
    assert document["historical_raw_sha256"] == record["approval_at_publication"]["raw_sha256"]
    assert document["historical_source_commit"] == record["approval_at_publication"]["source_commit"]
    assert projection["sha256"] != record["approval_at_publication"]["raw_sha256"]
    pdf = (folder / record["pdf"]["path"]).read_bytes()
    assert len(pdf) == record["pdf"]["bytes"]
    assert hashlib.sha256(pdf).hexdigest() == record["pdf"]["sha256"]
