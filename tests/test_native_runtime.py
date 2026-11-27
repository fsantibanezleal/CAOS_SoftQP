"""Fixed native 49-package launch and excluded live-worker software controls."""

from dataclasses import fields
from pathlib import Path
import os
import runpy
import subprocess

import pytest

from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import native_labels as n

from runtime_config import native49
from test_native_labels import build_plan


_ROOT = Path(__file__).resolve().parents[1]
_ENV = _ROOT / "environments/method-extension-scientific"
_BYTES = ("source_lock_bytes", "dependency_lock_bytes", "generator_source_bytes", "producer_source_bytes")


def _helper():
    return runpy.run_path(str(_ENV / "native_runtime.py"))


def _context_fixture(context):
    result = {}
    for field in fields(c.AdmissionContext):
        if not field.init:
            continue
        key = field.name
        value = getattr(context, key)
        if key == "authority":
            value = str(value.root)
        elif isinstance(value, Path):
            value = str(value)
        elif key in _BYTES:
            value = value.hex()
        elif key == "forbidden_roots":
            value = list(map(str, value))
        elif key == "catalog":
            value = {k: dict(v) for k, v in value.items()}
        elif key in ("settings_hashes", "source_records", "problem_hashes"):
            value = dict(value)
        elif key == "diagnostic_evidence":
            assert not value
            value = {}
        result[key] = value
    return result


def load_fixture_context(admission):
    """Approved test-only resolver loaded solely in the hashed qualification route."""
    assert set(admission) == {"root", "context"}
    meta = Path(admission["root"])
    doc = n._decode(n._native_scope_file(meta, admission["context"]))
    assert doc["allow_fixture"] is True and not doc["diagnostic_evidence"]
    doc["root"] = Path(doc["root"])
    doc["authority"] = c.Authority.load(Path(doc["authority"]))
    doc["forbidden_roots"] = tuple(map(Path, doc["forbidden_roots"]))
    for key in _BYTES:
        doc[key] = bytes.fromhex(doc[key])
    for key in ("expected_result_keys", "expected_diagnostic_keys"):
        doc[key] = tuple(map(tuple, doc[key]))
    doc["fit_source_ids"] = tuple(doc["fit_source_ids"])
    return c.AdmissionContext(**doc), meta


def fixture_input(base, profile_sha256, runtime_snapshot):
    """Bind the same analytic q=2/infeasible fixtures used for predecessor SDK tests."""
    nominated = native49()
    assert profile_sha256 == nominated.profile_sha256 and runtime_snapshot == nominated.snapshot
    profile = runtime_snapshot / "profile"
    assert n._file_sha(profile / "provenance.json") == profile_sha256
    plan, source_authority, _, _ = build_plan(base)
    meta = base / "authority"
    meta.mkdir()
    output = base / "output"
    output.mkdir()
    context = plan.context
    predecessor = source_authority.document
    predecessor["runtime"].update(
        python=str(nominated.python),
        python_sha256=n._file_sha(nominated.python),
        base_python=str(nominated.base_python),
        base_python_sha256=n._file_sha(nominated.base_python),
        python_dll=str(nominated.base_python.with_name("python312.dll")),
        python_dll_sha256=n._file_sha(nominated.base_python.with_name("python312.dll")),
        profile=str(profile),
        profile_sha256=profile_sha256,
        checker_sha256=n._file_sha(profile / "check_lock.py"),
        defaults_sha256=n._file_sha(profile / "defaults.json"),
    )
    predecessor["settings_hashes"] = n.settings_identities(predecessor["runtime"])
    predecessor["sources"] = {
        key: n._file_sha(runtime_snapshot / "source/data-pipeline/pipeline" / key)
        for key in predecessor["sources"]
    }
    assert n._file_sha(profile / "provenance.json") == profile_sha256
    preflight = n._persist(meta / "preflight.json", n._decode(plan.preflight.receipt_bytes))
    authority = n._persist(meta / "native-authority.json", predecessor)
    context_ref = n._persist(meta / "context.json", _context_fixture(context))
    request = {
        "schema": "softqp.r4.native-request/1",
        "operation": "native-label-fixture",
        "preflight_sha256": plan.preflight.sha256,
        "roles": list(plan.roles),
        "inventory_sha256": predecessor["inventory_sha256"],
    }
    request_ref = n._persist(meta / "request.json", request)
    policy = {
        "schema": "softqp.r4.native-policy/1",
        "operation": request["operation"],
        "request_sha256": request_ref["sha256"],
        "profile_sha256": profile_sha256,
        "admission": {"root": str(meta), "context": context_ref},
        "scope": {
            "preflight": preflight,
            "authority": authority,
            "roles": request["roles"],
            "inventory_sha256": request["inventory_sha256"],
            "max_wall_seconds": 900,
        },
        "output_root": str(output),
        "artifact_roots": [str(context.root), str(output)],
    }
    policy_ref = n._persist(meta / "policy.json", policy)
    return meta, request_ref, policy_ref, output, plan, source_authority


