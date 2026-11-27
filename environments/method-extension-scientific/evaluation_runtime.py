"""Independent candidate-bake watchdog. Runs in the external supervisor."""

import hashlib
import json
import os
import re
import time
from pathlib import Path

TRIAL_NS = 10_000_000_000
BAKE_NS = 24 * 3600 * 10**9
RSS_LIMIT = 4 * 2**30
MAX_BAKE_BYTES = 2**22
RECOVERY_BYTES = 2**30
_SHA = re.compile(r"[0-9a-f]{64}")
_NONCE = re.compile(r"[0-9a-f]{32}")


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def encode(value):
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def sha(value):
    return type(value) is str and _SHA.fullmatch(value) is not None


def canonical(raw):
    data = json.loads(raw)
    need(type(data) is dict and encode(data) == raw, "noncanonical candidate custody bytes")
    return data


def windows_boot_id():
    from ctypes import WinDLL, byref, c_long, c_uint32, c_ubyte
    import uuid

    query = WinDLL("ntdll").NtQuerySystemInformation
    query.restype = c_long
    response = (c_ubyte * 32)()
    returned = c_uint32()
    # SYSTEM_BOOT_ENVIRONMENT_INFORMATION begins with the BootIdentifier GUID.
    need(query(90, byref(response), len(response), byref(returned)) == 0 and returned.value >= 16,
         "Windows boot identity unavailable")
    return uuid.UUID(bytes_le=bytes(response[:16])).hex


def timer_receipt(bake):
    path = Path(bake["frontier_root"]) / "timer.json"
    with path.open("rb") as handle:
        raw = handle.read(8193)
    need(len(raw) <= 8192 and digest(raw) == bake["timer_sha256"],
         "independently anchored candidate timer digest differs")
    timer = canonical(raw)
    identities = {
        key: bake[key] for key in (
            "request_sha256", "policy_sha256", "profile_sha256", "schedule_sha256", "cohort_sha256",
            "test_sha256", "native_sha256", "proof_sha256",
        )
    }
    need(set(timer) == set(identities) | {"schema", "boot_id", "started_ns", "deadline_ns"}
         and timer["schema"] == "softqp.r4.candidate-timer/1"
         and all(timer[key] == value for key, value in identities.items())
         and type(timer["boot_id"]) is str and bool(timer["boot_id"])
         and type(timer["started_ns"]) is type(timer["deadline_ns"]) is int
         and timer["started_ns"] > 0
         and timer["deadline_ns"] - timer["started_ns"] == BAKE_NS,
         "candidate timer continuity or original 24-hour deadline differs")
    return timer


def timer_scope(bake, *, boot=windows_boot_id, now=time.perf_counter_ns):
    timer = timer_receipt(bake)
    need(timer["boot_id"] == boot() and timer["started_ns"] <= now() < timer["deadline_ns"],
         "candidate timer continuity or original 24-hour deadline differs")
    return timer["deadline_ns"]


def journal_plan_sha256(bake):
    return digest(encode({key: bake[key] for key in ("schedule_sha256", "timer_sha256")}))


def watchdog_inputs(bake, *, fixture):
    root = Path(bake["frontier_root"])
    plan_path = root / "schedule.ndjson"
    with plan_path.open("rb") as handle:
        raw = handle.read(32 * 2**20 + 1)
    need(len(raw) <= 32 * 2**20 and digest(raw) == bake["schedule_sha256"],
         "independent candidate schedule digest differs")
    rows = []
    for line in raw.splitlines(keepends=True):
        row = json.loads(line)
        need(type(row) is list and len(row) == 8 and encode(row) == line
             and all(type(value) in {int, str} for value in row),
             "noncanonical independent candidate schedule")
        rows.append(tuple(row))
    need(0 < len(rows) <= 239960 and (fixture or len(rows) == 239960)
         and len(rows) == len(set(rows)), "independent candidate schedule inventory differs")
    with (root / "frontier.json").open("rb") as handle:
        frontier_raw = handle.read(8193)
    need(len(frontier_raw) <= 8192 and digest(frontier_raw) == bake["frontier_sha256"],
         "independent candidate frontier digest differs")
    frontier = canonical(frontier_raw)
    need(frontier["schema"] == "softqp.r4.heldout-frontier/1"
         and frontier["plan_sha256"] == journal_plan_sha256(bake)
         and type(frontier["next"]) is int and 0 <= frontier["next"] <= len(rows),
         "independent candidate frontier scope differs")
    first = frontier["next"] + int(frontier["active"] is not None)
    need(first <= len(rows), "active candidate frontier is outside schedule")
    return first, len(rows), rows[first:]


