"""Independent I1 approval and current-runtime verification for R4 execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata, util
from hashlib import sha256
from pathlib import Path
import platform
import re
import subprocess
import sys
from weakref import WeakKeyDictionary

from . import contracts as c


_OPERATIONS = frozenset({"generate-source", "native-label", "train-model", "calibrate-model", "evaluate-heldout"})
_EVIDENCE = frozenset({"runtime", "seed_inventory", "semantic_matrix", "compatibility", "math_gates"})
_REQUIRED_FILES = frozenset(
    "data-pipeline/pipeline/learned_comparison/" + name
    for name in ("authority.py", "contracts.py", "generator.py", "stream_inputs.py")
)
_GENERATOR = "data-pipeline/pipeline/learned_comparison/generator.py"
_SCIENTIFIC_PACKAGES = frozenset({
    "numpy", "scipy", "softqp", "osqp", "daqp", "clarabel", "piqp", "torch", "torch-geometric", "jsonschema",
})
_PACKAGE_MODULES = {"torch-geometric": "torch_geometric"}
_ENGINE_CHECKER = "environments/method-extension-cpu/check_lock.py"
_CHECK_BOOTSTRAP = """import sys
from pathlib import Path
prefix = Path(sys.argv[1]).resolve(strict=True)
sys.prefix = sys.exec_prefix = str(prefix)
site = prefix / "Lib" / "site-packages"
if not site.is_dir():
    raise RuntimeError("Locked Windows CPU site-packages unavailable")