def test_independent_native_policy_scope_and_profile(tmp_path):
    helper = _helper()
    request = {
        "schema": "softqp.r4.native-request/1",
        "operation": "native-label",
        "preflight_sha256": "1" * 64,
        "roles": ["train", "validation"],
        "inventory_sha256": "2" * 64,
    }
    policy = {
        "schema": "softqp.r4.native-policy/1",
        "operation": request["operation"],
        "request_sha256": "",
        "profile_sha256": "3" * 64,
        "admission": {},
        "scope": {
            "preflight": {"sha256": request["preflight_sha256"]},
            "authority": {},
            "roles": request["roles"],
            "inventory_sha256": request["inventory_sha256"],
            "max_wall_seconds": 900,
        },
        "output_root": str(tmp_path),
        "artifact_roots": [],
    }

    def launch():
        raw = helper["encode"](request)
        policy["request_sha256"] = helper["digest"](raw)
        return raw, helper["encode"](policy)

    assert helper["native_scope"](launch(), "3" * 64)[2] == tmp_path / "native-run"
    with pytest.raises(ValueError, match="policy"):
        helper["native_scope"](launch(), "4" * 64)
    with pytest.raises(ValueError, match="request"):
        helper["native_scope"](launch(), "3" * 64, fixture_only=True)
    request["roles"] = ["test"]
    with pytest.raises(ValueError, match="non-test"):
        helper["native_scope"](launch(), "3" * 64)
    with pytest.raises(ModuleNotFoundError, match="softqp_native_runtime_custody"):
        n.dispatch_registered_native(launch()[0], object())


def test_native_permit_is_bound_to_frame_generation_and_prior_response(tmp_path):
    request = {
        "index": 1,
        "role": "validation",
        "generation": 7,
        "stage": "cold",
        "nonce": "f" * 32,
        "frame_id": "q2",
        "reference_sha256": "a" * 64,
        "original": None,
    }
    spec = {"generation": 7, "scope_sha256": "c" * 64, "nonce": "f" * 32, "roles": ["validation"]}
    live_calls = []
    with pytest.raises(ValueError, match="lost prior"):
        n._leaf_permit(
            tmp_path,
            spec,
            request,
            n._encode(request),
            (0, "q2", None, None, "b" * 64),
            lambda: live_calls.append(1),
        )
    assert live_calls == [] and not list(tmp_path.iterdir())
    permit = n._stage_permit(spec, request)
    n._persist(tmp_path / "permit-000001.json", {**permit, "role": "train"})
    with pytest.raises(ValueError, match="permit unavailable"):
        n._leaf_permit(
            tmp_path,
            spec,
            request,
            n._encode(request),
            (0, "q2", None, None, "a" * 64),
            lambda: live_calls.append(1),
        )
    assert live_calls == [1]


