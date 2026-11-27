"""Project a failed bake from sealed evidence without starting a candidate."""

from hashlib import sha256
from pathlib import Path
import secrets

from . import candidate_startup as startup
from . import contracts as c
from . import evaluation as e
from . import evaluation_dispatch as dispatch
from . import heldout_inputs as heldout
from . import phase_inputs as phase

RECOVERY_BYTES = 2**30


def _sha_file(path, *, limit=e.BAKE_BYTES, check_live=lambda: None):
    if not path.exists():
        return c.digest(b"")
    c.ensure(phase._path_stat(path).st_size <= limit, "recovery input exceeds bounded bytes")
    digest = sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(2**20), b""):
            check_live()
            digest.update(block)
    return digest.hexdigest()


def _require_inputs(bake, policy, check_live):
    frontier = Path(bake["frontier_root"]) / "frontier.json"
    journal = Path(bake["output_root"]) / "candidate-journal.ndjson"
    staged = journal.with_name(journal.name + ".terminal")
    expected = [(frontier, policy["frontier_sha256"], 8192), (journal, policy["journal_sha256"], e.BAKE_BYTES),
                (frontier.with_name("schedule.ndjson"), bake["schedule_sha256"], 32 * 2**20),
                (frontier.with_name("timer.json"), bake["timer_sha256"], 8192)]
    if policy["staged_sha256"] is not None:
        expected.append((staged, policy["staged_sha256"], e.MAX_RESULT_BYTES))
    c.ensure(staged.exists() == (policy["staged_sha256"] is not None), "unbound original staged terminal")
    for file, digest, maximum in expected:
        c.ensure(_sha_file(file, limit=maximum, check_live=check_live) == digest,
                 "independent original recovery bytes differ")
    return frontier, journal, staged


def _shadow(stage, bake, policy, schedule, plan_sha, live, *, budget):
    original, journal, staged = _require_inputs(bake, policy, live)
    raw = original.read_bytes()
    state = c.strict_loads(raw)
    c.ensure(
        raw == c.canonical_bytes(state)
        and set(state) == {"schema", "plan_sha256", "next", "bytes", "last_sha256", "active", "staged_sha256"}
        and state["schema"] == e.EvaluationJournal.FORMAT and state["plan_sha256"] == plan_sha
        and type(state["next"]) is int and 0 <= state["next"] <= len(schedule)
        and type(state["bytes"]) is int and 0 <= state["bytes"] < budget - 2**20,
        "candidate recovery original frontier differs",
    )
    active = state["active"] is not None
    if active:
        c.ensure(state["next"] < len(schedule) and state["active"] == list(schedule[state["next"]]),
                 "candidate recovery active key differs")
    c.ensure(state["staged_sha256"] is None or (active and state["staged_sha256"] == policy["staged_sha256"]),
             "candidate recovery staged outcome digest differs")
    if staged.exists():
        c.ensure(active, "unrelated original staged payload")
        e._read_journal_event(staged.read_bytes(), schema=e.EvaluationJournal.EVENT,
                              key=schedule[state["next"]], ordinal=state["next"], previous=state["last_sha256"])
    for name in ("authority", "journal"):
        (stage / name).mkdir()
    copy = stage / "journal" / journal.name
    shadow = stage / "authority" / original.name
    left = state["bytes"]
    with copy.open("xb") as target:
        if journal.exists():
            with journal.open("rb") as source:
                while left:
                    live()
                    block = source.read(min(2**20, left))
                    c.ensure(bool(block), "short original recovery journal prefix")
                    target.write(block)
                    left -= len(block)
        c.ensure(left == 0, "missing original recovery journal prefix")
    # Only the diagnostic copy can record an unobserved interruption.
    shadow_bytes = c.canonical_bytes({**state, "staged_sha256": None})
    e._write_exclusive(shadow, shadow_bytes)
    with e.EvaluationJournal(copy, shadow, expected_frontier_sha256=c.digest(shadow_bytes),
                             plan_sha256=plan_sha, schedule=schedule) as ledger:
        if active:
            ledger.reconcile()
        return shadow, copy, ledger.expected, state["next"], int(active)


