"""Actual SDK2 worked examples through a separate, read-only runtime boundary."""

import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import shutil
import tempfile

from jsonschema import Draft202012Validator

from .lesson_process import WorkerCleanupError, execute

ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "docs/teaching/coupled"
SCHEMA = ROOT / "docs/contracts/schemas/softqp-coupled-lesson.schema.json"
WORKER = Path(__file__).with_name("coupled_lesson_worker.py")
IDENTITIES = {
    "public-sdk-files.json": "e9851d644d0f25837a481cdd22c74345199f416b9b6f67d744cceeb2d04c0fd5",
    "requirements.txt": "2eff7832a1046fca5040163b98ac88e05c7318bf1f004c16c377206221c42ccc",
    "accepted-summary.json": "c82bf30bb53c7c10d464fc446bd2b99ee774b581dbe3f4dced86194e1fe54c6d",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def strict_json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def reject(token):
        raise ValueError(f"Nonfinite JSON extension: {token}")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def authorities():
    for name, expected in IDENTITIES.items():
        if sha(AUTHORITY / name) != expected:
            raise ValueError(f"Reviewed teaching authority differs: {name}")


def accepted_summary():
    """Inspect accepted bytes; does not repeat raw-trial inference or bootstrap."""
    authorities()
    return strict_json((AUTHORITY / "accepted-summary.json").read_bytes())


def runtime_identity(python):
    supplied = Path(python)
    if not supplied.is_absolute() or not supplied.is_file():
        raise ValueError("SOFTQP_COUPLED_PYTHON must be an absolute existing external executable")
    # Resolve directory aliases, preserving POSIX venv executable symlink semantics.
    executable = supplied.parent.resolve() / supplied.name
    prefix = executable.parent.parent
    if prefix.is_relative_to(ROOT.resolve()) or not (prefix / "pyvenv.cfg").is_file():
        raise ValueError("Lesson SDK requires an external virtual environment")
    config = (prefix / "pyvenv.cfg").read_text(encoding="utf-8")
    if "version = 3.12." not in config:
        raise ValueError("Lesson SDK requires the declared Python3.12 profile")
    if os.name == "nt":
        settings = dict(line.split(" = ", 1) for line in config.splitlines() if " = " in line)
        base = Path(settings.get("executable", ""))
        try:
            with base.open("rb") as stream:
                direct = stream.read(2) == b"MZ"
        except OSError:
            direct = False
        if not direct:
            raise ValueError("Brokered Windows Python cannot guarantee owned-tree cleanup; create an external "
                             "lesson venv with a direct Python3.12 executable and the unchanged lesson profile")
    sites = [prefix / "Lib/site-packages", prefix / "lib/python3.12/site-packages"]
    site = next((path for path in sites if path.is_dir()), None)
    if site is None:
        raise ValueError("External SDK site-packages is absent")
    authorities()
    pins = {}
    for line in (AUTHORITY / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, version = line.split("==")
            pins[name] = version
    installed = {dist.metadata["Name"].lower().replace("_", "-"): dist.version
                 for dist in importlib.metadata.distributions(path=[str(site)])}
    if any(installed.get(name) != version for name, version in pins.items()):
        raise ValueError("External SDK dependency profile differs from reviewed pins")
    manifest = strict_json((AUTHORITY / "public-sdk-files.json").read_bytes())
    for variant in manifest["variants"]:
        files = variant["files_sha256"]
        if all((site / name).is_file() and sha(site / name) == digest for name, digest in files.items()):
            actual = {path.relative_to(site).as_posix() for path in (site / "softqp").rglob("*.py")}
            if actual != {name for name in files if name.startswith("softqp/") and name.endswith(".py")}:
                raise ValueError("External SDK has unexpected Python sources")
            snapshots = {str(site / name): digest for name, digest in files.items()}
            snapshots[str(prefix / "pyvenv.cfg")] = sha(prefix / "pyvenv.cfg")
            snapshots[str(executable)] = sha(executable)
            if os.name == "nt":
                snapshots[str(base)] = sha(base)
            return executable, prefix, snapshots
    raise ValueError("External SDK bytes differ from verified public wheels")


def validate_input(value):
    schema = strict_json(SCHEMA.read_bytes())["properties"]["input"]
    Draft202012Validator(schema).validate(value)
    if not all(type(v) in (int, float) and math.isfinite(v) for v in value.values()):
        raise ValueError("Lesson input must be finite real numbers")
    if len(canonical(value)) > 4096:
        raise ValueError("Lesson input exceeds4KiB")


def validate_envelope(document, request, worker_sha):
    Draft202012Validator(strict_json(SCHEMA.read_bytes())).validate(document)
    canonical(document)  # JSON Schema number does not exclude IEEE NaN/Infinity
    if (document["input"] != request or document["input_sha256"] != hashlib.sha256(canonical(request)).hexdigest()
            or document["worker_sha256"] != worker_sha):
        raise ValueError("Lesson worker input/source identity differs")
    a, b, upper = request["linear"], request["quadratic"], request["upper_scale"]
    k = max(upper, 1.5)
    optimum = max(1, (5 - a*k + b*k*k) / (2 + b*k*k))
    for record in document["records"]:
        if record["method"] == "row-split-gsp" and b > 0:
            if record["state"] != "incompatible":
                raise ValueError("Quadratic row-split must preserve incompatibility")
            continue
        if record["state"] == "incompatible":
            raise ValueError("This admitted input has no incompatibility for that method")
        if record["state"] not in ("accepted", "accuracy-rejected"):
            continue  # a real numerical failure stays visible, never replaced by a candidate
        variables, rows, nnz = {"native": (2, 3, 6), "epigraph": (3, 6, 13 + int(b > 0)),
                                "row-split-gsp": (2, 5, 8)}[record["method"]]
        if a == b == 0 and record["method"] != "native":
            variables, rows, nnz = 2, 1, 4  # free soft groups disappear from both equivalent lifts
        if record["dimensions"] != dict(variables=variables, rows=rows, nnz=nnz):
            raise ValueError("Lesson formulation dimensions differ from this actual fixed problem")
        x, y = record["x"]
        peak = max(upper*max(x-1, 0), max(y-1, 0), max(-1-x, 0), 1.5*max(-1-y, 0))
        objective = (x*x+y*y)/2 - 3*x + 2*y + a*peak + b*peak*peak/2
        if any(abs(record[name] - actual) > 1e-7*max(1, abs(actual)) for name, actual in
               (("peak", peak), ("objective", objective), ("hard_violation", abs(x+y)))):
            raise ValueError("Lesson original physical objective/violation differs")
        if record["state"] == "accepted" and (max(abs(x-optimum), abs(y+optimum)) > 1e-5
                                               or record["kkt_max"] > 1e-6 or abs(x+y) > 1e-6):
            raise ValueError("Accepted lesson candidate fails independent analytic/original check")
    return document


def run_comparison(*, linear=0.6, quadratic=0, upper_scale=1, row_scale=1):
    """Execute the three genuine methods on the same declared two-variable QP."""
    request = dict(linear=linear, quadratic=quadratic, upper_scale=upper_scale, row_scale=row_scale)
    validate_input(request)
    python = os.environ.get("SOFTQP_COUPLED_PYTHON")
    if not python:
        raise ValueError("Set SOFTQP_COUPLED_PYTHON to the reviewed external SDK2 interpreter")
    executable, prefix, package = runtime_identity(python)
    temporary = Path(os.environ.get("CAOS_TEMP_ROOT", ""))
    if not temporary.is_absolute() or not temporary.is_dir():
        raise ValueError("CAOS_TEMP_ROOT must name an existing absolute external temporary root")
    temporary = temporary.resolve()
    if temporary.is_relative_to(ROOT.resolve()) or temporary.is_relative_to(prefix):
        raise ValueError("Lesson scratch must be outside the checkout and SDK environment")
    protected = [WORKER, Path(__file__), Path(__file__).with_name("lesson_process.py"), SCHEMA,
                 Path(__file__).with_name("coupled_accuracy.py"), Path(__file__).with_name("__init__.py"),
                 *[AUTHORITY / name for name in IDENTITIES]]
    snapshot = {**package, **{str(path): sha(path) for path in protected}}
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update(PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
    scratch = tempfile.mkdtemp(prefix="softqp-lesson-", dir=temporary)
    teardown_confirmed = True
    try:
        command = [str(executable), "-I", "-S", "-B", "-X", f"pycache_prefix={scratch}/cache", str(WORKER)]
        raw = execute(command, canonical(request), scratch, env)
        if any(sha(name) != digest for name, digest in snapshot.items()):
            raise ValueError("Lesson source or installed SDK changed during execution")
        # Re-read profile metadata too; version drift can occur outside the SDK directory.
        if runtime_identity(python)[2] != package:
            raise ValueError("External SDK identity changed")
        return validate_envelope(strict_json(raw), request, snapshot[str(WORKER)])
    except WorkerCleanupError:
        teardown_confirmed = False
        raise
    finally:
        if teardown_confirmed:
            try:
                shutil.rmtree(scratch)
            except OSError as error:
                raise RuntimeError(f"Lesson scratch cleanup failed; recovery directory: {scratch}") from error
