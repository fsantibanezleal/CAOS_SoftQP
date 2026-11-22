"""Actual factored v2 writers, preflight and role readers using software controls."""

from collections import Counter
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import shutil
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import stream_inputs as s
from test_learned_contracts import PROVIDER


def put(context, protocol, kind, name, payload, **kwargs):
    candidate = s.stream_document(kind, name, payload, context, protocol)
    artifact = s.write_stream_artifact(candidate, name + ".json", context, **kwargs)
    ref = dict(kind=kind, artifact_id=name, path=name + ".json", sha256=artifact.raw_sha256)
    return replace(context, catalog={**context.catalog, name: ref}), ref


def build_factored(context, protocol, known):
    context = replace(
        context,
        problem_hashes={
            **context.problem_hashes,
            **{name: p["original_sha256"] for name, p in known.items()},
        },
        source_records={
            **context.source_records,
            **{name: c.digest(c.canonical_bytes(p["source"])) for name, p in known.items()},
        },
        fit_source_ids=tuple(
            sorted({p["source"]["source_id"] for p in known.values() if p["source"]["split"] == "train"})
        ),
    )
    sources = {}
    frames = {}
    for name, problem in sorted(known.items()):
        identifier = problem["source"]["source_id"]
        if identifier not in sources:
            source = s.factor_source(problem)
            context, sources[identifier] = put(context, protocol, s.SOURCE, "factor-" + identifier, source)
        context, frames[name] = put(
            context, protocol, s.FRAME, name, s.factor_frame(problem, sources[identifier])
        )
    return context, sorted(sources.values(), key=lambda ref: ref["artifact_id"]), frames


@pytest.fixture(scope="module")
def source_bundle(tmp_path_factory):
    context, docs, refs = PROVIDER["build"](tmp_path_factory.mktemp("stream-source"))
    known = {}
    for idx in range(32):
        problem = PROVIDER["problem_payload"](
            "train", idx * 1.5, control="contract-fixture:stream-trajectory", family="N12"
        )
        problem["source"].update(frame=idx, source_id="trajectory-train", parent_id="trajectory-parent")
        known[f"trajectory-{idx:02d}"] = problem
    known["single-train"] = PROVIDER["problem_payload"]("train", 0.5)
    for role in ("validation", "calibration", "test"):
        known[f"single-{role}"] = docs[f"problem-{role}"]["payload"]
    protocol = refs["protocol"]
    context, sources, frames = build_factored(context, protocol, known)
    scope = {
        "sources": sources,
        "frames": list(frames.values()),
        "exclusions": sorted(docs["dataset"]["payload"]["exclusions"]),
        "fit_source_ids": list(context.fit_source_ids),
        "attribution": "Software controls adapted from the admitted fixture protocol",
        "license": "MIT",
    }
    labels = [
        {"frame_id": name, "ref": None, "state": "missing", "reason": "fixture labels unavailable"}
        for name in frames
    ]
    name = "trajectory-00"
    source_scope = s.population_identity(protocol, **scope)
    payload = deepcopy(docs["labels"]["payload"])
    for key in ("problem", "split"):
        del payload[key]
    # A small negative native side value must survive, even though the old
    # derived-label formula would have clipped it.
    transform = known[name]["transform"]
    graph = c.graph_coordinates(transform)[0]
    side = next(i for i, point in enumerate(graph["row_map"]) if point["canonical_row"] == 0)
    mapping = graph["row_map"][side]
    raw_side = -(2**-28)
    payload["multipliers"][2 + side] = raw_side
    lifted = payload["cold_candidate"]["lifted_y"]
    lifted[0] = mapping["sign"] * raw_side
    original_dual = [0]
    for item in transform["row_dual_map"]:
        original_dual[item["original_row"]] += item["coefficient"] * lifted[item["canonical_row"]]
    payload["cold_candidate"]["y"] = original_dual
    evidence = {
        "producer_source_sha256": context.producer_source_sha256,
        "settings_sha256": payload["settings_sha256"],
        "input_sha256": known[name]["original_sha256"],
        "native_flag": payload["cold_native_flag"],
        "raw_primal": payload["cold_candidate"]["lifted_x"],
        "raw_side_duals": payload["multipliers"][2:],
    }
    evidence["sha256"] = c.digest(c.canonical_bytes(evidence))
    payload.update(frame=frames[name], population_sha256=source_scope, native_evidence=evidence)
    context, label_ref = put(
        context, protocol, s.LABELS, "trajectory-label", payload, expected_population_sha256=source_scope
    )
    label = next(row for row in labels if row["frame_id"] == name)
    label.update(ref=label_ref, state="provider", reason=None)
    descriptor = s.derive_stream_payload(context, protocol, **scope, labels=labels)
    context, ref = put(context, protocol, s.STREAM, "feature-stream", descriptor)
    return context, docs, refs, known, descriptor, ref, protocol


