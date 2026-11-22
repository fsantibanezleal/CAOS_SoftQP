"""Strict U1 artifact admission. No solver, dataset generation or model execution.

The context is a trusted caller boundary, never constructed from an artifact's
own claims. Fixture admission is explicit and cannot imply registration.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
import gzip
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import struct
import tempfile
from types import MappingProxyType
from typing import Any, Literal, Mapping, TypedDict

from jsonschema import Draft202012Validator, FormatChecker, validators

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "docs/contracts/schemas"
DESIGN_MANIFEST_SHA256 = "e098010809f8b4cbb57f04e70279bf0b3f4aa90994be8a1ae022bbb52a4c7fb0"
KINDS = tuple(
    "learning-" + s
    for s in (
        "protocol",
        "problem",
        "dataset",
        "split",
        "features",
        "labels",
        "checkpoint",
        "calibration",
        "method-result",
        "evaluation",
        "export-index",
    )
)
LEARNED = {"learned_osqp", "learned_daqp"}
SEEDS = (41001, 41002, 41003)
Q = Fraction


class ContractError(ValueError):
    """Invalid/untrusted artifact; callers retain missing/failure states."""


ArtifactState = Literal["available", "provider", "missing"]
ArtifactPurpose = Literal["scientific", "contract-fixture"]
SplitName = Literal["train", "validation", "calibration", "test"]
ResultStatus = Literal[
    "accepted",
    "accuracy-rejected",
    "incompatible",
    "oracle-failed",
    "timeout",
    "missing",
    "failed",
    "unbounded",
    "inconclusive",
]


class Reference(TypedDict):
    kind: str
    artifact_id: str
    path: str
    sha256: str


class ProtocolPayload(TypedDict):
    status: str
    registration_sha256: str
    generator_sha256: str
    dependency_lock_sha256: str
    design_manifest_sha256: str
    bindings: dict[str, str]
    methods: list[str]
    network_seeds: list[int]
    split_units: dict[str, int]
    source_entropy_prefix: list[int]
    old_exclusions: list[str]
    budgets: dict[str, int | float]


class ProblemPayload(TypedDict):
    source: dict[str, Any]
    generator_sha256: str
    original: dict[str, Any]
    original_sha256: str
    curvature: dict[str, Any]
    transform: dict[str, Any]
    transform_sha256: str
    physical_calibration: dict[str, str]
    expected_control: str | None


class DatasetPayload(TypedDict):
    generator_sha256: str
    problems: list[dict[str, Any]]
    source_ids: list[str]
    counts: dict[str, int]
    exclusions: list[str]
    parent_manifest_sha256: str | None
    attribution: str
    license: str


class SplitPayload(TypedDict):
    dataset: Reference
    assignments: list[dict[str, Any]]
    entropy_prefix: list[int]
    fit_source_ids: list[str]
    disjointness_sha256: str


class FeaturesPayload(TypedDict):
    problem: Reference
    split: Reference
    representation: str
    head_id: str
    transform_sha256: str
    normalizer: dict[str, Any] | None
    coordinate_order: list[str]
    raw_values: list[float]
    values: list[float]
    graph: dict[str, Any] | None
    dtype: str
    fit_access: list[str]


class LabelsPayload(TypedDict):
    problem: Reference
    split: Reference
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


class CheckpointPayload(TypedDict):
    method: str
    dataset: Reference
    split: Reference
    features: list[Reference]
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


class CalibrationPayload(TypedDict):
    method: str
    checkpoint: Reference
    split: Reference
    applicability: str
    source_ids: list[str]
    threshold_grid: list[float]
    selected_threshold: float | None
    objective: str
    tie: str
    scores: list[float]
    class_counts: list[int]
    mask_count: int
    metrics: dict[str, Any]
    observations: list[dict[str, Any]]


class MethodResultPayload(TypedDict):
    problem: Reference
    key: list[str | int]
    method: str
    semantic_transform: str
    lane: str
    checkpoint: Reference | None
    calibration: Reference | None
    settings_sha256: str
    status: ResultStatus
    reason: str | None
    oracles: list[dict[str, Any]]
    trials: list[dict[str, Any]]
    injected_state: dict[str, Any] | None
    certificate: dict[str, Any] | None
    dimensions: dict[str, int]
    memory_bytes: int
    metric_policy_sha256: str
    diagnostic_native_flag: int | str | None


class EvaluationPayload(TypedDict):
    results: list[Reference]
    expected_keyset_sha256: str
    denominators: dict[str, int]
    source_totals: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    bootstrap: dict[str, Any]
    limits: str
    diagnostics: list[dict[str, Any]]
    diagnostic_denominators: dict[str, int]


class ExportIndexPayload(TypedDict):
    evaluation: Reference
    cases: list[dict[str, Any]]
    model_cards: list[dict[str, Any]]
    lane: str
    runtime_en: str
    supported_controls: list[dict[str, Any]]
    bounds_sha256: str


Payload = (
    ProtocolPayload
    | ProblemPayload
    | DatasetPayload
    | SplitPayload
    | FeaturesPayload
    | LabelsPayload
    | CheckpointPayload
    | CalibrationPayload
    | MethodResultPayload
    | EvaluationPayload
    | ExportIndexPayload
)


class Provenance(TypedDict):
    producer_source_sha256: str
    registration_sha256: str
    parent_ids: list[str]


class Envelope(TypedDict):
    schema_id: str
    version: Literal["1.0.0"]
    kind: str
    artifact_id: str
    purpose: ArtifactPurpose
    state: ArtifactState
    reason: str | None
    protocol_id: str
    protocol_sha256: str
    protocol_ref: Reference | None
    source_lock_sha256: str
    provenance: Provenance
    payload: Payload | None
    content_sha256: str


@dataclass(frozen=True)
class Artifact:
    """Validated, detached boundary snapshot. Mutable inputs cannot alter it."""

    kind: str
    artifact_id: str
    state: str
    reason: str | None
    raw: bytes
    raw_sha256: str

    @property
    def document(self) -> dict[str, Any]:
        return strict_loads(self.raw)

    @property
    def payload(self) -> Payload | None:
        return self.document["payload"]


def ensure(condition: bool, reason: str) -> None:
    if not condition:
        raise ContractError(reason)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def finite_tree(value: Any) -> None:
    if isinstance(value, float):
        ensure(math.isfinite(value), "nonfinite JSON")
        ensure(value != 0 or math.copysign(1, value) > 0, "negative-zero is not canonical")
    elif isinstance(value, dict):
        ensure(all(type(k) is str for k in value), "non-string key")
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            finite_tree(item)
    else:
        ensure(value is None or type(value) in (str, int, bool), "non-JSON object")


def canonical_bytes(value: Any) -> bytes:
    finite_tree(value)
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True) + "\n"
    ).encode("utf-8")


def json_bytes(value: Any) -> bytes:
    finite_tree(value)
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False, ensure_ascii=True) + "\n").encode(
        "utf-8"
    )


def content_digest(document: Mapping[str, Any]) -> str:
    return digest(canonical_bytes({k: v for k, v in document.items() if k != "content_sha256"}))


def strict_loads(raw: bytes) -> dict[str, Any]:
    ensure(b"\r" not in raw and raw.endswith(b"\n"), "UTF8/LF JSON required")

    def pairs(items):
        result = {}
        for key, value in items:
            ensure(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda s: (_ for _ in ()).throw(ContractError("nonfinite JSON")),
        )
    except ContractError:
        raise
    except (UnicodeError, ValueError, OverflowError) as error:
        raise ContractError("invalid JSON numeric representation or bytes") from error
    ensure(type(value) is dict, "artifact must be object")
    finite_tree(value)
    return value


def lossless_float64_number(value: Any) -> bool:
    """Scientific JSON numbers must retain their submitted value as float64.

    JSON integers are arbitrary precision. Checking finiteness alone would either
    overflow or silently round them before exact certificate arithmetic. Integer
    metadata (indices, seeds and RNG states) keeps its separate integer schema.
    """
    if type(value) not in (int, float):
        return False
    try:
        converted = float(value)
    except (OverflowError, ValueError):
        return False
    return (
        math.isfinite(converted)
        and converted == value
        and (converted != 0 or math.copysign(1, converted) > 0)
    )


_formats = FormatChecker()


@_formats.checks("lossless-float64")
def _lossless_float64_format(value: Any) -> bool:
    # Formats annotate numeric branches, including number/null union schemas.
    return type(value) not in (int, float) or lossless_float64_number(value)


_types = Draft202012Validator.TYPE_CHECKER.redefine_many(
    {
        "integer": lambda checker, value: type(value) is int,
        "number": lambda checker, value: (
            type(value) is int or (type(value) is float and math.isfinite(value))
        ),
    }
)
StrictValidator = validators.extend(Draft202012Validator, type_checker=_types)


@lru_cache(maxsize=32)
def _validator(raw: bytes):
    schema = strict_loads(raw)
    StrictValidator.check_schema(schema)
    return StrictValidator(schema, format_checker=_formats)


def schema_validate(document: dict[str, Any]) -> None:
    ensure(document.get("kind") in KINDS, "unknown contract kind")
    path = SCHEMAS / ("softqp-" + document["kind"] + ".schema.json")
    try:
        errors = sorted(_validator(path.read_bytes()).iter_errors(document), key=lambda e: str(e.path))
        reason = str(errors[0])[:500] if errors else ""
    except ContractError:
        raise
    except (ValueError, OverflowError) as error:
        # Python's bounded integer parser/formatter is retained; an invalid
        # numeric input is a contract refusal, never an uncaught traceback.
        raise ContractError("schema: numeric JSON value exceeds representation limits") from error
    pending = list(errors)
    while pending:
        error = pending.pop()
        if error.validator == "format" and error.validator_value == "lossless-float64":
            raise ContractError(
                "schema: lossless-float64 scientific number required at " + str(list(error.absolute_path))
            )
        pending.extend(error.context)
    ensure(not errors, "schema: " + reason)


def safe_path(root: Path, relative: str, *, must_exist: bool) -> Path:
    ensure(type(relative) is str and relative != "", "empty artifact path")
    p = PurePosixPath(relative)
    ensure(
        not p.is_absolute() and not any(x in ("", ".", "..") for x in relative.split("/")), "path traversal"
    )
    ensure("\\" not in relative and ":" not in relative and "\x00" not in relative, "unsafe artifact path")
    base = root.resolve(strict=True)
    current = base
    for component in p.parts:
        current = current / component
        ensure(
            not current.is_symlink() and not (hasattr(current, "is_junction") and current.is_junction()),
            "symlink/reparse escape",
        )
    ensure(not must_exist or current.is_file(), "missing artifact file: " + relative)
    resolved = current.resolve(strict=must_exist)
    ensure(resolved.is_relative_to(base) and resolved != base, "artifact escaped root")
    return resolved


@dataclass(frozen=True)
class Authority:
    """Exact accepted design, supplied independently of submitted artifacts."""

    root: Path
    _manifest: bytes
    _matrix: bytes
    _rules: bytes
    _inventory: bytes
    _controls: bytes

    def __post_init__(self):
        ensure(digest(self._manifest) == DESIGN_MANIFEST_SHA256, "unaccepted authority construction")
        bindings = strict_loads(self._manifest)["normative_sha256"]
        for name, raw in [
            ("semantic-matrix.json", self._matrix),
            ("normative-rules.json", self._rules),
            ("expected-keysets/inventory.json", self._inventory),
            ("negative-controls.json", self._controls),
        ]:
            ensure(digest(raw) == bindings[name], "forged authority bytes")

    @property
    def manifest(self):
        return strict_loads(self._manifest)

    @property
    def matrix(self):
        return strict_loads(self._matrix)

    @property
    def rules(self):
        return strict_loads(self._rules)

    @property
    def inventory(self):
        return strict_loads(self._inventory)

    @property
    def controls(self):
        return strict_loads(self._controls)["controls"]

    @classmethod
    def load(cls, root: Path) -> "Authority":
        raw = (root / "plan-check.json").read_bytes()
        ensure(digest(raw) == DESIGN_MANIFEST_SHA256, "unaccepted design manifest")
        manifest = strict_loads(raw)
        for name in (
            "semantic-matrix.json",
            "normative-rules.json",
            "negative-controls.json",
            "expected-keysets/inventory.json",
        ):
            ensure(
                digest((root / name).read_bytes()) == manifest["normative_sha256"][name],
                "design binding mismatch",
            )
        for name in (root / "expected-keysets").glob("*.jsonl.gz"):
            key = "expected-keysets/" + name.name
            ensure(
                digest(name.read_bytes()) == manifest["normative_sha256"][key], "keyset authority mismatch"
            )
        return cls(
            root.resolve(),
            raw,
            (root / "semantic-matrix.json").read_bytes(),
            (root / "normative-rules.json").read_bytes(),
            (root / "expected-keysets/inventory.json").read_bytes(),
            (root / "negative-controls.json").read_bytes(),
        )

    def keys(self, name: str) -> tuple[tuple[Any, ...], ...]:
        path = self.root / "expected-keysets" / (name + ".jsonl.gz")
        ensure(
            digest(path.read_bytes()) == self.manifest["normative_sha256"]["expected-keysets/" + path.name],
            "keyset changed",
        )
        return tuple(tuple(json.loads(line)) for line in gzip.decompress(path.read_bytes()).splitlines())

    def row(self, family: str, regime: int) -> Mapping[str, Any]:
        matches = [r for r in self.matrix["rows"] if (r["case_id"], r["regime"]) == (family, regime)]
        ensure(len(matches) == 1, "unknown family/regime")
        return matches[0]


@dataclass(frozen=True)
class AdmissionContext:
    root: Path
    authority: Authority
    protocol_id: str
    protocol_sha256: str
    source_lock_sha256: str
    registration_sha256: str
    producer_source_sha256: str
    generator_sha256: str
    dependency_lock_sha256: str
    settings_hashes: Mapping[str, str]
    source_lock_bytes: bytes
    dependency_lock_bytes: bytes
    generator_source_bytes: bytes
    producer_source_bytes: bytes
    catalog: Mapping[str, Reference]
    problem_hashes: Mapping[str, str]
    source_records: Mapping[str, str]
    fit_source_ids: tuple[str, ...]
    expected_result_keys: tuple[tuple[Any, ...], ...]
    allow_fixture: bool = False
    expected_diagnostic_keys: tuple[tuple[Any, ...], ...] = ()
    diagnostic_evidence: Mapping[tuple[Any, ...], str] = field(default_factory=dict)
    forbidden_roots: tuple[Path, ...] = (ROOT,)
    _validated: dict = field(default_factory=dict, init=False, compare=False, repr=False)

    def __post_init__(self):
        ensure(self.root.is_absolute() and self.root.exists(), "external context root missing")
        ensure(
            all(
                type(raw) is bytes and len(raw) > 0 and digest(raw) == expected
                for raw, expected in [
                    (self.source_lock_bytes, self.source_lock_sha256),
                    (self.dependency_lock_bytes, self.dependency_lock_sha256),
                    (self.generator_source_bytes, self.generator_sha256),
                    (self.producer_source_bytes, self.producer_source_sha256),
                ]
            ),
            "actual source/lock bytes differ from trusted identity",
        )
        ensure(
            not any(
                (parent / ".git").exists() for parent in (self.root.resolve(), *self.root.resolve().parents)
            ),
            "artifact root inside a Git checkout",
        )
        ensure(bool(self.expected_result_keys), "expected keyset cannot be empty")
        ensure(
            len(set(self.expected_result_keys)) == len(self.expected_result_keys), "duplicate trusted keys"
        )
        copied = strict_loads(json_bytes({key: dict(value) for key, value in self.catalog.items()}))
        object.__setattr__(
            self, "catalog", MappingProxyType({key: MappingProxyType(value) for key, value in copied.items()})
        )
        object.__setattr__(self, "problem_hashes", MappingProxyType(dict(self.problem_hashes)))
        object.__setattr__(self, "source_records", MappingProxyType(dict(self.source_records)))
        object.__setattr__(self, "settings_hashes", MappingProxyType(dict(self.settings_hashes)))
        object.__setattr__(self, "diagnostic_evidence", MappingProxyType(dict(self.diagnostic_evidence)))
        if not self.allow_fixture:
            ensure(
                set(self.expected_result_keys)
                == set(self.authority.keys("method-status")) | set(self.authority.keys("control-status")),
                "production expected matrix differs from registration",
            )
            ensure(
                set(self.expected_diagnostic_keys) == set(self.authority.keys("diagnostic-status")),
                "production diagnostic matrix differs from registration",
            )
        for base in self.forbidden_roots:
            ensure(not self.root.resolve().is_relative_to(base.resolve()), "context root inside checkout")


def _references(value: Any) -> list[Reference]:
    if isinstance(value, dict):
        if set(value) == {"kind", "artifact_id", "path", "sha256"}:
            return [value]
        return [r for v in value.values() for r in _references(v)]
    if isinstance(value, list):
        return [r for v in value for r in _references(v)]
    return []


def _reference_entries(value, field_name=""):
    if isinstance(value, dict):
        if set(value) == {"kind", "artifact_id", "path", "sha256"}:
            return [(field_name, value)]
        return [item for name, child in value.items() for item in _reference_entries(child, name)]
    if isinstance(value, list):
        return [item for child in value for item in _reference_entries(child, field_name)]
    return []


def dependency(ref: Reference, context: AdmissionContext, stack: tuple[str, ...]) -> dict[str, Any]:
    ensure(context.catalog.get(ref["artifact_id"]) == ref, "reference not in sealed catalog")
    ensure(ref["artifact_id"] not in stack, "artifact dependency cycle")
    path = safe_path(context.root, ref["path"], must_exist=True)
    ensure(digest(path.read_bytes()) == ref["sha256"], "parent raw-byte hash mismatch")
    artifact = read_artifact(path, context, expected_sha256=ref["sha256"], _stack=stack)
    ensure(
        artifact.kind == ref["kind"] and artifact.artifact_id == ref["artifact_id"],
        "parent identity mismatch",
    )
    ensure(artifact.payload is not None and artifact.state != "missing", "required parent is missing")
    return artifact.document["payload"]


def dense(matrix: Mapping[str, Any]) -> list[list[float]]:
    m, n = matrix["shape"]
    ensure(m <= 1024 and n <= 1024, "matrix exceeds admission resource limit")
    data, rows, ptr = matrix["data"], matrix["indices"], matrix["indptr"]
    ensure(
        len(ptr) == n + 1 and len(data) == len(rows) and ptr[0] == 0 and ptr[-1] == len(data), "CSC lengths"
    )
    ensure(all(0 <= a <= b <= len(data) for a, b in zip(ptr, ptr[1:])), "CSC offsets")
    ensure(all(0 <= i < m for i in rows) and all(v != 0 for v in data), "CSC rows/explicit zero")
    result = [[0 for _ in range(n)] for _ in range(m)]
    for j in range(n):
        indices = rows[ptr[j] : ptr[j + 1]]
        ensure(all(a < b for a, b in zip(indices, indices[1:])), "CSC duplicate/unsorted coordinate")
        for k in range(ptr[j], ptr[j + 1]):
            result[rows[k]][j] = data[k]
    return result


def csc(matrix: list[list[float]], n: int | None = None) -> dict[str, Any]:
    m = len(matrix)
    n = len(matrix[0]) if m else (n or 0)
    data, rows, ptr = [], [], [0]
    for j in range(n):
        for i in range(m):
            if matrix[i][j] != 0:
                data.append(matrix[i][j])
                rows.append(i)
        ptr.append(len(data))
    return {"shape": [m, n], "data": data, "indices": rows, "indptr": ptr}


def rational(value: int | float) -> Q:
    ensure(lossless_float64_number(value), "rational input must be lossless finite float64")
    # Preserve an admitted integer directly; no rounded coefficient can enter a
    # claimed exact proof. Python floats already denote exact binary64 dyadics.
    return Q(value)


def exact_curvature(P: list[list[float]]) -> tuple[int, list[str]]:
    n = len(P)
    ensure(all(len(r) == n for r in P), "Hessian shape")
    ensure(all(P[i][j] == P[j][i] for i in range(n) for j in range(n)), "exact Hessian symmetry")
    a = [[rational(v) for v in row] for row in P]
    pivots = []
    for k in range(n):
        pivot = a[k][k]
        ensure(
            pivot >= 0 and (pivot != 0 or all(a[j][k] == 0 for j in range(k + 1, n))),
            "exact nonconvex Hessian",
        )
        pivots.append(str(pivot))
        if pivot:
            for i in range(k + 1, n):
                if a[i][k]:
                    for j in range(i, n):
                        value = a[j][i] - a[i][k] * a[j][k] / pivot
                        a[j][i] = a[i][j] = value
    return sum(Q(x) > 0 for x in pivots), pivots


def canonical_transform(original: dict[str, Any]) -> dict[str, Any]:
    """Algebraic map validator's reference, never a solver or data generator."""
    n, m = original["n"], original["m"]
    P, A, p = dense(original["P"]), dense(original["A"]), original["penalty"]
    lower, upper = original["lower"], original["upper"]
    symmetric = p["lower_linear"] == p["upper_linear"] and p["lower_quadratic"] == p["upper_quadratic"]
    kind = "G" if original["formulation"] == "peak" else ("S" if symmetric else "A")
    variables = [f"x:{j}" for j in range(n)]
    tail_costs, rows, lo, up, row_names, dual = [], [], [], [], [], []

    # Sparse row dictionaries avoid changing matrix dimension while allocating variables.
    def emit(coefficients, l, u, name, original_row=None, factor=1):
        row_id = len(rows)
        rows.append(dict(coefficients))
        lo.append(l)
        up.append(u)
        row_names.append(name)
        if original_row is not None:
            dual.append({"original_row": original_row, "canonical_row": row_id, "coefficient": factor})

    def allocate(name, linear, quadratic):
        index = len(variables)
        variables.append(name)
        tail_costs.append((linear, quadratic))
        return index

    def coeff(i):
        return {j: v for j, v in enumerate(A[i]) if v}

    if kind == "S":
        xi, slack = {}, {}
        for i in range(m):
            if p["soft"][i] and p["lower_linear"][i] == 0 and p["lower_quadratic"][i] > 0:
                xi[i] = allocate(f"xi:{i}", 0, p["lower_quadratic"][i])
        for i in range(m):
            if p["soft"][i] and i not in xi:
                slack[i] = allocate(f"s:{i}", p["lower_linear"][i], p["lower_quadratic"][i])
        for i in range(m):
            row, l, u = coeff(i), lower[i], upper[i]
            if i in xi:
                row[xi[i]] = 1
            elif i in slack:
                upper_side = u is not None or l is None
                row[slack[i]] = -1 if upper_side else 1
                if upper_side:
                    l = None
                else:
                    u = None
            emit(row, l, u, f"top:{i}", i)
        for i, index in slack.items():
            if lower[i] is not None and upper[i] is not None:
                row = coeff(i)
                row[index] = 1
                emit(row, lower[i], None, f"lower:{i}", i)
        for i, index in slack.items():
            emit({index: 1}, 0, None, f"nonnegative-s:{i}")
    elif kind == "A":
        slacks = []
        for i in range(m):
            if not p["soft"][i]:
                emit(coeff(i), lower[i], upper[i], f"hard:{i}", i)
                continue
            for side, bound, sign in [("lower", lower[i], 1), ("upper", upper[i], -1)]:
                if bound is not None:
                    index = allocate(f"s:{i}:{side}", p[side + "_linear"][i], p[side + "_quadratic"][i])
                    row = coeff(i)
                    row[index] = sign
                    slacks.append((i, side, index))
                    emit(row, bound if sign == 1 else None, bound if sign == -1 else None, f"{side}:{i}", i)
        for i, side, index in slacks:
            emit({index: 1}, 0, None, f"nonnegative-s:{i}:{side}")
    else:
        groups = original["groups"]
        group_by_row = {row: (g, pos) for g in groups for pos, row in enumerate(g["rows"])}
        live = {}
        for g in groups:
            if (g["linear"] or g["quadratic"]) and any(
                lower[i] is not None or upper[i] is not None for i in g["rows"]
            ):
                live[g["group_id"]] = allocate(f"t:{g['group_id']}", g["linear"], g["quadratic"])
        for i in range(m):
            if not p["soft"][i]:
                emit(coeff(i), lower[i], upper[i], f"hard:{i}", i)
        for side, bounds, sign in [("upper", upper, 1), ("lower", lower, -1)]:
            for i in range(m):
                if i in group_by_row and bounds[i] is not None:
                    g, pos = group_by_row[i]
                    if g["group_id"] not in live:
                        continue
                    scale = g[side + "_scale"][pos]
                    row = {j: sign * scale * v for j, v in coeff(i).items()}
                    row[live[g["group_id"]]] = -1
                    emit(row, None, sign * scale * bounds[i], f"{side}:{i}", i, sign * scale)
        for group_id, index in live.items():
            emit({index: 1}, 0, None, f"nonnegative-t:{group_id}")
    nl = len(variables)
    outP = [list(row) + [0] * (nl - n) for row in P] + [[0] * nl for _ in range(nl - n)]
    for j, (_, b) in enumerate(tail_costs, n):
        outP[j][j] = b
    outA = [[row.get(j, 0) for j in range(nl)] for row in rows]
    result = {
        "kind": kind,
        "n": nl,
        "m": len(rows),
        "P": csc(outP),
        "A": csc(outA, nl),
        "q": original["q"] + [a for a, _ in tail_costs],
        "lower": lo,
        "upper": up,
        "x_original_indices": list(range(n)),
        "row_dual_map": dual,
        "variable_order": variables,
        "row_order": row_names,
    }
    finite_tree(result)
    return result


