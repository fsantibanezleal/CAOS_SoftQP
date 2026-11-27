"""Immutable model inputs for evaluation, without access to fitted roles."""

from dataclasses import dataclass
from pathlib import Path
import math
import os
import struct

from . import contracts as c
from . import training as t

PREPROCESS = "softqp.r4.inference-preprocessing/1"
BUNDLE = "softqp.r4.evaluation-model-bundle/1"
ROSTER = "softqp.r4.evaluation-model-roster/1"
_HASHES = (
    "run_sha256",
    "frozen_sha256",
    "checkpoint_sha256",
    "weights_sha256",
    "population_sha256",
    "preflight_sha256",
    "protocol_sha256",
    "source_lock_sha256",
    "producer_source_sha256",
    "dependency_lock_sha256",
)
_KEYS = tuple((method, seed) for method in sorted(c.LEARNED) for seed in c.SEEDS)


def _read(root, filename, sha256):
    t.phase._hash(sha256)
    root = t.phase._exact_directory(Path(root))
    path = c.safe_path(root, filename, must_exist=True)
    info = t.phase._path_stat(path)
    c.ensure(info.st_nlink == 1 and info.st_size <= 64 * 2**20, "aliased or oversized model metadata")
    return t._read_ref(root, {"path": filename, "sha256": sha256})


def _document(root, filename, expected):
    raw = _read(root, filename, expected)
    value = c.strict_loads(raw)
    c.ensure(raw == c.canonical_bytes(value), "noncanonical model projection bytes")
    return value


def _validate(name, value):
    t._validate("learning-" + name, value)


def _write(root, name, raw):
    root = t.phase._exact_directory(Path(root))
    final = root / name
    temporary = root / (name + ".pending")
    c.ensure(not final.exists(), "immutable evaluation model projection already exists")
    with temporary.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.rename(final)
    return c.digest(raw)


def _selected(
    frozen, *, expected_frozen, expected_run, expected_checkpoint, dependency_lock_sha256, allow_fixture
):
    admitted = t.read_frozen_inference(
        frozen,
        expected_receipt_sha256=expected_frozen,
        expected_run_sha256=expected_run,
        expected_checkpoint_sha256=expected_checkpoint,
        allow_fixture=allow_fixture,
    )
    doc = admitted.document
    checkpoint = _document(admitted.root, doc["checkpoint"]["path"], expected_checkpoint)
    payload = checkpoint["payload"]
    c.ensure(
        checkpoint["content_sha256"] == c.content_digest(checkpoint)
        and checkpoint["purpose"] == ("contract-fixture" if doc["fixture_only"] else "scientific")
        and payload["training_evidence"] == "real-produced",
        "frozen checkpoint content or lane differs",
    )
    identities = dict(
        method=doc["method"],
        seed=doc["seed"],
        fixture_only=doc["fixture_only"],
        run_sha256=expected_run,
        frozen_sha256=expected_frozen,
        checkpoint_sha256=expected_checkpoint,
        weights_sha256=doc["weights"]["sha256"],
        population_sha256=doc["population_sha256"],
        preflight_sha256=doc["preflight_sha256"],
        protocol_sha256=doc["protocol"]["sha256"],
        source_lock_sha256=checkpoint["source_lock_sha256"],
        producer_source_sha256=checkpoint["provenance"]["producer_source_sha256"],
        dependency_lock_sha256=dependency_lock_sha256,
        phases=payload["phase_manifest_sha256"],
    )
    c.ensure(
        (identities["method"], identities["seed"]) in _KEYS
        and all(type(identities[key]) is str and len(identities[key]) == 64 for key in _HASHES),
        "incomplete frozen model identity",
    )
    return admitted, doc, payload, identities


