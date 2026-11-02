"""Registration and supervisor adversaries; no scientific observation is rerun."""

import copy
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from pipeline import coupled_freeze

ROOT = Path(__file__).resolve().parents[2]


def test_registered_scientific_sources_remain_unchanged():
    protocol = json.loads((ROOT / "docs/design/coupled-experiments-v1.json").read_text())
    registration = json.loads((ROOT / "docs/design/coupled-experiments-v1.registration.json").read_text())
    assert coupled_freeze.source_hashes(ROOT, protocol) == registration["source_sha256"]
    assert coupled_freeze.canonical_digest(protocol) == registration["protocol_sha256"]


@pytest.mark.parametrize("mutation", ["protocol", "source", "review-decision", "review-digest", "dirty", "untracked"])
def test_adversarial_registration_refuses_changed_authorities(tmp_path, mutation):
    root = tmp_path / "registered-repo"
    folder = root / "docs/design"
    folder.mkdir(parents=True)
    source = root / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    protocol = {"source_files": ["source.py"], "state": "locked"}
    hashes = {"source.py": hashlib.sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest()}
    review = {"decision": "ACCEPT", "source_sha256": hashes,
              "protocol_sha256": coupled_freeze.canonical_digest(protocol)}
    review_path = folder / "review.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    registration = {"source_sha256": hashes, "protocol_sha256": review["protocol_sha256"],
                    "review_path": "docs/design/review.json",
                    "review_sha256": coupled_freeze.canonical_digest(review)}
    (folder / "coupled-experiments-v1.registration.json").write_text(json.dumps(registration))
    (folder / "coupled-experiments-v1.json").write_text(json.dumps(protocol))
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Contract fixture", "-c",
                    "user.email=fixture@example.invalid", "commit", "-qm", "Registered fixture"],
                   check=True, capture_output=True)
    assert coupled_freeze.verify_registration(root, protocol)["commit"]
    changed = copy.deepcopy(protocol)
    if mutation == "protocol":
        changed["state"] = "changed"
    elif mutation == "source":
        source.write_text("value = 2\n")
    elif mutation == "dirty":
        review_path.write_text(json.dumps(review) + "\n")
    elif mutation == "untracked":
        subprocess.run(["git", "-C", str(root), "rm", "--cached", "source.py"],
                       check=True, capture_output=True)
    else:
        review["decision" if mutation == "review-decision" else "protocol_sha256"] = "forged"
        review_path.write_text(json.dumps(review))
    with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
        coupled_freeze.verify_registration(root, changed)


@pytest.mark.parametrize("failure", ["rss", "timeout", "output-size", "invalid-json", "incomplete-oracle"])
def test_adversarial_supervisor_refuses_limits_and_incomplete_output(tmp_path, monkeypatch, failure):
    from pipeline import coupled_campaign as campaign

    class FakeProcess:
        pid = 123
        exitcode = 0

        def __init__(self, *, target, args, daemon):
            self.result = Path(args[1])
            self.alive = failure in ("rss", "timeout")
            self.closed = False

        def start(self):
            text = "not-json" if failure == "invalid-json" else '{"state":"accepted"}'
            if failure == "output-size":
                text = "x" * 16777217
            self.result.write_text(text, encoding="utf-8")

        def is_alive(self):
            return self.alive

        def terminate(self):
            self.alive = False

        def kill(self):
            self.alive = False

        def join(self, timeout):
            pass

        def close(self):
            self.closed = True

    processes = []

    def process(**kwargs):
        instance = FakeProcess(**kwargs)
        processes.append(instance)
        return instance

    monkeypatch.setattr(campaign.mp, "get_context", lambda _: SimpleNamespace(Process=process))
    monkeypatch.setattr(campaign, "process_memory", lambda _: (200 if failure == "rss" else 1, 1))
    monkeypatch.setattr(campaign.tempfile, "tempdir", str(tmp_path))
    clock = iter([0.0] + [2.0 if failure == "timeout" else 0.0] * 20)
    monkeypatch.setattr(campaign.time, "monotonic", lambda: next(clock))
    worker = campaign.CoupledWorker({"process_memory_limit_bytes": 100, "trial_timeout_seconds": 1})
    result = worker.observe({}, "__oracle__", {"protocol": {"frames": 32}}, 10)
    expected = {"rss": "resource-limit", "timeout": "timeout", "output-size": "resource-limit"}
    assert result["state"] == expected.get(failure, "failed")
    assert result["elapsed_seconds"] is None
    assert worker.process is None and worker.restarts == 1
    assert all(instance.closed and not instance.alive for instance in processes)