@pytest.fixture
def bundle(source_bundle, tmp_path):
    context, *values = source_bundle
    root = tmp_path / "global"
    shutil.copytree(context.root, root)
    return replace(context, root=root), *values


def admit(bundle):
    context, _, _, _, _, ref, _ = bundle
    return s.preflight_stream(
        context, descriptor_id=ref["artifact_id"], expected_descriptor_sha256=ref["sha256"]
    )


def phase_reader(receipt, root, role):
    digest = s.materialize_stream_phase(receipt, root, role=role, expected_preflight_sha256=receipt.sha256)
    reader = s.StreamingPhaseReader(
        root,
        role=role,
        expected_manifest_sha256=digest,
        expected_preflight_sha256=receipt.sha256,
        allow_fixture=True,
    )
    return reader, digest


def test_adversarial_factored_frame_legacy_parity_and_parent_tamper(bundle, tmp_path):
    context, _, _, known, descriptor, _, protocol = bundle
    frame_ref = next(ref for ref in descriptor["frames"] if ref["artifact_id"] == "trajectory-07")
    source_ref = s.read_stream_artifact(
        context.root / frame_ref["path"], context, expected_sha256=frame_ref["sha256"]
    ).payload["source_ref"]
    receipt = admit(bundle)
    reader, _ = phase_reader(receipt, tmp_path / "train", "train")
    for idx in range(32):
        key = f"trajectory-{idx:02d}"
        assert c.canonical_bytes(reader.read_problem(key)) == c.canonical_bytes(known[key])
    src_raw = (context.root / source_ref["path"]).read_bytes()
    static_doc = c.strict_loads(src_raw)
    for key in ("q", "lower", "upper"):
        assert key not in static_doc["payload"]["original_static"]
    assert sum(ref["artifact_id"] == source_ref["artifact_id"] for ref in descriptor["sources"]) == 1
    alt_ref = next(
        ref for ref in descriptor["sources"] if ref["artifact_id"].endswith("fixture-source-validation")
    )
    forged = s.factor_frame(known[frame_ref["artifact_id"]], alt_ref)
    doc = s.stream_document(s.FRAME, frame_ref["artifact_id"], forged, context, protocol)
    with pytest.raises(c.ContractError, match="source slot"):
        s.write_stream_artifact(doc, "refused.json", context)
    assert not (context.root / "refused.json").exists()
    for ref in (source_ref, frame_ref):
        local = next(row["path"] for row in reader._records.values() if row["ref"] == ref)
        path = tmp_path / "train" / local
        original = path.read_bytes()
        changed = original.replace(b'"2.0.0"', b'"2.0.1"')
        assert changed != original and len(changed) == len(original)
        path.write_bytes(changed)
        with pytest.raises(c.ContractError, match="stored byte mismatch"):
            reader.read_feature("trajectory-07", "mlp-v1")
        path.write_bytes(original)