def test_actual_49_owned_native_label_and_infeasible_reference(tmp_path):
    nominated = native49()
    snapshot = nominated.snapshot
    profile = snapshot / "profile"
    profile_sha = nominated.profile_sha256
    meta, request, policy, output, original_plan, original_authority = fixture_input(
        tmp_path, profile_sha, snapshot
    )
    run = tmp_path / "supervisor"
    cmd = [
        str(nominated.python),
        "-I",
        "-S",
        "-B",
        str(profile / "verify.py"),
        "--native-fixture",
        "--python",
        str(nominated.python),
        "--base-python",
        str(nominated.base_python),
        "--profile",
        str(profile),
        "--source",
        str(snapshot / "source"),
        "--tools",
        str(nominated.tools),
        "--run",
        str(run),
        "--expected-profile-sha256",
        profile_sha,
        "--request",
        str(meta / request["path"]),
        "--expected-request-sha256",
        request["sha256"],
        "--policy",
        str(meta / policy["path"]),
        "--expected-policy-sha256",
        policy["sha256"],
    ]
    child = subprocess.run(cmd, capture_output=True, timeout=1500)
    (tmp_path / "supervisor-stdout.txt").write_bytes(child.stdout)
    (tmp_path / "supervisor-stderr.txt").write_bytes(child.stderr)
    assert child.returncode == 0, (
        child.stdout,
        child.stderr,
        (run / "stderr.log").read_bytes() if (run / "stderr.log").exists() else None,
    )
    root = output / "native-run"
    manifest = n._decode((root / "native-run.json").read_bytes())
    assert manifest["fixture_only"] and len(manifest["workers"]) == 1
    receipt = n._decode((root / manifest["workers"][0]["path"]).read_bytes())
    assert receipt["audit"]["distributions"] == 49 and receipt["audit"]["profile_sha256"] == profile_sha
    assert receipt["pid"] == receipt["verified_files"]["pid"] != receipt["guardian"]["owner"]
    assert receipt["guardian"]["operation"] == "native-label-fixture"
    assert receipt["guardian"]["generation"] == 0 and len(list(root.glob("ordinal-*.json"))) == len(
        manifest["rows"]
    )
    rows = {row["input"]["frame"]["artifact_id"]: row for row in manifest["rows"]}
    assert set(rows) == {"native-bad", "native-cal", "native-ok", "native-psd", "native-val"}
    assert rows["native-bad"]["state"] == "oracle-failed"
    assert rows["native-cal"]["state"] == "accepted", rows["native-cal"]
    actual = n._decode((root / rows["native-cal"]["attempt"]["path"]).read_bytes())
    raw = actual["reference"]["observed"]["reference"]
    assert set(raw["references"]) == {"stock-osqp", "clarabel", "piqp"}
    assert actual["cold"]["observed"]["result"]["raw_side_dual"]
    label = c.strict_loads((root / rows["native-cal"]["label"]["path"]).read_bytes())["payload"]
    assert {row["metrics"]["f_ref"] for row in label["oracle_results"]} == {-0.25}
    import json

    observed = json.loads((run / "receipt.json").read_bytes())
    assert observed["cleanup"] == "owned-process-tree-closed"
    assert observed["status"] == "native-fixture-observed" and observed["fixture_only"] is True
    assert observed["i1_issued"] is False
    assert original_authority.document["mode"] == "fixture" and original_plan.context.allow_fixture


def test_native_leaf_scope_refuses_stale_generation_job_and_helper_bytes(tmp_path):
    import time

    helper = _helper()
    spec = {
        "schema": "softqp.r4.native-leaf/1",
        "operation": "native-label",
        "nonce": "a" * 32,
        "owner": os.getpid(),
        "generation": 0,
        "scope_sha256": "1" * 64,
        "authority_sha256": "2" * 64,
        "profile_sha256": "3" * 64,
        "request_sha256": "4" * 64,
        "policy_sha256": "5" * 64,
        "fixture_only": False,
        "roles": ["validation"],
        "deadline_monotonic_ns": time.monotonic_ns() + 10**9,
    }
    helper["check_leaf"](spec, "3" * 64, fixture_only=False)
    for tamper in (
        {"generation": -1},
        {"deadline_monotonic_ns": time.monotonic_ns() - 1},
        {"profile_sha256": "4" * 64},
        {"fixture_only": True},
    ):
        with pytest.raises(ValueError, match="native leaf scope"):
            helper["check_leaf"]({**spec, **tamper}, "3" * 64, fixture_only=False)
    verify = runpy.run_path(str(_ENV / "verify.py"))
    from types import SimpleNamespace

    original = (_ENV / "native_runtime.py").read_bytes()
    (tmp_path / "native_runtime.py").write_bytes(original + b" ")
    with pytest.raises(ValueError, match="external byte identity"):
        verify["native_component"](
            SimpleNamespace(profile=tmp_path), {"native_runtime_sha256": n._sha(original)}
        )
    with pytest.raises(ValueError, match="cannot resolve"):
        verify["require_owned_job"]("SoftQP-Lesson-nonexistent-native49-job")


def test_standalone_leaf_refuses_scientific_before_any_runtime_import(tmp_path, monkeypatch):
    authority = n._persist(tmp_path / "authority.json", {"mode": "scientific"})
    monkeypatch.setattr(n, "_profile_checks", lambda _: pytest.fail("standalone scientific import executed"))
    with pytest.raises(ValueError, match="excluded-fixture only"):
        n._worker(tmp_path, authority["sha256"], "a" * 32)
    assert not (tmp_path / "installed-files.json").exists()


def test_late_native_payload_decoding_does_not_become_an_observation(tmp_path, monkeypatch):
    child = object.__new__(n._OwnedWorker)
    child._monitor = lambda: None
    n._persist(tmp_path / "response.json", {"native": "observed"})
    elapsed = iter((100, 100.01, 100.5))
    monkeypatch.setattr(n.time, "monotonic", lambda: next(elapsed))
    with pytest.raises(TimeoutError, match="deadline reading"):
        child.wait_file(tmp_path / "response.json", 0.1)
