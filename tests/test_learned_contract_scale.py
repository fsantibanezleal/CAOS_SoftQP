"""Actual strict admission IO controls; fixtures are not scientific populations."""

from collections import Counter
import copy
from dataclasses import FrozenInstanceError, replace
import os
from pathlib import Path
import runpy
import shutil
import struct

import pytest

from pipeline.learned_comparison import contracts as c

PROVIDER = runpy.run_path(str(Path(__file__).parent / "fixtures/learned-contracts/provider.py"))


@pytest.fixture(scope="module")
def scale_bundle(tmp_path_factory):
    return PROVIDER["build"](tmp_path_factory.mktemp("u1-scale-provider"))


def observe_reads(monkeypatch):
    reads = Counter()
    original = Path.read_bytes

    def observed(path):
        reads[path.resolve()] += 1
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", observed)
    return reads


def missing_document(context, name):
    return PROVIDER["envelope"]("learning-problem", name, None, context, missing=True)


@pytest.mark.parametrize("unrelated_count", [0, 16, 64])
def test_single_root_payload_reads_ignore_unrelated_catalog(scale_bundle, monkeypatch, unrelated_count):
    context, _, refs = scale_bundle
    catalog = dict(context.catalog)
    extra_paths = []
    for i in range(unrelated_count):
        name = f"unrelated-{unrelated_count}-{i}"
        artifact = c.write_artifact(missing_document(context, name), name + ".json", context)
        catalog[name] = dict(kind=artifact.kind, artifact_id=name, path=name + ".json", sha256=artifact.raw_sha256)
        extra_paths.append(context.root / (name + ".json"))
    expanded = replace(context, catalog=catalog)
    reads = observe_reads(monkeypatch)
    request = c.ReadRequest(context.root / refs["protocol"]["path"], refs["protocol"]["sha256"])
    c.read_artifact(request.path, expanded, expected_sha256=request.expected_sha256)
    cold = dict(reads)
    reads.clear()
    c.read_artifact(request.path, expanded, expected_sha256=request.expected_sha256)
    assert dict(reads) == cold
    assert set(reads) == {request.path.resolve(), (c.SCHEMAS / "softqp-learning-protocol.schema.json").resolve()}
    assert sum(reads.values()) == 2
    assert not set(extra_paths).intersection(reads)


def test_unrelated_corruption_is_not_full_population_validation(scale_bundle, monkeypatch):
    context, _, refs = scale_bundle
    name = "explicit-corrupt-population-member"
    artifact = c.write_artifact(missing_document(context, name), name + ".json", context)
    reference = dict(kind=artifact.kind, artifact_id=name, path=name + ".json", sha256=artifact.raw_sha256)
    expanded = replace(context, catalog={**context.catalog, name: reference})
    path = context.root / reference["path"]
    path.write_bytes(b"invalid unrelated bytes\n")
    before = path.read_bytes()
    reads = observe_reads(monkeypatch)
    protocol = c.ReadRequest(context.root / refs["protocol"]["path"], refs["protocol"]["sha256"])
    assert c.read_artifact(protocol.path, expanded).kind == "learning-protocol"
    assert path.resolve() not in reads
    with pytest.raises(c.ContractError):
        c.read_artifacts((protocol, c.ReadRequest(path, reference["sha256"])), expanded)
    assert path.read_bytes() == before


def test_shared_positive_dag_and_duplicate_requests_read_each_file_once(scale_bundle, monkeypatch):
    context, _, refs = scale_bundle
    reads = observe_reads(monkeypatch)
    requests = tuple(
        c.ReadRequest(context.root / refs[name]["path"], refs[name]["sha256"])
        for name in ("checkpoint", "features", "checkpoint", "protocol")
    )
    artifacts = c.read_artifacts(requests, context)
    assert [artifact.artifact_id for artifact in artifacts] == ["checkpoint", "features", "checkpoint", "protocol"]
    assert len(artifacts) == len(requests) and artifacts[0].raw == artifacts[2].raw
    assert all(count == 1 for count in reads.values())
    assert (context.root / "fixture-untrained.f64").resolve() in reads
    assert (context.root / refs["dataset"]["path"]).resolve() in reads
    assert (context.root / refs["result"]["path"]).resolve() not in reads