def test_adversarial_complete_logical_domain_and_exact_streamed_statistics(bundle, tmp_path):
    context, _, _, known, descriptor, ref, protocol = bundle
    receipt = admit(bundle)
    reader, _ = phase_reader(receipt, tmp_path / "train", "train")
    normalizer = descriptor["normalizers"][0]
    assert len(descriptor["features"]) == 2 * len(known) == 72
    assert len(descriptor["labels"]) == len(known) == 36
    assert len(reader.logical_keys) == 66
    by_frame = sorted((key, p) for key, p in known.items() if p["source"]["split"] == "train")
    weights = [0.5 if key == "single-train" else 1 / 64 for key, _ in by_frame]
    assert weights == normalizer["source_weights"]
    raw_matrix = [c.mlp_coordinates(p["transform"])[1] for _, p in by_frame]
    independent_mean = [sum(w * x for w, x in zip(weights, col)) for col in zip(*raw_matrix)]
    independent_scale = [
        sum(w * (x - mean) ** 2 for w, x in zip(weights, col)) ** 0.5 or 1
        for col, mean in zip(zip(*raw_matrix), independent_mean)
    ]
    assert c.canonical_bytes(independent_mean) == c.canonical_bytes(normalizer["mean"])
    assert c.canonical_bytes(independent_scale) == c.canonical_bytes(normalizer["scale"])
    for key, problem in by_frame:
        vals = reader.read_feature(key, "mlp-v1").document
        names, expected = c.mlp_coordinates(problem["transform"])
        assert vals["coordinate_order"] == names and vals["raw_values"] == expected
        assert vals["values"] == [
            (x - m) / scale for x, m, scale in zip(expected, independent_mean, independent_scale)
        ]
        assert (
            reader.read_feature(key, "graph-v1").document["graph"]
            == c.graph_coordinates(problem["transform"])[0]
        )
    label = reader.read_label("trajectory-00")
    assert label["state"] == "provider"
    assert min(label["payload"]["multipliers"]) == -(2**-28)
    assert min(label["payload"]["native_evidence"]["raw_side_duals"]) == -(2**-28)
    assert reader.read_label("trajectory-01")["payload"] is None

    # A local producer cannot authorize a reduced or forged logical inventory.
    for mutation in ("feature-drop", "feature-hash", "label-drop", "normalizer"):
        bad = deepcopy(descriptor)
        if mutation == "feature-drop":
            bad["features"].pop()
        elif mutation == "feature-hash":
            bad["features"][0]["logical_sha256"] = "f" * 64
        elif mutation == "label-drop":
            bad["labels"].pop()
        else:
            bad["normalizers"][0]["mean"][0] += 1
        candidate = s.stream_document(s.STREAM, ref["artifact_id"], bad, context, protocol)
        with pytest.raises(c.ContractError):
            s.write_stream_artifact(candidate, mutation + ".json", context)


def test_adversarial_streamed_role_opens_and_publication(bundle, tmp_path, monkeypatch):
    context, _, _, _, descriptor, _, _ = bundle
    receipt = admit(bundle)
    roots = {role: tmp_path / role for role in ("train", "validation", "calibration")}
    digests = {
        role: s.materialize_stream_phase(receipt, root, role=role, expected_preflight_sha256=receipt.sha256)
        for role, root in roots.items()
    }
    with pytest.raises(c.ContractError, match="already exists"):
        s.materialize_stream_phase(
            receipt, roots["train"], role="train", expected_preflight_sha256=receipt.sha256
        )
    with pytest.raises(c.ContractError, match="unsupported phase role"):
        s.materialize_stream_phase(
            receipt, tmp_path / "test", role="test", expected_preflight_sha256=receipt.sha256
        )
    assert not (tmp_path / "test").exists()
    # Align two fully checked callers at the actual reservation syscall.
    raced = tmp_path / "racing-role"
    mkdir = Path.mkdir
    start = threading.Barrier(2)

    def aligned(path, *args, **kwargs):
        if path == raced:
            start.wait(timeout=10)
        return mkdir(path, *args, **kwargs)

    def competing():
        try:
            return s.materialize_stream_phase(
                receipt, raced, role="train", expected_preflight_sha256=receipt.sha256
            )
        except c.ContractError as error:
            assert "already reserved" in str(error)
            return None

    with monkeypatch.context() as patch:
        patch.setattr(Path, "mkdir", aligned)
        with ThreadPoolExecutor(max_workers=2) as workers:
            winners = tuple(result for result in workers.map(lambda _: competing(), range(2)) if result)
    assert winners == (digests["train"],)
    shutil.rmtree(context.root)
    real_open = Path.open
    opened = Counter()

    def observed(path, *args, **kwargs):
        if kwargs.get("mode", args[0] if args else "r") == "rb":
            opened[path] += 1
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", observed)
    for role, root in roots.items():
        opened.clear()
        params = dict(
            role=role,
            expected_manifest_sha256=digests[role],
            expected_preflight_sha256=receipt.sha256,
            allow_fixture=True,
        )
        reader = s.StreamingPhaseReader(root, **params)
        frame = "trajectory-00" if role == "train" else "single-" + role
        reader.read_feature(frame, "graph-v1")
        assert len(opened) == 3 and sum(opened.values()) == 3
        assert all(path.parent == root for path in opened)
        assert len(list(root.iterdir())) == len(reader._records) + 1
        assert not any((root / row["path"]).stat().st_size == 0 for row in reader._records.values())
        assert set(reader.logical_keys) <= {
            (item["frame_id"], item["representation"]) for item in descriptor["features"]
        }
        with pytest.raises(c.ContractError, match="absent from stream role"):
            reader.read_feature("single-test", "mlp-v1")
        with pytest.raises(c.ContractError, match="unsupported phase role"):
            s.StreamingPhaseReader(root, **{**params, "role": "test"})
        assert len(opened) == 3
        hidden = root / ".unpublished-manifest"
        hidden.write_bytes(b"foreign data")
        with pytest.raises(c.ContractError, match="foreign file"):
            s.StreamingPhaseReader(root, **params)
        hidden.unlink()
        frame_record = reader._records[frame]
        frame_doc = c.strict_loads((root / frame_record["path"]).read_bytes())
        source = reader._records[frame_doc["payload"]["source_ref"]["artifact_id"]]["path"]
        (root / source).unlink()
        with pytest.raises(c.ContractError, match="input unavailable"):
            reader.read_feature(frame, "mlp-v1")