def _architecture(payload, authority, fixture):
    architecture = payload["architecture"]
    heads = architecture["head_ids"]
    expected = (
        sorted(row["id"] for row in authority.matrix["heads"])
        if payload["method"] == "learned_osqp"
        else ["graph"]
    )
    c.ensure(
        heads == sorted(set(heads))
        and bool(heads)
        and (set(heads) <= set(expected) if fixture else heads == expected),
        "incomplete or reordered frozen head domain",
    )
    expected_parameters = c.parameter_shapes(payload["method"], heads, authority)
    c.ensure(
        [(p["head_id"], p["name"], p["shape"]) for p in architecture["parameters"]] == expected_parameters,
        "wrong frozen tensor order or shape",
    )
    offset = 0
    for row in architecture["parameters"]:
        count = math.prod(row["shape"])
        c.ensure(
            (row["offset"], row["count"], row["dtype"]) == (offset, count, "float64-le"),
            "noncontiguous frozen tensor layout",
        )
        offset += count
    c.ensure(
        offset == architecture["parameter_count"]
        and c.digest(c.canonical_bytes(architecture)) == payload["architecture_sha256"],
        "frozen architecture identity differs",
    )
    return heads


def _preprocessing(projection, payload, identities, authority):
    _validate("inference-preprocessing", projection)
    c.ensure(
        set(projection) == {"schema", "identities", "heads", "normalizers", "class_statistics"}
        and projection["schema"] == PREPROCESS
        and projection["identities"] == identities,
        "preprocessing ancestry differs",
    )
    heads = _architecture(payload, authority, identities["fixture_only"])
    c.ensure(projection["heads"] == heads, "preprocessing head roster differs")
    rows = projection["normalizers"]
    stats = projection["class_statistics"]
    if identities["method"] == "learned_daqp":
        c.ensure(
            rows == []
            and stats == payload["class_statistics"]
            and stats is not None
            and payload["normalizer_sha256"] == [],
            "graph statistics/normalizer scope differs",
        )
        n0, n1 = stats["N0"], stats["N1"]
        c.ensure(
            all(math.isfinite(x) and x > 0 for x in (n0, n1))
            and (stats["positive_prior"], stats["weight0"], stats["weight1"])
            == (n1 / (n0 + n1), (n0 + n1) / (2 * n0), (n0 + n1) / (2 * n1)),
            "graph class masses or positive prior differ",
        )
        return
    c.ensure(
        stats is None
        and payload["class_statistics"] is None
        and [row["head_id"] for row in rows] == heads
        and [row["sha256"] for row in rows] == payload["normalizer_sha256"],
        "normalizer order differs from selected checkpoint",
    )
    from softqp.learning.fixed_point import coordinate_names

    for row in rows:
        n, m = map(int, row["head_id"].split("-")[1:])
        columns = coordinate_names(n, m)
        sources, weights = row["fit_source_ids"], row["source_weights"]
        c.ensure(
            row["fit_split"] == "train"
            and sources == sorted(set(sources))
            and bool(sources)
            and weights
            and all(math.isfinite(v) and v > 0 for v in weights)
            and math.isclose(sum(weights), 1.0, abs_tol=1e-10)
            and row["coordinate_order"] == list(columns)
            and len(row["mean"]) == len(row["scale"]) == len(columns)
            and all(math.isfinite(x) for x in row["mean"])
            and all(math.isfinite(x) and x > 0 for x in row["scale"])
            and c.digest(c.canonical_bytes({k: v for k, v in row.items() if k != "sha256"})) == row["sha256"],
            "invalid train-only normalizer",
        )


def publish_preprocessing(
    root, *, run_root, frozen_root, expected_run, expected_frozen, expected_checkpoint, plan, runtime
):
    c.ensure(type(plan) is t.TrainingPlan, "admitted training plan required")
    run = t.read_training_run(run_root, expected_manifest_sha256=expected_run, plan=plan, runtime=runtime)
    _, _, payload, ids = _selected(
        frozen_root,
        expected_frozen=expected_frozen,
        expected_run=expected_run,
        expected_checkpoint=expected_checkpoint,
        dependency_lock_sha256=plan.context.dependency_lock_sha256,
        allow_fixture=plan.context.allow_fixture,
    )
    final = run.document["checkpoints"].get("final")
    c.ensure(
        final is not None
        and final["sha256"] == expected_checkpoint
        and run.document["heads"] == payload["architecture"]["head_ids"]
        and run.document["phases"] == ids["phases"],
        "selected checkpoint differs from verified training run",
    )
    heads = payload["architecture"]["head_ids"]
    rows = (
        [c.strict_loads(plan.train._normalizers[head]) for head in heads]
        if ids["method"] == "learned_osqp"
        else []
    )
    projected = dict(
        schema=PREPROCESS,
        identities=ids,
        heads=heads,
        normalizers=rows,
        class_statistics=payload["class_statistics"],
    )
    _preprocessing(projected, payload, ids, plan.context.authority)
    return _write(root, "preprocessing.json", c.canonical_bytes(projected))


