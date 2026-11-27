"""Actual installed-SDK controls for isolated learning orchestration."""

from collections import Counter
from dataclasses import replace
import json
from pathlib import Path

import pytest

from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import native_labels as native
from pipeline.learned_comparison import stream_inputs as stream
from pipeline.learned_comparison import training as t
from test_learned_contracts import PROVIDER
from test_native_labels import runtime_identity, native_problem
from test_stream_inputs import build_factored, put


def runtime_fixture(root):
    path = root / "training-runtime.json"
    product = Path(t.__file__).parent
    names = (
        "training.py",
        "training_worker.py",
        "native_labels.py",
        "stream_inputs.py",
        "phase_inputs.py",
        "contracts.py",
    )
    spec = {
        "lane": "excluded-software-fixture",
        "runtime": runtime_identity(),
        "product_sources": {name: native._file_sha(product / name) for name in names},
    }
    raw = c.canonical_bytes(spec)
    path.write_bytes(raw)
    return t.FixtureRuntime.load(path, expected_sha256=c.digest(raw))


@pytest.fixture(scope="module")
def admitted(tmp_path_factory):
    root = tmp_path_factory.mktemp("training")
    runtime = runtime_fixture(root)
    context, docs, refs = PROVIDER["build"](root / "source")
    runtime_doc = runtime.verify()["runtime"]
    context = replace(
        context, settings_hashes={**context.settings_hashes, **native.settings_identities(runtime_doc)}
    )
    protocol = refs["protocol"]
    roles = ("train", "validation", "calibration")
    known = {
        role + "-case": native_problem(role, q, role + "-fixture")
        for role, q in zip((*roles, "test"), (0, 0.25, 2, -1), strict=True)
    }
    context, sources, frames = build_factored(context, protocol, known)
    scope = dict(
        sources=sources,
        frames=list(frames.values()),
        fit_source_ids=list(context.fit_source_ids),
        exclusions=sorted(docs["dataset"]["payload"]["exclusions"]),
        attribution="Excluded analytical training and calibration fixtures",
        license="MIT",
    )
    missing = [
        {"frame_id": frame, "ref": None, "state": "missing", "reason": "P0 input only"} for frame in frames
    ]
    initial = stream.derive_stream_payload(context, protocol, **scope, labels=missing)
    context, reference = put(context, protocol, stream.STREAM, "p0", initial)
    p0 = stream.preflight_stream(context, descriptor_id="p0", expected_descriptor_sha256=reference["sha256"])
    p0_doc = c.strict_loads(p0.receipt_bytes)
    authority_doc = {
        "format": native.AUTHORITY,
        "mode": "fixture",
        "registration": None,
        "registration_file": None,
        "identities": p0_doc["identities"],
        "preflight_sha256": p0.sha256,
        "population_sha256": p0_doc["population_sha256"],
        "roles": list(roles),
        "inventory_sha256": native._hash(native._slots_data(native.planned_slots(p0, roles))),
        "runtime": runtime_doc,
        "settings_hashes": native.settings_identities(runtime_doc),
        "sources": {
            name: native._file_sha(Path(native.__file__).resolve().parents[1] / name)
            for name in native._WORKER_SOURCE
        },
    }
    path = root / "native-authority.json"
    raw = native._encode(authority_doc)
    path.write_bytes(raw)
    authority = native.NativeAuthority.load(path, expected_sha256=c.digest(raw))
    native_plan = native.NativePlan.from_preflight(
        context, p0, expected_preflight_sha256=p0.sha256, roles=roles, authority=authority
    )
    run = native.supervise_native_run(native_plan, authority, root / "native")
    labels = {row["frame_id"]: row for row in missing}
    for row in run.document["rows"]:
        assert row["state"] == "accepted"
        file = row["label"]
        raw = (run.root / file["path"]).read_bytes()
        name = c.strict_loads(raw)["artifact_id"]
        (context.root / (name + ".json")).write_bytes(raw)
        reference = dict(kind=stream.LABELS, artifact_id=name, path=name + ".json", sha256=c.digest(raw))
        context = replace(context, catalog={**context.catalog, name: reference})
        labels[row["input"]["frame"]["artifact_id"]].update(ref=reference, state="provider", reason=None)
    updated = stream.derive_stream_payload(context, protocol, **scope, labels=list(labels.values()))
    context, reference = put(context, protocol, stream.STREAM, "p1", updated)
    p1 = stream.preflight_stream(context, descriptor_id="p1", expected_descriptor_sha256=reference["sha256"])
    paths = {role: root / (role + "-native.json") for role in roles}
    digests = {role: run.project_role(role, paths[role]) for role in roles}
    trusts = native.bind_labeled_preflight(
        native_plan,
        run,
        p1,
        expected_manifest_sha256=run.sha256,
        expected_labeled_preflight_sha256=p1.sha256,
        projection_hashes=digests,
    )
    proofs = {
        row.role: native.NativeRoleProof.load(paths[row.role], row, allow_fixture=True) for row in trusts
    }
    readers = {}
    for role in roles:
        directory = root / role
        sha = stream.materialize_stream_phase(p1, directory, role=role, expected_preflight_sha256=p1.sha256)
        readers[role] = stream.StreamingPhaseReader(
            directory,
            role=role,
            expected_manifest_sha256=sha,
            expected_preflight_sha256=p1.sha256,
            allow_fixture=True,
        )
    policy = c.canonical_bytes(
        {
            "lane": "excluded-software-fixture",
            "p1": p1.sha256,
            "phases": {role: readers[role].manifest_sha256 for role in ("train", "validation")},
            "max_fixture_epochs": 4,
        }
    )
    plan = t.TrainingPlan.admit(
        None,
        context=context,
        protocol_ref=protocol,
        labeled_preflight=p1,
        expected_preflight_sha256=p1.sha256,
        train=readers["train"],
        validation=readers["validation"],
        native_role_proofs={role: proofs[role] for role in ("train", "validation")},
        expected_policy_sha256=c.digest(policy),
        fixture_policy=policy,
    )
    return root, runtime, plan, readers, proofs