def scoped_bake(raw, expected, request_raw, policy_raw, profile):
    """Authorize a fixed launch descriptor separately from the held-out policy."""
    need(sha(expected) and len(raw) <= MAX_BAKE_BYTES and digest(raw) == expected,
         "candidate bake digest differs")
    data = canonical(raw)
    request, policy = map(canonical, (request_raw, policy_raw))
    expected_fields = {
        "schema",
        "request_sha256",
        "policy_sha256",
        "profile_sha256",
        "scope_sha256",
        "roster_sha256",
        "test_sha256",
        "native_sha256",
        "proof_sha256",
        "schedule_sha256",
        "cohort_sha256",
        "frontier_sha256",
        "timer_sha256",
        "output_root",
        "frontier_root",
        "diagnostics",
        "committed_input_bytes",
    }
    need(
        set(data) == expected_fields and data["schema"] == "softqp.r4.candidate-bake/1",
        "candidate bake descriptor shape differs",
    )
    need(
        request.get("stage") == policy.get("stage") == "candidate"
        and request.get("operation") in {"evaluate-heldout", "evaluate-heldout-fixture"}
        and policy.get("operation") == request["operation"],
        "candidate bake requires the fixed held-out stage",
    )
    scope = policy["scope"]
    need(
        type(policy["expected"]) is dict
        and set(policy["expected"]) == {"test_sha256", "native_sha256", "proof_sha256"},
        "candidate bake stage digests differ",
    )
    expected_hashes = dict(
        request_sha256=digest(request_raw),
        policy_sha256=digest(policy_raw),
        profile_sha256=profile,
        scope_sha256=digest(encode(scope)),
        roster_sha256=request["roster_sha256"],
        **policy["expected"],
    )
    need(
        all(sha(value) and data.get(key) == value for key, value in expected_hashes.items())
        and sha(data["schedule_sha256"])
        and sha(data["cohort_sha256"])
        and sha(data["frontier_sha256"])
        and sha(data["timer_sha256"]),
        "candidate bake lineage differs",
    )
    output, frontier = (Path(data[key]) for key in ("output_root", "frontier_root"))
    need(
        all(path.is_absolute() and ".." not in path.parts for path in (output, frontier))
        and not (output.is_relative_to(frontier) or frontier.is_relative_to(output)),
        "candidate roots overlap",
    )
    for artifact in ("test_root", "proof_root", "native_root", "frontier_root"):
        prior = Path(scope[artifact])
        need(
            all(
                not (path.is_relative_to(prior) or prior.is_relative_to(path)) for path in (output, frontier)
            ),
            "candidate output aliases predecessor scope",
        )
    need(type(data["diagnostics"]) is list and len(data["diagnostics"]) <= 101,
         "candidate diagnostic inventory missing or oversized")
    need(
        type(data["committed_input_bytes"]) is int and 0 <= data["committed_input_bytes"] <= 8 * 2**30,
        "independently accounted test, model and reference inputs exceed 8 GiB",
    )
    return data


def recovery_scope(raw, expected, bake, original_bake_sha256):
    need(sha(expected) and len(raw) <= 8192 and digest(raw) == expected,
         "candidate recovery policy digest differs")
    data = canonical(raw)
    need(
        set(data) == {"schema", "original_bake_sha256", "frontier_sha256", "journal_sha256",
                      "terminal_sha256", "staged_sha256", "terminal_root", "output_root",
                      "max_wall_seconds"}
        and data["schema"] == "softqp.r4.candidate-recovery-policy/1"
        and data["original_bake_sha256"] == original_bake_sha256
        and all(sha(data[key]) for key in ("frontier_sha256", "journal_sha256", "terminal_sha256"))
        and (data["staged_sha256"] is None or sha(data["staged_sha256"]))
        and type(data["max_wall_seconds"]) is int and 0 < data["max_wall_seconds"] <= 86400,
        "candidate recovery policy shape or resources differ",
    )
    terminal, output = map(Path, (data["terminal_root"], data["output_root"]))
    original = tuple(Path(bake[name]) for name in ("frontier_root", "output_root"))
    need(terminal.is_absolute() and terminal.resolve(strict=True).parts == terminal.parts
         and output.is_absolute() and output.resolve().parts == output.parts
         and all(not (output.is_relative_to(path) or path.is_relative_to(output))
                 for path in (*original, terminal)), "candidate recovery output aliases original evidence")
    return data