def _problem(payload, context, document):
    o, source = payload["original"], payload["source"]
    n, m = o["n"], o["m"]
    ensure(n > 0 and n <= 66 and m <= 98, "original dimensions outside reviewed bound")
    ensure(o["P"]["shape"] == [n, n] and o["A"]["shape"] == [m, n], "original matrix shape")
    P, A = dense(o["P"]), dense(o["A"])
    ensure(len(o["q"]) == n, "linear term shape")
    for name in ["lower", "upper", "lower_finite", "upper_finite"]:
        ensure(len(o[name]) == m, "bound/mask shape")
    p, units = o["penalty"], o["units"]
    ensure(all(len(v) == m for v in p.values()), "price/mask shape")
    for i in range(m):
        for side in ["lower", "upper"]:
            ensure(o[side + "_finite"][i] == (o[side][i] is not None), "finite bound mask")
            if not p["soft"][i]:
                ensure(p[side + "_linear"][i] == p[side + "_quadratic"][i] == 0, "price on hard row")
        ensure(
            o["lower"][i] is None or o["upper"][i] is None or o["lower"][i] <= o["upper"][i],
            "reversed interval",
        )
    ensure(
        len(units["variable"]) == len(units["D_x"]) == n and len(units["row"]) == len(units["D_r"]) == m,
        "physical unit dimensions",
    )
    ensure(len(units["peak"]) == len(units["D_t"]) == len(o["groups"]), "peak units")
    ensure(
        all(v == 1 for k in ["D_x", "D_r", "D_t"] for v in units[k]) and units["S_f"] == 1,
        "noncanonical unit magnitudes",
    )
    allowed = {"dimensionless", "m", "m/s", "N", "degreeC", "kWh"}
    ensure(set(units["variable"] + units["row"] + units["peak"]) <= allowed, "unknown unit")
    ensure(units["objective"] in {"synthetic-operating-cost", "synthetic-currency"}, "unknown objective unit")
    group_rows = []
    ensure([g["group_id"] for g in o["groups"]] == list(range(len(o["groups"]))), "group ID order")
    for g in o["groups"]:
        ensure(g["rows"] == sorted(set(g["rows"])) and len(g["rows"]) > 0, "group row order")
        ensure(len(g["rows"]) == len(g["lower_scale"]) == len(g["upper_scale"]), "group scale shape")
        ensure(all(0 <= i < m and p["soft"][i] for i in g["rows"]), "group hard/invalid row")
        ensure(
            all(units["row"][i] == units["peak"][g["group_id"]] for i in g["rows"]), "incompatible group unit"
        )
        group_rows.extend(g["rows"])
    ensure(len(group_rows) == len(set(group_rows)), "overlapping peak groups")
    if o["formulation"] == "peak":
        ensure(set(group_rows) == {i for i in range(m) if p["soft"][i]}, "ungrouped soft peak row")
        ensure(all(v == 0 for k, vs in p.items() if k != "soft" for v in vs), "separable price on peak input")
    else:
        ensure(not o["groups"], "groups on separable input")
    rank, pivots = exact_curvature(P)
    certificate = payload["curvature"]
    ensure(certificate["rank"] == rank, "false exact rank")
    if certificate["kind"] == "exact-diagonal-PSD":
        ensure(all(P[i][j] == 0 for i in range(n) for j in range(n) if i != j), "non-diagonal PSD recipe")
        ensure(
            certificate["diagonal_support"] == [i for i in range(n) if P[i][i] > 0]
            and certificate["pivots"] == [],
            "false diagonal certificate",
        )
    else:
        ensure(
            rank == n and certificate["pivots"] == pivots and certificate["diagonal_support"] == [],
            "false LDL certificate",
        )
    ensure(payload["original_sha256"] == digest(canonical_bytes(o)), "original content hash")
    ensure(payload["transform"] == canonical_transform(o), "incorrect transform/order/recovery map")
    ensure(payload["transform_sha256"] == digest(canonical_bytes(payload["transform"])), "transform hash")
    ensure(payload["generator_sha256"] == context.generator_sha256, "generator identity")
    ensure(source["input_sha256"] == payload["original_sha256"], "source input identity")
    ensure(
        context.problem_hashes.get(document["artifact_id"]) == payload["original_sha256"],
        "same-size coefficient/source substitution",
    )
    ensure(
        context.source_records.get(document["artifact_id"]) == digest(canonical_bytes(source)),
        "source/parent/split record relabel",
    )
    ensure(
        payload["physical_calibration"]["calibration_sha256"] == digest(canonical_bytes(units)),
        "physical calibration identity",
    )
    row = context.authority.row(source["family"], source["regime"])
    if payload["expected_control"] is None:
        ensure(
            rank == row["exact_base_rank"] and (rank == n) == row["base_pd"],
            "registered base curvature/rank differs",
        )
        finite_soft = [
            (side, i)
            for i in range(m)
            if p["soft"][i]
            for side in ["lower", "upper"]
            if o[side][i] is not None
        ]
        pure_l1 = (
            bool(finite_soft)
            and all(p["soft"][i] for i in range(m) if o["lower"][i] is not None or o["upper"][i] is not None)
            and all(p[side + "_linear"][i] > 0 and p[side + "_quadratic"][i] == 0 for side, i in finite_soft)
        )
        ensure(pure_l1 == row["pure_l1"], "registered pure-L1 semantics differ")
        ensure((n, m) == (row["original_n"], row["original_m"]), "family dimension mismatch")
        ensure(
            (payload["transform"]["n"], payload["transform"]["m"], payload["transform"]["kind"])
            == (row["lifted_n"], row["lifted_m"], row["canonical_lift"]),
            "canonical family shape mismatch",
        )
        graph, _, _ = graph_coordinates(payload["transform"])
        ensure(
            len(graph["row_map"]) == row["graph_constraints"]
            and graph["node_kind"].count("equality") == row["graph_equalities"],
            "registered graph equality/constraint shape differs",
        )
        group = o["formulation"] == "peak"
        symmetric = p["lower_linear"] == p["upper_linear"] and p["lower_quadratic"] == p["upper_quadratic"]
        canonical_P = dense(payload["transform"]["P"])
        canonical_pd = (
            rank + sum(canonical_P[j][j] > 0 for j in range(n, payload["transform"]["n"]))
            == payload["transform"]["n"]
        )
        expected_eligibility = {
            "lifted": True,
            "clarabel": True,
            "proxqp": True,
            "piqp": True,
            "learned_osqp": True,
            "generalized": not group and symmetric,
            "asymmetric": not group,
            "daqp": canonical_pd
            if group
            else rank == n and all(p[side + "_quadratic"][i] > 0 for side, i in finite_soft),
            "flex": pure_l1,
            "elastiqp": pure_l1,
            "directional": group or symmetric,
            "learned_daqp": canonical_pd,
        }
        ensure(
            {method: cell["eligible"] for method, cell in row["methods"].items()} == expected_eligibility,
            "input mathematical domain differs from registered method semantics",
        )
    else:
        controls = context.authority.controls
        fixture_only = context.allow_fixture and payload["expected_control"].startswith("contract-fixture:")
        ensure(
            fixture_only or payload["expected_control"] in {c["id"] for c in controls},
            "unknown diagnostic control",
        )
        if payload["expected_control"] in {
            "NC22-unbounded-convex-objective",
            "NC23-tiny-positive-curvature",
            "NC24-tiny-positive-upper-recession",
        }:
            expected = next(c["fixture"] for c in controls if c["id"] == payload["expected_control"])
            ensure(
                P == expected["P"]
                and A == expected["A"]
                and o["q"] == expected["q"]
                and all(
                    o[k] == expected[k] for k in ["n", "m", "lower", "upper", "lower_finite", "upper_finite"]
                )
                and not any(p["soft"]),
                "recession diagnostic input differs from frozen exact witness",
            )
    ensure(
        source["frame_count"] == (32 if source["family"] == "N12" else 1)
        and source["frame"] < source["frame_count"],
        "trajectory frame identity",
    )
    split_code = ["train", "validation", "calibration", "test"].index(source["split"])
    ensure(source["unit_index"] < (32 if split_code == 0 else 8), "source split count")
    ensure(
        source["entropy"]
        == [20261105, 903, int(source["family"][1:]), source["regime"], split_code, source["unit_index"], 0],
        "source seed entropy",
    )
    ensure(
        source["rng_state_sha256"] == digest(canonical_bytes(source["rng_state"]))
        and source["rng_state"]["state"]["inc"] % 2 == 1,
        "source RNG state bytes/stream",
    )
    ensure(
        [p["name"] for p in source["parameters"]] == sorted(set(p["name"] for p in source["parameters"])),
        "duplicate/unsorted source parameter",
    )
    ensure(
        context.allow_fixture
        or (source["state_origin"] == "generator-produced" and bool(source["parameters"])),
        "fixture RNG/absent source parameters cannot be scientific input",
    )


