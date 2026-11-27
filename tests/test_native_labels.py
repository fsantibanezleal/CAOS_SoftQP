"""Actual isolated SDK worker and supervised custody controls."""

from collections import Counter
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import native_labels as n
from pipeline.learned_comparison import stream_inputs as stream
from runtime_config import native49, sdk45
from test_learned_contracts import PROVIDER
from test_stream_inputs import build_factored, put


PROFILE_SHA = "a4bfa531f8af72412cc6bfbaacf57e0cd3d9545a481a780a5caba96448629f3d"
WHEEL_SHA = "6b930ca688e629ee11b7e816c2b160135c817de382082e3876c8504d40da1c89"
CHECKER_SHA = "72d8e12a3a568b120186b3c8ae44895b33435fea32022da40d9b9537291db535"
DEFAULTS_SHA = "a11af752c5ab8f01352d0b44b341d5d431dd451ec704b9e65774e839dd5ad952"


def runtime_identity():
    config = sdk45()
    profile = config.profile
    assert n._file_sha(profile / "provenance.json") == PROFILE_SHA
    assert n._file_sha(config.wheel) == WHEEL_SHA
    assert n._file_sha(profile / "check_lock.py") == CHECKER_SHA
    assert n._file_sha(profile / "defaults.json") == DEFAULTS_SHA
    base = Path(
        subprocess.check_output(
            [str(config.python), "-I", "-S", "-B", "-c", "import sys; print(sys._base_executable)"], text=True,
            timeout=15,
        ).strip()
    )
    dll = base.with_name("python312.dll")
    return {
        "python": str(config.python),
        "python_sha256": n._file_sha(config.python),
        "base_python": str(base),
        "base_python_sha256": n._file_sha(base),
        "python_dll": str(dll),
        "python_dll_sha256": n._file_sha(dll),
        "profile": str(profile),
        "profile_sha256": PROFILE_SHA,
        "checker_sha256": CHECKER_SHA,
        "defaults_sha256": DEFAULTS_SHA,
        "wheel": str(config.wheel),
        "wheel_sha256": WHEEL_SHA,
        "engine_source": "febdc8ebaf424b7256a4a939055851ab331ff23a",
    }


def test_runtime_configuration_distinguishes_absent_and_invalid(monkeypatch, tmp_path):
    for prefix, names in (
        ("SDK45_FIXTURE", ("PYTHON", "PROFILE", "WHEEL")),
        ("NATIVE49_FIXTURE", ("SNAPSHOT", "PYTHON", "TOOLS", "PROFILE_SHA256", "BASE_PYTHON")),
    ):
        for name in names:
            monkeypatch.delenv(f"SOFTQP_{prefix}_{name}", raising=False)
    for read in (sdk45, native49):
        with pytest.raises(pytest.skip.Exception, match="not nominated"):
            read()
    monkeypatch.setenv("SOFTQP_SDK45_FIXTURE_PYTHON", sys.executable)
    with pytest.raises(pytest.fail.Exception, match="incomplete"):
        sdk45()
    monkeypatch.setenv("SOFTQP_SDK45_FIXTURE_PROFILE", str(tmp_path))
    monkeypatch.setenv("SOFTQP_SDK45_FIXTURE_WHEEL", str(tmp_path / "missing.whl"))
    with pytest.raises(pytest.fail.Exception, match="invalid nominated file"):
        sdk45()
    for key in ("SNAPSHOT", "PYTHON", "TOOLS", "PROFILE_SHA256"):
        monkeypatch.setenv(f"SOFTQP_NATIVE49_FIXTURE_{key}", str(tmp_path))
    with pytest.raises(pytest.fail.Exception, match="independently pinned"):
        native49()


def test_configured_sdk45_matches_independent_release_pins():
    config = runtime_identity()
    assert config["profile_sha256"] == PROFILE_SHA and config["wheel_sha256"] == WHEEL_SHA


def native_problem(role, q, name, *, family="N01", original=None):
    payload = PROVIDER["problem_payload"](
        role, q, family=family, original=original, control="contract-fixture:native-label-math-control"
    )
    payload["source"].update(source_id=name, parent_id="parent-" + name)
    return payload