def terminal_recovery_scope(doc, *, bake, policy, source_manifest, timer):
    need(doc["status"] == "refused" and doc["cleanup"] == "owned-process-tree-closed"
         and doc["profile_sha256"] == bake["profile_sha256"]
         and doc["source_manifest_sha256"] == source_manifest
         and doc["i1_issued"] is False and type(doc["owned_pids"]) is list,
         "candidate recovery terminal Job and profile differ")
    command = doc["command"]
    for flag, key in (
        ("--expected-bake-sha256", "original_bake_sha256"),
        ("--expected-request-sha256", "request_sha256"),
        ("--expected-policy-sha256", "policy_sha256"),
    ):
        need(command.count(flag) == 1 and command[command.index(flag) + 1] == (bake | policy)[key],
             "candidate terminal command differs")
    need(command.count("--candidate") == 1 and "--candidate-recover" not in command
         and command.count("--run") == 1 and Path(command[command.index("--run") + 1]) == Path(policy["terminal_root"]),
         "candidate terminal stage or root differs")
    terminal = doc["candidate_terminal"]
    need(terminal["timer_sha256"] == bake["timer_sha256"]
         and terminal["boot_id"] == timer["boot_id"]
         and terminal["reason"] in {"bake-deadline", "trial-deadline", "evaluation-rss-cap", "candidate-failed"}
         and (terminal["reason"] != "bake-deadline" or terminal["observed_ns"] >= timer["deadline_ns"]),
         "candidate original terminal clock or disposition differs")
    return terminal["reason"]


def marker_path(root, ordinal, kind):
    need(
        type(ordinal) is int and 0 <= ordinal < 239960 and kind in {"ready", "release", "observed", "closed"},
        "invalid candidate marker name",
    )
    return root / f"trial-{ordinal:06d}-{kind}.json"


def read_marker(path):
    with path.open("rb") as handle:
        raw = handle.read(4097)
    need(len(raw) <= 4096, "oversize candidate marker")
    return canonical(raw)


def polled_marker(path):
    try:
        return read_marker(path)
    except FileNotFoundError:
        return None
    except PermissionError:
        if os.name != "nt":
            raise
        return None


def write_marker(path, value):
    pending = path.with_suffix(".pending")
    with pending.open("xb") as handle:
        handle.write(encode(value))
    pending.rename(path)


