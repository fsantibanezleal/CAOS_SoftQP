"""Authority-gated, test-local raw input and observed native evaluation proof."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import stat
from weakref import WeakKeyDictionary

from . import contracts as c
from . import evaluation_models as models
from . import native_labels as native
from . import phase_inputs as phase
from . import stream_inputs as stream

POLICY = "softqp.heldout-policy/1"
REQUEST = "softqp.heldout-request/1"
INDEX = "softqp.test-slot-index/1"
PROJECTION = "softqp.test-input-projection/1"
NATIVE_RUN = "softqp.test-native-run/2"
NATIVE_ATTEMPT = "softqp.test-native-attempt/2"
NATIVE_PROOF = "softqp.test-native-proof/2"
_INPUT_MANIFEST = "test-inputs.json"
_SCHEMAS = {
    name: name.split(".")[1].split("/")[0]
    for name in (INDEX, PROJECTION, NATIVE_RUN, NATIVE_ATTEMPT, NATIVE_PROOF)
}

_OPERATIONS = {"test-native", "candidate"}
_ISSUED = WeakKeyDictionary()


class HeldoutAdmission:
    """Identity-only handle. Construction grants no filesystem or execution rights."""


@dataclass(frozen=True)
class _Admission:
    custody: object
    profile: str
    operation: str
    stage: str
    request_sha256: str
    policy_sha256: str
    scope_sha256: str
    policy_bytes: bytes
    p0_bytes: bytes
    p1_bytes: bytes
    index_bytes: bytes
    context: c.AdmissionContext
    protocol: bytes
    fixture_only: bool
    population_sha256: str
    candidate_models: tuple
    read_only: bool = False


def _exact(obj, keys, message):
    c.ensure(type(obj) is dict and set(obj) == keys, message)
    return obj


def _json(raw):
    obj = c.strict_loads(raw)
    c.ensure(type(obj) is dict and raw == c.canonical_bytes(obj), "held-out JSON must be canonical")
    name = _SCHEMAS.get(obj.get("schema"))
    if name is not None:
        c._validator((c.SCHEMAS / f"softqp-{name}.schema.json").read_bytes()).validate(obj)
    return obj


def _checked(raw, expected, name):
    phase._hash(expected)
    c.ensure(c.digest(raw) == expected, f"independent {name} byte identity differs")
    return _json(raw)


def _binding(state):
    binding = {
        "operation": state.operation,
        "stage": state.stage,
        "source_file": Path(__file__).resolve(),
        "profile_sha256": state.profile,
        "request_sha256": state.request_sha256,
    }
    if state.read_only:
        binding["read_only"] = True
    return binding


def _live(state):
    from softqp_heldout_runtime_custody import read_policy

    actual = read_policy(state.custody, **_binding(state))
    c.ensure(actual == state.policy_bytes, "held-out live launch policy changed")


def _state(handle, *stages):
    c.ensure(type(handle) is HeldoutAdmission and handle in _ISSUED, "unissued held-out admission")
    state = _ISSUED[handle]
    c.ensure(not stages or state.stage in stages, "held-out stage does not grant requested access")
    _live(state)
    return state


def _refs(receipt, *, role):
    rows = {}
    for entry in receipt["records"]:
        if entry["role"] == role:
            ref = entry["ref"]
            key = ref["artifact_id"]
            c.ensure(key not in rows, "duplicate held-out physical reference")
            rows[key] = ref
    return rows


def _slot_key(row):
    return row["family"], row["regime"], row["unit_index"], row["frame_index"]


def _domain(ctx):
    all_oracles = phase._authority_keys(ctx, "oracle-status")
    all_labels = phase._authority_keys(ctx, "label-status")
    oracles = {key[3:] for key in all_oracles if key[2] == "test"}
    labels = {key[3:] for key in all_labels if key[2] == "test"}
    c.ensure(
        len(oracles) == 2208
        and len(labels) == 2072
        and len({key[:3] for key in oracles}) == 720
        and len({key[:3] for key in labels}) == 584,
        "registered held-out domain changed",
    )
    backend_keys = {
        ("oracle", backend, "test", *key) for key in oracles for backend in ("stock_osqp", "clarabel", "piqp")
    }
    c.ensure(
        backend_keys == {key for key in all_oracles if key[2] == "test"}
        and {("label", "cold_daqp", "test", *key) for key in labels}
        == {key for key in all_labels if key[2] == "test"},
        "registered oracle or cold-label keys changed",
    )
    return oracles, labels


def _entries(raw_index, p0, p1, ctx, fixture):
    doc = _exact(_json(raw_index), {"schema", "rows"}, "held-out slot index shape differs")
    c.ensure(
        doc["schema"] == INDEX and type(doc["rows"]) is list and doc["rows"], "held-out slot index format"
    )
    rows = doc["rows"]
    refs0, refs1 = (_refs(x, role="test") for x in (p0, p1))
    c.ensure(refs0 == refs1 and refs0, "test physical records change between P0 and P1")
    expected_refs, frame_keys = {}, set()
    source_bindings, parent_bindings = {}, {}
    names = {
        "role",
        "family",
        "regime",
        "unit_index",
        "frame_index",
        "frame_count",
        "source_id",
        "parent_id",
        "frame",
        "source",
        "original_sha256",
        "transform_sha256",
        "units_sha256",
        "cold_eligible",
    }
    for row in rows:
        _exact(row, names, "held-out slot index row shape differs")
        key = _slot_key(row)
        c.ensure(
            row["role"] == "test" and key not in frame_keys and type(row["cold_eligible"]) is bool,
            "duplicate or relabeled held-out slot",
        )
        frame_keys.add(key)
        for name, kind in (("source", stream.SOURCE), ("frame", stream.FRAME)):
            ref = _exact(
                row[name], {"kind", "artifact_id", "path", "sha256"}, "held-out reference shape differs"
            )
            phase._hash(ref["sha256"])
            phase._path_parts(ref["path"])
            c.ensure(
                ref["kind"] == kind and refs0.get(ref["artifact_id"]) == ref, "held-out reference differs"
            )
            previous = expected_refs.setdefault(ref["artifact_id"], ref)
            c.ensure(previous == ref, "held-out reference recurs inconsistently")
        for name in ("original_sha256", "transform_sha256", "units_sha256"):
            phase._hash(row[name])
        source_scope = (key[:3], row["source"], row["parent_id"], row["frame_count"])
        c.ensure(
            source_bindings.setdefault(row["source_id"], source_scope) == source_scope
            and parent_bindings.setdefault(row["parent_id"], row["source_id"]) == row["source_id"],
            "held-out source or parent is substituted",
        )
    c.ensure(
        expected_refs == refs0
        and len({row["frame"]["artifact_id"] for row in rows}) == len(rows)
        and [_slot_key(row) for row in rows] == sorted(frame_keys),
        "incomplete held-out physical scope",
    )
    for source_id, scope in source_bindings.items():
        c.ensure(
            sorted(row["frame_index"] for row in rows if row["source_id"] == source_id)
            == list(range(scope[3])),
            "incomplete held-out source trajectory",
        )
    selected = {row["frame"]["artifact_id"] for row in rows if row["cold_eligible"]}
    for receipt in (p0, p1):
        slots = {
            entry["frame_id"]
            for entry in receipt["logical"]
            if entry["role"] == "test" and entry["representation"] == "graph-v1"
        }
        labels = {entry["frame_id"] for entry in receipt["labels"] if entry["role"] == "test"}
        c.ensure(
            slots == labels == selected
            and all(
                entry["state"] == "missing" and entry["ref"] is None
                for entry in receipt["labels"]
                if entry["role"] == "test"
            ),
            "held-out preflight label slots are populated or incomplete",
        )
    if not fixture:
        frames, cold = _domain(ctx)
        c.ensure(
            frame_keys == frames and {_slot_key(row) for row in rows if row["cold_eligible"]} == cold,
            "held-out index differs from exact R4 domain",
        )
    return rows


def admit_heldout(
    *,
    guardian,
    i1,
    request,
    policy,
    expected_policy_sha256,
    context,
    protocol_ref,
    p0,
    p1,
    index_bytes,
    roster_root,
    roster_trust,
    expected_roster_sha256,
    read_only=False,
):
    """Issue only inside the fixed guardian after independent model and metadata admission."""
    from softqp_heldout_runtime_custody import active_profile_sha256, approved_native_settings, read_policy
    from .authority import require_i1

    req = _exact(
        _json(request),
        {"schema", "operation", "stage", "roster_sha256", "p0_sha256", "p1_sha256", "inventory_sha256"},
        "held-out request shape differs",
    )
    fixture = req["operation"] == "evaluate-heldout-fixture"
    c.ensure(
        req["schema"] == REQUEST
        and req["stage"] in _OPERATIONS
        and req["operation"] in ("evaluate-heldout", "evaluate-heldout-fixture")
        and context.allow_fixture == fixture,
        "held-out operation or fixture lane differs",
    )
    capability = {"read_only": True} if read_only else {}
    live_profile = active_profile_sha256(guardian, **capability)
    c.ensure(
        all(context.settings_hashes.get(k) == v for k, v in approved_native_settings(guardian, **capability).items()),
        "held-out native settings differ from the live profile",
    )
    bound = read_policy(
        guardian,
        operation=req["operation"],
        stage=req["stage"],
        request_sha256=c.digest(request),
        source_file=Path(__file__).resolve(),
        profile_sha256=live_profile,
        **capability,
    )
    c.ensure(bound == policy, "held-out policy differs from live fixed guardian")
    governed = _exact(
        _checked(policy, expected_policy_sha256, "held-out policy"),
        {"schema", "operation", "stage", "request_sha256", "scope", "expected", "inputs"},
        "held-out policy shape differs",
    )
    scope = _exact(
        governed["scope"],
        {
            "profile_sha256",
            "identities",
            "p0_sha256",
            "p1_sha256",
            "roster_sha256",
            "inventory_sha256",
            "test_root",
            "native_root",
            "proof_root",
            "frontier_root",
            "artifact_roots",
        },
        "held-out stable scope shape differs",
    )
    c.ensure(
        governed["schema"] == POLICY
        and governed["operation"] == req["operation"]
        and governed["stage"] == req["stage"]
        and governed["request_sha256"] == c.digest(request)
        and scope["profile_sha256"] == live_profile,
        "held-out policy identity differs",
    )
    for k, actual in (
        ("p0_sha256", p0.sha256),
        ("p1_sha256", p1.sha256),
        ("roster_sha256", expected_roster_sha256),
        ("inventory_sha256", c.digest(index_bytes)),
    ):
        phase._hash(req[k])
        c.ensure(req[k] == scope[k] == actual, f"held-out {k} differs")
    if read_only:
        c.ensure(req["stage"] == "candidate" and i1 is None, "invalid recovery-only held-out admission")
    elif fixture:
        c.ensure(i1 is None, "excluded held-out control cannot consume I1")
    else:
        require_i1(i1, "evaluate-heldout", context=context, protocol_ref=protocol_ref)
        c.ensure(i1.runtime_profile_sha256 == live_profile, "held-out I1 and active profile differ")
    a, b = _json(p0.receipt_bytes), _json(p1.receipt_bytes)
    c.ensure(
        all(
            v["format"] == "softqp.stream-preflight/v2"
            and v["fixture_only"] == fixture
            and v["protocol_ref"] == protocol_ref
            and v["identities"] == scope["identities"]
            for v in (a, b)
        )
        and a["population_sha256"] == b["population_sha256"],
        "held-out P0/P1 protocol or population lineage differs",
    )
    for name in (
        "protocol_id",
        "protocol_sha256",
        "registration_sha256",
        "source_lock_sha256",
        "dependency_lock_sha256",
        "producer_source_sha256",
        "generator_sha256",
    ):
        c.ensure(
            scope["identities"][name] == getattr(context, name), "held-out approved source lineage differs"
        )
    c.ensure(
        a["identities"]["design_manifest_sha256"] == c.DESIGN_MANIFEST_SHA256
        and a["identities"]["learning_policy_sha256"]
        == context.authority.manifest["normative_sha256"]["learning-spec.md"],
        "held-out approved design or learning policy differs",
    )
    c.ensure(
        a["source_root"] == b["source_root"] == str(context.root)
        and a["forbidden_roots"] == b["forbidden_roots"] == list(map(str, context.forbidden_roots)),
        "held-out P0/P1 path policy differs",
    )
    admitted_roster = models.read_roster(
        roster_root,
        roster_trust,
        expected_sha256=expected_roster_sha256,
        authority=context.authority,
        allow_fixture=fixture,
    )
    c.ensure(
        all(
            t.protocol_sha256 == protocol_ref["sha256"]
            and t.population_sha256 == b["population_sha256"]
            and t.preflight_sha256 == p1.sha256
            for t in roster_trust
        ),
        "held-out roster ancestry differs",
    )
    entries = _entries(index_bytes, a, b, context, fixture)
    non_test = {row["ref"]["artifact_id"] for row in a["records"] if row["role"] != "test"}
    outside_hashes = {context.problem_hashes[key] for key in non_test if key in context.problem_hashes}
    c.ensure(
        not any(row["original_sha256"] in outside_hashes for row in entries),
        "held-out original overlaps a non-test role",
    )
    stage_expected = governed["expected"]
    if req["stage"] == "candidate":
        _exact(
            stage_expected,
            {"test_sha256", "native_sha256", "proof_sha256"},
            "candidate stage requires independently expected T/N/J",
        )
        for seal in stage_expected.values():
            phase._hash(seal)
    else:
        c.ensure(stage_expected is None, "test-native policy cannot carry a candidate seal")
    roots = [Path(scope[k]) for k in ("test_root", "native_root", "proof_root", "frontier_root")]
    c.ensure(
        all(root.is_absolute() and ".." not in root.parts for root in roots)
        and not any(
            a.is_relative_to(b) or b.is_relative_to(a) for i, a in enumerate(roots) for b in roots[i + 1 :]
        ),
        "held-out roots are not distinct and external",
    )
    _accounting_roots(scope, context, roots)
    handle = HeldoutAdmission()
    _ISSUED[handle] = _Admission(
        guardian,
        live_profile,
        req["operation"],
        req["stage"],
        c.digest(request),
        expected_policy_sha256,
        c.digest(c.canonical_bytes(scope)),
        policy,
        p0.receipt_bytes,
        p1.receipt_bytes,
        index_bytes,
        context,
        c.canonical_bytes(protocol_ref),
        fixture,
        a["population_sha256"],
        tuple(
            (
                (entry.method, entry.seed),
                entry
                if type(entry) is models.ModelTrust
                else CandidateModelFailure(c.canonical_bytes(admitted_roster[(entry.method, entry.seed)])),
            )
            for entry in roster_trust
        )
        if req["stage"] == "candidate"
        else (),
        read_only,
    )
    return handle


def _accounting_roots(scope, context, roots):
    accounting = tuple(Path(path) for path in scope["artifact_roots"])
    c.ensure(
        bool(accounting)
        and all(path.is_absolute() and ".." not in path.parts for path in accounting)
        and all(any(path.is_relative_to(parent) for parent in accounting) for path in (*roots, context.root))
        and not any(
            protected.is_relative_to(parent) or parent.is_relative_to(protected)
            for parent in accounting
            for protected in context.forbidden_roots
        ),
        "held-out artifact quota roots are incomplete or protected",
    )
    return accounting


def _scope(state):
    return _json(state.policy_bytes)["scope"]


def _quota_existing(state):
    scope = _scope(state)
    output = tuple(Path(scope[k]) for k in ("test_root", "native_root", "proof_root", "frontier_root"))
    roots = tuple(phase._exact_directory(path) for path in _accounting_roots(scope, state.context, output))
    return native._native_base_bytes(roots)


def _quota(bytes_used):
    c.ensure(
        bytes_used <= 8 * 2**30 - native._MANIFEST_LIMIT - 4 * native._FILE_LIMIT,
        "held-out aggregate artifact disk budget",
    )


def _keys(state):
    return _json(state.index_bytes)["rows"]


def _copy_record(root, destination, ref, local):
    data = phase._open_bytes(root, ref["path"], single_link=True)
    _record(data, ref)
    with (destination / local).open("xb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    reread = phase._open_bytes(destination, local, single_link=True)
    _record(reread, ref)
    return len(reread)


def _record(raw, ref):
    obj = _checked(raw, ref["sha256"], "test source or frame")
    c.ensure(
        (obj["artifact_id"], obj["kind"]) == (ref["artifact_id"], ref["kind"]),
        "held-out physical reference relabeled",
    )
    return obj


def _projection_document(state):
    records = {}
    rows = _keys(state)
    for row in rows:
        for name in ("source", "frame"):
            ref = row[name]
            key = ref["artifact_id"]
            if key not in records:
                records[key] = {"ref": ref, "path": f"input-{len(records):06d}.json"}
    identities = _scope(state)
    return {
        "schema": PROJECTION,
        "fixture_only": state.fixture_only,
        "role": "test",
        "scope_sha256": state.scope_sha256,
        "p0_sha256": identities["p0_sha256"],
        "p1_sha256": identities["p1_sha256"],
        "roster_sha256": identities["roster_sha256"],
        "inventory_sha256": identities["inventory_sha256"],
        "records": list(records.values()),
        "rows": rows,
    }


def _atomic_document(root, name, doc):
    raw = c.canonical_bytes(doc)
    pending = root / (name + ".pending")
    with pending.open("xb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    target = root / name
    try:
        os.link(pending, target)
    finally:
        pending.unlink()
    c.ensure(phase._open_bytes(root, name, single_link=True) == raw, "held-out publication bytes changed")
    return c.digest(raw)


def materialize_test_inputs(admission, *, destination):
    state = _state(admission, "test-native")
    root = phase._external_destination(Path(destination), state.context.root, state.context.forbidden_roots)
    c.ensure(root == Path(_scope(state)["test_root"]), "test projection destination differs")
    import shutil

    c.ensure(shutil.disk_usage(root.parent).free >= 20 * 2**30, "test projection external disk minimum")
    bytes_used = _quota_existing(state)
    _quota(bytes_used)
    root.mkdir()
    document = _projection_document(state)
    for row in document["records"]:
        _live(state)
        bytes_used += _copy_record(state.context.root, root, row["ref"], row["path"])
        _quota(bytes_used)
    digest = _atomic_document(root, _INPUT_MANIFEST, document)
    return _open_reader(admission, root, digest)


class TestInputReader:
    """Narrow fresh local pair access. There is no fitting or label method."""

    @classmethod
    def open(cls, admission, test_root, *, expected_projection_sha256):
        _state(admission, "test-native")
        return _open_reader(admission, test_root, expected_projection_sha256)

    @property
    def frame_ids(self):
        local = _reader(self)
        _state(local.admission)
        return tuple(local.slots)

    @property
    def manifest_sha256(self):
        return _reader(self).expected

    def read_sealed_frame_pair(self, frame_id):
        local_reader = _reader(self)
        state = _state(local_reader.admission)
        c.ensure(
            state.stage == "test-native" or _CANDIDATE_READERS.get(self) is local_reader.admission,
            "candidate test pair cannot precede verified native proof",
        )
        row = local_reader.slots.get(frame_id)
        c.ensure(row is not None, "test frame absent from authorized projection")
        pair = {}
        for name in ("source", "frame"):
            ref = row[name]
            local = local_reader.records[ref["artifact_id"]]["path"]
            raw = phase._open_bytes(local_reader.root, local, single_link=True)
            doc = _record(raw, ref)
            expected_purpose = "contract-fixture" if state.fixture_only else "scientific"
            c.ensure(doc["purpose"] == expected_purpose, "held-out fixture or purpose relabeled")
            meta = doc["payload"]["slot" if name == "source" else "source"]
            c.ensure(meta["split"] == "test", "non-test payload in held-out pair")
            if name == "frame":
                c.ensure(
                    doc["payload"]["source_ref"] == row["source"], "test frame links an alternate source"
                )
            pair[f"{name}_raw"] = raw
            pair[f"{name}_ref"] = dict(ref)
        return pair


_CANDIDATE_READERS = WeakKeyDictionary()


def _open_reader(admission, root, expected):
    state = _state(admission)
    root = phase._exact_directory(Path(root))
    c.ensure(root == Path(_scope(state)["test_root"]), "test-reader root differs")
    doc = _checked(phase._open_bytes(root, _INPUT_MANIFEST, single_link=True), expected, "test projection")
    c.ensure(doc == _projection_document(state), "test-local projection identity or inventory changed")
    physical = {row["path"] for row in doc["records"]} | {_INPUT_MANIFEST}
    c.ensure({path.name for path in root.iterdir()} == physical, "test-local file inventory differs")
    for local in physical:
        facts = phase._path_stat(root / local)
        c.ensure(stat.S_ISREG(facts.st_mode) and facts.st_nlink == 1, "test-local file alias")
    result = TestInputReader()
    _READERS[result] = _LocalReader(
        admission,
        root,
        expected,
        {row["frame"]["artifact_id"]: row for row in doc["rows"]},
        {row["ref"]["artifact_id"]: row for row in doc["records"]},
    )
    return result


def _native_problem(reader, frame_id, state):
    pair = reader.read_sealed_frame_pair(frame_id)
    source, frame = _json(pair["source_raw"]), _json(pair["frame_raw"])
    stream._source(source["payload"], state.context)
    problem = stream._problem(state.context, frame, source)
    meta = problem["source"]
    row = dict(_reader(reader).slots[frame_id])
    c.ensure(
        (
            meta["split"],
            meta["family"],
            meta["regime"],
            meta["unit_index"],
            meta["frame"],
            meta["frame_count"],
            meta["source_id"],
            meta["parent_id"],
            problem["original_sha256"],
            problem["transform_sha256"],
            native._hash(problem["original"]["units"]),
        )
        == (
            row["role"],
            *_slot_key(row),
            row["frame_count"],
            row["source_id"],
            row["parent_id"],
            row["original_sha256"],
            row["transform_sha256"],
            row["units_sha256"],
        ),
        "held-out original semantic identity differs",
    )
    if state.fixture_only:
        c.ensure(problem["expected_control"] is not None, "held-out fixture must be an excluded math control")
    return problem, row


@dataclass(frozen=True)
class _LocalReader:
    admission: HeldoutAdmission
    root: Path
    expected: str
    slots: object
    records: object


_READERS = WeakKeyDictionary()


def _reader(reader, admission=None):
    c.ensure(type(reader) is TestInputReader and reader in _READERS, "unissued test input reader")
    local = _READERS[reader]
    c.ensure(admission is None or local.admission is admission, "test reader admission differs")
    return local


def _observation_wire(value):
    if value is None:
        return None
    raw = native._encode(value)
    return {"encoding": "softqp-native-json/1", "json": raw.decode("utf-8"), "sha256": c.digest(raw)}


def _observation(wire):
    if wire is None:
        return None
    _exact(wire, {"encoding", "json", "sha256"}, "raw test-native observation wire differs")
    c.ensure(wire["encoding"] == "softqp-native-json/1", "test-native observation encoding differs")
    raw = wire["json"].encode("utf-8")
    c.ensure(c.digest(raw) == wire["sha256"], "observed test-native raw bytes differ")
    return native._decode(raw)


def _stage_attempt(problem, identity, reference, cold, state):
    context = state.context
    attempt = {"input": identity, "reference": reference, "cold": cold}
    outcome, reason, raw = native._disposition(
        attempt, problem, context, _json(state.protocol), state.population_sha256
    )
    rows = None
    if reference["status"] == "observed":
        try:
            _, rows = native._product_projection(reference, problem, context)
        except (ArithmeticError, ValueError):
            pass
    label = _json(raw)["payload"] if raw is not None and outcome == "accepted" else None
    return {"state": outcome, "reason": reason, "oracle_rows": rows, "label": label}


def _close_profile(state, reader):
    scoped = _scope(state)
    return native._hash(
        {
            "scope_sha256": state.scope_sha256,
            "test_sha256": reader.manifest_sha256,
            "policy_sha256": state.policy_sha256,
            "roster_sha256": scoped["roster_sha256"],
        }
    )


@dataclass(frozen=True)
class _NativeWorkerScope:
    state: _Admission
    reader: TestInputReader

    @property
    def profile_sha256(self):
        return self.state.profile

    @property
    def fixture_only(self):
        return self.state.fixture_only

    @property
    def policy_sha256(self):
        return self.state.policy_sha256

    @property
    def scope_sha256(self):
        return _close_profile(self.state, self.reader)

    def check(self):
        _live(self.state)

    def launch(self, root, nonce, generation, authority_sha256):
        from softqp_heldout_runtime_custody import open_test_native_worker

        return open_test_native_worker(
            self.state.custody,
            root=root,
            nonce=nonce,
            generation=generation,
            authority_sha256=authority_sha256,
            scope_sha256=self.scope_sha256,
            **_binding(self.state),
        )


@dataclass(frozen=True)
class _AuthorityReceipt:
    sha256: str

    @property
    def document(self):
        return {"roles": ["test"]}


def _header(state, reader):
    scope = _scope(state)
    return {
        "schema": NATIVE_RUN,
        "fixture_only": state.fixture_only,
        "role": "test",
        "scope_sha256": state.scope_sha256,
        "test_sha256": reader.manifest_sha256,
        "roster_sha256": scope["roster_sha256"],
        "profile_sha256": state.profile,
        "population_sha256": state.population_sha256,
        "inventory_sha256": scope["inventory_sha256"],
    }


def _intent(frontier, index, identity, worker, previous):
    entry = {
        "schema": "softqp.test-native-intent/1",
        "index": index,
        "frame": identity["frame"],
        "generation": worker.governed[0]["generation"],
        "nonce": worker.nonce,
        "previous": previous,
        "request_index": worker.index,
    }
    name = f"intent-{index:06d}.json"
    return {"path": name, "sha256": _atomic_document(frontier, name, entry)}


def supervise_test_native(admission, reader, destination):
    """Persistent actual 49 worker. An attempted ordinal cannot be redrawn."""
    state = _state(admission, "test-native")
    _reader(reader, admission)
    scope = _scope(state)
    root = phase._external_destination(Path(destination), state.context.root, state.context.forbidden_roots)
    frontier = phase._external_destination(
        Path(scope["frontier_root"]), state.context.root, state.context.forbidden_roots
    )
    c.ensure(root == Path(scope["native_root"]), "test-native destination differs")
    import shutil

    c.ensure(shutil.disk_usage(root.parent).free >= 20 * 2**30, "test native external disk minimum")
    # Keep the no-redraw frontier independent from the removable job tree.
    frontier.mkdir()
    _atomic_document(
        frontier, "intent.json", {"scope_sha256": state.scope_sha256, "test_sha256": reader.manifest_sha256}
    )
    root.mkdir()
    runtime = _NativeWorkerScope(state, reader)
    authority = _AuthorityReceipt(state.scope_sha256)
    rows, workers = [], []
    previous = None
    worker = None
    quota_base = _quota_existing(state)
    _quota(quota_base)
    staged = 0
    completed_work = 0
    try:
        for i, frame_id in enumerate(reader.frame_ids):
            if worker is None:
                generation = len(workers)
                worker, hello = native._start_governed_worker(root, authority, generation, runtime)
                workers.append(hello)
            _live(state)
            problem, identity = _native_problem(reader, frame_id, state)
            worker.identity = identity
            intent = _intent(frontier, i, identity, worker, previous)
            reference, cold, lost = native._run_input(worker, problem, identity, state.context)
            live_bytes = native._native_base_bytes((worker.root,))
            if lost is not None:
                completed_work += live_bytes
                live_bytes = 0
                worker = None
            outcome = _stage_attempt(problem, identity, reference, cold, state)
            value = {
                "schema": NATIVE_ATTEMPT,
                "index": i,
                "generation": generation,
                "identity": identity,
                "reference": _observation_wire(reference),
                "cold": _observation_wire(cold),
                **outcome,
            }
            path = f"attempt-{i:06d}.json"
            stored = {"path": path, "sha256": _atomic_document(root, path, value)}
            event = {"intent": intent, "attempt": stored, "state": outcome["state"]}
            name = f"terminal-{i:06d}.json"
            previous = {"path": name, "sha256": _atomic_document(frontier, name, event)}
            rows.append(
                {
                    "frame_id": frame_id,
                    "attempt": stored,
                    "terminal": previous,
                    "state": outcome["state"],
                    "reason": outcome["reason"],
                }
            )
            staged += (root / path).stat().st_size + (frontier / intent["path"]).stat().st_size
            staged += (frontier / name).stat().st_size
            _quota(quota_base + completed_work + live_bytes + staged)
        if worker is not None:
            worker.finish()
            worker = None
        _live(state)
        document = {**_header(state, reader), "workers": workers, "rows": rows}
        pending = "native-run-staged.json"
        digest = _atomic_document(root, pending, document)
        _read_test_native(admission, reader, root, digest, pending, frontier=frontier)
        os.link(root / pending, root / "native-run.json")
        (root / pending).unlink()
        return _read_test_native(admission, reader, root, digest, "native-run.json", frontier=frontier)
    finally:
        if worker is not None:
            worker.close()


@dataclass(frozen=True)
class TestNativeRun:
    root: Path
    manifest_sha256: str
    raw: bytes


def _receipt(root, ref):
    value = native._restore_custody(root, ref, limit=native._MANIFEST_LIMIT)
    return _json(value)


def _run_manifest(state, reader, raw):
    doc = _exact(_json(raw), set(_header(state, reader)) | {"workers", "rows"}, "test native run shape")
    c.ensure(all(doc[k] == v for k, v in _header(state, reader).items()), "native run ancestry differs")
    c.ensure(
        [r["frame_id"] for r in doc["rows"]] == list(reader.frame_ids) and bool(doc["workers"]),
        "native test outcome inventory differs",
    )
    return doc


def _guard_receipt(state, reader, root, ref, generation):
    hello = _receipt(root, ref)
    guardian = hello["guardian"]
    c.ensure(
        ref["path"] == f"worker-{generation:04d}-hello.json"
        and guardian["generation"] == generation
        and guardian["operation"] == state.operation
        and guardian["roles"] == ["test"]
        and guardian["fixture_only"] == state.fixture_only
        and hello["authority_sha256"] == state.scope_sha256
        and guardian["profile_sha256"] == state.profile
        and guardian["scope_sha256"]
        == native._hash(
            {
                "scope_sha256": state.scope_sha256,
                "test_sha256": reader.manifest_sha256,
                "policy_sha256": guardian["policy_sha256"],
                "roster_sha256": _scope(state)["roster_sha256"],
            }
        )
        and hello["audit"]["distributions"] == 49
        and hello["audit"]["full_files"]
        and hello["pid"] == hello["verified_files"]["pid"] != guardian["owner"],
        "observed test-native live-worker receipt differs",
    )
    return hello


def _check_attempt(state, reader, root, row, workers, index):
    value = _receipt(root, row["attempt"])
    problem, identity = _native_problem(reader, row["frame_id"], state)
    c.ensure(
        value["schema"] == NATIVE_ATTEMPT
        and value["index"] == index
        and value["identity"] == identity
        and row["attempt"]["path"] == f"attempt-{index:06d}.json",
        "test-native attempt linkage differs",
    )
    generation = value["generation"]
    c.ensure(type(generation) is int and 0 <= generation < len(workers), "test-native generation invalid")
    hello = workers[generation]
    raw_reference = _observation(value["reference"])
    raw_cold = _observation(value["cold"])
    for name, reply in (("reference", raw_reference), ("cold", raw_cold)):
        if reply is None or reply["status"] in native._TRANSPORT_FAILURES:
            continue
        expected = {
            "index": reply["index"],
            "nonce": hello["nonce"],
            "frame_id": row["frame_id"],
            "stage": name,
            "original": problem["original"] if name == "reference" else None,
            "generation": generation,
            "role": "test",
            "reference_sha256": native._hash(raw_reference) if name == "cold" else None,
        }
        c.ensure(
            reply["request_sha256"] == native._hash(expected) and reply["nonce"] == hello["nonce"],
            "observed test-native command digest differs",
        )
    native._expected_outcome(raw_reference, raw_cold, identity)
    expected = _stage_attempt(problem, identity, raw_reference, raw_cold, state)
    c.ensure(
        all(value.get(k) == v for k, v in expected.items())
        and (row["state"], row["reason"]) == (expected["state"], expected["reason"]),
        "test-native observation or numerical adjudication differs",
    )
    return value


def _read_test_native(admission, reader, root, digest, name, *, frontier):
    state = _state(admission, "test-native")
    _reader(reader, admission)
    root, frontier = (phase._exact_directory(Path(p)) for p in (root, frontier))
    c.ensure(
        root == Path(_scope(state)["native_root"]) and frontier == Path(_scope(state)["frontier_root"]),
        "test-native receipts are outside approved roots",
    )
    raw = phase._open_bytes(root, name, single_link=True)
    _checked(raw, digest, "test-native run")
    document = _run_manifest(state, reader, raw)
    workers = [_guard_receipt(state, reader, root, worker, i) for i, worker in enumerate(document["workers"])]
    previous = None
    for index, row in enumerate(document["rows"]):
        value = _check_attempt(state, reader, root, row, workers, index)
        terminal = _receipt(frontier, row["terminal"])
        intent = _receipt(frontier, terminal["intent"])
        c.ensure(
            row["terminal"]["path"] == f"terminal-{index:06d}.json"
            and terminal["intent"]["path"] == f"intent-{index:06d}.json"
            and terminal["attempt"] == row["attempt"]
            and terminal["state"] == row["state"]
            and intent["index"] == index
            and intent["frame"] == value["identity"]["frame"]
            and intent["generation"] == value["generation"]
            and intent["previous"] == previous,
            "test native durable frontier differs",
        )
        previous = row["terminal"]
    return TestNativeRun(root, digest, raw)


def read_test_native(admission, reader, root, *, expected_run_sha256):
    state = _state(admission, "test-native")
    return _read_test_native(
        admission,
        reader,
        root,
        expected_run_sha256,
        "native-run.json",
        frontier=Path(_scope(state)["frontier_root"]),
    )


def project_test_native(run, admission, reader, destination, *, expected_run_sha256):
    state = _state(admission, "test-native")
    _reader(reader, admission)
    c.ensure(
        type(run) is TestNativeRun
        and run.manifest_sha256 == expected_run_sha256
        and c.digest(run.raw) == expected_run_sha256,
        "test-native run has no independent seal",
    )
    verified = read_test_native(admission, reader, run.root, expected_run_sha256=expected_run_sha256)
    document = _run_manifest(state, reader, verified.raw)
    target = phase._external_destination(Path(destination), state.context.root, state.context.forbidden_roots)
    c.ensure(target == Path(_scope(state)["proof_root"]), "test-native proof root differs")
    bytes_used = _quota_existing(state)
    _quota(bytes_used)
    target.mkdir()
    records = [*document["workers"], *(row["attempt"] for row in document["rows"])]
    for ref in records:
        _live(state)
        value = _receipt(verified.root, ref)
        bytes_used += (verified.root / ref["path"]).stat().st_size
        _quota(bytes_used)
        c.ensure(
            _atomic_document(target, ref["path"], value) == ref["sha256"],
            "projected test-native custody bytes changed",
        )
    c.ensure(
        _atomic_document(target, "native-run.json", document) == expected_run_sha256,
        "projected native run bytes changed",
    )
    proof = {
        "schema": NATIVE_PROOF,
        "fixture_only": state.fixture_only,
        "scope_sha256": state.scope_sha256,
        "test_sha256": reader.manifest_sha256,
        "native_sha256": expected_run_sha256,
        "roster_sha256": _scope(state)["roster_sha256"],
        "records": records,
    }
    return _atomic_document(target, "proof.json", proof)


@dataclass(frozen=True)
class _ProofState:
    admission: HeldoutAdmission
    reader: TestInputReader
    root: Path
    rows: object


_PROOFS = WeakKeyDictionary()


class TestNativeProof:
    """Candidate may access its test-local pair and oracle rows only after exact N/J seals."""

    @classmethod
    def open(
        cls,
        admission,
        test_root,
        proof_root,
        *,
        expected_test_sha256,
        expected_run_sha256,
        expected_projection_sha256,
    ):
        state = _state(admission, "candidate")
        seals = _json(state.policy_bytes)["expected"]
        c.ensure(
            seals
            == {
                "test_sha256": expected_test_sha256,
                "native_sha256": expected_run_sha256,
                "proof_sha256": expected_projection_sha256,
            },
            "independent candidate T/N/J seals differ",
        )
        target = phase._exact_directory(Path(proof_root))
        c.ensure(target == Path(_scope(state)["proof_root"]), "candidate test-native proof root differs")
        proof = _checked(
            phase._open_bytes(target, "proof.json", single_link=True),
            expected_projection_sha256,
            "test-native proof",
        )
        raw = phase._open_bytes(target, "native-run.json", single_link=True)
        _checked(raw, expected_run_sha256, "test-native run")
        reader = _open_reader(admission, test_root, expected_test_sha256)
        document = _run_manifest(state, reader, raw)
        records = [*document["workers"], *(row["attempt"] for row in document["rows"])]
        c.ensure(
            proof
            == {
                "schema": NATIVE_PROOF,
                "fixture_only": state.fixture_only,
                "scope_sha256": state.scope_sha256,
                "test_sha256": expected_test_sha256,
                "native_sha256": expected_run_sha256,
                "roster_sha256": _scope(state)["roster_sha256"],
                "records": records,
            },
            "candidate native proof or roster differs",
        )
        physical_paths = {"proof.json", "native-run.json"} | {row["path"] for row in records}
        c.ensure(
            {path.name for path in target.iterdir()} == physical_paths
            and len(physical_paths) == len(records) + 2,
            "candidate proof files differ",
        )
        for i, ref in enumerate(document["workers"]):
            _guard_receipt(state, reader, target, ref, i)
        local = _reader(reader, admission)
        rows = {}
        for i, row in enumerate(document["rows"]):
            value = _receipt(target, row["attempt"])
            c.ensure(
                value["schema"] == NATIVE_ATTEMPT
                and value["index"] == i
                and value["identity"] == local.slots[row["frame_id"]]
                and value["state"] == row["state"]
                and value["reason"] == row["reason"],
                "candidate test-native custody index mismatch",
            )
            rows[row["frame_id"]] = c.canonical_bytes(row)
        admitted = cls()
        _PROOFS[admitted] = _ProofState(admission, reader, target, rows)
        _CANDIDATE_READERS[reader] = admission
        return admitted

    @property
    def reader(self):
        c.ensure(type(self) is TestNativeProof and self in _PROOFS, "unissued test-native proof")
        proof = _PROOFS[self]
        _state(proof.admission, "candidate")
        return proof.reader

    def read_outcome(self, frame_id):
        c.ensure(type(self) is TestNativeProof and self in _PROOFS, "unissued test-native proof")
        proof = _PROOFS[self]
        _state(proof.admission, "candidate")
        c.ensure(frame_id in proof.rows, "test-native outcome absent")
        # The independent observed seal is checked per open. Timed numerical
        # reconstruction remains the candidate leaf's job.
        row = _json(proof.rows[frame_id])
        attempt = _receipt(proof.root, row["attempt"])
        c.ensure(
            attempt["identity"] == _reader(proof.reader).slots[frame_id],
            "test-native outcome frame identity differs",
        )
        return {key: attempt[key] for key in ("state", "reason", "identity", "oracle_rows", "label")}


def _launch_arguments(raw, custody, *, read_only=False):
    from softqp_heldout_runtime_custody import active_profile_sha256, read_policy
    from .authority import load_i1_authority
    from .generator import _dispatch_context
    from dataclasses import replace

    req = _json(raw)
    capability = {"read_only": True} if read_only else {}
    profile = active_profile_sha256(custody, **capability)
    binding = {
        "operation": req["operation"],
        "stage": req["stage"],
        "request_sha256": c.digest(raw),
        "source_file": Path(__file__).resolve(),
        "profile_sha256": profile,
        **capability,
    }
    policy_bytes = read_policy(custody, **binding)
    policy = _json(policy_bytes)
    data = _exact(
        policy["inputs"],
        {"admission", "metadata", "p0", "p1", "index", "roster_root", "roster"},
        "held-out launch metadata shape differs",
    )
    fixture = req["operation"] == "evaluate-heldout-fixture"
    metadata = phase._exact_directory(Path(data["metadata"]))
    if fixture:
        from test_heldout_inputs import fixture_context

        context = fixture_context(data["admission"], metadata, profile)
        i1 = None
    else:
        configuration = dict(data["admission"])
        context_ref = configuration.pop("context")
        trust, context, protocol = _dispatch_context(configuration)
        c.ensure(metadata == trust.governance_root, "held-out independent metadata root differs")
        product = _json(native._native_scope_file(metadata, context_ref))
        _exact(
            product,
            {"catalog", "problem_hashes", "source_records", "fit_source_ids", "settings_hashes"},
            "held-out detached canonical context shape",
        )
        c.ensure(
            product["catalog"].get(protocol["artifact_id"]) == protocol, "held-out approved protocol differs"
        )
        context = replace(
            context,
            catalog=product["catalog"],
            problem_hashes=product["problem_hashes"],
            source_records=product["source_records"],
            fit_source_ids=tuple(product["fit_source_ids"]),
            settings_hashes=product["settings_hashes"],
        )
        if read_only:
            from .authority import _verify_historical_recovery

            _verify_historical_recovery(trust, context, protocol, custody, request_sha256=c.digest(raw))
            i1 = None
        else:
            i1 = load_i1_authority(trust=trust, context=context, protocol_ref=protocol)

    def preflight(ref):
        content = native._native_scope_file(metadata, ref)
        receipt = _json(content)
        return phase.PhasePreflight(
            Path(receipt["source_root"]), tuple(Path(p) for p in receipt["forbidden_roots"]), content
        )

    p0, p1 = preflight(data["p0"]), preflight(data["p1"])
    protocol_ref = _json(p0.receipt_bytes)["protocol_ref"]
    index = native._native_scope_file(metadata, data["index"])
    roster = []
    for entry in data["roster"]:
        _exact(entry, {"state", "trust"}, "held-out roster trust wire")
        spec = dict(entry["trust"])
        if entry["state"] == "available":
            cls = models.ModelTrust
            root_fields = ("bundle_root", "preprocessing_root", "frozen_root")
        else:
            c.ensure(entry["state"] in ("failed", "missing"), "invalid held-out roster disposition")
            cls = models.FailedModelTrust
            root_fields = ("root",)
        _exact(spec, set(cls.__dataclass_fields__), "held-out model trust wire")
        for name in root_fields:
            spec[name] = Path(spec[name])
        roster.append(cls(**spec))
    return req, admit_heldout(
        guardian=custody,
        i1=i1,
        request=raw,
        policy=policy_bytes,
        expected_policy_sha256=c.digest(policy_bytes),
        context=context,
        protocol_ref=protocol_ref,
        p0=p0,
        p1=p1,
        index_bytes=index,
        roster_root=Path(data["roster_root"]),
        roster_trust=tuple(roster),
        expected_roster_sha256=req["roster_sha256"],
        read_only=read_only,
    )


def dispatch_heldout_inputs(raw, custody):
    """Fixed parent entry for the observed test-native predecessor of candidate bake."""
    req, admission = _launch_arguments(raw, custody)
    state = _state(admission, "test-native")
    scope = _scope(state)
    reader = materialize_test_inputs(admission, destination=scope["test_root"])
    run = supervise_test_native(admission, reader, scope["native_root"])
    # This process independently observed publication; only an external pinned
    # policy may subsequently appoint it as expected candidate input.
    proof = project_test_native(
        run, admission, reader, scope["proof_root"], expected_run_sha256=run.manifest_sha256
    )
    _live(state)
    return {
        "schema": "softqp.heldout-inputs-result/1",
        "fixture_only": state.fixture_only,
        "request_sha256": c.digest(raw),
        "policy_sha256": state.policy_sha256,
        "scope_sha256": state.scope_sha256,
        "roster_sha256": req["roster_sha256"],
        "test_sha256": reader.manifest_sha256,
        "native_sha256": run.manifest_sha256,
        "proof_sha256": proof,
    }


def admit_candidate_inputs(raw, custody, *, read_only=False):
    """Fixed evaluator opens candidate proof only from separately issued stage policy."""
    _, admission = _launch_arguments(raw, custody, read_only=read_only)
    state = _state(admission, "candidate")
    sealed = _json(state.policy_bytes)["expected"]
    scope = _scope(state)
    return TestNativeProof.open(
        admission,
        scope["test_root"],
        scope["proof_root"],
        expected_test_sha256=sealed["test_sha256"],
        expected_run_sha256=sealed["native_sha256"],
        expected_projection_sha256=sealed["proof_sha256"],
    )


@dataclass(frozen=True, slots=True)
class CandidateModelFailure:
    evidence: bytes


_CANDIDATE_VIEWS = WeakKeyDictionary()


class CandidateView:
    """Identity-only access to the already admitted candidate metadata."""

    def _verified(self):
        c.ensure(type(self) is CandidateView and self in _CANDIDATE_VIEWS, "unissued candidate view")
        proof = _CANDIDATE_VIEWS[self]
        state = _state(proof.admission, "candidate")
        return proof, state

    def identities(self):
        _, state = self._verified()
        policy = _json(state.policy_bytes)
        return dict(
            scope_sha256=state.scope_sha256,
            request_sha256=state.request_sha256,
            policy_sha256=state.policy_sha256,
            profile_sha256=state.profile,
            roster_sha256=policy["scope"]["roster_sha256"],
            fixture_only=state.fixture_only,
            **policy["expected"],
        )

    def frame_index(self):
        proof, _ = self._verified()
        return {_slot_key(row): identifier for identifier, row in _reader(proof.reader).slots.items()}

    def authority(self):
        from dataclasses import replace

        _, state = self._verified()
        return replace(state.context.authority)

    def settings_hashes(self):
        _, state = self._verified()
        return dict(state.context.settings_hashes)

    def model_binding(self, method, seed):
        from dataclasses import replace

        _, state = self._verified()
        entries = dict(state.candidate_models)
        c.ensure((method, seed) in entries, "candidate model outside the fixed roster")
        return replace(entries[method, seed])


def candidate_view(proof):
    c.ensure(type(proof) is TestNativeProof and proof in _PROOFS, "unissued candidate proof")
    state = _PROOFS[proof]
    _state(state.admission, "candidate")
    view = CandidateView()
    _CANDIDATE_VIEWS[view] = state
    return view
