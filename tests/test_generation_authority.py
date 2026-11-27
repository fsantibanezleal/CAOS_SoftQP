"""Genuine I1 parser controls using only independently pinned fixture trust."""

from copy import deepcopy
from dataclasses import replace
from importlib import metadata, util
from pathlib import Path
import platform
import subprocess
import sys
from types import SimpleNamespace

import pytest

from pipeline.learned_comparison import authority as a
from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import generator as g
from test_learned_contracts import PROVIDER


def _hash(value):
    return c.digest(c.canonical_bytes(value))


def _approval(tmp_path, *, reviewer="independent-fixture-reviewer", implementer="fixture-author",
              decision="I1-accepted", subject_change=None, review_change=None, runtime_change=None):
    source_root = Path(__file__).resolve().parents[1]
    root = tmp_path / "submitted"
    gov = tmp_path / "governance"
    gov.mkdir()
    context, docs, _ = PROVIDER["build"](root)
    commit = subprocess.check_output(["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True).strip()
    filenames = (
        "data-pipeline/pipeline/learned_comparison/authority.py",
        "data-pipeline/pipeline/learned_comparison/contracts.py",
        "data-pipeline/pipeline/learned_comparison/stream_inputs.py",
        "data-pipeline/pipeline/learned_comparison/generator.py",
    )
    source_bytes = (source_root / filenames[-1]).read_bytes()
    lock = {"schema": "softqp.r4.source-lock/1", "product_commit": commit, "engine_commit": commit,
            "files": {name: c.digest((source_root / name).read_bytes()) for name in filenames}}
    payload = deepcopy(docs["protocol"]["payload"])
    payload.update(status="registered", generator_sha256=c.digest(source_bytes))
    del payload["registration_sha256"]

    def put(name, data):
        raw = data if isinstance(data, bytes) else c.canonical_bytes(data)
        path = name + ".json"
        (gov / path).write_bytes(raw)
        return {"path": path, "sha256": c.digest(raw)}

    meta = context.authority.root
    matrix = put("semantic_matrix", (meta / "semantic-matrix.json").read_bytes())
    seed_inventory = put("seed_inventory", (meta / "expected-keysets/inventory.json").read_bytes())
    compatibility = put("compatibility", {"decision": "accepted", "semantic_matrix_sha256": matrix["sha256"]})
    math_gates = put("math_gates", {"decision": "accepted", "generator_sha256": c.digest(source_bytes)})
    runtime = {"schema": "softqp.r4.runtime/1", "decision": "accepted",
               "dependency_lock_sha256": context.dependency_lock_sha256, "worker_count": 1,
               "python_version": platform.python_version(), "python_sha256": c.digest(Path(sys.executable).read_bytes()),
               "packages": {"numpy": {"version": metadata.version("numpy"), "module": "numpy",
                                     "sha256": c.digest(Path(util.find_spec("numpy").origin).read_bytes())}},
               "profile": None, "profile_sha256": None, "verifier_sha256": None}
    if runtime_change:
        runtime.update(runtime_change)
    evidence = {"runtime": put("runtime", runtime), "compatibility": compatibility, "math_gates": math_gates,
                "semantic_matrix": matrix, "seed_inventory": seed_inventory}
    subject = {
        "design_manifest_sha256": c.DESIGN_MANIFEST_SHA256, "protocol_core_sha256": _hash(payload),
        "product_commit": commit, "engine_commit": commit, "source_lock_sha256": _hash(lock),
        "generator_sha256": c.digest(source_bytes), "dependency_lock_sha256": context.dependency_lock_sha256,
        "operations": ["generate-source", "native-label"], **{k + "_sha256": v["sha256"] for k, v in evidence.items()},
    }
    if subject_change:
        subject.update(subject_change)
    review = {"schema": "softqp.r4.review/1", "reviewer": reviewer, "implementer": implementer,
              "decision": decision, "subject_sha256": _hash(subject), "signed_at": "2026-11-05T00:00:00Z"}
    if review_change:
        review.update(review_change)
    review_ref = put("review", review)
    registration = put("registration", {"schema": "softqp.r4.registration/1",
                                         "subject": subject, "review_sha256": review_ref["sha256"]})
    payload["registration_sha256"] = registration["sha256"]
    context = replace(context, catalog={}, protocol_sha256=_hash(payload), registration_sha256=registration["sha256"],
                      generator_source_bytes=source_bytes, generator_sha256=c.digest(source_bytes),
                      source_lock_bytes=c.canonical_bytes(lock), source_lock_sha256=_hash(lock))
    document = PROVIDER["envelope"]("learning-protocol", "i1-protocol-fixture", payload, context)
    protocol = c.write_artifact(document, "i1-protocol-fixture.json", context)
    protocol_ref = {"artifact_id": protocol.artifact_id, "kind": "learning-protocol",
                    "path": "i1-protocol-fixture.json", "sha256": protocol.raw_sha256}
    context = replace(context, catalog={protocol.artifact_id: protocol_ref})
    index = put("approved-index", {"schema": "softqp.r4.approved-index/1", "lane": "contract-fixture",
                                   "reviewer": reviewer, "registration": registration, "review": review_ref,
                                   "protocol_sha256": context.protocol_sha256, "protocol_ref": protocol_ref,
                                   "evidence": evidence})
    trust = a.ApprovalTrust(gov, index["path"], index["sha256"], reviewer, source_root, source_root,
                            fixture_only=True)
    return trust, context, protocol_ref


def test_actual_governed_fixture_receipts_issue_only_fixture_authority(tmp_path, monkeypatch):
    trust, context, protocol = _approval(tmp_path)
    authority = a.load_i1_authority(trust=trust, context=context, protocol_ref=protocol)
    assert authority.registration_sha256 == context.registration_sha256
    assert authority.source_lock_sha256 == context.source_lock_sha256
    assert authority.protocol_sha256 == context.protocol_sha256
    assert authority.design_manifest_sha256 == c.DESIGN_MANIFEST_SHA256
    assert not authority.allows("generate-source") and not authority.allows("native-label")

    def refused(*args, **kwargs):
        pytest.fail("fixture or forged I1 reached scientific draw/write")

    monkeypatch.setattr(g, "_rng", refused)
    monkeypatch.setattr(g.stream, "write_stream_artifact", refused)
    slot = g.SourceSlot("N01", 0, "train", 0)
    for invalid in (authority, a.I1Authority(), SimpleNamespace(allows=lambda _: True), None):
        with pytest.raises(g.RegistrationUnavailable, match="independently authenticated I1"):
            g.generate_registered_unit(slot, context=context, protocol_ref=protocol, authority=invalid)


@pytest.mark.parametrize("mutation,error", [
    ({"decision": "pending"}, "does not independently sign"),
    ({"implementer": "independent-fixture-reviewer"}, "does not independently sign"),
    ({"review_change": {"subject_sha256": "0"*64}}, "does not independently sign"),
    ({"runtime_change": {"python_version": "0.0.0"}}, "active Python differs"),
    ({"runtime_change": {"packages": {"numpy": {"version": "2.5.4", "module": "json", "sha256": "2"*64}}}},
     "distribution-to-module identity differs"),
    ({"subject_change": {"protocol_core_sha256": "1"*64}}, "registration back-reference differs"),
    ({"subject_change": {"operations": ["train", "test"]}}, "operation scope"),
    ({"subject_change": {"product_commit": "1"*40}}, "source commits differ"),
])
def test_resigned_inconsistent_fixture_records_still_refuse(tmp_path, mutation, error):
    trust, context, protocol = _approval(tmp_path, **mutation)
    with pytest.raises(c.ContractError, match=error):
        a.load_i1_authority(trust=trust, context=context, protocol_ref=protocol)


def test_adversarial_independent_index_identity_and_actual_review_bytes(tmp_path):
    trust, context, protocol = _approval(tmp_path)
    with pytest.raises(c.ContractError, match="I1 evidence byte identity mismatch"):
        a.load_i1_authority(trust=replace(trust, expected_index_sha256="0"*64), context=context,
                            protocol_ref=protocol)
    with pytest.raises(c.ContractError, match="trust lane"):
        a.load_i1_authority(trust=replace(trust, fixture_only=False), context=context, protocol_ref=protocol)
    review = trust.governance_root / "review.json"
    content = c.strict_loads(review.read_bytes())
    review.write_bytes(c.canonical_bytes({**content, "reviewer": "self-appointed"}))
    with pytest.raises(c.ContractError, match="I1 evidence byte identity mismatch"):
        a.load_i1_authority(trust=trust, context=context, protocol_ref=protocol)


def test_run_submitted_approval_root_refuses(tmp_path):
    trust, context, protocol = _approval(tmp_path)
    with pytest.raises(c.ContractError, match="governance cannot be supplied by the run"):
        a.load_i1_authority(trust=replace(trust, governance_root=context.root),
                            context=context, protocol_ref=protocol)


def test_same_protocol_payload_cannot_rebind_file_reference(tmp_path):
    trust, context, protocol = _approval(tmp_path)
    forged = {**protocol, "path": "alternate-protocol.json"}
    (context.root / forged["path"]).write_bytes((context.root / protocol["path"]).read_bytes())
    ctx = replace(context, catalog={forged["artifact_id"]: forged})
    with pytest.raises(c.ContractError, match="actual protocol file differs"):
        a.load_i1_authority(trust=trust, context=ctx, protocol_ref=forged)


def test_exact_runtime_checker_bootstrap_has_no_site_initialization():
    compile(a._CHECK_BOOTSTRAP, "<reviewed-runtime-bootstrap>", "exec")
    assert "site.addsitedir" not in a._CHECK_BOOTSTRAP and "sys.path.append" in a._CHECK_BOOTSTRAP


def _source_request():
    return {"schema": "softqp.r4.generate-source-request/1",
            "slot": {"family": "N12", "regime": 0, "split": "train", "unit": 0}}


def test_registered_dispatch_refuses_standalone_before_reading_governance_or_drawing(monkeypatch):
    monkeypatch.delitem(sys.modules, "softqp_runtime_custody", raising=False)

    def forbidden(*args, **kwargs):
        pytest.fail("standalone call reached governance or RNG")

    monkeypatch.setattr(g, "_dispatch_context", forbidden)
    monkeypatch.setattr(g, "_rng", forbidden)
    with pytest.raises(c.ContractError, match="verified owned worker"):
        g.dispatch_registered_request(c.canonical_bytes(_source_request()), object())


def test_dispatch_does_not_take_a_policy_or_different_slot_from_the_request(monkeypatch, tmp_path):
    request = _source_request()
    policy = {key: None for key in ("approval", "product_root", "engine_root", "design_root",
                                  "output_root", "locks", "protocol")}
    policy.update(schema="softqp.r4.generate-source-policy/1", slot={**request["slot"], "unit": 1})
    monkeypatch.setattr(g, "generator_worker_policy", lambda *_: (policy, "1"*64, "2"*64))

    def forbidden(*args, **kwargs):
        pytest.fail("invalid slot or request reached governance or RNG")

    monkeypatch.setattr(g, "_dispatch_context", forbidden)
    monkeypatch.setattr(g, "_rng", forbidden)
    with pytest.raises(c.ContractError, match="request slot was not independently approved"):
        g.dispatch_registered_request(c.canonical_bytes(request), object())
    injected = {**request, "output_root": str(tmp_path / "forged")}
    with pytest.raises(c.ContractError, match="invalid registered generator request"):
        g.dispatch_registered_request(c.canonical_bytes(injected), object())


def _source_scope():
    request = _source_request()
    policy = c.canonical_bytes({"schema": "softqp.r4.generate-source-policy/1", "slot": request["slot"]})
    return a._GeneratorWorkerScope(object(), _hash(request), c.digest(policy), ("N12", 0, "train", 0)), policy


def test_owned_worker_scope_cannot_be_reused_for_new_slot_or_stale_policy(monkeypatch):
    scope, policy = _source_scope()
    monkeypatch.setattr(a, "_worker_policy", lambda *_, **__: policy)
    a._require_generator_scope(scope, scope.slot)
    with pytest.raises(c.ContractError, match="slot differs"):
        a._require_generator_scope(scope, ("N12", 0, "train", 1))
    monkeypatch.setattr(a, "_worker_policy", lambda *_, **__: b"changed")
    with pytest.raises(c.ContractError, match="launch policy changed"):
        a._require_generator_scope(scope, scope.slot)
    forged = replace(scope, slot=("N12", 0, "train", 1))
    with pytest.raises(c.ContractError, match="request digest differs"):
        a._require_generator_scope(forged, forged.slot)


def test_owned_worker_scope_passes_independently_approved_profile_to_guard(monkeypatch):
    scope, policy = _source_scope()
    expected = "2"*64

    def guarded(custody, request, *, profile_sha256):
        assert (custody, request) == (scope.custody, scope.request_sha256)
        c.ensure(profile_sha256 == expected, "active profile differs")
        return policy

    monkeypatch.setattr(a, "_worker_policy", guarded)
    a._require_generator_scope(scope, scope.slot, profile_sha256=expected)
    with pytest.raises(c.ContractError, match="active profile differs"):
        a._require_generator_scope(scope, scope.slot, profile_sha256="3"*64)


def test_same_owned_request_cannot_claim_a_second_draw(monkeypatch):
    scope, _ = _source_scope()
    holder = a.I1Authority()
    monkeypatch.setattr(a, "require_i1", lambda *_, **__: None)
    monkeypatch.setattr(a, "_ISSUED", {holder: SimpleNamespace(generator_scope=scope)})
    monkeypatch.setattr(a, "_GENERATOR_DRAWS", set())
    a.claim_generator_draw(holder, context=None, protocol_ref=None, generator_slot=scope.slot)
    with pytest.raises(c.ContractError, match="already consumed"):
        a.claim_generator_draw(holder, context=None, protocol_ref=None, generator_slot=scope.slot)


def test_registered_campaign_cannot_start_outside_the_verified_owned_worker(monkeypatch):
    monkeypatch.delitem(sys.modules, "softqp_runtime_custody", raising=False)

    def forbidden(*args, **kwargs):
        pytest.fail("unowned campaign reached output or RNG")

    monkeypatch.setattr(g, "_run_campaign", forbidden)
    monkeypatch.setattr(g, "_rng", forbidden)
    raw = c.canonical_bytes({"schema": "softqp.r4.generate-campaign-request/1", "plan_sha256": "1"*64})
    with pytest.raises(c.ContractError, match="verified owned worker"):
        g.dispatch_registered_campaign(raw, object())