class TrialWatchdog:
    """One trial release at a time. Called by the owner of the outer Windows Job."""

    def __init__(self, root, *, first, finish, schedule, deadline_ns, now=time.perf_counter_ns):
        self.root = root
        self.ordinal = first
        self.finish = finish
        self.deadline = deadline_ns
        self.now = now
        self.schedule = iter(schedule)
        # The caller already opened and verified the independent frontier.
        self.current = next(self.schedule, None)
        self._active = None
        self.getter_pid = None
        need(
            type(first) is type(finish) is int and 0 <= first <= finish <= 239960,
            "invalid candidate watchdog range",
        )

    def step(self, *, owned_pids, combined_peak_rss):
        now = self.now()
        if combined_peak_rss >= RSS_LIMIT:
            raise TimeoutError("combined candidate Job working-set exceeded 4 GiB")
        if now >= self.deadline:
            raise TimeoutError("candidate 24-hour bake deadline")
        if self.ordinal == self.finish:
            return
        if self._active is None:
            ready = marker_path(self.root, self.ordinal, "ready")
            value = polled_marker(ready)
            if value is None:
                return
            need(
                set(value) == {"key", "ordinal", "owner", "nonce"}
                and self.current is not None
                and value["key"] == list(self.current)
                and value["ordinal"] == self.ordinal
                and type(value["owner"]) is int
                and value["owner"] in owned_pids
                and (self.getter_pid is None or value["owner"] == self.getter_pid)
                and type(value["nonce"]) is str
                and _NONCE.fullmatch(value["nonce"]),
                "candidate ready marker differs",
            )
            started = self.now()
            release = {**value, "released_ns": started, "deadline_ns": min(started + TRIAL_NS, self.deadline)}
            self._active = release
            write_marker(marker_path(self.root, self.ordinal, "release"), release)
            return
        release = self._active
        if now >= release["deadline_ns"]:
            raise TimeoutError(f"candidate whole-trial deadline at ordinal {self.ordinal}")
        need(release["owner"] in owned_pids, "candidate getter owner left its Job")
        observed = marker_path(self.root, self.ordinal, "observed")
        body = polled_marker(observed)
        if body is None:
            return
        need(
            set(body) == set(release) | {"result_sha256"}
            and sha(body["result_sha256"])
            and all(body[key] == value for key, value in release.items()),
            "candidate observed marker differs",
        )
        ended = self.now()
        if ended >= release["deadline_ns"]:
            raise TimeoutError(f"candidate result landed too late at ordinal {self.ordinal}")
        write_marker(marker_path(self.root, self.ordinal, "closed"), {**body, "observed_ns": ended})
        self.ordinal += 1
        self.current = next(self.schedule, None)
        self._active = None

    def require_complete(self):
        need(
            self.ordinal == self.finish and self.current is None and self._active is None,
            "candidate watchdog ended before the independently expected schedule",
        )


def check_leaf(spec, *, profile, fixture):
    expected = {
        "schema",
        "stage",
        "operation",
        "profile_sha256",
        "request_sha256",
        "policy_sha256",
        "scope_sha256",
        "roster_sha256",
        "nonce",
        "owner",
        "slot_floor",
        "deadline_ns",
        "fixture_only",
        "settings_hashes",
        "models",
        "design_manifest_hex",
        "design_matrix_hex",
    }
    need(
        set(spec) == expected
        and spec["schema"] == "softqp.r4.candidate-leaf/1"
        and spec["stage"] == "candidate"
        and spec["operation"] == ("evaluate-heldout-fixture" if fixture else "evaluate-heldout")
        and spec["profile_sha256"] == profile
        and spec["fixture_only"] is fixture
        and all(sha(spec[k]) for k in ("request_sha256", "policy_sha256", "scope_sha256", "roster_sha256"))
        and type(spec["owner"]) is int
        and spec["owner"] > 0
        and type(spec["slot_floor"]) is int
        and 0 <= spec["slot_floor"] < 239960
        and type(spec["nonce"]) is str
        and _NONCE.fullmatch(spec["nonce"]) is not None
        and type(spec["deadline_ns"]) is int
        and all(type(spec[name]) is str and 0 < len(spec[name]) <= 2**19
                for name in ("design_manifest_hex", "design_matrix_hex"))
        and time.perf_counter_ns() < spec["deadline_ns"] <= time.perf_counter_ns() + BAKE_NS,
        "candidate leaf scope differs",
    )
    need(
        type(spec["settings_hashes"]) is dict
        and all(sha(value) for value in spec["settings_hashes"].values()),
        "candidate leaf settings locks differ",
    )
    expected_roster = [
        (method, seed) for method in ("learned_daqp", "learned_osqp") for seed in (41001, 41002, 41003)
    ]
    need(
        type(spec["models"]) is list
        and [(item["method"], item["seed"]) for item in spec["models"]] == expected_roster,
        "candidate leaf model roster differs",
    )


