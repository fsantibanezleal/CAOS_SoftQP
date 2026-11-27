"""Excluded checks for the external candidate-trial clock and stage pins."""

from pathlib import Path
import json
import os
import runpy
import shutil
import subprocess
import sys
import time

import pytest


def helper():
    path = (
        Path(__file__).resolve().parents[1] / "environments/method-extension-scientific/evaluation_runtime.py"
    )
    return runpy.run_path(str(path))


def test_external_clock_precedes_getter_and_seals_full_elapsed(tmp_path):
    api = helper()
    ticks = [100]
    key = ("lifted", 0, "N01", 0, 0, 0, "measured", 0)
    watchdog = api["TrialWatchdog"](
        tmp_path, first=0, finish=1, schedule=[key], deadline_ns=10**12, now=lambda: ticks[0]
    )
    ready = dict(key=list(key), ordinal=0, owner=91, nonce="0" * 32)

    def marker(kind):
        return api["marker_path"](tmp_path, 0, kind)

    api["write_marker"](marker("ready"), ready)
    watchdog.step(owned_pids={91}, combined_peak_rss=0)
    release = api["read_marker"](marker("release"))
    assert release["released_ns"] == 100
    ticks[0] = 100 + 3 * 10**9
    api["write_marker"](marker("observed"), dict(release, result_sha256="a" * 64))
    watchdog.step(owned_pids={91}, combined_peak_rss=0)
    assert api["read_marker"](marker("closed"))["observed_ns"] - release["released_ns"] == 3 * 10**9
    watchdog.require_complete()


@pytest.mark.parametrize("attack", ["late-getter", "foreign-owner", "wrong-key", "rss"])
def test_external_watchdog_refuses_invalid_observation_before_completion(tmp_path, attack):
    api = helper()
    ticks = [100]
    key = ("lifted", 0, "N01", 0, 0, 0, "warmup", 0)
    watchdog = api["TrialWatchdog"](
        tmp_path, first=0, finish=1, schedule=[key], deadline_ns=10**12, now=lambda: ticks[0]
    )

    def marker(kind):
        return api["marker_path"](tmp_path, 0, kind)

    ready = dict(key=list(key), ordinal=0, owner=91, nonce="a" * 32)
    if attack == "wrong-key":
        ready["key"][0] = "flex"
    api["write_marker"](marker("ready"), ready)
    if attack == "late-getter":
        watchdog.step(owned_pids={91}, combined_peak_rss=0)
        ticks[0] += api["TRIAL_NS"]
    with pytest.raises((ValueError, TimeoutError)):
        watchdog.step(
            owned_pids={7} if attack == "foreign-owner" else {91},
            combined_peak_rss=api["RSS_LIMIT"] if attack == "rss" else 0,
        )
    assert not marker("closed").exists()


def test_candidate_views_and_model_bindings_require_live_exact_proof():
    from pipeline.learned_comparison import contracts as c
    from pipeline.learned_comparison import heldout_inputs as h

    with pytest.raises(c.ContractError, match="unissued"):
        h.candidate_view(h.TestNativeProof())
    with pytest.raises(c.ContractError, match="unissued"):
        h.CandidateView().model_binding("learned_osqp", 41001)


@pytest.mark.skipif(os.name != "nt", reason="requires the Windows sharing transition")
def test_atomic_candidate_packet_retry_keeps_deadline(tmp_path, monkeypatch):
    from pipeline.learned_comparison import evaluation_dispatch as dispatch

    path = tmp_path / "closed.json"
    path.write_bytes(b'{"checked":true}\n')
    native_open = Path.open
    attempts = 0

    def busy(candidate, *args, **kwargs):
        nonlocal attempts
        if candidate == path:
            attempts += 1
            if attempts == 1:
                raise PermissionError(13, "published filename is still shared")
        return native_open(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "open", busy)
    assert dispatch._read_packet(path, deadline=time.perf_counter_ns() + 10**9) == {"checked": True}
    assert attempts == 2
    with pytest.raises(TimeoutError):
        dispatch._read_packet(path, deadline=time.perf_counter_ns())
    assert attempts == 2


