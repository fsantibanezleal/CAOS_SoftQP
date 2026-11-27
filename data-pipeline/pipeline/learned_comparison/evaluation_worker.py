"""Timed installed-SDK routes for one held-out physical frame."""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import os
import time
from weakref import WeakSet

from . import contracts as c

BASE = dict(eps_abs=1e-7, eps_rel=1e-7, max_iter=200000, rho=.1, rho_is_vec=False,
            sigma=1e-6, alpha=1.6, scaling=10, adaptive_rho=True, adaptive_rho_interval=25,
            polishing=False, check_termination=25, verbose=False)
DIRECTIONAL = {k: v for k, v in BASE.items() if k != "adaptive_rho_interval"}
DIRECTIONAL.update(scaling=0, adaptive_rho=False, row_normalization=True)
OFFICIAL_FLAGS = {"clarabel": "Solved", "proxqp": "PROXQP_SOLVED", "piqp": "PIQP_SOLVED"}
RAW_OFFICIAL_FLAGS = {"clarabel": "Solved", "proxqp": "QPSolverOutput.PROXQP_SOLVED", "piqp": "Status.PIQP_SOLVED"}
LIMITS = {"H": 1e-6, "G": 1e-6, "K": 1e-5, "F": 1e-5, "F_all": 1e-5, "D": 1e-7}
_VERIFIED_ORACLES = WeakSet()


def _unit_args(original):
    u = original["units"]
    return dict(variable_units=u["D_x"], row_units=u["D_r"], peak_units=u["D_t"], objective_unit=u["S_f"])


def _physical(original):
    import numpy as np
    from scipy.sparse import csc_matrix
    from softqp.peak import PeakGroup, PeakProblem
    from softqp.problem import Penalty, Problem

    def csc(matrix):
        return csc_matrix((np.asarray(matrix["data"], dtype=np.float64), matrix["indices"],
                           matrix["indptr"]), shape=matrix["shape"])

    args = (csc(original["P"]), np.asarray(original["q"], dtype=np.float64), csc(original["A"]),
            np.asarray([-np.inf if v is None else v for v in original["lower"]], dtype=np.float64),
            np.asarray([np.inf if v is None else v for v in original["upper"]], dtype=np.float64))
    if original["formulation"] == "peak":
        return PeakProblem(*args, tuple(PeakGroup(np.asarray(g["rows"]), np.asarray(g["lower_scale"]),
                                              np.asarray(g["upper_scale"]), g["linear"], g["quadratic"])
                                        for g in original["groups"]))
    return Problem(*args, Penalty(**{key: np.asarray(value, dtype=bool if key == "soft" else np.float64)
                                    for key, value in original["penalty"].items()}))


def _singleton(problem):
    import numpy as np
    from softqp.peak import PeakGroup, PeakProblem

    p = problem.penalty
    c.ensure(np.array_equal(p.lower_linear, p.upper_linear)
             and np.array_equal(p.lower_quadratic, p.upper_quadratic), "directional singleton not equivalent")
    groups = tuple(PeakGroup(np.asarray([i]), np.ones(1), np.ones(1), p.lower_linear[i], p.lower_quadratic[i])
                   for i in np.flatnonzero(p.soft))
    return PeakProblem(problem.P, problem.q, problem.A, problem.lower, problem.upper, groups)


def _epigraph(problem, x, y, candidate, diagnostics):
    """Translate SDK interval-side arrays to the canonical reader's row layout."""
    if problem["original"]["formulation"] != "peak":
        return
    o = problem["original"]
    lower, upper = [0.] * o["m"], [0.] * o["m"]
    t, mu = [0.] * len(o["groups"]), [0.] * len(o["groups"])
    for i, sign, value in zip(diagnostics["side_rows"], diagnostics["side_signs"], diagnostics["lambda_sides"]):
        (upper if sign == 1 else lower)[i] = value
    for gid, value, multiplier in zip(diagnostics["group_ids"], diagnostics["peak"], diagnostics["mu"]):
        t[gid], mu[gid] = value, multiplier
    candidate.update(lifted_x=x, lifted_y=y, epigraph=dict(lambda_lower=lower, lambda_upper=upper, t=t, mu=mu))


