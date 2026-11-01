"""Check the real raw evidence, not a fabricated successful benchmark."""

import copy
import hashlib
import json
from pathlib import Path
import shutil
import pytest
from jsonschema import ValidationError
from pipeline.experiment_export import verify_campaign
from pipeline.softqp_run import validate_document

ROOT = Path(__file__).resolve().parents[1]


def test_experimental_exports_and_provider():
    for base in (ROOT / "data/derived/experiments", ROOT / "docs/contracts/fixtures/data/derived/experiments"):
        index = json.loads((base / "index.json").read_text(encoding="utf-8"))
        validate_document(index, "softqp-experiment-index")
        for entry in index["artifacts"]:
            raw = (base / entry["path"]).read_bytes()
            assert b"\r\n" not in raw, "Artifact digests must survive Git LF normalization"
            assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
            assert len(raw) == entry["bytes"]
            if entry["path"].endswith(".json"):
                validate_document(json.loads(raw), entry["schema"])
    campaign = verify_campaign(ROOT / "data/derived/experiments")
    assert campaign["completed_instances"] == campaign["planned_instances"]


def test_adversarial_experimental_contracts_reject_false_timing():
    root = ROOT / "data/derived/experiments"
    stream = json.loads((root / "stream.json").read_text(encoding="utf-8"))
    for mutate in (lambda d: d["frames"][0]["runs"][0].update(elapsed_seconds=True),
                   lambda d: d["frames"].pop(), lambda d: d.update(unknown=True)):
        changed = copy.deepcopy(stream)
        mutate(changed)
        with pytest.raises(ValidationError):
            validate_document(changed, "softqp-stream")


def test_adversarial_export_rejects_missing_raw_trial(tmp_path):
    root = ROOT / "data/derived/experiments"
    for name in ("campaign.json", "datasets.json", "trials.jsonl", "trials.csv"):
        shutil.copyfile(root / name, tmp_path / name)
    path = tmp_path / "trials.jsonl"
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b"".join(lines[1:]))
    # Even with a self-consistent digest, deleting an observation must not change the denominator.
    document = json.loads((tmp_path / "campaign.json").read_text(encoding="utf-8"))
    entry = next(a for a in document["artifacts"] if a["path"] == path.name)
    entry.update(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    (tmp_path / "campaign.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="missing or duplicate"):
        verify_campaign(tmp_path)