@pytest.mark.parametrize("target", ["root", "parent", "numeric", "schema"])
def test_adversarial_cross_call_same_size_mutations_cannot_reuse_success(scale_bundle, monkeypatch, tmp_path, target):
    context, _, refs = scale_bundle
    if target == "schema":
        schemas = tmp_path / "schemas"
        shutil.copytree(c.SCHEMAS, schemas)
        monkeypatch.setattr(c, "SCHEMAS", schemas)
    root = context.root / refs["checkpoint"]["path"]
    c.read_artifact(root, context)
    if target == "root":
        path = root
        original = path.read_bytes()
        changed = original.replace(b'"state": "provider"', b'"state": "missing "', 1)
    elif target == "parent":
        path = context.root / refs["protocol"]["path"]
        original = path.read_bytes()
        changed = original.replace(b"No scientific producer", b"No Scientific producer", 1)
    elif target == "numeric":
        path = context.root / "fixture-untrained.f64"
        original = path.read_bytes()
        changed = struct.pack("<d", 1) + original[8:]
    else:
        path = c.SCHEMAS / "softqp-learning-checkpoint.schema.json"
        original = path.read_bytes()
        changed = original.replace(b'"1.0.0"', b'"9.0.0"', 1)
    assert original != changed and len(original) == len(changed)
    path.write_bytes(changed)
    try:
        with pytest.raises(c.ContractError):
            c.read_artifact(root, context)
        assert path.read_bytes() == changed
    finally:
        path.write_bytes(original)


def test_adversarial_cached_dependency_still_refuses_an_ancestor_cycle(scale_bundle):
    context, docs, refs = scale_bundle
    # Dataset was valid independently, but its transitive problem-train identity
    # becomes an ancestor of the second request. No hash fixed point is needed.
    document = copy.deepcopy(docs["checkpoint"])
    document["artifact_id"] = "problem-train"
    document = PROVIDER["reseal"](document)
    path = context.root / "cached-cycle-root.json"
    raw = c.json_bytes(document)
    path.write_bytes(raw)
    with pytest.raises(c.ContractError, match="cycle through cached node"):
        c.read_artifacts(
            (
                c.ReadRequest(context.root / refs["dataset"]["path"], refs["dataset"]["sha256"]),
                c.ReadRequest(path, c.digest(raw)),
            ),
            context,
        )
    assert path.read_bytes() == raw
    with pytest.raises(c.ContractError, match="cycle"):
        c.write_artifact(document, "must-not-publish-cycle.json", context)
    assert not (context.root / "must-not-publish-cycle.json").exists()


@pytest.mark.parametrize("failure", ["hash", "usage", "missing", "untyped", "context"])
def test_batch_failure_never_returns_a_short_success_list(scale_bundle, failure):
    context, _, refs = scale_bundle
    first = c.ReadRequest(context.root / refs["protocol"]["path"], refs["protocol"]["sha256"])
    second = first
    if failure == "hash":
        second = replace(first, expected_sha256="0" * 64)
    elif failure == "usage":
        second = replace(first, usage="unknown")
    elif failure == "missing":
        second = replace(first, path=context.root / "absent-batch-file.json")
    elif failure == "untyped":
        second = dict(path=first.path)
    else:
        context = replace(context, protocol_sha256="0" * 64)
    before = {path.name for path in context.root.iterdir()}
    returned = None
    with pytest.raises(c.ContractError):
        returned = c.read_artifacts((first, second), context)
    assert returned is None and before == {path.name for path in context.root.iterdir()}