def _protocol(payload, context, document):
    ensure(
        digest(canonical_bytes(payload)) == context.protocol_sha256, "protocol payload registration mismatch"
    )
    ensure(payload["registration_sha256"] == context.registration_sha256, "protocol review receipt mismatch")
    ensure(
        payload["generator_sha256"] == context.generator_sha256
        and payload["dependency_lock_sha256"] == context.dependency_lock_sha256,
        "protocol source/dependency lock mismatch",
    )
    ensure(
        payload["bindings"] == context.authority.manifest["normative_sha256"],
        "protocol changed normative bindings",
    )
    ensure(payload["methods"] == context.authority.matrix["methods"], "method registry mismatch")
    ensure(
        payload["budgets"]
        == {
            "training_rss_bytes": 8 * 2**30,
            "dataset_checkpoint_bytes": 8 * 2**30,
            "inference_rss_bytes": 4 * 2**30,
            "trial_seconds": 10,
            "import_seconds": 180,
            "worker_count": 1,
        },
        "resource/timing budget changed",
    )
    old = {
        "3a79bc8abf63f70cac054c26bb5ec19bff0321e0047673d7bc3b239d380f00b5",
        "3d8eb822a6b31026c491b66cfb21f474b044a6ca3801074379243b8a3e7ca53f",
        "c82bf30bb53c7c10d464fc446bd2b99ee774b581dbe3f4dced86194e1fe54c6d",
    }
    ensure(
        set(payload["old_exclusions"]) == old and len(payload["old_exclusions"]) == 3,
        "historical exclusion identity",
    )
    if not context.allow_fixture:
        ensure(payload["status"] == "registered", "protocol is not independently registered")


def _dataset(payload, context, document, stack):
    ensure(
        payload["parent_manifest_sha256"] is None,
        "unread parent manifest cannot authorize this first-generation dataset",
    )
    ensure(payload["generator_sha256"] == context.generator_sha256, "dataset generator source")
    entries = payload["problems"]
    ids = [e["problem"]["artifact_id"] for e in entries]
    ensure(ids == sorted(set(ids)), "dataset problem order/duplicate")
    sources, parents, hashes = {}, {}, {}
    by_source = {}
    for entry in entries:
        problem = dependency(entry["problem"], context, stack)
        source = problem["source"]
        ensure(entry["source"] == source, "dataset relabeled original source")
        for field_name, seen in [("source_id", sources), ("parent_id", parents), ("input_sha256", hashes)]:
            value = source[field_name]
            ensure(value not in seen or seen[value] == source["split"], "split leakage: " + field_name)
            seen[value] = source["split"]
        by_source.setdefault(source["source_id"], []).append(source)
        ensure(source["input_sha256"] not in payload["exclusions"], "historical input relabeled")
    ensure(payload["source_ids"] == sorted(sources), "dataset source inventory")
    for values in by_source.values():
        first = values[0]
        ensure(
            len(values) == first["frame_count"]
            and {v["frame"] for v in values} == set(range(first["frame_count"])),
            "dropped trajectory frame",
        )
        ensure(
            all(
                (v["parent_id"], v["family"], v["regime"], v["split"], v["unit_index"])
                == (first["parent_id"], first["family"], first["regime"], first["split"], first["unit_index"])
                for v in values
            ),
            "source trajectory relabel",
        )
    slots = {}
    for source_id, values in by_source.items():
        s = values[0]
        slot = (s["family"], s["regime"], s["split"], s["unit_index"])
        ensure(slot not in slots, "duplicate registered source-unit slot")
        slots[slot] = source_id
    counts = {
        s: sum(v == s for v in sources.values()) for s in ["train", "validation", "calibration", "test"]
    }
    ensure(payload["counts"] == dict(problems=len(entries), sources=len(sources), **counts), "dataset counts")
    ensure(
        bool(payload["license"].strip()) and bool(payload["attribution"].strip()), "unresolved source license"
    )
    ensure(
        set(payload["exclusions"])
        >= {
            "3a79bc8abf63f70cac054c26bb5ec19bff0321e0047673d7bc3b239d380f00b5",
            "c82bf30bb53c7c10d464fc446bd2b99ee774b581dbe3f4dced86194e1fe54c6d",
        },
        "old study exclusions missing",
    )
    if not context.allow_fixture:
        ensure(
            payload["counts"]
            == dict(problems=15456, sources=5040, train=2880, validation=720, calibration=720, test=720),
            "registered dataset population",
        )
        cells = Counter((v[0]["family"], v[0]["regime"], v[0]["split"]) for v in by_source.values())
        expected = {
            (f"N{f:02}", r, s): count
            for f in range(1, 16)
            for r in range(6)
            for s, count in [("train", 32), ("validation", 8), ("calibration", 8), ("test", 8)]
        }
        ensure(dict(cells) == expected, "missing family/regime/split source")


def _split(payload, context, document, stack):
    dataset = dependency(payload["dataset"], context, stack)
    grouped = {}
    for entry in dataset["problems"]:
        source = entry["source"]
        item = grouped.setdefault(
            source["source_id"],
            {
                "source_id": source["source_id"],
                "parent_id": source["parent_id"],
                "input_sha256": source["input_sha256"],
                "split": source["split"],
                "problem_ids": [],
            },
        )
        # Source input digest covers every frame, not an arbitrarily chosen first frame.
        item["problem_ids"].append(entry["problem"]["artifact_id"])
    for source_id, item in grouped.items():
        entry_hashes = [
            e["source"]["input_sha256"] for e in dataset["problems"] if e["source"]["source_id"] == source_id
        ]
        item["input_sha256"] = digest(canonical_bytes(entry_hashes))
        item["problem_ids"].sort()
    expected = [grouped[k] for k in sorted(grouped)]
    ensure(payload["assignments"] == expected, "split differs from source-bound dataset")
    fit = sorted(k for k, v in grouped.items() if v["split"] == "train")
    ensure(payload["fit_source_ids"] == fit == sorted(context.fit_source_ids), "held-out source in fit path")
    ensure(payload["disjointness_sha256"] == digest(canonical_bytes(expected)), "split disjointness receipt")


def mlp_coordinates(transform):
    P, A = dense(transform["P"]), dense(transform["A"])
    n, m = transform["n"], transform["m"]
    names, values = [], []
    for i in range(n):
        for j in range(i, n):
            names.append(f"P:{i}:{j}")
            values.append(P[i][j])
    for i in range(m):
        for j in range(n):
            names.append(f"A:{i}:{j}")
            values.append(A[i][j])
    for name, vector in [
        ("q", transform["q"]),
        ("lower", transform["lower"]),
        ("upper", transform["upper"]),
        ("lower_finite", [int(v is not None) for v in transform["lower"]]),
        ("upper_finite", [int(v is not None) for v in transform["upper"]]),
    ]:
        for i, value in enumerate(vector):
            names.append(f"{name}:{i}")
            values.append(0 if value is None else value)
    return names, values


def graph_coordinates(transform):
    P, A = dense(transform["P"]), dense(transform["A"])
    n, m = transform["n"], transform["m"]
    nodes = [[q, 0, 0, 0] for q in transform["q"]]
    node_kind, mapping, G = ["variable"] * n, [], []
    for i in range(m):
        lo, up = transform["lower"][i], transform["upper"][i]
        sides = (
            [("equality", 1, up)] if lo is not None and up == lo else [("upper", 1, up), ("lower", -1, lo)]
        )
        for side, sign, bound in sides:
            if bound is not None:
                equality = side == "equality"
                nodes.append([0, sign * bound, int(equality), 1])
                G.append([sign * v for v in A[i]])
                node_kind.append("equality" if equality else "inequality")
                mapping.append({"canonical_row": i, "side": side, "sign": sign, "equality": equality})
    edges, weights = [], []
    for i in range(n):
        for j in range(n):
            if P[i][j]:
                edges.append([i, j])
                weights.append(P[i][j])
    for i, row in enumerate(G, n):
        for j, v in enumerate(row):
            if v:
                edges.extend([[j, i], [i, j]])
                weights.extend([v, v])
    normalized = [row[:] for row in nodes]
    for j in range(4):
        mean = sum(row[j] for row in nodes) / len(nodes)
        variance = sum((row[j] - mean) ** 2 for row in nodes) / len(nodes)
        scale = math.sqrt(variance) if variance > 0 else 1
        for i in range(len(nodes)):
            normalized[i][j] = (nodes[i][j] - mean) / scale
    return (
        {
            "node_features": normalized,
            "edge_index": edges,
            "edge_weight": weights,
            "node_kind": node_kind,
            "row_map": mapping,
        },
        G,
        nodes,
    )


