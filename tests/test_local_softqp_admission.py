"""The actual local replay admission must reject rehashed but incomplete inventories."""

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def staged(tmp_path):
    target = tmp_path / "candidate"
    shutil.copytree(ROOT / "data/derived", target / "data/derived")
    spec = importlib.util.spec_from_file_location("local_softqp_adapter", ROOT / "scripts/local/softqp_adapter.py")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    return target, adapter


def test_complete_authored_inventory_is_admitted(staged):
    target, adapter = staged
    adapter.validate(target)


@pytest.mark.parametrize("mutation", ["one-method", "duplicate-method", "missing-case", "duplicate-case",
                                      "failed-cell", "false-index-flag", "bad-backend-status", "wrong-method"])
def test_adversarial_rehashed_incomplete_inventory_is_refused(staged, mutation):
    target, adapter = staged
    folder = target / "data/derived/softqp"
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    path = folder / index["cases"][0]["path"]
    doc = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "one-method":
        doc["runs"] = doc["runs"][:1]
    elif mutation == "duplicate-method":
        doc["runs"][1] = doc["runs"][0]
    elif mutation == "missing-case":
        index["cases"] = index["cases"][:-1]
    elif mutation == "duplicate-case":
        index["cases"][-1] = index["cases"][0]
    elif mutation == "failed-cell":
        doc["runs"][0].update(state="failed", reason="preserved failed solve")
        index["cases"][0]["failed"] = True
    elif mutation == "false-index-flag":
        index["cases"][0]["failed"] = True
    elif mutation == "bad-backend-status":
        doc["runs"][0]["result"]["status_code"] = -7
    else:
        doc["runs"][0]["result"]["method"] = "different-backend"
    raw = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    index["cases"][0]["sha256"] = hashlib.sha256(raw).hexdigest()
    (folder / "index.json").write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(ValueError):
        adapter.validate(target)