@pytest.fixture(scope="module")
def l2_boundary(admitted):
    root, runtime, plan, _, _ = admitted
    full = t.supervise_training(
        plan, runtime, method="learned_osqp", seed=41001, destination=root / "l2-full", fixture_stop_after=2
    )
    assert full.document["state"] == "fixture-exercise", full.document["reason"]
    return full


def test_actual_six_transition_sdk_training_raw_resume_and_v2_checkpoint(admitted, l2_boundary):
    root, runtime, plan, _, _ = admitted
    full = l2_boundary
    partial = t.supervise_training(
        plan, runtime, method="learned_osqp", seed=41001, destination=root / "l2-cut", fixture_stop_after=1
    )
    resumed = t.supervise_training(
        plan,
        runtime,
        method="learned_osqp",
        seed=41001,
        destination=root / "l2-resumed",
        fixture_stop_after=2,
        resume=(partial.root, partial.sha256),
    )
    assert partial.document["state"] == resumed.document["state"] == "fixture-exercise"
    first, second = [run.document["snapshots"][0] for run in (full, resumed)]
    assert first["snapshot_sha256"] == second["snapshot_sha256"]
    parts = t._snapshot_parts(full.root, first)
    assert parts == t._snapshot_parts(resumed.root, second)
    assert parts["initial"] != parts["current"]
    metadata = json.loads(parts["metadata"])
    assert metadata["history"][0]["train_objective"] is None
    assert sum(row["optimizer_steps"] for row in metadata["history"]) == 2
    assert metadata["history"][1]["gradient_nonzero"]
    assert "latest" in full.document["checkpoints"]
    reread = t.read_training_run(full.root, expected_manifest_sha256=full.sha256, plan=plan, runtime=runtime)
    assert reread.raw == full.raw
    assert not (resumed.root / "H-2-3-001-current.f64").exists()


def test_adversarial_changed_snapshot_file_refuses_fresh_run(admitted, l2_boundary, tmp_path):
    import shutil

    _, runtime, plan, _, _ = admitted
    target = tmp_path / "forged"
    shutil.copytree(l2_boundary.root, target)
    actual = l2_boundary.document["snapshots"][0]["files"]["moments"]
    path = target / actual["path"]
    contents = path.read_bytes()
    path.write_bytes(bytes([contents[0] ^ 1]) + contents[1:])
    with pytest.raises(c.ContractError, match="stored bytes"):
        t.read_training_run(target, expected_manifest_sha256=l2_boundary.sha256, plan=plan, runtime=runtime)