def fitted_normalizer(head_id, split, context, stack):
    dataset = dependency(split["dataset"], context, stack)
    problems = []
    for entry in dataset["problems"]:
        if entry["source"]["split"] == "train":
            problem = dependency(entry["problem"], context, stack)
            t = problem["transform"]
            if f"H-{t['n']}-{t['m']}" == head_id:
                problems.append(problem)
    ensure(bool(problems), "required head has no training source")
    groups = {}
    for problem in problems:
        s = problem["source"]
        groups.setdefault((s["family"], s["regime"]), set()).add(s["source_id"])
    families = {f for f, _ in groups}
    weights = []
    for problem in problems:
        s = problem["source"]
        regimes = sum(f == s["family"] for f, _ in groups)
        weights.append(
            1 / (len(families) * regimes * len(groups[(s["family"], s["regime"])]) * s["frame_count"])
        )
    total = sum(weights)
    weights = [w / total for w in weights]
    arrays = [mlp_coordinates(p["transform"])[1] for p in problems]
    names = mlp_coordinates(problems[0]["transform"])[0]
    means = [sum(w * row[j] for w, row in zip(weights, arrays)) for j in range(len(names))]
    scales = []
    for j, mean in enumerate(means):
        variance = sum(w * (row[j] - mean) ** 2 for w, row in zip(weights, arrays))
        scales.append(math.sqrt(variance) if variance > 0 else 1)
    return names, means, scales, sorted({p["source"]["source_id"] for p in problems}), weights


def _features(payload, context, document, stack):
    problem = dependency(payload["problem"], context, stack)
    split = dependency(payload["split"], context, stack)
    t = problem["transform"]
    head_id = f"H-{t['n']}-{t['m']}"
    ensure(head_id in {h["id"] for h in context.authority.matrix["heads"]}, "unseen learned shape")
    ensure(
        payload["head_id"] == head_id and payload["transform_sha256"] == problem["transform_sha256"],
        "feature shape/transform binding",
    )
    ensure(
        set(payload["fit_access"]) <= set(split["fit_source_ids"])
        and payload["fit_access"] == sorted(set(payload["fit_access"])),
        "held-out feature fit access",
    )
    if payload["representation"] == "mlp-v1":
        names, raw = mlp_coordinates(t)
        ensure(
            payload["graph"] is None
            and payload["coordinate_order"] == names
            and payload["raw_values"] == raw,
            "reordered/altered feature coordinates",
        )
        normalizer = payload["normalizer"]
        ensure(normalizer is not None, "missing train normalizer")
        fitted_names, mean, scale, ids, weights = fitted_normalizer(head_id, split, context, stack)
        ensure(
            normalizer["head_id"] == head_id and normalizer["coordinate_order"] == fitted_names,
            "normalizer coordinate identity",
        )
        ensure(
            normalizer["mean"] == mean
            and normalizer["scale"] == scale
            and normalizer["fit_source_ids"] == ids
            and normalizer["source_weights"] == weights,
            "stale/test-fit normalizer",
        )
        ensure(
            normalizer["sha256"]
            == digest(canonical_bytes({k: v for k, v in normalizer.items() if k != "sha256"})),
            "normalizer digest",
        )
        ensure(payload["fit_access"] == ids, "incomplete/extra normalizer fit access")
        ensure(
            payload["values"] == [(x - a) / b for x, a, b in zip(raw, mean, scale)],
            "normalized features differ",
        )
    else:
        ensure(
            payload["normalizer"] is None
            and payload["coordinate_order"] == []
            and payload["raw_values"] == []
            and payload["values"] == []
            and payload["fit_access"] == [],
            "graph fitted/test normalizer not allowed",
        )
        graph, _, _ = graph_coordinates(t)
        ensure(payload["graph"] == graph, "graph coefficients/order/equality mask differs")
        ensure(exact_curvature(dense(t["P"]))[0] == t["n"], "GNN requires exact PD lift")


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _matvec(A, x):
    return [_dot(row, x) for row in A]


def original_metrics(original, candidate, f_ref):
    """Independent original-space evaluator, no native supplied metric trusted."""
    n, m = original["n"], original["m"]
    x, y = candidate["x"], candidate["y"]
    ensure(len(x) == n and len(y) == m, "candidate primal/dual dimensions")
    P, A, p = dense(original["P"]), dense(original["A"]), original["penalty"]
    z, px = _matvec(A, x), _matvec(P, x)
    finite_tree(z)
    finite_tree(px)
    lower, upper = original["lower"], original["upper"]
    vL = [max(l - a, 0) if l is not None else 0 for l, a in zip(lower, z)]
    vU = [max(a - u, 0) if u is not None else 0 for u, a in zip(upper, z)]
    ybar = [
        v if (v > 0 and upper[i] is not None) or (v < 0 and lower[i] is not None) else 0
        for i, v in enumerate(y)
    ]
    if original["formulation"] == "separable":
        for i in range(m):
            if p["soft"][i]:
                if ybar[i] > 0 and p["upper_quadratic"][i] == 0:
                    ybar[i] = min(ybar[i], p["upper_linear"][i])
                if ybar[i] < 0 and p["lower_quadratic"][i] == 0:
                    ybar[i] = max(ybar[i], -p["lower_linear"][i])
    else:
        for g in original["groups"]:
            polar = sum(
                max(ybar[i], 0) / cu + max(-ybar[i], 0) / cl
                for i, cl, cu in zip(g["rows"], g["lower_scale"], g["upper_scale"])
            )
            if g["quadratic"] == 0 and polar > g["linear"]:
                for i in g["rows"]:
                    ybar[i] *= g["linear"] / polar

    def stationarity(v):
        atv = [sum(A[i][j] * v[i] for i in range(m)) for j in range(n)]
        gradient = [px[j] + original["q"][j] + atv[j] for j in range(n)]
        denom = max([1] + list(map(abs, px)) + list(map(abs, original["q"])) + list(map(abs, atv)))
        return gradient, max(map(abs, gradient), default=0) / denom

    raw_gradient, kr = stationarity(y)
    repaired_gradient, kb = stationarity(ybar)

    def conjugate(a, b, polar):
        if b > 0:
            return max(polar - a, 0) ** 2 / (2 * b)
        ensure(polar <= a, "dual outside penalty domain")
        return 0

    def support(i):
        v = ybar[i]
        return 0 if v == 0 else v * (upper[i] if v > 0 else lower[i])

    terms = []
    grouped = set()
    peak_values = []
    if original["formulation"] == "peak":
        for g in original["groups"]:
            grouped.update(g["rows"])
            t = max(
                [0]
                + [cl * vL[i] for i, cl in zip(g["rows"], g["lower_scale"])]
                + [cu * vU[i] for i, cu in zip(g["rows"], g["upper_scale"])]
            )
            peak_values.append(t)
            phi = g["linear"] * t + g["quadratic"] * t**2 / 2
            polar = sum(
                max(ybar[i], 0) / cu + max(-ybar[i], 0) / cl
                for i, cl, cu in zip(g["rows"], g["lower_scale"], g["upper_scale"])
            )
            terms.append(
                (
                    phi,
                    sum(support(i) for i in g["rows"]),
                    conjugate(g["linear"], g["quadratic"], polar),
                    sum(ybar[i] * z[i] for i in g["rows"]),
                )
            )
    for i in range(m):
        if i in grouped:
            continue
        phi = (
            (
                p["lower_linear"][i] * vL[i]
                + p["lower_quadratic"][i] * vL[i] ** 2 / 2
                + p["upper_linear"][i] * vU[i]
                + p["upper_quadratic"][i] * vU[i] ** 2 / 2
            )
            if p["soft"][i]
            else 0
        )
        side = "upper" if ybar[i] > 0 else "lower"
        C = conjugate(p[side + "_linear"][i], p[side + "_quadratic"][i], abs(ybar[i])) if p["soft"][i] else 0
        terms.append((phi, support(i), C, ybar[i] * z[i]))

    def defect(v):
        return abs(v[0] + v[1] + v[2] - v[3]) / max(1, *map(abs, v))

    aggregate = [sum(v[i] for v in terms) for i in range(4)]
    penalty = sum(v[0] for v in terms)
    base, linear = _dot(x, px) / 2, _dot(original["q"], x)
    objective = base + linear + penalty
    result = {
        "objective": objective,
        "base_quadratic": base,
        "linear": linear,
        "penalty": penalty,
        "H": max([0] + [max(vL[i], vU[i]) for i in range(m) if not p["soft"][i]]),
        "G": abs(objective - f_ref) / max(1, abs(f_ref)),
        "K": max(kr, kb),
        "F": max(map(defect, terms), default=0),
        "F_all": defect(aggregate),
        "D": max([0] + [abs(a - b) for a, b in zip(y, ybar)]) / max([1] + list(map(abs, y))),
        "ybar": ybar,
        "raw_gradient": raw_gradient,
        "repaired_gradient": repaired_gradient,
        "f_ref": f_ref,
    }
    result.update(z=z, violation_lower=vL, violation_upper=vU, peak_values=peak_values)
    finite_tree(result)
    return result


def _recovery(problem, candidate, *, hard_limit=1e-6, limit=1e-5):
    t = problem["transform"]
    lx, ly = candidate["lifted_x"], candidate["lifted_y"]
    ensure((lx is None) == (ly is None), "partial canonical recovery")
    if lx is None:
        ensure(candidate["epigraph"] is None, "epigraph without canonical vectors")
        return
    ensure(len(lx) == t["n"] and len(ly) == t["m"], "canonical primal/dual shape")
    ensure(candidate["x"] == [lx[j] for j in t["x_original_indices"]], "wrong primal recovery map")
    y = [0] * problem["original"]["m"]
    for item in t["row_dual_map"]:
        y[item["original_row"]] += item["coefficient"] * ly[item["canonical_row"]]
    ensure(candidate["y"] == y, "wrong signed/weighted dual recovery")
    P, A = dense(t["P"]), dense(t["A"])
    z, px = _matvec(A, lx), _matvec(P, lx)
    atv = [sum(A[i][j] * ly[i] for i in range(t["m"])) for j in range(t["n"])]
    gradient = [px[j] + t["q"][j] + atv[j] for j in range(t["n"])]
    denominator = max([1] + list(map(abs, px)) + list(map(abs, t["q"])) + list(map(abs, atv)))
    ensure(
        max(map(abs, gradient), default=0) / denominator <= limit,
        "canonical stationarity/auxiliary cost invalid",
    )
    for i, (value, dual) in enumerate(zip(z, ly)):
        lo, up = t["lower"][i], t["upper"][i]
        ensure(
            (lo is None or value >= lo - hard_limit) and (up is None or value <= up + hard_limit),
            "canonical bound/soft slack violation",
        )
        ensure(
            (dual <= 1e-7 or up is not None) and (dual >= -1e-7 or lo is not None),
            "canonical dual toward absent side",
        )
        bound = up if dual > 0 else lo
        if dual and bound is not None:
            ensure(
                abs(dual * (value - bound)) / max(1, abs(dual * value), abs(dual * bound)) <= limit,
                "canonical complementarity",
            )
    canonical_objective = _dot(lx, px) / 2 + _dot(t["q"], lx)
    objective = original_metrics(problem["original"], candidate, 0)["objective"]
    ensure(
        abs(canonical_objective - objective) / max(1, abs(objective)) <= hard_limit,
        "auxiliary objective does not attain original penalty",
    )
    if t["kind"] != "G":
        ensure(candidate["epigraph"] is None, "unexpected peak diagnostics")
        return
    e = candidate["epigraph"]
    ensure(e is not None, "missing peak epigraph diagnostics")
    o = problem["original"]
    ensure(
        len(e["t"]) == len(e["mu"]) == len(o["groups"])
        and len(e["lambda_lower"]) == len(e["lambda_upper"]) == o["m"],
        "peak diagnostics shape",
    )
    lookup = {name: i for i, name in enumerate(t["row_order"])}
    variables = {name: i for i, name in enumerate(t["variable_order"])}
    z = _matvec(dense(o["A"]), candidate["x"])
    for g in o["groups"]:
        gid = g["group_id"]
        live = f"t:{gid}" in variables
        value = lx[variables[f"t:{gid}"]] if live else 0
        mu = -ly[lookup[f"nonnegative-t:{gid}"]] if live else 0
        ensure(
            e["t"][gid] == value and e["mu"][gid] == mu and value >= -1e-7 and mu >= -1e-7,
            "peak t/mu recovery",
        )
        multipliers = []
        for pos, i in enumerate(g["rows"]):
            for side, sign, bound in [("upper", 1, o["upper"][i]), ("lower", -1, o["lower"][i])]:
                multiplier = ly[lookup[f"{side}:{i}"]] if f"{side}:{i}" in lookup else 0
                ensure(e["lambda_" + side][i] == multiplier and multiplier >= -1e-7, "peak side multiplier")
                multipliers.append(multiplier)
                if bound is not None:
                    slack = value - sign * g[side + "_scale"][pos] * (z[i] - bound)
                    ensure(
                        abs(multiplier * slack)
                        / max(1, abs(multiplier * value), abs(multiplier * (value - slack)))
                        <= 1e-5,
                        "peak side complementarity",
                    )
        if live:
            denom = max(1, abs(g["linear"]), abs(g["quadratic"] * value), sum(map(abs, multipliers)), abs(mu))
            ensure(
                abs(g["linear"] + g["quadratic"] * value - sum(multipliers) - mu) / denom <= 1e-5
                and abs(mu * value) / max(1, abs(mu), abs(value)) <= 1e-5,
                "peak group stationarity",
            )


