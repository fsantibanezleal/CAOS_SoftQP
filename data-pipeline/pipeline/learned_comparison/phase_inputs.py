"""Complete graph admission and physically isolated phase input distribution."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
import gzip
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType

from . import contracts as c

_ROLES = ("train", "validation", "calibration")
_MANIFEST = "phase-inputs.json"
_RECEIPT_FORMAT = "softqp.phase-preflight/v1"
_BUNDLE_FORMAT = "softqp.phase-inputs/v1"
_PROBLEM = "learning-problem"
_FEATURE = "learning-features"
_LABEL = "learning-labels"
_VARIANTS = {_PROBLEM: {None}, _FEATURE: {"mlp-v1", "graph-v1"}, _LABEL: {"cold_daqp"}}
_HASH = re.compile(r"[0-9a-f]{64}")
_FILE = re.compile(r"input-[0-9]{6}\.json")


@dataclass(frozen=True)
class PhaseInput:
    """Trusted nomination of one key. Missing envelopes have no ancestry fields."""

    problem_id: str
    kind: str
    variant: str
    artifact_id: str

    @property
    def key(self):
        return self.problem_id, self.kind, self.variant


@dataclass(frozen=True)
class PhaseRecord:
    artifact_id: str
    kind: str
    variant: str | None
    problem_id: str
    role: str
    source_id: str
    parent_id: str
    input_sha256: str
    family: str
    regime: int
    unit_index: int
    frame: int
    frame_count: int
    state: str
    reason: str | None
    sha256: str
    path: str


@dataclass(frozen=True)
class PhasePreflight:
    source_root: Path
    forbidden_roots: tuple[Path, ...]
    receipt_bytes: bytes

    @property
    def sha256(self):
        return c.digest(self.receipt_bytes)


def _role(role):
    c.ensure(role in _ROLES, "unsupported phase role")


def _hash(value):
    c.ensure(type(value) is str and _HASH.fullmatch(value), "invalid phase digest")


def _path_stat(path):
    info = path.lstat()
    c.ensure(
        not stat.S_ISLNK(info.st_mode)
        and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
        "phase symlink/reparse escape",
    )
    return info


def _exact_directory(path):
    c.ensure(isinstance(path, Path) and path.is_absolute() and ".." not in path.parts, "unsafe phase root")
    for component in (*reversed(path.parents), path):
        c.ensure(stat.S_ISDIR(_path_stat(component).st_mode), "phase directory required")
    resolved = path.resolve(strict=True)
    c.ensure(path.parts[1:] == resolved.parts[1:], "phase directory case or path alias")
    return resolved


def _path_parts(relative):
    parts = c._relative_parts(relative)
    for part in parts:
        c.ensure(
            not part.endswith((" ", "."))
            and not any(ch in part for ch in '<>"|?*')
            and all(ord(ch) >= 32 for ch in part)
            and not Path(part).is_reserved(),
            "unsafe phase path component",
        )
    return parts


def _open_bytes(root, relative, *, single_link=False):
    parts = _path_parts(relative)
    current = _exact_directory(root)
    for part in parts[:-1]:
        current = current / part
        c.ensure(stat.S_ISDIR(_path_stat(current).st_mode), "phase path component is not a directory")
    path = current / parts[-1]
    info = _path_stat(path)
    c.ensure(stat.S_ISREG(info.st_mode), "phase input is not a regular file")
    c.ensure(not single_link or info.st_nlink == 1, "phase payload has an external hard-link alias")
    result = path.resolve(strict=True)
    c.ensure(result.parts == path.parts, "phase path case or identity alias")
    return path.read_bytes()


def _checked_ref(context, artifact_id, kind):
    ref = context.catalog.get(artifact_id)
    c.ensure(
        ref is not None and ref["artifact_id"] == artifact_id and ref["kind"] == kind,
        "phase nomination absent from sealed catalog or wrong kind",
    )
    _path_parts(ref["path"])
    _hash(ref["sha256"])
    return dict(ref)


def _admit(root, context, ref):
    path = root.joinpath(*_path_parts(ref["path"]))
    # The strict reader performs semantic admission, including reachable ancestors.
    # Also require exact spelling of nominated roots before entering it.
    c.ensure(path.resolve(strict=True).parts == path.parts, "phase input path case or identity alias")
    artifact = c.read_artifact(path, context, expected_sha256=ref["sha256"])
    c.ensure(
        (artifact.artifact_id, artifact.kind) == (ref["artifact_id"], ref["kind"]), "phase artifact relabel"
    )
    return artifact


def _authority_keys(context, name):
    # Check and decode the same byte snapshot, unlike a verification followed by
    # a separate authority-file reread.
    relative = "expected-keysets/" + name + ".jsonl.gz"
    raw = (context.authority.root / relative).read_bytes()
    c.ensure(
        c.digest(raw) == context.authority.manifest["normative_sha256"][relative],
        "phase authority keyset changed",
    )
    decoded = gzip.decompress(raw)
    keys = {tuple(json.loads(line)) for line in decoded.splitlines()}
    entry = context.authority.inventory[name]
    c.ensure(
        len(keys) == entry["count"] and c.digest(decoded) == entry["sha256"],
        "phase authority keyset inventory",
    )
    return keys


def _population_keys(context, sources):
    labels = _authority_keys(context, "label-status")
    slots = _authority_keys(context, "source-status")
    rows = {(row["case_id"], row["regime"]): row for row in context.authority.matrix["rows"]}
    expected = set()
    actual_labels = set()
    heldout_slots = set()
    for problem_id, (source, fixture_control_pd) in sources.items():
        family, regime = source["family"], source["regime"]
        role, unit, frame = source["split"], source["unit_index"], source["frame"]
        row = rows[family, regime]
        if role == "test":
            heldout_slots.add(("method", "lifted", 0, family, regime, unit))
        if row["methods"]["learned_osqp"]["eligible"] or fixture_control_pd is not None:
            expected.add((problem_id, _FEATURE, "mlp-v1"))
        label = ("label", "cold_daqp", role, family, regime, unit, frame)
        graph = row["methods"]["learned_daqp"]["eligible"]
        if fixture_control_pd is not None:
            graph = fixture_control_pd
        else:
            c.ensure(graph == (label in labels), "phase exact-PD and label eligibility disagree")
        if graph:
            expected.add((problem_id, _FEATURE, "graph-v1"))
            expected.add((problem_id, _LABEL, "cold_daqp"))
            actual_labels.add(label)
    if not context.allow_fixture:
        c.ensure(actual_labels == labels, "phase label population differs from accepted design")
        c.ensure(
            heldout_slots == {key for key in slots if key[:3] == ("method", "lifted", 0)},
            "phase held-out source slots differ from accepted design",
        )
    return expected


def _record(artifact, variant, problem_id, source, ref):
    return PhaseRecord(
        artifact.artifact_id,
        artifact.kind,
        variant,
        problem_id,
        source["split"],
        source["source_id"],
        source["parent_id"],
        source["input_sha256"],
        source["family"],
        source["regime"],
        source["unit_index"],
        source["frame"],
        source["frame_count"],
        artifact.state,
        artifact.reason,
        artifact.raw_sha256,
        ref["path"],
    )


def _preflight(context, root, dataset_id, split_id, inputs):
    dataset_ref = _checked_ref(context, dataset_id, "learning-dataset")
    split_ref = _checked_ref(context, split_id, "learning-split")
    split_doc = _admit(root, context, split_ref).document
    split = split_doc["payload"]
    c.ensure(
        split is not None and split["dataset"] == dataset_ref, "phase split differs from nominated dataset"
    )
    dataset_doc = _admit(root, context, dataset_ref).document
    protocol_ref = dataset_doc["protocol_ref"]
    c.ensure(
        protocol_ref is not None and split_doc["protocol_ref"] == protocol_ref, "phase protocol ancestry"
    )
    protocol = _admit(root, context, protocol_ref).payload
    dataset = dataset_doc["payload"]
    c.ensure(
        set(protocol["old_exclusions"]) <= set(dataset["exclusions"]),
        "phase dataset omits protocol exclusions",
    )

    sources = {}
    problem_refs = {}
    records = {}
    for entry in dataset["problems"]:
        ref = entry["problem"]
        problem_id = ref["artifact_id"]
        artifact = _admit(root, context, ref)
        document = artifact.document
        payload = document["payload"]
        c.ensure(document["protocol_ref"] == protocol_ref, "phase problem protocol ancestry")
        fixture_control_pd = None
        if payload["expected_control"] is not None:
            c.ensure(
                context.allow_fixture and document["purpose"] == "contract-fixture",
                "diagnostic control cannot replace a production population input",
            )
            transform = payload["transform"]
            fixture_control_pd = c.exact_curvature(c.dense(transform["P"]))[0] == transform["n"]
        source = entry["source"]
        problem_refs[problem_id] = ref
        sources[problem_id] = source, fixture_control_pd
        records[problem_id] = _record(artifact, None, problem_id, source, ref)

    expected = _population_keys(context, sources)
    by_key = {}
    reserved_ids = set(records) | {dataset_id, split_id, protocol_ref["artifact_id"]}
    for request in inputs:
        c.ensure(isinstance(request, PhaseInput), "untyped phase input nomination")
        c.ensure(
            all(type(value) is str and value for value in (*request.key, request.artifact_id)),
            "invalid phase nomination field",
        )
        c.ensure(request.key not in by_key, "duplicate phase semantic key")
        c.ensure(request.artifact_id not in reserved_ids, "duplicate phase artifact ID")
        by_key[request.key] = request.artifact_id
        reserved_ids.add(request.artifact_id)
    missing, extra = expected - by_key.keys(), by_key.keys() - expected
    c.ensure(
        not missing and not extra,
        f"phase semantic inventory differs: {len(missing)} missing, {len(extra)} extra",
    )
    for (problem_id, kind, variant), artifact_id in sorted(by_key.items()):
        ref = _checked_ref(context, artifact_id, kind)
        artifact = _admit(root, context, ref)
        document = artifact.document
        payload = document["payload"]
        if payload is not None:
            c.ensure(
                payload["split"] == split_ref
                and payload["problem"] == problem_refs[problem_id]
                and document["protocol_ref"] == protocol_ref,
                "phase input differs from nominated problem/split/protocol ancestry",
            )
            if kind == _FEATURE:
                c.ensure(payload["representation"] == variant, "phase feature representation relabel")
        records[artifact_id] = _record(artifact, variant, problem_id, sources[problem_id][0], ref)
    return dataset_ref, split_ref, protocol_ref, tuple(records[k] for k in sorted(records))


def preflight_phase_inputs(
    context: c.AdmissionContext, *, dataset_id: str, split_id: str, inputs: Sequence[PhaseInput]
) -> PhasePreflight:
    """Admit the complete nominated source graph. Input nominations are trusted policy."""
    try:
        root = _exact_directory(context.root)
        nominations = tuple(inputs)
        with c._admission(context, fresh=True):
            dataset, split, protocol, records = _preflight(context, root, dataset_id, split_id, nominations)
        identities = {
            name: getattr(context, name)
            for name in (
                "protocol_id",
                "protocol_sha256",
                "source_lock_sha256",
                "registration_sha256",
                "producer_source_sha256",
                "generator_sha256",
                "dependency_lock_sha256",
            )
        }
        identities["design_manifest_sha256"] = c.DESIGN_MANIFEST_SHA256
        forbidden_roots = tuple(path.resolve() for path in context.forbidden_roots)
        receipt = {
            "format": _RECEIPT_FORMAT,
            "source_root": str(root),
            "forbidden_roots": [str(path) for path in forbidden_roots],
            "fixture_only": context.allow_fixture,
            "identities": identities,
            "dataset": dataset,
            "split": split,
            "protocol": protocol,
            "fit_source_ids": sorted(context.fit_source_ids),
            "problem_hashes": dict(context.problem_hashes),
            "source_records": dict(context.source_records),
            "settings_hashes": dict(context.settings_hashes),
            "catalog": {key: dict(value) for key, value in context.catalog.items()},
            "records": [asdict(record) for record in records],
        }
        return PhasePreflight(root, forbidden_roots, c.json_bytes(receipt))
    except OSError as error:
        raise c.ContractError("phase preflight input unavailable or unsafe") from error


def _external_destination(destination, source_root, forbidden_roots):
    c.ensure(
        isinstance(destination, Path) and destination.is_absolute() and ".." not in destination.parts,
        "unsafe phase destination",
    )
    _path_parts(destination.name)
    parent = _exact_directory(destination.parent)
    destination = parent / destination.name
    c.ensure(
        not destination.is_relative_to(source_root) and not source_root.is_relative_to(destination),
        "phase destination overlaps preflight input root",
    )
    c.ensure(
        not any((base / ".git").exists() for base in (parent, *parent.parents)),
        "phase destination inside a Git checkout",
    )
    for forbidden in forbidden_roots:
        target = forbidden.resolve()
        c.ensure(not destination.is_relative_to(target), "phase destination inside protected root")
    c.ensure(
        all(child.name.casefold() != destination.name.casefold() for child in parent.iterdir()),
        "phase destination already exists or is a case alias",
    )
    return destination


def _create_bytes(path, raw, created):
    with path.open("xb") as handle:
        created.append(path)
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _publish(destination, source_root, selected, manifest):
    # mkdir reserves the absent destination exclusively. Consumers have no
    # trusted manifest until the atomic, no-clobber publication of its final name.
    destination.mkdir()
    owner = _path_stat(destination)
    created = []
    published = False
    temporary = destination / ".unpublished-manifest"
    try:
        for record in selected:
            raw = _open_bytes(source_root, record["source_path"])
            c.ensure(c.digest(raw) == record["sha256"], "phase source changed after preflight")
            target = destination / record["path"]
            _create_bytes(target, raw, created)
        _create_bytes(temporary, manifest, created)
        os.link(temporary, destination / _MANIFEST)
        published = True
    finally:
        # Never recurse through or remove a directory replaced by another party.
        if os.path.samestat(owner, _path_stat(destination)):
            if published:
                temporary.unlink(missing_ok=True)
            else:
                for path in reversed(created):
                    path.unlink(missing_ok=True)
                destination.rmdir()


def materialize_phase_inputs(
    preflight: PhasePreflight, destination: Path, *, role: str, expected_preflight_sha256: str
) -> str:
    """Create an absent physical role root and return its manifest SHA-256."""
    _role(role)
    _hash(expected_preflight_sha256)
    c.ensure(preflight.sha256 == expected_preflight_sha256, "phase preflight digest mismatch")
    receipt = c.strict_loads(preflight.receipt_bytes)
    c.ensure(receipt["format"] == _RECEIPT_FORMAT, "unknown preflight receipt format")
    c.ensure(
        receipt["source_root"] == str(preflight.source_root)
        and receipt["forbidden_roots"] == [str(path) for path in preflight.forbidden_roots],
        "materialization path policy differs from trusted preflight receipt",
    )
    selected = []
    for record in receipt["records"]:
        if record["role"] == role:
            selected.append(
                {**record, "source_path": record["path"], "path": f"input-{len(selected):06d}.json"}
            )
    c.ensure(bool(selected), "phase has no admitted inputs")
    manifest = c.json_bytes(
        {
            "format": _BUNDLE_FORMAT,
            "role": role,
            "preflight_sha256": expected_preflight_sha256,
            "fixture_only": receipt["fixture_only"],
            "identities": receipt["identities"],
            "records": [
                {key: value for key, value in record.items() if key != "source_path"} for record in selected
            ],
        }
    )
    try:
        source_root = _exact_directory(preflight.source_root)
        target = _external_destination(destination, source_root, preflight.forbidden_roots)
        _publish(target, source_root, selected, manifest)
    except OSError as error:
        raise c.ContractError("phase publication unavailable or destination already reserved") from error
    return c.digest(manifest)


def _record_from_manifest(row, role):
    c.ensure(
        type(row) is dict and row.keys() == PhaseRecord.__dataclass_fields__.keys(), "invalid phase record"
    )
    record = PhaseRecord(**row)
    for name in ("artifact_id", "kind", "problem_id", "source_id", "parent_id", "family", "path"):
        value = getattr(record, name)
        c.ensure(type(value) is str and value, "invalid phase text field")
    for name in ("regime", "unit_index", "frame", "frame_count"):
        value = getattr(record, name)
        c.ensure(type(value) is int and value >= 0, "invalid phase source index")
    c.ensure(record.frame < record.frame_count, "invalid phase frame")
    c.ensure(
        record.role == role
        and (record.variant is None or type(record.variant) is str)
        and record.variant in _VARIANTS.get(record.kind, ())
        and _FILE.fullmatch(record.path),
        "invalid phase role, kind, variant or payload path",
    )
    c.ensure(record.state in ("provider", "missing", "available"), "invalid phase input state")
    c.ensure(
        (
            record.reason is None
            if record.state == "available"
            else type(record.reason) is str and record.reason
        ),
        "invalid phase state reason",
    )
    _hash(record.input_sha256)
    _hash(record.sha256)
    return record


def _source_key(record):
    return (
        record.role,
        record.source_id,
        record.parent_id,
        record.input_sha256,
        record.family,
        record.regime,
        record.unit_index,
        record.frame,
        record.frame_count,
    )


class PhaseInputReader:
    """Consume one role using independently trusted manifest and preflight hashes."""

    def __init__(
        self, root, *, role, expected_manifest_sha256, expected_preflight_sha256, allow_fixture=False
    ):
        _role(role)
        _hash(expected_manifest_sha256)
        _hash(expected_preflight_sha256)
        try:
            self._root = _exact_directory(root)
            raw = _open_bytes(self._root, _MANIFEST)
        except OSError as error:
            raise c.ContractError("phase manifest unavailable") from error
        c.ensure(c.digest(raw) == expected_manifest_sha256, "phase manifest digest mismatch")
        manifest = c.strict_loads(raw)
        c.ensure(
            manifest.keys() == {"format", "role", "preflight_sha256", "fixture_only", "identities", "records"}
            and raw == c.json_bytes(manifest)
            and manifest["format"] == _BUNDLE_FORMAT,
            "invalid phase manifest format",
        )
        c.ensure(
            manifest["role"] == role and manifest["preflight_sha256"] == expected_preflight_sha256,
            "phase role/preflight mismatch",
        )
        c.ensure(
            type(manifest["fixture_only"]) is bool
            and (not manifest["fixture_only"] or allow_fixture is True),
            "fixture phase rejected by independent consumer policy",
        )
        c.ensure(
            type(manifest["records"]) is list and manifest["records"], "empty or invalid phase inventory"
        )
        records = tuple(_record_from_manifest(row, role) for row in manifest["records"])
        by_id = {record.artifact_id: record for record in records}
        paths = {record.path for record in records}
        c.ensure(
            len(by_id)
            == len(paths)
            == len({(r.problem_id, r.kind, r.variant) for r in records})
            == len(records),
            "duplicate phase inventory entry",
        )
        for record in records:
            source = by_id.get(record.problem_id)
            c.ensure(
                source is not None and source.kind == _PROBLEM and _source_key(record) == _source_key(source),
                "phase record differs from bound problem source",
            )
            c.ensure(
                record.kind != _PROBLEM or source is record and record.state != "missing",
                "invalid phase problem",
            )
            c.ensure(
                record.state != "provider" or manifest["fixture_only"],
                "fixture record under production manifest",
            )
        self._check_inventory(paths, manifest_raw=raw)
        self._records = records
        self._by_id = MappingProxyType(by_id)
        self._fixture_only = manifest["fixture_only"]
        self._role = role
        self._preflight_sha256 = expected_preflight_sha256
        self._manifest_sha256 = expected_manifest_sha256
        self._identities = MappingProxyType(manifest["identities"])

    def _check_inventory(self, paths, *, manifest_raw):
        try:
            actual = {path.name for path in self._root.iterdir()}
            temporary = self._root / ".unpublished-manifest"
            if temporary.name in actual:
                try:
                    temporary_info = _path_stat(temporary)
                except FileNotFoundError:
                    # A publishing call may remove the temporary hard link
                    # between the directory inventory and this stat.
                    pass
                else:
                    published = self._root / _MANIFEST
                    c.ensure(
                        os.path.samestat(temporary_info, _path_stat(published))
                        and _open_bytes(self._root, _MANIFEST) == manifest_raw,
                        "foreign file masquerades as transient phase manifest",
                    )
                actual.remove(temporary.name)
        except OSError as error:
            raise c.ContractError("phase inventory unavailable") from error
        c.ensure(actual == paths | {_MANIFEST}, "phase directory inventory differs from trusted manifest")

    @property
    def records(self):
        return self._records

    @property
    def role(self):
        return self._role

    @property
    def preflight_sha256(self):
        return self._preflight_sha256

    @property
    def manifest_sha256(self):
        return self._manifest_sha256

    @property
    def fixture_only(self):
        return self._fixture_only

    def read(self, artifact_id: str) -> c.Artifact:
        """Open one local payload. Typed ancestry was verified by preflight."""
        record = self._by_id.get(artifact_id)
        c.ensure(record is not None, "input absent from this phase role")
        try:
            raw = _open_bytes(self._root, record.path, single_link=True)
        except OSError as error:
            raise c.ContractError("phase payload unavailable") from error
        c.ensure(c.digest(raw) == record.sha256, "phase payload byte hash mismatch")
        document = c.strict_loads(raw)
        c.ensure(
            (document["artifact_id"], document["kind"], document["state"], document["reason"])
            == (record.artifact_id, record.kind, record.state, record.reason),
            "phase payload metadata relabel",
        )
        c.ensure(
            document["purpose"] != "contract-fixture" or self._fixture_only,
            "fixture payload under production phase manifest",
        )
        payload = document["payload"]
        if payload is not None:
            if record.kind == _PROBLEM:
                source = payload["source"]
                c.ensure(
                    _source_key(record)
                    == (
                        source["split"],
                        source["source_id"],
                        source["parent_id"],
                        source["input_sha256"],
                        source["family"],
                        source["regime"],
                        source["unit_index"],
                        source["frame"],
                        source["frame_count"],
                    ),
                    "phase payload source relabel",
                )
            else:
                problem = self._by_id[record.problem_id]
                c.ensure(
                    (payload["problem"]["artifact_id"], payload["problem"]["sha256"])
                    == (problem.artifact_id, problem.sha256),
                    "phase input original problem relabel",
                )
                if record.kind == _FEATURE:
                    c.ensure(
                        payload["representation"] == record.variant, "phase payload representation relabel"
                    )
        for key in ("protocol_id", "protocol_sha256", "source_lock_sha256"):
            c.ensure(document[key] == self._identities[key], "phase payload identity mismatch")
        for key in ("registration_sha256", "producer_source_sha256"):
            c.ensure(
                document["provenance"][key] == self._identities[key], "phase payload provenance mismatch"
            )
        return c.Artifact(record.kind, record.artifact_id, record.state, record.reason, raw, record.sha256)
