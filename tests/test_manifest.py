import hashlib
import json
from pathlib import Path
from pipeline.core.manifest import export_manifests
from pipeline.softqp_run import bake


def test_manifest_matches_artifact_and_gate(tmp_path):
    bake(tmp_path / "softqp", selected=["C01"])
    index = export_manifests(tmp_path)
    manifest = json.loads((tmp_path / index["cases"][0]["manifest_path"]).read_text(encoding="utf-8"))
    artifact = tmp_path / manifest["artifact"]["path"]
    assert manifest["artifact"]["bytes"] == artifact.stat().st_size
    assert manifest["artifact"]["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert manifest["lane"] == manifest["gate"]["lane"] == "precompute"


def test_small_native_cases_are_not_declared_browser_live():
    # A tiny problem still requires the native extension: bytes alone cannot admit a live browser lane.
    root = Path(__file__).parents[1] / "data/derived/manifests"
    for path in root.glob("C*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["lane"] == "precompute" and doc["gate"]["reasons"]
