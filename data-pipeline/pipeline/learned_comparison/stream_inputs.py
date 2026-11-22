"""Versioned factored scientific inputs and role-local computed features."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Any, Literal, TypedDict

from jsonschema.exceptions import SchemaError, ValidationError

from . import contracts as c
from . import phase_inputs as phase

SOURCE = "learning-stream-source"
FRAME = "learning-stream-frame"
STREAM = "learning-feature-stream"
LABELS = "learning-stream-labels"
CHECKPOINT = "learning-stream-checkpoint"
KINDS = (SOURCE, FRAME, STREAM, LABELS, CHECKPOINT)
VERSION = "2.0.0"
_PRE = "softqp.stream-preflight/v2"
_PHASE = "softqp.stream-phase/v2"
_FEATURE = "softqp.logical-feature/v2"
_URL = "https://fsantibanezleal.github.io/CAOS_SoftQP/contracts/softqp-"
_VECTORS = ("q", "lower", "upper")
_SLOT = (
    "source_id",
    "parent_id",
    "family",
    "regime",
    "split",
    "unit_index",
    "frame_count",
)
_POLICY = ("generator_sha256", "curvature", "physical_calibration", "expected_control")


class StreamSource(TypedDict):
    slot: dict[str, Any]
    original_static: dict[str, Any]
    generator_sha256: str
    curvature: dict[str, Any]
    physical_calibration: dict[str, Any]
    expected_control: str | None


class StreamFrame(TypedDict):
    source_ref: c.Reference
    source: dict[str, Any]
    vectors: dict[str, Any]
    original_sha256: str
    transform_sha256: str


class LogicalKey(TypedDict):
    frame_id: str
    representation: str
    logical_sha256: str


class StreamLabelKey(TypedDict):
    frame_id: str
    ref: c.Reference | None
    state: str
    reason: str | None


class FeatureStream(TypedDict):
    sources: list[c.Reference]
    frames: list[c.Reference]
    exclusions: list[str]
    fit_source_ids: list[str]
    attribution: str
    license: str
    population_sha256: str
    normalizers: list[dict[str, Any]]
    features: list[LogicalKey]
    labels: list[StreamLabelKey]


class NativeLabelEvidence(TypedDict):
    producer_source_sha256: str
    settings_sha256: str
    input_sha256: str
    native_flag: int
    raw_primal: list[float]
    raw_side_duals: list[float]
    sha256: str


class StreamLabels(TypedDict):
    frame: c.Reference
    population_sha256: str
    oracle_results: list[dict[str, Any]]
    oracle_source_sha256: str
    settings_sha256: str
    status: str
    reason: str | None
    slack: list[float]
    multipliers: list[float]
    labels: list[int | None]
    mask: list[bool]
    node_kind: list[str]
    bound: list[float]
    tau_dual: float
    tau_tight: float
    fit_access: list[str]
    cold_candidate: dict[str, Any] | None
    cold_native_flag: int | None
    native_evidence: NativeLabelEvidence | None


class StreamCheckpoint(TypedDict):
    feature_stream: c.Reference
    population_sha256: str
    preflight_sha256: str
    phase_manifest_sha256: dict[str, str]
    method: str
    architecture: dict[str, Any]
    architecture_sha256: str
    seed: int
    epoch: dict[str, int]
    best_epoch: dict[str, int]
    normalizer_sha256: list[str]
    weights: dict[str, Any]
    initial_weights_sha256: str
    history: list[dict[str, Any]]
    optimizer: dict[str, Any]
    rng: dict[str, Any]
    training_evidence: str
    learning_policy_sha256: str
    class_statistics: dict[str, Any] | None
    role: Literal["initial", "latest", "best", "final"]
    initial_weights: dict[str, Any]
    best_weights: dict[str, Any]


@dataclass(frozen=True)
class LogicalFeature:
    frame_id: str
    representation: str
    raw: bytes
    logical_sha256: str

    @property
    def document(self):
        return c.strict_loads(self.raw)


def _digest(value):
    return c.digest(c.canonical_bytes(value))


def _slot(source):
    return {name: source[name] for name in _SLOT}


def factor_source(problem: c.ProblemPayload) -> StreamSource:
    return {
        "slot": _slot(problem["source"]),
        "original_static": {
            name: value for name, value in problem["original"].items() if name not in _VECTORS
        },
        **{name: problem[name] for name in _POLICY},
    }


def factor_frame(problem: c.ProblemPayload, source_ref: c.Reference) -> StreamFrame:
    return {
        "source_ref": source_ref,
        "source": problem["source"],
        "vectors": {name: problem["original"][name] for name in _VECTORS},
        "original_sha256": problem["original_sha256"],
        "transform_sha256": problem["transform_sha256"],
    }


def stream_document(kind, artifact_id, payload, context, protocol_ref):
    """Make a candidate document. The writer still independently validates it."""
    refs = c._references(payload) + [protocol_ref]
    document = {
        "schema_id": _URL + kind + "/" + VERSION,
        "version": VERSION,
        "kind": kind,
        "artifact_id": artifact_id,
        "purpose": "contract-fixture" if context.allow_fixture else "scientific",
        "state": "provider" if context.allow_fixture else "available",
        "reason": "contract fixture" if context.allow_fixture else None,
        "protocol_id": context.protocol_id,
        "protocol_sha256": context.protocol_sha256,
        "protocol_ref": protocol_ref,
        "source_lock_sha256": context.source_lock_sha256,
        "provenance": {
            "producer_source_sha256": context.producer_source_sha256,
            "registration_sha256": context.registration_sha256,
            "parent_ids": sorted({ref["artifact_id"] for ref in refs}),
        },
        "payload": payload,
    }
    document["content_sha256"] = c.content_digest(document)
    return document


def _schema(document, context):
    kind = document.get("kind")
    c.ensure(kind in KINDS, "unknown stream contract kind")
    path = c.SCHEMAS / ("softqp-" + kind + ".schema.json")
    try:
        c._validator(c._snapshot_bytes(path, context, schema=True)).validate(document)
    except (ValueError, TypeError, OSError, SchemaError, ValidationError) as error:
        raise c.ContractError("invalid stream schema") from error


def _document(document, context, protocol_ref=None):
    _schema(document, context)
    c.ensure(document["content_sha256"] == c.content_digest(document), "stream document content hash")
    for key in ("protocol_id", "protocol_sha256", "source_lock_sha256"):
        c.ensure(document[key] == getattr(context, key), "stream protocol/source relabel")
    fixture = document["purpose"] == "contract-fixture"
    c.ensure(
        (not fixture or context.allow_fixture)
        and (document["state"] == "provider") == fixture
        and (document["reason"] is not None) == fixture,
        "stream fixture/state policy",
    )
    provenance = document["provenance"]
    for key in ("registration_sha256", "producer_source_sha256"):
        c.ensure(provenance[key] == getattr(context, key), "stream source/registration relabel")
    refs = c._references(document["payload"]) + [document["protocol_ref"]]
    c.ensure(provenance["parent_ids"] == sorted({ref["artifact_id"] for ref in refs}), "stream parent list")
    if protocol_ref is not None:
        c.ensure(protocol_ref == document["protocol_ref"], "stream protocol ancestry")
    return document


def _sealed(context, ref, kind):
    c.ensure(ref["kind"] == kind, "wrong stream reference kind")
    c.ensure(context.catalog.get(ref["artifact_id"]) == ref, "stream reference not in sealed catalog")
    return phase._checked_ref(context, ref["artifact_id"], kind)


def _protocol(context, ref):
    _sealed(context, ref, "learning-protocol")
    document = phase._admit(phase._exact_directory(context.root), context, ref).document
    c.ensure(document["payload"] is not None, "missing stream protocol")
    c.ensure((document["purpose"] == "contract-fixture") == context.allow_fixture, "stream protocol lane")
    return document["payload"]


def _load(context, ref, kind, protocol_ref):
    _sealed(context, ref, kind)
    root = phase._exact_directory(context.root)
    # Use the existing call-local first-read snapshot after full exact-path checks.
    path = c.safe_path(root, ref["path"], must_exist=True)
    named = root.joinpath(*phase._path_parts(ref["path"]))
    c.ensure(path.parts == named.parts, "stream reference path case or identity alias")
    raw = c._snapshot_bytes(path, context)
    c.ensure(c.digest(raw) == ref["sha256"], "stream stored byte hash mismatch")
    document = _document(c.strict_loads(raw), context, protocol_ref)
    c.ensure(raw == c.canonical_bytes(document), "noncanonical stored stream bytes")
    c.ensure(
        (document["kind"], document["artifact_id"]) == (kind, ref["artifact_id"]), "stream file identity"
    )
    return document


def _pivot_character_bound(order):
    def determinant_bits(dimension):
        if dimension == 0:
            return 0
        return 2098 * dimension + (dimension * (dimension - 1).bit_length() + 1) // 2

    numerator = determinant_bits(order)
    denominator = 1074 + determinant_bits(order - 1)
    return (302 * numerator + 999) // 1000 + (302 * denominator + 999) // 1000 + 1


def _matrix_shape(static):
    c.ensure(1 <= static["n"] <= 66 and 0 <= static["m"] <= 98, "stream source dimension")
    c.ensure(
        static["P"]["shape"] == [static["n"]] * 2 and static["A"]["shape"] == [static["m"], static["n"]],
        "stream source matrix shape",
    )


def _source(payload, context):
    slot = payload["slot"]
    static = payload["original_static"]
    c.ensure(payload["generator_sha256"] == context.generator_sha256, "stream source generator identity")
    c.ensure(slot["frame_count"] == (32 if slot["family"] == "N12" else 1), "stream source frame count")
    c.ensure(slot["unit_index"] < (32 if slot["split"] == "train" else 8), "stream source unit index")
    _matrix_shape(static)
    certificate = payload["curvature"]
    c.ensure(
        len(certificate["pivots"]) <= static["n"]
        and all(
            len(text) <= _pivot_character_bound(index) for index, text in enumerate(certificate["pivots"], 1)
        ),
        "stream source LDL certificate exceeds exact binary64 bound",
    )
    base_p = c.dense(static["P"])
    rank, pivots = c.exact_curvature(base_p)
    c.dense(static["A"])
    c.ensure(certificate["rank"] == rank, "stream source exact curvature")
    if certificate["kind"] == "exact-rational-LDL":
        c.ensure(
            rank == static["n"] and certificate["pivots"] == pivots and not certificate["diagonal_support"],
            "stream source exact LDL receipt",
        )
    else:
        c.ensure(
            all(i == j or value == 0 for i, row in enumerate(base_p) for j, value in enumerate(row))
            and certificate["diagonal_support"] == [i for i, row in enumerate(base_p) if row[i] > 0]
            and not certificate["pivots"],
            "stream source exact diagonal receipt",
        )
    c.ensure(
        payload["physical_calibration"]["calibration_sha256"] == _digest(static["units"]),
        "stream source unit identity",
    )


def _reconstruct(source, frame):
    c.ensure(_slot(frame["source"]) == source["slot"], "frame differs from source slot")
    original = {**source["original_static"], **frame["vectors"]}
    _matrix_shape(original)
    c.ensure(
        all(
            [value is not None for value in original[name]] == original[name + "_finite"]
            for name in ("lower", "upper")
        ),
        "stream frame finite-mask drift",
    )
    c.ensure(
        len(original["q"]) == original["n"]
        and len(original["lower"]) == len(original["upper"]) == original["m"],
        "stream frame vector dimension",
    )
    c.ensure(_digest(original) == frame["original_sha256"], "stream frame original identity")
    try:
        transform = c.canonical_transform(original)
    except (IndexError, KeyError) as error:
        raise c.ContractError("invalid stream source policy or group shape") from error
    c.ensure(_digest(transform) == frame["transform_sha256"], "stream frame canonical transform identity")
    return {
        "original": original,
        "transform": transform,
        "source": frame["source"],
        "original_sha256": frame["original_sha256"],
        "transform_sha256": frame["transform_sha256"],
        **{name: source[name] for name in _POLICY},
    }


def _problem(context, frame_document, source_document):
    problem = _reconstruct(source_document["payload"], frame_document["payload"])
    c.ensure(
        bool(problem["source"]["license"].strip()) and bool(problem["source"]["attribution"].strip()),
        "unresolved stream frame license/attribution",
    )
    doc_id = frame_document["artifact_id"]
    c._problem(problem, context, {"artifact_id": doc_id},
               v2_fixture=frame_document["purpose"] == source_document["purpose"] == "contract-fixture")
    return problem


def _layout(problem):
    transform = problem["transform"]
    original = problem["original"]
    return _digest(
        {
            **{name: value for name, value in transform.items() if name not in _VECTORS},
            "original_equality": [
                lo is not None and lo == hi for lo, hi in zip(original["lower"], original["upper"])
            ],
            "equality": [
                lo is not None and lo == hi for lo, hi in zip(transform["lower"], transform["upper"])
            ],
        }
    )


def _label(context, doc, frame_ref, problem, scope):
    payload = doc["payload"]
    c.ensure(
        payload["frame"] == frame_ref and payload["population_sha256"] == scope,
        "stream label frame/population binding",
    )
    if not context.allow_fixture or context.native_run is not None:
        from .native_labels import NativeRun

        c.ensure(
            type(context.native_run) is NativeRun
            and context.expected_native_manifest_sha256 is not None,
            "stream label source-run attestation unavailable",
        )
        context.native_run.require_label(
            doc,
            frame_ref,
            problem,
            scope,
            expected_manifest_sha256=context.expected_native_manifest_sha256,
        )
    evidence = payload["native_evidence"]
    if payload["status"] == "oracle-failed":
        c.ensure(evidence is None, "fabricated raw DAQP output after oracle failure")
        c._label_values(payload, problem, context.fit_source_ids, context)
        return
    c.ensure(evidence is not None, "missing raw label evidence")
    c.ensure(
        evidence["sha256"] == _digest({k: v for k, v in evidence.items() if k != "sha256"}),
        "raw native evidence digest",
    )
    candidate = payload["cold_candidate"]
    c.ensure(candidate is not None, "raw label evidence without cold candidate")
    t = problem["transform"]
    graph, _, _ = c.graph_coordinates(t)
    raw = evidence["raw_side_duals"]
    c.ensure(
        evidence["producer_source_sha256"] == context.producer_source_sha256
        and evidence["settings_sha256"] == payload["settings_sha256"]
        and evidence["input_sha256"] == problem["original_sha256"]
        and evidence["native_flag"] == payload["cold_native_flag"]
        and evidence["raw_primal"] == candidate["lifted_x"]
        and len(raw) == len(graph["row_map"]),
        "raw DAQP evidence identity",
    )
    lifted = [0] * t["m"]
    for mapping, value in zip(graph["row_map"], raw):
        lifted[mapping["canonical_row"]] += mapping["sign"] * value
    c.ensure(lifted == candidate["lifted_y"], "raw DAQP signed scatter differs from canonical dual")
    c._label_values(payload, problem, context.fit_source_ids, context, raw_side_duals=raw)


def _feature(frame_id, problem, representation, normalizer):
    t = problem["transform"]
    header = {
        "domain": _FEATURE,
        "frame_id": frame_id,
        "representation": representation,
        "head_id": f"H-{t['n']}-{t['m']}",
        "dtype": "float64",
        "original_sha256": problem["original_sha256"],
        "transform_sha256": problem["transform_sha256"],
    }
    if representation == "mlp-v1":
        names, raw = c.mlp_coordinates(t)
        c.ensure(
            normalizer is not None and names == normalizer["coordinate_order"], "normalizer coordinate order"
        )
        values = [(x - m) / s for x, m, s in zip(raw, normalizer["mean"], normalizer["scale"], strict=True)]
        body = {
            **header,
            "normalizer_sha256": normalizer["sha256"],
            "coordinate_order": names,
            "raw_values": raw,
            "values": values,
        }
    else:
        c.ensure(representation == "graph-v1", "unknown logical representation")
        body = {**header, "normalizer_sha256": None, "graph": c.graph_coordinates(t)[0]}
    raw = c.canonical_bytes(body)
    return LogicalFeature(frame_id, representation, raw, c.digest(raw))


def _coefficient_coordinates(transform):
    n = transform["n"]
    matrix_size = n * (n + 1) // 2
    sparse = {}
    for name in ("P", "A"):
        csc = transform[name]
        for col, (start, stop) in enumerate(zip(csc["indptr"], csc["indptr"][1:])):
            for offset in range(start, stop):
                row = csc["indices"][offset]
                if name == "P":
                    if row > col:
                        continue
                    index = row * n - row * (row - 1) // 2 + col - row
                else:
                    index = matrix_size + row * n + col
                sparse[index] = csc["data"][offset]
    return sparse


def _vector_coordinates(transform):
    lower, upper = transform["lower"], transform["upper"]
    return (
        *transform["q"],
        *(0 if value is None else value for value in lower),
        *(0 if value is None else value for value in upper),
        *(int(value is not None) for value in lower),
        *(int(value is not None) for value in upper),
    )


def _fit(head, names, matrix_size, rows):
    weights = c._normalizer_weights([source for source, _, _ in rows])
    means, scales = [], []
    for index in range(len(names)):
        if index < matrix_size:
            column = [sparse.get(index, 0) for _, sparse, _ in rows]
        else:
            column = [vectors[index - matrix_size] for _, _, vectors in rows]
        mean = sum(w * value for w, value in zip(weights, column))
        variance = sum(w * (value - mean) ** 2 for w, value in zip(weights, column))
        means.append(mean)
        scales.append(math.sqrt(variance) if variance > 0 else 1)
    normalizer = {
        "normalizer_id": "stream-" + head,
        "head_id": head,
        "fit_source_ids": sorted({s["source_id"] for s, _, _ in rows}),
        "fit_split": "train",
        "coordinate_order": names,
        "mean": means,
        "scale": scales,
        "source_weights": weights,
    }
    return {**normalizer, "sha256": _digest(normalizer)}


def population_identity(protocol_ref, sources, frames, exclusions, fit_source_ids, *, attribution, license):
    return _digest(
        {
            "domain": "softqp.stream-population/v2",
            "protocol": protocol_ref,
            "sources": sources,
            "frames": frames,
            "exclusions": exclusions,
            "fit_source_ids": fit_source_ids,
            "attribution": attribution,
            "license": license,
        }
    )


def _by_id(refs):
    ids = [ref["artifact_id"] for ref in refs]
    c.ensure(ids == sorted(set(ids)), "stream reference list must be sorted and unique")
    return dict(zip(ids, refs))


def _validate_record_paths(refs):
    paths = [ref["path"].casefold() for ref in refs]
    c.ensure(len(paths) == len(set(paths)), "stream storage alias")
    for ref in refs:
        phase._path_parts(ref["path"])


def _route_problem(context, frame_ref, source_ref, protocol_ref):
    frame = _load(context, frame_ref, FRAME, protocol_ref)
    c.ensure(frame["payload"]["source_ref"] == source_ref, "alternate source file in stream frame")
    source = _load(context, source_ref, SOURCE, protocol_ref)
    return frame, _reconstruct(source["payload"], frame["payload"])


def _scan(context, protocol_ref, scope_inputs):
    source_refs = _by_id(scope_inputs["sources"])
    frame_refs = _by_id(scope_inputs["frames"])
    c.ensure(not source_refs.keys() & frame_refs.keys(), "duplicate stream ID across kinds")
    _validate_record_paths([protocol_ref, *source_refs.values(), *frame_refs.values()])
    source_documents = {}
    for source_id, ref in source_refs.items():
        document = _load(context, ref, SOURCE, protocol_ref)
        _source(document["payload"], context)
        source_documents[source_id] = document
    source_slots = [doc["payload"]["slot"]["source_id"] for doc in source_documents.values()]
    c.ensure(len(set(source_slots)) == len(source_slots), "duplicated physical source unit")

    sources = {}
    frames, layouts, used_sources = {}, {}, set()
    head_rows, head_specs, source_coefficients = {}, {}, {}
    all_heads = set()
    states = {name: 0 for name in ("train", "validation", "calibration", "test")}
    for frame_id, ref in frame_refs.items():
        document = _load(context, ref, FRAME, protocol_ref)
        source_ref = document["payload"]["source_ref"]
        source_id = source_ref["artifact_id"]
        c.ensure(source_refs.get(source_id) == source_ref, "alternate source file in stream frame")
        used_sources.add(source_id)
        problem = _problem(context, document, source_documents[source_id])
        transform = problem["transform"]
        source = problem["source"]
        layout = _layout(problem)
        c.ensure(
            layouts.setdefault(source_id, layout) == layout,
            "stream trajectory coefficient/equality/layout drift",
        )
        fixture_pd = (
            c.exact_curvature(c.dense(transform["P"]))[0] == transform["n"]
            if problem["expected_control"] is not None and context.allow_fixture
            else None
        )
        c.ensure(
            problem["expected_control"] is None or context.allow_fixture,
            "control cannot enter scientific stream",
        )
        sources[frame_id] = (source, fixture_pd)
        frames[frame_id] = source_ref
        head = f"H-{transform['n']}-{transform['m']}"
        all_heads.add(head)
        if source["split"] == "train":
            if head not in head_specs:
                head_specs[head] = (
                    c.mlp_coordinates(transform)[0],
                    transform["n"] * (transform["n"] + 1) // 2 + transform["n"] * transform["m"],
                )
            if source_id not in source_coefficients:
                source_coefficients[source_id] = _coefficient_coordinates(transform)
            head_rows.setdefault(head, []).append(
                (source, source_coefficients[source_id], _vector_coordinates(transform))
            )
    c.ensure(used_sources == source_refs.keys(), "unused or missing source unit in stream")
    c.ensure(all_heads <= {head["id"] for head in context.authority.matrix["heads"]}, "unknown stream head")
    c.ensure(set(head_rows) == all_heads, "stream required head has no training source")
    if not context.allow_fixture:
        c.ensure(
            all_heads == {head["id"] for head in context.authority.matrix["heads"]},
            "stream required head absent",
        )
    unique_sources = {s["source_id"]: s for s, _ in sources.values()}
    for source in unique_sources.values():
        states[source["split"]] += 1
    fit = sorted(k for k, v in unique_sources.items() if v["split"] == "train")
    c.ensure(
        scope_inputs["fit_source_ids"] == fit == sorted(context.fit_source_ids),
        "stream train-only fit inventory",
    )
    exclusions = scope_inputs["exclusions"]
    c.ensure(exclusions == sorted(set(exclusions)), "stream exclusions must be sorted and unique")
    c._dataset_sources(
        {
            "parent_manifest_sha256": None,
            "generator_sha256": context.generator_sha256,
            "problems": [{"problem": ref, "source": sources[fid][0]} for fid, ref in frame_refs.items()],
            "source_ids": sorted(unique_sources),
            "counts": {"problems": len(frames), "sources": len(unique_sources), **states},
            "exclusions": exclusions,
            "license": scope_inputs["license"],
            "attribution": scope_inputs["attribution"],
        },
        context,
        lambda ref: sources[ref["artifact_id"]][0],
    )

    normalizers = {head: _fit(head, *head_specs[head], head_rows[head]) for head in sorted(head_rows)}
    return source_refs, frame_refs, sources, frames, normalizers


def _derive(context, protocol_ref, scope_inputs, label_keys):
    protocol = _protocol(context, protocol_ref)
    c.ensure(
        set(protocol["old_exclusions"]) <= set(scope_inputs["exclusions"]),
        "stream omits registered exclusions",
    )
    scope = population_identity(protocol_ref, **scope_inputs)
    source_refs, frame_refs, source_meta, frame_sources, normalizers = _scan(
        context, protocol_ref, scope_inputs
    )
    expected = phase._population_keys(context, source_meta)
    label_ids = [label["frame_id"] for label in label_keys]
    c.ensure(
        len(set(label_ids)) == len(label_ids)
        and set(label_ids) == {frame_id for frame_id, kind, _ in expected if kind == "learning-labels"},
        "stream label key inventory mismatch",
    )
    label_by_frame = {label["frame_id"]: label for label in label_keys}
    label_refs = [label["ref"] for label in label_keys if label["ref"] is not None]
    ids = [ref["artifact_id"] for ref in label_refs]
    c.ensure(
        len(ids) == len(set(ids)) and not set(ids) & (source_refs.keys() | frame_refs.keys()),
        "stream label artifact duplicate",
    )
    _validate_record_paths([protocol_ref, *source_refs.values(), *frame_refs.values(), *label_refs])
    features = []
    for frame_id, frame_ref in frame_refs.items():
        _, problem = _route_problem(context, frame_ref, frame_sources[frame_id], protocol_ref)
        t = problem["transform"]
        normalizer = normalizers[f"H-{t['n']}-{t['m']}"]
        for rep in ("graph-v1", "mlp-v1"):
            if (frame_id, "learning-features", rep) in expected:
                feature = _feature(frame_id, problem, rep, normalizer)
                features.append(
                    {"frame_id": frame_id, "representation": rep, "logical_sha256": feature.logical_sha256}
                )
        if frame_id not in label_by_frame:
            continue
        label = label_by_frame[frame_id]
        if label["state"] == "missing":
            c.ensure(label["ref"] is None and bool(label["reason"]), "invalid explicit missing stream label")
        else:
            c.ensure(label["ref"] is not None, "missing stored stream label reference")
            document = _load(context, label["ref"], LABELS, protocol_ref)
            _label(context, document, frame_ref, problem, scope)
            payload = document["payload"]
            state = "oracle-failed" if payload["status"] == "oracle-failed" else document["state"]
            c.ensure(
                (state, payload["reason"]) == (label["state"], label["reason"]), "stream label status relabel"
            )
    return (
        {
            **scope_inputs,
            "population_sha256": scope,
            "normalizers": list(normalizers.values()),
            "features": features,
            "labels": sorted(label_keys, key=lambda key: key["frame_id"]),
        },
        source_meta,
        frame_sources,
    )


def derive_stream_payload(
    context, protocol_ref, *, sources, frames, exclusions, fit_source_ids, labels, attribution, license
):
    """Verify the complete factor graph and compute one descriptor without feature-file writes."""
    scope = {
        "sources": list(sources),
        "frames": list(frames),
        "exclusions": list(exclusions),
        "fit_source_ids": list(fit_source_ids),
        "attribution": attribution,
        "license": license,
    }
    try:
        with c._admission(context, fresh=True):
            return _derive(context, protocol_ref, scope, list(labels))[0]
    except OSError as error:
        raise c.ContractError("stream source unavailable") from error


def _expect_descriptor(context, document):
    payload = document["payload"]
    scope = {
        name: payload[name]
        for name in ("sources", "frames", "exclusions", "fit_source_ids", "attribution", "license")
    }
    expected, sources, frame_sources = _derive(context, document["protocol_ref"], scope, payload["labels"])
    c.ensure(
        c.canonical_bytes(payload) == c.canonical_bytes(expected),
        "stream descriptor logical inventory or normalization differs",
    )
    return sources, frame_sources


def _graph_for_document(document, context, *, expected_population_sha256=None, train=None, validation=None):
    _document(document, context)
    ref = document["protocol_ref"]
    kind = document["kind"]
    payload = document["payload"]
    if kind != CHECKPOINT:
        _protocol(context, ref)
    if kind == SOURCE:
        _source(payload, context)
    elif kind == FRAME:
        source = _load(context, payload["source_ref"], SOURCE, ref)
        _source(source["payload"], context)
        _problem(context, document, source)
    elif kind == STREAM:
        _expect_descriptor(context, document)
    elif kind == LABELS:
        phase._hash(expected_population_sha256)
        frame = _load(context, payload["frame"], FRAME, ref)
        source = _load(context, frame["payload"]["source_ref"], SOURCE, ref)
        _source(source["payload"], context)
        problem = _problem(context, frame, source)
        _label(context, document, payload["frame"], problem, expected_population_sha256)
    else:
        _checkpoint(context, document, train, validation)


def _artifact(document, raw):
    return c.Artifact(
        document["kind"], document["artifact_id"], document["state"], document["reason"], raw, c.digest(raw)
    )


def read_stream_artifact(path, context, *, expected_sha256, **admission):
    """Verify physical bytes, strict v2 schema and full producer/consumer dependencies."""
    phase._hash(expected_sha256)
    try:
        with c._admission(context, fresh=True):
            root = phase._exact_directory(context.root)
            relative = c._requested_relative(path, root)
            raw = phase._open_bytes(root, relative)
            c.ensure(c.digest(raw) == expected_sha256, "stream artifact stored byte hash mismatch")
            document = c.strict_loads(raw)
            c.ensure(raw == c.canonical_bytes(document), "noncanonical stored stream document")
            _graph_for_document(document, context, **admission)
            return _artifact(document, raw)
    except OSError as error:
        raise c.ContractError("stream artifact unavailable") from error


def write_stream_artifact(document, relative, context, **admission):
    """Admit and atomically write an absent file in the configured external directory."""
    raw = c.canonical_bytes(document)
    immutable = c.strict_loads(raw)
    try:
        with c._admission(context, fresh=True):
            _graph_for_document(immutable, context, **admission)
            root = phase._exact_directory(context.root)
            parts = phase._path_parts(relative)
            target = root.joinpath(*parts)
            parent = phase._exact_directory(target.parent)
            aliases = {path.name.casefold() for path in parent.iterdir()}
            protected = [base.resolve() for base in context.forbidden_roots]
            c.ensure(
                target.name.casefold() not in aliases
                and os.path.normcase(str(target)) not in context._input_aliases
                and not any(c._inside_protected_root(target, base) for base in protected)
                and not any((base / ".git").exists() for base in (parent, *parent.parents)),
                "stream output aliases existing/protected path",
            )
            c.ensure(target.suffix == ".json", "stream output requires .json")
            temporary = None
            published = False
            accepted = False
            checksum = c.digest(raw)
            try:
                with tempfile.NamedTemporaryFile(dir=parent, prefix=".stream-", delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                read_stream_artifact(temporary, context, expected_sha256=checksum, **admission)
                os.link(temporary, target)
                published = True
                result = read_stream_artifact(target, context, expected_sha256=checksum, **admission)
                accepted = True
                return result
            finally:
                if temporary is not None:
                    try:
                        if published and not accepted and os.path.samestat(target.lstat(), temporary.lstat()):
                            target.unlink()
                    except FileNotFoundError:
                        pass
                    finally:
                        temporary.unlink(missing_ok=True)
    except OSError as error:
        raise c.ContractError("stream output unavailable or already reserved") from error


def preflight_stream(context, *, descriptor_id, expected_descriptor_sha256):
    phase._hash(expected_descriptor_sha256)
    try:
        with c._admission(context, fresh=True):
            descriptor = phase._checked_ref(context, descriptor_id, STREAM)
            c.ensure(
                descriptor["sha256"] == expected_descriptor_sha256,
                "stream descriptor independently expected digest differs",
            )
            root = phase._exact_directory(context.root)
            raw = phase._open_bytes(root, descriptor["path"])
            c.ensure(
                c.digest(raw) == expected_descriptor_sha256, "stream descriptor stored byte hash mismatch"
            )
            document = _document(c.strict_loads(raw), context)
            c.ensure(
                document["artifact_id"] == descriptor_id
                and document["kind"] == STREAM
                and raw == c.canonical_bytes(document),
                "stream descriptor physical identity",
            )
            sources, frame_sources = _expect_descriptor(context, document)
            payload = document["payload"]
            roles = {frame_id: source["split"] for frame_id, (source, _) in sources.items()}
            source_roles = {ref["artifact_id"]: roles[frame_id] for frame_id, ref in frame_sources.items()}
            label_roles = {
                row["ref"]["artifact_id"]: roles[row["frame_id"]] for row in payload["labels"] if row["ref"]
            }
            protected = tuple(base.resolve() for base in context.forbidden_roots)
            records = [
                {"ref": ref, "role": mapping[ref["artifact_id"]]}
                for refs, mapping in (
                    (payload["sources"], source_roles),
                    (payload["frames"], roles),
                    ([row["ref"] for row in payload["labels"] if row["ref"]], label_roles),
                )
                for ref in refs
            ]
            receipt = {
                "format": _PRE,
                "source_root": str(root),
                "forbidden_roots": [str(path) for path in protected],
                "fixture_only": context.allow_fixture,
                "descriptor": descriptor,
                "protocol_ref": document["protocol_ref"],
                "identities": {
                    **{
                        key: getattr(context, key)
                        for key in (
                            "protocol_id",
                            "protocol_sha256",
                            "source_lock_sha256",
                            "registration_sha256",
                            "producer_source_sha256",
                            "generator_sha256",
                            "dependency_lock_sha256",
                        )
                    },
                    "learning_policy_sha256": context.authority.manifest["normative_sha256"][
                        "learning-spec.md"
                    ],
                    "design_manifest_sha256": c.DESIGN_MANIFEST_SHA256,
                },
                "population_sha256": payload["population_sha256"],
                "records": records,
                "logical": [dict(row, role=roles[row["frame_id"]]) for row in payload["features"]],
                "labels": [dict(row, role=roles[row["frame_id"]]) for row in payload["labels"]],
                "normalizers": payload["normalizers"],
            }
            return phase.PhasePreflight(root, protected, c.canonical_bytes(receipt))
    except OSError as error:
        raise c.ContractError("stream preflight inputs unavailable") from error


def materialize_stream_phase(preflight, destination, *, role, expected_preflight_sha256):
    phase._role(role)
    phase._hash(expected_preflight_sha256)
    c.ensure(preflight.sha256 == expected_preflight_sha256, "stream phase preflight digest mismatch")
    receipt = c.strict_loads(preflight.receipt_bytes)
    c.ensure(
        receipt.get("format") == _PRE
        and receipt["source_root"] == str(preflight.source_root)
        and receipt["forbidden_roots"] == [str(path) for path in preflight.forbidden_roots],
        "stream phase materialization path policy",
    )
    selection = []
    records = []
    for record in receipt["records"]:
        if record["role"] != role:
            continue
        ref = record["ref"]
        local = f"input-{len(selection):06d}.json"
        selection.append({"source_path": ref["path"], "path": local, "sha256": ref["sha256"]})
        records.append({"ref": ref, "path": local})
    c.ensure(bool(selection), "stream phase has no admitted inputs")
    manifest = {
        "format": _PHASE,
        "role": role,
        "preflight_sha256": expected_preflight_sha256,
        **{
            name: receipt[name]
            for name in (
                "fixture_only",
                "descriptor",
                "population_sha256",
                "identities",
                "protocol_ref",
                "normalizers",
            )
        },
        "records": records,
        "logical": [row for row in receipt["logical"] if row["role"] == role],
        "labels": [row for row in receipt["labels"] if row["role"] == role],
    }
    raw = c.canonical_bytes(manifest)
    try:
        root = phase._exact_directory(preflight.source_root)
        target = phase._external_destination(destination, root, preflight.forbidden_roots)
        phase._publish(target, root, selection, raw)
    except OSError as error:
        raise c.ContractError("stream phase publication unavailable or already reserved") from error
    return c.digest(raw)


class StreamingPhaseReader:
    """Role-local source/frame bytes and on-demand logical feature values."""

    def __init__(
        self, root, *, role, expected_manifest_sha256, expected_preflight_sha256, allow_fixture=False
    ):
        phase._role(role)
        phase._hash(expected_manifest_sha256)
        phase._hash(expected_preflight_sha256)
        self._root = root
        try:
            self._root = phase._exact_directory(root)
            raw = phase._open_bytes(self._root, phase._MANIFEST)
        except OSError as error:
            raise c.ContractError("stream phase manifest unavailable") from error
        c.ensure(c.digest(raw) == expected_manifest_sha256, "stream phase manifest digest mismatch")
        manifest = c.strict_loads(raw)
        c.ensure(
            manifest.get("format") == _PHASE
            and manifest["role"] == role
            and manifest["preflight_sha256"] == expected_preflight_sha256
            and raw == c.canonical_bytes(manifest),
            "stream phase role/preflight/format mismatch",
        )
        c.ensure(
            type(manifest["fixture_only"]) is bool
            and (not manifest["fixture_only"] or allow_fixture is True),
            "stream phase fixture rejected by independent policy",
        )
        paths = {row["path"] for row in manifest["records"]}
        self._records = MappingProxyType(
            {
                row["ref"]["artifact_id"]: MappingProxyType({**row, "ref": MappingProxyType(row["ref"])})
                for row in manifest["records"]
            }
        )
        c.ensure(
            len(paths) == len(self._records) == len(manifest["records"]),
            "duplicate stream phase physical input",
        )
        c.ensure(all(phase._FILE.fullmatch(name) for name in paths), "unsafe stream phase input path")
        phase._check_role_inventory(self._root, paths, manifest_raw=raw)
        self._logical = MappingProxyType(
            {(row["frame_id"], row["representation"]): row["logical_sha256"] for row in manifest["logical"]}
        )
        self._labels = MappingProxyType(
            {
                row["frame_id"]: MappingProxyType(
                    {**row, "ref": MappingProxyType(row["ref"]) if row["ref"] else None}
                )
                for row in manifest["labels"]
            }
        )
        c.ensure(
            len(self._logical) == len(manifest["logical"])
            and len(self._labels) == len(manifest["labels"])
            and all(row["role"] == role for row in [*manifest["logical"], *manifest["labels"]]),
            "duplicate or relabeled stream phase logical key",
        )
        self._normalizers = MappingProxyType(
            {row["head_id"]: c.canonical_bytes(row) for row in manifest["normalizers"]}
        )
        c.ensure(len(self._normalizers) == len(manifest["normalizers"]), "duplicate stream phase normalizer")
        c.ensure(
            all(
                self._records.get(frame_id, {}).get("ref", {}).get("kind") == FRAME
                and representation in ("mlp-v1", "graph-v1")
                for frame_id, representation in self._logical
            )
            and all((frame_id, "graph-v1") in self._logical for frame_id in self._labels),
            "stream phase logical-to-physical topology",
        )
        self._fixture_only = manifest["fixture_only"]
        self._population = manifest["population_sha256"]
        self._protocol_ref = MappingProxyType(manifest["protocol_ref"])
        self._descriptor = MappingProxyType(manifest["descriptor"])
        self._identities = MappingProxyType(manifest["identities"])
        self._role = role
        self._expected_manifest_sha256 = expected_manifest_sha256
        self._expected_preflight_sha256 = expected_preflight_sha256

    @property
    def role(self):
        return self._role

    @property
    def manifest_sha256(self):
        return self._expected_manifest_sha256

    @property
    def preflight_sha256(self):
        return self._expected_preflight_sha256

    @property
    def fixture_only(self):
        return self._fixture_only

    @property
    def logical_keys(self):
        return tuple(self._logical)

    def _stored_record(self, artifact_id, expected_kind):
        row = self._records.get(artifact_id)
        c.ensure(
            row is not None and row["ref"]["kind"] == expected_kind, "stored input absent from stream role"
        )
        try:
            raw = phase._open_bytes(self._root, row["path"], single_link=True)
        except OSError as error:
            raise c.ContractError("stream phase input unavailable") from error
        c.ensure(c.digest(raw) == row["ref"]["sha256"], "stream phase input stored byte mismatch")
        document = c.strict_loads(raw)
        c.ensure(
            (document["artifact_id"], document["kind"]) == (artifact_id, expected_kind),
            "stream phase input relabel",
        )
        c.ensure(
            document["purpose"] != "contract-fixture" or self.fixture_only,
            "hidden stream fixture substitution",
        )
        return raw, document

    def _stored(self, artifact_id, expected_kind):
        return self._stored_record(artifact_id, expected_kind)[1]

    def read_sealed_frame_pair(self, frame_id):
        """Fresh local raw inputs, without numerical reconstruction or test admission.

        Scientific supervisors must start full-cost timing and the whole-trial
        deadline before this broker read and stop after observing checked output.
        """
        frame_raw, frame_document = self._stored_record(frame_id, FRAME)
        frame = frame_document["payload"]
        source_ref = frame["source_ref"]
        source_row = self._records.get(source_ref["artifact_id"])
        c.ensure(
            source_row is not None and source_row["ref"] == source_ref,
            "stream phase alternate source binding",
        )
        source_raw, source_document = self._stored_record(source_ref["artifact_id"], SOURCE)
        c.ensure(
            source_document["payload"]["slot"]["split"] == frame["source"]["split"] == self.role,
            "stream phase source role relabel",
        )
        c.ensure(
            frame_raw == c.canonical_bytes(frame_document)
            and source_raw == c.canonical_bytes(source_document),
            "stream phase raw projection must be canonical",
        )
        return {
            "source_raw": source_raw,
            "frame_raw": frame_raw,
            "source_ref": dict(source_ref),
            "frame_ref": dict(self._records[frame_id]["ref"]),
        }

    def _problem(self, frame_id):
        frame = self._stored(frame_id, FRAME)["payload"]
        source_ref = frame["source_ref"]
        row = self._records.get(source_ref["artifact_id"])
        c.ensure(row is not None and row["ref"] == source_ref, "stream phase alternate source binding")
        source = self._stored(source_ref["artifact_id"], SOURCE)["payload"]
        c.ensure(
            source["slot"]["split"] == frame["source"]["split"] == self.role,
            "stream phase source role relabel",
        )
        return _reconstruct(source, frame)

    def read_problem(self, frame_id):
        return self._problem(frame_id)

    def read_feature(self, frame_id, representation):
        expected = self._logical.get((frame_id, representation))
        c.ensure(expected is not None, "logical feature absent from stream role")
        problem = self._problem(frame_id)
        t = problem["transform"]
        normalizer_raw = self._normalizers.get(f"H-{t['n']}-{t['m']}")
        normalizer = c.strict_loads(normalizer_raw) if normalizer_raw is not None else None
        feature = _feature(frame_id, problem, representation, normalizer)
        c.ensure(feature.logical_sha256 == expected, "stream logical feature digest mismatch")
        return feature

    def read_label(self, frame_id):
        label = self._labels.get(frame_id)
        c.ensure(label is not None, "label key absent from stream role")
        ref = label["ref"]
        if ref is None:
            return {"state": label["state"], "reason": label["reason"], "payload": None}
        c.ensure(self._records[ref["artifact_id"]]["ref"] == ref, "stream label stored identity")
        document = self._stored(ref["artifact_id"], LABELS)
        frame_ref = document["payload"]["frame"]
        c.ensure(
            frame_ref == self._records[frame_id]["ref"]
            and document["payload"]["population_sha256"] == self._population,
            "stream role label frame or population relabel",
        )
        return {"state": label["state"], "reason": label["reason"], "payload": document["payload"]}


def _checkpoint(context, document, train, validation):
    c.ensure(
        isinstance(train, StreamingPhaseReader)
        and isinstance(validation, StreamingPhaseReader)
        and train.role == "train"
        and validation.role == "validation",
        "stream checkpoint requires independent train and validation readers",
    )
    payload = document["payload"]
    c.ensure(
        train.preflight_sha256 == validation.preflight_sha256 == payload["preflight_sha256"]
        and train._descriptor == validation._descriptor == payload["feature_stream"]
        and train._population == validation._population == payload["population_sha256"]
        and train._protocol_ref == validation._protocol_ref == document["protocol_ref"]
        and train._identities == validation._identities
        and train.fixture_only == validation.fixture_only == (document["purpose"] == "contract-fixture"),
        "stream checkpoint descriptor/population/role ancestry",
    )
    c.ensure(
        payload["phase_manifest_sha256"]
        == {"train": train.manifest_sha256, "validation": validation.manifest_sha256},
        "stream checkpoint phase selection differs",
    )
    for name in (
        "protocol_sha256",
        "source_lock_sha256",
        "registration_sha256",
        "producer_source_sha256",
        "generator_sha256",
        "dependency_lock_sha256",
    ):
        c.ensure(getattr(context, name) == train._identities[name], "stream checkpoint source/lock differs")
    c.ensure(
        payload["learning_policy_sha256"] == train._identities["learning_policy_sha256"],
        "stream checkpoint learning policy differs",
    )
    c._checkpoint_values(payload, context)
    if payload["method"] == "learned_osqp":
        heads = payload["architecture"]["head_ids"]
        c.ensure(
            set(heads) == set(train._normalizers) == set(validation._normalizers),
            "stream checkpoint head selection differs",
        )
        c.ensure(
            payload["normalizer_sha256"]
            == [c.strict_loads(train._normalizers[head])["sha256"] for head in heads]
            and train._normalizers == validation._normalizers,
            "stream checkpoint frozen normalizer differs",
        )
        c.ensure(payload["class_statistics"] is None, "invented stream classifier statistics")
    else:
        c.ensure(payload["normalizer_sha256"] == [], "stream graph cannot carry train normalizer")
        stats = payload["class_statistics"]
        c.ensure(
            stats is not None and bool(train._labels) and bool(validation._labels),
            "stream graph label inventory absent",
        )
        expected = [row["ref"] for row in train._labels.values()]
        c.ensure(
            all(
                row["state"] in ("available", "provider")
                for row in [*train._labels.values(), *validation._labels.values()]
            )
            and stats["labels"] == expected,
            "stream graph requires exact admitted train/validation label domain",
        )
        values = [
            (train.read_label(frame_id)["payload"], train.read_problem(frame_id)["source"])
            for frame_id in train._labels
        ]
        c._checkpoint_class_values(stats, values, sdk_order=not train.fixture_only)