def test_adversarial_checkpoint_binds_stream_and_phase_selection(bundle, tmp_path):
    context, docs, refs, _, descriptor, ref, protocol = bundle
    receipt = admit(bundle)
    train, train_sha = phase_reader(receipt, tmp_path / "train", "train")
    validation, val_sha = phase_reader(receipt, tmp_path / "validation", "validation")
    legacy_context = replace(context, fit_source_ids=("fixture-source-train",))
    old = c.read_artifact(
        context.root / refs["checkpoint"]["path"],
        legacy_context,
        expected_sha256=refs["checkpoint"]["sha256"],
    )
    assert old.raw == c.json_bytes(docs["checkpoint"])
    payload = deepcopy(old.payload)
    for key in ("dataset", "split", "features"):
        del payload[key]
    payload.update(
        feature_stream=ref,
        population_sha256=descriptor["population_sha256"],
        preflight_sha256=receipt.sha256,
        phase_manifest_sha256={"train": train_sha, "validation": val_sha},
        normalizer_sha256=[descriptor["normalizers"][0]["sha256"]],
    )
    candidate = s.stream_document(s.CHECKPOINT, "v2-checkpoint", payload, context, protocol)
    # Phase trust carries descriptor and protocol checks. Those files are
    # absent during checkpoint admission; neither reads their ancestor graph.
    (context.root / ref["path"]).unlink()
    (context.root / protocol["path"]).unlink()
    output = context.root / "stream-checkpoint.json"
    result = s.write_stream_artifact(candidate, output.name, context, train=train, validation=validation)
    got = s.read_stream_artifact(
        output, context, expected_sha256=result.raw_sha256, train=train, validation=validation
    )
    assert got.payload == payload
    with pytest.raises(c.ContractError, match="requires independent"):
        s.read_stream_artifact(
            output, context, expected_sha256=result.raw_sha256, train=validation, validation=train
        )
    for prefix, changed, match in (
        ("phase", {"phase_manifest_sha256": {"train": "0" * 64, "validation": val_sha}}, "phase selection"),
        ("descriptor", {"feature_stream": {**ref, "sha256": "0" * 64}}, "descriptor/population"),
    ):
        bad = s.stream_document(s.CHECKPOINT, prefix, {**payload, **changed}, context, protocol)
        with pytest.raises(c.ContractError, match=match):
            s.write_stream_artifact(bad, prefix + ".json", context, train=train, validation=validation)
    weights = context.root / payload["weights"]["path"]
    raw = weights.read_bytes()
    weights.write_bytes(b"\x01" + raw[1:])
    with pytest.raises(c.ContractError, match="stale numeric"):
        s.read_stream_artifact(
            output, context, expected_sha256=result.raw_sha256, train=train, validation=validation
        )


