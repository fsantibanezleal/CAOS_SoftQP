"""Paired C12 cold/warm solver stream on a single independent plant trajectory."""

import hashlib
import json
from pathlib import Path
import time
import numpy as np
from softqp.sessions import PreparedSolver, DaqpWorkspace
from .softqp_cases import mpc
from .environment import environment
from .experiment_common import SETTINGS, acceptance, cold_observation, oracle

ROOT = Path(__file__).resolve().parents[2]


def run_stream(protocol=None):
    if protocol is None:
        protocol = json.loads((ROOT / "docs/design/experiments-v1.json").read_text(encoding="utf-8"))
    provenance = environment()
    if provenance["engine_revision"] != protocol["engine_source"] or provenance["engine_source_dirty"] is not False:
        raise RuntimeError("Stream requires the exact clean native source revision recorded in the protocol")
    spec = protocol["stream"]
    state = np.array(spec["initial_state"], dtype=float)
    dt = spec["dt_seconds"]
    F = np.array([[1.0, dt], [0.0, 1.0]])
    B = np.array([dt**2 / 2, dt])
    workspaces = {}
    frames = []
    for frame in range(spec["frames"]):
        impulse = spec["velocity_impulses"].get(str(frame), 0.0)
        state[1] += impulse
        start = time.perf_counter()
        problem = mpc(True, True, float(state[0]), float(state[1]))
        generation_seconds = time.perf_counter() - start
        reference, objective = oracle(problem)
        # The condensed objective excludes this state-dependent constant.
        offset = np.concatenate([np.linalg.matrix_power(F, k + 1) @ state for k in range(spec["horizon"])])
        constant = float(0.5 * offset @ (np.tile([3.0, 0.3], spec["horizon"]) * offset))
        runs = []
        for method in spec["methods"]:
            if method == "generalized":
                for mode in spec["modes"]:
                    runs.append(dict(method=method, mode=mode, state="incompatible",
                                     reason="The fixed stream has unequal lower/upper penalty weights.",
                                     metrics=None, normalized_gap=None, result=None,
                                     elapsed_seconds=None, update_seconds=None, workspace_setup_seconds=None))
                continue
            for mode in spec["modes"]:
                if mode == "cold":
                    observation = cold_observation(problem, method, objective)
                else:
                    setup = None
                    if method not in workspaces:
                        start = time.perf_counter()
                        workspaces[method] = (
                            DaqpWorkspace(problem, **{k: SETTINGS[k] for k in ("eps_abs", "eps_rel", "max_iter")})
                            if method == "daqp" else PreparedSolver(problem, method, **SETTINGS)
                        )
                        setup = time.perf_counter() - start
                    workspace = workspaces[method]
                    start = time.perf_counter()
                    # Frame zero has no update; all subsequent frames validate and update vectors.
                    if frame:
                        workspace.update(q=problem.q, lower=problem.lower, upper=problem.upper)
                    result = workspace.solve()
                    checked = acceptance(problem, result, objective)
                    observation = dict(**checked, elapsed_seconds=time.perf_counter() - start,
                                       update_seconds=workspace.update_wall_seconds if frame else 0.0,
                                       workspace_setup_seconds=setup, result=result)
                runs.append(dict(method=method, mode=mode, **observation))
        # Clamp only oracle solver roundoff to the declared actuator interval, and record it.
        raw_control = float(reference["x"][0])
        control = float(np.clip(raw_control, -1.0, 1.0))
        next_state = F @ state + B * control
        frames.append(dict(frame=frame, time_seconds=frame * dt, state=state.tolist(),
                           velocity_impulse=impulse, oracle_objective=objective,
                           objective_constant=constant, oracle_horizon_cost=objective + constant,
                           oracle_control=raw_control, applied_control=control,
                           next_state=next_state.tolist(), generation_seconds=generation_seconds, runs=runs))
        state = next_state
    all_runs = [r for frame in frames for r in frame["runs"]]
    return dict(schema_version="softqp.stream/v1", case_id="C12", protocol_id=protocol["protocol_id"],
                engine_source=protocol["engine_source"], environment=provenance, specification=spec,
                frames=frames, counts={s: sum(r["state"] == s for r in all_runs) for s in
                                      ("accepted", "incompatible", "failed", "accuracy-rejected")},
                limitations=["One stream observation per frame is descriptive, not a statistical timing claim.",
                             "Every method receives the same oracle-driven states, not its own controller rollout.",
                             "Predicted horizon costs overlap and must not be summed as realized plant cost.",
                             "Hard actuator bounds and condensed dynamics are model assumptions, not a safety certificate."])


def export_stream(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    document = run_stream()
    raw = (json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    (output / "stream.json").write_bytes(raw)
    return dict(path="stream.json", sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), counts=document["counts"])
