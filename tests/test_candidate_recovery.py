"""Excluded adversaries for the read-only candidate recovery boundary."""

import subprocess
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

from pipeline.learned_comparison import authority as a
from pipeline.learned_comparison import candidate_recovery as recovery
from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import evaluation as e


def test_recovery_preserves_original_staged_but_unobserved_result(tmp_path):
    plan = "0" * 64
    basis = tmp_path / "basis"
    basis.mkdir()
    original = tmp_path / "original"
    original.mkdir()
    journal = original / "candidate-journal.ndjson"
    frontier = basis / "frontier.json"
    schedule = tuple(("lifted", 0, "N01", 0, 0, 0, "measured", i) for i in range(3))
    schedule_bytes = b"".join(c.canonical_bytes(list(row)) for row in schedule)
    (basis / "schedule.ndjson").write_bytes(schedule_bytes)
    (basis / "timer.json").write_bytes(b"same observed timer")
    initial = e.EvaluationJournal.initial_frontier(plan_sha256=plan)
    frontier.write_bytes(initial)
    with e.EvaluationJournal(journal, frontier, expected_frontier_sha256=c.digest(initial),
                             plan_sha256=plan, schedule=schedule) as owner:
        owner.begin()
        owner.settle({"state": "oracle-failed", "reason": "old observed failure", "receipt": None})
        owner.begin()
        staged = c.canonical_bytes({"schema": owner.EVENT, "key": list(schedule[1]), "ordinal": 1,
                                    "previous_sha256": owner._state["last_sha256"],
                                    "terminal": {"state": "failed", "reason": "uncommitted staged observation",
                                                 "receipt": None}})
        owner.stage.write_bytes(staged)
        owner._replace(staged_sha256=c.digest(staged))
    old = {name: name.read_bytes() for name in (journal, frontier, owner.stage)}
    bake = {"frontier_root": str(basis), "output_root": str(original),
            "schedule_sha256": c.digest(schedule_bytes), "timer_sha256": c.digest(b"same observed timer")}
    policy = {"frontier_sha256": c.digest(old[frontier]), "journal_sha256": c.digest(old[journal]),
              "staged_sha256": c.digest(staged)}
    staged_copy = tmp_path / "recovery"
    staged_copy.mkdir()
    _, projected, _, committed, interrupted = recovery._shadow(
        staged_copy, bake, policy, schedule, plan, lambda: None, budget=2**30,
    )
    assert (committed, interrupted) == (1, 1)
    rows = [c.strict_loads(row) for row in projected.read_bytes().splitlines(keepends=True)]
    assert rows[0]["terminal"]["reason"] == "old observed failure"
    assert rows[1]["terminal"] == {"state": "failed", "reason": "interrupted-owned-trial", "receipt": None}
    assert all(path.read_bytes() == raw for path, raw in old.items())
    owner.stage.write_bytes(staged + b"unapproved suffix")
    with pytest.raises(c.ContractError, match="original recovery bytes differ"):
        recovery._require_inputs(bake, policy, lambda: None)


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL).strip()


def _replacement(root, path):
    root.mkdir()
    _git(root, "init")
    item = root / path
    item.parent.mkdir(parents=True, exist_ok=True)
    item.write_bytes(b"original\n")
    _git(root, "add", path)
    _git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "original")
    original = _git(root, "rev-parse", "HEAD").decode()
    item.write_bytes(b"replacement\n")
    _git(root, "add", path)
    _git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "alternate")
    replacement = _git(root, "rev-parse", "HEAD").decode()
    _git(root, "checkout", "--detach", original)
    _git(root, "replace", original, replacement)
    assert _git(root, "show", f"{original}:{path}") == b"replacement"
    return original, item


def test_historical_product_and_engine_ignore_real_replacement_commits(tmp_path):
    product, engine = tmp_path / "product", tmp_path / "engine"
    original, generator = _replacement(product, a._GENERATOR)
    engine_original, _ = _replacement(engine, a._ENGINE_CHECKER)
    assert a._head(product) == original and a._head(engine) == engine_original
    assert a._literal_git_file(engine, "HEAD", a._ENGINE_CHECKER).stdout == b"original\n"
    generator.write_bytes(b"replacement\n")
    trust = SimpleNamespace(product_root=product, engine_root=engine, fixture_only=False)
    lock = {"product_commit": original, "engine_commit": engine_original,
            "files": {a._GENERATOR: c.digest(generator.read_bytes()),
                      **{path: "0" * 64 for path in a._REQUIRED_FILES if path != a._GENERATOR}}}
    with pytest.raises(c.ContractError, match="reviewed Git object"):
        a._sources(lock, trust, verify_committed=True)


def test_historical_call_has_no_public_issue_route():
    with pytest.raises((ImportError, c.ContractError)):
        a._verify_historical_recovery(None, None, None, object(), request_sha256="a" * 64)
    with pytest.raises(TypeError):
        a.load_i1_authority(trust=None, context=None, protocol_ref=None, held_recovery_profile="a" * 64)


@pytest.mark.parametrize("reason", ["bake-deadline", "evaluation-rss-cap"])
def test_fixed_recovery_terminal_rejects_completed_and_substituted_scope(tmp_path, reason):
    runtime = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                                 "environments/method-extension-scientific/evaluation_runtime.py"))
    bake = dict(request_sha256="a" * 64, policy_sha256="b" * 64, profile_sha256="c" * 64,
                timer_sha256="d" * 64)
    policy = dict(original_bake_sha256="e" * 64, terminal_root=str(tmp_path))
    timer = dict(boot_id="excluded-boot", deadline_ns=100)
    source = "f" * 64
    terminal = dict(
        status="refused", cleanup="owned-process-tree-closed", profile_sha256=bake["profile_sha256"],
        source_manifest_sha256=source, i1_issued=False, owned_pids=[100],
        command=["python", "--candidate", "--run", str(tmp_path),
                 "--expected-request-sha256", bake["request_sha256"],
                 "--expected-policy-sha256", bake["policy_sha256"],
                 "--expected-bake-sha256", policy["original_bake_sha256"]],
        candidate_terminal=dict(reason=reason, timer_sha256=bake["timer_sha256"],
                                boot_id=timer["boot_id"], observed_ns=100),
    )

    def read(doc):
        return runtime["terminal_recovery_scope"](doc, bake=bake, policy=policy, source_manifest=source, timer=timer)

    assert read(terminal) == reason
    with pytest.raises(ValueError, match="terminal Job"):
        read({**terminal, "status": "registered-dispatch-observed"})
    with pytest.raises(ValueError, match="terminal Job"):
        read({**terminal, "cleanup": "live"})
    with pytest.raises(ValueError, match="terminal clock"):
        read({**terminal, "candidate_terminal": {**terminal["candidate_terminal"], "boot_id": "other-boot"}})