def _official(problem, method, units):
    from softqp.comparators.backend import solve_candidate
    from softqp.comparators.vertical import ComparatorSession

    session = ComparatorSession(problem, method, **units)
    raw = solve_candidate(method, *session.data[3])
    solved = raw.native_status == RAW_OFFICIAL_FLAGS[method]
    output = dict(native_flag=OFFICIAL_FLAGS[method] if solved else raw.native_status,
                  native_status=raw.native_status, x=None, y=None, lifted_x=None, lifted_y=None,
                  setup_seconds=raw.setup_seconds, solve_seconds=raw.solve_seconds, iterations=raw.iterations,
                  setup_wall_seconds=session.setup_wall_seconds)
    if solved:
        x, y, metrics = session.recover_metrics(raw)
        output.update(x=x, y=y, lifted_x=raw.x * session.data[4],
                      lifted_y=raw.y * (session.sf / session.data[5]), metrics=metrics)
    return output


def _stock_lift(problem, units):
    import osqp
    from scipy.sparse import triu
    from softqp.comparators.vertical import ComparatorSession

    session = ComparatorSession(problem, "clarabel", **units)
    P, q, A, lo, hi = session.data[0]
    model = osqp.OSQP()
    setup_start = time.perf_counter_ns()
    model.setup(triu(P, format="csc"), q, A, lo, hi, **BASE)
    setup_wall = (time.perf_counter_ns() - setup_start) / 1e9
    result = model.solve(raise_error=False)
    info = result.info
    output = dict(native_flag=info.status_val, native_status=info.status, x=None, y=None,
                  iterations=info.iter, setup_seconds=info.setup_time, setup_wall_seconds=setup_wall,
                  solve_seconds=info.solve_time)
    if info.status_val == 1:
        x, y = session.data[1](result.x, result.y)
        output.update(x=x, y=y, lifted_x=result.x, lifted_y=result.y)
        if session.peak:
            output["metrics"] = {"epigraph": session._epigraph(result.x, result.y, session.data[2])}
    return output


def _legacy_daqp(problem, units, *, peak):
    from importlib.metadata import version

    import daqp
    import numpy as np
    from softqp.comparators.vertical import ComparatorSession
    from softqp.problem import Penalty, Problem
    from softqp.solvers import _daqp_controls, _read_daqp

    c.ensure(version("softqp") == "0.3.0" and version("daqp") == "0.10.3", "unreviewed DAQP adapter version")
    session = ComparatorSession(problem, "clarabel", **units) if peak else None
    if session is not None:
        P, q, A, lower, upper = session.data[0]
        physical = Problem(P, q, A, lower, upper, Penalty.uniform(len(lower), soft=False))
    else:
        physical = problem
    physical.validate()
    n, m = physical.A.shape[1], physical.A.shape[0]
    c.ensure(n <= 2048 and m <= 8192, "DAQP dense reference budget exceeded")
    def raw(data):
        return np.ascontiguousarray(data, dtype=np.float64)
    H = raw(physical.P.toarray())
    np.linalg.cholesky(H)
    penalty = physical.penalty
    c.ensure(not np.any(penalty.soft & np.isfinite(physical.lower) & (penalty.lower_quadratic <= 0))
             and not np.any(penalty.soft & np.isfinite(physical.upper) & (penalty.upper_quadratic <= 0)),
             "DAQP requires positive curvature on each finite soft side")
    controls = _daqp_controls(dict(eps_abs=1e-7, eps_rel=1e-7, max_iter=200000))
    controls["eq_reduction"] = -1
    model = daqp.Model()
    model.settings = controls

    def observed():
        settings = model.settings
        result = {name: settings.get(name) for name in controls}
        c.ensure(result == controls, "native DAQP effective settings differ from R4")
        return result

    before_setup = observed()
    sense = np.where(penalty.soft, 8, np.where(physical.lower == physical.upper, 5, 0)).astype(np.intc)
    setup_flag, setup_seconds = model.setup(H, raw(physical.q), raw(physical.A.toarray()),
                                          raw(physical.upper), raw(physical.lower), sense)
    c.ensure(setup_flag >= 0, f"DAQP native setup flag {setup_flag}")
    side_weights = None
    if np.any(penalty.soft):
        def reciprocal(quadratic):
            return np.divide(1., quadratic, out=np.zeros(m), where=penalty.soft & (quadratic > 0))

        side_weights = dict(rho_l=reciprocal(penalty.lower_quadratic), rho_u=reciprocal(penalty.upper_quadratic),
                            w_l=raw(penalty.lower_linear), w_u=raw(penalty.upper_linear))
        model.soft_weights(**side_weights)
    after_setup = observed()
    result, x, y, _, settings = _read_daqp(physical, model, setup_seconds)
    after_solve = observed()

    info = result.info
    output = dict(native_flag=info.status_val, native_status=info.status, x=None, y=None,
                  iterations=info.iter, setup_seconds=info.setup_time, solve_seconds=info.solve_time,
                  backend_settings=settings, native_sense=sense, side_weights=side_weights,
                  observed_controls={"before_setup": before_setup, "after_setup": after_setup, "after_solve": after_solve})
    if info.status_val in (1, 2):
        if session is None:
            output.update(x=x, y=y)
        else:
            original_x, original_y = session.data[1](x, y)
            output.update(x=original_x, y=original_y, lifted_x=x, lifted_y=y,
                          metrics={"epigraph": session._epigraph(x, y, session.data[2])})
    return output


