"""Fixed native-label parent and leaf routing under the held scientific runtime."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from types import ModuleType

ROLES = ("train", "validation", "calibration")
REQUEST_KEYS = {"schema", "operation", "preflight_sha256", "roles", "inventory_sha256"}
POLICY_KEYS = {
    "schema",
    "operation",
    "request_sha256",
    "profile_sha256",
    "admission",
    "scope",
    "output_root",
    "artifact_roots",
}
LEAF_KEYS = {
    "schema",
    "operation",
    "nonce",
    "owner",
    "generation",
    "scope_sha256",
    "authority_sha256",
    "profile_sha256",
    "request_sha256",
    "policy_sha256",
    "deadline_monotonic_ns",
    "fixture_only",
    "roles",
}


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def hex_digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def encode(value):
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def canonical(raw):
    value = json.loads(raw)
    need(type(value) is dict and encode(value) == raw, "noncanonical native launch")
    return value


def native_scope(launch, expected_profile, *, fixture_only=False):
    request, policy = map(canonical, launch)
    operation = "native-label-fixture" if fixture_only else "native-label"
    need(
        set(request) == REQUEST_KEYS
        and request["schema"] == "softqp.r4.native-request/1"
        and request["operation"] == operation
        and all(hex_digest(request[key]) for key in ("preflight_sha256", "inventory_sha256")),
        "invalid fixed native request",
    )
    roles = request["roles"]
    need(
        type(roles) is list and roles and roles == [role for role in ROLES if role in roles],
        "native roles must be exact ordered non-test roles",
    )
    need(
        set(policy) == POLICY_KEYS
        and policy["schema"] == "softqp.r4.native-policy/1"
        and policy["operation"] == operation
        and policy["request_sha256"] == digest(launch[0])
        and policy["profile_sha256"] == expected_profile,
        "native launch policy differs",
    )
    scope = policy["scope"]
    expected = {"preflight", "authority", "roles", "inventory_sha256", "max_wall_seconds"}
    need(
        type(scope) is dict
        and set(scope) == expected
        and scope["roles"] == roles
        and scope["inventory_sha256"] == request["inventory_sha256"]
        and type(scope["preflight"]) is dict
        and scope["preflight"].get("sha256") == request["preflight_sha256"]
        and type(scope["max_wall_seconds"]) is int
        and 1 <= scope["max_wall_seconds"] <= 1_000_000,
        "native exact scope or deadline differs",
    )
    workspace = Path(policy["output_root"])
    need(
        workspace.is_absolute()
        and workspace.is_dir()
        and workspace.resolve(strict=True).parts == workspace.parts,
        "native workspace must be exact and external",
    )
    return request, policy, workspace / "native-run"


def check_leaf(spec, profile, *, fixture_only):
    operation = "native-label-fixture" if fixture_only else "native-label"
    need(
        set(spec) == LEAF_KEYS
        and spec["schema"] == "softqp.r4.native-leaf/1"
        and spec["operation"] == operation
        and spec["profile_sha256"] == profile
        and spec["fixture_only"] is fixture_only
        and type(spec["roles"]) is list
        and bool(spec["roles"])
        and spec["roles"] == [role for role in ROLES if role in spec["roles"]]
        and all(
            hex_digest(spec[key])
            for key in ("authority_sha256", "policy_sha256", "request_sha256", "scope_sha256")
        )
        and type(spec["generation"]) is int
        and 0 <= spec["generation"] < 15456
        and type(spec["owner"]) is int
        and spec["owner"] > 0
        and type(spec["nonce"]) is str
        and re.fullmatch(r"[0-9a-f]{32}", spec["nonce"])
        and type(spec["deadline_monotonic_ns"]) is int
        and time.monotonic_ns() < spec["deadline_monotonic_ns"] <= time.monotonic_ns() + 10**15,
        "native leaf scope, profile or expiration differs",
    )


def dispatch_native(args, held, launch, *, verify_live, create_child, fixture_only):
    from pipeline.learned_comparison import native_labels

    request, policy, target = native_scope(launch, args.expected_profile_sha256, fixture_only=fixture_only)
    for protected in (args.source, args.profile, args.python.parents[1], args.base_python.parent, args.run):
        need(
            not target.is_relative_to(protected) and not protected.is_relative_to(target),
            "native output overlaps approved source or runtime",
        )
    need(shutil.disk_usage(target.parent).free >= 20 * 2**30, "native volume free-space minimum")
    handle = object()
    module = ModuleType("softqp_native_runtime_custody")
    owner = os.getpid()
    deadline = time.monotonic_ns() + policy["scope"]["max_wall_seconds"] * 10**9
    child = None
    next_generation = 0

    def validate(candidate, *, operation, request_sha256, source_file, profile_sha256):
        verify_live()
        need(
            candidate is handle
            and os.getpid() == owner
            and sys.modules.get(module.__name__) is module
            and request["operation"] == operation
            and request_sha256 == digest(launch[0])
            and args.expected_profile_sha256 == profile_sha256
            and time.monotonic_ns() < deadline,
            "active native operation/job/profile differs",
        )
        kind, relative, _ = held.identify(source_file)
        need(
            (kind, relative) == ("source", "data-pipeline/pipeline/learned_comparison/native_labels.py"),
            "active native dispatcher source differs",
        )
        return launch[1]

    def open_worker(candidate, *, root, nonce, generation, authority_sha256, scope_sha256, **binding):
        nonlocal child, next_generation
        validate(candidate, **binding)
        need(
            (child is None or child.process is None)
            and generation == next_generation
            and root == target / f"worker-{generation:04d}"
            and not root.exists()
            and hex_digest(authority_sha256)
            and hex_digest(scope_sha256),
            "native leaf namespace, generation or prior cleanup differs",
        )
        spec = dict(
            schema="softqp.r4.native-leaf/1",
            operation=request["operation"],
            owner=owner,
            nonce=nonce,
            generation=generation,
            authority_sha256=authority_sha256,
            scope_sha256=scope_sha256,
            request_sha256=digest(launch[0]),
            policy_sha256=digest(launch[1]),
            profile_sha256=args.expected_profile_sha256,
            deadline_monotonic_ns=deadline,
            fixture_only=fixture_only,
            roles=request["roles"],
        )
        check_leaf(spec, args.expected_profile_sha256, fixture_only=fixture_only)
        child = create_child(root, spec)
        next_generation += 1
        return child

    def profile(candidate):
        need(
            candidate is handle and os.getpid() == owner and sys.modules.get(module.__name__) is module,
            "active native capability owner differs",
        )
        verify_live()
        return args.expected_profile_sha256

    module.active_profile_sha256 = profile
    module.read_policy = validate
    module.open_worker = open_worker
    need(module.__name__ not in sys.modules, "unexpected native custody module")
    sys.modules[module.__name__] = module
    try:
        result = native_labels.dispatch_registered_native(launch[0], handle, fixture_only=fixture_only)
        verify_live()
        expected = dict(
            schema="softqp.r4.native-result/1",
            request_sha256=digest(launch[0]),
            policy_sha256=digest(launch[1]),
            fixture_only=fixture_only,
        )
        need(
            child is not None
            and child.process is None
            and set(result) == set(expected) | {"manifest_sha256"}
            and all(result[k] == v for k, v in expected.items())
            and hex_digest(result["manifest_sha256"]),
            "native completion lacks a closed verified leaf",
        )
        path = target / "native-run.json"
        need(
            path.resolve(strict=True).parts == path.parts
            and digest(path.read_bytes()) == result["manifest_sha256"],
            "native completion bytes differ",
        )
        return result
    finally:
        sys.modules.pop(module.__name__, None)
        if child is not None:
            child.close()