def test_adversarial_all_fourteen_heads_compute_actual_logical_values(source_bundle, tmp_path):
    context, docs, _, _, _, _, protocol = source_bundle
    root = tmp_path / "heads"
    shutil.copytree(context.root, root)
    context = replace(context, root=root)
    heads = context.authority.matrix["heads"]
    families = [f"N{index:02d}" for index in range(1, 16) if index != 12]
    known = {}
    for index, (head, family) in enumerate(zip(heads, families, strict=True)):
        n_lift, m_lift = head["n"], head["m"]
        n, soft, hard = next(
            (n, n_lift - n, m_lift - 3 * (n_lift - n))
            for n in range(1, min(66, n_lift) + 1)
            if 0 <= m_lift - 3 * (n_lift - n) and (n_lift - n) + m_lift - 3 * (n_lift - n) <= 98
        )
        m = soft + hard
        original = deepcopy(docs["problem-train"]["payload"]["original"])
        original.update(
            n=n,
            m=m,
            P=c.csc([[int(i == j) for j in range(n)] for i in range(n)]),
            A=c.csc([[int(i % n == j) for j in range(n)] for i in range(m)]),
            q=[index / 4] + [0] * (n - 1),
            lower=[0] * m,
            upper=[1] * m,
            lower_finite=[True] * m,
            upper_finite=[True] * m,
        )
        original["penalty"] = {
            key: [True] * soft + [False] * hard if key == "soft" else [1] * soft + [0] * hard
            for key in original["penalty"]
        }
        original["units"].update(
            variable=["dimensionless"] * n, row=["dimensionless"] * m, D_x=[1] * n, D_r=[1] * m
        )
        problem = PROVIDER["problem_payload"](
            "train", original=original, family=family, control="contract-fixture:stream-head"
        )
        assert (problem["transform"]["n"], problem["transform"]["m"]) == (n_lift, m_lift)
        key = f"head-fixture-{index:02d}"
        problem["source"].update(source_id=key, parent_id="parent-" + key)
        known[key] = problem
    context, sources, frames = build_factored(context, protocol, known)
    labels = [
        {"frame_id": key, "ref": None, "state": "missing", "reason": "fixture label unavailable"}
        for key in frames
    ]
    descriptor = s.derive_stream_payload(
        context,
        protocol,
        sources=sources,
        frames=frames.values(),
        fit_source_ids=context.fit_source_ids,
        exclusions=sorted(docs["dataset"]["payload"]["exclusions"]),
        labels=labels,
        attribution="Independently dimensioned fixture matrices for every head",
        license="MIT",
    )
    assert [row["head_id"] for row in descriptor["normalizers"]] == sorted(h["id"] for h in heads)
    assert len(descriptor["features"]) == 28
    for row in descriptor["normalizers"]:
        assert all(value == 1 for value in row["scale"])
        assert row["source_weights"] == [1]
    context, ref = put(context, protocol, s.STREAM, "all-head-stream", descriptor)
    receipt = s.preflight_stream(
        context, descriptor_id=ref["artifact_id"], expected_descriptor_sha256=ref["sha256"]
    )
    reader, _ = phase_reader(receipt, tmp_path / "heads-train", "train")
    for name, problem in known.items():
        feature = reader.read_feature(name, "mlp-v1").document
        assert feature["raw_values"] == c.mlp_coordinates(problem["transform"])[1]
        assert all(value == 0 for value in feature["values"])
        assert (
            reader.read_feature(name, "graph-v1").document["graph"]
            == c.graph_coordinates(problem["transform"])[0]
        )


def test_adversarial_stream_frames_forbid_finite_mask_and_equality_drift(bundle):
    context, _, _, known, descriptor, _, protocol = bundle
    existing = next(ref for ref in descriptor["frames"] if ref["artifact_id"] == "trajectory-07")
    frame = s.read_stream_artifact(
        context.root / existing["path"], context, expected_sha256=existing["sha256"]
    ).payload
    malformed = s.stream_document(
        s.FRAME,
        "trajectory-07",
        {**frame, "vectors": {**frame["vectors"], "lower": [None]}},
        context,
        protocol,
    )
    with pytest.raises(c.ContractError, match="finite-mask drift"):
        s.write_stream_artifact(malformed, "mask-drift.json", context)
    established = known["trajectory-07"]
    original = {**established["original"], "upper": [0]}
    problem = {**established, "original": original}
    problem["original_sha256"] = c.digest(c.canonical_bytes(original))
    problem["transform"] = c.canonical_transform(original)
    problem["transform_sha256"] = c.digest(c.canonical_bytes(problem["transform"]))
    problem["source"] = {**problem["source"], "input_sha256": problem["original_sha256"]}
    ctx = replace(
        context,
        problem_hashes={**context.problem_hashes, "trajectory-07": problem["original_sha256"]},
        source_records={
            **context.source_records,
            "trajectory-07": c.digest(c.canonical_bytes(problem["source"])),
        },
    )
    candidate = s.stream_document(
        s.FRAME, "trajectory-07", s.factor_frame(problem, frame["source_ref"]), ctx, protocol
    )
    newly_written = s.write_stream_artifact(candidate, "changed-equality.json", ctx)
    new_ref = {**existing, "path": "changed-equality.json", "sha256": newly_written.raw_sha256}
    ctx = replace(ctx, catalog={**ctx.catalog, "trajectory-07": new_ref})
    frames = [new_ref if ref == existing else ref for ref in descriptor["frames"]]
    with pytest.raises(c.ContractError, match="trajectory coefficient/equality/layout drift"):
        s.derive_stream_payload(
            ctx,
            protocol,
            sources=descriptor["sources"],
            frames=frames,
            exclusions=descriptor["exclusions"],
            fit_source_ids=descriptor["fit_source_ids"],
            labels=descriptor["labels"],
            attribution=descriptor["attribution"],
            license=descriptor["license"],
        )