def _learned(problem, method, units, model_scope, previous):
    from softqp.learning.solvers import InferenceBinding, PreparedLearningProblem, previous_working_set, solve_daqp, solve_osqp

    prepared = PreparedLearningProblem(problem, **units)
    mode, solver = method.split("_")
    arguments = {}
    if mode == "learned":
        if model_scope is None:
            return {"native_flag": None, "x": None, "y": None, "missing": "frozen checkpoint or calibration absent"}, None
        model, normalizer, weight_sha, threshold = model_scope
        binding = InferenceBinding(prepared.transform_sha256, weight_sha,
                                   normalizer.numeric_sha256 if normalizer is not None else None, threshold)
        arguments.update(model=model, binding=binding)
        if solver == "osqp":
            arguments["normalizer"] = normalizer
    if mode == "previous" and previous is not None:
        old, observation = previous
        if solver == "osqp":
            arguments["previous"] = (observation["lifted_x"], observation["lifted_y"])
        else:
            # SDK helper ultimately uses robust_labels from the previous original
            # input and rechecks unchanged exact map before making any flags.
            arguments["previous"] = previous_working_set(old, observation, prepared)
    result = (solve_osqp if solver == "osqp" else solve_daqp)(prepared, mode=mode, **arguments)
    if solver == "daqp" and result.get("lifted_x") is not None:
        session = prepared._session
        result["physical_lifted_x"] = result["lifted_x"] * session.data[4]
        result["physical_lifted_y"] = result["lifted_y"] * (session.sf / session.data[5])
    previous_state = (prepared, result) if mode == "previous" else None
    return result, previous_state


def load_numeric_model(*, method, seed, shape, weights, weights_sha256, normalizer, prior, threshold):
    """Load one already-authenticated immutable bundle outside steady-state timing."""
    from softqp.learning.fixed_point import L2WSHead, Normalizer
    from softqp.learning.parameters import load_weights

    if method == "learned_osqp":
        c.ensure(normalizer is not None and prior is threshold is None, "wrong frozen L2WS model scope")
        model = L2WSHead(*shape, seed)
        fitted = Normalizer.from_admitted(normalizer["mean"], normalizer["scale"], normalizer["source_ids"],
                                         normalizer["frame_weights"])
        c.ensure(fitted.numeric_sha256 == normalizer["numeric_sha256"], "frozen normalizer digest differs")
    else:
        from softqp.learning.graph import GRID, ActiveSetGNN

        c.ensure(method == "learned_daqp" and normalizer is None and threshold in GRID,
                 "wrong frozen DAQP calibration scope")
        model = ActiveSetGNN(seed, prior)
        fitted = None
    load_weights(model, weights, expected_sha256=weights_sha256)
    model.eval()
    return model, fitted, weights_sha256, threshold