def build_plan(root, *, roles=("train", "validation", "calibration")):
    runtime = runtime_identity()
    context, docs, refs = PROVIDER["build"](root / "source")
    context = replace(context, settings_hashes={**context.settings_hashes, **n.settings_identities(runtime)})
    protocol = refs["protocol"]
    impossible = deepcopy(docs["problem-train"]["payload"]["original"])
    impossible.update(
        n=2,
        m=3,
        P=c.csc([[1, 0], [0, 1]]),
        A=c.csc([[1, 0], [1, 0], [0, 1]]),
        q=[0, 0],
        lower=[None, 1, 0],
        upper=[0, None, 1],
        lower_finite=[False, True, True],
        upper_finite=[True, False, True],
    )
    impossible["penalty"] = {
        key: ([False] * 3 if key == "soft" else [0] * 3) for key in impossible["penalty"]
    }
    impossible["units"].update(
        D_x=[1, 1], D_r=[1, 1, 1], variable=["dimensionless"] * 2, row=["dimensionless"] * 3
    )
    psd = deepcopy(impossible)
    psd.update(
        P=c.csc([[1, 0], [0, 0]]),
        A=c.csc([[1, 0], [0, 1], [0, 0]]),
        lower=[0, 0, None],
        upper=[0, 0, 0],
        lower_finite=[True, True, False],
        upper_finite=[True, True, True],
    )
    known = {
        "native-bad": native_problem("train", 0, "infeasible", family="N02", original=impossible),
        "native-ok": native_problem("train", 0, "feasible"),
        "native-psd": native_problem("train", 0, "reference-only", family="N03", original=psd),
        "native-val": native_problem("validation", 0.25, "validation"),
        "native-cal": native_problem("calibration", 2, "calibration"),
        "not-executed-test": native_problem("test", -1, "test"),
    }
    context, sources, frames = build_factored(context, protocol, known)
    scope = {
        "sources": sources,
        "frames": list(frames.values()),
        "fit_source_ids": list(context.fit_source_ids),
        "exclusions": sorted(docs["dataset"]["payload"]["exclusions"]),
        "attribution": "Hand-defined excluded numerical controls",
        "license": "MIT",
    }
    p0_labels = [
        {"frame_id": key, "ref": None, "state": "missing", "reason": "No native work authorized yet"}
        for key in frames
        if key != "native-psd"
    ]
    descriptor = stream.derive_stream_payload(context, protocol, **scope, labels=p0_labels)
    context, p0_ref = put(context, protocol, stream.STREAM, "input-only", descriptor)
    p0 = stream.preflight_stream(
        context, descriptor_id=p0_ref["artifact_id"], expected_descriptor_sha256=p0_ref["sha256"]
    )
    parsed = c.strict_loads(p0.receipt_bytes)
    authority_doc = {
        "format": n.AUTHORITY,
        "mode": "fixture",
        "registration": None,
        "registration_file": None,
        "identities": parsed["identities"],
        "preflight_sha256": p0.sha256,
        "population_sha256": parsed["population_sha256"],
        "roles": list(roles),
        "inventory_sha256": n._hash(n._slots_data(n.planned_slots(p0, roles))),
        "runtime": runtime,
        "settings_hashes": n.settings_identities(runtime),
        "sources": {
            name: n._file_sha(Path(n.__file__).resolve().parents[1] / name) for name in n._WORKER_SOURCE
        },
    }
    path = root / "native-authority.json"
    path.write_bytes(n._encode(authority_doc))
    authority = n.NativeAuthority.load(path, expected_sha256=n._hash(authority_doc))
    plan = n.NativePlan.from_preflight(
        context, p0, expected_preflight_sha256=p0.sha256, roles=roles, authority=authority
    )
    return plan, authority, scope, p0_labels


@pytest.fixture(scope="module")
def supervised(tmp_path_factory):
    root = tmp_path_factory.mktemp("native")
    plan, authority, scope, labels = build_plan(root)
    run = n.supervise_native_run(plan, authority, root / "native-run")
    return root, plan, authority, run, scope, labels


