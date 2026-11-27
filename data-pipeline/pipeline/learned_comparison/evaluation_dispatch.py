"""Fixed candidate parent, supervised packet transport and durable writer."""

from pathlib import Path
import os
import secrets
import shutil
import time
from types import SimpleNamespace

from .candidate_startup import TimingCohorts, cohort_plan, verify_startup
from . import contracts as c
from . import evaluation as e
from . import heldout_inputs as heldout
from . import phase_inputs as phase


def _artifact_validator(name):
    path = c.SCHEMAS / f"softqp-{name}.schema.json"
    return c._validator(c._snapshot_bytes(path, schema=True))


def _write_packet(path, raw):
    c.ensure(len(raw) <= e.MAX_RESULT_BYTES, "candidate packet too large")
    with path.open("xb") as handle:
        handle.write(raw)
    return c.digest(raw)


def _read_packet(path, *, deadline):
    while True:
        if time.perf_counter_ns() >= deadline:
            raise TimeoutError(f"candidate {path.name} not observed by its deadline")
        try:
            with path.open("rb") as handle:
                raw = handle.read(e.MAX_RESULT_BYTES + 1)
        except FileNotFoundError:
            time.sleep(0.005)
            continue
        except PermissionError:
            # Windows can expose the final name before a concurrent atomic
            # rename releases its sharing guard. Keep the same absolute timer.
            if os.name != "nt":
                raise
            time.sleep(0.005)
            continue
        break
    c.ensure(len(raw) <= e.MAX_RESULT_BYTES, "candidate packet too large")
    value = c.strict_loads(raw)
    c.ensure(raw == c.canonical_bytes(value), "noncanonical candidate packet")
    if time.perf_counter_ns() >= deadline:
        raise TimeoutError(f"candidate {path.name} observed too late")
    return value


def _published_packet(path, value):
    pending = path.with_suffix(".pending")
    _write_packet(pending, c.canonical_bytes(value))
    pending.rename(path)


def _marker(root, index, kind):
    return root / f"trial-{index:06d}-{kind}.json"


def _seal_payload(root, raw):
    digest = c.digest(raw)
    path = root / (digest + ".json")
    if not path.exists():
        pending = path.with_suffix(".pending")
        e._write_exclusive(pending, raw)
        pending.rename(path)
    else:
        c.ensure(path.read_bytes() == raw, "candidate content-addressed payload changed")
    return {"path": path.name, "sha256": digest, "bytes": len(raw)}