def _route(problem, method, model_scope, previous):
    from softqp.peak import solve_peak
    from softqp.solvers import solve

    original = problem["original"]
    p = _physical(original)
    units = _unit_args(original)
    peak = original["formulation"] == "peak"
    if method in OFFICIAL_FLAGS:
        return _official(p, method, units), None
    if method in {"learned_osqp", "cold_osqp", "previous_osqp", "learned_daqp", "cold_daqp", "previous_daqp"}:
        return _learned(p, method, units, model_scope, previous)
    if method == "lifted":
        return _stock_lift(p, units), None
    if method == "daqp":
        return _legacy_daqp(p, units, peak=peak), None
    if method == "directional":
        output = solve_peak(p if peak else _singleton(p), method="native", **DIRECTIONAL)
    elif method == "flex":
        from softqp.flex import solve_flex

        output = solve_flex(p, eps_abs=1e-7, eps_rel=1e-7, max_iter=200000,
                            rho=1, sigma_x=1e-6, sigma_s=1, alpha=1.6)
    elif method == "elastiqp":
        from softqp.elasti import solve_elastiqp

        output = solve_elastiqp(p, eps_abs=1e-7, eps_rel=1e-7, max_iter=200000)
    else:
        c.ensure(method in {"generalized", "asymmetric"}, "unknown evaluation route")
        output = solve(p, method=method, **BASE)
    output["native_flag"] = output["status_code"]
    if method == "elastiqp":
        output["native_flag"] = "Solved" if (output["status"], output["status_code"]) == ("Status.Solved", 1) else output["status"]
    return output, None


def _numeric_json(value):
    if is_dataclass(value):
        value = asdict(value)
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, dict):
        return {key: _numeric_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_numeric_json(item) for item in value]
    if isinstance(value, float) and value == 0:
        return 0.0
    return value


def _candidate(problem, method, result, f_ref):
    candidate = {key: _numeric_json(result.get(key)) for key in ("x", "y")}
    candidate.update(lifted_x=None, lifted_y=None, epigraph=None)
    flag = result["native_flag"]
    if method == "daqp":
        verify_legacy_daqp(problem, result)
    expected = _success_flags(method)
    if result.get("missing"):
        return "missing", result["missing"], candidate, None
    if flag not in expected:
        return "failed", "native flag outside registered success alphabet", candidate, None
    if candidate["x"] is None or candidate["y"] is None:
        return "accuracy-rejected", "native success lacked finite original candidate", candidate, None
    metrics = c.original_metrics(problem["original"], candidate, f_ref)
    if method in OFFICIAL_FLAGS or method == "lifted" or "_" in method or (
        method == "daqp" and problem["original"]["formulation"] == "peak"
    ):
        x, y = (_numeric_json(result.get(f"physical_{key}", result.get(key))) for key in ("lifted_x", "lifted_y"))
        if x is None or y is None:
            return "accuracy-rejected", "lifted route lacked raw canonical interval evidence", candidate, metrics
        candidate.update(lifted_x=x, lifted_y=y)
    if problem["original"]["formulation"] == "peak" and method != "directional":
        diag = (result.get("metrics") or {}).get("epigraph")
        if diag is None or candidate["lifted_x"] is None:
            return "accuracy-rejected", "peak route lacked raw canonical interval evidence", candidate, metrics
        _epigraph(problem, candidate["lifted_x"], candidate["lifted_y"], candidate, _numeric_json(diag))
    c._recovery(problem, candidate)
    if not all(metrics[key] <= bound for key, bound in LIMITS.items()):
        return "accuracy-rejected", "original-space numerical gate", candidate, metrics
    return "accepted", None, candidate, metrics


def _success_flags(method):
    if method.endswith("daqp"):
        return (1, 2)
    if method in OFFICIAL_FLAGS:
        return (OFFICIAL_FLAGS[method],)
    return ("Solved",) if method == "elastiqp" else (1,)