sys.path.append(str(site))
sys.argv = [sys.argv[2], *sys.argv[3:]]
scope = {"__name__": "__main__", "__file__": sys.argv[0]}
exec(compile(sys.stdin.buffer.read(), sys.argv[0], "exec", optimize=0), scope)
"""
_ISSUED = WeakKeyDictionary()
_MODULE_BYTES = Path(__file__).read_bytes()
_LIMIT = 16 * 2**20
_GENERATOR_FILE = Path(__file__).with_name("generator.py")
_GENERATOR_SLOT_KEYS = ("family", "regime", "split", "unit")
_GENERATOR_DRAWS = set()


@dataclass(frozen=True)
class _GeneratorWorkerScope:
    custody: object
    request_sha256: str
    policy_sha256: str
    slot: tuple


def _worker_policy(custody, request_sha256, *, profile_sha256=None):
    worker = sys.modules.get("softqp_runtime_custody")
    c.ensure(worker is not None and sys.flags.isolated and sys.flags.no_site
             and sys.flags.dont_write_bytecode, "registered generation requires the verified owned worker")
    try:
        profile = {} if profile_sha256 is None else {"profile_sha256": profile_sha256}
        raw = worker.read_active_policy(
            custody, operation="generate-source", request_sha256=request_sha256, source_file=_GENERATOR_FILE,
            **profile,
        )
    except (AttributeError, TypeError, ValueError, RuntimeError) as error:
        raise c.ContractError("verified generator worker scope is unavailable") from error
    c.ensure(type(raw) is bytes and len(raw) <= _LIMIT, "invalid owned generator launch policy")
    return raw


def generator_worker_policy(custody, raw_request):
    """Read governed configuration from the active worker, never the request."""
    c.ensure(type(raw_request) is bytes and len(raw_request) <= 4096, "invalid bounded generator request")
    request_sha256 = c.digest(raw_request)
    raw_policy = _worker_policy(custody, request_sha256)
    return _json(raw_policy), request_sha256, c.digest(raw_policy)


def _campaign_worker():
    worker = sys.modules.get("softqp_runtime_custody")
    c.ensure(worker is not None and sys.flags.isolated and sys.flags.no_site
             and sys.flags.dont_write_bytecode, "registered campaign requires the verified owned worker")
    return worker


def campaign_worker_policy(custody, raw_request, *, profile_sha256=None):
    c.ensure(type(raw_request) is bytes and len(raw_request) <= 4096, "invalid bounded campaign request")
    request_sha256 = c.digest(raw_request)
    scope = {} if profile_sha256 is None else {"profile_sha256": profile_sha256}
    try:
        raw = _campaign_worker().read_active_campaign_policy(
            custody, request_sha256=request_sha256, source_file=_GENERATOR_FILE, **scope,
        )
    except (AttributeError, TypeError, ValueError, RuntimeError) as error:
        raise c.ContractError("verified owned worker campaign scope is unavailable") from error
    c.ensure(type(raw) is bytes and len(raw) <= _LIMIT, "invalid owned campaign launch policy")
    return _json(raw), request_sha256


def activate_campaign_slot(custody, request_sha256, slot_request, slot_policy, *, ordinal):
    """Request a one-use child scope from the already verified campaign worker."""
    try:
        return _campaign_worker().activate_generator_slot(
            custody, request_sha256=request_sha256, source_file=_GENERATOR_FILE, ordinal=ordinal,
            slot_request=slot_request, slot_policy=slot_policy,
        )
    except (AttributeError, TypeError, ValueError, RuntimeError) as error:
        raise c.ContractError("verified owned worker refused the campaign child scope") from error


def _require_generator_scope(scope, slot, *, profile_sha256=None):
    c.ensure(type(scope) is _GeneratorWorkerScope and scope.slot == slot,
             "registered source slot differs from the owned worker scope")
    slot_record = dict(zip(_GENERATOR_SLOT_KEYS, slot, strict=True))
    c.ensure(_digest({"schema": "softqp.r4.generate-source-request/1", "slot": slot_record})
             == scope.request_sha256, "owned generator request digest differs from source slot")
    raw = _worker_policy(scope.custody, scope.request_sha256, profile_sha256=profile_sha256)
    c.ensure(c.digest(raw) == scope.policy_sha256, "governed generator launch policy changed")
    policy = _json(raw)
    c.ensure(policy.get("schema") == "softqp.r4.generate-source-policy/1"
             and c.canonical_bytes(policy.get("slot")) == c.canonical_bytes(slot_record),
             "owned generator launch policy grants a different slot")


@dataclass(frozen=True)
class ApprovalTrust:
    """Configured by the governed operator independently of a submitted run.

    The approved-index digest and named reviewer are trust inputs. The index,
    its directory and these expected values must come from the independent
    approval channel, never the dataset or the author submitting a run.
    """

    governance_root: Path
    index_path: str
    expected_index_sha256: str
    expected_reviewer: str
    product_root: Path
    engine_root: Path
    fixture_only: bool = False


def _shape(value, keys, message):
    c.ensure(type(value) is dict and set(value) == set(keys), message)
    return value


def _hex(value, digits=64):
    return type(value) is str and re.fullmatch("[0-9a-f]{" + str(digits) + "}", value) is not None


def _digest(value):
    return c.digest(c.canonical_bytes(value))


def _read(root, path, expected):
    c.ensure(_hex(expected), "invalid independently expected I1 file hash")
    file = c.safe_path(root, path, must_exist=True)
    c.ensure(file.is_file() and file.stat().st_size <= _LIMIT, "invalid bounded I1 evidence file")
    raw = file.read_bytes()
    c.ensure(len(raw) <= _LIMIT and c.digest(raw) == expected, "I1 evidence byte identity mismatch")
    return raw


def _json(raw):
    record = c.strict_loads(raw)
    c.ensure(type(record) is dict and c.canonical_bytes(record) == raw, "noncanonical I1 evidence")
    return record


def _reference(root, reference):
    ref = _shape(reference, {"path", "sha256"}, "invalid governed I1 reference")
    return _read(root, ref["path"], ref["sha256"])


def _head(root):
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD^{commit}"],
                            capture_output=True, check=False, text=True, timeout=10)
    c.ensure(result.returncode == 0 and _hex(result.stdout.strip(), 40), "unavailable I1 source commit")
    return result.stdout.strip()


def _sources(lock, trust, *, verify_committed=False):
    c.ensure(_head(trust.product_root) == lock["product_commit"]
             and _head(trust.engine_root) == lock["engine_commit"], "I1 source commit differs")
    files = lock["files"]
    c.ensure(type(files) is dict and _REQUIRED_FILES <= files.keys(), "incomplete I1 source map")
    for path, expected in files.items():
        _read(trust.product_root, path, expected)
        if verify_committed and not trust.fixture_only:
            frozen = subprocess.run(
                ["git", "-C", str(trust.product_root), "show", f"{lock['product_commit']}:{path}"],
                capture_output=True, check=False, timeout=10,
            )
            c.ensure(frozen.returncode == 0 and c.digest(frozen.stdout) == expected,
                     "I1 source map does not match the reviewed Git object")
    module = Path(__file__).resolve()
    path = module.relative_to(trust.product_root.resolve()).as_posix()
    c.ensure(path in files and c.digest(_MODULE_BYTES) == files[path], "loaded I1 verifier source differs")


def _runtime(runtime, trust, dependency_lock_sha256, *, full=False):
    _shape(runtime, {"schema", "decision", "dependency_lock_sha256", "python_version",
                     "python_sha256", "packages", "worker_count", "profile", "profile_sha256",
                     "verifier_sha256"}, "invalid locked runtime receipt")
    c.ensure(runtime["schema"] == "softqp.r4.runtime/1" and runtime["decision"] == "accepted"
             and runtime["dependency_lock_sha256"] == dependency_lock_sha256
             and runtime["worker_count"] == 1, "runtime is not independently admitted")
    c.ensure(runtime["python_version"] == platform.python_version()
             and runtime["python_sha256"] == c.digest(Path(sys.executable).read_bytes()),
             "active Python differs from I1 runtime")
    required = {"numpy"} if trust.fixture_only else _SCIENTIFIC_PACKAGES
    packages = runtime["packages"]
    c.ensure(type(packages) is dict and required <= packages.keys(), "I1 runtime package coverage differs")
    for name, entry in packages.items():
        _shape(entry, {"version", "module", "sha256"}, "invalid I1 package identity")
        c.ensure(entry["module"] == _PACKAGE_MODULES.get(name, name),
                 "I1 distribution-to-module identity differs")
        spec = util.find_spec(entry["module"])
        c.ensure(spec is not None and spec.origin is not None and metadata.version(name) == entry["version"]
                 and c.digest(Path(spec.origin).read_bytes()) == entry["sha256"],
                 f"active I1 runtime package differs: {name}")
        if not trust.fixture_only:
            c.ensure(Path(spec.origin).resolve().is_relative_to(Path(sys.prefix).resolve()),
                     f"active I1 package is outside the locked runtime: {name}")
    if trust.fixture_only:
        c.ensure(all(runtime[k] is None for k in ("profile", "profile_sha256", "verifier_sha256")),
                 "fixture-only I1 runtime cannot represent a scientific profile")
        return
    c.ensure(type(runtime["profile"]) is str and bool(runtime["profile"]), "missing scientific I1 runtime profile")
    profile_file = c.safe_path(trust.governance_root, runtime["profile"] + "/provenance.json", must_exist=True)
    profile_root = profile_file.parent
    raw = _read(profile_root, "provenance.json", runtime["profile_sha256"])
    profile = c.strict_loads(raw)
    c.ensure(profile["requirements_sha256"] == dependency_lock_sha256, "I1 runtime profile differs from dependency lock")
    locked = {re.sub(r"[-_.]+", "-", row["name"]).lower(): row["version"] for row in profile["distributions"]}
    c.ensure(required <= locked.keys() and all(locked.get(name) == entry["version"]
                                             for name, entry in packages.items()),
             "I1 runtime package entries differ from the locked profile")
    _read(profile_root, "requirements.lock", dependency_lock_sha256)
    checker = c.safe_path(trust.engine_root, _ENGINE_CHECKER, must_exist=True)
    checker_raw = _read(trust.engine_root, _ENGINE_CHECKER, runtime["verifier_sha256"])
    if full:
        frozen = subprocess.run(["git", "-C", str(trust.engine_root), "show", f"HEAD:{_ENGINE_CHECKER}"],
                                capture_output=True, check=False, timeout=10)
        c.ensure(frozen.returncode == 0 and c.digest(frozen.stdout) == runtime["verifier_sha256"],
                 "I1 runtime verifier differs from reviewed engine Git object")
        observed = subprocess.run([
            sys.executable, "-I", "-S", "-B", "-c", _CHECK_BOOTSTRAP, sys.prefix, str(checker),
            "--check", "--full-files",
            "--profile", str(profile_root), "--expected-profile-sha256", runtime["profile_sha256"],
        ], input=checker_raw, capture_output=True, check=False, timeout=600)
        c.ensure(observed.returncode == 0, "active I1 runtime failed the full installed-file gate")
        outcome = c.strict_loads(observed.stdout)
        c.ensure(outcome == {
            "distributions": len(profile["distributions"]),
            "full_source_files_checked": sum(row["source_file_count"] for row in profile["distributions"]),
            "full_files": True,
            "read_only": True,
        }, "I1 verifier did not check the complete installed runtime")
    if full:
        # The generator's only numerical package is NumPy. Recheck all its
        # installed source/native file bytes before source draws or writes.
        verifier = {"__name__": "softqp_pinned_engine_check_lock", "__file__": str(checker)}
        exec(compile(checker_raw, str(checker), "exec", optimize=0), verifier)
        row = next(item for item in profile["distributions"] if item["name"].lower() == "numpy")
        prefix = Path(sys.prefix).resolve()
        plan = verifier["_source_plan"](metadata.distribution("numpy"), prefix)
        entries = [entry for entry, _ in plan]
        c.ensure(len(entries) == row["source_file_count"]
                 and sha256(verifier["encode"](entries)).hexdigest() == row["source_manifest_sha256"],
                 "I1 NumPy full source manifest differs")
        numerical_core = util.find_spec("numpy._core._multiarray_umath")
        c.ensure(numerical_core is not None and numerical_core.origin is not None,
                 "active I1 NumPy numerical core missing")
        core = Path(numerical_core.origin).resolve()
        c.ensure(core in {path for _, path in plan}, "active I1 NumPy numerical core outside source manifest")
        for (relative, recorded, size), path in plan:
            try:
                verifier["_verify_source"](path, relative, recorded, size)
            except AssertionError as error:
                raise c.ContractError("I1 active NumPy source bytes differ") from error


def _verify(trust, context, protocol_ref, generator_scope=None):
    c.ensure(type(trust) is ApprovalTrust and type(context) is c.AdmissionContext
             and trust.fixture_only == context.allow_fixture, "I1 trust lane mismatch")
    governance = trust.governance_root.resolve(strict=True)
    submitted = context.root.resolve(strict=True)
    c.ensure(governance != submitted and not governance.is_relative_to(submitted)
             and not submitted.is_relative_to(governance), "I1 governance cannot be supplied by the run")
    index = _shape(_json(_read(governance, trust.index_path, trust.expected_index_sha256)),
                   {"schema", "lane", "reviewer", "registration", "review", "protocol_sha256",
                    "protocol_ref", "evidence"},
                   "invalid independent approved index")
    lane = "contract-fixture" if trust.fixture_only else "scientific"
    c.ensure(index["schema"] == "softqp.r4.approved-index/1" and index["lane"] == lane
             and index["reviewer"] == trust.expected_reviewer and bool(trust.expected_reviewer.strip())
             and index["protocol_sha256"] == context.protocol_sha256, "unapproved I1 index identity")
    c.ensure(index["protocol_ref"] == protocol_ref, "I1 actual protocol file differs from independent index")
    registration_raw = _reference(governance, index["registration"])
    review_raw = _reference(governance, index["review"])
    c.ensure(c.digest(registration_raw) == context.registration_sha256, "I1 registration identity differs")
    registration = _shape(_json(registration_raw), {"schema", "subject", "review_sha256"}, "invalid I1 registration")
    subject = _shape(registration["subject"], {
        "design_manifest_sha256", "protocol_core_sha256", "product_commit", "engine_commit",
        "source_lock_sha256", "dependency_lock_sha256", "generator_sha256", "operations",
        "runtime_sha256", "seed_inventory_sha256", "semantic_matrix_sha256", "compatibility_sha256",
        "math_gates_sha256",
    }, "invalid I1 registration subject")
    review = _shape(_json(review_raw), {
        "schema", "decision", "subject_sha256", "reviewer", "implementer", "signed_at",
    }, "invalid independent I1 signoff")
    try:
        signed = datetime.fromisoformat(review["signed_at"])
    except (TypeError, ValueError) as error:
        raise c.ContractError("invalid I1 signoff timestamp") from error
    c.ensure(registration["schema"] == "softqp.r4.registration/1"
             and registration["review_sha256"] == c.digest(review_raw)
             and review["schema"] == "softqp.r4.review/1" and review["decision"] == "I1-accepted"
             and review["subject_sha256"] == _digest(subject)
             and review["reviewer"] == index["reviewer"]
             and type(review["implementer"]) is str and bool(review["implementer"].strip())
             and review["implementer"].strip().casefold() != review["reviewer"].strip().casefold()
             and signed.tzinfo is not None and signed <= datetime.now(timezone.utc),
             "I1 review does not independently sign the exact subject")
    operations = subject["operations"]
    c.ensure(type(operations) is list and bool(operations) and all(type(v) is str for v in operations)
             and operations == sorted(set(operations))
             and set(operations) <= _OPERATIONS, "unrecognized I1 operation scope")
    c.ensure(subject["design_manifest_sha256"] == c.DESIGN_MANIFEST_SHA256
             and subject["source_lock_sha256"] == context.source_lock_sha256
             and subject["dependency_lock_sha256"] == context.dependency_lock_sha256
             and subject["generator_sha256"] == context.generator_sha256,
             "I1 review source/lock identity differs")
    lock = _shape(_json(context.source_lock_bytes), {"schema", "product_commit", "engine_commit", "files"},
                  "invalid governed I1 source lock")
    c.ensure(lock["schema"] == "softqp.r4.source-lock/1"
             and all(subject[k] == lock[k] and _hex(lock[k], 40) for k in ("product_commit", "engine_commit")),
             "I1 reviewed source commits differ from source lock")
    c.ensure(type(lock["files"]) is dict and lock["files"].get(_GENERATOR) == context.generator_sha256,
             "I1 generator differs from source lock")
    _sources(lock, trust, verify_committed=True)
    refs = _shape(index["evidence"], _EVIDENCE, "incomplete I1 engineering evidence")
    examined = {}
    for kind, ref in refs.items():
        raw = _reference(governance, ref)
        c.ensure(c.digest(raw) == subject[kind + "_sha256"], f"unreviewed I1 {kind} evidence")
        examined[kind] = raw
    bindings = context.authority.manifest["normative_sha256"]
    c.ensure(subject["semantic_matrix_sha256"] == bindings["semantic-matrix.json"]
             and subject["seed_inventory_sha256"] == bindings["expected-keysets/inventory.json"],
             "I1 semantic matrix or expected keyset differs")
    compatibility = _shape(_json(examined["compatibility"]), {"decision", "semantic_matrix_sha256"},
                           "invalid reviewed compatibility evidence")
    math_gates = _shape(_json(examined["math_gates"]), {"decision", "generator_sha256"},
                        "invalid reviewed mathematical evidence")
    c.ensure(compatibility == {"decision": "accepted", "semantic_matrix_sha256": subject["semantic_matrix_sha256"]}
             and math_gates == {"decision": "accepted", "generator_sha256": context.generator_sha256},
             "I1 engineering evidence lacks exact subject acceptance")
    runtime = _json(examined["runtime"])
    if generator_scope is not None:
        c.ensure(_hex(runtime.get("profile_sha256")), "I1 runtime requires an exact live worker profile")
        _require_generator_scope(generator_scope, generator_scope.slot, profile_sha256=runtime["profile_sha256"])
    _runtime(runtime, trust, context.dependency_lock_sha256, full=generator_scope is None)
    c.ensure(context.catalog.get(protocol_ref["artifact_id"]) == protocol_ref
             and protocol_ref["kind"] == "learning-protocol", "I1 protocol reference is not sealed")
    path = c.safe_path(context.root, protocol_ref["path"], must_exist=True)
    protocol = c.read_artifact(path, context, expected_sha256=protocol_ref["sha256"])
    payload = protocol.payload
    c.ensure(payload is not None and payload["status"] == "registered"
             and (protocol.document["purpose"] == "contract-fixture") == trust.fixture_only
             and payload["split_units"] == context.authority.matrix["split_units"]
             and payload["network_seeds"] == list(c.SEEDS)
             and payload["source_entropy_prefix"] == [20261105, 903]
             and _digest({k: v for k, v in payload.items() if k != "registration_sha256"})
             == subject["protocol_core_sha256"], "I1 registered protocol or registration back-reference differs")
    return frozenset(operations), lock, runtime, (index["registration"], index["review"], *refs.values())


@dataclass(frozen=True)
class _IssuedApproval:
    trust: ApprovalTrust
    context: c.AdmissionContext
    protocol_ref: dict
    operations: frozenset
    lock: dict
    runtime: dict
    approved_refs: tuple
    generator_scope: _GeneratorWorkerScope | None


class I1Authority:
    """Opaque process-local authority issued only after independent verification."""

    __slots__ = ("__weakref__",)

    @property
    def registration_sha256(self):
        return _ISSUED[self].context.registration_sha256

    @property
    def source_lock_sha256(self):
        return _ISSUED[self].context.source_lock_sha256

    @property
    def design_manifest_sha256(self):
        return c.DESIGN_MANIFEST_SHA256

    @property
    def protocol_id(self):
        return _ISSUED[self].context.protocol_id

    @property
    def protocol_sha256(self):
        return _ISSUED[self].context.protocol_sha256

    @property
    def runtime_profile_sha256(self) -> str | None:
        """The independently approved profile; fixture parser records have none."""
        state = _ISSUED.get(self)
        c.ensure(state is not None, "independently authenticated I1 authority unavailable")
        return state.runtime["profile_sha256"]

    def allows(self, operation):
        state = _ISSUED.get(self)
        return (state is not None and operation in state.operations and not state.trust.fixture_only
                and (operation != "generate-source" or state.generator_scope is not None))


def load_i1_authority(*, trust, context, protocol_ref, generator_scope=None):
    """Admit actual approved bytes from a separately configured governance root."""
    if generator_scope is not None:
        c.ensure(type(generator_scope) is _GeneratorWorkerScope and not trust.fixture_only,
                 "invalid scientific generator scope")
        _require_generator_scope(generator_scope, generator_scope.slot)
    operations, lock, runtime, approved_refs = _verify(trust, context, protocol_ref, generator_scope)
    authority = I1Authority()
    _ISSUED[authority] = _IssuedApproval(
        trust, context, dict(protocol_ref), operations, lock, runtime, approved_refs, generator_scope,
    )
    return authority


def require_i1(authority, operation, *, context, protocol_ref, generator_slot=None):
    """Recheck active source and runtime before scientific work."""
    state = _ISSUED.get(authority) if type(authority) is I1Authority else None
    c.ensure(state is not None and authority.allows(operation), "independently authenticated I1 authority unavailable")
    if operation == "generate-source":
        _require_generator_scope(state.generator_scope, generator_slot, profile_sha256=state.runtime["profile_sha256"])
    approved = state.context
    c.ensure(type(context) is c.AdmissionContext and not context.allow_fixture
             and context.root.resolve() == approved.root.resolve()
             and protocol_ref == state.protocol_ref
             and all(getattr(context, name) == getattr(approved, name) for name in (
                 "registration_sha256", "source_lock_sha256", "generator_sha256", "producer_source_sha256",
                 "dependency_lock_sha256", "protocol_id", "protocol_sha256", "source_lock_bytes",
                 "dependency_lock_bytes", "generator_source_bytes", "producer_source_bytes",
             )), "I1 runtime context differs")
    _read(state.trust.governance_root, state.trust.index_path, state.trust.expected_index_sha256)
    for ref in state.approved_refs:
        _reference(state.trust.governance_root, ref)
    c.ensure(context.catalog.get(protocol_ref["artifact_id"]) == protocol_ref, "I1 protocol is no longer sealed")
    _read(context.root, protocol_ref["path"], protocol_ref["sha256"])
    _sources(state.lock, state.trust)
    _runtime(state.runtime, state.trust, approved.dependency_lock_sha256)
    if operation == "generate-source":
        _require_generator_scope(state.generator_scope, generator_slot, profile_sha256=state.runtime["profile_sha256"])


def claim_generator_draw(authority, *, context, protocol_ref, generator_slot):
    """Consume the active worker's single scientific draw after fresh admission."""
    require_i1(authority, "generate-source", context=context, protocol_ref=protocol_ref,
               generator_slot=generator_slot)
    scope = _ISSUED[authority].generator_scope
    identity = (id(scope.custody), scope.request_sha256)
    c.ensure(identity not in _GENERATOR_DRAWS, "owned generator request already consumed its scientific draw")
    _GENERATOR_DRAWS.add(identity)