class CandidateBroker:
    """Own an already admitted candidate proof and a fixed leaf lease."""

    def __init__(self, *, runtime, proof, view, leaf, markers, payloads):
        self.runtime = runtime
        self.proof = proof
        self.view = view
        self.leaf = leaf
        self.markers = markers
        self.payloads = payloads
        self.validate_receipt = _artifact_validator("candidate-trial-receipt").validate
        self.frames = view.frame_index()
        self.identities = view.identities()
        self.payload_bytes = sum(entry.stat().st_size for entry in payloads.iterdir())
        self._pending_paths = ()

    def clear_committed_transport(self):
        for path in self._pending_paths:
            path.unlink()
        self._pending_paths = ()

    def require_live(self):
        self.runtime.require_live()
        c.ensure(self.view.identities() == self.identities, "candidate proof custody changed")

    def observe_trial(self, key, *, ordinal, deadline_ns):
        self.require_live()
        self.clear_committed_transport()
        nonce = secrets.token_hex(16)
        request = {"key": list(key), "ordinal": ordinal, "owner": os.getpid(), "nonce": nonce}
        _published_packet(_marker(self.markers, ordinal, "ready"), request)
        release = _read_packet(_marker(self.markers, ordinal, "release"), deadline=deadline_ns)
        c.ensure(
            set(release) == set(request) | {"released_ns", "deadline_ns"}
            and all(release[field] == value for field, value in request.items())
            and release["deadline_ns"] <= deadline_ns
            and 0 < release["deadline_ns"] - release["released_ns"] <= e.TRIAL_NS,
            "candidate release marker differs",
        )
        frame_id = self.frames[tuple(key[2:6])]
        pair = self.proof.reader.read_sealed_frame_pair(frame_id)
        outcome = self.proof.read_outcome(frame_id)
        self.require_live()
        prefix = self.leaf.root / f"trial-{ordinal:06d}"
        raw_hashes = {
            name: _write_packet(prefix.with_suffix("." + name), pair[name + "_raw"])
            for name in ("source", "frame")
        }
        c.ensure(
            all(raw_hashes[name] == pair[name + "_ref"]["sha256"] for name in raw_hashes),
            "candidate transport opened alternate test bytes",
        )
        _published_packet(
            prefix.with_suffix(".request"),
            {
                **release,
                "raw_sha256": raw_hashes,
                "outcome": outcome,
            },
        )
        while True:
            seconds = (release["deadline_ns"] - time.perf_counter_ns()) / 1e9
            if seconds <= 0:
                raise TimeoutError("candidate getter exhausted whole-trial window")
            try:
                result = self.leaf.wait_file(prefix.with_suffix(".result"), seconds)
            except PermissionError:
                if os.name != "nt":
                    raise
                time.sleep(0.005)
                continue
            break
        c.ensure(
            result["key"] == list(key)
            and result["nonce"] == nonce
            and result["pid"] == self.leaf.candidate_pid
            and result["startup_sha256"] == self.leaf.startup_sha256
            and result["model_load_ns"] == 0
            and result["pid"] in self.leaf._pids(),
            "candidate response has foreign leaf identity",
        )
        c.ensure(
            result["raw_sha256"] == raw_hashes
            and result["outcome_sha256"] == c.digest(c.canonical_bytes(outcome)),
            "candidate leaf solved alternate test input or native outcome",
        )
        self.require_live()
        result_raw = c.canonical_bytes(result)
        numeric_sha = c.digest(result_raw)
        _published_packet(
            _marker(self.markers, ordinal, "observed"), dict(release, result_sha256=numeric_sha)
        )
        closed = _read_packet(_marker(self.markers, ordinal, "closed"), deadline=release["deadline_ns"])
        c.ensure(
            set(closed) == set(release) | {"result_sha256", "observed_ns"}
            and all(closed[k] == v for k, v in release.items())
            and closed["result_sha256"] == numeric_sha
            and release["released_ns"]
            <= result["started_ns"]
            < result["ended_ns"]
            <= closed["observed_ns"]
            < release["deadline_ns"],
            "candidate external end receipt differs",
        )
        c.ensure(
            self.payload_bytes
            + len(result_raw)
            + (self.payloads.parent / "candidate-journal.ndjson").stat().st_size
            <= e.BAKE_BYTES,
            "candidate numeric output exceeds aggregate 4 GiB budget",
        )
        ref = _seal_payload(self.payloads, result_raw)
        self.payload_bytes += len(result_raw)
        receipt = {
            "schema": "softqp.r4.heldout-trial-receipt/2",
            "key": list(key),
            "ordinal": ordinal,
            **{name: self.identities[name] for name in ("request_sha256", "policy_sha256", "profile_sha256")},
            "nonce": nonce,
            "owned_pid": result["pid"],
            "released_ns": release["released_ns"],
            "observed_ns": closed["observed_ns"],
            "numeric_sha256": numeric_sha,
            "full_cost_ns": closed["observed_ns"] - release["released_ns"],
            "numeric": ref,
            "frame_id": frame_id,
        }
        self.validate_receipt(receipt)
        self._pending_paths = tuple(
            prefix.with_suffix(ext) for ext in (".source", ".frame", ".request", ".result")
        ) + tuple(_marker(self.markers, ordinal, kind) for kind in ("ready", "release", "observed", "closed"))
        # The parent now has every byte and independent clock edge needed to
        # persist this exact trial. The kernel owner watches the bake separately.
        return {"state": result["status"], "reason": result["reason"], "receipt": receipt}


