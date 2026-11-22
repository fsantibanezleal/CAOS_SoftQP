"""Fixed learning launch contract for the byte-bound scientific supervisor."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from types import ModuleType

OPERATIONS = {"train-model", "calibrate-model"}
METHODS = {"learned_osqp", "learned_daqp"}
HOURS_48 = 48 * 3600
REQUEST_KEYS = {"schema", "operation", "method", "seed", "resume"}
POLICY_KEYS = {"schema", "operation", "request_sha256", "profile_sha256", "admission", "scope",
               "output_root", "artifact_roots"}


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def hex_digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def canonical(raw):
    value = json.loads(raw)
    need(type(value) is dict and encode(value) == raw, "noncanonical learning launch document")
    return value


def encode(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode() + b"\n"


def learning_scope(launch, expected_profile):
    raw, policy_raw = launch
    request, policy = canonical(raw), canonical(policy_raw)
    need(set(request) == REQUEST_KEYS and request["schema"] == "softqp.r4.learning-request/1"
         and type(request["operation"]) is str and request["operation"] in OPERATIONS
         and type(request["method"]) is str and request["method"] in METHODS
         and type(request["seed"]) is int and request["seed"] in (41001, 41002, 41003),
         "unsupported learning method, seed or operation")
    operation = request["operation"]
    resume = request["resume"]
    need(resume is None or (operation == "train-model" and type(resume) is dict
         and set(resume) == {"root", "sha256"} and type(resume["root"]) is str
         and Path(resume["root"]).is_absolute() and hex_digest(resume["sha256"])),
         "invalid learning resume")
    need(set(policy) == POLICY_KEYS and policy["schema"] == "softqp.r4.learning-policy/1"
         and policy["operation"] == operation and policy["profile_sha256"] == expected_profile
         and policy["request_sha256"] == digest(raw), "learning policy identity differs")
    scope = policy["scope"]
    roles = {"train", "validation"} if operation == "train-model" else {"calibration"}
    expected = {"preflight", "roles", "resume"} | ({"frozen", "committed_artifact_receipt"} if operation == "calibrate-model" else set())
    need(type(scope) is dict and set(scope) == expected and type(scope["roles"]) is dict
         and set(scope["roles"]) == roles and scope["resume"] == resume, "learning role or resume scope differs")
    workspace = Path(policy["output_root"])
    need(workspace.is_absolute() and workspace.resolve(strict=True).parts == workspace.parts and workspace.is_dir(),
         "learning workspace must be an existing exact external directory")
    bundle = f'{request["method"]}-{request["seed"]}'
    if resume is not None:
        bundle += "-resume-" + resume["sha256"][:16]
    leaf = workspace / (("calibration-" if operation == "calibrate-model" else "") + bundle) / "worker"
    return request, policy, leaf


def dispatch_learning(args, held, launch, *, verify_live, create_child):
    from pipeline.learned_comparison import training

    request, policy, leaf = learning_scope(launch, args.expected_profile_sha256)
    operation = request["operation"]
    for protected in (args.source, args.profile, args.python.parents[1], args.base_python.parent, args.run):
        need(not leaf.is_relative_to(protected) and not protected.is_relative_to(leaf.parent),
             "learning scratch overlaps verified input or supervisor scratch")
    need(shutil.disk_usage(leaf.parent.parent).free >= 20 * 2**30, "learning workspace free disk below 20 GiB")
    scope = object()
    owner = os.getpid()
    module = ModuleType("softqp_runtime_custody")
    deadline = time.monotonic_ns() + HOURS_48 * 10**9
    live = True
    child = None
    started = False

    def check(handle, *, operation, request_sha256, source_file, profile_sha256=None):
        verify_live()
        need(live and os.getpid() == owner and sys.modules.get(module.__name__) is module
             and handle is scope and operation == request["operation"]
             and request_sha256 == digest(launch[0]) and profile_sha256 in (None, args.expected_profile_sha256)
             and time.monotonic_ns() < deadline, "active learning operation custody differs or expired")
        kind, relative, _ = held.identify(source_file)
        need(kind == "source" and relative == "data-pipeline/pipeline/learned_comparison/training.py",
             "active learning dispatcher source differs")

    def read_active_learning_policy(handle, **identity):
        check(handle, **identity)
        return launch[1]

    def open_learning_worker(handle, *, root, nonce, expected_boot_sha256, **identity):
        nonlocal child, started
        check(handle, **identity)
        target = Path(root)
        need(not started and target.parts == leaf.parts and not target.exists()
             and target.parent.resolve(strict=True).parts == target.parent.parts
             and hex_digest(expected_boot_sha256) and type(nonce) is str and re.fullmatch(r"[0-9a-f]{32}", nonce) is not None,
             "learning worker location, nonce or one-use lease differs")
        started = True
        payload = {"schema": "softqp.r4.learning-leaf/1", "nonce": nonce,
                   "operation": operation, "method": request["method"], "seed": request["seed"],
                   "request_sha256": digest(launch[0]), "policy_sha256": digest(launch[1]),
                   "profile_sha256": args.expected_profile_sha256, "deadline_monotonic_ns": deadline,
                   "boot_sha256": expected_boot_sha256,
                   "owner": owner}
        child = create_child(target, payload)
        return child

    module.read_active_learning_policy = read_active_learning_policy
    module.open_learning_worker = open_learning_worker
    need(module.__name__ not in sys.modules, "unexpected preexisting learning custody module")
    sys.modules[module.__name__] = module
    try:
        result = training.dispatch_registered_learning(launch[0], scope)
        verify_live()
        expected = {key: request[key] for key in ("operation", "method", "seed")}
        expected.update(schema="softqp.r4.learning-result/1", request_sha256=digest(launch[0]),
                        policy_sha256=digest(launch[1]))
        need(started and child is not None and child.process is None and type(result) is dict
             and len(encode(result)) <= 8192 and set(result) == set(expected) | {"manifest", "state"}
             and all(result[key] == value for key, value in expected.items()),
             "learning operation lacks a closed worker or scoped completion")
        ref = result["manifest"]
        name = "calibration.json" if operation == "calibrate-model" else "training-run.json"
        need(type(ref) is dict and set(ref) == {"path", "sha256"} and hex_digest(ref["sha256"])
             and ref["path"] == f"{leaf.parent.name}/{name}", "learning completion manifest differs")
        manifest = leaf.parent / name
        need(manifest.resolve(strict=True).parts == manifest.parts and manifest.stat().st_size <= 2**24
             and digest(manifest.read_bytes()) == ref["sha256"],
             "learning completion bytes differ from observed manifest")
        return result
    finally:
        live = False
        sys.modules.pop(module.__name__, None)
        if child is not None:
            child.close()
