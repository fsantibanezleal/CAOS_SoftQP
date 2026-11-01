"""Author the initial self-contained experimental schemas; not a runtime generator."""

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "docs/contracts/schemas"
N = {"type": "number"}
S = {"type": "string"}
Z = {"type": "integer", "minimum": 0}
T = {"type": "number", "minimum": 0}
H = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
REV = {"type": "string", "pattern": "^[0-9a-f]{40}$"}
STATES = ["accepted", "incompatible", "failed", "accuracy-rejected", "timeout", "resource-limit", "oracle-failed"]
METHODS = ["lifted", "generalized", "asymmetric", "daqp", "flex", "elastiqp"]


def obj(properties, required=None):
    return dict(type="object", additionalProperties=False, properties=properties,
                required=list(properties) if required is None else required)


def array(item, **limits):
    return dict(type="array", items=item, **limits)


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def literal(value):
    if isinstance(value, dict):
        return obj({k: literal(v) for k, v in value.items()})
    if isinstance(value, list):
        return dict(type="array", prefixItems=[literal(v) for v in value], items=False,
                    minItems=len(value), maxItems=len(value))
    return {"const": value}


def write(name, body):
    doc = {"$schema": "https://json-schema.org/draft/2020-12/schema",
           "$id": f"https://fsantibanezleal.github.io/CAOS_SoftQP/contracts/{name}.schema.json", **body}
    (FOLDER / f"{name}.schema.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def main():
    result = json.loads((FOLDER / "softqp-case-result.schema.json").read_text(encoding="utf-8"))
    payload = copy.deepcopy(result["properties"]["runs"]["items"]["properties"]["result"]["anyOf"][0])
    metrics = payload["properties"]["metrics"]["anyOf"][0]
    # Standalone native results precede the catalog's pairwise-gap annotation.
    # The stream observation carries its own independently computed normalized_gap.
    metrics["required"].remove("objective_gap_against_lifted")
    metrics["properties"]["stationarity_residual"] = nullable(T)
    env = json.loads((FOLDER / "softqp-index.schema.json").read_text(encoding="utf-8"))["properties"]["environment"]
    protocol = json.loads((ROOT / "docs/design/experiments-v1.json").read_text(encoding="utf-8"))
    counts = obj({s: Z for s in STATES}, required=[])
    pair = array(N, minItems=2, maxItems=2)
    observation = dict(state={"enum": STATES}, reason=nullable(S), metrics=nullable(metrics),
                       normalized_gap=nullable(T), elapsed_seconds=nullable(T), update_seconds=nullable(T),
                       workspace_setup_seconds=nullable(T), result=nullable(payload))
    frame = obj(dict(frame=Z, time_seconds=T, state=pair, velocity_impulse=N, oracle_objective=N,
                     objective_constant=N, oracle_horizon_cost=N, oracle_control=N, applied_control=N,
                     next_state=pair, generation_seconds=T,
                     runs=array(obj(dict(method={"enum": METHODS}, mode={"enum": ["cold", "warm"]},
                                         **observation)), minItems=8, maxItems=8)))
    write("softqp-stream", obj(dict(schema_version={"const": "softqp.stream/v1"}, case_id={"const": "C12"},
                                    protocol_id={"const": protocol["protocol_id"]}, engine_source=REV,
                                    environment=env, specification=literal(protocol["stream"]),
                                    frames=array(frame, minItems=32, maxItems=32), counts=counts,
                                    limitations=array(S))))
    spec = dict(id={"type": "string", "pattern": "^(development|heldout|robustness)-[0-9]{4}$"},
                split={"enum": ["development", "heldout", "robustness"]}, n=Z, density=T, condition=T,
                family={"enum": ["symmetric-elastic", "asymmetric-elastic", "asymmetric-l1"]}, seed=Z)
    dataset = obj(dict(**spec, generation_seconds=T, problem_sha256=H,
                       oracle_state={"enum": ["accepted", "oracle-failed"]}, oracle_reason=nullable(S),
                       oracle_objective=nullable(N)))
    write("softqp-datasets", array(dataset))
    flat_metrics = obj({k: nullable(T) if k == "stationarity_residual" else N for k in (
        "objective", "base_objective", "penalty_objective", "hard_violation", "stationarity_residual",
        "total_lower_violation", "total_upper_violation")})
    trial_fields = dict(**spec, method={"enum": METHODS}, repetition={"type": "integer", "minimum": -1},
                        warmup={"type": "boolean"}, **observation)
    trial_fields["metrics"] = nullable(flat_metrics)
    trial_fields.update(iterations=nullable(Z), dimensions=nullable(payload["properties"]["dimensions"]),
                        native_setup_seconds=nullable(T), native_solve_seconds=nullable(T),
                        status=nullable(S), status_code=nullable({"type": "integer"}))
    write("softqp-trial", obj(trial_fields, required=list(spec) + ["method", "repetition", "warmup", "state", "reason",
                                                                "elapsed_seconds", "metrics", "normalized_gap"]))
    cell = obj(dict(**{k: v for k, v in spec.items() if k not in ("id", "seed")}, method={"enum": METHODS},
                    counts=counts, median_seconds=nullable(T), quantile_25_seconds=nullable(T),
                    quantile_75_seconds=nullable(T), max_normalized_gap=nullable(T), max_hard_violation=nullable(T)))
    primary = obj(dict(state={"enum": ["met", "not-established"]}, median_relative_reduction=nullable(N),
                       confidence_interval_95=nullable(pair), paired_samples=Z, rejected_pairs=Z, seed_clusters=Z))
    artifact = obj(dict(path={"type": "string", "pattern": "^[a-z][a-z0-9-]*\\.(json|csv|jsonl)$"}, bytes=Z, sha256=H))
    campaign = obj(dict(schema_version={"const": "softqp.campaign/v1"}, protocol=literal(protocol), environment=env,
                        protocol_sha256=H, source_sha256={"type": "object", "additionalProperties": H},
                        observed_wall_seconds=T, worker_peak_rss_bytes=Z, worker_restarts=Z,
                        planned_instances=Z, completed_instances=Z, cells=array(cell), primary_endpoint=primary,
                        counts=counts, artifacts=array(artifact)))
    write("softqp-campaign", campaign)
    entry = obj(dict(path=artifact["properties"]["path"], bytes=Z, sha256=H,
                     schema={"enum": ["softqp-stream", "softqp-campaign", "softqp-datasets", "softqp-trial", "csv"]}))
    write("softqp-experiment-index", obj(dict(schema_version={"const": "softqp.experiments/v1"},
                                              protocol_id={"const": protocol["protocol_id"]},
                                              artifacts=array(entry), state={"enum": ["development", "measured"]})))


if __name__ == "__main__":
    main()