def dispatch_candidate(raw, custody):
    """Guardian-only parent route. No capability is issued by importing this module."""
    from softqp_candidate_runtime_custody import active_candidate

    runtime = active_candidate(custody, request_sha256=c.digest(raw), source_file=Path(__file__).resolve())
    proof = heldout.admit_candidate_inputs(raw, custody)
    view = heldout.candidate_view(proof)
    return run_candidate(runtime, proof, view)


def _schedule(authority, view):
    frame_index = view.frame_index()
    all_trials = e.execution_schedule(authority)
    if view.identities()["fixture_only"]:
        return tuple(row for row in all_trials if tuple(row[2:6]) in frame_index)
    c.ensure(len(frame_index) == 2208, "scientific candidate test projection is incomplete")
    rows = tuple(all_trials)
    expected = set(authority.keys("method-repetitions")) | set(authority.keys("control-repetitions"))
    c.ensure(
        len(rows) == len(expected) == 239960 and set(rows) == expected, "frozen candidate schedule differs"
    )
    return rows


def run_candidate(runtime, proof, view):
    """Bind the existing durable driver to one admitted owned candidate leaf."""
    from hashlib import sha256

    runtime.require_live()
    bake = runtime.bake_descriptor()
    ids = view.identities()
    c.ensure(
        all(
            bake[key] == ids[key]
            for key in (
                "request_sha256",
                "policy_sha256",
                "profile_sha256",
                "scope_sha256",
                "roster_sha256",
                "test_sha256",
                "native_sha256",
                "proof_sha256",
            )
        ),
        "candidate descriptor is from another scope",
    )
    authority = view.authority()
    schedule = _schedule(authority, view)
    cohorts = cohort_plan(authority, schedule)
    c.ensure(c.digest(c.canonical_bytes(cohorts)) == bake["cohort_sha256"],
             "candidate cohorts differ from independent bake pin")
    order = sha256()
    for key in schedule:
        order.update(c.canonical_bytes(list(key)))
    c.ensure(
        order.hexdigest() == bake["schedule_sha256"], "candidate order differs from independent bake pin"
    )
    journal_plan = c.digest(c.canonical_bytes({name: bake[name] for name in
                                             ("schedule_sha256", "timer_sha256")}))
    output = Path(bake["output_root"])
    c.ensure(
        shutil.disk_usage(output.parent).free >= 20 * 2**30, "candidate workspace free disk below 20 GiB"
    )
    if not output.exists():
        output.mkdir()
    output = phase._exact_directory(output)
    frontier = phase._exact_directory(Path(bake["frontier_root"])) / "frontier.json"
    payloads = output / "numeric"
    if not payloads.exists():
        payloads.mkdir()
    payloads = phase._exact_directory(payloads)
    journal = output / "candidate-journal.ndjson"
    with e.EvaluationJournal(
        journal,
        frontier,
        expected_frontier_sha256=bake["frontier_sha256"],
        plan_sha256=journal_plan,
        schedule=schedule,
    ) as ledger:
        if ledger._state["active"] is not None:
            ledger.reconcile()
        leaf = None
        try:
            if ledger.next_key is not None:
                leaf = runtime.open_leaf(
                    output / f"worker-{ledger._state['next']:06d}", ledger._state["next"], view
                )
                broker = CandidateBroker(
                    runtime=runtime,
                    proof=proof,
                    view=view,
                    leaf=leaf,
                    markers=runtime.marker_root,
                    payloads=payloads,
                )
                result = e.drive_bake(ledger, broker, deadline_ns=runtime.deadline_ns)
                broker.clear_committed_transport()
                _published_packet(leaf.root / "stop.json", {"next_ordinal": result["next_ordinal"]})
                c.ensure(leaf.process.wait(timeout=30) == 0, "candidate leaf did not close cleanly")
            else:
                result = {
                    "state": "complete",
                    "next_ordinal": ledger._state["next"],
                    "frontier_sha256": ledger.expected,
                    "reason": None,
                }
        finally:
            if leaf is not None:
                leaf.close()
    runtime.require_live()
    exported = _export(runtime, proof, view, output, frontier, journal, bake, result, journal_plan,
                       cohorts=cohorts)
    return {"schema": "softqp.r4.candidate-run/1", **ids, **result, "export": exported}