def test_batch_order_usage_limits_and_request_immutability(scale_bundle):
    context, _, refs = scale_bundle
    train = c.ReadRequest(context.root / refs["problem-train"]["path"], usage="fit")
    test = c.ReadRequest(context.root / refs["problem-test"]["path"])
    assert c.read_artifacts((), context) == ()
    result = c.read_artifacts((test, train, test), context)
    assert [artifact.artifact_id for artifact in result] == ["problem-test", "problem-train", "problem-test"]
    with pytest.raises(FrozenInstanceError):
        train.usage = "consume"
    with pytest.raises(c.ContractError, match="held-out"):
        c.read_artifacts((test, replace(test, usage="fit")), context)
    with pytest.raises(c.ContractError, match="limit"):
        c.read_artifacts((train,) * (c.MAX_BATCH_REQUESTS + 1), context)
    with pytest.raises(c.ContractError, match="sequence"):
        c.read_artifacts(iter((train,)), context)


def test_batch_freezes_mutable_request_order_before_io(scale_bundle, monkeypatch):
    context, _, refs = scale_bundle
    request = c.ReadRequest(context.root / refs["protocol"]["path"])
    requests = [request, request]
    original_read = Path.read_bytes

    def mutate_caller_list(path):
        requests.clear()
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", mutate_caller_list)
    result = c.read_artifacts(requests, context)
    assert requests == [] and len(result) == 2
    assert [artifact.artifact_id for artifact in result] == ["protocol", "protocol"]


def test_eviction_and_path_aliases_do_not_authorize_stale_roots(scale_bundle, monkeypatch):
    context, _, refs = scale_bundle
    monkeypatch.setattr(c, "_CACHE_ENTRIES", 1)
    monkeypatch.setattr(c, "_CACHE_BYTES", 1)
    path = context.root / refs["protocol"]["path"]
    alias = context.root / "unused-directory" / ".." / path.name
    requests = (c.ReadRequest(path), c.ReadRequest(alias))
    # abspath normalization is the existing single-reader behavior; duplicates
    # remain explicit positions even when cache storage is disabled.
    assert len(c.read_artifacts(requests, context)) == 2
    assert c.read_artifact(path, context).artifact_id == "protocol"


@pytest.mark.parametrize("retain_snapshot", [False, True])
def test_batch_snapshot_and_evicted_reread_have_honest_mutation_semantics(scale_bundle, monkeypatch, retain_snapshot):
    context, _, refs = scale_bundle
    path = context.root / refs["protocol"]["path"]
    raw = path.read_bytes()
    changed = raw.replace(b"No scientific producer", b"No Scientific producer", 1)
    assert changed != raw and len(changed) == len(raw)
    if not retain_snapshot:
        monkeypatch.setattr(c, "_CACHE_BYTES", 1)
    original_read = Path.read_bytes
    mutated = False

    def concurrent_write_after_read(current):
        nonlocal mutated
        result = original_read(current)
        if current == path and not mutated:
            mutated = True
            path.write_bytes(changed)
        return result

    monkeypatch.setattr(Path, "read_bytes", concurrent_write_after_read)
    try:
        requests = (c.ReadRequest(path), c.ReadRequest(path))
        if retain_snapshot:
            artifacts = c.read_artifacts(requests, context)
            assert [artifact.raw for artifact in artifacts] == [raw, raw]
        else:
            with pytest.raises(c.ContractError, match="root bytes changed"):
                c.read_artifacts(requests, context)
        # A new public call can never inherit the prior first-read snapshot.
        with pytest.raises(c.ContractError):
            c.read_artifact(path, context)
        assert original_read(path) == changed
    finally:
        path.write_bytes(raw)


def test_missing_required_parent_is_not_hidden_by_a_previous_batch(scale_bundle):
    context, _, refs = scale_bundle
    root = context.root / refs["checkpoint"]["path"]
    c.read_artifacts((c.ReadRequest(root),), context)
    path = context.root / refs["protocol"]["path"]
    raw = path.read_bytes()
    path.unlink()
    try:
        with pytest.raises(c.ContractError, match="missing artifact"):
            c.read_artifacts((c.ReadRequest(root),), context)
    finally:
        path.write_bytes(raw)