@pytest.mark.skipif(os.name != "nt", reason="requires actual Windows Job ownership")
def test_watchdog_timeout_closes_owned_blocked_getter(tmp_path):
    from pipeline.learned_comparison.native_labels import _OwnedWorker

    api = helper()
    root = tmp_path / "markers"
    root.mkdir()
    key = ("lifted", 0, "N01", 0, 0, 0, "warmup", 0)
    ticks = [100]
    watchdog = api["TrialWatchdog"](
        root, first=0, finish=1, schedule=[key], deadline_ns=10**12, now=lambda: ticks[0]
    )
    executable = Path(sys._base_executable)
    owner = _OwnedWorker(
        tmp_path / "worker",
        [str(executable), "-I", "-S", "-B", "-c", "import time; time.sleep(60)"],
        executable,
        nonce="a" * 32,
    )
    try:
        pid = owner.process.pid
        assert pid in owner._pids()
        api["write_marker"](
            api["marker_path"](root, 0, "ready"),
            dict(key=list(key), ordinal=0, owner=pid, nonce="a" * 32),
        )
        watchdog.step(owned_pids=owner._pids(), combined_peak_rss=0)
        ticks[0] += api["TRIAL_NS"]
        with pytest.raises(TimeoutError, match="whole-trial deadline"):
            watchdog.step(owned_pids=owner._pids(), combined_peak_rss=0)
        assert owner.process.poll() is None
    finally:
        process = owner.process
        owner.close()
    assert process.wait(timeout=5) != 0
    assert not api["marker_path"](root, 0, "closed").exists()


def test_candidate_scope_refuses_alternate_t_and_protected_alias(tmp_path):
    api = helper()
    request = dict(stage="candidate", operation="evaluate-heldout", roster_sha256="a" * 64)
    scope = {key: str(tmp_path / key) for key in ("test_root", "native_root", "proof_root", "frontier_root")}
    seals = dict(test_sha256="b" * 64, native_sha256="c" * 64, proof_sha256="d" * 64)
    policy = dict(stage="candidate", operation=request["operation"], scope=scope, expected=seals)
    request_raw, policy_raw = map(api["encode"], (request, policy))
    bake = dict(
        schema="softqp.r4.candidate-bake/1",
        request_sha256=api["digest"](request_raw),
        policy_sha256=api["digest"](policy_raw),
        profile_sha256="e" * 64,
        scope_sha256=api["digest"](api["encode"](scope)),
        roster_sha256=request["roster_sha256"],
        schedule_sha256="f" * 64,
        cohort_sha256="a" * 64,
        frontier_sha256="0" * 64,
        timer_sha256="1" * 64,
        output_root=str(tmp_path / "output"),
        frontier_root=str(tmp_path / "candidate-lease"),
        diagnostics=[],
        committed_input_bytes=1024,
        **seals,
    )

    def read(document):
        raw = api["encode"](document)
        return api["scoped_bake"](raw, api["digest"](raw), request_raw, policy_raw, "e" * 64)

    assert read(bake) == bake
    with pytest.raises(ValueError, match="lineage"):
        read({**bake, "test_sha256": "1" * 64})
    with pytest.raises(ValueError, match="aliases"):
        read({**bake, "output_root": str(Path(scope["test_root"]) / "unexpected")})
    with pytest.raises(ValueError, match="exceed 8 GiB"):
        read({**bake, "committed_input_bytes": 8 * 2**30 + 1})
    diagnostics = [
        dict(key=["scoped-control", k, "measurement"], sha256="d" * 64,
             path=f"independent-diagnostics/checked-candidate-setting-route-{k:03d}.json")
        for k in range(101)
    ]
    assert len(api["encode"]({**bake, "diagnostics": diagnostics})) > 16384
    assert read({**bake, "diagnostics": diagnostics})["diagnostics"] == diagnostics
    with pytest.raises(ValueError, match="oversized"):
        read({**bake, "diagnostics": diagnostics + [diagnostics[0]]})