def test_adversarial_raw_label_scatter_refuses_clipping_and_attestation_substitution(bundle):
    context, _, _, _, descriptor, _, protocol = bundle
    label = next(row for row in descriptor["labels"] if row["state"] == "provider")
    raw = (context.root / label["ref"]["path"]).read_bytes()
    artifact = s.read_stream_artifact(
        context.root / label["ref"]["path"],
        context,
        expected_sha256=label["ref"]["sha256"],
        expected_population_sha256=descriptor["population_sha256"],
    )
    assert artifact.raw == raw
    for attack in ("clip", "forge-source"):
        payload = artifact.payload
        evidence = payload["native_evidence"]
        if attack == "clip":
            evidence["raw_side_duals"] = [max(value, 0) for value in evidence["raw_side_duals"]]
        else:
            evidence["producer_source_sha256"] = "f" * 64
        _ = evidence.pop("sha256")
        evidence["sha256"] = c.digest(c.canonical_bytes(evidence))
        candidate = s.stream_document(s.LABELS, attack, payload, context, protocol)
        with pytest.raises(c.ContractError, match="raw DAQP"):
            s.write_stream_artifact(
                candidate,
                attack + ".json",
                context,
                expected_population_sha256=descriptor["population_sha256"],
            )


def test_adversarial_versioned_dense_ldl_accepts_exact_pivots_and_refuses_oversize(bundle):
    import random
    import sys

    context, docs, _, _, _, _, protocol = bundle
    rng = random.Random(17)
    dense = [[0.0] * 32 for _ in range(32)]
    for i in range(32):
        dense[i][i] = 32 + rng.random()
        for j in range(i):
            dense[i][j] = dense[j][i] = rng.random() - 0.5
    original = deepcopy(docs["problem-train"]["payload"]["original"])
    original.update(n=32, P=c.csc(dense), A=c.csc([[1] + [0] * 31]), q=[0] * 32)
    original["units"].update(D_x=[1] * 32, variable=["dimensionless"] * 32)
    problem = PROVIDER["problem_payload"](original=original, control="contract-fixture:dense-ldl32")
    pivots = problem["curvature"]["pivots"]
    assert len(pivots) == 32 and max(map(len, pivots)) > 1000
    candidate = s.factor_source(problem)
    context, ref = put(context, protocol, s.SOURCE, "dense-ldl-source", candidate)
    accepted = s.read_stream_artifact(context.root / ref["path"], context, expected_sha256=ref["sha256"])
    assert accepted.payload["curvature"]["pivots"] == pivots
    frame_name = "dense-ldl-frame"
    context = replace(
        context,
        problem_hashes={**context.problem_hashes, frame_name: problem["original_sha256"]},
        source_records={**context.source_records, frame_name: c.digest(c.canonical_bytes(problem["source"]))},
    )
    context, frame_ref = put(context, protocol, s.FRAME, frame_name, s.factor_frame(problem, ref))
    assert (
        s.read_stream_artifact(
            context.root / frame_ref["path"], context, expected_sha256=frame_ref["sha256"]
        ).payload["original_sha256"]
        == problem["original_sha256"]
    )

    for attack, text, reason in (
        ("oversize", "1" * 84001, "schema"),
        ("order-bound", "1" * (s._pivot_character_bound(1) + 1), "binary64 bound"),
        ("malformed", "2/-3", "schema"),
        ("wrong-value", "2", "exact LDL receipt"),
    ):
        bad = deepcopy(candidate)
        bad["curvature"]["pivots"][0] = text
        doc = s.stream_document(s.SOURCE, attack, bad, context, protocol)
        with pytest.raises(c.ContractError, match=reason):
            s.write_stream_artifact(doc, attack + ".json", context)

    cap = sys.get_int_max_str_digits()
    subnormal = 2**-1074
    tridiagonal = [
        [1 if i == j else subnormal if abs(i - j) == 1 else 0 for j in range(10)] for i in range(10)
    ]
    rank, extreme = c.exact_curvature(tridiagonal)
    assert rank == 10 and max(map(len, extreme)) > 4300
    assert sys.get_int_max_str_digits() == cap