def test_adversarial_actual_leconv_training_and_frozen_calibration_role_io(admitted, monkeypatch):
    root, runtime, plan, readers, proofs = admitted
    result = t.supervise_training(
        plan, runtime, method="learned_daqp", seed=41002, destination=root / "graph", fixture_stop_after=3
    )
    assert result.document["state"] == "fixture-exercise", result.document["reason"]
    ref = result.document["checkpoints"]["final"]
    frozen = t.publish_frozen_inference(result, root / "frozen", expected_run_sha256=result.sha256)
    setup = t.CalibrationPlan.admit(
        None,
        context=plan.context,
        calibration=readers["calibration"],
        frozen_inference=frozen,
        native_role_proof=proofs["calibration"],
        expected_policy_sha256=readers["calibration"]._identities["learning_policy_sha256"],
        expected_calibration_manifest_sha256=readers["calibration"].manifest_sha256,
        expected_receipt_sha256=frozen.sha256,
        expected_run_sha256=result.sha256,
        expected_checkpoint_sha256=ref["sha256"],
    )
    paths = [plan.context.root, plan.train._root, plan.validation._root, result.root]
    shifted = [path.with_name(path.name + "-unavailable") for path in paths]
    reads = Counter()
    original = Path.open

    def observed(path, *args, **kwargs):
        if kwargs.get("mode", args[0] if args else "r") == "rb":
            reads[path] += 1
        return original(path, *args, **kwargs)

    for path, hidden in zip(paths, shifted, strict=True):
        path.rename(hidden)
    try:
        monkeypatch.setattr(Path, "open", observed)
        value = t.supervise_calibration(setup, runtime, root / "calibrated")
        assert value["state"] == "calibrated", value["reason"]
        assert len(value["values"]["scores"]) == 9
        assert value["values"]["mask_count"] > 0
        assert any(path.parent == readers["calibration"]._root for path in reads)
        assert not any(path.is_relative_to(parent) for path in reads for parent in [*paths, *shifted])
    finally:
        for path, hidden in zip(paths, shifted, strict=True):
            hidden.rename(path)