def test_independent_original_timer_does_not_reset_on_resume(tmp_path):
    api = helper()
    keys = ("request_sha256", "policy_sha256", "profile_sha256", "schedule_sha256", "cohort_sha256",
            "test_sha256", "native_sha256", "proof_sha256")
    seals = {key: f"{i + 1:064x}" for i, key in enumerate(keys)}
    first = 100
    cutoff = first + api["BAKE_NS"]
    raw = api["encode"](dict(schema="softqp.r4.candidate-timer/1", boot_id="observed-boot",
                             started_ns=first, deadline_ns=cutoff, **seals))
    timer = tmp_path / "timer.json"
    timer.write_bytes(raw)
    bake = dict(frontier_root=str(tmp_path), timer_sha256=api["digest"](raw), **seals)
    assert api["timer_scope"](bake, boot=lambda: "observed-boot", now=lambda: cutoff - 1) == cutoff
    with pytest.raises(ValueError, match="continuity"):
        api["timer_scope"](bake, boot=lambda: "after-reboot", now=lambda: cutoff - 1)
    with pytest.raises(ValueError, match="continuity"):
        api["timer_scope"](bake, boot=lambda: "observed-boot", now=lambda: cutoff)
    timer.write_bytes(raw.replace(b"observed-boot", b"replaced-boot"))
    with pytest.raises(ValueError, match="digest differs"):
        api["timer_scope"](bake, boot=lambda: "replaced-boot", now=lambda: cutoff - 1)


