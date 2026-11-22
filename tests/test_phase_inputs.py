"""Public phase-boundary controls using strictly admitted software fixtures."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import os
from pathlib import Path
import shutil
import subprocess
import threading

import pytest

from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import phase_inputs as phase
from test_learned_contracts import PROVIDER


def add(context, docs, kind, name, payload, *, missing=False):
    document = PROVIDER["envelope"](kind, name, payload, context, missing=missing)
    artifact = c.write_artifact(document, name + ".json", context)
    ref = {"kind": kind, "artifact_id": name, "path": name + ".json", "sha256": artifact.raw_sha256}
    docs[name] = document
    return replace(context, catalog={**context.catalog, name: ref})


@pytest.fixture(scope="module")
def fixture_source(tmp_path_factory):
    context, docs, refs = PROVIDER["build"](tmp_path_factory.mktemp("phase-source"))
    context, docs, refs = PROVIDER["build_graph"](context, docs, refs)
    inputs = []
    for role in ("train", "validation", "calibration", "test"):
        problem_id = "problem-" + role
        for representation, name in (("mlp-v1", "features"), ("graph-v1", "graph-features")):
            artifact_id = name
            if role != "train":
                artifact_id += "-" + role
                payload = deepcopy(docs[name]["payload"])
                payload["problem"] = refs[problem_id]
                payload["transform_sha256"] = docs[problem_id]["payload"]["transform_sha256"]
                if representation == "mlp-v1":
                    names, raw = c.mlp_coordinates(docs[problem_id]["payload"]["transform"])
                    payload["coordinate_order"] = names
                    payload["raw_values"] = raw
                    payload["values"] = [
                        (v - m) / scale
                        for v, m, scale in zip(
                            raw, payload["normalizer"]["mean"], payload["normalizer"]["scale"]
                        )
                    ]
                else:
                    payload["graph"] = c.graph_coordinates(docs[problem_id]["payload"]["transform"])[0]
                context = add(context, docs, "learning-features", artifact_id, payload)
            inputs.append(phase.PhaseInput(problem_id, "learning-features", representation, artifact_id))
        label_id = {"train": "labels", "calibration": "calibration-labels"}.get(role)
        if label_id is None:
            label_id = "missing-labels-" + role
            context = add(context, docs, "learning-labels", label_id, None, missing=True)
        inputs.append(phase.PhaseInput(problem_id, "learning-labels", "cold_daqp", label_id))
    return context, docs, tuple(inputs)


@pytest.fixture
def source(fixture_source, tmp_path):
    context, docs, inputs = fixture_source
    root = tmp_path / "source"
    shutil.copytree(context.root, root)
    return replace(context, root=root), deepcopy(docs), inputs


def preflight(context, inputs, *, dataset_id="dataset", split_id="split"):
    return phase.preflight_phase_inputs(context, dataset_id=dataset_id, split_id=split_id, inputs=inputs)


def make_bundle(source, tmp_path, role="train"):
    context, _, inputs = source
    receipt = preflight(context, inputs)
    target = tmp_path / role
    manifest = phase.materialize_phase_inputs(
        receipt, target, role=role, expected_preflight_sha256=receipt.sha256
    )
    return receipt, target, manifest


def open_bundle(receipt, target, manifest, *, role="train", allow_fixture=True):
    return phase.PhaseInputReader(
        target,
        role=role,
        expected_manifest_sha256=manifest,
        expected_preflight_sha256=receipt.sha256,
        allow_fixture=allow_fixture,
    )


@pytest.mark.parametrize("role", ["train", "validation", "calibration"])
def test_adversarial_actual_phase_opens_after_other_roles_are_removed(source, tmp_path, monkeypatch, role):
    context, docs, inputs = source
    real_open = Path.open
    opened = []

    def observed(path, *args, **kwargs):
        if kwargs.get("mode", args[0] if args else "r") == "rb":
            opened.append(path)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", observed)
    receipt, root, manifest = make_bundle(source, tmp_path, role=role)
    for other in ("train", "validation", "calibration", "test"):
        assert context.root / ("problem-" + other + ".json") in opened
    assert len(c.strict_loads(receipt.receipt_bytes)["records"]) == len(inputs) + 4
    shutil.rmtree(context.root)
    opened.clear()
    reader = open_bundle(receipt, root, manifest, role=role)
    records = reader.records
    assert len(records) == 4
    for record in records:
        artifact = reader.read(record.artifact_id)
        assert artifact.raw == c.json_bytes(docs[record.artifact_id])
        assert record.role == role
    assert opened == [root / "phase-inputs.json", *(root / record.path for record in records)]
    forbidden = "problem-test"
    with pytest.raises(c.ContractError, match="absent from this phase"):
        reader.read(forbidden)
    assert len(opened) == 5
    if role == "validation":
        label = reader.read("missing-labels-validation")
        assert (label.state, label.reason, label.payload) == (
            "missing",
            docs[label.artifact_id]["reason"],
            None,
        )


def test_adversarial_preflight_requires_exact_semantic_inventory(source):
    context, docs, inputs = source
    with pytest.raises(c.ContractError, match="1 missing, 0 extra"):
        preflight(context, inputs[:-1])
    request = inputs[0]
    context = add(context, docs, request.kind, "second-features", docs[request.artifact_id]["payload"])
    duplicate = replace(request, artifact_id="second-features")
    with pytest.raises(c.ContractError, match="duplicate phase semantic key"):
        preflight(context, (*inputs, duplicate))
    extra = replace(duplicate, variant="fabricated")
    with pytest.raises(c.ContractError, match="0 missing, 1 extra"):
        preflight(context, (*inputs, extra))
    with pytest.raises(c.ContractError, match="duplicate phase artifact ID"):
        preflight(context, (replace(inputs[0], artifact_id=inputs[1].artifact_id), *inputs[1:]))


def test_adversarial_preflight_refuses_catalog_valid_alternate_dataset_split_and_problem(source):
    context, docs, inputs = source
    context = add(context, docs, "learning-dataset", "alternate-dataset", docs["dataset"]["payload"])
    alternate_split = deepcopy(docs["split"]["payload"])
    alternate_split["dataset"] = dict(context.catalog["alternate-dataset"])
    context = add(context, docs, "learning-split", "alternate-split", alternate_split)
    with pytest.raises(c.ContractError, match="split differs from nominated dataset"):
        preflight(context, inputs, split_id="alternate-split")

    for index, alternate_field, substitute in [
        (0, "split", "alternate-split"),
        (2, "split", "alternate-split"),
        (2, "problem", "problem-calibration"),
    ]:
        inputs_wrong = list(inputs)
        request = inputs[index]
        base = "calibration-labels" if alternate_field == "problem" else request.artifact_id
        payload = deepcopy(docs[base]["payload"])
        payload[alternate_field] = dict(context.catalog[substitute])
        new_id = f"alternate-{index}-{alternate_field}"
        active = add(context, docs, request.kind, new_id, payload)
        inputs_wrong[index] = replace(request, artifact_id=new_id)
        with pytest.raises(c.ContractError, match="differs from nominated problem/split/protocol"):
            preflight(active, inputs_wrong)


def test_adversarial_trust_and_roles_refuse_before_payload_open(source, tmp_path, monkeypatch):
    receipt, target, manifest = make_bundle(source, tmp_path)
    real = Path.open
    opened = []

    def observed(path, *args, **kwargs):
        opened.append(path)
        return real(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", observed)
    with pytest.raises(c.ContractError, match="unsupported phase role"):
        open_bundle(receipt, target, manifest, role="test")
    with pytest.raises(c.ContractError, match="unsupported phase role"):
        phase.materialize_phase_inputs(
            receipt, tmp_path / "test", role="test", expected_preflight_sha256=receipt.sha256
        )
    assert not opened
    with pytest.raises(c.ContractError, match="fixture phase rejected"):
        open_bundle(receipt, target, manifest, allow_fixture=False)
    with pytest.raises(c.ContractError, match="role/preflight mismatch"):
        open_bundle(receipt, target, manifest, role="validation")
    with pytest.raises(c.ContractError, match="role/preflight mismatch"):
        phase.PhaseInputReader(
            target,
            role="train",
            expected_manifest_sha256=manifest,
            expected_preflight_sha256="0" * 64,
            allow_fixture=True,
        )
    assert set(opened) == {target / "phase-inputs.json"}


@pytest.mark.parametrize("mutation", ["reduced", "source", "role", "fixture", "path"])
def test_adversarial_manifest_substitution_refused_even_with_rehashed_document(source, tmp_path, mutation):
    receipt, target, manifest = make_bundle(source, tmp_path)
    path = target / "phase-inputs.json"
    forged = c.strict_loads(path.read_bytes())
    if mutation == "reduced":
        forged["records"].pop()
    elif mutation == "source":
        forged["records"][0]["source_id"] = "other-source"
    elif mutation == "role":
        forged["records"][0]["role"] = "test"
    elif mutation == "fixture":
        forged["fixture_only"] = False
    else:
        forged["records"][0]["path"] = "../outside.json"
    raw = c.json_bytes(forged)
    path.write_bytes(raw)
    assert c.digest(raw) != manifest
    with pytest.raises(c.ContractError, match="manifest digest mismatch"):
        open_bundle(receipt, target, manifest)
    with pytest.raises(c.ContractError):
        open_bundle(receipt, target, c.digest(raw))


def test_adversarial_same_size_mutation_missing_input_and_fresh_reopen(source, tmp_path):
    receipt, target, manifest = make_bundle(source, tmp_path)
    reader = open_bundle(receipt, target, manifest)
    record = reader.records[0]
    artifact = reader.read(record.artifact_id)
    path = target / record.path
    raw = path.read_bytes()
    changed = raw.replace(b'"version": "1.0.0"', b'"version": "2.0.0"')
    assert changed != raw and len(changed) == len(raw)
    path.write_bytes(changed)
    with pytest.raises(c.ContractError, match="payload byte hash mismatch"):
        reader.read(record.artifact_id)
    path.unlink()
    with pytest.raises(c.ContractError, match="payload unavailable"):
        reader.read(record.artifact_id)
    with pytest.raises(c.ContractError, match="inventory differs"):
        open_bundle(receipt, target, manifest)
    assert artifact.raw == raw


def test_adversarial_path_alias_junction_and_hardlink_refused(source, tmp_path):
    receipt, root, manifest = make_bundle(source, tmp_path)
    with pytest.raises(c.ContractError, match="exists or is a case alias"):
        phase.materialize_phase_inputs(
            receipt, root.with_name("Train"), role="train", expected_preflight_sha256=receipt.sha256
        )
    if os.name == "nt":
        with pytest.raises(c.ContractError, match="case or path alias"):
            open_bundle(receipt, root.with_name("Train"), manifest)
        sibling = root.with_name("train-sibling")
        sibling.mkdir()
        junction = root.with_name("train-junction")
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(sibling)], check=True, capture_output=True
        )
        try:
            with pytest.raises(c.ContractError, match="symlink/reparse"):
                open_bundle(receipt, junction, manifest)
            with pytest.raises(c.ContractError, match="symlink/reparse"):
                phase.materialize_phase_inputs(
                    receipt, junction / "out", role="train", expected_preflight_sha256=receipt.sha256
                )
        finally:
            junction.rmdir()
    reader = open_bundle(receipt, root, manifest)
    record = reader.records[0]
    payload = root / record.path
    external = tmp_path / "external.json"
    external.write_bytes(payload.read_bytes())
    payload.unlink()
    try:
        payload.symlink_to(external)
    except OSError as error:
        # Windows without Developer Mode or SeCreateSymbolicLinkPrivilege still
        # exercises the real reparse-point refusal with the junction above.
        assert os.name == "nt" and error.winerror == 1314
    else:
        with pytest.raises(c.ContractError, match="symlink/reparse"):
            reader.read(record.artifact_id)
        payload.unlink()
    os.link(external, payload)
    with pytest.raises(c.ContractError, match="hard-link alias"):
        reader.read(record.artifact_id)


def test_adversarial_publish_copies_verified_source_and_cleans_owned_failure(source, tmp_path):
    context, _, inputs = source
    receipt = preflight(context, inputs)
    target = tmp_path / "target"
    with pytest.raises(c.ContractError, match="overlaps"):
        phase.materialize_phase_inputs(
            receipt, context.root / "target", role="train", expected_preflight_sha256=receipt.sha256
        )
    with pytest.raises(c.ContractError, match="unsafe phase destination"):
        phase.materialize_phase_inputs(
            receipt, tmp_path / ".." / "outside", role="train", expected_preflight_sha256=receipt.sha256
        )
    path = context.root / "problem-train.json"
    raw = path.read_bytes()
    changed = raw.replace(b'"version": "1.0.0"', b'"version": "2.0.0"')
    assert raw != changed and len(raw) == len(changed)
    path.write_bytes(changed)
    with pytest.raises(c.ContractError, match="changed after preflight"):
        phase.materialize_phase_inputs(
            receipt, target, role="train", expected_preflight_sha256=receipt.sha256
        )
    assert not target.exists() and path.read_bytes() == changed


def test_adversarial_atomic_last_manifest_and_racing_destination(source, tmp_path, monkeypatch):
    context, _, inputs = source
    receipt = preflight(context, inputs)
    destination = tmp_path / "race"
    reserved = threading.Event()
    release = threading.Event()
    original = os.link

    def pause_manifest(origin, target):
        reserved.set()
        assert release.wait(timeout=15)
        return original(origin, target)

    monkeypatch.setattr(os, "link", pause_manifest)
    kwargs = {"role": "train", "expected_preflight_sha256": receipt.sha256}
    with ThreadPoolExecutor(max_workers=1) as executor:
        first = executor.submit(phase.materialize_phase_inputs, receipt, destination, **kwargs)
        try:
            assert reserved.wait(timeout=15)
            assert not (destination / "phase-inputs.json").exists()
            with pytest.raises(c.ContractError, match="manifest unavailable"):
                open_bundle(receipt, destination, "0" * 64)
            with pytest.raises(c.ContractError, match="exists or is a case alias"):
                phase.materialize_phase_inputs(receipt, destination, **kwargs)
        finally:
            release.set()
        manifest = first.result(timeout=15)
    reader = open_bundle(receipt, destination, manifest)
    assert len(list(destination.iterdir())) == len(reader.records) + 1
    assert reader.read("problem-train").state == "provider"


def test_adversarial_concurrent_reservation_has_one_winner(source, tmp_path, monkeypatch):
    context, _, inputs = source
    receipt = preflight(context, inputs)
    destination = tmp_path / "same-unreserved-target"
    original = Path.mkdir
    start = threading.Barrier(2)

    def align_reservations(path, *args, **kwargs):
        if path == destination:
            start.wait(timeout=15)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", align_reservations)

    def publish():
        try:
            return phase.materialize_phase_inputs(
                receipt, destination, role="train", expected_preflight_sha256=receipt.sha256
            )
        except c.ContractError as error:
            assert "destination already reserved" in str(error)
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: publish(), range(2)))
    (winner,) = tuple(value for value in results if value is not None)
    reader = open_bundle(receipt, destination, winner)
    assert len(reader.records) == 4
    assert reader.read("labels").payload["status"] == "accepted"


def test_adversarial_r4_key_projection_excludes_ineligible_graphs_and_rejects_a_dropped_frame(fixture_source):
    # Accepted design metadata only. This creates no scientific input or solver output.
    context, _, _ = fixture_source

    class ProductionPolicy:
        authority = context.authority
        allow_fixture = False

    sources = {}
    for row in context.authority.matrix["rows"]:
        family, regime = row["case_id"], row["regime"]
        for role, size in context.authority.matrix["split_units"].items():
            for unit in range(size):
                for frame in range(32 if family == "N12" else 1):
                    identifier = f"{family}-{regime}-{role}-{unit}-{frame}"
                    sources[identifier] = (
                        {
                            "family": family,
                            "regime": regime,
                            "split": role,
                            "unit_index": unit,
                            "frame": frame,
                        },
                        None,
                    )
    keys = phase._population_keys(ProductionPolicy(), sources)
    assert len(sources) == 15456
    assert sum(key[2] == "mlp-v1" for key in keys) == 15456
    assert sum(key[2] == "graph-v1" for key in keys) == 14504
    assert sum(key[2] == "cold_daqp" for key in keys) == 14504
    identifier, _, _ = next(key for key in keys if key[2] == "cold_daqp" and key[0].startswith("N12"))
    del sources[identifier]
    with pytest.raises(c.ContractError, match="label population differs"):
        phase._population_keys(ProductionPolicy(), sources)


def test_adversarial_foreign_transient_manifest_file_is_refused(source, tmp_path):
    receipt, target, manifest = make_bundle(source, tmp_path)
    final = target / "phase-inputs.json"
    temporary = target / ".unpublished-manifest"
    temporary.write_bytes(final.read_bytes())
    with pytest.raises(c.ContractError, match="foreign file masquerades"):
        open_bundle(receipt, target, manifest)
    temporary.unlink()
    os.link(final, temporary)
    assert open_bundle(receipt, target, manifest).read("problem-train").state == "provider"


def test_adversarial_receipt_path_policy_cannot_be_rebound(source, tmp_path, monkeypatch):
    context, _, inputs = source
    protected = tmp_path / "protected"
    protected.mkdir()
    context = replace(context, forbidden_roots=(*context.forbidden_roots, protected))
    receipt = preflight(context, inputs)
    relocated = tmp_path / "relocated"
    shutil.copytree(context.root, relocated)

    def forbidden_io(*_args, **_kwargs):
        pytest.fail("rebinding must fail before publication file I/O")

    monkeypatch.setattr(Path, "open", forbidden_io)
    for forged, destination in (
        (replace(receipt, source_root=relocated), tmp_path / "forged-source"),
        (replace(receipt, forbidden_roots=()), protected / "forged-protected-root"),
    ):
        assert forged.sha256 == receipt.sha256
        with pytest.raises(c.ContractError, match="path policy differs"):
            phase.materialize_phase_inputs(
                forged, destination, role="train", expected_preflight_sha256=receipt.sha256
            )
        assert not destination.exists()