def dispatch(
    args,
    held,
    launch,
    bake_raw,
    expected_bake_sha256,
    *,
    heldout_token,
    verify_live,
    create_child,
    deadline_ns,
):
    """Install the fixed parent route inside an active held-out stage capability."""
    from dataclasses import asdict
    import os
    import secrets
    import sys
    from types import ModuleType, SimpleNamespace
    from pipeline.learned_comparison import evaluation_dispatch, evaluation_models, heldout_inputs

    bake = scoped_bake(bake_raw, expected_bake_sha256, *launch, args.expected_profile_sha256)
    request = canonical(launch[0])
    for name in ("output_root", "frontier_root"):
        root = Path(bake[name])
        need(
            not any(
                root.is_relative_to(protected) or protected.is_relative_to(root)
                for protected in (
                    args.source,
                    args.profile,
                    args.python.parents[1],
                    args.base_python.parent,
                    args.run,
                )
            ),
            "candidate runtime output overlaps a protected root",
        )
    guardian = ModuleType("softqp_candidate_runtime_custody")
    owner = os.getpid()
    opened = False
    child = None

    def live():
        verify_live()
        need(
            os.getpid() == owner
            and sys.modules.get(guardian.__name__) is guardian
            and time.perf_counter_ns() < deadline_ns,
            "candidate runtime custody or bake deadline differs",
        )

    def open_leaf(root, slot_floor, view):
        nonlocal child, opened
        live()
        need(
            not opened
            and child is None
            and root == Path(bake["output_root"]) / f"worker-{slot_floor:06d}"
            and not root.exists(),
            "candidate leaf lease or output path differs",
        )
        ids = view.identities()
        roster = []
        for method in ("learned_daqp", "learned_osqp"):
            for seed in (41001, 41002, 41003):
                entry = view.model_binding(method, seed)
                if type(entry) is evaluation_models.ModelTrust:
                    model = {k: str(v) if isinstance(v, Path) else v for k, v in asdict(entry).items()}
                    roster.append(dict(method=method, seed=seed, trust=model))
                else:
                    need(
                        type(entry) is heldout_inputs.CandidateModelFailure,
                        "unissued candidate model failure",
                    )
                    roster.append(dict(method=method, seed=seed, failure=canonical(entry.evidence)))
        nonce = secrets.token_hex(16)
        design = view.authority()
        spec = dict(
            schema="softqp.r4.candidate-leaf/1",
            stage="candidate",
            operation=request["operation"],
            **{
                key: ids[key]
                for key in (
                    "request_sha256",
                    "policy_sha256",
                    "scope_sha256",
                    "roster_sha256",
                    "profile_sha256",
                )
            },
            nonce=nonce,
            owner=owner,
            slot_floor=slot_floor,
            deadline_ns=deadline_ns,
            fixture_only=ids["fixture_only"],
            settings_hashes=view.settings_hashes(),
            models=roster,
            design_manifest_hex=design._manifest.hex(),
            design_matrix_hex=design._matrix.hex(),
        )
        check_leaf(spec, profile=args.expected_profile_sha256, fixture=ids["fixture_only"])
        opened = True
        launch_ns = time.perf_counter_ns()
        child = create_child(root, spec)
        installed = child.wait_file(root / "installed.json", 600)
        need(
            installed["pid"] in child._pids()
            and installed["nonce"] == nonce
            and installed["audit"]["full_files"] is True
            and installed["audit"]["distributions"] == 49,
            "candidate leaf installed-file custody differs",
        )
        write_marker(root / "import-ack.json", {"installed_sha256": digest(encode(installed))})
        imported = child.wait_file(root / "candidate-imported.json", 180)
        need(imported["pid"] == installed["pid"] and imported["nonce"] == nonce,
             "candidate leaf cold import identity differs")
        remaining = (deadline_ns - time.perf_counter_ns()) / 10**9
        need(remaining > 0, "candidate preload exceeded original bake deadline")
        ready = child.wait_file(root / "ready.json", remaining)
        ready_ns = time.perf_counter_ns()
        need(
            ready["pid"] == installed["pid"] and ready["nonce"] == nonce and ready["pid"] in child._pids()
            and launch_ns < imported["start_ns"] < imported["end_ns"] <= ready_ns < deadline_ns,
            "candidate leaf observed startup custody differs",
        )
        child.candidate_pid = ready["pid"]
        startup = dict(
            schema="softqp.r4.candidate-startup/1", slot_floor=slot_floor, nonce=nonce, pid=ready["pid"],
            profile_sha256=bake["profile_sha256"], policy_sha256=bake["policy_sha256"],
            launch_ns=launch_ns, ready_ns=ready_ns, installed=installed, imported=imported,
            heads=ready["heads"], fixture_only=ids["fixture_only"],
        )
        model_roster = [
            {"method": row["method"], "seed": row["seed"],
             "checkpoint_sha256": row["trust"]["checkpoint_sha256"],
             "projection_sha256": row["trust"]["preprocessing_sha256"],
             "calibration_sha256": row["trust"]["calibration_sha256"]} if "trust" in row else row
            for row in roster
        ]
        evaluation_dispatch.verify_startup(startup, expected_roster=model_roster,
                                           frozen_heads=design.matrix["heads"])
        child.startup_sha256 = digest(encode(startup))
        write_marker(root / "startup-observed.json", startup)
        write_marker(root / "startup-ack.json", {"startup_sha256": child.startup_sha256})
        return child

    def active_candidate(candidate, *, request_sha256, source_file):
        live()
        need(
            candidate is heldout_token
            and request_sha256 == bake["request_sha256"]
            and held.identify(source_file)[:2]
            == ("source", "data-pipeline/pipeline/learned_comparison/evaluation_dispatch.py"),
            "candidate fixed dispatcher differs",
        )
        return SimpleNamespace(
            require_live=live,
            open_leaf=open_leaf,
            marker_root=args.run,
            bake_descriptor=lambda: canonical(bake_raw),
            deadline_ns=deadline_ns,
        )

    guardian.active_candidate = active_candidate
    need(guardian.__name__ not in sys.modules, "unexpected candidate runtime capability")
    sys.modules[guardian.__name__] = guardian
    try:
        result = evaluation_dispatch.dispatch_candidate(launch[0], heldout_token)
        live()
        need(child is None or child.process is None, "candidate leaf did not release ownership")
        return result
    finally:
        sys.modules.pop(guardian.__name__, None)
        if child is not None:
            child.close()


