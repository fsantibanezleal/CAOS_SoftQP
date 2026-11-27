"""Excluded controls for scheduling, receipts and the actual installed SDK."""
from collections import Counter
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import evaluation as e
from pipeline.learned_comparison import evaluation_worker as w
from pipeline.learned_comparison import native_labels as native
from pipeline.learned_comparison import stream_inputs as stream
from test_learned_contracts import PROVIDER


DESIGN = Path(__file__).parent / "fixtures/learned-contracts/accepted-design"


class Authority:
    def __init__(self):
        data = c.strict_loads((DESIGN / "semantic-matrix.json").read_bytes())
        self.rows = {(row["case_id"], row["regime"]): row for row in data["rows"]}

    def row(self, family, regime):
        return self.rows[family, regime]


def keys(name):
    lines = gzip.decompress((DESIGN / "expected-keysets" / f"{name}.jsonl.gz").read_bytes()).splitlines(keepends=True)
    rows = [json.loads(line) for line in lines]
    assert all(type(row) is list and c.canonical_bytes(row) == line for row, line in zip(rows, lines))
    return {tuple(row) for row in rows}


def test_full_frozen_status_and_repetition_keysets():
    authority = Authority()
    actual = list(e.status_slots(authority))
    assert len(actual) == 42816
    assert {slot.key for slot in actual} == keys("control-status") | keys("method-status")
    all_trials = []
    for family, regime in authority.rows:
        for unit in range(8):
            all_trials.extend(e.schedule_source(authority, family, regime, unit))
    assert len(all_trials) == 239960
    assert set(all_trials) == keys("control-repetitions") | keys("method-repetitions")
    assert Counter(row[-2] for row in all_trials) == {"warmup": 68560, "measured": 171400}


def test_missing_eligible_rows_and_stream_refuse_substitution(tmp_path):
    slots = [e.Slot(("learned_daqp", 41001, "N01", 0, 0, 0), True, None),
             e.Slot(("learned_daqp", 41001, "N07", 0, 0, 0), False, "not PD")]
    rows = [e.missing_status(slot, "checkpoint declared absent") for slot in slots]
    path = tmp_path / "status.ndjson"
    seal = e.write_json_lines(path, rows)
    assert e.read_status_shard(path, seal, slots) == {"missing": 1, "incompatible": 1}
    rows[0]["trials"].pop()
    bad = tmp_path / "fewer.ndjson"
    with pytest.raises(c.ContractError, match="trial keyset"):
        e.read_status_shard(bad, e.write_json_lines(bad, rows), slots)


def test_parent_observed_receipt_and_deadline():
    key = ("lifted", 0, "N01", 0, 0, 0, "measured", 0)
    nonce = "a" * 32
    wire = dict(key=list(key), nonce=nonce, pid=71, started_ns=110, ended_ns=170)
    arguments = dict(slot=key, ordinal=0, request_sha="a"*64, policy_sha="b"*64, profile_sha="c"*64,
                     nonce=nonce, owned_pid=71, released_ns=100, observed_ns=180, child=wire)
    receipt = e.trial_receipt(**arguments)
    assert e.validate_trial(receipt, wire, c.digest(c.canonical_bytes(receipt))) == 60
    with pytest.raises(c.ContractError, match="late or impossible"):
        e.trial_receipt(**{**arguments, "observed_ns": 100 + e.TRIAL_NS})
    with pytest.raises(c.ContractError, match="identity differs"):
        e.trial_receipt(**{**arguments, "owned_pid": 72})


def test_bootstrap_raw_draws_and_reversal(tmp_path):
    rows = list(e.bootstrap_draw_rows("learned_osqp", [("N12", 0)]))
    assert len(rows) == 10000 and all(len(row) == 11 for row in rows)
    assert rows != list(e.bootstrap_draw_rows("learned_daqp", [("N12", 0)]))
    assert c.trajectory_reduction([1, 1, 100], [.5, .5, 120]) == pytest.approx(-19 / 102)
    reference = e.write_bootstrap_draws(tmp_path, "learned_osqp", [("N12", 0)])
    inputs = [dict(seed=seed, family="N12", regime=0, source_index=u, reduction=.25)
              for seed in c.SEEDS for u in range(8)]
    context = SimpleNamespace(root=tmp_path, allow_fixture=False, _admission_session=None)
    assert c._bootstrap_interval(inputs, "learned_osqp", reference["file"], context) == [.25, .25]


def test_previous_state_requires_exact_prior_ordinal_and_scoped_launch_refuses():
    old = ("previous_osqp", 0, "N12", 0, 0, 0, "measured", 0)
    state = w.PreviousVector(old, (object(), object()))
    current = (*old[:5], 1, *old[6:])
    assert w._previous_vector(current, state) is state.sdk_state
    with pytest.raises(c.ContractError, match="crosses source"):
        w._previous_vector((*current[:-1], 1), state)
    with pytest.raises(c.ContractError, match="verified evaluation supervisor"):
        e.read_registered_launch(b"{}\n", object())


