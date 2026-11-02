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


def test_validated_objective_baselines_preserve_reviewed_sources():
    baseline = json.loads((ROOT / "data-pipeline/validated-objectives.json").read_text())
    assert set(baseline["cases"]) == {f"C{i:02d}" for i in range(1, 16)}
    for case_id, expected in baseline["cases"].items():
        raw = (ROOT / "data/derived/softqp" / (case_id + ".json")).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected["source_sha256"]
        document = json.loads(raw)
        lifted = next(r for r in document["runs"] if r["method"] == "lifted")
        assert expected["objective"] == lifted["result"]["metrics"]["objective"]


@pytest.mark.parametrize("mutation", ["different-problem", "different-settings", "false-gap", "null-gap",
                                      "suboptimal-single", "suboptimal-all", "hard-threshold"])
def test_adversarial_input_settings_and_objective_parity(staged, monkeypatch, mutation):
    from pipeline.experiment_export import verify_campaign
    import pipeline.experiment_export as historical
    from pipeline.softqp_cases import cases, scalar

    # Historical replay has its own full positive/control gate; these inputs probe
    # only the scientific matrix admission and never run or retime that campaign.
    assert callable(verify_campaign)
    monkeypatch.setattr(historical, "verify_campaign", lambda *_: None)
    target, adapter = staged
    folder = target / "data/derived/softqp"
    index = json.loads((folder / "index.json").read_text())
    entry = index["cases"][3 if mutation == "hard-threshold" else 0]
    path = folder / entry["path"]
    doc = json.loads(path.read_text())
    if mutation == "different-problem":
        doc["problem"]["q"][0] += 1000
    elif mutation == "different-settings":
        doc["settings"]["max_iter"] = 1
    elif mutation in ("false-gap", "null-gap"):
        doc["runs"][2]["result"]["metrics"]["objective_gap_against_lifted"] = (100 if mutation == "false-gap" else None)
    elif mutation == "hard-threshold":
        result = doc["runs"][2]["result"]
        result["x"][0] += 1.04e-6
        result["metrics"].update(cases()[3].problem.evaluate(result["x"]))
        result["metrics"]["objective_gap_against_lifted"] = abs(
            result["metrics"]["objective"] - doc["runs"][0]["result"]["metrics"]["objective"])
        assert result["metrics"]["hard_violation"] > 1e-6
        result["metrics"]["hard_violation"] = 0.95e-6
    else:
        for run in (doc["runs"] if mutation == "suboptimal-all" else [doc["runs"][2]]):
            result = run["result"]
            result["x"] = [0]
            result["metrics"].update(scalar(-3).evaluate([0]), objective_gap_against_lifted=0)
    raw = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    entry["sha256"] = hashlib.sha256(raw).hexdigest()
    (folder / "index.json").write_text(json.dumps(index))
    with pytest.raises(ValueError):
        adapter.validate(target)


@pytest.mark.parametrize("mutation", ["one-method", "duplicate-method", "missing-case", "duplicate-case",
                                      "failed-cell", "false-index-flag", "bad-backend-status", "wrong-method",
                                      "all-incompatible", "short-x", "null-metrics", "false-metrics",
                                      "wrong-row-unit", "wrong-soft-policy"])
def test_adversarial_rehashed_incomplete_inventory_is_refused(staged, mutation):
    target, adapter = staged
    folder = target / "data/derived/softqp"
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    entry = index["cases"][3 if mutation == "short-x" else 0]
    path = folder / entry["path"]
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
    elif mutation == "wrong-method":
        doc["runs"][0]["result"]["method"] = "different-backend"
    elif mutation == "all-incompatible":
        for run in doc["runs"]:
            run.update(state="incompatible", result=None, reason="Fabricated incompatibility")
    elif mutation == "short-x":
        doc["runs"][0]["result"]["x"] = [0]
    elif mutation == "null-metrics":
        doc["runs"][0]["result"]["metrics"] = None
    elif mutation == "wrong-row-unit":
        doc["rows"][0]["unit"] = "unrelated-physical-unit"
    elif mutation == "wrong-soft-policy":
        doc["rows"][0]["soft"] = not doc["rows"][0]["soft"]
    else:
        doc["runs"][0]["result"]["metrics"]["objective"] += 1
    raw = (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    entry["sha256"] = hashlib.sha256(raw).hexdigest()
    (folder / "index.json").write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(ValueError):
        adapter.validate(target)