def test_actual_installed_three_oracles_and_signed_daqp_with_independent_fresh_verifier(supervised):
    _, plan, authority, run, _, _ = supervised
    assert (
        n.read_native_run(run.root, expected_manifest_sha256=run.sha256, authority=authority, plan=plan)
        == run
    )
    by_id = {row["input"]["frame"]["artifact_id"]: row for row in run.document["rows"]}
    assert set(by_id) == {"native-bad", "native-ok", "native-val", "native-psd", "native-cal"}
    assert len(run.document["workers"]) == 1
    psd = by_id["native-psd"]
    assert (
        psd["input"]["cold_eligible"] is False and psd["state"] == "reference-only" and psd["label"] is None
    )
    actual_psd = n._decode((run.root / psd["attempt"]["path"]).read_bytes())
    assert actual_psd["cold"] is None
    assert actual_psd["reference"]["observed"]["reference"]["status"] == "oracle-agreed"

    entry = by_id["native-ok"]
    assert entry["state"] == "accepted", entry
    attempt = n._decode((run.root / entry["attempt"]["path"]).read_bytes())
    observed = attempt["reference"]["observed"]["reference"]
    assert observed["status"] == "oracle-agreed"
    assert {key: value["backend_version"] for key, value in observed["references"].items()} == n._VERSIONS
    cold = attempt["cold"]["observed"]
    assert cold["result"]["native_flag"] in (1, 2)
    assert cold["result"]["raw_side_dual"] and len(cold["sides"]) == len(cold["result"]["raw_side_dual"])
    actual = c.strict_loads((run.root / entry["label"]["path"]).read_bytes())["payload"]
    assert actual["native_evidence"]["raw_side_duals"] == cold["result"]["raw_side_dual"]
    assert all(x is None for x in [ref["candidate"]["lifted_x"] for ref in actual["oracle_results"]])
    calibration = by_id["native-cal"]
    assert calibration["state"] == "accepted", calibration
    reply = n._decode((run.root / calibration["attempt"]["path"]).read_bytes())
    observed_cal = reply["reference"]["observed"]["reference"]
    cal_label = c.strict_loads((run.root / calibration["label"]["path"]).read_bytes())["payload"]
    assert observed_cal["objective"] == -0.2499999999999999
    assert {row["metrics"]["f_ref"] for row in cal_label["oracle_results"]} == {-0.25}
    for row in cal_label["oracle_results"]:
        raw = observed_cal["references"][row["backend"].replace("_", "-")]
        assert row["candidate"]["x"] == raw["x"]
        assert row["candidate"]["y"] == raw["y"]

    failure = by_id["native-bad"]
    assert failure["state"] == "oracle-failed"
    bad_attempt = n._decode((run.root / failure["attempt"]["path"]).read_bytes())
    assert bad_attempt["cold"] is None
    assert all(
        not ref["passed"] for ref in bad_attempt["reference"]["observed"]["reference"]["references"].values()
    )
    assert (
        c.strict_loads((run.root / failure["label"]["path"]).read_bytes())["payload"]["native_evidence"]
        is None
    )
    updated = deepcopy(attempt)
    updated["reference"]["telemetry"]["elapsed_seconds"] += 123
    updated["cold"]["telemetry"]["solve_seconds"] += 123
    assert n._result_sha(updated) == n._result_sha(attempt)
    updated["cold"]["observed"]["result"]["raw_side_dual"][0] += 1
    assert n._result_sha(updated) != n._result_sha(attempt)
    assert 0 < max(attempt["peak_rss_bytes"], bad_attempt["peak_rss_bytes"]) < n._PEAK_LIMIT


def test_adversarial_own_rehash_cannot_authorize_fake_success_or_failure(supervised, tmp_path):
    _, plan, authority, run, _, _ = supervised
    root = tmp_path / "forged"
    shutil.copytree(run.root, root)
    manifest = run.document
    for manipulation in ("omit", "failed", "wrong-unit"):
        forged = deepcopy(manifest)
        if manipulation == "omit":
            forged["rows"].pop()
        elif manipulation == "failed":
            forged["rows"][0]["state"] = "cold-native-failure"
            forged["rows"][0]["reason"] = "invented failure"
        else:
            forged["rows"][0]["input"]["units_sha256"] = "0" * 64
        forged["scope_sha256"] = n._scope(forged)
        (root / "native-run.json").write_bytes(n._encode(forged))
        with pytest.raises(ValueError, match="stored byte digest differs"):
            n.read_native_run(root, expected_manifest_sha256=run.sha256, authority=authority, plan=plan)
    (root / "native-run.json").write_bytes(run.raw)
    entry = next(row for row in manifest["rows"] if row["state"] == "accepted")
    label = root / entry["label"]["path"]
    original = label.read_bytes()
    edited = c.strict_loads(original)
    edited["payload"]["cold_native_flag"] = 2 if edited["payload"]["cold_native_flag"] == 1 else 1
    edited["content_sha256"] = c.content_digest(edited)
    modified = c.canonical_bytes(edited)
    assert len(modified) == len(original) and modified != original
    label.write_bytes(modified)
    with pytest.raises(ValueError, match="stored byte digest differs"):
        n.read_native_run(root, expected_manifest_sha256=run.sha256, authority=authority, plan=plan)