def test_durable_frontier_resume_refuses_redraw_or_mutated_receipt(tmp_path):
    authority, spool = (tmp_path / name for name in ("authority", "spool"))
    authority.mkdir()
    spool.mkdir()
    frontier, journal = authority / "advance.json", spool / "events.ndjson"
    plan = "1" * 64
    keys = [("lifted", 0, "N01", 0, 0, 0, "warmup", i) for i in range(2)]
    raw = e.EvaluationJournal.initial_frontier(plan_sha256=plan)
    frontier.write_bytes(raw)

    def resume(expected):
        return e.EvaluationJournal(journal, frontier, expected_frontier_sha256=expected,
                                   plan_sha256=plan, schedule=keys)

    with resume(c.digest(raw)) as ledger:
        active = ledger.begin()
        with pytest.raises(c.ContractError, match="already issued"):
            ledger.begin()
    with pytest.raises(c.ContractError, match="frontier changed"), resume(c.digest(raw)):
        pass
    with resume(active) as ledger:
        ledger.reconcile()
        assert ledger.next_key == keys[1]
        ledger.begin()
        confirmed = ledger.settle({"state": "timeout", "reason": "observed deadline", "receipt": None})
        assert ledger.next_key is None
    with resume(confirmed) as ledger:
        assert ledger.next_key is None
    assert b'interrupted-owned-trial' in journal.read_bytes()
    journal.write_bytes(journal.read_bytes().replace(b"observed deadline", b"forgeded deadline"))
    with pytest.raises(c.ContractError, match="prefix differs"), resume(confirmed):
        pass


def test_project_interrupted_journal_many_missing_and_incompatible_slots(tmp_path, monkeypatch):
    trust, scratch = (tmp_path / name for name in ("trust", "scratch"))
    trust.mkdir()
    scratch.mkdir()
    plan, frontier, journal = "a" * 64, trust / "frontier.json", scratch / "timing.ndjson"
    eligible = ("lifted", 0, "N01", 0, 0, 0)
    forbidden = ("flex", 0, "N01", 0, 0, 0)
    keys = [(*eligible, phase, rep) for phase, _, n in e.PHASES for rep in range(n)]
    slots = [e.Slot(eligible, True, None), e.Slot(forbidden, False, "frozen linear-only condition")]
    monkeypatch.setattr(e, "execution_schedule", lambda _: iter(keys))
    monkeypatch.setattr(e, "status_slots", lambda _: iter(slots))
    frontier.write_bytes(e.EvaluationJournal.initial_frontier(plan_sha256=plan))
    with e.EvaluationJournal(journal, frontier, expected_frontier_sha256=c.digest(frontier.read_bytes()),
                             plan_sha256=plan, schedule=keys) as attempt:
        attempt.begin()
        head = attempt.settle({"state": "timeout", "reason": "watched whole trial", "receipt": None})
    output = scratch / "statuses.ndjson"
    reference = e.project_status_journal(journal, frontier, expected_frontier_sha256=head, authority=object(),
                                         plan_sha256=plan, temporary_index=scratch / "index.db", output=output,
                                         missing_reason="24-hour bake elapsed")
    assert e.read_status_shard(output, reference, slots) == {"timeout": 1, "incompatible": 1}
    result = c.strict_loads(output.read_bytes().splitlines(keepends=True)[0])
    assert Counter(row["state"] for row in result["trials"]) == {"timeout": 1, "missing": 6}


def test_matched_totals_keep_trajectory_identity_and_suppress_failed_estimate():
    totals = e.MatchedTrajectoryTotals()
    for method, seed, costs in (["cold_osqp", 0, [2, 2, 200] + [2] * 29],
                                ["learned_osqp", 41001, [1, 1, 240] + [2] * 29]):
        for frame, median in enumerate(costs):
            totals.add({"key": [method, seed, "N12", 0, 0, frame], "state": "accepted",
                        "trials": [{"phase": "measured", "full_cost_ns": median} for _ in range(5)]})
    observed = totals.projection("learned_osqp", diagnostics_complete=True)
    assert observed["totals"][0]["reduction"] == pytest.approx(-19 / 131)
    totals.add({"key": ["learned_osqp", 41002, "N12", 0, 0, 0], "state": "timeout"})
    assert totals.projection("learned_osqp", diagnostics_complete=True) == {
        "state": "undefined", "failed_statuses": 1, "totals": []}