def exact_unbounded(original, certificate):
    ensure(
        certificate["kind"] == "exact-hard-qp-recession"
        and certificate["arithmetic"] == "exact-submitted-float64-dyadics"
        and certificate["screen_only"] is False,
        "screen alone cannot prove unbounded",
    )
    ensure(
        not any(original["penalty"]["soft"]) and not original["groups"],
        "exact certificate scope is hard-only",
    )
    P, A = dense(original["P"]), dense(original["A"])
    exact_curvature(P)
    x, d = certificate["anchor"], certificate["direction"]
    ensure(
        len(x) == len(d) == original["n"] and max(map(abs, d), default=0) == 1,
        "certificate nonzero normalized direction",
    )
    x, d = list(map(rational, x)), list(map(rational, d))
    ensure(all(sum(rational(v) * di for v, di in zip(row, d)) == 0 for row in P), "exact nonzero Pd")
    ensure(sum(rational(v) * di for v, di in zip(original["q"], d)) < 0, "exact nonnegative qd")
    for i, row in enumerate(A):
        ax = sum(rational(v) * xi for v, xi in zip(row, x))
        ad = sum(rational(v) * di for v, di in zip(row, d))
        lo, up = original["lower"][i], original["upper"][i]
        ensure(lo is None or (ax >= rational(lo) and ad >= 0), "exact lower anchor/recession violation")
        ensure(up is None or (ax <= rational(up) and ad <= 0), "exact upper anchor/recession violation")
    return True


def _oracle(problem, oracles, context):
    ensure(
        {o["backend"] for o in oracles} == {"stock_osqp", "clarabel", "piqp"} and len(oracles) == 3,
        "three required oracles missing",
    )
    ensure(
        all(
            o["accepted"]
            and o["status"] == "accepted"
            and o["candidate"] is not None
            and o["metrics"] is not None
            for o in oracles
        ),
        "oracle missing/failed candidate",
    )
    objectives = [original_metrics(problem["original"], o["candidate"], 0)["objective"] for o in oracles]
    f_ref = sorted(objectives)[1]
    ensure(
        (max(objectives) - min(objectives)) / max(1, *map(abs, objectives)) <= 1e-8,
        "oracle objective disagreement",
    )
    for o in oracles:
        ensure(
            o["accepted"]
            and o["status"] == "accepted"
            and o["reason"] is None
            and context.settings_hashes.get("oracle:" + o["backend"]) == o["settings_sha256"],
            "oracle failure/settings mismatch",
        )
        ensure(
            o["native_flag"] == {"stock_osqp": 1, "clarabel": "Solved", "piqp": "PIQP_SOLVED"}[o["backend"]],
            "oracle native failure",
        )
        ensure(
            o["result_sha256"]
            == digest(canonical_bytes({k: v for k, v in o.items() if k != "result_sha256"})),
            "oracle result identity",
        )
        _recovery(problem, o["candidate"], hard_limit=1e-8, limit=1e-8)
        expected = original_metrics(problem["original"], o["candidate"], f_ref)
        ensure(o["metrics"] == expected, "oracle copied/forged original metrics")
        ensure(
            all(
                expected[k] <= limit
                for k, limit in [("H", 1e-8), ("K", 1e-8), ("F", 1e-8), ("F_all", 1e-8), ("D", 1e-9)]
            ),
            "oracle tighter acceptance failed",
        )
    return f_ref


def _failed_oracles(oracles, context):
    ensure(
        len(oracles) == 3 and {o["backend"] for o in oracles} == {"stock_osqp", "clarabel", "piqp"},
        "failed oracle ledger incomplete",
    )
    ensure(any(not o["accepted"] for o in oracles), "oracle-failed state without failed reference")
    for o in oracles:
        ensure(
            context.settings_hashes.get("oracle:" + o["backend"]) == o["settings_sha256"],
            "failed oracle settings relabel",
        )
        ensure(
            o["accepted"] == (o["status"] == "accepted") and (o["reason"] is None) == o["accepted"],
            "oracle failure status contradiction",
        )
        ensure((o["candidate"] is None) == (o["metrics"] is None), "fabricated partial oracle solution")
        ensure(
            o["result_sha256"]
            == digest(canonical_bytes({k: v for k, v in o.items() if k != "result_sha256"})),
            "failed oracle result identity",
        )


def _labels(payload, context, document, stack):
    problem = dependency(payload["problem"], context, stack)
    split = dependency(payload["split"], context, stack)
    ensure(set(payload["fit_access"]) <= set(split["fit_source_ids"]), "held-out labels in fit path")
    ensure(
        payload["oracle_source_sha256"] == context.producer_source_sha256
        and payload["settings_sha256"] == context.settings_hashes.get("label:cold_daqp"),
        "label source/settings mismatch",
    )
    if payload["status"] == "oracle-failed":
        _failed_oracles(payload["oracle_results"], context)
        ensure(
            payload["reason"] is not None
            and all(
                payload[k] == [] for k in ["labels", "mask", "slack", "multipliers", "node_kind", "bound"]
            )
            and payload["cold_candidate"] is None,
            "fabricated labels after oracle failure",
        )
        return
    ensure(payload["reason"] is None, "accepted labels with failure reason")
    f_ref = _oracle(problem, payload["oracle_results"], context)
    candidate = payload["cold_candidate"]
    ensure(
        candidate is not None and payload["cold_native_flag"] in [1, 2], "missing genuine cold candidate flag"
    )
    _recovery(problem, candidate, hard_limit=1e-8, limit=1e-8)
    metric = original_metrics(problem["original"], candidate, f_ref)
    ensure(
        all(
            metric[k] <= lim
            for k, lim in [("H", 1e-8), ("K", 1e-8), ("F", 1e-8), ("F_all", 1e-8), ("D", 1e-9)]
        ),
        "cold label original acceptance",
    )
    t = problem["transform"]
    ensure(
        candidate["lifted_x"] is not None and exact_curvature(dense(t["P"]))[0] == t["n"],
        "label hard lift must be PD",
    )
    graph, G, nodes = graph_coordinates(t)
    slack, multipliers, labels, masks, bounds = (
        [0] * t["n"],
        [0] * t["n"],
        [None] * t["n"],
        [False] * t["n"],
        [0] * t["n"],
    )
    for row, mapping, features in zip(G, graph["row_map"], nodes[t["n"] :]):
        bound = features[1]
        d = bound - _dot(row, candidate["lifted_x"])
        value = candidate["lifted_y"][mapping["canonical_row"]]
        multiplier = value if mapping["equality"] else max(mapping["sign"] * value, 0)
        tau = 1e-7 * max(1, abs(bound))
        label = (
            1 if abs(d) <= tau and multiplier > 1e-7 else (0 if d > tau and abs(multiplier) <= 1e-7 else None)
        )
        if mapping["equality"]:
            label = None
        slack.append(d)
        multipliers.append(multiplier)
        labels.append(label)
        masks.append(label is not None)
        bounds.append(bound)
    ensure(
        payload["slack"] == slack
        and payload["multipliers"] == multipliers
        and payload["labels"] == labels
        and payload["mask"] == masks
        and payload["bound"] == bounds
        and payload["node_kind"] == graph["node_kind"],
        "false labels/ambiguity/equality/variable masks",
    )


def parameter_shapes(method, heads, authority):
    result = []
    if method == "learned_osqp":
        for head_id in heads:
            found = [h for h in authority.matrix["heads"] if h["id"] == head_id]
            ensure(len(found) == 1, "unknown checkpoint head")
            h = found[0]
            shapes = {
                "hidden1.weight": [128, h["feature_length"]],
                "hidden1.bias": [128],
                "hidden2.weight": [128, 128],
                "hidden2.bias": [128],
                "output.weight": [h["output_length"], 128],
                "output.bias": [h["output_length"]],
            }
            result.extend((head_id, name, shapes[name]) for name in sorted(shapes))
    else:
        ensure(heads == ["graph"], "GNN head identity")
        shapes = {}
        for layer, ni, no in [("input_layer", 4, 128), ("inner_layer", 128, 128), ("output_layer", 128, 1)]:
            for linear in ["lin1", "lin2", "lin3"]:
                shapes[f"{layer}.{linear}.weight"] = [no, ni]
                if linear != "lin2":
                    shapes[f"{layer}.{linear}.bias"] = [no]
        for norm in ["norm1", "norm2"]:
            shapes[norm + ".weight"] = [128]
            shapes[norm + ".bias"] = [128]
        result = [("graph", name, shapes[name]) for name in sorted(shapes)]
    return result


def numeric_file(value, context, *, dtype="float64-le"):
    ensure(
        value["format"] == "raw-" + dtype
        and value["path"].endswith(".f64" if dtype == "float64-le" else ".u8"),
        "executable/unknown numeric serializer",
    )
    path = safe_path(context.root, value["path"], must_exist=True)
    raw = path.read_bytes()
    ensure(len(raw) == value["byte_count"] and digest(raw) == value["sha256"], "missing/stale numeric file")
    if dtype == "float64-le":
        ensure(
            len(raw) % 8 == 0 and all(math.isfinite(v[0]) for v in struct.iter_unpack("<d", raw)),
            "nonfinite/malformed numeric weights",
        )
    return raw


def _checkpoint(payload, context, document, stack):
    dataset = dependency(payload["dataset"], context, stack)
    split = dependency(payload["split"], context, stack)
    ensure(
        payload["split"]["artifact_id"] and split["dataset"] == payload["dataset"],
        "checkpoint dataset/split identity",
    )
    features = [dependency(ref, context, stack) for ref in payload["features"]]
    ensure(all(f["split"] == payload["split"] for f in features), "checkpoint stale split")
    a, method, seed = payload["architecture"], payload["method"], payload["seed"]
    ensure(
        payload["learning_policy_sha256"]
        == context.authority.manifest["normative_sha256"]["learning-spec.md"],
        "changed loss/label/initialization policy",
    )
    ensure(
        a["method"] == method and a["dtype"] == "float64" and a["head_ids"] == sorted(set(a["head_ids"])),
        "architecture method/head identity",
    )
    if a["coverage"] == "single-head-contract-fixture":
        ensure(
            context.allow_fixture and method == "learned_osqp" and len(a["head_ids"]) == 1,
            "partial head bundle cannot be production",
        )
    elif a["coverage"] == "graph-contract-fixture":
        ensure(context.allow_fixture and method == "learned_daqp", "graph fixture cannot be production")
    else:
        expected_heads = (
            sorted(h["id"] for h in context.authority.matrix["heads"])
            if method == "learned_osqp"
            else ["graph"]
        )
        ensure(a["head_ids"] == expected_heads, "required head absent")
    expected = parameter_shapes(method, a["head_ids"], context.authority)
    ensure(
        [(p["head_id"], p["name"], p["shape"]) for p in a["parameters"]] == expected,
        "parameter names/shapes/order",
    )
    raw = numeric_file(payload["weights"], context)
    initial_raw = numeric_file(payload["initial_weights"], context)
    best_raw = numeric_file(payload["best_weights"], context)
    ensure(
        len(initial_raw) == len(best_raw) == len(raw)
        and digest(initial_raw) == payload["initial_weights_sha256"],
        "missing/stale initial or best numeric snapshot",
    )
    if payload["role"] in ["best", "final"]:
        ensure(raw == best_raw, "public selected checkpoint is not immutable best arrays")
    offset, rng = 0, []
    for p in a["parameters"]:
        count = math.prod(p["shape"])
        ensure(
            p["count"] == count and p["offset"] == offset and p["dtype"] == "float64-le",
            "parameter offsets/count/dtype",
        )
        chunk = raw[8 * offset : 8 * (offset + count)]
        ensure(len(chunk) == count * 8 and p["sha256"] == digest(chunk), "numeric parameter bytes mismatch")
        name, head = p["name"], p["head_id"]
        random = name.endswith(".weight") and not name.startswith("norm")
        stream = (
            int.from_bytes(
                hashlib.sha256(
                    f"softqp-learning-r2|{'L-1' if method == 'learned_osqp' else 'L-2'}|{seed}|{head}|{name}".encode()
                ).digest()[:8],
                "little",
            )
            % 2**63
        )
        ensure(
            p["initialization_seed"] == (stream if random else 0),
            "constructor123/wrong parameter initialization stream",
        )
        expected_rule = (
            (
                "xavier-output-gain1"
                if name.startswith("output")
                else ("xavier-relu-sqrt2" if method == "learned_osqp" else "xavier-leakyrelu-slope0.1")
            )
            if random
            else (
                "ones"
                if name.startswith("norm") and name.endswith("weight")
                else ("train-log-positive-odds" if name == "output_layer.lin3.bias" else "zeros")
            )
        )
        ensure(p["initialization_rule"] == expected_rule, "parameter initializer semantics")
        if random:
            rng.append((head + "/" + name, stream))
        offset += count
    ensure(a["parameter_count"] == offset and len(raw) == offset * 8, "architecture weight byte count")
    ensure(payload["architecture_sha256"] == digest(canonical_bytes(a)), "stale architecture digest")
    ensure([(r["parameter"], r["seed"]) for r in payload["rng"]["streams"]] == rng, "RNG stream inventory")
    numeric_file(payload["rng"]["state_file"], context, dtype="uint8")
    optimizer = payload["optimizer"]
    state = numeric_file(optimizer["state_file"], context)
    ensure(len(state) == 2 * len(raw), "AdamW moment state shape")
    ensure(
        optimizer["tensors"]
        == [
            {
                "parameter": h + "/" + name,
                "shape": shape,
                "first_moment_offset": off,
                "second_moment_offset": off + offset,
            }
            for (h, name, shape), off in zip(expected, [p["offset"] for p in a["parameters"]])
        ],
        "AdamW moment coordinate map",
    )
    ensure(
        {
            k: optimizer[k]
            for k in ["name", "learning_rate", "weight_decay", "beta1", "beta2", "eps", "amsgrad"]
        }
        == {
            "name": "AdamW",
            "learning_rate": 0.001,
            "weight_decay": 0.0001 if method == "learned_osqp" else 0.01,
            "beta1": 0.9,
            "beta2": 0.999,
            "eps": 1e-8,
            "amsgrad": False,
        },
        "optimizer definition changed",
    )
    norms = [f["normalizer"]["sha256"] for f in features if f["normalizer"] is not None]
    ensure(
        payload["normalizer_sha256"] == norms and len(set(norms)) == len(norms), "stale checkpoint normalizer"
    )
    ensure(
        {f["head_id"] for f in features}
        == (set(a["head_ids"]) if method == "learned_osqp" else {f["head_id"] for f in features})
        and bool(features),
        "missing head feature contract",
    )
    ensure(
        all((f["representation"] == "mlp-v1") == (method == "learned_osqp") for f in features),
        "checkpoint feature architecture mismatch",
    )
    ensure(
        set(payload["epoch"]) == set(payload["best_epoch"]) == set(a["head_ids"]),
        "checkpoint head progress inventory",
    )
    ensure(
        all(0 <= payload["best_epoch"][head] <= payload["epoch"][head] <= 100 for head in a["head_ids"]),
        "checkpoint epoch history",
    )
    history = payload["history"]
    ensure(
        [(h["head_id"], h["epoch"]) for h in history]
        == [(head, epoch) for head in a["head_ids"] for epoch in range(payload["epoch"][head] + 1)],
        "missing/duplicate head epoch history",
    )
    for head in a["head_ids"]:
        entries = [h for h in history if h["head_id"] == head]
        ensure(
            payload["best_epoch"][head]
            == min(entries, key=lambda h: (h["validation_objective"], h["epoch"]))["epoch"],
            "best epoch alias/selection",
        )
    ensure(
        optimizer["step_count"] == sum(h["optimizer_steps"] for h in history), "resume optimizer step count"
    )
    if payload["training_evidence"] in ["untrained-contract-fixture", "initialized"]:
        ensure(
            (context.allow_fixture or payload["training_evidence"] == "initialized")
            and payload["role"] == "initial"
            and all(v == 0 for v in payload["epoch"].values())
            and optimizer["step_count"] == 0
            and payload["initial_weights_sha256"] == payload["weights"]["sha256"],
            "fixture/initialized checkpoint misrepresented as trained",
        )
    else:
        ensure(
            all(v > 0 for v in payload["epoch"].values())
            and payload["initial_weights_sha256"] != payload["weights"]["sha256"]
            and all(h["gradient_finite"] for h in history)
            and any(h["gradient_nonzero"] for h in history),
            "no genuine training evidence",
        )
    if not context.allow_fixture:
        ensure(
            payload["training_evidence"] in ["real-produced", "initialized"]
            and a["coverage"] == "complete-bundle",
            "fixture/partial model cannot be available",
        )
    if method == "learned_osqp":
        ensure(payload["class_statistics"] is None, "invented classifier statistics for L2WS")
    else:
        stats = payload["class_statistics"]
        ensure(stats is not None and bool(stats["labels"]), "missing GNN train class statistics")
        label_data = []
        for ref in stats["labels"]:
            label = dependency(ref, context, stack)
            problem = dependency(label["problem"], context, stack)
            ensure(
                label["split"] == payload["split"]
                and label["status"] == "accepted"
                and problem["source"]["split"] == "train",
                "test/failed labels in class fit",
            )
            label_data.append((label, problem["source"]))
        ensure(
            len({l["problem"]["artifact_id"] for l, s in label_data}) == len(label_data),
            "duplicate class-fit label",
        )
        expected_labels = {
            e["problem"]["artifact_id"]
            for e in dataset["problems"]
            if e["source"]["split"] == "train"
            and context.authority.row(e["source"]["family"], e["source"]["regime"])["methods"][
                "learned_daqp"
            ]["eligible"]
        }
        ensure(
            {l["problem"]["artifact_id"] for l, s in label_data} == expected_labels,
            "missing training class-fit label population",
        )
        weighted = _source_frame_weights([s for l, s in label_data])
        mass = [0.0, 0.0]
        for (label, source), weight in zip(label_data, weighted):
            active = [v for v, mask in zip(label["labels"], label["mask"]) if mask]
            if active:
                for cls in [0, 1]:
                    mass[cls] += weight * active.count(cls) / len(active)
        ensure(all(v > 0 for v in mass), "zero training class cannot be qualified")
        total = sum(mass)
        ensure(
            [stats["N0"], stats["N1"], stats["weight0"], stats["weight1"], stats["positive_prior"]]
            == [mass[0], mass[1], total / (2 * mass[0]), total / (2 * mass[1]), mass[1] / total],
            "wrong source-weighted class loss/prior",
        )