def test_adversarial_unregistered_production_and_wrong_runtime_refuse_before_work(
    supervised, tmp_path, monkeypatch
):
    _, plan, authority, _, _, _ = supervised

    def not_spawned(*_args, **_kw):
        pytest.fail("untrusted request launched an SDK worker")

    monkeypatch.setattr(n, "_start_worker", not_spawned)
    scientific = authority.document
    scientific["mode"] = "scientific"
    raw = n._encode(scientific)
    with pytest.raises(ValueError, match="lacks independent I1"):
        n.supervise_native_run(plan, n.NativeAuthority(raw, n._sha(raw)), tmp_path / "forbidden")
    assert not (tmp_path / "forbidden").exists()
    forged = authority.document
    forged["runtime"]["python_sha256"] = "0" * 64
    raw = n._encode(forged)
    with pytest.raises(ValueError, match="runtime python identity"):
        n.supervise_native_run(plan, n.NativeAuthority(raw, n._sha(raw)), tmp_path / "wrong-runtime")
    assert not (tmp_path / "wrong-runtime").exists()
    with pytest.raises(ValueError, match="cannot include test"):
        n.planned_slots(plan.preflight, ("test",))
    assert not (tmp_path / "test").exists()


def test_adversarial_p0_manifest_projection_p1_role_bytes_without_global_opens(
    supervised, tmp_path, monkeypatch
):
    _, plan, authority, run, scope, pending = supervised
    context = plan.context
    manifest = run.document
    protocol = c.strict_loads(plan.preflight.receipt_bytes)["protocol_ref"]
    labels = deepcopy(pending)
    for row in manifest["rows"]:
        if not row["input"]["cold_eligible"]:
            continue
        frame_id = row["input"]["frame"]["artifact_id"]
        slot = next(value for value in labels if value["frame_id"] == frame_id)
        state, reason = n._label_disposition(row)
        if state == "available":
            state = "provider"
        ref = None
        if row["label"] is not None:
            raw = (run.root / row["label"]["path"]).read_bytes()
            doc = c.strict_loads(raw)
            name = doc["artifact_id"] + ".json"
            path = context.root / name
            path.write_bytes(raw)
            product = stream.read_stream_artifact(
                path,
                context,
                expected_sha256=row["label"]["sha256"],
                expected_population_sha256=manifest["population_sha256"],
            )
            ref = dict(
                kind=stream.LABELS, artifact_id=product.artifact_id, path=name, sha256=product.raw_sha256
            )
            context = replace(context, catalog={**context.catalog, ref["artifact_id"]: ref})
        slot.update(state=state, reason=reason, ref=ref)
    descriptor = stream.derive_stream_payload(context, protocol, **scope, labels=labels)
    context, ref = put(context, protocol, stream.STREAM, "output-with-native-labels", descriptor)
    p1 = stream.preflight_stream(
        context, descriptor_id=ref["artifact_id"], expected_descriptor_sha256=ref["sha256"]
    )

    projection_paths = {role: tmp_path / (role + ".json") for role in plan.roles}
    projections = {role: run.project_role(role, path) for role, path in projection_paths.items()}
    trusts = n.bind_labeled_preflight(
        plan,
        run,
        p1,
        expected_manifest_sha256=run.sha256,
        expected_labeled_preflight_sha256=p1.sha256,
        projection_hashes=projections,
    )
    with pytest.raises(ValueError, match="cannot include test"):
        run.project_role("test", tmp_path / "test-role.json")
    assert not (tmp_path / "test-role.json").exists()
    forged = c.strict_loads(p1.receipt_bytes)
    forged["logical"][0]["logical_sha256"] = "f" * 64
    impostor = replace(p1, receipt_bytes=c.canonical_bytes(forged))
    with pytest.raises(ValueError, match="P0/P1 nonlabel identity"):
        n.bind_labeled_preflight(
            plan,
            run,
            impostor,
            expected_manifest_sha256=run.sha256,
            expected_labeled_preflight_sha256=impostor.sha256,
            projection_hashes=projections,
        )
    with pytest.raises(ValueError, match="refused"):
        n.NativeRoleProof.load(projection_paths["train"], trusts[0])

    phase_roots = {role: tmp_path / role for role in plan.roles}
    phase_hashes = {
        role: stream.materialize_stream_phase(p1, path, role=role, expected_preflight_sha256=p1.sha256)
        for role, path in phase_roots.items()
    }
    all_reads = Counter()
    real = Path.open

    def probe(path, *args, **kwargs):
        if kwargs.get("mode", args[0] if args else "r") == "rb":
            all_reads[path] += 1
        return real(path, *args, **kwargs)

    inaccessible_sources = context.root.with_name("temporary-unavailable-global")
    inaccessible_run = run.root.with_name("temporary-unavailable-run")
    context.root.rename(inaccessible_sources)
    run.root.rename(inaccessible_run)
    try:
        monkeypatch.setattr(Path, "open", probe)
        for trust in trusts:
            role = trust.role
            all_reads.clear()
            proof = n.NativeRoleProof.load(projection_paths[role], trust, allow_fixture=True)
            reader = stream.StreamingPhaseReader(
                phase_roots[role],
                role=role,
                expected_manifest_sha256=phase_hashes[role],
                expected_preflight_sha256=p1.sha256,
                allow_fixture=True,
            )
            rows = [row for row in manifest["rows"] if row["input"]["role"] == role]
            for row in rows:
                result = proof.verify(reader, row["input"]["frame"]["artifact_id"])
                assert (result["state"], result["reason"]) == (row["state"], row["reason"])
            schema = c.SCHEMAS / "softqp-learning-native-run.schema.json"
            assert all_reads.pop(schema) == 1
            assert (
                sum(all_reads.values()) == 2 * len(rows) + sum(row["label"] is not None for row in rows) + 2
            )
            assert all(
                path.parent == phase_roots[role] or path == projection_paths[role] for path in all_reads
            )
            with pytest.raises(ValueError, match="absent from trusted role"):
                proof.verify(reader, "not-executed-test")
    finally:
        inaccessible_sources.rename(context.root)
        inaccessible_run.rename(run.root)