def test_adversarial_stream_requires_real_frame_and_dataset_provenance_and_fresh_publication(
    bundle, monkeypatch
):
    context, _, _, _, descriptor, _, protocol = bundle
    candidate = s.stream_document(
        s.STREAM, "missing-license", {**descriptor, "license": " "}, context, protocol
    )
    with pytest.raises(c.ContractError, match="unresolved source license"):
        s.write_stream_artifact(candidate, "missing-license.json", context)
    frame_ref = next(ref for ref in descriptor["frames"] if ref["artifact_id"] == "trajectory-00")
    origin = context.root / frame_ref["path"]
    original = s.read_stream_artifact(origin, context, expected_sha256=frame_ref["sha256"]).payload
    unlicensed = deepcopy(original)
    unlicensed["source"]["attribution"] = " "
    ctx = replace(
        context,
        source_records={
            **context.source_records,
            frame_ref["artifact_id"]: c.digest(c.canonical_bytes(unlicensed["source"])),
        },
    )
    forged = s.stream_document(s.FRAME, frame_ref["artifact_id"], unlicensed, ctx, protocol)
    with pytest.raises(c.ContractError, match="unresolved stream frame"):
        s.write_stream_artifact(forged, "missing-attribution.json", ctx)
    assert not (context.root / "missing-attribution.json").exists()

    source_path = context.root / original["source_ref"]["path"]
    raw = source_path.read_bytes()
    changed = raw.replace(b'"version":"2.0.0"', b'"version":"2.0.1"')
    assert len(changed) == len(raw) and changed != raw
    link = s.os.link

    def publish_then_change_input(staging, target):
        link(staging, target)
        source_path.write_bytes(changed)

    monkeypatch.setattr(s.os, "link", publish_then_change_input)
    replication = s.stream_document(s.FRAME, frame_ref["artifact_id"], original, context, protocol)
    with pytest.raises(c.ContractError, match="stored byte hash mismatch"):
        s.write_stream_artifact(replication, "fresh-check-refuses.json", context)
    assert not (context.root / "fresh-check-refuses.json").exists()
    assert not list(context.root.glob(".stream-*"))
    assert source_path.read_bytes() == changed


def test_adversarial_inconsistent_source_shape_refuses_before_dense_factorization(bundle, monkeypatch):
    context, _, _, _, descriptor, _, protocol = bundle
    source = deepcopy(s.factor_source(bundle[3]["trajectory-00"]))
    source["original_static"]["P"]["shape"] = [128, 128]
    document = s.stream_document(s.SOURCE, "invalid-shape", source, context, protocol)

    def tracked(_matrix):
        pytest.fail("inconsistent original shape reached dense factorization")

    monkeypatch.setattr(c, "exact_curvature", tracked)
    with pytest.raises(c.ContractError, match="stream source matrix shape"):
        s.write_stream_artifact(document, "invalid-shape.json", context)

    raw = c.canonical_bytes(document)
    path = context.root / "invalid-shape-stored.json"
    path.write_bytes(raw)
    wrong_source = dict(kind=s.SOURCE, artifact_id="invalid-shape", path=path.name, sha256=c.digest(raw))
    context = replace(context, catalog={**context.catalog, "invalid-shape": wrong_source})
    frame = next(ref for ref in descriptor["frames"] if ref["artifact_id"] == "trajectory-00")
    actual_frame = c.strict_loads((context.root / frame["path"]).read_bytes())["payload"]
    corrupt = s.stream_document(
        s.FRAME, "trajectory-00", {**actual_frame, "source_ref": wrong_source}, context, protocol
    )
    with pytest.raises(c.ContractError, match="stream source matrix shape"):
        s.write_stream_artifact(corrupt, "invalid-parent-shape.json", context)