def _disposition(calibration, ids, frozen_doc):
    c.ensure(
        all(
            calibration[key] == ids[key]
            for key in ("method", "seed", "fixture_only", "population_sha256", "preflight_sha256")
        )
        and calibration["frozen_sha256"] == ids["frozen_sha256"]
        and calibration["checkpoint"] == frozen_doc["checkpoint"],
        "observed calibration ancestry differs",
    )
    if ids["method"] == "learned_osqp":
        c.ensure(
            calibration["state"] == "not-applicable"
            and calibration["observations"] == []
            and calibration["values"] is None,
            "L2WS calibration must be not-applicable",
        )
        return {"state": "not-applicable", "threshold": None}
    c.ensure(calibration["state"] == "calibrated", "graph calibration unavailable")
    values = calibration["values"]
    scores = values["scores"]
    c.ensure(
        len(scores) == 9
        and all(math.isfinite(s) and 0 <= s <= 1 for s in scores)
        and values["mask_count"] > 0,
        "invalid observed graph calibration grid",
    )
    winner = max(range(9), key=lambda i: (scores[i], i))
    threshold = (winner + 1) / 10
    c.ensure(
        (values["threshold"], values["f1"]) == (threshold, scores[winner]),
        "calibration threshold or tie differs",
    )
    return {"state": "calibrated", "threshold": threshold}


def publish_bundle(
    root, *, preprocessing_root, calibration_root, expected_preprocessing, expected_calibration, plan, runtime
):
    c.ensure(type(plan) is t.CalibrationPlan, "admitted calibration plan required")
    calibration = t.read_calibration(
        calibration_root, expected_sha256=expected_calibration, plan=plan, runtime=runtime
    )
    _, frozen, payload, ids = _selected(
        plan.frozen.root,
        expected_frozen=plan.expected_receipt_sha256,
        expected_run=plan.expected_run_sha256,
        expected_checkpoint=plan.expected_checkpoint_sha256,
        dependency_lock_sha256=plan.context.dependency_lock_sha256,
        allow_fixture=plan.context.allow_fixture,
    )
    projected = _document(preprocessing_root, "preprocessing.json", expected_preprocessing)
    _preprocessing(projected, payload, ids, plan.context.authority)
    disposition = _disposition(calibration, ids, frozen)
    raw = _read(calibration_root, "calibration.json", expected_calibration)
    c.ensure(calibration == c.strict_loads(raw), "calibration changed after observed verification")
    _write(root, "calibration-receipt.json", raw)
    bundle = dict(
        schema=BUNDLE,
        identities=ids,
        preprocessing_sha256=expected_preprocessing,
        calibration_sha256=expected_calibration,
        calibration_phase_sha256=calibration["phase_sha256"],
        disposition=disposition,
    )
    _validate("evaluation-model-bundle", bundle)
    return _write(root, "bundle.json", c.canonical_bytes(bundle))


@dataclass(frozen=True)
class ModelTrust:
    bundle_root: Path
    preprocessing_root: Path
    frozen_root: Path
    bundle_sha256: str
    preprocessing_sha256: str
    calibration_sha256: str
    frozen_sha256: str
    run_sha256: str
    checkpoint_sha256: str
    method: str
    seed: int
    protocol_sha256: str
    population_sha256: str
    preflight_sha256: str
    dependency_lock_sha256: str