def _source_frame_weights(sources):
    cells = {}
    for source in sources:
        cells.setdefault((source["family"], source["regime"]), set()).add(source["source_id"])
    families = {f for f, r in cells}
    return [
        1
        / (
            len(families)
            * sum(f == s["family"] for f, r in cells)
            * len(cells[(s["family"], s["regime"])])
            * s["frame_count"]
        )
        for s in sources
    ]


def _calibration(payload, context, document, stack):
    checkpoint = dependency(payload["checkpoint"], context, stack)
    split = dependency(payload["split"], context, stack)
    ensure(
        checkpoint["split"] == payload["split"] and checkpoint["method"] == payload["method"],
        "stale checkpoint/calibration identity",
    )
    dataset = dependency(split["dataset"], context, stack)
    eligible = [
        entry
        for entry in dataset["problems"]
        if entry["source"]["split"] == "calibration"
        and context.authority.row(entry["source"]["family"], entry["source"]["regime"])["methods"][
            payload["method"]
        ]["eligible"]
    ]
    calibration_ids = {entry["source"]["source_id"] for entry in eligible}
    ensure(
        payload["source_ids"] == sorted(set(payload["source_ids"]))
        and set(payload["source_ids"]) <= calibration_ids,
        "test-derived calibration",
    )
    if payload["method"] == "learned_osqp":
        ensure(payload["observations"] == [], "L2WS has no threshold observations")
        ensure(
            payload["applicability"] == "not-applicable"
            and payload["threshold_grid"]
            == payload["scores"]
            == payload["source_ids"]
            == payload["class_counts"]
            == []
            and payload["selected_threshold"] is None
            and payload["mask_count"] == 0
            and payload["objective"] == payload["tie"] == "not-applicable",
            "L2WS calibration must be explicit not-applicable",
        )
        ensure(
            payload["metrics"]
            == {"f1": None, "brier": None, "ece": None, "undefined_reason": "not-applicable"},
            "invented L2WS classification metrics",
        )
    else:
        grid = [i / 10 for i in range(1, 10)]
        ensure(
            payload["applicability"] == "threshold"
            and payload["threshold_grid"] == grid
            and len(payload["scores"]) == 9
            and all(0 <= s <= 1 for s in payload["scores"]),
            "calibration candidate grid",
        )
        ensure(
            set(payload["source_ids"]) == calibration_ids
            and payload["mask_count"] > 0
            and len(payload["class_counts"]) == 2
            and sum(payload["class_counts"]) == payload["mask_count"],
            "missing calibration masks/classes",
        )
        ensure(
            payload["selected_threshold"] == max(zip(payload["scores"], grid))[1]
            and payload["objective"] == "source-weighted-macro-F1"
            and payload["tie"] == "largest-threshold",
            "calibration threshold/tie changed",
        )
        ensure(
            payload["metrics"]["f1"] == max(payload["scores"])
            and all(
                payload["metrics"][k] is None or 0 <= payload["metrics"][k] <= 1
                for k in ["f1", "brier", "ece"]
            ),
            "calibration metric domain",
        )
        observations = []
        for observation in payload["observations"]:
            label = dependency(observation["labels"], context, stack)
            problem = dependency(label["problem"], context, stack)
            ensure(
                label["status"] == "accepted"
                and label["split"] == payload["split"]
                and problem["source"]["split"] == "calibration",
                "test/failed calibration observation",
            )
            ensure(len(observation["probabilities"]) == len(label["labels"]), "calibration probability shape")
            observations.append((observation, label, problem["source"]))
        ensure(
            len({l["problem"]["artifact_id"] for o, l, s in observations}) == len(observations)
            and {l["problem"]["artifact_id"] for o, l, s in observations}
            == {e["problem"]["artifact_id"] for e in eligible},
            "missing/duplicate calibration frame",
        )
        counts = [
            sum(sum(mask and y == cls for y, mask in zip(l["labels"], l["mask"])) for o, l, s in observations)
            for cls in [0, 1]
        ]
        ensure(
            payload["class_counts"] == counts and payload["mask_count"] == sum(counts),
            "calibration mask/class counts",
        )
        weights = _source_frame_weights([s for o, l, s in observations])
        macro_scores = []
        for threshold in grid:
            per_source = {}
            for observation, label, source in observations:
                counts = per_source.setdefault(source["source_id"], [0, 0, 0, source])
                for probability, y, mask in zip(observation["probabilities"], label["labels"], label["mask"]):
                    if mask:
                        predicted = probability > threshold
                        counts[0] += (predicted and y == 1) / source["frame_count"]
                        counts[1] += (predicted and y == 0) / source["frame_count"]
                        counts[2] += (not predicted and y == 1) / source["frame_count"]
            source_weights = _source_frame_weights([{**v[3], "frame_count": 1} for v in per_source.values()])
            macro_scores.append(
                sum(
                    w * (2 * v[0] / (2 * v[0] + v[1] + v[2]) if 2 * v[0] + v[1] + v[2] else 0)
                    for w, v in zip(source_weights, per_source.values())
                )
            )
        ensure(payload["scores"] == macro_scores, "forged calibration threshold scores")
        points = []
        for (observation, label, source), weight in zip(observations, weights):
            count = sum(label["mask"])
            if count:
                points.extend(
                    (p, y, weight / count)
                    for p, y, mask in zip(observation["probabilities"], label["labels"], label["mask"])
                    if mask
                )
        mass = sum(w for p, y, w in points)
        brier = sum(w * (p - y) ** 2 for p, y, w in points) / mass
        ece = 0
        for bin_index in range(10):
            selected = [(p, y, w) for p, y, w in points if min(int(p * 10), 9) == bin_index]
            if selected:
                ece += abs(sum(w * p for p, y, w in selected) - sum(w * y for p, y, w in selected)) / mass
        ensure(
            payload["metrics"]["brier"] == brier
            and payload["metrics"]["ece"] == ece
            and payload["metrics"]["undefined_reason"] is None,
            "forged calibration Brier/ECE",
        )


