"""Actual strict admission IO controls; fixtures are not scientific populations."""

from collections import Counter
import copy
from dataclasses import FrozenInstanceError, replace
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
def test_cross_call_same_size_mutations_cannot_reuse_success(scale_bundle, monkeypatch, tmp_path, target):
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


def test_cached_dependency_still_refuses_an_ancestor_cycle(scale_bundle):
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


def test_writer_alias_index_reads_no_unrelated_paths_and_refuses_reserved_input(scale_bundle, monkeypatch):
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


def test_unknown_historical_fixture_producer_identity_refuses(tmp_path):
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