def read_bundle(trust, *, authority, allow_fixture=False):
    c.ensure(type(trust) is ModelTrust, "independent evaluation model trust required")
    roots = tuple(
        t.phase._exact_directory(Path(path))
        for path in (trust.bundle_root, trust.preprocessing_root, trust.frozen_root)
    )
    c.ensure(
        all(
            not lhs.is_relative_to(rhs)
            for i, lhs in enumerate(roots)
            for j, rhs in enumerate(roots)
            if i != j
        ),
        "overlapping evaluation model root aliases",
    )
    doc = _document(trust.bundle_root, "bundle.json", trust.bundle_sha256)
    _validate("evaluation-model-bundle", doc)
    _, frozen, payload, ids = _selected(
        trust.frozen_root,
        expected_frozen=trust.frozen_sha256,
        expected_run=trust.run_sha256,
        expected_checkpoint=trust.checkpoint_sha256,
        dependency_lock_sha256=trust.dependency_lock_sha256,
        allow_fixture=allow_fixture,
    )
    c.ensure(
        all(
            ids[key] == getattr(trust, key)
            for key in ("method", "seed", "preflight_sha256", "population_sha256", "protocol_sha256")
        ),
        "independent evaluation model method/seed/protocol binding differs",
    )
    prep = _document(trust.preprocessing_root, "preprocessing.json", trust.preprocessing_sha256)
    _preprocessing(prep, payload, ids, authority)
    calibrated = _document(trust.bundle_root, "calibration-receipt.json", trust.calibration_sha256)
    disposition = _disposition(calibrated, ids, frozen)
    expected = dict(
        schema=BUNDLE,
        identities=ids,
        preprocessing_sha256=trust.preprocessing_sha256,
        calibration_sha256=trust.calibration_sha256,
        calibration_phase_sha256=calibrated["phase_sha256"],
        disposition=disposition,
    )
    c.ensure(doc == expected, "evaluation model bundle provenance differs")
    return _AdmittedModel(
        trust.frozen_root,
        c.canonical_bytes(
            {
                "weights": frozen["weights"],
                "tensors": payload["architecture"]["parameters"],
                "preprocessing": prep,
                "disposition": disposition,
            }
        ),
        trust.method,
        trust.seed,
    )


@dataclass(frozen=True, slots=True)
class _AdmittedModel:
    root: Path
    _verified_bytes: bytes
    method: str
    seed: int

    @property
    def weights(self):
        return c.strict_loads(self._verified_bytes)["weights"]

    @property
    def tensors(self):
        return tuple(c.strict_loads(self._verified_bytes)["tensors"])

    @property
    def preprocessing(self):
        return c.strict_loads(self._verified_bytes)["preprocessing"]

    @property
    def disposition(self):
        return c.strict_loads(self._verified_bytes)["disposition"]

    def load_head(self, head):
        from .evaluation_worker import load_numeric_model

        snapshot = c.strict_loads(self._verified_bytes)
        weights, prep = snapshot["weights"], snapshot["preprocessing"]
        c.ensure(head in prep["heads"], "requested inference head is unavailable")
        rows = [row for row in snapshot["tensors"] if row["head_id"] == head]
        path = c.safe_path(self.root, weights["path"], must_exist=True)
        info = t.phase._path_stat(path)
        c.ensure(
            info.st_nlink == 1
            and info.st_size == weights["byte_count"]
            and path.resolve(strict=True).parts == path.parts,
            "numeric inference path alias or size changed",
        )
        parts = []
        with path.open("rb") as handle:
            handle.seek(rows[0]["offset"] * 8)
            for row in rows:
                part = handle.read(row["count"] * 8)
                c.ensure(
                    len(part) == row["count"] * 8 and c.digest(part) == row["sha256"],
                    "numeric inference tensor changed after admission",
                )
                parts.append(part)
        raw = b"".join(parts)
        normalizer = prior = None
        shape = None
        if self.method == "learned_osqp":
            shape = tuple(map(int, head.split("-")[1:]))
            row = next(row for row in prep["normalizers"] if row["head_id"] == head)
            packed = b"".join(struct.pack("<d", x) for x in row["mean"] + row["scale"])
            normalizer = dict(
                mean=row["mean"],
                scale=row["scale"],
                source_ids=row["fit_source_ids"],
                frame_weights=row["source_weights"],
                numeric_sha256=c.digest(packed),
            )
        else:
            prior = prep["class_statistics"]["positive_prior"]
        return load_numeric_model(
            method=self.method,
            seed=self.seed,
            shape=shape,
            weights=raw,
            weights_sha256=c.digest(raw),
            normalizer=normalizer,
            prior=prior,
            threshold=snapshot["disposition"]["threshold"],
        )


FAILURE = "softqp.r4.evaluation-model-failure/1"
ABSENCE = "softqp.r4.evaluation-model-absence/1"