def test_actual_sdk_fourteen_heads_and_three_seed_initializers(admitted, tmp_path):
    import secrets

    _, runtime, plan, _, _ = admitted
    spec = runtime.verify()
    work = tmp_path / "initializer"
    script = tmp_path / "initialize.py"
    script.write_text(
        """import json, os, runpy, sys
from hashlib import sha256
from pathlib import Path
p = Path(sys.argv[1])
while not (p / 'boot.json').exists():
    __import__('time').sleep(.005)
config = json.loads((p / 'boot.json').read_bytes())
admit = runpy.run_path(config['native'])['_profile_checks']
audit = admit({'runtime':config['runtime']})
from softqp.learning.fixed_point import L2WSHead
from softqp.learning.graph import ActiveSetGNN, Labels, fit_classes
from softqp.learning.parameters import HEADS,SEEDS,weight_bytes,torch
from softqp.learning.training import SourceUnit, balance_sources
from types import SimpleNamespace

torch.set_num_threads(1)
torch.set_num_interop_threads(1)
rows=[]
for seed in SEEDS:
    for n,m in HEADS:
        model=L2WSHead(n,m,seed)
        raw=weight_bytes(model)
        rows.append((model.head,seed,len(raw)//8,sha256(raw).hexdigest()))
    model=ActiveSetGNN(seed,.5)
    raw=weight_bytes(model)
    rows.append((model.head,seed,len(raw)//8,sha256(raw).hexdigest()))
same=sha256(weight_bytes(L2WSHead(2,3,41001))).hexdigest()
units=[]
for source in range(3):
    frames=[]
    for frame in range(32):
        positive=(source+frame*frame)%3
        labels=Labels(torch.tensor([1]*positive+[0]*(3-positive),dtype=torch.float64),
                      torch.ones(3,dtype=torch.bool))
        frames.append(SimpleNamespace(labels=labels))
    units.append(SourceUnit(chr(65+source),'N12',0,'train',frames))
statistics=fit_classes(balance_sources(list(reversed(units)),'train'))
out={'audit':audit,'pid':os.getpid(),'rows':rows,'repeat':same,
     'class_order': [statistics.mass0.hex(),statistics.mass1.hex()]}
staged=p / 'output'
staged.write_bytes((json.dumps(out,sort_keys=True,separators=(',',':'))+'\\n').encode())
os.link(staged,p / 'initializer.json')
while not (p / 'exit').exists():
    __import__('time').sleep(.005)
""",
        encoding="utf-8",
    )
    python = Path(spec["runtime"]["python"])
    launch = [
        str(python),
        "-I",
        "-S",
        "-B",
        "-X",
        f"pycache_prefix={work / 'unused-cache'}",
        str(script),
        str(work),
    ]
    owned = native._OwnedWorker(work, launch, python, nonce=secrets.token_hex(16))
    try:
        t._json_ref(work / "boot.json", {"runtime": spec["runtime"], "native": str(Path(native.__file__))})
        report = owned.wait_file(work / "initializer.json", 600)
        assert report["pid"] in owned._pids() and report["audit"]["full_source_files_checked"] == 19500
        (work / "exit").touch()
        assert owned.process.wait(timeout=10) == 0
    finally:
        owned.close()
    counts = {head["id"]: head["parameter_count"] for head in plan.context.authority.matrix["heads"]}
    expected = {
        (head, seed, amount) for head, amount in {**counts, "graph": 52098}.items() for seed in c.SEEDS
    }
    assert {(head, seed, amount) for head, seed, amount, _ in report["rows"]} == expected
    assert sum(counts.values()) == 21922702
    assert len({digest for _, _, _, digest in report["rows"]}) == 45
    assert report["repeat"] == next(x[3] for x in report["rows"] if x[:2] == ["H-2-3", 41001])
    assert report["class_order"] == ["0x1.555555555554cp-1", "0x1.5555555555550p-2"]
    reversed_mass0 = 0.0
    for source in reversed(range(3)):
        for frame in reversed(range(32)):
            reversed_mass0 += (1 / 3 / 32) * (3 - (source + frame * frame) % 3) / 3
    assert reversed_mass0.hex() == "0x1.5555555555549p-1"
    assert float.fromhex(report["class_order"][0]) != reversed_mass0


def test_registered_request_exact_six_and_no_fixture_epoch_narrowing(tmp_path):
    jobs = t.registered_jobs()
    assert jobs == tuple(
        (method, seed) for method in ("learned_osqp", "learned_daqp") for seed in (41001, 41002, 41003)
    )
    for method, seed in jobs:
        request = c.strict_loads(t.registered_learning_request("train-model", method, seed))
        assert set(request) == {"schema", "operation", "method", "seed", "resume"}
        assert (request["method"], request["seed"], request["resume"]) == (method, seed, None)
    with pytest.raises(c.ContractError, match="unregistered learning"):
        t.registered_learning_request("train-model", "learned_osqp", 42000)
    with pytest.raises(c.ContractError, match="no resume"):
        t.registered_learning_request(
            "calibrate-model",
            "learned_daqp",
            41001,
            resume={"root": str(tmp_path / "excluded-controls"), "sha256": "1" * 64},
        )


def test_aggregate_artifact_budget_counts_unique_physical_bytes(tmp_path, monkeypatch):
    import os
    import shutil
    from collections import namedtuple

    limit = namedtuple("DiskUsage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda _: limit(64 * 2**30, 0, 64 * 2**30))
    root = tmp_path / "artifacts"
    root.mkdir()
    calibration = root / "calibration"
    calibration.mkdir()
    (calibration / "artifact.bin").write_bytes(b"source")
    os.link(calibration / "artifact.bin", root / "same-physical-bytes.bin")
    budget = t.LearningBudget((root, calibration), root / "next", committed_bytes=10)
    assert budget.check() == 16
    assert budget.check(extra_bytes=5) == 16
    assert budget.high_water == 21
    with pytest.raises(c.ContractError, match="aggregate learning"):
        budget.check(extra_bytes=8 * 2**30)