def problem(kind):
    original = deepcopy(PROVIDER["problem_payload"]("test", .25)["original"])
    if kind in {"linear", "linear-interval"}:
        original["penalty"]["lower_quadratic"] = [0.]
        original["penalty"]["upper_quadratic"] = [0.]
    if kind == "linear-interval":
        original.update(q=[0.], lower=[-1.], upper=[1.], lower_finite=[True], upper_finite=[True])
        original["penalty"].update(lower_linear=[.2], upper_linear=[.2])
    if kind == "peak":
        original["formulation"] = "peak"
        original["groups"] = [dict(group_id=0, rows=[0], lower_scale=[1.], upper_scale=[2.],
                                   linear=1., quadratic=1.)]
        original["units"]["D_t"] = [1.]
    return original


@pytest.mark.parametrize(("method", "kind"), [
    ("lifted", "symmetric"), ("generalized", "symmetric"), ("asymmetric", "symmetric"),
    ("directional", "symmetric"), ("daqp", "symmetric"), ("elastiqp", "linear"),
    ("flex", "linear-interval"), ("clarabel", "symmetric"), ("proxqp", "symmetric"),
    ("piqp", "symmetric"), ("cold_osqp", "symmetric"), ("cold_daqp", "symmetric"),
    ("previous_osqp", "symmetric"), ("previous_daqp", "symmetric"),
    ("lifted", "peak"), ("daqp", "peak"), ("clarabel", "peak"), ("proxqp", "peak"),
    ("piqp", "peak"), ("cold_osqp", "peak"), ("cold_daqp", "peak"),
])
def test_actual_installed_routes(method, kind):
    original = problem(kind)
    prepared = native._prepare(original)
    reference = prepared.reference().as_dict()
    assert reference["status"] == "oracle-agreed", reference
    physical = {"original": original, "transform": c.canonical_transform(original)}
    output, _state = w._route(physical, method, None, None)
    observed = w._candidate(physical, method, output, reference["objective"])
    assert observed[0] == "accepted", (observed, output)


def test_actual_flex_iteration_failure_is_never_accepted():
    from softqp.flex import solve_flex

    original = problem("linear")
    physical = {"original": original, "transform": c.canonical_transform(original)}
    predecessor = solve_flex(w._physical(original), eps_abs=1e-7, eps_rel=1e-7, max_iter=200000,
                             rho=1, sigma_x=1e-6, sigma_s=1e-6, alpha=1.6)
    predecessor["native_flag"] = predecessor["status_code"]
    assert predecessor["native_flag"] == 7
    assert w._candidate(physical, "flex", predecessor, 0.)[:2] == (
        "failed", "native flag outside registered success alphabet")
    output, _ = w._route(physical, "flex", None, None)
    assert output["native_flag"] == 1 and output["backend_settings"]["sigma_s"] == 1


def test_actual_legacy_daqp_retains_asymmetric_weights_and_redundant_equality():
    from softqp.solvers import solve

    original = problem("symmetric")
    original.update(n=2, m=3, P=c.csc([[1., 0.], [0., 2.]]), A=c.csc([[1., 0.], [0., 1.], [0., 1.]]),
                    q=[3., 0.], lower=[0., 0., 0.], upper=[1., 0., 0.],
                    lower_finite=[True] * 3, upper_finite=[True] * 3)
    original["units"].update(D_x=[1., 1.], D_r=[1.] * 3)
    original["penalty"].update(soft=[True, False, False], lower_linear=[.25, 0., 0.], upper_linear=[.75, 0., 0.],
                               lower_quadratic=[1., 0., 0.], upper_quadratic=[4., 0., 0.])
    physical = {"original": original, "transform": c.canonical_transform(original)}
    old = solve(w._physical(original), method="daqp", max_iter=200000)
    assert old["backend_settings"]["eq_reduction"] == 0
    output, _ = w._route(physical, "daqp", None, None)
    w.verify_legacy_daqp(physical, output)
    assert output["native_sense"].tolist() == [8, 5, 5]
    assert output["side_weights"]["rho_u"].tolist() == [.25, 0., 0.]
    assert output["native_flag"] in (1, 2)
    expected = -((3. - .25) ** 2) / 4
    status, _, _, metrics = w._candidate(physical, "daqp", output, expected)
    assert status == "accepted" and metrics["objective"] == pytest.approx(expected, abs=1e-8)
    changed = deepcopy(output)
    changed["observed_controls"]["before_setup"]["eq_reduction"] = 0
    with pytest.raises(c.ContractError, match="settings evidence"):
        w.verify_legacy_daqp(physical, changed)