def verify_legacy_daqp(problem, result):
    """Recompute native sense/weights and check the sealed effective settings."""
    required = dict(primal_tol=1e-7, dual_tol=1e-7, iter_limit=200000, w_soft=0., eps_prox=0., eq_reduction=-1)
    stages = result.get("observed_controls")
    c.ensure(stages == dict.fromkeys(("before_setup", "after_setup", "after_solve"), required)
             and all(result["backend_settings"].get(key) == value for key, value in required.items()),
             "legacy DAQP settings evidence differs from R4")
    original = problem["original"]
    peak = original["formulation"] == "peak"
    rows = problem["transform"] if peak else original
    penalty = original["penalty"]
    soft = [False] * rows["m"] if peak else penalty["soft"]
    senses = [8 if elastic else 5 if lower is not None and lower == upper else 0
              for elastic, lower, upper in zip(soft, rows["lower"], rows["upper"])]
    c.ensure(_numeric_json(result.get("native_sense")) == senses, "legacy DAQP sense evidence differs")
    weights = None
    if any(soft):
        weights = {"rho_l": [1/q if s and q > 0 else 0. for s, q in zip(soft, penalty["lower_quadratic"])],
                   "rho_u": [1/q if s and q > 0 else 0. for s, q in zip(soft, penalty["upper_quadratic"])],
                   "w_l": penalty["lower_linear"], "w_u": penalty["upper_linear"]}
    c.ensure(_numeric_json(result.get("side_weights")) == weights, "legacy DAQP side weights evidence differs")


@dataclass(frozen=True, eq=False)
class VerifiedFrameOracle:
    frame_sha256: str
    original_sha256: str
    transform_sha256: str
    rows_sha256: str
    objective: float | None


@dataclass(frozen=True)
class PreviousVector:
    key: tuple
    sdk_state: tuple


def _previous_vector(key, previous):
    method, seed, family, regime, unit, frame, phase, rep = key
    if not method.startswith("previous_"):
        c.ensure(previous is None, "primary trial received previous state")
        return None
    c.ensure(family == "N12", "previous control outside trajectory")
    if previous is None:
        return None
    expected = (method, seed, family, regime, unit, frame - 1, phase, rep)
    c.ensure(frame > 0 and type(previous) is PreviousVector and previous.key == expected,
             "previous vector crosses source, frame, phase or repetition")
    return previous.sdk_state


def verify_frame_oracle(problem, frame_sha256, rows, context, *, state, expected_rows_sha256):
    """Validate the sealed prior oracle output outside the timed candidate path."""
    outcome_digest = c.digest(c.canonical_bytes(rows))
    c.ensure(outcome_digest == expected_rows_sha256, "oracle differs from independent seal")
    if state == "oracle-agreed":
        objective = c._oracle(problem, rows, context)
    else:
        c.ensure(state == "oracle-failed", "unknown reference disposition")
        if all(row["accepted"] for row in rows):
            try:
                c._oracle(problem, rows, context)
            except c.ContractError as error:
                c.ensure(str(error) == "oracle objective disagreement", "invalid oracle failure ledger")
            else:
                raise c.ContractError("sealed oracle disagreement did not occur")
        else:
            c._failed_oracles(rows, context)
        objective = None
    receipt = VerifiedFrameOracle(frame_sha256, problem["original_sha256"], problem["transform_sha256"],
                                  outcome_digest, objective)
    _VERIFIED_ORACLES.add(receipt)
    return receipt


