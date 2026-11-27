"""Scheduling and bounded receipt validation for the R4 held-out ledger."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import os
from pathlib import Path
import re
import time

from . import contracts as c

CONTROLS = {
    "cold_osqp": "learned_osqp",
    "cold_daqp": "learned_daqp",
    "previous_osqp": "learned_osqp",
    "previous_daqp": "learned_daqp",
}
PHASES = (("warmup", 0, 2), ("measured", 1, 5))
TRIAL_NS = 10_000_000_000
MAX_RESULT_BYTES = 16 * 2**20
BAKE_BYTES = 4 * 2**30
EVALUATION_RSS = 4 * 2**30
BAKE_NS = 24 * 3600 * 10**9
OPERATION = "evaluate-heldout"
_SHA256 = re.compile(r"[a-f0-9]{64}")


def is_sha256(value):
    return type(value) is str and _SHA256.fullmatch(value) is not None


@dataclass(frozen=True)
class Slot:
    key: tuple
    eligible: bool
    reason: str | None


def status_slots(authority):
    """Derive status membership before opening payloads."""
    for family_number in range(1, 16):
        family = f"N{family_number:02d}"
        for regime in range(6):
            methods = authority.row(family, regime)["methods"]
            for unit in range(8):
                for method in sorted(set(methods) | set(CONTROLS)):
                    if method.startswith("previous_") and family != "N12":
                        continue
                    cell = methods[CONTROLS.get(method, method)]
                    for seed in c.SEEDS if method in c.LEARNED else (0,):
                        for frame in range(32 if family == "N12" else 1):
                            yield Slot((method, seed, family, regime, unit, frame),
                                       cell["eligible"], cell["reason"])


def schedule_source(authority, family, regime, unit):
    """Registered clock order. Incompatible turns never enter the worker."""
    import numpy as np

    methods = authority.row(family, regime)["methods"]
    eligible = [(method, seed) for method in sorted(set(methods) | set(CONTROLS))
                if (family == "N12" or not method.startswith("previous_"))
                and methods[CONTROLS.get(method, method)]["eligible"]
                for seed in (c.SEEDS if method in c.LEARNED else (0,))]
    for phase, phase_index, count in PHASES:
        for rep in range(count):
            rng = np.random.Generator(np.random.PCG64(
                np.random.SeedSequence([20261105, 41110, int(family[1:]), regime, unit, phase_index, rep])))
            first = int(rng.integers(len(eligible)))
            for method, seed in eligible[first:] + eligible[:first]:
                for frame in range(32 if family == "N12" else 1):
                    yield (method, seed, family, regime, unit, frame, phase, rep)


def execution_schedule(authority):
    for family_number in range(1, 16):
        family = f"N{family_number:02d}"
        for regime in range(6):
            for unit in range(8):
                yield from schedule_source(authority, family, regime, unit)


def bootstrap_draw_rows(method, cells, *, source_count=8):
    """Yield canonical RNG bytes. The shared contract reader verifies every draw."""
    import numpy as np

    c.ensure(method in c.LEARNED and cells == sorted(set(cells)) and cells and 0 < source_count <= 8,
             "noncanonical bootstrap strata")
    rng = np.random.Generator(np.random.PCG64(
        np.random.SeedSequence([20261105, 41100, 0 if method == "learned_osqp" else 1])))
    for _ in range(10000):
        row = bytearray(rng.integers(0, 3, size=3).astype(np.uint8).tobytes())
        for _cell in cells:
            row.extend(rng.integers(0, source_count, size=source_count).astype(np.uint8).tobytes())
        yield bytes(row)


def write_bootstrap_draws(root, method, cells, *, source_count=8):
    """Store the exact canonical cross-stratum byte stream for the shared reader."""
    from hashlib import sha256

    c.ensure(method in c.LEARNED, "unknown bootstrap hypothesis")
    name = f"bootstrap-{method}.u8"
    target, pending = root / name, root / (name + ".pending")
    c.ensure(not target.exists(), "bootstrap draw file is already sealed")
    digest, length = sha256(), 0
    with pending.open("xb") as handle:
        for raw in bootstrap_draw_rows(method, cells, source_count=source_count):
            handle.write(raw)
            digest.update(raw)
            length += len(raw)
        handle.flush()
        os.fsync(handle.fileno())
    pending.rename(target)
    return {"method": method, "file": {"path": name, "format": "raw-uint8", "sha256": digest.hexdigest(),
                                        "byte_count": length}}


def missing_status(slot, reason):
    c.ensure(type(reason) is str and bool(reason), "missing status needs an explicit reason")
    phase_rows = [{"phase": phase, "rep": rep, "state": "missing", "reason": reason,
                   "receipt": None, "full_cost_ns": None}
                  for phase, _, count in PHASES for rep in range(count)] if slot.eligible else []
    return {"key": list(slot.key), "state": "missing" if slot.eligible else "incompatible",
            "reason": reason if slot.eligible else slot.reason, "trials": phase_rows}


def trial_receipt(*, slot, ordinal, request_sha, policy_sha, profile_sha, nonce, owned_pid, released_ns,
                  observed_ns, child):
    """Bind actual parent-observed timing and reject impossible or late success."""
    c.ensure(type(ordinal) is int and ordinal >= 0 and type(owned_pid) is int and owned_pid > 0
             and all(is_sha256(h) for h in (request_sha, policy_sha, profile_sha))
             and type(nonce) is str and re.fullmatch(r"[a-f0-9]{32}", nonce),
             "invalid owned trial identities")
    c.ensure(type(observed_ns) is int and type(released_ns) is int and observed_ns >= released_ns,
             "nonmonotonic parent observation")
    c.ensure(child["key"] == list(slot) and child["nonce"] == nonce and child["pid"] == owned_pid,
             "trial identity differs from owned worker")
    start, end = child["started_ns"], child["ended_ns"]
    c.ensure(type(start) is int and type(end) is int and released_ns <= start < end <= observed_ns
             and observed_ns - released_ns < TRIAL_NS, "late or impossible trial clock")
    raw = c.canonical_bytes(child)
    c.ensure(len(raw) <= MAX_RESULT_BYTES, "numeric result exceeds trial packet limit")
    return {"schema": "softqp.r4.heldout-trial-receipt/1", "key": list(slot), "ordinal": ordinal,
            "request_sha256": request_sha, "policy_sha256": policy_sha, "profile_sha256": profile_sha,
            "nonce": nonce, "owned_pid": owned_pid, "released_ns": released_ns,
            "observed_ns": observed_ns, "numeric_sha256": c.digest(raw), "full_cost_ns": end - start}


def validate_trial(receipt, child, expected_sha256):
    """Consumer needs independent receipt custody and actual numeric bytes."""
    c.ensure(c.digest(c.canonical_bytes(receipt)) == expected_sha256, "unrecognized trial custody digest")
    actual = trial_receipt(slot=receipt["key"], ordinal=receipt["ordinal"], request_sha=receipt["request_sha256"],
                           policy_sha=receipt["policy_sha256"], profile_sha=receipt["profile_sha256"],
                           nonce=receipt["nonce"], owned_pid=receipt["owned_pid"],
                           released_ns=receipt["released_ns"], observed_ns=receipt["observed_ns"], child=child)
    c.ensure(actual == receipt, "trial custody/timing changed")
    return actual["full_cost_ns"]


def await_owned_trial(child, result_path, **identity):
    """Observe under the whole-release timer. Stop only the owned worker on refusal."""
    from ..coupled_resources import process_memory

    released = identity["released_ns"]
    try:
        seconds = (released + TRIAL_NS - time.perf_counter_ns()) / 1e9
        c.ensure(seconds > 0, "trial deadline elapsed")
        observation = child.wait_file(result_path, seconds)
        observed = time.perf_counter_ns()
        c.ensure(identity["owned_pid"] in child._pids(), "trial worker lost actual job custody")
        c.ensure(child.peak_rss + process_memory(os.getpid())[1] < EVALUATION_RSS,
                 "combined trial RSS exceeded evaluation cap")
        return trial_receipt(observed_ns=observed, child=observation, **identity), observation
    except BaseException:
        child.close()
        raise


def write_json_lines(path: Path, rows, *, byte_limit=BAKE_BYTES):
    """Write one immutable bounded spool shard and return exact byte custody."""
    from hashlib import sha256

    count = size = 0
    digest = sha256()
    pending = path.with_name(path.name + ".pending")
    c.ensure(not path.exists(), "status shard is already sealed")
    with pending.open("xb") as target:
        for row in rows:
            raw = c.canonical_bytes(row)
            size += len(raw)
            c.ensure(size <= byte_limit, "benchmark shard exhausted its admitted byte budget")
            target.write(raw)
            digest.update(raw)
            count += 1
        target.flush()
        os.fsync(target.fileno())
    pending.rename(path)
    return {"path": path.name, "sha256": digest.hexdigest(), "byte_count": size, "rows": count}


def read_status_shard(path, expected_ref, slots, *, verified_trial=None):
    """Verify exact ordered status membership and phase roster from independent bytes."""
    from hashlib import sha256

    count = size = 0
    digest = sha256()
    totals = Counter()
    with path.open("rb") as source:
        for slot in slots:
            raw = source.readline(MAX_RESULT_BYTES + 1)
            c.ensure(len(raw) <= MAX_RESULT_BYTES and raw.endswith(b"\n"), "missing or oversize status row")
            row = c.strict_loads(raw)
            c.ensure(raw == c.canonical_bytes(row) and set(row) == {"key", "state", "reason", "trials"}
                     and row["key"] == list(slot.key), "noncanonical, missing or reordered status row")
            expected = [(phase, rep) for phase, _, n in PHASES for rep in range(n)] if slot.eligible else []
            c.ensure(all(type(v) is dict and set(v) == {"phase", "rep", "state", "reason", "receipt", "full_cost_ns"}
                         for v in row["trials"]), "unknown repetition fields")
            c.ensure([(v["phase"], v["rep"]) for v in row["trials"]] == expected, "trial keyset differs")
            if slot.eligible:
                allowed = {"accepted", "accuracy-rejected", "oracle-failed", "timeout", "missing", "failed"}
                c.ensure(row["state"] in allowed and all(v["state"] in allowed for v in row["trials"]),
                         "compatible status invented incompatibility")
                all_accepted = all(v["state"] == "accepted" for v in row["trials"])
                c.ensure((row["state"] == "accepted") == all_accepted
                         and ((row["reason"] is None) if all_accepted else type(row["reason"]) is str and row["reason"]),
                         "status does not reflect complete trial failures")
                for v in row["trials"]:
                    if v["state"] == "accepted":
                        c.ensure(v["reason"] is None and type(v["full_cost_ns"]) is int
                                 and 0 < v["full_cost_ns"] < TRIAL_NS and type(v["receipt"]) is dict,
                                 "accepted trial lacks observed cost or receipt")
                    else:
                        c.ensure(type(v["reason"]) is str and bool(v["reason"]), "failed trial lacks reason")
                    if v["receipt"] is None:
                        c.ensure(v["full_cost_ns"] is None, "unobserved trial invented full cost")
                    else:
                        c.ensure(verified_trial is not None and verified_trial(slot.key, v) == v["full_cost_ns"],
                                 "trial lacks independent numerical and custody verification")
            else:
                c.ensure(row["state"] == "incompatible" and row["reason"] == slot.reason, "wrong incompatibility")
            count += 1
            size += len(raw)
            digest.update(raw)
            totals[row["state"]] += 1
        c.ensure(not source.read(1), "extra status row")
    c.ensure(expected_ref == {"path": path.name, "sha256": digest.hexdigest(), "byte_count": size, "rows": count},
             "status shard differs from independent expected digest")
    return totals


def read_registered_launch(raw, custody):
    """Bind the committed dispatcher to an actual I1 launch before test data IO."""
    try:
        from softqp_runtime_custody import read_active_evaluation_policy
    except ImportError as error:
        raise c.ContractError("verified evaluation supervisor custody required") from error
    from .authority import load_i1_authority, require_i1
    from .generator import _dispatch_context

    request = c.strict_loads(raw)
    c.ensure(raw == c.canonical_bytes(request) and set(request) == {"schema", "operation", "projection_sha256"}
             and request["schema"] == "softqp.r4.heldout-request/1" and request["operation"] == OPERATION
             and is_sha256(request["projection_sha256"]),
             "invalid fixed evaluation request")
    request_digest = c.digest(raw)
    policy_raw = read_active_evaluation_policy(custody, operation=OPERATION, request_sha256=request_digest,
                                               source_file=Path(__file__).resolve())
    policy = c.strict_loads(policy_raw)
    fields = {"schema", "operation", "request_sha256", "profile_sha256", "admission", "scope", "output_root"}
    c.ensure(policy_raw == c.canonical_bytes(policy) and set(policy) == fields
             and policy["schema"] == "softqp.r4.heldout-policy/1" and policy["operation"] == OPERATION
             and policy["request_sha256"] == request_digest, "evaluation policy mismatch")
    trust, context, protocol = _dispatch_context(policy["admission"])
    authority = load_i1_authority(trust=trust, context=context, protocol_ref=protocol)
    require_i1(authority, OPERATION, context=context, protocol_ref=protocol)
    c.ensure(authority.runtime_profile_sha256 == policy["profile_sha256"],
             "I1-approved profile differs from exact held-out worker profile")
    c.ensure(read_active_evaluation_policy(custody, operation=OPERATION, request_sha256=request_digest,
                                            source_file=Path(__file__).resolve(),
                                            profile_sha256=authority.runtime_profile_sha256) == policy_raw,
             "evaluation supervisor policy changed during admission")
    return request, policy, authority, context, protocol


def drive_bake(ledger, broker, *, deadline_ns):
    """Drive the pinned schedule through the owning broker and durable frontier."""
    now = time.perf_counter_ns()
    c.ensure(type(deadline_ns) is int and now < deadline_ns <= now + BAKE_NS, "invalid held-out bake deadline")
    if ledger._state["active"] is not None:
        ledger.reconcile()
    while ledger.next_key is not None:
        broker.require_live()
        if time.perf_counter_ns() >= deadline_ns:
            return {"state": "incomplete", "next_ordinal": ledger._state["next"],
                    "frontier_sha256": ledger.expected, "reason": "24-hour-bake-deadline"}
        key, ordinal = ledger.next_key, ledger._state["next"]
        ledger.begin()
        try:
            terminal = broker.observe_trial(key, ordinal=ordinal, deadline_ns=deadline_ns)
        except TimeoutError:
            terminal = {"state": "timeout", "reason": "owned-trial-deadline", "receipt": None}
        broker.require_live()
        if time.perf_counter_ns() >= deadline_ns:
            terminal = {"state": "timeout", "reason": "24-hour-bake-deadline", "receipt": None}
        ledger.settle(terminal)
    return {"state": "complete", "next_ordinal": ledger._state["next"],
            "frontier_sha256": ledger.expected, "reason": None}


def validate_model_inventory(entries):
    """Require exactly six frozen dispositions with explicit independently pinned absence."""
    expected = [(method, seed) for method in sorted(c.LEARNED) for seed in c.SEEDS]
    c.ensure(type(entries) is list and len(entries) == len(expected), "incomplete frozen model roster")
    for entry, (method, seed) in zip(entries, expected):
        c.ensure(type(entry) is dict and set(entry) == {"method", "seed", "disposition", "checkpoint", "calibration", "reason"}
                 and (entry["method"], entry["seed"]) == (method, seed), "unexpected frozen model roster key")
        checkpoint, calibration = (entry[key] for key in ("checkpoint", "calibration"))
        if entry["disposition"] == "absent":
            c.ensure((checkpoint is None or calibration is None) and type(entry["reason"]) is str and entry["reason"],
                     "unexplained frozen model absence")
        else:
            c.ensure(entry["disposition"] == "admitted" and entry["reason"] is None
                     and checkpoint is not None and calibration is not None, "invalid frozen model disposition")
        for reference in (checkpoint, calibration):
            if reference is not None:
                c.ensure(type(reference) is dict and set(reference) == {"path", "sha256"}
                         and type(reference["path"]) is str and reference["path"] and is_sha256(reference["sha256"]),
                         "invalid frozen artifact ref")
    return {(entry["method"], entry["seed"]): entry for entry in entries}


class EvaluationJournal:
    """Durable append-only receipt chain with a separately held authority frontier.

    Acquire one external lease for the entire use. An issued attempt is never
    executed again. Recovery can append the exactly staged terminal bytes or
    record an interrupted attempt if no terminal bytes were independently pinned.
    """

    FORMAT = "softqp.r4.heldout-frontier/1"
    EVENT = "softqp.r4.heldout-journal-event/1"

    def __init__(self, journal, frontier, *, expected_frontier_sha256, plan_sha256, schedule):
        self.journal = Path(journal)
        self.frontier = Path(frontier)
        self.stage = self.journal.with_name(self.journal.name + ".terminal")
        self.lease = self.frontier.with_name(self.frontier.name + ".lease")
        self.plan_sha256 = plan_sha256
        self.expected = expected_frontier_sha256
        self.schedule = iter(schedule)
        self._lease = None
        self._state = None
        self._next = None

    @classmethod
    def initial_frontier(cls, *, plan_sha256):
        c.ensure(is_sha256(plan_sha256), "invalid independent evaluation plan digest")
        return c.canonical_bytes({"schema": cls.FORMAT, "plan_sha256": plan_sha256, "next": 0, "bytes": 0,
                                  "last_sha256": None, "active": None, "staged_sha256": None})

    def __enter__(self):
        import msvcrt

        c.ensure(self.journal.parent.resolve(strict=True) != self.frontier.parent.resolve(strict=True)
                 and all(path.is_absolute() and path.resolve() == path for path in (self.journal, self.frontier)),
                 "journal and authority frontier must have separate exact external roots")
        self._lease = self.lease.open("a+b")
        try:
            self._lease.seek(0)
            msvcrt.locking(self._lease.fileno(), msvcrt.LK_NBLCK, 1)
            raw = self.frontier.read_bytes()
            c.ensure(len(raw) <= 8192 and c.digest(raw) == self.expected, "evaluation frontier changed")
            state = c.strict_loads(raw)
            c.ensure(raw == c.canonical_bytes(state) and set(state) ==
                     {"schema", "plan_sha256", "next", "bytes", "last_sha256", "active", "staged_sha256"}
                     and state["schema"] == self.FORMAT and state["plan_sha256"] == self.plan_sha256
                     and type(state["next"]) is int and type(state["bytes"]) is int
                     and state["next"] >= 0 and 0 <= state["bytes"] <= BAKE_BYTES, "malformed evaluation frontier")
            if not self.journal.exists():
                c.ensure(state["next"] == state["bytes"] == 0, "missing committed execution journal")
                self.journal.touch(exist_ok=False)
            self._state = state
            self._verify_prefix()
        except BaseException:
            self._lease.close()
            self._lease = None
            raise
        return self

    def __exit__(self, *exc):
        if self._lease is not None:
            self._lease.close()
            self._lease = None

    def _verify_prefix(self):
        head = None
        state = self._state
        with self.journal.open("rb") as source:
            for ordinal in range(state["next"]):
                key = next(self.schedule, None)
                raw = source.readline(MAX_RESULT_BYTES + 1)
                _read_journal_event(raw, schema=self.EVENT, key=key, ordinal=ordinal, previous=head)
                head = c.digest(raw)
            c.ensure(source.tell() == state["bytes"] and head == state["last_sha256"],
                     "evaluation committed prefix differs from independent frontier")
            tail = source.read(MAX_RESULT_BYTES + 1)
            if tail:
                c.ensure(is_sha256(state["staged_sha256"]) and self.stage.is_file(),
                         "unrecognized bytes beyond evaluation journal frontier")
                staged = self.stage.read_bytes()
                c.ensure(c.digest(staged) == state["staged_sha256"] and staged.startswith(tail),
                         "evaluation journal tail differs from independently staged bytes")
        self._next = next(self.schedule, None)
        if state["active"] is not None:
            c.ensure(self._next is not None and state["active"] == list(self._next),
                     "independent frontier has wrong active trial")
        else:
            c.ensure(state["staged_sha256"] is None, "staged receipt lacked active trial")
            if self.stage.exists():
                c.ensure(self.stage.stat().st_size <= MAX_RESULT_BYTES and
                         c.digest(self.stage.read_bytes()) == state["last_sha256"],
                         "unexpected orphan staged evaluation terminal")
                self.stage.unlink()

    def _replace(self, **changes):
        c.ensure(self._lease is not None and c.digest(self.frontier.read_bytes()) == self.expected,
                 "live evaluation frontier custody lost")
        state = {**self._state, **changes}
        raw = c.canonical_bytes(state)
        pending = self.frontier.with_name(self.frontier.name + ".pending")
        _write_exclusive(pending, raw)
        os.replace(pending, self.frontier)
        self._state, self.expected = state, c.digest(raw)
        return self.expected

    @property
    def next_key(self):
        return self._next

    def begin(self):
        c.ensure(self._state["active"] is None and self._next is not None and not self.stage.exists(),
                 "evaluation attempt already issued or schedule exhausted")
        return self._replace(active=list(self._next))

    def settle(self, terminal):
        c.ensure(self._state["active"] is not None and self._state["staged_sha256"] is None,
                 "no unsettled active evaluation attempt")
        event = {"schema": self.EVENT, "key": list(self._next), "ordinal": self._state["next"],
                 "previous_sha256": self._state["last_sha256"], "terminal": terminal}
        raw = c.canonical_bytes(event)
        _read_journal_event(raw, schema=self.EVENT, key=self._next, ordinal=self._state["next"],
                            previous=self._state["last_sha256"])
        _write_exclusive(self.stage, raw)
        self._replace(staged_sha256=c.digest(raw))
        return self.reconcile()

    def reconcile(self):
        c.ensure(self._state["active"] is not None, "no active evaluation attempt to reconcile")
        if self._state["staged_sha256"] is None:
            c.ensure(not self.stage.exists(), "unsealed staged terminal requires external disposition")
            return self.settle({"state": "failed", "reason": "interrupted-owned-trial", "receipt": None})
        raw = self.stage.read_bytes()
        c.ensure(len(raw) <= MAX_RESULT_BYTES and c.digest(raw) == self._state["staged_sha256"],
                 "staged evaluation terminal differs from independent frontier")
        _read_journal_event(raw, schema=self.EVENT, key=self._next, ordinal=self._state["next"],
                            previous=self._state["last_sha256"])
        start, end = self._state["bytes"], self._state["bytes"] + len(raw)
        c.ensure(end <= BAKE_BYTES, "evaluation journal exceeds byte budget")
        with self.journal.open("r+b") as handle:
            handle.seek(start)
            tail = handle.read(MAX_RESULT_BYTES + 1)
            c.ensure(raw.startswith(tail), "evaluation journal has different staged suffix")
            if len(tail) < len(raw):
                handle.write(raw[len(tail):])
                handle.flush()
                os.fsync(handle.fileno())
        head = self._replace(next=self._state["next"] + 1, bytes=end, last_sha256=c.digest(raw),
                             active=None, staged_sha256=None)
        self.stage.unlink()
        self._next = next(self.schedule, None)
        return head


def _write_exclusive(path, raw):
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _read_journal_event(raw, *, schema, key, ordinal, previous):
    c.ensure(bool(raw) and len(raw) <= MAX_RESULT_BYTES and key is not None, "truncated evaluation journal")
    event = c.strict_loads(raw)
    c.ensure(raw == c.canonical_bytes(event) and set(event) == {"schema", "key", "ordinal", "previous_sha256", "terminal"}
             and event["schema"] == schema and event["key"] == list(key)
             and event["ordinal"] == ordinal and event["previous_sha256"] == previous,
             "evaluation journal event breaks ordered receipt chain")
    terminal = event["terminal"]
    c.ensure(type(terminal) is dict and set(terminal) == {"state", "reason", "receipt"}
             and terminal["state"] in {"accepted", "accuracy-rejected", "oracle-failed", "timeout", "missing", "failed"},
             "invalid evaluation trial terminal")
    if terminal["state"] == "accepted":
        c.ensure(terminal["reason"] is None and type(terminal["receipt"]) is dict,
                 "accepted terminal lacks receipt")
    else:
        c.ensure(type(terminal["reason"]) is str and bool(terminal["reason"]), "terminal failure lacks reason")
    if terminal["receipt"] is not None:
        receipt = terminal["receipt"]
        c.ensure(type(receipt) is dict and receipt.get("key") == event["key"]
                 and receipt.get("ordinal") == ordinal and type(receipt.get("full_cost_ns")) is int
                 and 0 < receipt["full_cost_ns"] < TRIAL_NS, "terminal carries unrelated trial receipt")
    return event


def project_status_journal(journal, frontier, *, expected_frontier_sha256, authority, plan_sha256,
                           temporary_index, output, missing_reason=None, byte_limit=BAKE_BYTES,
                           fixture_frames=None):
    """Project a sealed receipt chain to complete ordered statuses using bounded disk indexing."""
    import sqlite3

    c.ensure(type(byte_limit) is int and 0 < byte_limit <= BAKE_BYTES, "invalid candidate projection byte limit")
    temporary_index = Path(temporary_index)
    c.ensure(not temporary_index.exists(), "evaluation index already exists")
    if fixture_frames is not None:
        c.ensure(type(fixture_frames) is frozenset and 0 < len(fixture_frames) < 2208,
                 "excluded evaluation projection domain differs")

    def trial_keys():
        return (key for key in execution_schedule(authority)
                if fixture_frames is None or key[2:6] in fixture_frames)

    # Create the activity index only after the separately pinned frontier and
    # key sequence have independently admitted the exact complete journal prefix.
    with EvaluationJournal(journal, frontier, expected_frontier_sha256=expected_frontier_sha256,
                           plan_sha256=plan_sha256, schedule=trial_keys()) as ledger:
        state = ledger._state
        c.ensure(state["active"] is None and (ledger.next_key is None or
                 type(missing_reason) is str and bool(missing_reason)), "unsealed or incomplete evaluation replay")
        conn = sqlite3.connect(temporary_index)
        try:
            conn.execute("PRAGMA cache_size=-1024")
            conn.execute("PRAGMA journal_mode=OFF")  # Reconstructable, excluded projection index.
            page = conn.execute("PRAGMA page_size").fetchone()[0]
            allowance = byte_limit - state["bytes"]
            c.ensure(allowance >= page * 4, "no budget for evaluation projection index")
            conn.execute(f"PRAGMA max_page_count={allowance // page}")
            conn.execute("CREATE TABLE trials (k BLOB PRIMARY KEY, row BLOB NOT NULL) WITHOUT ROWID")
            with ledger.journal.open("rb") as source:
                previous = None
                for ordinal, key in enumerate(trial_keys()):
                    if ordinal == state["next"]:
                        break
                    raw = source.readline(MAX_RESULT_BYTES + 1)
                    event = _read_journal_event(raw, schema=ledger.EVENT, key=key, ordinal=ordinal, previous=previous)
                    conn.execute("INSERT INTO trials VALUES(?, ?)",
                                 (c.canonical_bytes(list(key)), c.canonical_bytes(event["terminal"])))
                    previous = c.digest(raw)
                c.ensure(source.tell() == state["bytes"] and previous == state["last_sha256"],
                         "evaluation journal changed during projection")
            conn.commit()

            def statuses():
                for slot in status_slots(authority):
                    if fixture_frames is not None and slot.key[2:6] not in fixture_frames:
                        continue
                    if not slot.eligible:
                        yield missing_status(slot, "incompatible")
                        continue
                    rows = []
                    for phase, _, count in PHASES:
                        for rep in range(count):
                            key = c.canonical_bytes([*slot.key, phase, rep])
                            found = conn.execute("SELECT row FROM trials WHERE k=?", (key,)).fetchone()
                            if found is None:
                                c.ensure(missing_reason is not None, "sealed evaluation omitted a compatible trial")
                                trial = {"state": "missing", "reason": missing_reason, "receipt": None}
                            else:
                                trial = c.strict_loads(found[0])
                            receipt = trial["receipt"]
                            rows.append({"phase": phase, "rep": rep, **trial,
                                         "full_cost_ns": receipt["full_cost_ns"] if receipt is not None else None})
                    failure = next((trial for trial in rows if trial["state"] != "accepted"), None)
                    yield {"key": list(slot.key), "state": failure["state"] if failure else "accepted",
                           "reason": failure["reason"] if failure else None, "trials": rows}

            budget = allowance - temporary_index.stat().st_size
            c.ensure(budget > 0, "no byte budget for projected status output")
            return write_json_lines(output, statuses(), byte_limit=budget)
        finally:
            conn.close()


class MatchedTrajectoryTotals:
    """Compact accumulator after independent status-shard validation."""

    def __init__(self):
        self._medians = {}
        self._failed = Counter()

    def add(self, row):
        method, *coordinates = row["key"]
        hypotheses = {"learned_osqp": "learned_osqp", "learned_daqp": "learned_daqp",
                      "cold_osqp": "learned_osqp", "cold_daqp": "learned_daqp"}
        if method not in hypotheses or row["state"] == "incompatible":
            return
        key = (method, *coordinates)
        c.ensure(key not in self._medians, "duplicate matched timing status")
        if row["state"] != "accepted":
            self._failed[hypotheses[method]] += 1
            self._medians[key] = None
            return
        times = [trial["full_cost_ns"] for trial in row["trials"] if trial["phase"] == "measured"]
        c.ensure(len(times) == 5 and all(type(v) is int and 0 < v < TRIAL_NS for v in times),
                 "invalid measured full-cost roster")
        self._medians[key] = sorted(times)[2]

    def projection(self, method, *, diagnostics_complete):
        cold = {"learned_osqp": "cold_osqp", "learned_daqp": "cold_daqp"}[method]
        families = sorted({k[1:5] for k in self._medians if k[0] == method})
        if self._failed[method] or not diagnostics_complete:
            return {"state": "undefined", "failed_statuses": self._failed[method], "totals": []}
        totals = []
        for seed, family, regime, unit in families:
            frames = range(32 if family == "N12" else 1)
            learned = [self._medians.get((method, seed, family, regime, unit, t)) for t in frames]
            match = [self._medians.get((cold, 0, family, regime, unit, t)) for t in frames]
            c.ensure(all(v is not None for v in learned + match), "incomplete matched trajectory frame keys")
            totals.append({"method": method, "seed": seed, "family": family, "regime": regime,
                           "source_index": unit, "learned_ns": sum(learned), "cold_ns": sum(match),
                           "reduction": c.trajectory_reduction(match, learned)})
        return {"state": "defined" if totals else "undefined", "failed_statuses": 0, "totals": totals}