def _numeric_receipt(proof, view, output, slot, trial, *, frames=None, timing=None, startups=None,
                     validate_receipt=None):
    from . import evaluation_worker as numeric
    from . import stream_inputs as stream

    receipt = trial["receipt"]
    if validate_receipt is None:
        validate_receipt = _artifact_validator("candidate-trial-receipt").validate
    key = (*slot, trial["phase"], trial["rep"])
    ids = view.identities()
    ref = receipt["numeric"]
    frame_id = (view.frame_index() if frames is None else frames)[tuple(slot[2:6])]
    c.ensure(
        receipt["schema"] == "softqp.r4.heldout-trial-receipt/2"
        and receipt["key"] == list(key)
        and receipt["frame_id"] == frame_id
        and all(receipt[name] == ids[name] for name in ("request_sha256", "policy_sha256", "profile_sha256"))
        and e.is_sha256(receipt["numeric_sha256"])
        and ref["sha256"] == receipt["numeric_sha256"]
        and ref["path"] == ref["sha256"] + ".json"
        and 0 < ref["bytes"] <= e.MAX_RESULT_BYTES,
        "candidate numeric custody receipt differs",
    )
    raw = phase._open_bytes(output / "numeric", ref["path"], single_link=True)
    value = c.strict_loads(raw)
    if timing is not None:
        startup = startups.get(value["startup_sha256"])
        c.ensure(startup is not None and startup["pid"] == value["pid"]
                 and startup["ready_ns"] <= receipt["released_ns"]
                 and startup["slot_floor"] <= receipt["ordinal"] and value["model_load_ns"] == 0,
                 "candidate trial lacks the exact prior startup observation")
        if value["checkpoint_sha256"] is not None:
            group = timing.frames[tuple(slot)]
            c.ensure(value["head"] == group[2] and any(
                (entry["method"], entry["seed"], entry["head"], entry.get("checkpoint_sha256"))
                == (*group, value["checkpoint_sha256"]) for entry in startup["heads"]),
                "candidate selected head differs from prospectively preloaded cohort")
    settings = view.settings_hashes()
    c.ensure(
        slot[0] in settings and value["settings_sha256"] == settings[slot[0]],
        "candidate numeric method settings provenance differs",
    )
    if slot[0] in c.LEARNED:
        from .evaluation_models import ModelTrust
        from .heldout_inputs import CandidateModelFailure

        binding = view.model_binding(*slot[:2])
        expected = binding.checkpoint_sha256 if type(binding) is ModelTrust else None
        c.ensure(
            value["checkpoint_sha256"] == expected
            and (expected is not None or value["status"] != "accepted"),
            "candidate frozen checkpoint differs",
        )
        if type(binding) is CandidateModelFailure:
            failure = c.strict_loads(binding.evidence)
            c.ensure(
                (value["status"], value["reason"]) == (failure["state"], failure["reason"]),
                "candidate typed model failure differs",
            )
    else:
        c.ensure(value["checkpoint_sha256"] is None, "deterministic candidate invented a model checkpoint")
    c.ensure(
        len(raw) == ref["bytes"]
        and c.digest(raw) == ref["sha256"]
        and raw == c.canonical_bytes(value)
        and value["key"] == list(key)
        and value["nonce"] == receipt["nonce"]
        and value["pid"] == receipt["owned_pid"]
        and value["status"] == trial["state"]
        and value["reason"] == trial["reason"]
        and receipt["released_ns"] <= value["started_ns"] < value["ended_ns"] <= receipt["observed_ns"]
        and 0 < receipt["observed_ns"] - receipt["released_ns"] == receipt["full_cost_ns"] < e.TRIAL_NS,
        "candidate numeric receipt or full-cost clock differs",
    )
    pair = proof.reader.read_sealed_frame_pair(frame_id)
    outcome = proof.read_outcome(frame_id)
    c.ensure(
        value["raw_sha256"] == {kind: pair[kind + "_ref"]["sha256"] for kind in ("source", "frame")}
        and value["outcome_sha256"] == c.digest(c.canonical_bytes(outcome)),
        "candidate original frame proof differs",
    )
    source, frame = (c.strict_loads(pair[kind + "_raw"]) for kind in ("source", "frame"))
    problem = stream._reconstruct(source["payload"], frame["payload"])
    oracle = None
    if trial["state"] == "accepted":
        rows = outcome["oracle_rows"]
        oracle = numeric.verify_frame_oracle(
            problem,
            pair["frame_ref"]["sha256"],
            rows,
            SimpleNamespace(settings_hashes=view.settings_hashes()),
            state="oracle-agreed",
            expected_rows_sha256=c.digest(c.canonical_bytes(rows)),
        )
    numeric.verify_numeric_output(problem, slot[0], value, oracle=oracle)
    validate_receipt(receipt)
    if timing is not None:
        timing.observe(slot, trial, value)
    return receipt["full_cost_ns"]