def evaluate_trial(source_raw, frame_raw, *, key, nonce, oracle, model_scope=None, previous=None):
    """Pure numeric leaf operation. The guardian owns scheduling and deadline."""
    from . import stream_inputs as stream

    started = time.perf_counter_ns()
    method, seed, family, regime, unit, frame, phase, rep = key
    result, state = None, None
    numeric = {"status": "failed", "reason": None, "candidate": None, "metrics": None}
    try:
        source_doc, frame_doc = c.strict_loads(source_raw), c.strict_loads(frame_raw)
        c.ensure(source_raw == c.canonical_bytes(source_doc) and frame_raw == c.canonical_bytes(frame_doc),
                 "noncanonical source/frame bytes")
        c.ensure(source_doc["kind"] == stream.SOURCE and frame_doc["kind"] == stream.FRAME,
                 "wrong held-out physical input kind")
        source, frame_payload = source_doc["payload"], frame_doc["payload"]
        src = frame_payload["source"]
        c.ensure((src["family"], src["regime"], src["unit_index"], src["frame"], src["split"])
                 == (family, regime, unit, frame, "test"), "frame outside timed test scope")
        c.ensure(frame_payload["source_ref"]["sha256"] == c.digest(source_raw) and
                 frame_payload["source_ref"]["artifact_id"] == source_doc["artifact_id"],
                 "timed source/frame link differs")
        problem = stream._reconstruct(source, frame_payload)
        preprocessed = time.perf_counter_ns()
        if oracle is not None:
            c.ensure(oracle in _VERIFIED_ORACLES and oracle.frame_sha256 == c.digest(frame_raw)
                     and (oracle.original_sha256, oracle.transform_sha256)
                     == (problem["original_sha256"], problem["transform_sha256"]),
                     "unverified reference or different test frame")
        if oracle is None or oracle.objective is None:
            numeric.update(status="oracle-failed", reason="independently verified reference absent")
        else:
            sdk_previous = _previous_vector(key, previous)
            numeric["previous_failure_reset"] = method.startswith("previous_") and frame > 0 and sdk_previous is None
            result, state = _route(problem, method, model_scope, sdk_previous)
            status, reason, candidate, metrics = _candidate(problem, method, result, oracle.objective)
            numeric.update(status=status, reason=reason, candidate=candidate, metrics=metrics)
            if state is not None and status == "accepted":
                result["status"] = "accepted"
                state = PreviousVector(tuple(key), state)
            else:
                state = None
        numeric["preprocess_ns"] = preprocessed - started
    except (ArithmeticError, AttributeError, ImportError, KeyError, TypeError, ValueError) as error:
        numeric.update(status="failed", reason=f"{type(error).__name__}: {error}"[:1000])
        state = None
    ended = time.perf_counter_ns()
    if result is not None and numeric["candidate"] is not None:
        repeated = {"x", "y", "metrics", "lifted_x", "lifted_y", "physical_lifted_x", "physical_lifted_y"}
        numeric["native"] = _numeric_json({key: value for key, value in result.items() if key not in repeated})
    else:
        numeric["native"] = _numeric_json(result)
    numeric.update(key=list(key), nonce=nonce, pid=os.getpid(), started_ns=started, ended_ns=ended)
    return numeric, state


def verify_numeric_output(problem, method, output, *, oracle):
    """Consumer-side acceptance using independently verified source and oracle."""
    c.ensure(output["key"][0] == method, "relabelled evaluation numeric method")
    if oracle is not None:
        c.ensure(oracle in _VERIFIED_ORACLES and (oracle.original_sha256, oracle.transform_sha256) ==
                 (problem["original_sha256"], problem["transform_sha256"]), "unverified evaluation reference")
    candidate = output["candidate"]
    if output["status"] != "accepted":
        c.ensure(type(output["reason"]) is str and output["reason"], "numeric failure lacks reason")
        return
    c.ensure(oracle is not None and oracle.objective is not None and
             output["reason"] is None and candidate is not None and
             output["native"]["native_flag"] in _success_flags(method), "unqualified native trial")
    if method in OFFICIAL_FLAGS or method == "lifted" or "_" in method or (
        method == "daqp" and problem["original"]["formulation"] == "peak"
    ):
        c.ensure(candidate["lifted_x"] is not None and candidate["lifted_y"] is not None,
                 "accepted trial lacks canonical raw recovery evidence")
    if method == "daqp":
        verify_legacy_daqp(problem, output["native"])
    c._recovery(problem, candidate)
    metrics = c.original_metrics(problem["original"], candidate, oracle.objective)
    c.ensure(output["metrics"] == metrics and all(metrics[key] <= bound for key, bound in LIMITS.items()),
             "observed original-space metrics differ from independently checked candidate")