def test_adversarial_deadline_stops_owned_worker_and_keeps_unrelated_process(tmp_path):
    launcher = Path(sys.executable)
    command = [str(launcher), "-I", "-B", "-c", "import time; time.sleep(30)"]
    neighbor = subprocess.Popen(command)
    worker = None
    try:
        worker = n._OwnedWorker(tmp_path / "owned", command, launcher, nonce="0" * 32)
        owned_process = worker.process
        pid, neighbor_pid = owned_process.pid, neighbor.pid
        assert pid != neighbor_pid and owned_process.poll() is None and neighbor.poll() is None
        with pytest.raises(TimeoutError, match="deadline"):
            worker.wait_file(worker.root / "missing.json", 0.1)
        worker.close()
        worker = None
        assert owned_process.poll() is not None and neighbor.poll() is None
    finally:
        if worker is not None:
            worker.close()
        if neighbor.poll() is None:
            neighbor.terminate()
        neighbor.wait(timeout=5)


def test_adversarial_native_runtime_profile_worker_code_and_custody_tamper(supervised, tmp_path):
    _, plan, authority, run, _, _ = supervised
    for mutate, match in (
        (lambda d: d["runtime"].update(profile_sha256="0" * 64), "profile or checker differs"),
        (lambda d: d["sources"].update({n._WORKER_SOURCE[0]: "0" * 64}), "native product source differs"),
    ):
        document = authority.document
        mutate(document)
        path = tmp_path / ("authority-" + n._hash(document)[:12] + ".json")
        path.write_bytes(n._encode(document))
        with pytest.raises(ValueError, match=match):
            n.NativeAuthority.load(path, expected_sha256=n._hash(document))
    root = tmp_path / "resealed"
    shutil.copytree(run.root, root)
    first = run.document["rows"][0]
    attempt_path = root / first["attempt"]["path"]
    edited = n._decode(attempt_path.read_bytes())
    edited["state"] = "accepted"
    edited["result_sha256"] = n._result_sha(edited)
    attempt_path.write_bytes(n._encode(edited))
    with pytest.raises(ValueError, match="stored byte digest differs"):
        n.read_native_run(root, expected_manifest_sha256=run.sha256, authority=authority, plan=plan)


def test_adversarial_owned_process_exit_preserves_attested_missing_outcome(tmp_path):
    executor = Path(sys.executable)
    command = [str(executor), "-I", "-B", "-c", "raise SystemExit(7)"]
    worker = n._OwnedWorker(tmp_path / "exit", command, executor, nonce="1" * 32)
    process = worker.process
    try:
        reference, cold, event = n._run_input(
            worker,
            {"original": {}},
            {"frame": {"artifact_id": "excluded-fixture"}, "cold_eligible": True},
            None,
        )
        assert cold is None and event == "reference"
        assert reference["status"] == "worker-exit" and reference["observed"] is None
        assert reference["telemetry"]["diagnostic"].endswith(": 7")
        assert process.poll() == 7
    finally:
        worker.close()