def _balanced_estimate(rows):
    cells = {}
    for row in rows:
        cells.setdefault((row["seed"], row["family"], row["regime"]), {})[row["source_index"]] = row[
            "reduction"
        ]
    family_values = {}
    for (seed, family, _regime), sources in sorted(cells.items()):
        c.ensure(set(sources) == set(range(8)), "candidate estimate source stratum incomplete")
        family_values.setdefault((seed, family), []).append(sum(sources[u] for u in range(8)) / 8)
    seed_values = {}
    for (seed, _family), values in sorted(family_values.items()):
        seed_values.setdefault(seed, []).append(sum(values) / len(values))
    c.ensure(
        tuple(seed_values) == c.SEEDS
        and all(
            {(f, r) for s, f, r in cells if s == seed} == {(f, r) for s, f, r in cells if s == c.SEEDS[0]}
            for seed in c.SEEDS
        ),
        "candidate seed/stratum roster differs",
    )
    return sum(sum(values) / len(values) for values in seed_values.values()) / len(c.SEEDS)


def _diagnostics(bake, authority, stage, *, frontier_root, output, byte_limit=e.BAKE_BYTES):
    slots = set(authority.keys("diagnostic-status"))
    rows = {}
    for ref in bake["diagnostics"]:
        c.ensure(
            type(ref) is dict
            and set(ref) == {"key", "path", "sha256"}
            and e.is_sha256(ref["sha256"])
            and tuple(ref["key"]) in slots
            and tuple(ref["key"]) not in rows,
            "candidate independent diagnostics inventory differs",
        )
        raw = phase._open_bytes(frontier_root, ref["path"], single_link=True)
        doc = c.strict_loads(raw)
        c.ensure(
            c.digest(raw) == ref["sha256"]
            and raw == c.canonical_bytes(doc)
            and doc["key"] == ref["key"]
            and doc.get("state") in {"passed", "failed", "missing"},
            "candidate diagnostic receipt differs",
        )
        rows[tuple(ref["key"])] = {**doc, "external_sha256": ref["sha256"]}
    complete = len(rows) == len(slots) and all(row["state"] == "passed" for row in rows.values())
    projected = (
        rows.get(key, {"key": list(key), "state": "missing", "reason": "independent-diagnostic-absent"})
        for key in sorted(slots)
    )
    remaining = byte_limit - _output_bytes(output)
    c.ensure(remaining > 0, "candidate diagnostics exceed output budget")
    return complete, e.write_json_lines(stage / "diagnostics.ndjson", projected, byte_limit=remaining)