@pytest.mark.parametrize("method", ["learned_osqp", "learned_daqp"])
def test_actual_excluded_numeric_inference_injects_native_state(method):
    from softqp.learning.fixed_point import L2WSHead, Normalizer
    from softqp.learning.graph import ActiveSetGNN
    from softqp.learning.parameters import weight_bytes

    original = problem("symmetric")
    original.update(lower=[-1.], upper=[1.], lower_finite=[True], upper_finite=[True])
    prepared = native._prepare(original)
    reference = prepared.reference().as_dict()
    shape = prepared.shape
    if method == "learned_osqp":
        model = L2WSHead(*shape, 41001)
        p = prepared.features().numel()
        fitted = Normalizer.from_admitted([0.] * p, [1.] * p, ["excluded-train"], [1.])
        normalizer = dict(mean=[0.] * p, scale=[1.] * p, source_ids=["excluded-train"], frame_weights=[1.],
                          numeric_sha256=fitted.numeric_sha256)
        prior = threshold = None
    else:
        prior, threshold, normalizer = .5, .5, None
        model = ActiveSetGNN(41001, prior)
    weights = weight_bytes(model)
    scope = w.load_numeric_model(method=method, seed=41001, shape=shape, weights=weights,
                                 weights_sha256=c.digest(weights), normalizer=normalizer, prior=prior,
                                 threshold=threshold)
    physical = {"original": original, "transform": c.canonical_transform(original)}
    output, _ = w._route(physical, method, scope, None)
    assert w._candidate(physical, method, output, reference["objective"])[0] == "accepted"
    assert output["inference_seconds"] > 0
    if method == "learned_osqp":
        assert output["initial_x"] is not None and output["initial_y"] is not None
    else:
        assert output["node_scores"] is not None and len(output["attempts"]) >= 1


def test_actual_owned_worker_killed_after_whole_trial_deadline(tmp_path):
    command = [sys._base_executable, "-I", "-S", "-B", "-c", "import time; time.sleep(30)"]
    root = tmp_path / "owned"
    child = native._OwnedWorker(root, command, Path(sys._base_executable), nonce="deadline")
    process = child.process
    released = time.perf_counter_ns()
    try:
        with pytest.raises(TimeoutError):
            e.await_owned_trial(child, root / "never.json", released_ns=released)
        assert 9.9 <= (time.perf_counter_ns() - released) / 1e9 < 14
        assert process.poll() not in (0, None)
    finally:
        child.close()


def test_real_timed_factored_decode_refuses_forged_oracle_and_wrong_role():
    problem = PROVIDER["problem_payload"]("test", .25)
    reference = native._prepare(problem["original"]).reference().as_dict()
    context = SimpleNamespace(settings_hashes={f"oracle:{key}": str(index) * 64 for index, key in
                                                 enumerate(("stock_osqp", "clarabel", "piqp"))})
    rows = native._product_reference(reference, problem, context)
    source_id, frame_id = "source-excluded", "frame-excluded"
    source = c.canonical_bytes(dict(artifact_id=source_id, kind=stream.SOURCE, payload=stream.factor_source(problem)))
    source_ref = dict(artifact_id=source_id, kind=stream.SOURCE, path="source.json", sha256=c.digest(source))
    frame = c.canonical_bytes(dict(artifact_id=frame_id, kind=stream.FRAME, payload=stream.factor_frame(problem, source_ref)))
    oracle = w.verify_frame_oracle(problem, c.digest(frame), rows, context, state="oracle-agreed",
                                   expected_rows_sha256=c.digest(c.canonical_bytes(rows)))
    family, regime, unit, frame_index = (problem["source"][key] for key in ("family", "regime", "unit_index", "frame"))
    key = ("lifted", 0, family, regime, unit, frame_index, "measured", 0)
    result, _ = w.evaluate_trial(source, frame, key=key, nonce="a" * 32, oracle=oracle)
    assert result["status"] == "accepted" and 0 < result["preprocess_ns"] < result["ended_ns"] - result["started_ns"]
    w.verify_numeric_output(problem, "lifted", result, oracle=oracle)
    forged_metrics = deepcopy(result)
    forged_metrics["metrics"]["G"] += .1
    with pytest.raises(c.ContractError, match="original-space metrics differ"):
        w.verify_numeric_output(problem, "lifted", forged_metrics, oracle=oracle)
    forged = w.VerifiedFrameOracle(oracle.frame_sha256, oracle.original_sha256, oracle.transform_sha256,
                                   oracle.rows_sha256, oracle.objective)
    refused, _ = w.evaluate_trial(source, frame, key=key, nonce="a" * 32, oracle=forged)
    assert refused["status"] == "failed" and "unverified reference" in refused["reason"]
    refused, _ = w.evaluate_trial(source, frame.replace(b'"split":"test"', b'"split":"train"'), key=key,
                                  nonce="a" * 32, oracle=oracle)
    assert refused["status"] == "failed" and "outside timed test scope" in refused["reason"]