def _method_result(payload, context, document, stack):
    problem = dependency(payload["problem"], context, stack)
    source, t = problem["source"], problem["transform"]
    ensure(
        problem["expected_control"] is not None or source["split"] == "test",
        "primary method results require a held-out test source",
    )
    method, seed, family, regime, unit, frame = payload["key"]
    ensure(
        payload["method"] == method
        and (family, regime, unit, frame)
        == (source["family"], source["regime"], source["unit_index"], source["frame"]),
        "result input/key relabel",
    )
    ensure(seed in (SEEDS if method in LEARNED else (0,)), "method/network seed mismatch")
    row = context.authority.row(family, regime)
    base_method = {
        "cold_osqp": "learned_osqp",
        "cold_daqp": "learned_daqp",
        "previous_osqp": "learned_osqp",
        "previous_daqp": "learned_daqp",
    }.get(method, method)
    ensure(base_method in row["methods"], "unknown method")
    if method.startswith("previous_"):
        ensure(family == "N12", "previous-vector control outside N12")
    cell = row["methods"][base_method]
    if problem["expected_control"] is not None and method in {"lifted", "clarabel", "proxqp", "piqp"}:
        controls = {v["id"]: v for v in context.authority.controls}
        control = controls.get(problem["expected_control"])
        ensure(
            (context.allow_fixture and problem["expected_control"].startswith("contract-fixture:"))
            or control is not None
            and (
                method in control["targets"]
                or {"recession-certificate-reader", "public-status-reader"} <= set(control["targets"])
            ),
            "method not a declared diagnostic target",
        )
        cell = {"eligible": True, "transform": t["kind"], "reason": None}
    ensure(
        payload["semantic_transform"] == (cell["transform"] if cell["eligible"] else "incompatible"),
        "forged semantic transform",
    )
    ensure(
        payload["dimensions"]
        == {
            "original_n": problem["original"]["n"],
            "original_m": problem["original"]["m"],
            "canonical_n": t["n"],
            "canonical_m": t["m"],
        },
        "result dimensions",
    )
    ensure(
        payload["metric_policy_sha256"]
        == context.authority.manifest["normative_sha256"]["numerical-spec.md"],
        "different original metric policy",
    )
    if not cell["eligible"]:
        ensure(
            payload["diagnostic_native_flag"] is None, "incompatible cells must not invent native execution"
        )
        ensure(
            payload["status"] == "incompatible"
            and payload["reason"] == cell["reason"]
            and payload["trials"] == []
            and payload["certificate"] is None,
            "incompatibility not predeclared",
        )
        return
    ensure(payload["status"] != "incompatible", "missing runtime reclassified incompatible")
    ensure(
        payload["settings_sha256"] == context.settings_hashes.get(method),
        "solver settings/source lock mismatch",
    )
    ensure(
        (payload["status"] == "accepted") == (payload["reason"] is None), "result status/reason contradiction"
    )
    if method in LEARNED:
        if payload["status"] == "missing":
            ensure(
                payload["checkpoint"] is None or payload["calibration"] is None,
                "missing learned dependency not named",
            )
        else:
            ensure(
                payload["checkpoint"] is not None
                and payload["calibration"] is not None
                and payload["injected_state"] is not None,
                "missing model/calibration/injection",
            )
            checkpoint = dependency(payload["checkpoint"], context, stack)
            calibration = dependency(payload["calibration"], context, stack)
            checkpoint_split = dependency(checkpoint["split"], context, stack)
            ensure(
                any(
                    a["split"] == "test"
                    and a["source_id"] == source["source_id"]
                    and payload["problem"]["artifact_id"] in a["problem_ids"]
                    for a in checkpoint_split["assignments"]
                ),
                "inference input is outside the checkpoint held-out split",
            )
            ensure(
                checkpoint["method"] == method
                and checkpoint["seed"] == seed
                and calibration["checkpoint"] == payload["checkpoint"],
                "stale model/calibration/seed",
            )
            if not context.allow_fixture:
                ensure(
                    checkpoint["role"] in ["best", "final"]
                    and checkpoint["training_evidence"] == "real-produced",
                    "initialized/latest model is not qualified public inference",
                )
            injected = payload["injected_state"]
            if method == "learned_osqp":
                ensure(
                    len(injected["x"]) == t["n"]
                    and len(injected["y"]) == t["m"]
                    and injected["scores"] == injected["flags"] == [],
                    "wrong learned iterate shape",
                )
            else:
                graph, _, _ = graph_coordinates(t)
                ensure(
                    len(injected["scores"]) == len(graph["node_kind"])
                    and all(0 <= s <= 1 for s in injected["scores"]),
                    "graph score shape/domain",
                )
                expected_flags = [
                    5 if kind == "equality" else int(score > calibration["selected_threshold"])
                    for kind, score in zip(graph["node_kind"][t["n"] :], injected["scores"][t["n"] :])
                ]
                ensure(
                    injected["flags"] == expected_flags and injected["x"] == injected["y"] == [],
                    "equality/predicted flag mutation",
                )
    else:
        ensure(
            payload["checkpoint"] is None
            and payload["calibration"] is None
            and payload["injected_state"] is None,
            "fake deterministic checkpoint",
        )
    if payload["status"] == "unbounded":
        ensure(payload["diagnostic_native_flag"] is not None, "unbounded diagnostic raw native flag missing")
        ensure(
            problem["expected_control"] is not None
            and payload["certificate"] is not None
            and not payload["trials"],
            "public unbounded missing exact diagnostic proof",
        )
        exact_unbounded(problem["original"], payload["certificate"])
        return
    if payload["status"] == "inconclusive":
        ensure(
            problem["expected_control"] is not None and payload["trials"] == [] and payload["oracles"] == [],
            "inconclusive diagnostic cannot invent timed trials or accepted references",
        )
        ensure(
            payload["certificate"] is None or payload["certificate"]["screen_only"] is True,
            "inconclusive record must not claim an established exact certificate",
        )
        return
    ensure(
        payload["diagnostic_native_flag"] is None,
        "finite/missing trial flags belong in the complete trial ledger",
    )
    ensure(payload["certificate"] is None, "certificate contradicts finite/non-unbounded result")
    expected_trials = [("warmup", i) for i in range(2)] + [("measured", i) for i in range(5)]
    ensure(
        [(trial["phase"], trial["repetition"]) for trial in payload["trials"]] == expected_trials,
        "missing/duplicate/extra trial key",
    )
    if payload["status"] == "oracle-failed":
        _failed_oracles(payload["oracles"], context)
    if payload["status"] == "missing":
        ensure(payload["oracles"] == [], "missing execution has invented reference observations")
    f_ref = (
        _oracle(problem, payload["oracles"], context)
        if payload["status"] not in ["oracle-failed", "missing"]
        else None
    )
    native_success = {
        "lifted": [1],
        "generalized": [1],
        "asymmetric": [1],
        "directional": [1],
        "daqp": [1, 2],
        "flex": [1],
        "elastiqp": ["Solved"],
        "clarabel": ["Solved"],
        "proxqp": ["PROXQP_SOLVED"],
        "piqp": ["PIQP_SOLVED"],
        "learned_osqp": [1],
        "learned_daqp": [1, 2],
        "cold_osqp": [1],
        "previous_osqp": [1],
        "cold_daqp": [1, 2],
        "previous_daqp": [1, 2],
    }
    for trial in payload["trials"]:
        ensure(
            trial["status"] not in ["incompatible", "unbounded", "inconclusive"],
            "trial cannot invent semantic/public certificate state",
        )
        ensure(
            trial["clock"] == ("contract-fixture" if context.allow_fixture else "perf-counter"),
            "fictional measured time",
        )
        ensure(trial["full_cost"] == sum(trial["timing"].values()), "full-cost missing phase/retry")
        ensure(
            (trial["status"] == "accepted") == (trial["reason"] is None), "trial state/reason contradiction"
        )
        if trial["status"] == "accepted":
            ensure(trial["full_cost"] <= 10, "accepted trial exceeded deadline")
            ensure(
                trial["native_flag"] in native_success[method]
                and f_ref is not None
                and trial["candidate"] is not None
                and trial["metrics"] is not None
                and trial["full_cost"] > 0,
                "native flag without independently checked metrics",
            )
            if cell["transform"] in {"S", "A", "G"}:
                ensure(trial["candidate"]["lifted_x"] is not None, "missing canonical recovery evidence")
            _recovery(problem, trial["candidate"])
            metric = original_metrics(problem["original"], trial["candidate"], f_ref)
            ensure(trial["metrics"] == metric, "forged/copied candidate objective/metrics")
            ensure(
                all(
                    metric[k] <= threshold
                    for k, threshold in [
                        ("H", 1e-6),
                        ("G", 1e-6),
                        ("K", 1e-5),
                        ("F", 1e-5),
                        ("F_all", 1e-5),
                        ("D", 1e-7),
                    ]
                ),
                "original-space acceptance rejected",
            )
        else:
            ensure(
                trial["candidate"] is None
                and trial["metrics"] is None
                or trial["candidate"] is not None
                and trial["metrics"] is not None,
                "partial failed candidate metrics",
            )
            if trial["candidate"] is not None:
                ensure(f_ref is not None, "oracle failure cannot support candidate metrics")
                _recovery(problem, trial["candidate"])
                ensure(
                    trial["metrics"] == original_metrics(problem["original"], trial["candidate"], f_ref),
                    "forged failed-candidate metrics",
                )
        if method == "learned_daqp" and payload["status"] != "missing":
            flags = payload["injected_state"]["flags"]
            attempts = trial["attempt_flags"]
            ensure(
                attempts
                and attempts[0] == flags
                and len(attempts) == len(trial["attempt_native_flags"])
                and len(attempts) <= flags.count(1) + 1,
                "unbounded/ignored graph initialization repair",
            )
            scores = payload["injected_state"]["scores"][t["n"] :]
            removed = []
            for previous, following, native in zip(attempts, attempts[1:], trial["attempt_native_flags"]):
                ensure(native == -6, "retry after unregistered native failure")
                candidates = [i for i, flag in enumerate(previous) if flag == 1]
                ensure(bool(candidates), "duplicate cold fallback")
                index = min(candidates, key=lambda i: (scores[i], i))
                expected = previous[:]
                expected[index] = 0
                ensure(following == expected, "wrong removal/equality flag")
                removed.append(index)
            ensure(
                trial["removed_rows"] == removed
                and trial["fallback_count"] == sum(not any(v == 1 for v in a) for a in attempts),
                "retry/fallback receipt mismatch",
            )
        else:
            ensure(
                trial["attempt_flags"] == trial["removed_rows"] == trial["attempt_native_flags"] == []
                and trial["fallback_count"] == 0,
                "unregistered retry metadata",
            )
    ensure(
        (payload["status"] == "accepted") == all(t["status"] == "accepted" for t in payload["trials"]),
        "dropped failed repetition",
    )
    aggregate = next(
        s
        for s in ["oracle-failed", "missing", "timeout", "failed", "accuracy-rejected", "accepted"]
        if any(t["status"] == s for t in payload["trials"])
    )
    ensure(payload["status"] == aggregate, "aggregate result status hides a trial state")


def _evaluation(payload, context, document, stack):
    results = [dependency(ref, context, stack) for ref in payload["results"]]
    paired_inputs = {}
    for result in results:
        slot = tuple(result["key"][2:])
        identity = (result["problem"]["artifact_id"], result["problem"]["sha256"])
        ensure(
            slot not in paired_inputs or paired_inputs[slot] == identity,
            "paired methods/controls used different source-frame inputs",
        )
        paired_inputs[slot] = identity
    ensure(
        all(dependency(r["problem"], context, stack)["expected_control"] is None for r in results),
        "diagnostic relabeled as primary population",
    )
    keys = [tuple(r["key"]) for r in results]
    expected = context.expected_result_keys
    ensure(
        len(keys) == len(set(keys)) and set(keys) == set(expected),
        "missing/duplicate/extra expected status key",
    )
    ensure(
        payload["expected_keyset_sha256"]
        == digest(b"".join(canonical_bytes(list(k)) for k in sorted(expected))),
        "expected-keyset identity",
    )
    counts = Counter(r["status"] for r in results)
    failed = len(results) - counts["accepted"] - counts["incompatible"]
    ensure(
        payload["denominators"]
        == {
            "expected": len(expected),
            "accepted": counts["accepted"],
            "failed": failed,
            "incompatible": counts["incompatible"],
        },
        "failure denominator mutation",
    )
    diagnostic_keys = [tuple(d["key"]) for d in payload["diagnostics"]]
    ensure(
        len(diagnostic_keys) == len(set(diagnostic_keys))
        and set(diagnostic_keys) == set(context.expected_diagnostic_keys),
        "missing/duplicate/extra diagnostic key",
    )
    control_by_id = {d["id"]: d for d in context.authority.controls}
    for diagnostic in payload["diagnostics"]:
        key = tuple(diagnostic["key"])
        control = control_by_id[key[0]]
        ensure(
            key[1] in control["targets"] and diagnostic["fixture_sha256"] == digest(canonical_bytes(control)),
            "diagnostic source/target relabel",
        )
        outcome = control.get("outcomes", {}).get(key[1], control["expected"])
        ensure(diagnostic["expected_outcome"] == outcome, "diagnostic expected outcome changed")
        if diagnostic["state"] == "missing":
            ensure(
                diagnostic["evidence"] is None
                and diagnostic["observed_outcome"] is None
                and diagnostic["reason"] is not None,
                "missing diagnostic has fabricated evidence",
            )
        else:
            evidence = diagnostic["evidence"]
            ensure(evidence is not None, "diagnostic evidence missing")
            raw = safe_path(context.root, evidence["path"], must_exist=True).read_bytes()
            ensure(
                len(raw) == evidence["byte_count"]
                and digest(raw) == evidence["sha256"] == context.diagnostic_evidence.get(key),
                "diagnostic evidence not independently sealed",
            )
            try:
                raw.decode("utf-8")
            except UnicodeError as error:
                raise ContractError("diagnostic evidence UTF8") from error
            ensure(b"\r" not in raw and raw.endswith(b"\n"), "diagnostic log must use LF")
            ensure(
                (diagnostic["observed_outcome"] == outcome) == (diagnostic["state"] == "passed"),
                "diagnostic outcome/pass contradiction",
            )
            ensure(
                (diagnostic["reason"] is None) == (diagnostic["state"] == "passed"),
                "diagnostic failure reason missing",
            )
    diag_counts = Counter(d["state"] for d in payload["diagnostics"])
    ensure(
        payload["diagnostic_denominators"]
        == {
            "expected": len(diagnostic_keys),
            "passed": diag_counts["passed"],
            "failed": diag_counts["failed"],
            "missing": diag_counts["missing"],
        },
        "dropped diagnostic failure denominator",
    )
    medians = {}
    oracle_sets = {}
    for r in results:
        if r["oracles"]:
            identity = tuple(sorted((o["backend"], o["result_sha256"]) for o in r["oracles"]))
            problem_id = r["problem"]["artifact_id"]
            ensure(
                problem_id not in oracle_sets or oracle_sets[problem_id] == identity,
                "reference substituted for a candidate",
            )
            oracle_sets[problem_id] = identity
        if r["status"] == "accepted":
            times = sorted(t["full_cost"] for t in r["trials"] if t["phase"] == "measured")
            ensure(len(times) == 5, "incomplete measured times")
            medians[tuple(r["key"])] = times[2]
    totals = []
    for method in sorted(LEARNED):
        for seed, family, regime, unit in sorted({tuple(k[1:5]) for k in keys if k[0] == method}):
            candidate_keys = [k for k in keys if k[:5] == (method, seed, family, regime, unit)]
            if candidate_keys and all(k in medians for k in candidate_keys):
                cold = "cold_osqp" if method == "learned_osqp" else "cold_daqp"
                cold_keys = [(cold, 0, family, regime, unit, k[5]) for k in candidate_keys]
                if all(k in medians for k in cold_keys):
                    learned_cost, cold_cost = (
                        sum(medians[k] for k in candidate_keys),
                        sum(medians[k] for k in cold_keys),
                    )
                    totals.append(
                        {
                            "method": method,
                            "seed": seed,
                            "family": family,
                            "regime": regime,
                            "source_index": unit,
                            "learned": learned_cost,
                            "cold": cold_cost,
                            "reduction": trajectory_reduction([cold_cost], [learned_cost]),
                        }
                    )
    ensure(payload["source_totals"] == totals, "wrong trajectory totals/frame-ratio reduction")
    ensure(
        [h["method"] for h in payload["hypotheses"]] == ["learned_osqp", "learned_daqp"],
        "missing/duplicate learned hypotheses",
    )
    draw_files = payload["bootstrap"]["draw_files"]
    ensure(len({d["method"] for d in draw_files}) == len(draw_files), "duplicate bootstrap draw artifact")
    ensure(
        payload["bootstrap"]["draws_sha256"] == (digest(canonical_bytes(draw_files)) if draw_files else None),
        "bootstrap raw draw manifest identity",
    )
    for hypothesis in payload["hypotheses"]:
        method = hypothesis["method"]
        available = [v for v in totals if v["method"] == method]
        cold = "cold_osqp" if method == "learned_osqp" else "cold_daqp"
        primary_failed = (
            any(
                r["status"] not in ["accepted", "incompatible"]
                for r in results
                if r["method"] in [method, cold]
            )
            or diag_counts["failed"] > 0
            or diag_counts["missing"] > 0
        )
        if primary_failed or not available:
            ensure(
                hypothesis["estimate"] is None
                and hypothesis["interval"] is None
                and not hypothesis["qualified"]
                and hypothesis["reason"] is not None,
                "compatible failure averaged away",
            )
        else:
            by_seed = {}
            for seed in SEEDS:
                families = sorted({v["family"] for v in available if v["seed"] == seed})
                family_values = []
                for family in families:
                    regimes = sorted(
                        {v["regime"] for v in available if v["seed"] == seed and v["family"] == family}
                    )
                    family_values.append(
                        sum(
                            sum(
                                v["reduction"]
                                for v in available
                                if (v["seed"], v["family"], v["regime"]) == (seed, family, regime)
                            )
                            / sum(
                                (v["seed"], v["family"], v["regime"]) == (seed, family, regime)
                                for v in available
                            )
                            for regime in regimes
                        )
                        / len(regimes)
                    )
                if family_values:
                    by_seed[seed] = sum(family_values) / len(family_values)
            ensure(len(by_seed) == 3, "missing learned seed in primary statistic")
            ensure(hypothesis["estimate"] == sum(by_seed.values()) / 3, "wrong balanced primary estimator")
            draw = next((d["file"] for d in draw_files if d["method"] == method), None)
            if draw is None:
                ensure(
                    hypothesis["interval"] is None
                    and not hypothesis["qualified"]
                    and hypothesis["reason"] == "bootstrap-not-produced",
                    "bootstrap artifact absent; cannot claim interval/qualification",
                )
            else:
                interval = _bootstrap_interval(available, method, draw, context)
                ensure(
                    hypothesis["interval"] == interval
                    and hypothesis["qualified"] == (interval[0] > 0.10)
                    and hypothesis["reason"] is None,
                    "incorrect crossed bootstrap/qualification",
                )


