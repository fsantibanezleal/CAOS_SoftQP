"""Owned SDK execution and independent custody for v2 native labels."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import runpy
import secrets
import signal
import stat
import subprocess
import sys
import time
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .contracts import AdmissionContext
    from .phase_inputs import PhasePreflight
    from .stream_inputs import StreamingPhaseReader

VERSION = "1.0.0"
AUTHORITY = "softqp.native-label-authority/v1"
MANIFEST = "softqp.native-run/v1"
ATTEMPT = "softqp.native-attempt/v1"
ROLE = "softqp.native-role/v1"
_BACKENDS = ("stock-osqp", "clarabel", "piqp")
_VERSIONS = dict(zip(_BACKENDS, ("1.1.3", "0.11.1", "0.6.4"), strict=True))
_FLAGS = {"stock-osqp": "solved", "clarabel": "Solved", "piqp": "Status.PIQP_SOLVED"}
_ROLE_ORDER = ("train", "validation", "calibration")
_PEAK_LIMIT = 8 * 2**30
_FILE_LIMIT = 8 * 2**20
_MANIFEST_LIMIT = 64 * 2**20
_DIAGNOSTIC_LIMIT = 16 * 2**20
_DISK_LIMIT = 8 * 2**30
_VERIFY_SECONDS = 600
_IMPORT_SECONDS = 180
_TRIAL_SECONDS = 30
_TRANSPORT_FAILURES = ("timeout", "worker-exit")
_WORKER_SOURCE = (
    "learned_comparison/native_labels.py",
    "learned_comparison/contracts.py",
    "learned_comparison/stream_inputs.py",
    "learned_comparison/phase_inputs.py",
    "lesson_process.py",
    "coupled_resources.py",
)


def _encode(value):
    # Native custody preserves IEEE signed zero. The v2 label serialization
    # uses the separate product canonical numerical policy.
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n"
    ).encode()


def _decode(raw):
    value = json.loads(raw)
    if not isinstance(value, dict) or _encode(value) != raw:
        raise ValueError("noncanonical native custody document")
    return value


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hash(value):
    return _sha(_encode(value))


def _file_sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _hex(text):
    return type(text) is str and len(text) == 64 and all(x in "0123456789abcdef" for x in text)


def _write(path, raw):
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _publish(path, value):
    raw = _encode(value)
    _require(len(raw) <= _FILE_LIMIT, "native IPC exceeds byte limit")
    temporary = path.with_suffix(".unpublished")
    _write(temporary, raw)
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink()
    return _sha(raw)


def _bounded(path, limit=_FILE_LIMIT):
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    _require(len(raw) <= limit, "native file exceeds byte limit")
    return raw


def _signed_zero_canonical(value):
    if isinstance(value, dict):
        return {key: _signed_zero_canonical(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_signed_zero_canonical(item) for item in value]
    return 0.0 if type(value) is float and value == 0 else value


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if hasattr(value, "tolist"):
        return _plain(value.tolist())
    return value


def _profile_checks(authority):
    """Run only in the exact isolated package runtime before solver imports."""
    runtime = authority["runtime"]
    root = Path(runtime["profile"])
    checker = root / "check_lock.py"
    _require(_file_sha(checker) == runtime["checker_sha256"], "profile checker bytes differ")
    _require(_file_sha(sys.executable) == runtime["python_sha256"], "running Python executable differs")
    _require(
        Path(sys._base_executable).resolve() == Path(runtime["base_python"]).resolve()
        and _file_sha(sys._base_executable) == runtime["base_python_sha256"],
        "loaded base Python differs",
    )
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        name = ctypes.windll.kernel32.GetModuleFileNameW
        name.argtypes = (wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD)
        name.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        count = name(sys.dllhandle, buffer, len(buffer))
        _require(
            0 < count < len(buffer)
            and Path(buffer.value).resolve() == Path(runtime["python_dll"]).resolve()
            and _file_sha(buffer.value) == runtime["python_dll_sha256"],
            "loaded Python DLL differs",
        )
    # -S suppresses executable .pth startup. Add only the independently
    # pinned worker's exact package root for installed-byte verification.
    _require(
        sys.flags.isolated
        and sys.flags.no_site
        and sys.dont_write_bytecode
        and sys.pycache_prefix is not None
        and not Path(sys.pycache_prefix).exists(),
        "native isolated bootstrap policy differs",
    )
    prefix = Path(runtime["python"]).resolve().parents[1]
    packages = prefix / "Lib" / "site-packages"
    _require(
        packages.is_dir() and packages.resolve(strict=True).parts == packages.parts,
        "native isolated site-packages path differs",
    )
    sys.prefix = sys.exec_prefix = str(prefix)
    sys.path.append(str(packages))
    audit = runpy.run_path(str(checker))["check"](
        root, runtime["profile_sha256"], full=True, progress=lambda message: print(message, flush=True)
    )
    provenance = json.loads((root / "provenance.json").read_bytes())
    windows = "softqp-0.3.0-cp312-cp312-win_amd64.whl"
    _require(
        provenance["canonical_engine_source"] == runtime["engine_source"]
        and provenance["source_artifacts"]["checksums"][windows] == runtime["wheel_sha256"]
        and provenance["defaults_sha256"] == runtime["defaults_sha256"],
        "admitted SDK release/profile identity differs",
    )
    return audit


def _prepare(original):
    import numpy as np
    from scipy import sparse
    from softqp.learning.solvers import PreparedLearningProblem
    from softqp.peak import PeakGroup, PeakProblem
    from softqp.problem import Penalty, Problem

    def csc(value):
        return sparse.csc_matrix(
            (np.array(value["data"], dtype=np.float64), value["indices"], value["indptr"]),
            shape=value["shape"],
        )

    P, A = csc(original["P"]), csc(original["A"])
    q = np.array(original["q"], dtype=np.float64)
    lower = np.array([-np.inf if v is None else v for v in original["lower"]], dtype=np.float64)
    upper = np.array([np.inf if v is None else v for v in original["upper"]], dtype=np.float64)
    if original["formulation"] == "peak":
        groups = tuple(
            PeakGroup(
                np.array(g["rows"]),
                np.array(g["lower_scale"]),
                np.array(g["upper_scale"]),
                g["linear"],
                g["quadratic"],
            )
            for g in original["groups"]
        )
        problem = PeakProblem(P, q, A, lower, upper, groups)
    else:
        penalty = Penalty(
            **{
                k: np.array(v, dtype=bool if k == "soft" else np.float64)
                for k, v in original["penalty"].items()
            }
        )
        problem = Problem(P, q, A, lower, upper, penalty)
    units = original["units"]
    return PreparedLearningProblem(
        problem,
        variable_units=units["D_x"],
        row_units=units["D_r"],
        peak_units=units["D_t"],
        objective_unit=units["S_f"],
    )


def _lift_digest(P, A, q, lower, upper):
    matrix = lambda rows: [[float(value) or 0.0 for value in row] for row in rows]  # noqa: E731
    bounds = lambda values: [float(v) or 0.0 if v is not None and math.isfinite(v) else None for v in values]  # noqa: E731
    return _hash(
        {
            "P": matrix(P),
            "A": matrix(A),
            "q": [float(v) or 0.0 for v in q],
            "lower": bounds(lower),
            "upper": bounds(upper),
        }
    )


def _observed_lift(problem):
    # Read-only view into the independently pinned 0.3.0 preparation. It
    # captures the actual native interval beyond shape without factoring an
    # unrelated L2WS system before the oracle.
    P, q, A, lower, upper = problem._session.data[3]
    return _lift_digest(P.toarray(), A.toarray(), q, lower, upper)


def _actual_cold(problem, handle):
    from dataclasses import asdict
    from softqp.learning.solvers import cold_labels

    graph, result = cold_labels(problem, reference=handle)
    lift = problem.one_sided()
    telemetry = {name: _plain(result.pop(name)) for name in ("iterations", "setup_seconds", "solve_seconds")}
    return {
        "result": _plain(result),
        "sides": [asdict(row) for row in lift.row_map],
        "bounds": _plain(lift.b),
        "target": _plain(graph.labels.target),
        "mask": _plain(graph.labels.mask),
    }, telemetry


def _worker(root, expected_authority, nonce):
    path = root / "authority.json"
    deadline = time.monotonic() + 3
    while not path.is_file() and time.monotonic() < deadline:
        time.sleep(0.005)
    raw = _bounded(path)
    _require(_sha(raw) == expected_authority, "owned worker authority differs")
    authority = _decode(raw)
    _require(_file_sha(__file__) == authority["sources"][_WORKER_SOURCE[0]], "running worker code differs")
    _check_independent_review(authority)
    verification_started = time.monotonic()
    audit = _profile_checks(authority)
    staged_digest = _publish(
        root / "installed-files.json",
        {
            "nonce": nonce,
            "authority_sha256": expected_authority,
            "pid": os.getpid(),
            "audit": audit,
            "verify_seconds": time.monotonic() - verification_started,
        },
    )
    ack = root / "import-authorized.json"
    deadline = time.monotonic() + 10
    while not ack.is_file() and time.monotonic() < deadline:
        time.sleep(0.005)
    _require(
        _decode(_bounded(ack)) == {"nonce": nonce, "verified_sha256": staged_digest},
        "native import lacks verified supervisor ACK",
    )
    startup = time.monotonic()

    from importlib.metadata import version
    import clarabel
    import daqp
    import osqp
    import piqp
    import torch
    from softqp.learning import graph  # noqa: F401 - admit the full numerical import path
    from softqp.learning.solvers import backend_settings

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    _require(version("softqp") == "0.3.0", "actual SDK version differs")
    import_origins = {
        name: _file_sha(module.__file__)
        for name, module in (("stock-osqp", osqp), ("clarabel", clarabel), ("piqp", piqp), ("daqp", daqp))
    }
    import_versions = {
        "stock-osqp": osqp.__version__,
        "clarabel": clarabel.__version__,
        "piqp": version("piqp"),
        "daqp": version("daqp"),
    }
    _require(import_versions == {**_VERSIONS, "daqp": "0.10.3"}, "native backend versions differ")
    _publish(
        root / "hello.json",
        {
            "nonce": nonce,
            "authority_sha256": expected_authority,
            "pid": os.getpid(),
            "audit": audit,
            "verified_sha256": staged_digest,
            "versions": import_versions,
            "import_origins": import_origins,
            "cold_settings": _plain(backend_settings()["daqp-label"]),
            "import_seconds": time.monotonic() - startup,
        },
    )
    index = 0
    state = None
    while True:
        request_path = root / f"request-{index:06d}.json"
        if not request_path.is_file():
            time.sleep(0.005)
            continue
        raw = _bounded(request_path)
        request = _decode(raw)
        _require(request["nonce"] == nonce and request["index"] == index, "native worker sequence mismatch")
        stage = request["stage"]
        if stage == "stop":
            return
        started = time.monotonic()
        timing = {}
        try:
            if stage == "reference":
                problem = _prepare(request["original"])
                lift_digest = _observed_lift(problem)
                evidence = problem.reference()
                state = (index, request["frame_id"], problem, evidence)
                observed = {"lift_sha256": lift_digest, "reference": _plain(evidence.as_dict())}
            else:
                _require(
                    stage == "cold" and state is not None and state[:2] == (index - 1, request["frame_id"]),
                    "cold request lost its opaque reference custody",
                )
                observed, timing = _actual_cold(state[2], state[3])
                state = None
            status, reason = "observed", None
        except (ArithmeticError, ImportError, RuntimeError, ValueError) as error:
            observed, status, reason = None, "native-failure", f"{type(error).__name__}: {error}"
            state = None
        _publish(
            root / f"response-{index:06d}.json",
            {
                "index": index,
                "nonce": nonce,
                "request_sha256": _sha(raw),
                "frame_id": request["frame_id"],
                "stage": stage,
                "status": status,
                "reason": reason,
                "observed": observed,
                "telemetry": {"elapsed_seconds": time.monotonic() - started, **timing},
            },
        )
        index += 1


def _check_independent_review(document):
    if document["mode"] == "fixture":
        _require(
            document["registration"] is None and document["registration_file"] is None,
            "fixture authority cannot claim scientific registration",
        )
        return
    _require(document["mode"] == "scientific", "unknown native execution lane")
    reference = document["registration_file"]
    _require(
        isinstance(reference, dict)
        and set(reference) == {"path", "sha256"}
        and _hex(reference["sha256"])
        and reference["sha256"] == document["registration"],
        "native execution lacks independent I1 registration",
    )
    actual = _bounded(Path(reference["path"]))
    _require(_sha(actual) == reference["sha256"], "independent I1 registration bytes differ")
    receipt = _decode(actual)
    subject = receipt["subject"]
    _require(
        receipt.get("schema") == "softqp.r4.registration/1"
        and "native-label" in subject["operations"]
        and subject.get("design_manifest_sha256") == document["identities"]["design_manifest_sha256"]
        and subject.get("source_lock_sha256") == document["identities"]["source_lock_sha256"],
        "native authority registration lacks exact I1 disposition",
    )


@dataclass(frozen=True)
class NativeAuthority:
    raw: bytes
    sha256: str
    i1_authority: object | None = None

    @classmethod
    def load(cls, path, *, expected_sha256, i1_authority=None):
        from . import phase_inputs as p

        path = Path(path)
        raw = p._open_bytes(p._exact_directory(path.parent), path.name)
        _require(
            _hex(expected_sha256) and _sha(raw) == expected_sha256,
            "independent native authority digest differs",
        )
        authority = cls(raw, expected_sha256, i1_authority)
        authority.verify()
        return authority

    @property
    def document(self):
        return _decode(self.raw)

    def verify(self):
        _require(_hex(self.sha256) and _sha(self.raw) == self.sha256, "native authority digest differs")
        doc = self.document
        expected_keys = {
            "format",
            "mode",
            "registration",
            "registration_file",
            "identities",
            "preflight_sha256",
            "population_sha256",
            "roles",
            "inventory_sha256",
            "runtime",
            "sources",
            "settings_hashes",
        }
        _require(set(doc) == expected_keys and doc["format"] == AUTHORITY, "native authority format")
        _require(
            all(_hex(doc[name]) for name in ("preflight_sha256", "population_sha256", "inventory_sha256")),
            "native authority scope digest",
        )
        _check_independent_review(doc)
        runtime = doc["runtime"]
        _require(
            set(runtime)
            == {
                "python",
                "python_sha256",
                "base_python",
                "base_python_sha256",
                "python_dll",
                "python_dll_sha256",
                "profile",
                "profile_sha256",
                "checker_sha256",
                "defaults_sha256",
                "wheel",
                "wheel_sha256",
                "engine_source",
            },
            "native runtime authority fields",
        )
        for path_key, hash_key in (
            ("python", "python_sha256"),
            ("base_python", "base_python_sha256"),
            ("python_dll", "python_dll_sha256"),
            ("wheel", "wheel_sha256"),
        ):
            path = Path(runtime[path_key])
            _require(
                path.is_absolute() and _file_sha(path) == runtime[hash_key],
                f"native runtime {path_key} identity differs",
            )
        profile = Path(runtime["profile"])
        _require(profile.is_absolute(), "native profile root must be absolute")
        for name, fingerprint in (
            ("provenance.json", "profile_sha256"),
            ("check_lock.py", "checker_sha256"),
            ("defaults.json", "defaults_sha256"),
        ):
            _require(
                _file_sha(profile / name) == runtime[fingerprint],
                "native admitted profile or checker differs",
            )
        pipeline = Path(__file__).resolve().parents[1]
        names = _WORKER_SOURCE + (("learned_comparison/authority.py",) if doc["mode"] == "scientific" else ())
        _require(set(doc["sources"]) == set(names), "native local source binding inventory differs")
        for name in names:
            _require(
                _file_sha(pipeline / name) == doc["sources"][name], "native product source differs: " + name
            )
        _require(
            doc["settings_hashes"] == settings_identities(runtime), "native policy settings digest inventory"
        )


@dataclass(frozen=True)
class NativeSlot:
    frame_id: str
    role: str
    cold_eligible: bool
    frame_sha256: str


def _roles(roles):
    chosen = tuple(roles)
    _require(
        bool(chosen) and chosen == tuple(role for role in _ROLE_ORDER if role in chosen),
        "native role selection must be nonempty, ordered and cannot include test",
    )
    return chosen


def planned_slots(preflight, roles):
    """Return the exact role projection of input-only, verified v2 preflight metadata."""
    roles = _roles(roles)
    receipt = _decode(preflight.receipt_bytes)
    _require(receipt.get("format") == "softqp.stream-preflight/v2", "native run requires v2 input preflight")
    _require(
        all(row["state"] == "missing" and row["ref"] is None for row in receipt["labels"]),
        "native input preflight P0 must be unpopulated",
    )
    eligible = {row["frame_id"] for row in receipt["logical"] if row["representation"] == "graph-v1"}
    slots = tuple(
        NativeSlot(
            row["ref"]["artifact_id"],
            row["role"],
            row["ref"]["artifact_id"] in eligible,
            row["ref"]["sha256"],
        )
        for row in receipt["records"]
        if row["ref"]["kind"] == "learning-stream-frame" and row["role"] in roles
    )
    ids = [slot.frame_id for slot in slots]
    _require(
        ids == sorted(set(ids)) and ids and {slot.role for slot in slots} == set(roles),
        "native exact frame inventory absent or unordered",
    )
    return slots


def _slots_data(slots):
    return [
        {
            "frame_id": s.frame_id,
            "role": s.role,
            "cold_eligible": s.cold_eligible,
            "frame_sha256": s.frame_sha256,
        }
        for s in slots
    ]


@dataclass(frozen=True)
class NativePlan:
    context: AdmissionContext
    preflight: PhasePreflight
    authority_sha256: str
    slots: tuple[NativeSlot, ...]
    roles: tuple[str, ...]

    @classmethod
    def from_preflight(cls, context, preflight, *, expected_preflight_sha256, roles, authority):
        authority.verify()
        _require(
            _hex(expected_preflight_sha256) and preflight.sha256 == expected_preflight_sha256,
            "native independently expected input preflight differs",
        )
        document = authority.document
        receipt = _decode(preflight.receipt_bytes)
        chosen = _roles(roles)
        _require(
            document["preflight_sha256"] == expected_preflight_sha256
            and document["population_sha256"] == receipt["population_sha256"]
            and document["roles"] == list(chosen)
            and document["identities"] == receipt["identities"],
            "native independent scope authority differs",
        )
        fixture = document["mode"] == "fixture"
        _require(fixture == context.allow_fixture == receipt["fixture_only"], "native fixture lane differs")
        _require(
            fixture or document["registration"] == context.registration_sha256,
            "native independently reviewed I1 registration differs",
        )
        if not fixture:
            from .authority import require_i1

            require_i1(
                authority.i1_authority, "native-label", context=context, protocol_ref=receipt["protocol_ref"]
            )
        _require(
            str(context.root.resolve()) == str(preflight.source_root) == receipt["source_root"]
            and receipt["forbidden_roots"] == [str(path) for path in preflight.forbidden_roots],
            "native preflight path custody differs",
        )
        for key in (
            "protocol_id",
            "protocol_sha256",
            "source_lock_sha256",
            "registration_sha256",
            "producer_source_sha256",
            "generator_sha256",
            "dependency_lock_sha256",
        ):
            _require(
                receipt["identities"][key] == getattr(context, key), "native context source identity differs"
            )
        _require(
            all(
                context.settings_hashes.get(key) == value
                for key, value in document["settings_hashes"].items()
            ),
            "native context settings differ",
        )
        slots = planned_slots(preflight, chosen)
        _require(
            _hash(_slots_data(slots)) == document["inventory_sha256"],
            "native independent exact inventory differs",
        )
        return cls(context, preflight, authority.sha256, slots, chosen)


def _recheck_plan(plan, authority):
    verified = NativePlan.from_preflight(
        plan.context,
        plan.preflight,
        expected_preflight_sha256=plan.preflight.sha256,
        roles=plan.roles,
        authority=authority,
    )
    _require(
        plan.slots == verified.slots and plan.authority_sha256 == authority.sha256, "native plan was rebound"
    )


def _native_environment(root, executable):
    keys = ("SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE")
    env = {key: os.environ[key] for key in keys if key in os.environ}
    system = Path(env.get("SystemRoot", "/usr")) / ("System32" if os.name == "nt" else "bin")
    env.update(
        {
            "PATH": os.pathsep.join((str(executable.parent), str(system))),
            "TMP": str(root),
            "TEMP": str(root),
            "TMPDIR": str(root),
            "USERPROFILE": str(root),
            "HOME": str(root),
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            "VECLIB_MAXIMUM_THREADS": "1",
        }
    )
    return env


class _WorkerExited(ValueError):
    """The actual owned process exited before a required observation."""


class _OwnedWorker:
    def __init__(self, root, command, executable, *, nonce):
        from ..lesson_process import WindowsJob

        self.root = root
        self.nonce = nonce
        self.index = 0
        self.peak_rss = 0
        self.job = None
        self.process = None
        root.mkdir()
        try:
            self.job = WindowsJob() if os.name == "nt" else None
            with (root / "stdout.log").open("xb") as stdout, (root / "stderr.log").open("xb") as stderr:
                self.process = subprocess.Popen(
                    command,
                    cwd=root,
                    env=_native_environment(root, executable),
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    creationflags=4 if os.name == "nt" else 0,
                    start_new_session=os.name != "nt",
                )
                if self.job is not None:
                    self.job.attach_and_resume(self.process)
        except BaseException:
            self.close()
            raise

    def _pids(self):
        if self.job is None:
            return (self.process.pid,) if self.process.poll() is None else ()
        import ctypes
        from ctypes import wintypes

        class ProcessIds(ctypes.Structure):
            _fields_ = [
                ("assigned", wintypes.DWORD),
                ("count", wintypes.DWORD),
                ("ids", ctypes.c_size_t * 32),
            ]

        members = ProcessIds()
        if not self.job.api.QueryInformationJobObject(
            self.job.handle, 3, ctypes.byref(members), ctypes.sizeof(members), None
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        _require(members.count == members.assigned <= 32, "native owned process inventory incomplete")
        return tuple(members.ids[: members.count])

    def _monitor(self):
        from ..coupled_resources import process_memory

        for name in ("stdout.log", "stderr.log"):
            _require((self.root / name).stat().st_size <= _DIAGNOSTIC_LIMIT, "native worker diagnostic limit")
        total = 0
        for pid in self._pids():
            try:
                _, peak = process_memory(pid)
            except OSError:
                if pid not in self._pids():
                    continue
                raise
            total += peak
        self.peak_rss = max(self.peak_rss, total)
        _require(self.peak_rss <= _PEAK_LIMIT, "native worker RSS limit")

    def wait_file(self, path, seconds):
        deadline = time.monotonic() + seconds
        while True:
            self._monitor()
            if time.monotonic() >= deadline:
                raise TimeoutError(f"native worker deadline for {path.name}")
            if path.is_file():
                return _decode(_bounded(path))
            code = self.process.poll()
            if code is not None:
                raise _WorkerExited(f"native worker exited before {path.name}: {code}")
            time.sleep(0.01)

    def exchange(self, frame_id, stage, original=None):
        index = self.index
        request = {
            "index": index,
            "nonce": self.nonce,
            "frame_id": frame_id,
            "stage": stage,
            "original": original,
        }
        request_sha = _publish(self.root / f"request-{index:06d}.json", request)
        record = self.wait_file(self.root / f"response-{index:06d}.json", _TRIAL_SECONDS)
        _require(
            all(record[key] == request[key] for key in ("index", "nonce", "frame_id", "stage"))
            and record["request_sha256"] == request_sha,
            "native observed output custody mismatch",
        )
        self.index += 1
        (self.root / f"request-{index:06d}.json").unlink()
        (self.root / f"response-{index:06d}.json").unlink()
        return record

    def finish(self):
        _publish(
            self.root / f"request-{self.index:06d}.json",
            {"index": self.index, "nonce": self.nonce, "frame_id": None, "stage": "stop", "original": None},
        )
        try:
            _require(self.process.wait(timeout=3) == 0, "native observed child exited unsuccessfully")
        finally:
            self.close()

    def close(self):
        from ..lesson_process import WorkerCleanupError

        deadline = time.monotonic() + 3
        failure = None
        if self.job is not None:
            try:
                self.job.close(deadline=deadline)
            except Exception as error:
                failure = error
            self.job = None
        process = self.process
        self.process = None
        if process is not None:
            try:
                if os.name != "nt":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=max(0, deadline - time.monotonic()))
            except Exception as error:
                failure = failure or error
        if failure is not None:
            raise WorkerCleanupError(f"Native job teardown uncertain: {self.root}") from failure


def settings_identities(runtime):
    """Bind each exact exposed policy to the independently checked wheel/defaults."""
    policy = {
        "profile_sha256": runtime["profile_sha256"],
        "defaults_sha256": runtime["defaults_sha256"],
        "wheel_sha256": runtime["wheel_sha256"],
        "engine_source": runtime["engine_source"],
    }
    return {
        key: _hash({"format": "softqp.native-settings/v1", "policy": key, **policy})
        for key in ("oracle:stock_osqp", "oracle:clarabel", "oracle:piqp", "label:cold_daqp")
    }


def _problem_input(plan, slot, receipt, records):
    from . import stream_inputs as stream

    frame_entry = records[slot.frame_id]
    frame_ref = frame_entry["ref"]
    _require(
        frame_ref["sha256"] == slot.frame_sha256 and frame_entry["role"] == slot.role,
        "native frame custody changed",
    )
    frame = stream._load(plan.context, frame_ref, stream.FRAME, receipt["protocol_ref"])
    source_ref = frame["payload"]["source_ref"]
    _require(
        records.get(source_ref["artifact_id"]) == {"ref": source_ref, "role": slot.role},
        "native frame source/role custody changed",
    )
    source = stream._load(plan.context, source_ref, stream.SOURCE, receipt["protocol_ref"])
    stream._source(source["payload"], plan.context)
    problem = stream._problem(plan.context, frame, source)
    metadata = problem["source"]
    _require(metadata["split"] == slot.role, "native frame role changed")
    if plan.context.allow_fixture:
        _require(
            frame["purpose"] == source["purpose"] == "contract-fixture"
            and problem["expected_control"] is not None
            and metadata["state_origin"] == "contract-fixture",
            "native fixture requires an explicitly excluded diagnostic",
        )
    else:
        _require(
            frame["purpose"] == source["purpose"] == "scientific" and problem["expected_control"] is None,
            "native production cannot use excluded controls",
        )
    identity = {
        "frame": frame_ref,
        "source": source_ref,
        "role": slot.role,
        "source_id": metadata["source_id"],
        "parent_id": metadata["parent_id"],
        "family": metadata["family"],
        "regime": metadata["regime"],
        "unit_index": metadata["unit_index"],
        "frame_index": metadata["frame"],
        "frame_count": metadata["frame_count"],
        "cold_eligible": slot.cold_eligible,
        "original_sha256": problem["original_sha256"],
        "transform_sha256": problem["transform_sha256"],
        "units_sha256": _hash(problem["original"]["units"]),
    }
    return problem, identity


def _result_sha(attempt):
    def result(stage):
        if stage is None:
            return None
        return {key: stage[key] for key in ("stage", "status", "reason", "observed")}

    return _hash(
        {
            "format": "softqp.native-numerical-result/v1",
            "input": attempt["input"],
            "state": attempt["state"],
            "reason": attempt["reason"],
            "reference": result(attempt["reference"]),
            "cold": result(attempt["cold"]),
        }
    )


def _failure(stage, status, reason, diagnostic):
    return {
        "stage": stage,
        "status": status,
        "reason": reason,
        "observed": None,
        "telemetry": {"diagnostic": diagnostic},
    }


def _product_reference(reference, problem, context):
    from . import contracts as c

    actual = reference["references"]
    _require(set(actual) == set(_BACKENDS), "native observed oracle inventory differs")
    _require(reference["status"] in ("oracle-agreed", "oracle-failed"), "native oracle status unknown")
    lengths = [actual[k].get("x") is not None and actual[k].get("y") is not None for k in _BACKENDS]
    candidates = [
        {"x": actual[k]["x"], "y": actual[k]["y"], "lifted_x": None, "lifted_y": None, "epigraph": None}
        if available
        else None
        for k, available in zip(_BACKENDS, lengths)
    ]
    candidates = [_signed_zero_canonical(candidate) for candidate in candidates]
    f_ref = 0
    if reference["status"] == "oracle-agreed":
        _require(all(candidate is not None for candidate in candidates), "agreed native oracle lacks vectors")
        # The attempt retains SDK metrics. Product rows use the product's canonical arithmetic.
        objectives = [
            c.original_metrics(problem["original"], candidate, 0)["objective"] for candidate in candidates
        ]
        f_ref = sorted(objectives)[1]
    rows = []
    for key, candidate in zip(_BACKENDS, candidates):
        original = actual[key]
        backend = key.replace("-", "_")
        native_status = original.get("native_status")
        okay = original["passed"] is True
        if okay:
            _require(
                candidate is not None
                and original["backend_version"] == _VERSIONS[key]
                and native_status == _FLAGS[key],
                "native claimed oracle success lacks observed candidate",
            )
        product_success_flags = {"stock-osqp": 1, "clarabel": "Solved", "piqp": "PIQP_SOLVED"}
        native = product_success_flags[key] if okay else native_status
        row = {
            "backend": backend,
            "settings_sha256": context.settings_hashes["oracle:" + backend],
            "accepted": okay,
            "status": "accepted" if okay else ("accuracy-rejected" if candidate else "failed"),
            "reason": None
            if okay
            else (original.get("reason") or "Observed reference: " + str(native_status)),
            "candidate": candidate,
            "metrics": c.original_metrics(problem["original"], candidate, f_ref) if candidate else None,
            "native_flag": native,
        }
        row = _signed_zero_canonical(row)
        row["result_sha256"] = c.digest(c.canonical_bytes(row))
        rows.append(row)
    if reference["status"] == "oracle-agreed":
        _require(c._oracle(problem, rows, context) == f_ref, "canonical product oracle objective differs")
    elif not all(row["accepted"] for row in rows):
        c._failed_oracles(rows, context)
    return rows


def _candidate(cold, problem):
    result = cold["result"]
    candidate = {name: result[name] for name in ("x", "y", "lifted_x", "lifted_y")}
    candidate["epigraph"] = None
    if problem["transform"]["kind"] == "G":
        observed = result["metrics"]["epigraph"]
        groups = problem["original"]["groups"]
        size = problem["original"]["m"]
        summary = {
            "t": [0] * len(groups),
            "mu": [0] * len(groups),
            "lambda_lower": [0] * size,
            "lambda_upper": [0] * size,
        }
        for gid, value, mu in zip(observed["group_ids"], observed["peak"], observed["mu"], strict=True):
            summary["t"][gid], summary["mu"][gid] = value, mu
        for row, sign, value in zip(
            observed["side_rows"], observed["side_signs"], observed["lambda_sides"], strict=True
        ):
            summary["lambda_upper" if sign == 1 else "lambda_lower"][row] = value
        candidate["epigraph"] = summary
    return _signed_zero_canonical(candidate)


def _label_data(cold, problem, context):
    from . import contracts as c

    transform = problem["transform"]
    graph, matrix, nodes = c.graph_coordinates(transform)
    side_order = graph["row_map"]
    candidate = _candidate(cold, problem)
    result = cold["result"]
    _require(result["status"] == "accepted" and result["native_flag"] in (1, 2), "unaccepted cold SDK result")
    raw = _signed_zero_canonical(result["raw_side_dual"])
    n, m = transform["n"], transform["m"]
    _require(
        cold["sides"] == side_order
        and cold["bounds"] == [row[1] for row in nodes[n:]]
        and len(side_order) == len(raw),
        "actual native signed side layout differs",
    )
    lifted = [0] * m
    slack, multipliers, target, mask, bound = [0] * n, [0] * n, [None] * n, [False] * n, [0] * n
    for side, row, features, multiplier in zip(side_order, matrix, nodes[n:], raw, strict=True):
        lifted[side["canonical_row"]] += side["sign"] * multiplier
        b = features[1]
        distance = b - c._dot(row, candidate["lifted_x"])
        tau = 1e-7 * max(1, abs(b))
        label = (
            1
            if abs(distance) <= tau and multiplier > 1e-7
            else (0 if distance > tau and abs(multiplier) <= 1e-7 else None)
        )
        if side["equality"]:
            label = None
        slack.append(distance)
        multipliers.append(multiplier)
        target.append(label)
        mask.append(label is not None)
        bound.append(b)
    _require(lifted == candidate["lifted_y"], "actual cold signed scatter differs")
    _require(
        mask == cold["mask"] and cold["target"] == [0 if value is None else value for value in target],
        "actual cold masks/labels differ from original typed evaluator",
    )
    evidence = {
        "producer_source_sha256": context.producer_source_sha256,
        "settings_sha256": context.settings_hashes["label:cold_daqp"],
        "input_sha256": problem["original_sha256"],
        "native_flag": result["native_flag"],
        "raw_primal": candidate["lifted_x"],
        "raw_side_duals": raw,
    }
    evidence["sha256"] = c.digest(c.canonical_bytes(evidence))
    return {
        "slack": slack,
        "multipliers": multipliers,
        "labels": target,
        "mask": mask,
        "bound": bound,
        "node_kind": graph["node_kind"],
        "cold_candidate": candidate,
        "cold_native_flag": result["native_flag"],
        "native_evidence": evidence,
    }


def _product_projection(reply, problem, context):
    from . import contracts as c

    observed = reply["observed"]
    t = problem["transform"]
    expected_lift = _lift_digest(c.dense(t["P"]), c.dense(t["A"]), t["q"], t["lower"], t["upper"])
    _require(
        observed["lift_sha256"] == expected_lift, "observed native lift differs from exact product transform"
    )
    observed_reference = observed["reference"]
    return observed_reference, _product_reference(observed_reference, problem, context)


def _disposition(attempt, problem, context, protocol_ref, population_sha256):
    from . import contracts as c
    from . import stream_inputs as stream

    identity = attempt["input"]
    ref_reply, cold_reply = attempt["reference"], attempt["cold"]
    if ref_reply["status"] != "observed":
        return ("oracle-" + ref_reply["status"], ref_reply["reason"], None)
    try:
        observed_reference, rows = _product_projection(ref_reply, problem, context)
    except (ArithmeticError, ValueError) as error:
        return "reference-product-rejected", str(error), None
    if not identity["cold_eligible"]:
        state = "reference-only" if observed_reference["status"] == "oracle-agreed" else "oracle-failed"
        return state, None if state == "reference-only" else "Observed three-reference failure", None
    payload = {
        "frame": identity["frame"],
        "population_sha256": population_sha256,
        "oracle_results": rows,
        "oracle_source_sha256": context.producer_source_sha256,
        "settings_sha256": context.settings_hashes["label:cold_daqp"],
        "tau_dual": 1e-7,
        "tau_tight": 1e-7,
        "fit_access": [],
    }
    if observed_reference["status"] == "oracle-failed":
        if all(row["accepted"] for row in rows):
            return "oracle-disagreement", "Observed three-reference objective disagreement", None
        reason = "Observed native three-reference failure"
        payload.update(
            status="oracle-failed",
            reason=reason,
            slack=[],
            multipliers=[],
            labels=[],
            mask=[],
            node_kind=[],
            bound=[],
            cold_candidate=None,
            cold_native_flag=None,
            native_evidence=None,
        )
        c._label_values(payload, problem, context.fit_source_ids, context)
        state = "oracle-failed"
    else:
        _require(cold_reply is not None, "eligible agreed native input has no cold disposition")
        if cold_reply["status"] != "observed":
            return "cold-" + cold_reply["status"], cold_reply["reason"], None
        try:
            payload.update(
                status="accepted", reason=None, **_label_data(cold_reply["observed"], problem, context)
            )
            payload = _signed_zero_canonical(payload)
            c._label_values(
                payload,
                problem,
                context.fit_source_ids,
                context,
                raw_side_duals=payload["native_evidence"]["raw_side_duals"],
            )
        except (ArithmeticError, ValueError) as error:
            return "cold-product-rejected", str(error), None
        state, reason = "accepted", None
    artifact_id = "native-label-" + _hash(identity["frame"]["artifact_id"])[:24]
    document = stream.stream_document(stream.LABELS, artifact_id, payload, context, protocol_ref)
    stream._document(document, context, protocol_ref)
    return state, reason, c.canonical_bytes(document)


def _validate_custody(document):
    from . import contracts as c

    schema = c.SCHEMAS / "softqp-learning-native-run.schema.json"
    c._validator(schema.read_bytes()).validate(document)


def _scope(manifest):
    return _hash(
        {
            key: manifest[key]
            for key in (
                "authority_sha256",
                "preflight_sha256",
                "population_sha256",
                "roles",
                "inventory_sha256",
                "rows",
            )
        }
    )


def _persist(path, payload, *, limit=_FILE_LIMIT):
    raw = _encode(payload)
    _require(len(raw) <= limit, "native custody document too large")
    temporary = path.with_suffix(".unpublished")
    _write(temporary, raw)
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink()
    return {"path": path.name, "sha256": _sha(raw)}


def _restore_custody(root, ref, *, limit=_FILE_LIMIT):
    from . import phase_inputs as p

    _require(
        type(ref) is dict and set(ref) == {"path", "sha256"} and _hex(ref["sha256"]),
        "native custody reference malformed",
    )
    _require(len(p._path_parts(ref["path"])) == 1, "native custody local path required")
    path = p._exact_directory(root) / ref["path"]
    # Check exact local spelling, reparse and link count before bounded I/O.
    facts = p._path_stat(path)
    _require(
        stat.S_ISREG(facts.st_mode) and facts.st_nlink == 1 and path.resolve(strict=True).parts == path.parts,
        "native custody path alias",
    )
    raw = _bounded(path, limit)
    _require(_sha(raw) == ref["sha256"], "native custody stored byte digest differs")
    return raw


def _start_worker(run_root, authority, index):
    doc = authority.document
    nonce = secrets.token_hex(16)
    executable = Path(doc["runtime"]["python"])
    owned_root = run_root / f"worker-{index:04d}"
    command = [
        str(executable),
        "-I",
        "-S",
        "-B",
        "-X",
        "pycache_prefix=" + str(owned_root / "unused-bytecode"),
        str(Path(__file__).resolve()),
        "--worker",
        str(owned_root),
        authority.sha256,
        nonce,
    ]
    worker = _OwnedWorker(owned_root, command, executable, nonce=nonce)
    try:
        # Child waits for the externally verified bytes staged by the parent.
        _persist(worker.root / "authority.json", authority.document)
        verified = worker.wait_file(worker.root / "installed-files.json", _VERIFY_SECONDS)
        _require(
            verified["nonce"] == nonce
            and verified["authority_sha256"] == authority.sha256
            and verified["pid"] in worker._pids()
            and verified["audit"]["full_files"] is True
            and verified["audit"]["full_source_files_checked"] > 0,
            "owned SDK installed file custody mismatch",
        )
        verified_sha256 = _hash(verified)
        _persist(worker.root / "import-authorized.json", {"nonce": nonce, "verified_sha256": verified_sha256})
        hello = worker.wait_file(worker.root / "hello.json", _IMPORT_SECONDS)
        _require(
            hello["authority_sha256"] == authority.sha256
            and hello["nonce"] == nonce
            and hello["pid"] == verified["pid"]
            and hello["pid"] in worker._pids()
            and hello["verified_sha256"] == verified_sha256
            and hello["audit"] == verified["audit"]
            and hello["audit"]["full_files"] is True
            and hello["audit"]["full_source_files_checked"] > 0,
            "owned SDK runtime hello mismatch",
        )
        hello["verified_files"] = verified
        telemetry = _persist(run_root / f"worker-{index:04d}-hello.json", hello)
        return worker, telemetry
    except BaseException:
        worker.close()
        raise


def _run_input(worker, problem, identity, context):
    reference = cold = None
    timeout_stage = None
    try:
        reference = worker.exchange(identity["frame"]["artifact_id"], "reference", problem["original"])
        if (
            identity["cold_eligible"]
            and reference["status"] == "observed"
            and reference["observed"]["reference"]["status"] == "oracle-agreed"
        ):
            try:
                _product_projection(reference, problem, context)
            except (ArithmeticError, ValueError):
                return reference, None, None
            cold = worker.exchange(identity["frame"]["artifact_id"], "cold")
    except (TimeoutError, _WorkerExited) as error:
        timeout_stage = "reference" if reference is None else "cold"
        timed_out = isinstance(error, TimeoutError)
        failed = _failure(
            timeout_stage,
            "timeout" if timed_out else "worker-exit",
            "Supervised numerical deadline exceeded"
            if timed_out
            else "Owned worker exited before observing a result",
            str(error),
        )
        if reference is None:
            reference = failed
        else:
            cold = failed
        worker.close()  # failure here prevents another launch and no run can be sealed
    return reference, cold, timeout_stage


def supervise_native_run(plan, authority, destination):
    """Produce immutable attempts/labels only from an exact owned SDK child."""
    from . import phase_inputs as p

    _recheck_plan(plan, authority)
    receipt = _decode(plan.preflight.receipt_bytes)
    records = {row["ref"]["artifact_id"]: row for row in receipt["records"]}
    target = p._external_destination(
        Path(destination), plan.preflight.source_root, plan.preflight.forbidden_roots
    )
    if authority.document["mode"] == "scientific":
        import shutil

        _require(
            shutil.disk_usage(target.parent).free >= 20 * 2**30, "scientific native external disk minimum"
        )
    target.mkdir()
    rows, workers = [], []
    worker = None
    stored_bytes = 0
    completed_work_bytes = 0
    try:
        for index, slot in enumerate(plan.slots):
            problem, identity = _problem_input(plan, slot, receipt, records)
            if worker is None:
                worker_index = len(workers)
                worker, hello = _start_worker(target, authority, worker_index)
                workers.append(hello)
                stored_bytes += (target / hello["path"]).stat().st_size
            reference, cold, timed_out = _run_input(worker, problem, identity, plan.context)
            attempt = {
                "format": ATTEMPT,
                "version": VERSION,
                "authority_sha256": authority.sha256,
                "preflight_sha256": plan.preflight.sha256,
                "input": identity,
                "worker": worker_index,
                "reference": reference,
                "cold": cold,
                "peak_rss_bytes": worker.peak_rss,
            }
            current_work_bytes = sum(path.stat().st_size for path in worker.root.iterdir() if path.is_file())
            if timed_out is not None:
                completed_work_bytes += current_work_bytes
                current_work_bytes = 0
                worker = None
            try:
                state, reason, raw_label = _disposition(
                    attempt, problem, plan.context, receipt["protocol_ref"], receipt["population_sha256"]
                )
            except BaseException:
                _persist(target / f"rejected-attempt-{index:06d}.json", attempt)
                raise
            attempt.update(state=state, reason=reason)
            attempt["result_sha256"] = _result_sha(attempt)
            _validate_custody(attempt)
            attempt_ref = _persist(target / f"attempt-{index:06d}.json", attempt)
            label_ref = None
            if raw_label is not None:
                path = target / f"native-label-{index:06d}.json"
                _write(path, raw_label)
                label_ref = {"path": path.name, "sha256": _sha(raw_label)}
            stored_bytes += len(_encode(attempt)) + (len(raw_label) if raw_label else 0)
            _require(
                stored_bytes + completed_work_bytes + current_work_bytes
                <= _DISK_LIMIT - _MANIFEST_LIMIT - _DIAGNOSTIC_LIMIT * 2,
                "native stored run exceeds its disk budget",
            )
            rows.append(
                {
                    "input": identity,
                    "state": state,
                    "reason": reason,
                    "result_sha256": attempt["result_sha256"],
                    "attempt": attempt_ref,
                    "label": label_ref,
                }
            )
        if worker is not None:
            worker.finish()
            worker = None
        manifest = {
            "format": MANIFEST,
            "version": VERSION,
            "authority_sha256": authority.sha256,
            "preflight_sha256": plan.preflight.sha256,
            "population_sha256": receipt["population_sha256"],
            "fixture_only": plan.context.allow_fixture,
            "roles": list(plan.roles),
            "inventory_sha256": authority.document["inventory_sha256"],
            "rows": rows,
            "workers": workers,
        }
        manifest["scope_sha256"] = _scope(manifest)
        _validate_custody(manifest)
        staged = target / ".staged-run.json"
        final = target / "native-run.json"
        sealed = _persist(staged, manifest, limit=_MANIFEST_LIMIT)
        owned = None
        try:
            _read_run(target, staged.name, sealed["sha256"], authority, plan)
            owned = staged.lstat()
            os.link(staged, final)
            staged.unlink()
            return read_native_run(
                target, expected_manifest_sha256=sealed["sha256"], authority=authority, plan=plan
            )
        except BaseException:
            if owned is not None and final.exists() and os.path.samestat(owned, final.lstat()):
                final.unlink()
            raise
        finally:
            staged.unlink(missing_ok=True)
    finally:
        if worker is not None:
            worker.close()


@dataclass(frozen=True)
class NativeRun:
    root: Path
    raw: bytes
    sha256: str

    _rows: object = field(init=False, repr=False, compare=False)
    _population_sha256: str = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        doc = _decode(self.raw)
        _require(
            _sha(self.raw) == self.sha256 and doc["format"] == MANIFEST,
            "native run detached identity differs",
        )
        rows = {row["input"]["frame"]["artifact_id"]: _encode(row) for row in doc["rows"]}
        _require(len(rows) == len(doc["rows"]), "duplicate native run frame")
        object.__setattr__(self, "_rows", MappingProxyType(rows))
        object.__setattr__(self, "_population_sha256", doc["population_sha256"])

    @property
    def document(self):
        return _decode(self.raw)

    def require_label(
        self,
        document,
        frame_ref,
        problem,
        population_sha256,
        *,
        expected_manifest_sha256,
    ):
        """Seam for the strict v2 labeled descriptor consumer."""
        from . import contracts as c

        _require(
            self.sha256 == expected_manifest_sha256 and self._population_sha256 == population_sha256,
            "independent native label run identity differs",
        )
        stored = self._rows.get(frame_ref["artifact_id"])
        _require(stored is not None, "native label lacks supervised inclusion")
        row = _decode(stored)
        _require(row["label"] is not None, "native label lacks supervised inclusion")
        identity = row["input"]
        expected_state = "oracle-failed" if row["state"] == "oracle-failed" else "accepted"
        payload = document["payload"]
        _require(
            identity["frame"] == frame_ref
            and identity["role"] == problem["source"]["split"]
            and identity["original_sha256"] == problem["original_sha256"]
            and identity["transform_sha256"] == problem["transform_sha256"]
            and identity["units_sha256"] == _hash(problem["original"]["units"])
            and payload["status"] == expected_state
            and row["label"]["sha256"] == _sha(c.canonical_bytes(document)),
            "native exact labeled descriptor inclusion differs",
        )

    def project_role(self, role, destination):
        from . import phase_inputs as p

        _roles((role,))
        document = self.document
        _require(
            role in document["roles"] and _sha(self.raw) == self.sha256,
            "native role projection authority differs",
        )
        target = Path(destination)
        p._path_parts(target.name)
        parent = p._exact_directory(target.parent)
        _require(
            not any((base / ".git").exists() for base in (parent, *parent.parents)),
            "native role projection cannot write inside a checkout",
        )
        projection = {
            "format": ROLE,
            "version": VERSION,
            "role": role,
            "manifest_sha256": self.sha256,
            "preflight_sha256": document["preflight_sha256"],
            "population_sha256": document["population_sha256"],
            "fixture_only": document["fixture_only"],
            "scope_sha256": document["scope_sha256"],
            "rows": [row for row in document["rows"] if row["input"]["role"] == role],
        }
        _validate_custody(projection)
        return _persist(target, projection, limit=_MANIFEST_LIMIT)["sha256"]


def _expected_outcome(reference, cold, identity):
    if reference["status"] != "observed" or reference["observed"]["reference"]["status"] != "oracle-agreed":
        _require(cold is None, "cold output exists without agreed opaque reference")
    if not identity["cold_eligible"]:
        _require(cold is None, "cold output exists for ineligible input")


def read_native_run(root, *, expected_manifest_sha256, authority, plan):
    """Fresh whole-run verification under independently supplied trust."""
    return _read_run(root, "native-run.json", expected_manifest_sha256, authority, plan)


def _read_run(root, filename, expected_manifest_sha256, authority, plan):
    from . import phase_inputs as p

    _require(_hex(expected_manifest_sha256), "independent expected native manifest digest required")
    root = p._exact_directory(Path(root))
    raw = _restore_custody(
        root, {"path": filename, "sha256": expected_manifest_sha256}, limit=_MANIFEST_LIMIT
    )
    manifest = _decode(raw)
    _validate_custody(manifest)
    _recheck_plan(plan, authority)
    expected = authority.document
    receipt = _decode(plan.preflight.receipt_bytes)
    records = {row["ref"]["artifact_id"]: row for row in receipt["records"]}
    _require(
        manifest["format"] == MANIFEST
        and manifest["authority_sha256"] == authority.sha256
        and manifest["preflight_sha256"] == plan.preflight.sha256
        and manifest["population_sha256"] == receipt["population_sha256"]
        and manifest["inventory_sha256"] == expected["inventory_sha256"]
        and manifest["roles"] == list(plan.roles)
        and manifest["fixture_only"] == plan.context.allow_fixture
        and manifest["scope_sha256"] == _scope(manifest),
        "native trusted manifest ancestry differs",
    )
    _require(len(manifest["rows"]) == len(plan.slots), "native run exact inventory mismatch")
    worker_records = []
    for index, ref in enumerate(manifest["workers"]):
        _require(ref["path"] == f"worker-{index:04d}-hello.json", "native worker generation order differs")
        hello = _decode(_restore_custody(root, ref))
        _require(
            hello["authority_sha256"] == authority.sha256 and hello["audit"]["full_files"] is True,
            "native worker fresh admission differs",
        )
        worker_records.append(hello)
    for index, (row, slot) in enumerate(zip(manifest["rows"], plan.slots, strict=True)):
        problem, identity = _problem_input(plan, slot, receipt, records)
        _require(
            row["input"] == identity and row["attempt"]["path"] == f"attempt-{index:06d}.json",
            "native run frame, source or result order differs",
        )
        attempt = _decode(_restore_custody(root, row["attempt"]))
        _validate_custody(attempt)
        _require(
            attempt["format"] == ATTEMPT
            and attempt["authority_sha256"] == authority.sha256
            and attempt["preflight_sha256"] == plan.preflight.sha256
            and attempt["input"] == identity
            and 0 <= attempt["worker"] < len(worker_records)
            and attempt["result_sha256"] == row["result_sha256"] == _result_sha(attempt),
            "native observed attempt binding differs",
        )
        hello = worker_records[attempt["worker"]]
        for name in ("reference", "cold"):
            stage = attempt[name]
            if stage is not None and stage["status"] not in _TRANSPORT_FAILURES:
                expected_request = {
                    "index": stage["index"],
                    "nonce": hello["nonce"],
                    "frame_id": slot.frame_id,
                    "stage": name,
                    "original": problem["original"] if name == "reference" else None,
                }
                _require(
                    stage["nonce"] == hello["nonce"]
                    and stage["frame_id"] == slot.frame_id
                    and stage["stage"] == name
                    and stage["request_sha256"] == _hash(expected_request),
                    "native observed worker/slot/request replay differs",
                )
        _expected_outcome(attempt["reference"], attempt["cold"], identity)
        state, reason, label = _disposition(
            attempt, problem, plan.context, receipt["protocol_ref"], receipt["population_sha256"]
        )
        _require(
            (state, reason) == (row["state"], row["reason"]) == (attempt["state"], attempt["reason"]),
            "native failure/acceptance status suppressed",
        )
        if label is None:
            _require(row["label"] is None, "fabricated native label bytes")
        else:
            _require(
                row["label"] is not None
                and row["label"]["path"] == f"native-label-{index:06d}.json"
                and _restore_custody(root, row["label"]) == label,
                "native label bytes differ from independently supervised output",
            )
    return NativeRun(root, raw, expected_manifest_sha256)


def _label_disposition(row):
    if row["label"] is not None:
        return "oracle-failed" if row["state"] == "oracle-failed" else "available", row["reason"]
    return "missing", row["reason"]


def _compare_label_slot(row, slot, *, fixture):
    if not row["input"]["cold_eligible"]:
        _require(slot is None, "native ineligible frame acquired label")
        return
    _require(slot is not None, "native expected eligible label slot omitted")
    state, reason = _label_disposition(row)
    if fixture and state == "available":
        state = "provider"
    _require(
        (slot["state"], slot["reason"]) == (state, reason), "native label disposition differs from supervisor"
    )
    ref = slot["ref"]
    if row["label"] is None:
        _require(ref is None, "native absent slot acquired fabricated bytes")
    else:
        _require(
            ref is not None and ref["sha256"] == row["label"]["sha256"],
            "native actual label byte binding differs",
        )


@dataclass(frozen=True)
class NativeRoleTrust:
    role: str
    manifest_sha256: str
    projection_sha256: str
    input_preflight_sha256: str
    labeled_preflight_sha256: str
    population_sha256: str
    scope_sha256: str
    inventory_sha256: str
    fixture_only: bool


def bind_labeled_preflight(
    plan,
    run,
    labeled_preflight,
    *,
    expected_manifest_sha256,
    expected_labeled_preflight_sha256,
    projection_hashes,
):
    """Link independently verified P0, manifest M and role projections to P1."""
    _require(
        _hex(expected_manifest_sha256) and expected_manifest_sha256 == _sha(run.raw) == run.sha256,
        "labeled preflight lacks independent native manifest trust",
    )
    _require(
        _hex(expected_labeled_preflight_sha256)
        and expected_labeled_preflight_sha256 == labeled_preflight.sha256,
        "independent labeled P1 preflight digest differs",
    )
    p0, p1 = _decode(plan.preflight.receipt_bytes), _decode(labeled_preflight.receipt_bytes)
    manifest = run.document
    _require(
        manifest["preflight_sha256"] == plan.preflight.sha256
        and manifest["scope_sha256"] == _scope(manifest),
        "labeled preflight native input anchor differs",
    )
    stable = {
        "format",
        "source_root",
        "forbidden_roots",
        "fixture_only",
        "protocol_ref",
        "identities",
        "population_sha256",
        "logical",
        "normalizers",
    }
    for key in stable:
        _require(p0[key] == p1[key], "P0/P1 nonlabel identity differs: " + key)
    refs = lambda p: [row for row in p["records"] if row["ref"]["kind"] != "learning-stream-labels"]  # noqa: E731
    _require(refs(p0) == refs(p1), "P0/P1 source and frame storage diverged")
    previous = {(row["frame_id"], row["role"]): row for row in p0["labels"]}
    upgraded = {(row["frame_id"], row["role"]): row for row in p1["labels"]}
    _require(
        len(previous) == len(p0["labels"])
        and len(upgraded) == len(p1["labels"])
        and previous.keys() == upgraded.keys(),
        "P0/P1 label topology differs",
    )
    records = {(row["input"]["frame"]["artifact_id"], row["input"]["role"]): row for row in manifest["rows"]}
    _require(
        len(records) == len(manifest["rows"]) and {key[1] for key in records} == set(plan.roles),
        "native labeled roles or exact inventory differs",
    )
    for key, row in records.items():
        _compare_label_slot(row, upgraded.get(key), fixture=p1["fixture_only"])
    for key in previous.keys() - records.keys():
        _require(previous[key] == upgraded[key], "P1 supplied label outside supervised roles")
    _require(
        set(projection_hashes) == set(plan.roles) and all(_hex(h) for h in projection_hashes.values()),
        "native independent role projection digest inventory",
    )
    return tuple(
        NativeRoleTrust(
            role,
            run.sha256,
            projection_hashes[role],
            plan.preflight.sha256,
            labeled_preflight.sha256,
            p1["population_sha256"],
            manifest["scope_sha256"],
            _hash([row["input"] for row in manifest["rows"] if row["input"]["role"] == role]),
            p1["fixture_only"],
        )
        for role in plan.roles
    )


@dataclass(frozen=True)
class NativeRoleProof:
    raw: bytes
    trust: NativeRoleTrust
    _rows: object = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        doc = _decode(self.raw)
        _require(_sha(self.raw) == self.trust.projection_sha256, "native role detached identity differs")
        rows = {row["input"]["frame"]["artifact_id"]: _encode(row) for row in doc["rows"]}
        _require(len(rows) == len(doc["rows"]), "native role projection duplicates a frame")
        object.__setattr__(self, "_rows", MappingProxyType(rows))

    @classmethod
    def load(cls, path, trust, *, allow_fixture=False):
        from . import phase_inputs as p

        _roles((trust.role,))
        _require(not trust.fixture_only or allow_fixture is True, "native role fixture admission refused")
        raw = _restore_custody(
            p._exact_directory(Path(path).parent),
            {"path": Path(path).name, "sha256": trust.projection_sha256},
            limit=_MANIFEST_LIMIT,
        )
        doc = _decode(raw)
        _validate_custody(doc)
        _require(
            doc["format"] == ROLE
            and doc["role"] == trust.role
            and doc["manifest_sha256"] == trust.manifest_sha256
            and doc["preflight_sha256"] == trust.input_preflight_sha256
            and doc["population_sha256"] == trust.population_sha256
            and doc["scope_sha256"] == trust.scope_sha256
            and doc["fixture_only"] == trust.fixture_only
            and _hash([row["input"] for row in doc["rows"]]) == trust.inventory_sha256,
            "native local role inclusion trust differs",
        )
        _require(
            all(row["input"]["role"] == trust.role for row in doc["rows"]),
            "native projection contains foreign role",
        )
        return cls(raw, trust)

    def verify(self, reader: StreamingPhaseReader, frame_id):
        """Verify locally held bytes and exact label disposition using sealed inclusion."""
        _require(
            reader.role == self.trust.role
            and reader.preflight_sha256 == self.trust.labeled_preflight_sha256
            and reader._population == self.trust.population_sha256
            and reader.fixture_only == self.trust.fixture_only,
            "native role proof and phase trust differ",
        )
        raw_row = self._rows.get(frame_id)
        _require(raw_row is not None, "native frame absent from trusted role inclusion")
        row = _decode(raw_row)
        identity = row["input"]
        frame = reader._records.get(frame_id)
        source = reader._records.get(identity["source"]["artifact_id"])
        _require(
            frame is not None
            and frame["ref"] == identity["frame"]
            and source is not None
            and source["ref"] == identity["source"],
            "native role physical identity changed",
        )
        problem = reader.read_problem(frame_id)
        _require(
            problem["original_sha256"] == identity["original_sha256"]
            and problem["transform_sha256"] == identity["transform_sha256"]
            and _hash(problem["original"]["units"]) == identity["units_sha256"],
            "native role input math binding differs",
        )
        label_slot = reader._labels.get(frame_id)
        _compare_label_slot(row, label_slot, fixture=self.trust.fixture_only)
        label = reader.read_label(frame_id) if label_slot is not None else None
        return {"state": row["state"], "reason": row["reason"], "label": label}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("authority_sha256")
    parser.add_argument("nonce")
    args = parser.parse_args()
    _worker(args.worker, args.authority_sha256, args.nonce)
