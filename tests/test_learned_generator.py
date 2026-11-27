"""R4 generator source fixtures using exclusively the excluded software namespace."""

from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import os
from types import SimpleNamespace

import numpy as np
import pytest

from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import generator as g
from pipeline.learned_comparison import stream_inputs as stream
from test_learned_contracts import PROVIDER


@pytest.fixture(scope="module")
def authority():
    return c.Authority.load(Path(__file__).parent / "fixtures/learned-contracts/accepted-design")


def digest(value):
    return c.digest(c.canonical_bytes(value))


def rng(slot, code):
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(slot.entropy(code, fixture=True))))


def parameters(payload):
    return {row["name"]: row["value"] for row in payload["source"]["parameters"]}


def verify_state(payload, trace, code, stage="final"):
    assert bytes(int(v) for v in parameters(payload)[f"pcg64_stream_{code}_{stage}_sha256"]).hex() == digest(
        trace.bit_generator.state
    )


def test_plan_counts_shape_coverage_and_disjoint_seed_slots(authority, monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail("enumerating the registry must never construct RNG")

    monkeypatch.setattr(g, "_rng", refuse)
    slots = tuple(g.source_slots(authority))
    frames = tuple(g.frame_keys(authority))
    assert len(slots) == len({row.source_id for row in slots}) == 5_040
    assert len(frames) == len(set(frames)) == 15_456
    assert Counter(row.split for row in slots) == {"train": 2880, "validation": 720,
                                                "calibration": 720, "test": 720}
    assert sum(frame[2] == "test" for frame in frames) == 2208
    assert sum(frame[0] == "N12" for frame in frames) == 10_752
    assert len({tuple(slot.entropy(code)) for slot in slots for code in range(3)}) == 15_120
    assert len({row["head_id"] for row in authority.matrix["rows"]}) == 14
    assert sum(row["frames"] * 56 for row in authority.matrix["rows"]
               if row["methods"]["learned_daqp"]["eligible"]) == 14_504
    assert slots[0].entropy(0) == [20261105, 903, 1, 0, 0, 0, 0]
    assert slots[0].entropy(0, fixture=True) == [20261122, 800003, 1, 0, 0, 0, 0]
    for arguments in (("N00", 0, "train", 0), ("N01", True, "train", 0), ("N12", 0, "test", 8)):
        with pytest.raises(ValueError, match="unknown R4"):
            g.SourceSlot(*arguments)


@pytest.mark.parametrize("family", g.REGIMES)
def test_all_six_regimes_match_the_reviewed_original_canonical_and_graph_domains(authority, family):
    seen = set()
    for regime, regime_value in enumerate(g.REGIMES[family]):
        slot = g.SourceSlot(family, regime, "validation", 0)
        unit = g.generate_fixture_unit(slot)
        problem = unit.problem(0)
        artifact_id = unit.frame_id(0)
        context = SimpleNamespace(
            allow_fixture=True, authority=authority, generator_sha256=g.generator_sha256(),
            problem_hashes={artifact_id: problem["original_sha256"]},
            source_records={artifact_id: digest(problem["source"])},
        )
        c._problem(problem, context, {"artifact_id": artifact_id}, v2_fixture=True)
        assert problem["source"]["state_origin"] == "contract-fixture"
        units = problem["original"]["units"]
        assert units["objective"] == ("synthetic-currency" if family in {"N13", "N14"} else "synthetic-operating-cost")
        if family not in {"N09", "N10", "N12", "N13", "N14"}:
            assert set(units["variable"] + units["row"] + units["peak"]) == {"dimensionless"}
        assert len(unit.vectors) == slot.frame_count
        assert parameters(problem)["regime_value"] == [regime_value]
        assert problem["source"]["input_sha256"] == digest(problem["original"])
        assert problem["transform_sha256"] == digest(problem["transform"])
        assert problem["original_sha256"] not in seen
        seen.add(problem["original_sha256"])


def test_dense_draw_order_certificate_density_and_fresh_split():
    slot = g.SourceSlot("N06", 2, "train", 3)
    unit = g.generate_fixture_unit(slot)
    problem = unit.problem(0)
    original = problem["original"]
    assert c.canonical_bytes(problem) == c.canonical_bytes(g.generate_fixture_unit(slot).problem(0))
    co, op = rng(slot, 0), rng(slot, 1)
    verify_state(problem, co, 0, "initial")
    raw = co.normal(size=(32, 32))
    Q, R = np.linalg.qr(raw, mode="reduced")
    Q = Q * np.where(np.diag(R) < 0, -1, 1)
    temporary = ((Q * np.geomspace(1, 10, 32)) @ Q.T) * co.uniform(.8, 1.2)
    mask = co.uniform(size=(48, 32)) < .2
    expected_rows = np.where(mask, co.normal(size=(48, 32)) / np.sqrt(.2*32), 0.)
    centers = op.uniform(-.1, .1, size=48)
    widths = op.uniform(.3, .6, size=48)
    q = op.normal(0, 3, size=32)
    verify_state(problem, co, 0)
    verify_state(problem, op, 1)
    P, A = np.array(c.dense(original["P"])), np.array(c.dense(original["A"]))
    assert np.array_equal(P, P.T) and np.array_equal(np.triu(P), np.triu(temporary))
    assert np.array_equal(A[:32], np.eye(32))
    assert np.array_equal(A[32:], expected_rows)
    assert original["q"] == q.tolist()
    assert original["lower"][32:] == (centers - widths).tolist()
    assert original["upper"][32:] == (centers + widths).tolist()
    assert parameters(problem)["actual_full_row_density"] == [np.count_nonzero(A) / A.size]
    assert parameters(problem)["actual_random_row_density"] == [np.count_nonzero(expected_rows) / expected_rows.size]
    prec = problem["curvature"]
    assert prec["temporary_constructor_sha256"] == digest(temporary.tolist())
    assert prec["rank"] == 32 and prec["pivots"] == c.exact_curvature(P.tolist())[1]
    assert len(max(prec["pivots"], key=len)) > 1000
    validation = g.generate_fixture_unit(replace(slot, split="validation"))
    assert validation.static["P"] != unit.static["P"] and validation.identity != unit.identity


def test_rank_zero_and_full_psd_draw_order_and_exact_negative_witness():
    for regime, rank in [(0, 0), (3, 8), (5, 16)]:
        slot = g.SourceSlot("N07", regime, "train", 0)
        problem = g.generate_fixture_unit(slot).problem(0)
        trace = rng(slot, 0)
        permutation = trace.permutation(16)
        value = trace.uniform(.8, 1.2)
        expected = np.zeros(16)
        expected[permutation[:rank]] = value * np.geomspace(1, 10, rank)
        trace.uniform(size=(24, 16))
        trace.normal(size=(24, 16))
        verify_state(problem, trace, 0)
        assert np.array_equal(np.diag(expected), c.dense(problem["original"]["P"]))
        assert problem["curvature"]["diagonal_support"] == sorted(permutation[:rank])
        assert problem["curvature"]["rank"] == rank
        assert problem["curvature"]["pivots"] == []
    with pytest.raises(c.ContractError, match="nonconvex"):
        g._certificate(np.diag([1., -(2.**-60)]), np.diag([1., -(2.**-60)]), diagonal=True)
    with pytest.raises(c.ContractError, match="symmetry"):
        g._certificate(np.array([[1., 0.2], [np.nextafter(.2, 1.), 1.]]), np.eye(2))


def test_impulses_hold_and_condensed_cost_against_independent_recursion():
    slot = g.SourceSlot("N12", 5, "train", 0)
    unit = g.generate_fixture_unit(slot)
    first = unit.problem(0)
    facts = parameters(first)
    coef, op, per = (rng(slot, code) for code in range(3))
    mass, wp, wv, wu = (coef.uniform(a, b) for a, b in ((.8, 1.2), (2.7, 3.3), (.27, .33), (.09, .11)))
    state = np.array([op.uniform(.8, 1.6), op.uniform(-.1, .1)])
    verify_state(first, coef, 0)
    verify_state(first, op, 1)
    verify_state(first, per, 2)
    assert facts["mass"] == [mass]
    assert facts["force_weight"] == [wu]
    original = first["original"]
    P = np.array(c.dense(original["P"]))
    A = np.array(c.dense(original["A"]))
    assert original["units"]["row"] == ["N"]*20 + ["m"]*20 + ["m/s"]*20

    def step(s, u):
        p, v = s
        return np.array([p + .2*v + .02*u/mass, v + .2*u/mass])

    def rollout(s, controls):
        result = []
        for u in controls:
            s = step(s, u)
            result.append(s)
        return np.array(result)

    controls = np.linspace(-.8, .8, 20)
    for frame, q_and_bounds in enumerate(unit.vectors):
        problem = unit.problem(frame) if frame in (0, 8, 20, 31) else None
        meta = {row["name"]: row["value"] for row in unit.observations[frame]["parameters"]}
        np.testing.assert_allclose(state, [meta["pre_impulse_position"][0], meta["pre_impulse_velocity"][0]],
                                   atol=5e-16)
        impulse = 1. if frame == 8 else -.75 if frame == 20 else 0.
        assert meta["impulse_velocity"] == [impulse]
        state[1] += impulse
        assert meta["post_impulse_velocity"][0] == pytest.approx(state[1], abs=1e-15)
        force = float(np.clip(-.5*state[0] - .2*state[1], -1., 1.))
        assert meta["held_reference_force"] == pytest.approx([force], abs=1e-15)
        baseline, predicted = rollout(state, np.zeros(20)), rollout(state, controls)
        np.testing.assert_allclose(A[20:40] @ controls + baseline[:, 0], predicted[:, 0], atol=2e-14)
        np.testing.assert_allclose(A[40:] @ controls + baseline[:, 1], predicted[:, 1], atol=2e-14)
        np.testing.assert_allclose(q_and_bounds["lower"][20:40], -.4 - baseline[:, 0], atol=1e-14)
        np.testing.assert_allclose(q_and_bounds["upper"][40:], 1.5 - baseline[:, 1], atol=1e-14)
        expanded = .5*(wp*np.sum(predicted[:, 0]**2 - baseline[:, 0]**2)
                       + wv*np.sum(predicted[:, 1]**2 - baseline[:, 1]**2)
                       + wu * (controls @ controls))
        condensed = .5 * controls @ P @ controls + controls @ np.array(q_and_bounds["q"])
        assert condensed == pytest.approx(expanded, rel=2e-13, abs=3e-14)
        state = step(state, force)
        assert meta["next_pre_impulse_velocity"][0] == pytest.approx(state[1], abs=1e-15)
        if problem is not None:
            assert problem["original"]["P"] == original["P"] and problem["original"]["A"] == original["A"]
            assert problem["source"]["parent_id"] == first["source"]["parent_id"]


@pytest.mark.parametrize("family", ["N13", "N14"])
def test_thermal_physical_layout_and_exact_draw_order(family):
    slot = g.SourceSlot(family, 4, "calibration", 1)
    problem = g.generate_fixture_unit(slot).problem(0)
    p = parameters(problem)
    co, op = rng(slot, 0), rng(slot, 1)
    a, b = zip(*[(co.uniform(.88, .94), co.uniform(.22, .30)) for _ in range(2)])
    phases, offset = op.uniform(0, 2*np.pi, size=2), op.uniform(0, 24)
    verify_state(problem, co, 0)
    verify_state(problem, op, 1)
    assert p["retention"] == list(a) and p["heater_gain"] == list(b)
    assert p["initial_temperature_phase"] == phases.tolist()
    assert p["daytime_offset"] == [offset]
    orig = problem["original"]
    assert (orig["n"], orig["m"]) == (66, 98)
    assert orig["units"]["variable"] == ["degreeC"]*34 + ["kWh"]*32
    assert orig["units"]["row"] == ["degreeC"]*34 + ["kWh"]*32 + ["degreeC"]*32
    assert "bbdd7909b2ee523881383764eb969eaab079d4de" in problem["source"]["attribution"]
    A = np.array(c.dense(orig["A"]))
    predicted = np.zeros(66)
    for zone in range(2):
        t, heat = 17*zone, 34 + 16*zone
        predicted[t] = 21.5 + .5*np.sin(phases[zone])
        assert np.flatnonzero(A[t]).tolist() == [t]
        for hour in range(16):
            outside = 8 + 3*np.sin(2*np.pi*(hour + offset)/24)
            predicted[t+hour+1] = a[zone]*predicted[t+hour] + (1-a[zone])*outside
            assert np.flatnonzero(A[t+hour+1]).tolist() == [t+hour, t+hour+1, heat+hour]
            assert orig["lower"][heat+hour] == 0 and orig["upper"][heat+hour] == 6
            assert np.flatnonzero(A[heat+hour+32]).tolist() == [t+hour+1]
    np.testing.assert_allclose((A @ predicted)[:34], orig["lower"][:34], atol=5e-15)
    np.testing.assert_allclose(p["zero_heat_temperature_anchor"], predicted[:34], atol=5e-15)
    assert orig["lower"][:34] == orig["upper"][:34]
    assert not any(orig["penalty"]["soft"][:66]) and all(orig["penalty"]["soft"][66:])
    if family == "N13":
        assert [group["rows"] for group in orig["groups"]] == [list(range(66, 82)), list(range(82, 98))]
        assert [group["linear"] for group in orig["groups"]] == [20., 20.]
    else:
        assert orig["penalty"]["upper_quadratic"][66:] == [1.6]*32
    assert problem["curvature"]["rank"] == 66


def _fixture_context(root, unit):
    base, docs, _ = PROVIDER["build"](root)
    source_bytes = Path(g.__file__).read_bytes()
    protocol_payload = deepcopy(docs["protocol"]["payload"])
    protocol_payload["generator_sha256"] = c.digest(source_bytes)
    problem_hashes, source_records = {}, {}
    for i in range(unit.slot.frame_count):
        payload = unit.problem(i)
        problem_hashes[unit.frame_id(i)] = payload["original_sha256"]
        source_records[unit.frame_id(i)] = digest(payload["source"])
    context = replace(base, protocol_sha256=digest(protocol_payload), generator_source_bytes=source_bytes,
                      generator_sha256=c.digest(source_bytes), catalog={},
                      problem_hashes=problem_hashes, source_records=source_records,
                      fit_source_ids=(unit.identity,) if unit.slot.split == "train" else ())
    envelope = PROVIDER["envelope"]("learning-protocol", "generator-protocol", protocol_payload, context)
    protocol = c.write_artifact(envelope, "generator-protocol.json", context)
    ref = dict(kind="learning-protocol", artifact_id="generator-protocol", path="generator-protocol.json",
               sha256=protocol.raw_sha256)
    return replace(context, catalog={"generator-protocol": ref}), ref


def test_factored_v2_actual_write_read_and_thin_trajectory(tmp_path):
    unit = g.generate_fixture_unit(g.SourceSlot("N12", 4, "train", 0))
    context, protocol = _fixture_context(tmp_path, unit)
    source_ref, frames = g.write_fixture_unit(unit, context=context, protocol_ref=protocol)
    refs = {r["artifact_id"]: r for r in (source_ref, *frames)}
    context = replace(context, catalog={**context.catalog, **refs})
    source = stream.read_stream_artifact(tmp_path / source_ref["path"], context,
                                         expected_sha256=source_ref["sha256"])
    static = source.payload["original_static"]
    assert set(static) >= {"P", "A", "units", "lower_finite"}
    assert len(frames) == 32
    for i, ref in enumerate(frames):
        frame = stream.read_stream_artifact(tmp_path / ref["path"], context, expected_sha256=ref["sha256"])
        assert frame.payload["source_ref"] == source_ref
        assert set(frame.payload["vectors"]) == {"q", "lower", "upper"}
        expected = unit.problem(i)
        assert stream._reconstruct(source.payload, frame.payload) == expected
    for kind in ("q", "lower", "upper"):
        assert kind not in static
    assert len(list(tmp_path.glob("fixture-N12-*source.json"))) == 1


def test_dense32_real_file_retains_rational_certificate_and_tamper_refusal(tmp_path):
    unit = g.generate_fixture_unit(g.SourceSlot("N08", 5, "validation", 1))
    context, protocol = _fixture_context(tmp_path, unit)
    source, (frame,) = g.write_fixture_unit(unit, context=context, protocol_ref=protocol)
    catalog = {**context.catalog, source["artifact_id"]: source, frame["artifact_id"]: frame}
    context = replace(context, catalog=catalog)
    admitted = stream.read_stream_artifact(tmp_path / frame["path"], context, expected_sha256=frame["sha256"])
    current = admitted.document
    current["payload"]["vectors"]["q"][0] += 1.
    current["content_sha256"] = c.content_digest(current)
    path = tmp_path / "tampered.json"
    path.write_bytes(c.canonical_bytes(current))
    with pytest.raises(c.ContractError, match="original identity"):
        stream.read_stream_artifact(path, context, expected_sha256=c.digest(path.read_bytes()))


def test_fixture_entropy_requires_lane_slot_and_actual_initial_state(authority, tmp_path):
    unit = g.generate_fixture_unit(g.SourceSlot("N01", 2, "train", 0))
    context, protocol = _fixture_context(tmp_path, unit)
    source, (frame,) = g.write_fixture_unit(unit, context=context, protocol_ref=protocol)
    context = replace(context, catalog={**context.catalog, source["artifact_id"]: source})
    original = unit.problem(0)
    with pytest.raises(c.ContractError, match="outside v2 fixture lane"):
        c._problem(original, context, {"artifact_id": unit.frame_id(0)})
    for scenario in ("origin", "slot", "state"):
        forgery = deepcopy(original)
        source_data = forgery["source"]
        if scenario == "origin":
            source_data["state_origin"] = "generator-produced"
        elif scenario == "slot":
            source_data["entropy"][-2] = 1
        else:
            source_data["rng_state"]["state"]["state"] += 1
            source_data["rng_state_sha256"] = digest(source_data["rng_state"])
        ctx = replace(context, source_records={unit.frame_id(0): digest(source_data)})
        document = stream.stream_document(stream.FRAME, unit.frame_id(0),
                    stream.factor_frame(forgery, source), ctx, protocol)
        with pytest.raises(c.ContractError, match="fixture entropy|seed entropy|initial RNG state"):
            stream.write_stream_artifact(document, scenario + ".json", ctx)
        assert not (tmp_path / (scenario + ".json")).exists()


def test_unregistered_operation_refuses_before_draws_or_output(tmp_path, monkeypatch):
    fixture = g.generate_fixture_unit(g.SourceSlot("N01", 0, "test", 0))

    def violation(*args, **kwargs):
        pytest.fail("unregistered operation attempted generation or publication")

    monkeypatch.setattr(g, "_rng", violation)
    monkeypatch.setattr(stream, "write_stream_artifact", violation)
    bogus = SimpleNamespace(allow_fixture=False, root=tmp_path, registration_sha256="1"*64,
                            protocol_sha256="2"*64)
    forged = {"status": "registered", "sha256": "3"*64}
    with pytest.raises(g.RegistrationUnavailable, match="independently authenticated I1"):
        g.generate_registered_unit(fixture.slot, context=bogus, protocol_ref=forged)
    with pytest.raises(g.RegistrationUnavailable, match="I1"):
        g.write_fixture_unit(fixture, context=bogus, protocol_ref=forged)
    assert not list(tmp_path.iterdir())


@pytest.fixture
def excluded_campaign(tmp_path):
    if os.name != "nt":
        pytest.skip("campaign durability exercises actual Win32 persistence calls")
    slots = tuple(g.SourceSlot(family, 0, "train", 0) for family in ("N01", "N02"))
    root, supervisor = tmp_path / "artifacts", tmp_path / "supervisor"
    supervisor.mkdir()
    context, protocol = _fixture_context(root, g.generate_fixture_unit(slots[0]))
    (root / ".generation.lease").write_bytes(b"excluded fixture output lease")
    entries = tuple(g._campaign_entry({}, slot)[0] for slot in slots)
    plan_sha = digest({"fixture-entries": entries})
    frontier = supervisor / "frontier.json"
    frontier.with_name("frontier.json.lease").write_bytes(b"excluded fixture campaign lease")
    initial = c.canonical_bytes({"schema": g._CAMPAIGN_FRONTIER, "plan_sha256": plan_sha,
                                 "next": 0, "last_sha256": None, "attempt": None})
    frontier.write_bytes(initial)
    draws = []

    @contextmanager
    def authorize(ordinal, slot, entry):
        assert (slots[ordinal], entries[ordinal]) == (slot, entry)

        def make_unit():
            draws.append(ordinal)
            return g.generate_fixture_unit(slot)

        yield make_unit, lambda: None

    def run(*, end=2, expected=None, budget=60):
        return g._run_campaign(
            context, protocol, plan_sha256=plan_sha, slots=slots, entries=entries,
            frontier_path=frontier, expected_frontier_sha256=expected or c.digest(frontier.read_bytes()),
            end=end, max_wall_seconds=budget, authorize=authorize,
        )

    return SimpleNamespace(root=root, supervisor=supervisor, frontier=frontier, initial=initial,
                           slots=slots, draws=draws, run=run, plan_sha=plan_sha,
                           journal=root / ".generation")


def test_real_excluded_campaign_resume_recovers_identical_published_bytes(excluded_campaign, monkeypatch):
    f = excluded_campaign
    durable = g._durable_write

    def fail_after_publication(path, raw, **options):
        if path == f.journal / "00000.json":
            raise OSError("excluded crash before completion")
        durable(path, raw, **options)

    with monkeypatch.context() as mutation:
        mutation.setattr(g, "_durable_write", fail_after_publication)
        with pytest.raises(OSError, match="excluded crash before completion"):
            f.run()
    frontier = c.strict_loads(f.frontier.read_bytes())
    assert f.draws == [0] and frontier["next"] == 0 and frontier["attempt"]["ready_sha256"]
    first = f.root / f.slots[0].source_id
    previously_published = {path.name: path.read_bytes() for path in first.iterdir()}
    assert len(previously_published) == 2
    resumed = f.run()
    assert resumed["complete"] and resumed["source_count"] == resumed["frame_count"] == 2
    assert f.draws == [0, 1]
    assert previously_published == {path.name: path.read_bytes() for path in first.iterdir()}
    assert not (f.journal / "attempt-00000" / "artifacts").exists()
    assert f.run() == resumed and f.draws == [0, 1]


def test_real_campaign_lease_frontier_rollback_and_output_owner(excluded_campaign):
    f = excluded_campaign
    with g._campaign_lease(f.frontier.with_name("frontier.json.lease")):
        with pytest.raises(c.ContractError, match="lease is held"):
            f.run()
    with g._campaign_lease(f.root / ".generation.lease"):
        with pytest.raises(c.ContractError, match="lease is held"):
            f.run()
    occupied = f.root / f.slots[0].source_id
    occupied.mkdir()
    with pytest.raises(c.ContractError, match="no authorized attempt"):
        f.run()
    assert f.draws == [] and f.frontier.read_bytes() == f.initial
    occupied.rmdir()
    admitted = f.run(end=1)
    assert admitted["source_count"] == 1 and not admitted["complete"] and f.draws == [0]
    with pytest.raises(c.ContractError, match="changed or rolled back"):
        f.run(expected=c.digest(f.initial))
    (f.journal / "00000.json").unlink()
    with pytest.raises(c.ContractError, match="invalid bounded campaign record"):
        f.run(expected=admitted["frontier_sha256"])
    assert f.draws == [0]


def test_adversarial_campaign_timeout_and_ambiguous_attempt_never_redraw(excluded_campaign, monkeypatch):
    f = excluded_campaign
    ticks = iter((0, 2))
    with monkeypatch.context() as mutation:
        mutation.setattr(g, "monotonic", lambda: next(ticks))
        with pytest.raises(c.ContractError, match="wall-time budget exhausted"):
            f.run(budget=1)
    assert not f.journal.exists() and f.draws == []

    def crash_after_draw(context, protocol, stage, slot, entry, make_unit):
        make_unit()
        raise TimeoutError("excluded timeout before durable staged value")

    with monkeypatch.context() as mutation:
        mutation.setattr(g, "_stage_campaign_unit", crash_after_draw)
        with pytest.raises(TimeoutError, match="excluded timeout"):
            f.run()
    frontier = c.strict_loads(f.frontier.read_bytes())
    assert f.draws == [0] and frontier["next"] == 0 and frontier["attempt"]["ready_sha256"] is None
    with pytest.raises(c.ContractError, match="ambiguous campaign attempt after intent"):
        f.run()
    assert f.draws == [0]


def test_campaign_reconciliation_refuses_changed_published_bytes(excluded_campaign, monkeypatch):
    f = excluded_campaign
    durable = g._durable_write

    def fail_before_completion(path, raw, **options):
        if path == f.journal / "00000.json":
            raise OSError("excluded cutoff")
        durable(path, raw, **options)

    with monkeypatch.context() as mutation:
        mutation.setattr(g, "_durable_write", fail_before_completion)
        with pytest.raises(OSError, match="excluded cutoff"):
            f.run()
    published = next((f.root / f.slots[0].source_id).glob("*-f00.json"))
    published.write_bytes(b"altered")
    with pytest.raises(c.ContractError, match="I1 evidence byte identity mismatch"):
        f.run()
    assert published.read_bytes() == b"altered" and f.draws == [0]


def test_owned_frontier_anchors_ready_bytes_and_can_reconcile_existing_completion(excluded_campaign, monkeypatch):
    f = excluded_campaign
    durable = g._durable_write

    def fail_advancing_after_completion(path, raw, **options):
        if path == f.frontier and c.strict_loads(raw)["next"] == 1:
            raise OSError("excluded crash after completion")
        durable(path, raw, **options)

    with monkeypatch.context() as mutation:
        mutation.setattr(g, "_durable_write", fail_advancing_after_completion)
        with pytest.raises(OSError, match="excluded crash after completion"):
            f.run()
    assert (f.journal / "00000.json").is_file()
    frontier = c.strict_loads(f.frontier.read_bytes())
    assert frontier["next"] == 0 and frontier["attempt"]["ready_sha256"]
    ready = f.journal / "attempt-00000" / "ready.json"
    original = ready.read_bytes()
    ready.write_bytes(c.canonical_bytes({**c.strict_loads(original), "generator_sha256": "1"*64}))
    with pytest.raises(c.ContractError, match="independently anchored attempt"):
        f.run()
    assert f.draws == [0]
    ready.write_bytes(original)
    assert f.run()["complete"] and f.draws == [0, 1]