def trajectory_reduction(cold_frame_medians, learned_frame_medians):
    ensure(len(cold_frame_medians) == len(learned_frame_medians) > 0, "trajectory cost shape")
    ensure(
        all(math.isfinite(v) and v > 0 for v in cold_frame_medians + learned_frame_medians),
        "invalid full trajectory cost",
    )
    return 1 - sum(learned_frame_medians) / sum(cold_frame_medians)


def _bootstrap_interval(totals, method, draw, context):
    """Read/verify existing index draws; never samples scientific inputs."""
    import numpy as np

    raw = numeric_file(draw, context, dtype="uint8")
    cells = sorted({(v["family"], v["regime"]) for v in totals})
    source_count = (
        8
        if not context.allow_fixture
        else len({v["source_index"] for v in totals if (v["family"], v["regime"]) == cells[0]})
    )
    ensure(
        source_count > 0
        and all(
            {v["source_index"] for v in totals if (v["family"], v["regime"]) == cell}
            == set(range(source_count))
            for cell in cells
        ),
        "bootstrap incomplete source stratum",
    )
    width = 3 + source_count * len(cells)
    ensure(len(raw) == 10000 * width, "bootstrap draw shape")
    draws = np.frombuffer(raw, dtype=np.uint8).reshape(10000, width)
    rng = np.random.Generator(
        np.random.PCG64(np.random.SeedSequence([20261105, 41100, 0 if method == "learned_osqp" else 1]))
    )
    families = sorted({f for f, r in cells})
    lookup = {(v["seed"], v["family"], v["regime"], v["source_index"]): v["reduction"] for v in totals}
    samples = []
    for draw_row in draws:
        seed_draws = rng.integers(0, 3, size=3)
        ensure(list(draw_row[:3]) == list(seed_draws), "bootstrap seed draw receipt mismatch")
        source_draws = {}
        for i, cell in enumerate(cells):
            indices = rng.integers(0, source_count, size=source_count)
            ensure(
                list(draw_row[3 + i * source_count : 3 + (i + 1) * source_count]) == list(indices),
                "bootstrap crossed source draws mismatch",
            )
            source_draws[cell] = indices
        values = []
        for seed_index in seed_draws:
            per_family = []
            for family in families:
                regimes = [r for f, r in cells if f == family]
                per_family.append(
                    sum(
                        sum(
                            lookup[(SEEDS[int(seed_index)], family, regime, int(u))]
                            for u in source_draws[(family, regime)]
                        )
                        / source_count
                        for regime in regimes
                    )
                    / len(regimes)
                )
            values.append(sum(per_family) / len(per_family))
        samples.append(sum(values) / 3)
    samples.sort()

    def quantile(p):
        h = 9999 * p
        j = math.floor(h)
        return (1 - (h - j)) * samples[j] + (h - j) * samples[min(j + 1, 9999)]

    return [quantile(0.0125), quantile(0.9875)]


def _export_index(payload, context, document, stack):
    evaluation = dependency(payload["evaluation"], context, stack)
    evaluated = {ref["artifact_id"]: ref for ref in evaluation["results"]}
    ensure(
        [c["case_id"] for c in payload["cases"]] == sorted(set(c["case_id"] for c in payload["cases"])),
        "duplicate/reordered replay cases",
    )
    for case in payload["cases"]:
        ensure(bool(case["results"]), "empty replay case")
        for ref in case["results"]:
            ensure(evaluated.get(ref["artifact_id"]) == ref, "unevaluated replay result")
            result = dependency(ref, context, stack)
            problem = dependency(result["problem"], context, stack)
            ensure(
                problem["source"]["family"] == case["case_id"]
                and case["units"] == problem["original"]["units"],
                "replay selected-case/units substitution",
            )
    methods = []
    for card in payload["model_cards"]:
        checkpoint = dependency(card["checkpoint"], context, stack)
        calibration = dependency(card["calibration"], context, stack)
        ensure(
            card["method"] == checkpoint["method"] and calibration["checkpoint"] == card["checkpoint"],
            "model card stale identity",
        )
        if not context.allow_fixture:
            ensure(
                checkpoint["training_evidence"] == "real-produced"
                and checkpoint["role"] in ["best", "final"],
                "untrained model card cannot be public available",
            )
        methods.append(card["method"])
    ensure(len(methods) == len(set(methods)), "duplicate model card")
    ensure(
        payload["bounds_sha256"] == digest(canonical_bytes(payload["supported_controls"])),
        "replay control bounds hash",
    )
    ensure(
        len({c["control_id"] for c in payload["supported_controls"]}) == len(payload["supported_controls"]),
        "duplicate replay control",
    )
    for control in payload["supported_controls"]:
        cases = [case for case in payload["cases"] if case["case_id"] == control["case_id"]]
        ensure(len(cases) == 1, "replay control has no selected case")
        regimes = set()
        for ref in cases[0]["results"]:
            result = dependency(ref, context, stack)
            problem = dependency(result["problem"], context, stack)
            regimes.add(problem["source"]["regime"])
        ensure(control["values"] == sorted(regimes), "control admits an unexported regime/value")
    if not context.allow_fixture:
        ensure(
            [c["case_id"] for c in payload["cases"]] == [f"N{i:02}" for i in range(1, 16)]
            and set(methods) == LEARNED,
            "public export omits required cases/models",
        )


def validate_artifact(
    document: dict[str, Any], context: AdmissionContext, *, usage="consume", _stack=()
) -> Artifact:
    """Actual producer/consumer admission. No permissive absent-field defaults."""
    finite_tree(document)
    schema_validate(document)
    ensure(document["content_sha256"] == content_digest(document), "artifact content identity")
    ensure(
        document["protocol_id"] == context.protocol_id
        and document["protocol_sha256"] == context.protocol_sha256
        and document["source_lock_sha256"] == context.source_lock_sha256,
        "protocol/source lock relabel",
    )
    provenance = document["provenance"]
    ensure(
        provenance["registration_sha256"] == context.registration_sha256
        and provenance["producer_source_sha256"] == context.producer_source_sha256,
        "source/registration relabel",
    )
    fixture = document["purpose"] == "contract-fixture"
    ensure(not fixture or context.allow_fixture, "fixture rejected by production consumer")
    ensure(
        (document["state"] == "provider") == fixture if document["state"] != "missing" else True,
        "provider/scientific state contradiction",
    )
    ensure(
        document["reason"] is not None
        if document["state"] in ["missing", "provider"]
        else document["reason"] is None,
        "availability reason contradiction",
    )
    ensure(usage in ["consume", "fit", "calibrate"], "unknown consumer usage")
    payload = document["payload"]
    if payload is not None:
        refs = _references(payload) + _references(document["protocol_ref"])
        ensure(
            provenance["parent_ids"] == sorted({r["artifact_id"] for r in refs}), "parent provenance mismatch"
        )
        stack = tuple(_stack) + (document["artifact_id"],)
        kind = document["kind"]
        ref_kinds = {
            "protocol_ref": "learning-protocol",
            "problem": "learning-problem",
            "dataset": "learning-dataset",
            "split": "learning-split",
            "features": "learning-features",
            "checkpoint": "learning-checkpoint",
            "calibration": "learning-calibration",
            "evaluation": "learning-evaluation",
            "results": "learning-method-result",
            "labels": "learning-labels",
        }
        for field_name, ref in _reference_entries(
            {"payload": payload, "protocol_ref": document["protocol_ref"]}
        ):
            ensure(ref_kinds.get(field_name) == ref["kind"], "wrong typed parent boundary")
            ensure(context.catalog.get(ref["artifact_id"]) == ref, "parent is not in sealed catalog")
            parent = safe_path(context.root, ref["path"], must_exist=True)
            ensure(digest(parent.read_bytes()) == ref["sha256"], "parent actual bytes mismatch")
        if kind == "learning-protocol":
            ensure(document["protocol_ref"] is None, "protocol self-parent")
        else:
            ensure(document["protocol_ref"] is not None, "required approved protocol is missing")
            dependency(document["protocol_ref"], context, stack)
        if kind == "learning-protocol":
            _protocol(payload, context, document)
        elif kind == "learning-problem":
            _problem(payload, context, document)
        elif kind == "learning-dataset":
            _dataset(payload, context, document, stack)
        elif kind == "learning-split":
            _split(payload, context, document, stack)
        elif kind == "learning-features":
            _features(payload, context, document, stack)
        elif kind == "learning-labels":
            _labels(payload, context, document, stack)
        elif kind == "learning-checkpoint":
            _checkpoint(payload, context, document, stack)
        elif kind == "learning-calibration":
            _calibration(payload, context, document, stack)
        elif kind == "learning-method-result":
            _method_result(payload, context, document, stack)
        elif kind == "learning-evaluation":
            _evaluation(payload, context, document, stack)
        elif kind == "learning-export-index":
            _export_index(payload, context, document, stack)
        if usage in ["fit", "calibrate"]:
            source = (
                payload["source"]
                if kind == "learning-problem"
                else (
                    dependency(payload["problem"], context, stack)["source"]
                    if kind in ["learning-features", "learning-labels"]
                    else None
                )
            )
            if source is not None:
                ensure(
                    source["split"] == ("train" if usage == "fit" else "calibration"),
                    "held-out source in fit/calibration consumer",
                )
    else:
        ensure(provenance["parent_ids"] == [], "missing artifact has fabricated parents")
    raw = json_bytes(document)
    return Artifact(
        document["kind"], document["artifact_id"], document["state"], document["reason"], raw, digest(raw)
    )


def read_artifact(
    path: Path, context: AdmissionContext, *, expected_sha256: str | None = None, usage="consume", _stack=()
) -> Artifact:
    lexical = Path(os.path.abspath(path))
    ensure(lexical.is_relative_to(context.root.resolve()), "input outside configured artifact root")
    relative = lexical.relative_to(context.root.resolve()).as_posix()
    path = safe_path(context.root, relative, must_exist=True)
    raw = path.read_bytes()
    if expected_sha256 is not None:
        ensure(digest(raw) == expected_sha256, "actual input byte hash mismatch")
    document = strict_loads(raw)
    # Cache only consumers, with a byte-bound closure fingerprint. Every sealed
    # JSON/numeric dependency and every schema is rehashed before reuse; a
    # same-size coefficient/weight mutation cannot use a stale admitted object.
    closure = []
    for ref in context.catalog.values():
        parent_path = safe_path(context.root, ref["path"], must_exist=True)
        parent_raw = parent_path.read_bytes()
        closure.append((ref["artifact_id"], digest(parent_raw)))
        parent_doc = strict_loads(parent_raw)

        def numeric_refs(value):
            if isinstance(value, dict):
                if set(value) == {"path", "sha256", "byte_count", "format"}:
                    numeric_path = safe_path(context.root, value["path"], must_exist=True)
                    closure.append((value["path"], digest(numeric_path.read_bytes())))
                else:
                    for child in value.values():
                        numeric_refs(child)
            elif isinstance(value, list):
                for child in value:
                    numeric_refs(child)

        numeric_refs(parent_doc)
    closure.extend(
        (p.name, digest(p.read_bytes())) for p in sorted(SCHEMAS.glob("softqp-learning-*.schema.json"))
    )
    cache_key = (digest(raw), usage, digest(canonical_bytes(closure)))
    if cache_key in context._validated:
        return context._validated[cache_key]
    artifact = validate_artifact(document, context, usage=usage, _stack=_stack)
    ensure(raw == artifact.raw, "noncanonical JSON bytes")
    context._validated[cache_key] = artifact
    return artifact


def write_artifact(document: dict[str, Any], relative: str, context: AdmissionContext) -> Artifact:
    """New external output only, validate before any filesystem mutation."""
    artifact = validate_artifact(document, context)
    ensure(
        type(relative) is str
        and relative.endswith(".json")
        and not any(part.startswith(".") for part in PurePosixPath(relative).parts),
        "unsafe JSON output name",
    )
    path = safe_path(context.root, relative, must_exist=False)
    ensure(
        not any((parent / ".git").exists() for parent in (path.parent, *path.parent.parents)),
        "output inside a Git checkout",
    )
    for forbidden in context.forbidden_roots:
        ensure(not path.is_relative_to(forbidden.resolve()), "output inside checkout/protected root")
    aliases = [safe_path(context.root, ref["path"], must_exist=False) for ref in context.catalog.values()]
    ensure(path not in aliases and not path.exists(), "output aliases an input/existing authority")
    ensure(path.parent.exists(), "output parent must already exist")
    temporary = None
    published = False
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".u1-", suffix=".json", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(artifact.raw)
            handle.flush()
            os.fsync(handle.fileno())
        read_artifact(temporary, context, expected_sha256=artifact.raw_sha256)
        # Hard-link publication is atomic and refuses an existing destination;
        # unlike replace(), this cannot overwrite a concurrently created input.
        os.link(temporary, path)
        published = True
        return read_artifact(path, context, expected_sha256=artifact.raw_sha256)
    except (OSError, ContractError) as error:
        if (
            published
            and path.exists()
            and temporary is not None
            and path.stat().st_ino == temporary.stat().st_ino
        ):
            path.unlink()
        raise ContractError("atomic artifact publication refused: " + str(error)) from error
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