def leaf_models(spec):
    """Preload only independently bound immutable model bundles inside the leaf."""
    from types import SimpleNamespace
    from pipeline.learned_comparison import contracts as c
    from pipeline.learned_comparison import evaluation_models as models

    manifest = bytes.fromhex(spec["design_manifest_hex"])
    matrix = bytes.fromhex(spec["design_matrix_hex"])
    need(digest(manifest) == c.DESIGN_MANIFEST_SHA256
         and digest(matrix) == c.strict_loads(manifest)["normative_sha256"]["semantic-matrix.json"],
         "candidate leaf design matrix differs")
    authority = SimpleNamespace(matrix=c.strict_loads(matrix))
    admitted, observations = {}, []
    for row in spec["models"]:
        method, seed = row["method"], row["seed"]
        if set(row) == {"method", "seed", "failure"}:
            failure = row["failure"]
            need(
                failure["method"] == method
                and failure["seed"] == seed
                and failure["state"] in {"missing", "failed"}
                and bool(failure["reason"]),
                "candidate model failure differs",
            )
            admitted[method, seed] = (None, (failure["state"], failure["reason"]))
            observations.append(dict(method=method, seed=seed, head=None, failure=failure))
            continue
        need(set(row) == {"method", "seed", "trust"}, "candidate model trust differs")
        trust = dict(row["trust"])
        for name in ("bundle_root", "preprocessing_root", "frozen_root"):
            trust[name] = Path(trust[name])
        need(trust["method"] == method and trust["seed"] == seed, "candidate model trust was relabeled")
        model = models.read_bundle(
            models.ModelTrust(**trust), authority=authority, allow_fixture=spec["fixture_only"]
        )
        heads = {}
        for head in model.preprocessing["heads"]:
            start = time.perf_counter_ns()
            scope = model.load_head(head)
            end = time.perf_counter_ns()
            preprocessing = (scope[1].numeric_sha256 if scope[1] is not None
                             else digest(c.canonical_bytes(model.preprocessing["class_statistics"])))
            heads[head] = scope
            observations.append(dict(method=method, seed=seed, head=head, start_ns=start, end_ns=end,
                                     checkpoint_sha256=trust["checkpoint_sha256"], weights_sha256=scope[2],
                                     preprocessing_sha256=preprocessing,
                                     projection_sha256=trust["preprocessing_sha256"],
                                     calibration_sha256=trust["calibration_sha256"]))
        admitted[method, seed] = ((heads, trust["checkpoint_sha256"]), None)

    def binding(method, seed, head):
        model, failure = admitted[method, seed]
        if failure is not None:
            return None, None, failure
        heads, checkpoint = model
        need(head in heads, "candidate frame belongs to an unpreloaded head")
        return heads[head], checkpoint, None

    return binding, observations
