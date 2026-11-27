"""Fixed held-out test-native capability. Imported only by the verified runtime."""

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from types import ModuleType


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def canonical(raw):
    value = json.loads(raw)
    need(type(value) is dict and encode(value) == raw, "held-out launch is not canonical")
    return value


def hex_digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def scope(launch, profile, fixture, *, candidate=False):
    request, policy = map(canonical, launch)
    operation = "evaluate-heldout-fixture" if fixture else "evaluate-heldout"
    need(
        set(request)
        == {"schema", "operation", "stage", "roster_sha256", "p0_sha256", "p1_sha256", "inventory_sha256"}
        and request["schema"] == "softqp.heldout-request/1"
        and request["operation"] == operation
        and (
            request["stage"] == "candidate" if candidate else
            request["stage"] == "test-native" or (fixture and request["stage"] == "candidate")
        ),
        "fixed held-out input operation differs",
    )
    need(
        set(policy) == {"schema", "operation", "stage", "request_sha256", "scope", "expected", "inputs"}
        and policy["schema"] == "softqp.heldout-policy/1"
        and policy["operation"] == operation
        and policy["stage"] == request["stage"]
        and policy["request_sha256"] == digest(launch[0])
        and (
            policy["expected"] is None
            if request["stage"] == "test-native"
            else type(policy["expected"]) is dict
            and set(policy["expected"]) == {"test_sha256", "native_sha256", "proof_sha256"}
            and all(hex_digest(sha) for sha in policy["expected"].values())
        ),
        "held-out launch policy differs",
    )
    bound = policy["scope"]
    need(
        bound["profile_sha256"] == profile
        and all(
            hex_digest(request[k]) and request[k] == bound[k]
            for k in ("roster_sha256", "p0_sha256", "p1_sha256", "inventory_sha256")
        ),
        "held-out seal mismatch",
    )
    return request, policy