def test_adversarial_writer_alias_index_reads_no_unrelated_paths_and_refuses_reserved_input(scale_bundle, monkeypatch):
    context, _, _ = scale_bundle
    extras = {
        f"reserved-{i}": dict(kind="learning-problem", artifact_id=f"reserved-{i}", path=f"reserved-{i}.json", sha256="0" * 64)
        for i in range(64)
    }
    expanded = replace(context, catalog={**context.catalog, **extras})
    paths = []
    original = c.safe_path

    def observed(root, relative, *, must_exist):
        paths.append(relative)
        return original(root, relative, must_exist=must_exist)

    monkeypatch.setattr(c, "safe_path", observed)
    c.write_artifact(missing_document(expanded, "writer-missing"), "writer-missing.json", expanded)
    assert not set(paths).intersection(reference["path"] for reference in extras.values())
    before = {path.name for path in context.root.iterdir()}
    with pytest.raises(c.ContractError, match="aliases"):
        c.write_artifact(missing_document(expanded, "writer-reserved"), "reserved-0.json", expanded)
    assert before == {path.name for path in context.root.iterdir()}
    assert not (context.root / "reserved-0.json").exists()


def test_historical_fixture_producer_identity_is_distinct_from_current_consumer(tmp_path):
    source = Path(__file__).parent / "fixtures/learned-contracts"
    root = tmp_path / "historical-provider"
    shutil.copytree(source / "provider-tree", root)
    before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    context = PROVIDER["load_context"](root)
    expected = "cb20ff7c9f12e5243d92a02418e9c34bdd8ffbc8082cd3d0127c964f1222bae0"
    assert context.producer_source_sha256 == expected == c.digest(context.producer_source_bytes)
    assert context.producer_source_bytes == (source / "provider-source.py.fixture").read_bytes()
    assert c.digest(Path(c.__file__).read_bytes()) != expected
    assert c.read_artifact(root / "protocol.json", context).state == "provider"
    assert before == {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_adversarial_unknown_historical_fixture_producer_identity_refuses(tmp_path):
    source = Path(__file__).parent / "fixtures/learned-contracts/provider-tree"
    root = tmp_path / "unknown-producer"
    shutil.copytree(source, root)
    path = root / "fixture-context.json"
    value = c.strict_loads(path.read_bytes())
    value["producer_source_sha256"] = "0" * 64
    changed = c.json_bytes(value)
    path.write_bytes(changed)
    with pytest.raises(c.ContractError, match="unknown fixture producer"):
        PROVIDER["load_context"](root)
    assert path.read_bytes() == changed


def test_known_historical_producer_snapshot_requires_exact_bytes(tmp_path, monkeypatch):
    source = Path(__file__).parent / "fixtures/learned-contracts"
    root = tmp_path / "changed-producer-snapshot"
    shutil.copytree(source / "provider-tree", root)
    snapshot_root = tmp_path / "snapshot-files"
    snapshot_root.mkdir()
    raw = (source / "provider-source.py.fixture").read_bytes()
    changed = b"#" + raw[1:]
    assert changed != raw and len(changed) == len(raw)
    snapshot = snapshot_root / "provider-source.py.fixture"
    snapshot.write_bytes(changed)
    monkeypatch.setitem(PROVIDER["load_context"].__globals__, "HERE", snapshot_root)
    with pytest.raises(c.ContractError, match="historical producer snapshot changed"):
        PROVIDER["load_context"](root)
    assert snapshot.read_bytes() == changed


def test_current_producer_context_still_loads_its_actual_bytes(scale_bundle, tmp_path):
    context, _, _ = scale_bundle
    root = tmp_path / "current-producer-context"
    root.mkdir()
    PROVIDER["save_context"](context, root / "fixture-context.json")
    loaded = PROVIDER["load_context"](root)
    actual = Path(c.__file__).read_bytes()
    assert loaded.producer_source_sha256 == c.digest(actual)
    assert loaded.producer_source_bytes == actual


def test_escaped_surrogate_artifact_id_round_trips(scale_bundle):
    context, _, _ = scale_bundle
    identifier = "artifact-\ud800"
    document = missing_document(context, identifier)
    raw = c.json_bytes(document)
    assert b"\\ud800" in raw
    c.schema_validate(c.strict_loads(raw))

    path = context.root / "escaped-surrogate.json"
    written = c.write_artifact(document, path.name, context)
    request = c.ReadRequest(path, c.digest(raw))
    artifacts = (
        c.validate_artifact(document, context),
        written,
        c.read_artifact(path, context, expected_sha256=request.expected_sha256),
        *c.read_artifacts((request, request), context),
    )
    assert all(artifact.artifact_id == identifier and artifact.raw == raw for artifact in artifacts)
    assert path.read_bytes() == raw


def test_batch_reads_distinct_files_with_colliding_windows_case_keys(scale_bundle):
    context, _, _ = scale_bundle
    paths = (context.root / "deseret-\U00010400.json", context.root / "deseret-\U00010428.json")
    identifiers = ("distinct-deseret-0", "distinct-deseret-1")
    written = tuple(
        c.write_artifact(missing_document(context, identifier), path.name, context)
        for path, identifier in zip(paths, identifiers, strict=True)
    )
    assert not paths[0].samefile(paths[1])
    if os.name == "nt":
        assert os.path.normcase(str(paths[0].resolve())) == os.path.normcase(str(paths[1].resolve()))
    scalar = tuple(c.read_artifact(path, context) for path in paths)
    assert tuple(artifact.artifact_id for artifact in scalar) == identifiers
    assert c.read_artifacts(tuple(c.ReadRequest(path) for path in paths), context) == written
    sealed = tuple(
        c.ReadRequest(path, artifact.raw_sha256) for path, artifact in zip(paths, written, strict=True)
    )
    assert c.read_artifacts(sealed, context) == written


@pytest.mark.parametrize("entry", ["read", "batch"])
def test_adversarial_distinct_case_colliding_sibling_root_refuses(scale_bundle, tmp_path, entry):
    context, _, _ = scale_bundle
    inside = tmp_path / "scope-\U00010400"
    outside = tmp_path / "scope-\U00010428"
    inside.mkdir()
    outside.mkdir()
    assert not inside.samefile(outside)
    allowed = replace(context, root=inside, catalog={})
    other = replace(context, root=outside, catalog={})
    original = c.write_artifact(missing_document(allowed, "inside-artifact"), "target.json", allowed)
    different = c.write_artifact(missing_document(other, "outside-artifact"), "target.json", other)
    requested = outside / "target.json"
    if os.name == "nt":
        assert requested.is_relative_to(inside)
    assert c.read_artifact(requested, other) == different
    with pytest.raises(c.ContractError, match="input outside configured artifact root"):
        if entry == "read":
            c.read_artifact(requested, allowed)
        else:
            c.read_artifacts((c.ReadRequest(requested),), allowed)
    assert (inside / "target.json").read_bytes() == original.raw
    assert requested.read_bytes() == different.raw


def test_genuine_root_case_alias_resolves_to_the_same_input(scale_bundle):
    context, _, _ = scale_bundle
    path = context.root / "protocol.json"
    actual = c.read_artifact(path, context)
    alias = path
    if os.name == "nt":
        alias = path.parent.with_name(path.parent.name.upper()) / path.name
        assert str(alias) != str(path) and alias.samefile(path)
    assert c.read_artifacts((c.ReadRequest(path), c.ReadRequest(alias, actual.raw_sha256)), context) == (
        actual,
        actual,
    )


def test_protected_root_checks_distinguish_actual_case_colliding_directories(scale_bundle, tmp_path):
    context, _, _ = scale_bundle
    allowed = tmp_path / "scope-\U00010400"
    protected = tmp_path / "scope-\U00010428"
    allowed.mkdir()
    protected.mkdir()
    assert not allowed.samefile(protected)
    external = replace(context, root=tmp_path, catalog={}, forbidden_roots=(protected,))
    child = replace(external, root=allowed)
    assert child.root.samefile(allowed)
    with pytest.raises(c.ContractError, match="context root inside checkout"):
        replace(external, root=protected)
    document = missing_document(external, "protected-root-probe")
    artifact = c.write_artifact(document, f"{allowed.name}/target.json", external)
    with pytest.raises(c.ContractError, match="protected root"):
        c.write_artifact(document, f"{protected.name}/target.json", external)
    assert (allowed / "target.json").read_bytes() == artifact.raw
    assert not (protected / "target.json").exists()


@pytest.mark.parametrize("entry", ["validate", "write", "read", "batch"])
def test_missing_schema_is_a_contract_refusal(scale_bundle, monkeypatch, tmp_path, entry):
    context, _, _ = scale_bundle
    document = missing_document(context, "schema-missing-" + entry)
    source = context.root / f"schema-missing-input-{entry}.json"
    output = context.root / f"schema-missing-output-{entry}.json"
    artifact = c.write_artifact(document, source.name, context)
    request = c.ReadRequest(source, artifact.raw_sha256)
    monkeypatch.setattr(c, "SCHEMAS", tmp_path)
    invoke = {
        "validate": lambda: c.validate_artifact(document, context),
        "write": lambda: c.write_artifact(document, output.name, context),
        "read": lambda: c.read_artifact(source, context, expected_sha256=request.expected_sha256),
        "batch": lambda: c.read_artifacts((request,), context),
    }[entry]
    with pytest.raises(c.ContractError, match="schema bytes unavailable"):
        invoke()
    assert source.read_bytes() == artifact.raw
    assert not output.exists()


@pytest.fixture(scope="module")
def production_admission_context(scale_bundle):
    context, _, _ = scale_bundle
    return replace(
        context,
        allow_fixture=False,
        expected_result_keys=context.authority.keys("method-status") + context.authority.keys("control-status"),
        expected_diagnostic_keys=context.authority.keys("diagnostic-status"),
    )


@pytest.mark.parametrize("usage", ["fit", "calibrate"])
@pytest.mark.parametrize("entry", ["validate", "read", "batch"])
def test_adversarial_production_training_usage_refuses_before_reads(
    scale_bundle, production_admission_context, monkeypatch, entry, usage
):
    fixture, docs, refs = scale_bundle
    context = production_admission_context
    root = c.ReadRequest(context.root / refs["features"]["path"], refs["features"]["sha256"], usage)
    consume = c.ReadRequest(context.root / refs["protocol"]["path"], refs["protocol"]["sha256"])
    reads = observe_reads(monkeypatch)
    with pytest.raises(c.ContractError, match="production fit/calibrate requires isolated role-scoped admission"):
        if entry == "validate":
            c.validate_artifact(docs["features"], context, usage=usage)
        elif entry == "read":
            c.read_artifact(root.path, context, expected_sha256=root.expected_sha256, usage=usage)
        else:
            c.read_artifacts((consume, root), context)
    assert not reads

    kind = "problem-train" if usage == "fit" else "problem-calibration"
    allowed = c.ReadRequest(fixture.root / refs[kind]["path"], refs[kind]["sha256"], usage)
    assert c.read_artifacts((allowed,), fixture)[0].artifact_id == kind


def test_split_digest_preserves_interleaved_dataset_entry_order(scale_bundle):
    context, docs, _ = scale_bundle
    trajectory_id = "fixture-trajectory-train"
    trajectory_parent = "fixture-trajectory-parent"
    payloads = {}
    for frame in range(32):
        artifact_id = f"interleaved-frame-{31 - frame:02d}"
        payload = PROVIDER["problem_payload"](
            "train", (frame + 65) / 64, control="contract-fixture:interleaved-split", family="N12"
        )
        payload["source"].update(source_id=trajectory_id, parent_id=trajectory_parent, frame=frame)
        payloads[artifact_id] = payload
    frame_ids = sorted(payloads)
    middle_id = "interleaved-frame-16-middle"
    payloads[middle_id] = copy.deepcopy(docs["problem-validation"]["payload"])
    context = replace(
        context,
        fit_source_ids=(trajectory_id,),
        problem_hashes={**context.problem_hashes, **{key: value["original_sha256"] for key, value in payloads.items()}},
        source_records={
            **context.source_records,
            **{key: c.digest(c.canonical_bytes(value["source"])) for key, value in payloads.items()},
        },
    )

    def put(kind, identifier, payload, trust):
        document = PROVIDER["envelope"](kind, identifier, payload, trust)
        path = identifier + ".json"
        artifact = c.write_artifact(document, path, trust)
        return dict(kind=kind, artifact_id=identifier, path=path, sha256=artifact.raw_sha256)

    entries = [
        dict(problem=put("learning-problem", key, payloads[key], context), source=payloads[key]["source"])
        for key in sorted(payloads)
    ]
    assert entries[17]["problem"]["artifact_id"] == middle_id
    assert [entry["source"]["frame"] for entry in entries if entry["source"]["source_id"] == trajectory_id] == list(
        reversed(range(32))
    )
    context = replace(context, catalog={**context.catalog, **{entry["problem"]["artifact_id"]: entry["problem"] for entry in entries}})
    dataset = copy.deepcopy(docs["dataset"]["payload"])
    single = payloads[middle_id]["source"]
    dataset.update(
        problems=entries,
        source_ids=sorted((trajectory_id, single["source_id"])),
        counts=dict(problems=33, sources=2, train=1, validation=1, calibration=0, test=0),
    )
    dataset_ref = put("learning-dataset", "interleaved-dataset", dataset, context)
    context = replace(context, catalog={**context.catalog, dataset_ref["artifact_id"]: dataset_ref})
    frame_hashes = [payloads[frame_id]["source"]["input_sha256"] for frame_id in frame_ids]
    assignments = sorted(
        [
            dict(
                source_id=trajectory_id,
                parent_id=trajectory_parent,
                input_sha256=c.digest(c.canonical_bytes(frame_hashes)),
                split="train",
                problem_ids=frame_ids,
            ),
            dict(
                source_id=single["source_id"],
                parent_id=single["parent_id"],
                input_sha256=c.digest(c.canonical_bytes([single["input_sha256"]])),
                split="validation",
                problem_ids=[middle_id],
            ),
        ],
        key=lambda item: item["source_id"],
    )
    split = copy.deepcopy(docs["split"]["payload"])
    split.update(
        dataset=dataset_ref,
        assignments=assignments,
        fit_source_ids=[trajectory_id],
        disjointness_sha256=c.digest(c.canonical_bytes(assignments)),
    )
    ref = put("learning-split", "interleaved-split", split, context)
    result = c.read_artifact(context.root / ref["path"], context, expected_sha256=ref["sha256"])
    assert result.payload == split

    changed = copy.deepcopy(split)
    trajectory = next(item for item in changed["assignments"] if item["source_id"] == trajectory_id)
    trajectory["input_sha256"] = c.digest(c.canonical_bytes(list(reversed(frame_hashes))))
    changed["disjointness_sha256"] = c.digest(c.canonical_bytes(changed["assignments"]))
    with pytest.raises(c.ContractError, match="split differs from source-bound dataset"):
        put("learning-split", "reversed-frame-split", changed, context)
    assert not (context.root / "reversed-frame-split.json").exists()
