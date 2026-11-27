"""Excluded held-out authority, sealed role data, and owned 49 native replay."""

from dataclasses import asdict, replace
from pathlib import Path
from copy import deepcopy
import json
import subprocess

import pytest

from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import heldout_inputs as h
from pipeline.learned_comparison import native_labels as n
from pipeline.learned_comparison import stream_inputs as s
from test_learned_contracts import PROVIDER
from test_native_labels import native_problem
from test_native_runtime import _context_fixture, load_fixture_context
from runtime_config import native49
from test_stream_inputs import build_factored, put


def fixture_context(config, metadata, profile):
    context, actual = load_fixture_context(config)
    assert actual == metadata and context.allow_fixture
    assert len(profile) == 64
    return context


def _make_inputs(root, profile_sha, profile):
    from pipeline.learned_comparison import evaluation_models as models

    context, docs, refs = PROVIDER["build"](root / "source")
    import json

    admitted = json.loads((profile / "provenance.json").read_bytes())
    settings = n.settings_identities(
        {
            "profile_sha256": profile_sha,
            "defaults_sha256": admitted["defaults_sha256"],
            "wheel_sha256": admitted["source_artifacts"]["checksums"][
                "softqp-0.3.0-cp312-cp312-win_amd64.whl"
            ],
            "engine_source": admitted["canonical_engine_source"],
        }
    )
    context = replace(context, settings_hashes={**context.settings_hashes, **settings})
    protocol = refs["protocol"]
    original = deepcopy(docs["problem-train"]["payload"]["original"])
    original.update(
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
    original["penalty"] = {key: ([False] * 3 if key == "soft" else [0] * 3) for key in original["penalty"]}
    original["units"].update(
        D_x=[1, 1], D_r=[1, 1, 1], variable=["dimensionless"] * 2, row=["dimensionless"] * 3
    )
    cases = {
        "control-train": native_problem("train", 0, "train"),
        "control-validation": native_problem("validation", 0.25, "validation"),
        "control-calibration": native_problem("calibration", 0.125, "calibration"),
        "control-q2": native_problem("test", 2, "heldout-q2"),
        "control-infeasible": native_problem(
            "test", 0, "heldout-infeasible", family="N02", original=original
        ),
    }
    context, sources, frames = build_factored(context, protocol, cases)
    labels = [
        {"frame_id": key, "ref": None, "state": "missing", "reason": "Excluded fixture"} for key in frames
    ]
    descriptor = s.derive_stream_payload(
        context,
        protocol,
        sources=sources,
        frames=list(frames.values()),
        exclusions=docs["dataset"]["payload"]["exclusions"],
        fit_source_ids=list(context.fit_source_ids),
        labels=labels,
        attribution="Explicitly excluded held-out numerical controls",
        license="MIT",
    )
    context, p0_ref = put(context, protocol, s.STREAM, "heldout-p0", descriptor)
    context, p1_ref = put(context, protocol, s.STREAM, "heldout-p1", descriptor)
    p0, p1 = (
        s.preflight_stream(
            context, descriptor_id=ref["artifact_id"], expected_descriptor_sha256=ref["sha256"]
        )
        for ref in (p0_ref, p1_ref)
    )
    parsed = c.strict_loads(p0.receipt_bytes)
    source_by_id = {ref["artifact_id"]: ref for ref in sources}
    rows = []
    for key in ("control-q2", "control-infeasible"):
        case = cases[key]
        frame = c.strict_loads((context.root / frames[key]["path"]).read_bytes())["payload"]
        source = case["source"]
        rows.append(
            {
                "role": "test",
                "family": source["family"],
                "regime": source["regime"],
                "unit_index": source["unit_index"],
                "frame_index": source["frame"],
                "frame_count": source["frame_count"],
                "source_id": source["source_id"],
                "parent_id": source["parent_id"],
                "frame": frames[key],
                "source": source_by_id[frame["source_ref"]["artifact_id"]],
                "original_sha256": case["original_sha256"],
                "transform_sha256": case["transform_sha256"],
                "units_sha256": n._hash(case["original"]["units"]),
                "cold_eligible": True,
            }
        )
    stored = root / "meta"
    stored.mkdir()
    p0_file, p1_file = (
        n._persist(stored / name, c.strict_loads(doc.receipt_bytes))
        for name, doc in (("p0.json", p0), ("p1.json", p1))
    )
    index = n._persist(stored / "index.json", {"schema": h.INDEX, "rows": rows})
    detached = n._persist(stored / "context.json", _context_fixture(context))
    roster = []
    population = parsed["population_sha256"]
    for method, seed in models._KEYS:
        job = stored / f"{method}-{seed}"
        job.mkdir()
        evidence = {
            "schema": models.ABSENCE,
            "method": method,
            "seed": seed,
            "fixture_only": True,
            "population_sha256": population,
            "preflight_sha256": p1.sha256,
            "protocol_sha256": protocol["sha256"],
            "state": "missing",
            "reason": "This excluded native control does not execute model fitting",
            "stage": "training",
        }
        evidence_ref = n._persist(job / "evidence.json", evidence)
        failure = n._persist(
            job / "failure.json",
            {**evidence, "schema": models.FAILURE, "evidence_sha256": evidence_ref["sha256"]},
        )
        roster.append(
            models.FailedModelTrust(
                job, failure["sha256"], method, seed, protocol["sha256"], population, p1.sha256
            )
        )
    roster_root = stored / "roster"
    roster_root.mkdir()
    roster_sha = models.publish_roster(
        roster_root, tuple(roster), authority=context.authority, allow_fixture=True
    )
    req = {
        "schema": h.REQUEST,
        "operation": "evaluate-heldout-fixture",
        "stage": "test-native",
        "roster_sha256": roster_sha,
        "p0_sha256": p0.sha256,
        "p1_sha256": p1.sha256,
        "inventory_sha256": index["sha256"],
    }
    req_ref = n._persist(stored / "request.json", req)
    scope = {k: req[k] for k in ("roster_sha256", "p0_sha256", "p1_sha256", "inventory_sha256")}
    scope.update(
        profile_sha256=profile_sha,
        identities=parsed["identities"],
        artifact_roots=[str(root)],
        **{k: str(root / k) for k in ("test_root", "native_root", "proof_root", "frontier_root")},
    )
    inputs = {
        "admission": {"root": str(stored), "context": detached},
        "metadata": str(stored),
        "p0": p0_file,
        "p1": p1_file,
        "index": index,
        "roster_root": str(roster_root),
        "roster": [
            {"state": "missing", "trust": {**asdict(entry), "root": str(entry.root)}} for entry in roster
        ],
    }
    policy = {
        "schema": h.POLICY,
        "operation": req["operation"],
        "stage": req["stage"],
        "scope": scope,
        "request_sha256": req_ref["sha256"],
        "expected": None,
        "inputs": inputs,
    }
    return stored, req_ref, n._persist(stored / "policy.json", policy), context


def test_adversarial_fabricated_handle_and_reader_refuse_before_io(monkeypatch):
    def opened(*args, **kwargs):
        pytest.fail("held-out data opened before admission")

    monkeypatch.setattr(Path, "open", opened)
    with pytest.raises(c.ContractError, match="unissued"):
        h.TestInputReader.open(h.HeldoutAdmission(), Path("D:/missing"), expected_projection_sha256="0" * 64)
    with pytest.raises(c.ContractError, match="unissued"):
        h.TestNativeProof().read_outcome("q2")
    with pytest.raises(c.ContractError, match="unissued"):
        h.TestInputReader().read_sealed_frame_pair("q2")
    with pytest.raises(c.ContractError, match="unsupported phase role"):
        s.StreamingPhaseReader(
            Path("D:/missing"),
            role="test",
            expected_manifest_sha256="0" * 64,
            expected_preflight_sha256="0" * 64,
        )
    with pytest.raises(ValueError, match="cannot include test"):
        n._roles(["test"])


def test_exact_registered_test_domain(tmp_path):
    context, _, _ = PROVIDER["build"](tmp_path / "source")
    refs, cold = h._domain(context)
    assert len(refs) == 2208 and len(cold) == 2072
    assert len({key[:3] for key in refs}) == 720 and len({key[:3] for key in cold}) == 584


def test_actual_heldout_native_after_six_excluded_roster_dispositions(tmp_path):
    config = native49()
    snapshot, profile_sha = config.snapshot, config.profile_sha256
    profile = snapshot / "profile"
    assert n._file_sha(profile / "provenance.json") == profile_sha
    metadata, req, policy, context = _make_inputs(tmp_path, profile_sha, profile)
    run = tmp_path / "supervisor"
    command = [
        str(config.python),
        "-I",
        "-S",
        "-B",
        str(profile / "verify.py"),
        "--heldout-fixture",
        "--python",
        str(config.python),
        "--base-python",
        str(config.base_python),
        "--source",
        str(snapshot / "source"),
        "--profile",
        str(profile),
        "--expected-profile-sha256",
        profile_sha,
        "--tools",
        str(config.tools),
        "--run",
        str(run),
        "--request",
        str(metadata / req["path"]),
        "--expected-request-sha256",
        req["sha256"],
        "--policy",
        str(metadata / policy["path"]),
        "--expected-policy-sha256",
        policy["sha256"],
    ]
    observed = subprocess.run(command, capture_output=True, timeout=1500)
    (tmp_path / "supervisor-stderr.log").write_bytes(observed.stderr)
    assert observed.returncode == 0, (
        observed.stderr,
        (run / "stderr.log").read_bytes() if run.exists() else b"",
    )
    receipt = json.loads((run / "receipt.json").read_bytes())
    assert receipt["status"] == "heldout-fixture-observed" and receipt["fixture_only"]
    assert receipt["cleanup"] == "owned-process-tree-closed" and receipt["i1_issued"] is False
    manifest = h._json((tmp_path / "native_root" / "native-run.json").read_bytes())
    assert manifest["fixture_only"] and manifest["role"] == "test" and len(manifest["workers"]) == 1
    actual = {entry["frame_id"]: entry for entry in manifest["rows"]}
    assert actual["control-infeasible"]["state"] == "oracle-failed"
    assert actual["control-q2"]["state"] == "accepted"
    observation = h._json((tmp_path / "native_root" / actual["control-q2"]["attempt"]["path"]).read_bytes())
    assert {row["metrics"]["f_ref"] for row in observation["oracle_rows"]} == {-0.25}
    assert observation["label"]["native_evidence"]["raw_side_duals"]
    assert observation["label"]["fit_access"] == []
    assert (tmp_path / "proof_root" / "proof.json").is_file()
    native_stage = json.loads((run / "heldout-inputs.json").read_bytes())["observed"]
    original_request = h._json((metadata / req["path"]).read_bytes())
    original_policy = h._json((metadata / policy["path"]).read_bytes())
    req_candidate = n._persist(
        metadata / "candidate-request.json", {**original_request, "stage": "candidate"}
    )
    policy_candidate = n._persist(
        metadata / "candidate-policy.json",
        {
            **original_policy,
            "stage": "candidate",
            "request_sha256": req_candidate["sha256"],
            "expected": {k: native_stage[k] for k in ("test_sha256", "native_sha256", "proof_sha256")},
        },
    )
    run_candidate = tmp_path / "candidate-supervisor"
    command_candidate = list(command)
    for name, value in {
        "--run": str(run_candidate),
        "--request": str(metadata / req_candidate["path"]),
        "--expected-request-sha256": req_candidate["sha256"],
        "--policy": str(metadata / policy_candidate["path"]),
        "--expected-policy-sha256": policy_candidate["sha256"],
    }.items():
        command_candidate[command_candidate.index(name) + 1] = value
    global_unavailable = context.root.with_name("global-payloads-unavailable")
    native_path = tmp_path / "native_root"
    native_unavailable = native_path.with_name("native-run-unavailable")
    context.root.rename(global_unavailable)
    context.root.mkdir()
    native_path.rename(native_unavailable)
    try:
        result = subprocess.run(command_candidate, capture_output=True, timeout=1500)
        (tmp_path / "candidate-stderr.log").write_bytes(result.stderr)
        assert result.returncode == 0, (result.stderr, (run_candidate / "stderr.log").read_bytes())
        audit = json.loads((run_candidate / "heldout-inputs.json").read_bytes())["observed"]
        assert audit["schema"] == "softqp.heldout-candidate-audit/1" and audit["fixture_only"]
        assert audit["test_pair_opens"] == 2 and audit["native_attempt_opens"] == 1
    finally:
        context.root.rmdir()
        global_unavailable.rename(context.root)
        native_unavailable.rename(native_path)


def observe_candidate_fixture(raw, custody):
    """Fixed excluded access audit executed under the actual guardian."""
    from unittest.mock import patch

    _, provisional = h._launch_arguments(raw, custody)

    def refuse_data(*args, **kwargs):
        raise AssertionError("candidate opened a payload before binding independent N/J")

    with patch.object(Path, "open", refuse_data):
        try:
            h.TestInputReader.open(provisional, Path("D:/inadmissible"), expected_projection_sha256="0" * 64)
        except c.ContractError as error:
            assert "stage" in str(error)
        else:
            raise AssertionError("candidate bypassed test-native proof")
    proof = h.admit_candidate_inputs(raw, custody)
    reader = proof.reader
    opened = []
    original = Path.open

    def tracking(path, *args, **kwargs):
        opened.append(path)
        return original(path, *args, **kwargs)

    with patch.object(Path, "open", tracking):
        pair = reader.read_sealed_frame_pair("control-q2")
        evidence = proof.read_outcome("control-q2")
    root = h._reader(reader).root
    native = h._PROOFS[proof].root
    direct = [path for path in opened if not path.is_relative_to(c.SCHEMAS)]
    assert len([path for path in direct if path.parent == root]) == 2
    assert len([path for path in direct if path.parent == native]) == 1
    assert all(path.parent in (root, native) for path in direct)
    assert pair["frame_ref"] == evidence["identity"]["frame"] and evidence["state"] == "accepted"
    return {
        "schema": "softqp.heldout-candidate-audit/1",
        "fixture_only": True,
        "test_pair_opens": 2,
        "native_attempt_opens": 1,
        "frame_sha256": c.digest(pair["frame_raw"]),
        "test_sha256": reader.manifest_sha256,
    }


def test_adversarial_prefit_operation_and_wrong_live_profile_refuse(tmp_path):
    import runpy

    helper = runpy.run_path(
        str(
            Path(h.__file__).resolve().parents[3]
            / "environments/method-extension-scientific/heldout_runtime.py"
        )
    )
    pins = {key: "a" * 64 for key in ("p0_sha256", "p1_sha256", "roster_sha256", "inventory_sha256")}
    request = {"schema": h.REQUEST, "operation": "evaluate-heldout", "stage": "test-native", **pins}

    def launch():
        raw = helper["encode"](request)
        policy = {
            "schema": h.POLICY,
            "operation": request["operation"],
            "stage": request["stage"],
            "expected": None,
            "request_sha256": c.digest(raw),
            "scope": {"profile_sha256": "b" * 64, **pins},
            "inputs": {},
        }
        return raw, helper["encode"](policy)

    helper["scope"](launch(), "b" * 64, False)
    with pytest.raises(ValueError, match="seal mismatch"):
        helper["scope"](launch(), "c" * 64, False)
    request["operation"] = "native-label"
    with pytest.raises(ValueError, match="operation differs"):
        helper["scope"](launch(), "b" * 64, False)
    request["operation"] = "evaluate-heldout"
    request["stage"] = "candidate"
    with pytest.raises(ValueError, match="operation differs"):
        helper["scope"](launch(), "b" * 64, False)


def test_adversarial_native_raw_signed_zero_is_preserved_without_normalizing():
    import math

    wire = h._observation_wire({"native": [-0.0]})
    assert "-0.0" in wire["json"]
    assert math.copysign(1, h._observation(wire)["native"][0]) == -1
    with pytest.raises(c.ContractError, match="raw bytes"):
        h._observation({**wire, "json": wire["json"].replace("-0.0", "0.0")})