def test_export_retry_reuses_terminal_history_and_does_not_clobber(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from pipeline.learned_comparison import contracts as c
    from pipeline.learned_comparison import evaluation_dispatch as dispatch

    journal = tmp_path / "candidate-journal.ndjson"
    journal.write_bytes(b"unchanged committed trials")
    observed = []
    stale = False

    def live():
        if stale and observed:
            raise TimeoutError("late export")

    def staged(runtime, proof, view, output, stage, frontier, stage_journal, bake, run, plan, *, cohorts):
        assert stage_journal.read_bytes() == b"unchanged committed trials"
        artifact = stage / "evaluation.json"
        artifact.write_bytes(b"checked export")
        observed.append(stage)
        return {"path": artifact.name, "sha256": c.digest(artifact.read_bytes())}

    monkeypatch.setattr(dispatch, "_stage_export", staged)

    def export():
        return dispatch._export(SimpleNamespace(require_live=live), None, None, tmp_path,
                                None, journal, None, None, None, cohorts=[])

    stale = True
    with pytest.raises(TimeoutError, match="late export"):
        export()
    assert not (tmp_path / "export").exists()
    assert (observed[0] / "evaluation.json").read_bytes() == b"checked export"
    stale = False
    result = export()
    assert (tmp_path / result["path"]).read_bytes() == b"checked export"
    assert observed[0] != observed[1]
    with pytest.raises(c.ContractError, match="already published"):
        export()
    assert len(observed) == 2 and journal.read_bytes() == b"unchanged committed trials"


def test_admitted_cohort_amortizes_one_observed_startup_and_keeps_failures():
    from types import SimpleNamespace
    from pipeline.learned_comparison import candidate_startup as startup

    method = "lifted"
    slot = (method, 0, "N01", 0, 0, 0)
    plan = startup.cohort_plan(SimpleNamespace(matrix={"heads": []}),
                               [(*slot, "warmup", 0), (*slot, "measured", 0)])
    digest = "a" * 64
    observed = {digest: {"launch_ns": 100, "ready_ns": 1100,
                         "imported": {"start_ns": 200, "end_ns": 300}}}

    def report(*, failure=False, startup_change=False, setup=True):
        rollup = startup.TimingCohorts(plan)
        rollup.observe(slot, {"phase": "warmup", "rep": 0, "state": "accepted"},
                       {"startup_sha256": digest, "native": {"setup_seconds": .01} if setup else None})
        for rep, cost in enumerate((50, 10, 60, 20, 30)):
            rollup.observe(slot, {"phase": "measured", "rep": rep, "state": "accepted", "full_cost_ns": cost},
                           {"startup_sha256": "b" * 64 if startup_change else digest})
        rollup.finish_frame({"key": list(slot), "state": "failed" if failure else "accepted"})
        return next(rollup.rows(observed))

    actual = report()
    assert actual["steady_mean_ns"] == 30 and actual["cold_launch_to_ready_ns"] == 1000
    assert [row["per_frame_ns"] for row in actual["batch"]] == [1030, 130, 40]
    assert report(failure=True)["reason"] == "incomplete-eligible-frames"
    assert report(setup=False)["reason"] == "prospectively-keyed-native-setup-unobserved"
    assert report(startup_change=True)["reason"] == "no-single-observed-cold-configuration"


def test_installed_preload_infers_after_frozen_roots_are_unavailable(tmp_path):
    root_value = os.environ.get("SOFTQP_CANDIDATE_MODEL_FIXTURE_ROOT")
    pins_sha = os.environ.get("SOFTQP_CANDIDATE_MODEL_FIXTURE_PINS_SHA256")
    if root_value is None and pins_sha is None:
        pytest.skip("nominate exact excluded frozen model fixture and expected pin manifest SHA-256")
    from pipeline.learned_comparison import contracts as c
    from pipeline.learned_comparison import evaluation_worker as worker
    from pipeline.learned_comparison import native_labels as native
    from softqp.learning.parameters import weight_bytes
    from test_native_labels import native_problem
    import torch

    assert root_value is not None and pins_sha is not None
    root = Path(root_value)
    assert root.is_absolute() and root.resolve(strict=True) == root
    pins = (root / "fresh-model-pins.json").read_bytes()
    assert c.digest(pins) == pins_sha
    design = Path(__file__).resolve().parents[1] / "tests/fixtures/learned-contracts/accepted-design"
    authority = c.Authority.load(design)
    trust, copies = {}, []
    for pin in json.loads(pins):
        method, seed = pin["method"], pin["seed"]
        source = root / method
        selected = tmp_path / method
        shutil.copytree(source, selected)
        copies.append(selected)
        trust[method, seed] = {"method": method, "seed": seed, "trust": {
            **pin, "bundle_root": str(selected / "bundle"),
            "preprocessing_root": str(selected / "preprocessing"), "frozen_root": str(selected / "frozen")
        }}
    roster = [trust.get((method, seed), dict(method=method, seed=seed, failure={
        "method": method, "seed": seed, "state": "missing", "reason": "excluded nonparticipant"
    })) for method in sorted(c.LEARNED) for seed in c.SEEDS]
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        binding, evidence = helper()["leaf_models"]({
            "design_manifest_hex": authority._manifest.hex(), "design_matrix_hex": authority._matrix.hex(),
            "fixture_only": True, "models": roster,
        })
        for path in copies:
            path.rename(path.with_name(path.name + "-unavailable"))
        p = native_problem("test", 2, "excluded-preload")
        objective = native._prepare(p["original"]).reference().as_dict()["objective"]
        for row in evidence:
            method, seed, head = row["method"], row["seed"], row["head"]
            scope, checkpoint, failure = binding(method, seed, head)
            if failure:
                assert scope is checkpoint is None and failure[0] == "missing"
                continue
            assert checkpoint == row["checkpoint_sha256"]
            assert c.digest(weight_bytes(scope[0])) == row["weights_sha256"]
            assert row["end_ns"] > row["start_ns"]
            for _ in range(2):
                repeated, _, _ = binding(method, seed, head)
                assert repeated is scope
                result, _ = worker._route(p, method, repeated, None)
                assert result["inference_seconds"] > 0
                assert worker._candidate(p, method, result, objective)[0] == "accepted"
    finally:
        torch.set_num_threads(threads)


@pytest.mark.parametrize("recover_late", [False, True], ids=["complete-bake", "expired-recovery"])
def test_actual_candidate_bake_from_excluded_native_proof(tmp_path, recover_late):
    from runtime_config import native49

    config = native49()
    from test_heldout_inputs import _make_inputs
    from pipeline.learned_comparison import contracts as c
    from pipeline.learned_comparison.candidate_startup import cohort_plan
    from pipeline.learned_comparison import evaluation as e
    from pipeline.learned_comparison import heldout_inputs as h

    profile = config.snapshot / "profile"
    assert c.digest((profile / "provenance.json").read_bytes()) == config.profile_sha256
    metadata, req, policy, context = _make_inputs(tmp_path, config.profile_sha256, profile)
    command = [
        str(config.python), "-I", "-S", "-B", str(profile / "verify.py"), "--heldout-fixture",
        "--python", str(config.python), "--base-python", str(config.base_python),
        "--source", str(config.snapshot / "source"), "--profile", str(profile),
        "--expected-profile-sha256", config.profile_sha256, "--tools", str(config.tools),
    ]

    def stage(name, request, request_sha, policy, policy_sha, extra=(), *, outcome="heldout-inputs"):
        run = tmp_path / name
        observed = subprocess.run(
            [*command, "--run", str(run), "--request", str(request), "--expected-request-sha256", request_sha,
             "--policy", str(policy), "--expected-policy-sha256", policy_sha, *extra],
            capture_output=True, timeout=1600,
        )
        (tmp_path / (name + "-stderr.log")).write_bytes(observed.stderr)
        assert (observed.returncode == 0) == (outcome is not None), (observed.stderr, (run / "stderr.log").read_bytes())
        receipt = json.loads((run / "receipt.json").read_bytes())
        assert receipt["cleanup"] == "owned-process-tree-closed" and receipt["i1_issued"] is False
        return (json.loads((run / (outcome + ".json")).read_bytes())["observed"]
                if outcome is not None else None), receipt

    before, _ = stage("native-supervisor", metadata / req["path"], req["sha256"],
                      metadata / policy["path"], policy["sha256"])
    native_policy = c.strict_loads((metadata / policy["path"]).read_bytes())
    request = {**c.strict_loads((metadata / req["path"]).read_bytes()), "stage": "candidate"}
    req_raw = c.canonical_bytes(request)
    expected = {key: before[key] for key in ("test_sha256", "native_sha256", "proof_sha256")}
    governed = {**native_policy, "stage": "candidate", "expected": expected,
                "request_sha256": c.digest(req_raw)}
    policy_raw = c.canonical_bytes(governed)
    index = c.strict_loads((metadata / governed["inputs"]["index"]["path"]).read_bytes())
    frame_keys = {h._slot_key(row) for row in index["rows"]}
    schedule = tuple(row for row in e.execution_schedule(context.authority) if tuple(row[2:6]) in frame_keys)
    schedule_raw = b"".join(c.canonical_bytes(list(row)) for row in schedule)
    plan_sha = c.digest(schedule_raw)
    frontier = tmp_path / "candidate-lease"
    frontier.mkdir()
    api = helper()
    scope = dict(request_sha256=c.digest(req_raw), policy_sha256=c.digest(policy_raw),
                 profile_sha256=config.profile_sha256, schedule_sha256=plan_sha,
                 cohort_sha256=c.digest(c.canonical_bytes(cohort_plan(context.authority, schedule))),
                 **expected)
    started = time.perf_counter_ns()
    if recover_late:
        assert started > api["BAKE_NS"], "excluded late-control requires an independently known long-lived boot"
        started -= api["BAKE_NS"] - 120 * 10**9
    timer_raw = c.canonical_bytes(dict(schema="softqp.r4.candidate-timer/1",
                                      boot_id=api["windows_boot_id"](), started_ns=started,
                                      deadline_ns=started + api["BAKE_NS"], **scope))
    timer_sha = c.digest(timer_raw)
    initial = e.EvaluationJournal.initial_frontier(
        plan_sha256=api["journal_plan_sha256"](dict(schedule_sha256=plan_sha, timer_sha256=timer_sha))
    )
    (frontier / "timer.json").write_bytes(timer_raw)
    (frontier / "schedule.ndjson").write_bytes(schedule_raw)
    (frontier / "frontier.json").write_bytes(initial)
    output = tmp_path / "candidate-output"
    bake = dict(schema="softqp.r4.candidate-bake/1", timer_sha256=timer_sha,
                scope_sha256=c.digest(c.canonical_bytes(governed["scope"])),
                roster_sha256=request["roster_sha256"],
                frontier_sha256=c.digest(initial), output_root=str(output), frontier_root=str(frontier),
                diagnostics=[], committed_input_bytes=0, **scope)
    (metadata / "candidate-request.json").write_bytes(req_raw)
    (metadata / "candidate-policy.json").write_bytes(policy_raw)
    bake_raw = c.canonical_bytes(bake)
    (metadata / "candidate-bake.json").write_bytes(bake_raw)
    unavailable = context.root.with_name("global-payloads-unavailable")
    context.root.rename(unavailable)
    context.root.mkdir()
    try:
        result, observation = stage(
            "candidate-supervisor", metadata / "candidate-request.json", c.digest(req_raw),
            metadata / "candidate-policy.json", c.digest(policy_raw),
            ("--candidate", "--bake", str(metadata / "candidate-bake.json"), "--expected-bake-sha256",
             c.digest(bake_raw)),
            outcome=None if recover_late else "heldout-inputs",
        )
        if recover_late:
            assert observation["candidate_terminal"]["reason"] == "bake-deadline"
            old_run = tmp_path / "candidate-supervisor"
            journal = output / "candidate-journal.ndjson"
            old = {f: f.read_bytes() for f in (journal, frontier / "frontier.json", frontier / "timer.json")}
            state = c.strict_loads(old[frontier / "frontier.json"])
            assert 0 < state["next"] < len(schedule)
            staged = journal.with_name(journal.name + ".terminal")
            recovery_root = tmp_path / "recovered-output"
            policy = dict(
                schema="softqp.r4.candidate-recovery-policy/1", original_bake_sha256=c.digest(bake_raw),
                frontier_sha256=c.digest(old[frontier / "frontier.json"]),
                journal_sha256=c.digest(old[journal]),
                staged_sha256=c.digest(staged.read_bytes()) if staged.exists() else None,
                terminal_sha256=c.digest((old_run / "receipt.json").read_bytes()),
                terminal_root=str(old_run), output_root=str(recovery_root), max_wall_seconds=600,
            )
            recovery = metadata / "recovery-policy.json"
            recovery.write_bytes(c.canonical_bytes(policy))
            recovered, final = stage(
                "recovery-supervisor", metadata / "candidate-request.json", c.digest(req_raw),
                metadata / "candidate-policy.json", c.digest(policy_raw),
                ("--candidate-recover", "--bake", str(metadata / "candidate-bake.json"),
                 "--expected-bake-sha256", c.digest(bake_raw), "--recovery", str(recovery),
                 "--expected-recovery-sha256", c.digest(recovery.read_bytes())),
                outcome="candidate-recovery",
            )
            report_raw = (recovery_root / "recovery" / "recovery.json").read_bytes()
            report = c.strict_loads(report_raw)
            assert recovered["sha256"] == c.digest(report_raw)
            assert report["scientifically_qualified"] is False
            assert report["committed_trials"] == state["next"]
            assert report["interrupted_trials"] == int(state["active"] is not None)
            assert report["committed_trials"] + report["interrupted_trials"] + report["missing_trials"] == len(schedule)
            assert all(f.read_bytes() == content for f, content in old.items())
            assert len(final["owned_pids"]) <= 2, "read-only recovery must run no numerical child"
            return
    finally:
        context.root.rmdir()
        unavailable.rename(context.root)
    assert observation["status"] == "heldout-fixture-observed"
    assert result["state"] == "complete" and result["next_ordinal"] == len(schedule) > 0
    events = [c.strict_loads(raw) for raw in (output / "candidate-journal.ndjson").read_bytes().splitlines(keepends=True)]
    assert len(events) == len(schedule)
    assert any(row["terminal"]["state"] == "accepted" for row in events)
    assert any(row["terminal"]["state"] == "missing" for row in events)
    export_raw = (output / result["export"]["path"]).read_bytes()
    assert result["export"]["sha256"] == c.digest(export_raw)
    export = c.strict_loads(export_raw)
    assert export["fixture_only"] and not export["scientifically_qualified"]
    assert not export["matrix_complete"] and not export["diagnostics_complete"]
    assert not export["timing_complete"] and export["startups"]["rows"] == 1
    assert export["amortization"]["rows"] > 0