def _output_bytes(root):
    return sum(phase._path_stat(path).st_size for path in root.rglob("*") if path.is_file())


def _export(runtime, proof, view, output, frontier, journal, bake, run, journal_plan, *, cohorts):
    runtime.require_live()
    final = output / "export"
    c.ensure(not final.exists(), "candidate export is already published")
    stage = output / (".export-stage-" + secrets.token_hex(12))
    stage.mkdir()
    reference = _stage_export(runtime, proof, view, output, stage, frontier, journal, bake, run,
                              journal_plan, cohorts=cohorts)
    runtime.require_live()
    # The owned stage only becomes visible under the fixed final name after
    # complete readback. Windows rename fails if another writer owns that name.
    stage.rename(final)
    return {"path": "export/" + reference["path"], "sha256": reference["sha256"]}


def _observed_startups(view, output):
    from .evaluation_models import ModelTrust

    roster = []
    for method in sorted(c.LEARNED):
        for seed in c.SEEDS:
            binding = view.model_binding(method, seed)
            identity = dict(method=method, seed=seed)
            if type(binding) is ModelTrust:
                identity.update(checkpoint_sha256=binding.checkpoint_sha256,
                                projection_sha256=binding.preprocessing_sha256,
                                calibration_sha256=binding.calibration_sha256)
            else:
                identity["failure"] = c.strict_loads(binding.evidence)
            roster.append(identity)
    ids = view.identities()
    heads = view.authority().matrix["heads"]
    observed = {}
    for worker in sorted(output.glob("worker-*")):
        if not (worker / "startup-observed.json").is_file():
            continue
        raw = phase._open_bytes(worker, "startup-observed.json", single_link=True)
        doc = c.strict_loads(raw)
        verify_startup(doc, expected_roster=roster, frozen_heads=heads)
        c.ensure(worker.name == f"worker-{doc['slot_floor']:06d}" and c.canonical_bytes(doc) == raw
                 and all(doc[key] == ids[key] for key in ("policy_sha256", "profile_sha256", "fixture_only")),
                 "candidate startup file identity differs")
        observed[c.digest(raw)] = doc
    return observed