@dataclass(frozen=True)
class FailedModelTrust:
    root: Path
    sha256: str
    method: str
    seed: int
    protocol_sha256: str
    population_sha256: str
    preflight_sha256: str


def _roster(trust, *, authority, allow_fixture):
    c.ensure(
        type(trust) is tuple
        and all(type(entry) in (ModelTrust, FailedModelTrust) for entry in trust)
        and tuple((entry.method, entry.seed) for entry in trust) == _KEYS,
        "incomplete, duplicate or reordered evaluation model roster",
    )
    scopes = {(entry.protocol_sha256, entry.population_sha256, entry.preflight_sha256) for entry in trust}
    c.ensure(len(scopes) == 1, "evaluation model roster combines populations")
    protocol, population, p1 = next(iter(scopes))
    entries, admitted = [], {}
    for entry in trust:
        key = entry.method, entry.seed
        if type(entry) is ModelTrust:
            admitted[key] = read_bundle(entry, authority=authority, allow_fixture=allow_fixture)
            entries.append(
                dict(method=entry.method, seed=entry.seed, state="available", sha256=entry.bundle_sha256)
            )
            continue
        failure = _document(entry.root, "failure.json", entry.sha256)
        _validate("evaluation-model-failure", failure)
        c.ensure(
            set(failure)
            == {
                "schema",
                "method",
                "seed",
                "fixture_only",
                "protocol_sha256",
                "population_sha256",
                "preflight_sha256",
                "state",
                "reason",
                "stage",
                "evidence_sha256",
            },
            "invalid sealed model failure shape",
        )
        c.ensure(
            (
                failure["schema"],
                failure["method"],
                failure["seed"],
                failure["protocol_sha256"],
                failure["population_sha256"],
                failure["preflight_sha256"],
            )
            == (FAILURE, *key, protocol, population, p1)
            and type(failure["fixture_only"]) is bool
            and (not failure["fixture_only"] or allow_fixture is True)
            and failure["state"] in ("missing", "failed")
            and failure["stage"] in ("training", "calibration", "preprocessing")
            and type(failure["reason"]) is str
            and bool(failure["reason"]),
            "sealed model failure ancestry differs",
        )
        raw = _read(entry.root, "evidence.json", failure["evidence_sha256"])
        evidence = c.strict_loads(raw)
        c.ensure(raw == c.canonical_bytes(evidence), "noncanonical sealed model failure evidence")
        common = (
            "method",
            "seed",
            "fixture_only",
            "population_sha256",
            "preflight_sha256",
            "state",
            "reason",
        )
        c.ensure(
            all(evidence.get(name) == failure[name] for name in common), "model failure evidence differs"
        )
        if failure["state"] == "failed" and failure["stage"] == "training":
            t._validate("learning-training-run", evidence)
            c.ensure(evidence["protocol"]["sha256"] == protocol, "failed training protocol differs")
        elif failure["state"] == "failed" and failure["stage"] == "calibration":
            t._validate("learning-stream-calibration", evidence)
        else:
            c.ensure(
                evidence
                == {"schema": ABSENCE, **{k: failure[k] for k in (*common, "stage", "protocol_sha256")}},
                "invalid pinned model absence evidence",
            )
        admitted[key] = failure
        entries.append(
            dict(method=entry.method, seed=entry.seed, state=failure["state"], sha256=entry.sha256)
        )
    return dict(
        schema=ROSTER,
        protocol_sha256=protocol,
        population_sha256=population,
        preflight_sha256=p1,
        entries=entries,
    ), admitted


def publish_roster(root, trust, *, authority, allow_fixture=False):
    document, _ = _roster(trust, authority=authority, allow_fixture=allow_fixture)
    _validate("evaluation-model-roster", document)
    return _write(root, "roster.json", c.canonical_bytes(document))


def read_roster(root, trust, *, expected_sha256, authority, allow_fixture=False):
    document = _document(root, "roster.json", expected_sha256)
    _validate("evaluation-model-roster", document)
    expected, admitted = _roster(trust, authority=authority, allow_fixture=allow_fixture)
    c.ensure(document == expected, "evaluation model roster differs from independent dispositions")
    return admitted