def main_verified(root, *, slot_floor, settings_hashes, model_binding, startup_sha256, require_live, deadline_ns):
    """Execute fixed candidate packets in an already verified, owned leaf."""
    from types import SimpleNamespace

    from . import evaluation as e
    from . import evaluation_dispatch as transport
    from . import stream_inputs as stream

    context = SimpleNamespace(settings_hashes=dict(settings_hashes))
    ordinal = slot_floor
    previous = last_key = None
    while True:
        require_live()
        prefix = root / f"trial-{ordinal:06d}"
        request_path = prefix.with_suffix(".request")
        while not request_path.is_file():
            if (root / "stop.json").is_file():
                c.ensure(transport._read_packet(root / "stop.json", deadline=deadline_ns) ==
                         {"next_ordinal": ordinal}, "candidate leaf shutdown identity differs")
                require_live()
                return
            if time.perf_counter_ns() >= deadline_ns:
                raise TimeoutError("candidate leaf reached the bake deadline")
            time.sleep(.005)
        req = transport._read_packet(request_path, deadline=deadline_ns)
        required = {"key", "ordinal", "owner", "nonce", "released_ns", "deadline_ns", "raw_sha256", "outcome"}
        c.ensure(set(req) == required and req["ordinal"] == ordinal and len(req["key"]) == 8 and
                 e.is_sha256(req["raw_sha256"]["source"]) and e.is_sha256(req["raw_sha256"]["frame"]) and
                 req["released_ns"] <= time.perf_counter_ns() < req["deadline_ns"] <= deadline_ns and
                 req["deadline_ns"] - req["released_ns"] <= e.TRIAL_NS, "candidate leaf request scope differs")
        key = tuple(req["key"])
        method, seed, _, _, _, frame, _, _ = key
        started = time.perf_counter_ns()
        raw = {}
        for kind in ("source", "frame"):
            with prefix.with_suffix("." + kind).open("rb") as source:
                raw[kind] = source.read(e.MAX_RESULT_BYTES + 1)
            c.ensure(len(raw[kind]) <= e.MAX_RESULT_BYTES and c.digest(raw[kind]) == req["raw_sha256"][kind],
                     "candidate raw transport bytes differ")
        src, frame_doc = (c.strict_loads(raw[k]) for k in ("source", "frame"))
        problem = stream._reconstruct(src["payload"], frame_doc["payload"])
        outcome = req["outcome"]
        rows = outcome["oracle_rows"]
        oracle = None
        if rows and all(row["accepted"] for row in rows):
            try:
                oracle = verify_frame_oracle(problem, req["raw_sha256"]["frame"], rows, context,
                                             state="oracle-agreed", expected_rows_sha256=c.digest(c.canonical_bytes(rows)))
            except c.ContractError as error:
                c.ensure(str(error) == "oracle objective disagreement", "candidate oracle evidence differs")
        lost_previous = (method.startswith("previous_") and frame > 0 and
                         last_key != (*key[:5], frame - 1, *key[6:]))
        head = model_scope = checkpoint_sha = model_failure = None
        if method in c.LEARNED:
            head = ("graph" if method == "learned_daqp" else
                    f"H-{problem['transform']['n']}-{problem['transform']['m']}")
            model_scope, checkpoint_sha, model_failure = model_binding(method, seed, head)
        if model_failure is not None:
            state, reason = model_failure
            result = dict(key=list(key), nonce=req["nonce"], pid=os.getpid(), started_ns=started,
                          status=state, reason=reason, candidate=None, metrics=None, native=None)
            previous = None
        elif lost_previous:
            result = dict(key=list(key), nonce=req["nonce"], pid=os.getpid(), started_ns=started,
                          status="failed", reason="previous-state-unknown-after-interruption",
                          candidate=None, metrics=None, native=None)
            previous = None
        else:
            result, previous = evaluate_trial(raw["source"], raw["frame"], key=key, nonce=req["nonce"],
                                              oracle=oracle, model_scope=model_scope,
                                              previous=previous if method.startswith("previous_") and frame > 0 else None)
            verify_numeric_output(problem, method, result, oracle=oracle)
        result.update(model_load_ns=0, head=head, startup_sha256=startup_sha256,
                      raw_sha256=req["raw_sha256"], checkpoint_sha256=checkpoint_sha,
                      settings_sha256=settings_hashes.get(method),
                      outcome_sha256=c.digest(c.canonical_bytes(outcome)))
        require_live()
        result["ended_ns"] = time.perf_counter_ns()
        if result["ended_ns"] >= req["deadline_ns"]:
            raise TimeoutError("candidate numeric leaf exceeded whole trial window")
        transport._published_packet(prefix.with_suffix(".result"), result)
        last_key = key
        ordinal += 1