def project(raw, custody, *, bake, original_policy, policy, expected_recovery, termination, require_live):
    """Fixed read-only product callback. No benchmark launch capability is present."""
    proof = heldout.admit_candidate_inputs(raw, custody, read_only=True)
    view = heldout.candidate_view(proof)
    ids = view.identities()
    for name in ("request_sha256", "policy_sha256", "profile_sha256", "scope_sha256", "roster_sha256",
                 "test_sha256", "native_sha256", "proof_sha256"):
        c.ensure(bake[name] == ids[name], "candidate recovery scope differs")
    authority, frames = view.authority(), view.frame_index()
    schedule = dispatch._schedule(authority, view)
    digest = sha256()
    for key in schedule:
        digest.update(c.canonical_bytes(list(key)))
    cohorts = startup.cohort_plan(authority, schedule)
    c.ensure(digest.hexdigest() == bake["schedule_sha256"]
             and c.digest(c.canonical_bytes(cohorts)) == bake["cohort_sha256"],
             "candidate recovery schedule or cohorts differ")
    output = Path(policy["output_root"])
    output.mkdir(exist_ok=True)
    output = phase._exact_directory(output)
    c.ensure(not (output / "recovery").exists(), "candidate recovery already published")
    budget = RECOVERY_BYTES - dispatch._output_bytes(output)
    stage = output / (".recovery-stage-" + secrets.token_hex(12))
    stage.mkdir()
    plan_sha = c.digest(c.canonical_bytes({name: bake[name] for name in ("schedule_sha256", "timer_sha256")}))
    shadow, journal, head, committed, interrupted = _shadow(
        stage, bake, policy, schedule, plan_sha, require_live, budget=budget,
    )
    fixture_frames = frozenset(frames) if ids["fixture_only"] else None
    statuses = e.project_status_journal(
        journal, shadow, expected_frontier_sha256=head, authority=authority, plan_sha256=plan_sha,
        temporary_index=stage / "index.db", output=stage / "statuses.ndjson",
        missing_reason=termination, byte_limit=budget - 2**20, fixture_frames=fixture_frames,
    )
    timings = startup.TimingCohorts(cohorts)
    original_output = Path(bake["output_root"])
    startups = dispatch._observed_startups(view, original_output)
    receipt_validator = dispatch._artifact_validator("candidate-trial-receipt").validate

    def check_numeric(slot, trial):
        require_live()
        return dispatch._numeric_receipt(proof, view, original_output, slot, trial, frames=frames,
                                         timing=timings, startups=startups, validate_receipt=receipt_validator)

    counts = e.read_status_shard(stage / statuses["path"], statuses,
                                 (slot for slot in e.status_slots(authority)
                                  if fixture_frames is None or slot.key[2:6] in fixture_frames),
                                 verified_trial=check_numeric)
    # These are diagnostic counts. An unobserved suffix cannot be promoted.
    _require_inputs(bake, policy, require_live)
    original = c.strict_loads(original_policy)
    scope, inputs = original["scope"], original["inputs"]
    expected = [
        (Path(scope["test_root"]) / "test-inputs.json", ids["test_sha256"]),
        (Path(scope["proof_root"]) / "native-run.json", ids["native_sha256"]),
        (Path(scope["proof_root"]) / "proof.json", ids["proof_sha256"]),
        (Path(inputs["roster_root"]) / "roster.json", ids["roster_sha256"]),
        *((c.safe_path(Path(inputs["metadata"]), inputs[key]["path"], must_exist=True), inputs[key]["sha256"])
          for key in ("p0", "p1")),
    ]
    for path, pinned in expected:
        c.ensure(_sha_file(path, check_live=require_live) == pinned, "read-only held-out evidence changed")
    _, diagnostics = dispatch._diagnostics(
        bake, authority, stage, frontier_root=Path(bake["frontier_root"]), output=output,
        byte_limit=RECOVERY_BYTES,
    )
    report = {
        "schema": "softqp.r4.candidate-recovery-export/1",
        **ids,
        **{name: policy[name] for name in ("original_bake_sha256", "frontier_sha256",
                                          "journal_sha256", "terminal_sha256")},
        **{name: bake[name] for name in ("timer_sha256", "schedule_sha256", "cohort_sha256")},
        "recovery_sha256": expected_recovery,
        "termination": termination,
        "committed_trials": committed,
        "interrupted_trials": interrupted,
        "missing_trials": len(schedule) - committed - interrupted,
        "statuses": statuses,
        "diagnostics": diagnostics,
        "counts": dict(counts),
        "scientifically_qualified": False,
    }
    content = c.canonical_bytes(report)
    require_live()
    c.ensure(dispatch._output_bytes(output) + len(content) <= RECOVERY_BYTES, "candidate recovery output cap")
    e._write_exclusive(stage / "recovery.json", content)
    c.ensure((stage / "recovery.json").read_bytes() == content, "candidate recovery manifest changed")
    require_live()
    return {"stage": stage.name, "sha256": c.digest(content)}