def check_leaf(spec, profile, fixture):
    need(
        set(spec)
        == {
            "schema",
            "operation",
            "stage",
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
        and spec["schema"] == "softqp.heldout-native-leaf/1"
        and spec["operation"] == ("evaluate-heldout-fixture" if fixture else "evaluate-heldout")
        and spec["stage"] == "test-native"
        and spec["fixture_only"] is fixture
        and spec["roles"] == ["test"]
        and spec["profile_sha256"] == profile
        and all(
            hex_digest(spec[k])
            for k in ("scope_sha256", "authority_sha256", "request_sha256", "policy_sha256")
        )
        and type(spec["owner"]) is int
        and spec["owner"] > 0
        and type(spec["generation"]) is int
        and 0 <= spec["generation"] < 2208
        and type(spec["nonce"]) is str
        and re.fullmatch(r"[0-9a-f]{32}", spec["nonce"])
        and type(spec["deadline_monotonic_ns"]) is int
        and time.monotonic_ns() < spec["deadline_monotonic_ns"] <= time.monotonic_ns() + 86400 * 10**9,
        "held-out native leaf custody differs",
    )


def dispatch(args, held, launch, *, verify_live, create_child, fixture, dispatch_candidate=None,
             read_only=False):
    from pipeline.learned_comparison import heldout_inputs

    request, policy = scope(launch, args.expected_profile_sha256, fixture,
                            candidate=dispatch_candidate is not None)
    need(not read_only or (dispatch_candidate is not None and create_child is None),
         "held-out recovery scope is read-only")
    roots = [
        Path(policy["scope"][key]) for key in ("test_root", "native_root", "proof_root", "frontier_root")
    ]
    for root in roots if request["stage"] == "test-native" else ():
        need(
            root.is_absolute()
            and not root.exists()
            and root.parent.resolve(strict=True).parts == root.parent.parts
            and not any(
                root.is_relative_to(p) or p.is_relative_to(root)
                for p in (
                    args.source,
                    args.profile,
                    args.python.parents[1],
                    args.base_python.parent,
                    args.run,
                )
            ),
            "held-out owned output overlaps a protected root",
        )
    native_root = roots[1]
    module = ModuleType("softqp_heldout_runtime_custody")
    token = object()
    owner = os.getpid()
    child = None
    next_generation = 0
    deadline = time.monotonic_ns() + 86400 * 10**9

    def active(candidate, *, read_only=False):
        verify_live()
        need(
            candidate is token
            and read_only is recovery_scope
            and os.getpid() == owner
            and sys.modules.get(module.__name__) is module
            and time.monotonic_ns() < deadline,
            "active held-out worker ownership differs",
        )
        return args.expected_profile_sha256

    recovery_scope = read_only

    def check(candidate, *, operation, stage, request_sha256, profile_sha256, source_file, read_only=False):
        need(
            active(candidate, read_only=read_only) == profile_sha256
            and operation == request["operation"]
            and stage == request["stage"]
            and request_sha256 == digest(launch[0]),
            "held-out live operation or profile changed",
        )
        kind, relative, _ = held.identify(source_file)
        need(
            (kind, relative) == ("source", "data-pipeline/pipeline/learned_comparison/heldout_inputs.py"),
            "held-out native fixed entrypoint differs",
        )
        return launch[1]

    def spawn(candidate, *, root, nonce, generation, authority_sha256, scope_sha256, **identity):
        nonlocal child, next_generation
        check(candidate, **identity)
        need(request["stage"] == "test-native", "candidate fixture cannot launch test-native worker")
        need(
            (child is None or child.process is None)
            and generation == next_generation
            and root == native_root / f"worker-{generation:04d}"
            and not root.exists(),
            "held-out native leaf generation or target differs",
        )
        spec = dict(
            schema="softqp.heldout-native-leaf/1",
            operation=request["operation"],
            stage="test-native",
            nonce=nonce,
            owner=owner,
            generation=generation,
            scope_sha256=scope_sha256,
            authority_sha256=authority_sha256,
            profile_sha256=args.expected_profile_sha256,
            request_sha256=digest(launch[0]),
            policy_sha256=digest(launch[1]),
            deadline_monotonic_ns=deadline,
            fixture_only=fixture,
            roles=["test"],
        )
        check_leaf(spec, args.expected_profile_sha256, fixture)
        child = create_child(root, spec)
        next_generation += 1
        return child

    def native_settings(candidate, *, read_only=False):
        profile_sha = active(candidate, read_only=read_only)
        from pipeline.learned_comparison.native_labels import settings_identities

        raw = (args.profile / "provenance.json").read_bytes()
        need(digest(raw) == profile_sha, "held-out profile changed before settings admission")
        profile = json.loads(raw)
        return settings_identities(
            {
                "profile_sha256": profile_sha,
                "defaults_sha256": profile["defaults_sha256"],
                "wheel_sha256": profile["source_artifacts"]["checksums"][
                    "softqp-0.3.0-cp312-cp312-win_amd64.whl"
                ],
                "engine_source": profile["canonical_engine_source"],
            }
        )

    module.approved_native_settings = native_settings
    module.active_profile_sha256, module.read_policy = active, check
    if not read_only:
        module.open_test_native_worker = spawn
    else:
        def historical_profile(candidate, *, request_sha256, source_file):
            profile = active(candidate, read_only=True)
            need(not fixture and request_sha256 == digest(launch[0]) and held.identify(source_file)[:2] ==
                 ("source", "data-pipeline/pipeline/learned_comparison/authority.py"),
                 "historical entrypoint or recovery lane differs")
            return profile

        module.historical_profile = historical_profile
    need(module.__name__ not in sys.modules, "unexpected held-out capability module")
    sys.modules[module.__name__] = module
    try:
        if request["stage"] == "candidate":
            if dispatch_candidate is not None:
                return dispatch_candidate(token)
            from test_heldout_inputs import observe_candidate_fixture

            need(fixture, "only the excluded fixture may use the candidate audit route")
            result = observe_candidate_fixture(launch[0], token)
            verify_live()
            return result
        result = heldout_inputs.dispatch_heldout_inputs(launch[0], token)
        verify_live()
        expected = dict(
            schema="softqp.heldout-inputs-result/1",
            fixture_only=fixture,
            request_sha256=digest(launch[0]),
            policy_sha256=digest(launch[1]),
            roster_sha256=request["roster_sha256"],
        )
        need(
            child is not None
            and child.process is None
            and all(result.get(k) == v for k, v in expected.items()),
            "held-out native result lacks owned clean closure",
        )
        for path, key in (
            (roots[0] / "test-inputs.json", "test_sha256"),
            (roots[1] / "native-run.json", "native_sha256"),
            (roots[2] / "proof.json", "proof_sha256"),
        ):
            need(
                path.resolve(strict=True).parts == path.parts and digest(path.read_bytes()) == result[key],
                "held-out final stored byte identity changed",
            )
        return result
    finally:
        sys.modules.pop(module.__name__, None)
        if child is not None:
            child.close()