def _stage_export(runtime, proof, view, output, stage, frontier, journal, bake, run, journal_plan, *, cohorts):
    authority = view.authority()
    frames = view.frame_index()
    ids = view.identities()
    timing = TimingCohorts(cohorts)
    startups = _observed_startups(view, output)
    fixture_frames = frozenset(frames) if ids["fixture_only"] else None
    validate_receipt = _artifact_validator("candidate-trial-receipt").validate
    tail = e.BAKE_BYTES - (_output_bytes(output) - journal.stat().st_size)
    statuses = e.project_status_journal(
        journal,
        frontier,
        expected_frontier_sha256=run["frontier_sha256"],
        authority=authority,
        plan_sha256=journal_plan,
        temporary_index=stage / "status-index.db",
        output=stage / "statuses.ndjson",
        missing_reason=run["reason"],
        byte_limit=tail,
        fixture_frames=fixture_frames,
    )
    status_path = stage / statuses["path"]
    counts = e.read_status_shard(
        status_path,
        statuses,
        (slot for slot in e.status_slots(authority)
         if fixture_frames is None or slot.key[2:6] in fixture_frames),
        verified_trial=lambda slot, trial: _numeric_receipt(
            proof, view, output, slot, trial, frames=frames, timing=timing, startups=startups,
            validate_receipt=validate_receipt,
        ),
    )
    complete_diag, diagnostics = _diagnostics(bake, authority, stage, frontier_root=frontier.parent, output=output)
    matrix_complete = all(count == 0 for state, count in counts.items()
                          if state not in {"accepted", "incompatible"})
    aggregate = e.MatchedTrajectoryTotals()
    from hashlib import sha256

    digest = sha256()
    with status_path.open("rb") as file:
        for raw in file:
            digest.update(raw)
            row = c.strict_loads(raw)
            timing.finish_frame(row)
            aggregate.add(row)
    c.ensure(
        digest.hexdigest() == statuses["sha256"], "candidate status projection changed during aggregation"
    )
    hypotheses = {}
    for method in sorted(c.LEARNED):
        estimate = aggregate.projection(method, diagnostics_complete=complete_diag)
        if estimate["state"] != "defined":
            hypotheses[method] = {
                "estimate": None,
                "interval": None,
                "qualified": False,
                "failed_statuses": estimate["failed_statuses"],
                "bootstrap": None,
            }
            continue
        totals = estimate["totals"]
        cells = sorted({(row["family"], row["regime"]) for row in totals})
        c.ensure(
            e.BAKE_BYTES - _output_bytes(output) >= 10000 * (3 + 8 * len(cells)),
            "candidate bootstrap exceeds aggregate 4 GiB budget",
        )
        draws = e.write_bootstrap_draws(stage, method, cells)
        interval = c._bootstrap_interval(
            totals, method, draws["file"], SimpleNamespace(root=stage, allow_fixture=False)
        )
        hypotheses[method] = {
            "estimate": _balanced_estimate(totals),
            "interval": interval,
            "qualified": interval[0] > 0.10,
            "failed_statuses": 0,
            "bootstrap": draws,
        }
    timing_rows = list(timing.rows(startups))
    timing_complete = all(row["reason"] is None for row in timing_rows)
    startup_rows = [{"sha256": key, "observation": startups[key]} for key in sorted(timing.startups)]
    remaining = e.BAKE_BYTES - _output_bytes(output)
    c.ensure(remaining > 0, "no output budget for candidate startup evidence")
    report = e.write_json_lines(stage / "startup.ndjson", startup_rows, byte_limit=remaining)
    remaining = e.BAKE_BYTES - _output_bytes(output)
    c.ensure(remaining > 0, "no output budget for candidate amortization")
    amortization = e.write_json_lines(stage / "amortization.ndjson", timing_rows, byte_limit=remaining)
    for ref, rows in ((report, startup_rows), (amortization, timing_rows)):
        reread = (stage / ref["path"]).read_bytes()
        c.ensure(c.digest(reread) == ref["sha256"] and reread == b"".join(map(c.canonical_bytes, rows)),
                 "candidate startup or amortization readback differs")
    document = {
        "schema": "softqp.r4.candidate-export/1",
        **ids,
        "schedule_sha256": bake["schedule_sha256"],
        "cohort_sha256": bake["cohort_sha256"],
        "frontier_sha256": run["frontier_sha256"],
        "statuses": statuses,
        "diagnostics": diagnostics,
        "counts": dict(counts),
        "matrix_complete": matrix_complete,
        "diagnostics_complete": complete_diag,
        "timing_complete": timing_complete,
        "startups": report,
        "amortization": amortization,
        "scientifically_qualified": (
            not ids["fixture_only"] and matrix_complete and complete_diag and timing_complete
            and all(row["qualified"] for row in hypotheses.values())
        ),
        "hypotheses": hypotheses,
    }
    raw = c.canonical_bytes(document)
    runtime.require_live()
    c.ensure(_output_bytes(output) + len(raw) <= e.BAKE_BYTES, "candidate export exceeds output budget")
    validate_export = _artifact_validator("candidate-export").validate
    validate_export(document)
    _published_packet(stage / "evaluation.json", document)
    verified = (stage / "evaluation.json").read_bytes()
    c.ensure(verified == raw, "candidate export changed before publication")
    validate_export(c.strict_loads(verified))
    return {"path": "evaluation.json", "sha256": c.digest(raw)}
