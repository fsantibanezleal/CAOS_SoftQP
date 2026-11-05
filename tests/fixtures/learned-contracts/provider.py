"""Small explicit contract provider; never registered data or trained models.

Only tests/the example-authoring command execute this helper. Numeric zeros are
serialization fixtures. No solver, RNG, gradient or scientific generator runs.
"""

from __future__ import annotations
from dataclasses import replace
import copy
import hashlib
from pathlib import Path

from pipeline.learned_comparison import contracts as c

HERE = Path(__file__).resolve().parent


def H(name):
    return c.digest(("contract-fixture:" + name).encode())


def problem_payload(split="train", q=0, *, original=None, control=None, family="N01", regime=3):
    if original is None:
        original = {
            "n": 1,
            "m": 1,
            "P": c.csc([[1]]),
            "A": c.csc([[1]]),
            "q": [q],
            "lower": [0],
            "upper": [1],
            "lower_finite": [True],
            "upper_finite": [True],
            "penalty": {
                "soft": [True],
                "lower_linear": [1],
                "upper_linear": [1],
                "lower_quadratic": [1],
                "upper_quadratic": [1],
            },
            "groups": [],
            "units": {
                "variable": ["dimensionless"],
                "row": ["dimensionless"],
                "peak": [],
                "objective": "synthetic-operating-cost",
                "D_x": [1],
                "D_r": [1],
                "D_t": [],
                "S_f": 1,
            },
            "formulation": "separable",
        }
    original = copy.deepcopy(original)
    transform = c.canonical_transform(original)
    rank, pivots = c.exact_curvature(c.dense(original["P"]))
    diagonal = rank != original["n"]
    source = {
        "source_id": "fixture-source-" + split,
        "parent_id": "fixture-parent-" + split,
        "family": family,
        "regime": regime,
        "split": split,
        "unit_index": 0,
        "frame": 0,
        "frame_count": 32 if family == "N12" else 1,
        "input_sha256": c.digest(c.canonical_bytes(original)),
        "entropy": [
            20261105,
            903,
            int(family[1:]),
            regime,
            ["train", "validation", "calibration", "test"].index(split),
            0,
            0,
        ],
        "rng_state_sha256": H("no-rng-executed:" + split),
        "attribution": "Authored analytic serialization fixture; not a generated scientific sample",
        "license": "MIT",
    }
    source["rng_state"] = {
        "bit_generator": "PCG64",
        "state": {"state": 0, "inc": 1},
        "has_uint32": 0,
        "uinteger": 0,
    }
    source["rng_state_sha256"] = c.digest(c.canonical_bytes(source["rng_state"]))
    source.update(state_origin="contract-fixture", parameters=[])
    return {
        "source": source,
        "generator_sha256": H("no-scientific-generator"),
        "original": original,
        "original_sha256": source["input_sha256"],
        "curvature": {
            "kind": "exact-diagonal-PSD" if diagonal else "exact-rational-LDL",
            "rank": rank,
            "pivots": [] if diagonal else pivots,
            "diagonal_support": [i for i, r in enumerate(c.dense(original["P"])) if r[i] > 0]
            if diagonal
            else [],
            "temporary_constructor_sha256": H("no-temporary-constructor"),
            "requested_condition": None,
            "actual_condition": None,
        },
        "transform": transform,
        "transform_sha256": c.digest(c.canonical_bytes(transform)),
        "physical_calibration": {
            "scale_policy": "canonical-reference-magnitudes-one",
            "calibration_sha256": c.digest(c.canonical_bytes(original["units"])),
        },
        "expected_control": control,
    }


def envelope(kind, artifact_id, payload, context, *, missing=False):
    result = {
        "schema_id": f"https://fsantibanezleal.github.io/CAOS_SoftQP/contracts/softqp-{kind}/1.0.0",
        "version": "1.0.0",
        "kind": kind,
        "artifact_id": artifact_id,
        "purpose": "contract-fixture",
        "state": "missing" if missing else "provider",
        "reason": "No scientific producer has run; explicitly synthetic contract provider",
        "protocol_id": context.protocol_id,
        "protocol_sha256": context.protocol_sha256,
        "source_lock_sha256": context.source_lock_sha256,
        "protocol_ref": None
        if kind == "learning-protocol" or missing
        else dict(next(r for r in context.catalog.values() if r["kind"] == "learning-protocol")),
        "provenance": {
            "producer_source_sha256": context.producer_source_sha256,
            "registration_sha256": context.registration_sha256,
            "parent_ids": sorted({r["artifact_id"] for r in c._references(payload)}) if payload else [],
        },
        "payload": None if missing else payload,
    }
    result["provenance"]["parent_ids"] = (
        sorted({r["artifact_id"] for r in c._references(payload) + c._references(result["protocol_ref"])})
        if payload is not None
        else []
    )
    result["content_sha256"] = c.content_digest(result)
    return result


def reseal(document):
    document["provenance"]["parent_ids"] = (
        sorted(
            {
                r["artifact_id"]
                for r in c._references(document["payload"]) + c._references(document["protocol_ref"])
            }
        )
        if document["payload"]
        else []
    )
    document["content_sha256"] = c.content_digest(document)
    return document


def build(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    authority = c.Authority.load(HERE / "accepted-design")
    problems = {
        s: problem_payload(s, q)
        for s, q in [("train", 0), ("validation", 0.25), ("calibration", 2), ("test", -1)]
    }
    protocol = {
        "status": "accepted-design",
        "registration_sha256": H("not-a-scientific-registration"),
        "generator_sha256": H("no-scientific-generator"),
        "dependency_lock_sha256": H("no-admitted-training-runtime"),
        "design_manifest_sha256": c.DESIGN_MANIFEST_SHA256,
        "bindings": dict(authority.manifest["normative_sha256"]),
        "methods": authority.matrix["methods"],
        "network_seeds": [41001, 41002, 41003],
        "split_units": {"train": 32, "validation": 8, "calibration": 8, "test": 8},
        "source_entropy_prefix": [20261105, 903],
        "old_exclusions": [
            "3a79bc8abf63f70cac054c26bb5ec19bff0321e0047673d7bc3b239d380f00b5",
            "3d8eb822a6b31026c491b66cfb21f474b044a6ca3801074379243b8a3e7ca53f",
            "c82bf30bb53c7c10d464fc446bd2b99ee774b581dbe3f4dced86194e1fe54c6d",
        ],
        "budgets": {
            "training_rss_bytes": 8 * 2**30,
            "dataset_checkpoint_bytes": 8 * 2**30,
            "inference_rss_bytes": 4 * 2**30,
            "trial_seconds": 10,
            "import_seconds": 180,
            "worker_count": 1,
        },
    }
    methods = list(authority.matrix["methods"]) + ["cold_osqp", "cold_daqp", "previous_osqp", "previous_daqp"]
    settings = {m: H("settings:" + m) for m in methods}
    settings.update({"oracle:" + b: H("oracle-settings:" + b) for b in ["stock_osqp", "clarabel", "piqp"]})
    settings["label:cold_daqp"] = H("label-settings:cold_daqp")
    context = c.AdmissionContext(
        root=root.resolve(),
        authority=authority,
        protocol_id="contract-fixture-not-registered",
        protocol_sha256=c.digest(c.canonical_bytes(protocol)),
        source_lock_sha256=H("no-source-lock-admission"),
        registration_sha256=protocol["registration_sha256"],
        producer_source_sha256=c.digest(Path(c.__file__).read_bytes()),
        generator_sha256=protocol["generator_sha256"],
        dependency_lock_sha256=protocol["dependency_lock_sha256"],
        settings_hashes=settings,
        catalog={},
        problem_hashes={"problem-" + s: v["original_sha256"] for s, v in problems.items()},
        source_lock_bytes=b"contract-fixture:no-source-lock-admission",
        dependency_lock_bytes=b"contract-fixture:no-admitted-training-runtime",
        generator_source_bytes=b"contract-fixture:no-scientific-generator",
        producer_source_bytes=Path(c.__file__).read_bytes(),
        source_records={
            "problem-" + s: c.digest(c.canonical_bytes(v["source"])) for s, v in problems.items()
        },
        fit_source_ids=("fixture-source-train",),
        expected_result_keys=(("lifted", 0, "N01", 3, 0, 0),),
        allow_fixture=True,
    )
    docs, refs = {}, {}

    def put(kind, artifact_id, payload):
        nonlocal context
        doc = envelope(kind, artifact_id, payload, context)
        artifact = c.write_artifact(doc, artifact_id + ".json", context)
        ref = {
            "kind": kind,
            "artifact_id": artifact_id,
            "path": artifact_id + ".json",
            "sha256": artifact.raw_sha256,
        }
        docs[artifact_id], refs[artifact_id] = doc, ref
        context = replace(context, catalog={**context.catalog, artifact_id: ref})
        return ref

    put("learning-protocol", "protocol", protocol)
    for split, payload in problems.items():
        put("learning-problem", "problem-" + split, payload)
    entries = [{"problem": refs["problem-" + s], "source": problems[s]["source"]} for s in sorted(problems)]
    dataset = {
        "generator_sha256": context.generator_sha256,
        "problems": entries,
        "source_ids": sorted(v["source"]["source_id"] for v in problems.values()),
        "counts": {"problems": 4, "sources": 4, "train": 1, "validation": 1, "calibration": 1, "test": 1},
        "exclusions": protocol["old_exclusions"],
        "parent_manifest_sha256": None,
        "attribution": "Four hand-defined contract fixtures only",
        "license": "MIT",
    }
    put("learning-dataset", "dataset", dataset)
    assignments = [
        {
            "source_id": e["source"]["source_id"],
            "parent_id": e["source"]["parent_id"],
            "input_sha256": c.digest(c.canonical_bytes([e["source"]["input_sha256"]])),
            "split": e["source"]["split"],
            "problem_ids": [e["problem"]["artifact_id"]],
        }
        for e in entries
    ]
    assignments.sort(key=lambda a: a["source_id"])
    split = {
        "dataset": refs["dataset"],
        "assignments": assignments,
        "entropy_prefix": [20261105, 903],
        "fit_source_ids": ["fixture-source-train"],
        "disjointness_sha256": c.digest(c.canonical_bytes(assignments)),
    }
    put("learning-split", "split", split)
    train = problems["train"]
    names, raw = c.mlp_coordinates(train["transform"])
    norm = {
        "normalizer_id": "fixture-normalizer",
        "head_id": "H-2-3",
        "fit_source_ids": ["fixture-source-train"],
        "fit_split": "train",
        "coordinate_order": names,
        "mean": raw,
        "scale": [1] * len(raw),
        "source_weights": [1],
    }
    norm["sha256"] = c.digest(c.canonical_bytes(norm))
    features = {
        "problem": refs["problem-train"],
        "split": refs["split"],
        "representation": "mlp-v1",
        "head_id": "H-2-3",
        "transform_sha256": train["transform_sha256"],
        "normalizer": norm,
        "coordinate_order": names,
        "raw_values": raw,
        "values": [0] * len(raw),
        "graph": None,
        "dtype": "float64",
        "fit_access": ["fixture-source-train"],
    }
    put("learning-features", "features", features)

    def candidate_for(split_name):
        return {
            "train": {"x": [0], "y": [0], "lifted_x": [0, 0], "lifted_y": [0, 0, -1], "epigraph": None},
            "test": {"x": [1], "y": [0], "lifted_x": [1, 0], "lifted_y": [0, 0, -1], "epigraph": None},
            "calibration": {
                "x": [-0.5],
                "y": [-1.5],
                "lifted_x": [-0.5, 0.5],
                "lifted_y": [0, -1.5, 0],
                "epigraph": None,
            },
        }[split_name]

    def oracles_for(split_name):
        candidate = candidate_for(split_name)
        problem = problems[split_name]
        f = c.original_metrics(problem["original"], candidate, 0)["objective"]
        result = []
        for backend, flag in [("stock_osqp", 1), ("clarabel", "Solved"), ("piqp", "PIQP_SOLVED")]:
            item = {
                "backend": backend,
                "settings_sha256": settings["oracle:" + backend],
                "accepted": True,
                "status": "accepted",
                "reason": None,
                "candidate": candidate,
                "metrics": c.original_metrics(problem["original"], candidate, f),
                "native_flag": flag,
            }
            item["result_sha256"] = c.digest(c.canonical_bytes(item))
            result.append(item)
        return result

    labels = {
        "problem": refs["problem-train"],
        "split": refs["split"],
        "oracle_results": oracles_for("train"),
        "oracle_source_sha256": context.producer_source_sha256,
        "settings_sha256": settings["label:cold_daqp"],
        "status": "accepted",
        "reason": None,
        "slack": [0, 0, 1, 0, 0],
        "multipliers": [0, 0, 0, 0, 1],
        "labels": [None, None, 0, None, 1],
        "mask": [False, False, True, False, True],
        "node_kind": ["variable", "variable", "inequality", "inequality", "inequality"],
        "bound": [0, 0, 1, 0, 0],
        "tau_dual": 1e-7,
        "tau_tight": 1e-7,
        "fit_access": ["fixture-source-train"],
        "cold_candidate": candidate_for("train"),
        "cold_native_flag": 1,
    }
    put("learning-labels", "labels", labels)
    shapes = c.parameter_shapes("learned_osqp", ["H-2-3"], authority)
    count = sum(__import__("math").prod(shape) for _, _, shape in shapes)
    weight_bytes = bytes(count * 8)
    parameters, offset, streams = [], 0, []
    for head, name, shape in shapes:
        size = __import__("math").prod(shape)
        random = name.endswith("weight")
        seed = (
            int.from_bytes(
                hashlib.sha256(f"softqp-learning-r2|L-1|41001|{head}|{name}".encode()).digest()[:8], "little"
            )
            % 2**63
            if random
            else 0
        )
        parameters.append(
            {
                "head_id": head,
                "name": name,
                "shape": shape,
                "dtype": "float64-le",
                "offset": offset,
                "count": size,
                "sha256": c.digest(bytes(size * 8)),
                "initialization_seed": seed,
                "initialization_rule": (
                    "xavier-output-gain1" if name.startswith("output") else "xavier-relu-sqrt2"
                )
                if random
                else "zeros",
            }
        )
        if random:
            streams.append(
                {"parameter": head + "/" + name, "seed": seed, "sha256": H("unexecuted-stream:" + name)}
            )
        offset += size

    def numeric(name, data, format="raw-float64-le"):
        (root / name).write_bytes(data)
        return {"path": name, "sha256": c.digest(data), "byte_count": len(data), "format": format}

    architecture = {
        "method": "learned_osqp",
        "head_ids": ["H-2-3"],
        "parameter_count": count,
        "parameters": parameters,
        "dtype": "float64",
        "coverage": "single-head-contract-fixture",
    }
    weights = numeric("fixture-untrained.f64", weight_bytes)
    checkpoint = {
        "method": "learned_osqp",
        "dataset": refs["dataset"],
        "split": refs["split"],
        "features": [refs["features"]],
        "architecture": architecture,
        "architecture_sha256": c.digest(c.canonical_bytes(architecture)),
        "seed": 41001,
        "epoch": {"H-2-3": 0},
        "best_epoch": {"H-2-3": 0},
        "normalizer_sha256": [norm["sha256"]],
        "weights": weights,
        "initial_weights_sha256": weights["sha256"],
        "history": [
            {
                "head_id": "H-2-3",
                "epoch": 0,
                "train_objective": 0,
                "validation_objective": 0,
                "gradient_finite": True,
                "gradient_nonzero": False,
                "optimizer_steps": 0,
            }
        ],
        "optimizer": {
            "name": "AdamW",
            "learning_rate": 0.001,
            "weight_decay": 0.0001,
            "beta1": 0.9,
            "beta2": 0.999,
            "eps": 1e-8,
            "amsgrad": False,
            "step_count": 0,
            "state_file": numeric("fixture-moments.f64", bytes(2 * len(weight_bytes))),
            "tensors": [
                {
                    "parameter": p["head_id"] + "/" + p["name"],
                    "shape": p["shape"],
                    "first_moment_offset": p["offset"],
                    "second_moment_offset": p["offset"] + count,
                }
                for p in parameters
            ],
        },
        "rng": {
            "streams": streams,
            "epoch_order_sha256": H("no-epoch-order-executed"),
            "state_file": numeric(
                "fixture-rng.u8", b"opaque-contract-fixture-not-runtime-state", "raw-uint8"
            ),
        },
        "training_evidence": "untrained-contract-fixture",
    }
    checkpoint.update(
        learning_policy_sha256=authority.manifest["normative_sha256"]["learning-spec.md"],
        class_statistics=None,
    )
    checkpoint.update(
        role="initial", initial_weights=copy.deepcopy(weights), best_weights=copy.deepcopy(weights)
    )
    put("learning-checkpoint", "checkpoint", checkpoint)
    calibration = {
        "method": "learned_osqp",
        "checkpoint": refs["checkpoint"],
        "split": refs["split"],
        "applicability": "not-applicable",
        "source_ids": [],
        "threshold_grid": [],
        "selected_threshold": None,
        "objective": "not-applicable",
        "tie": "not-applicable",
        "scores": [],
        "class_counts": [],
        "mask_count": 0,
        "metrics": {"f1": None, "brier": None, "ece": None, "undefined_reason": "not-applicable"},
    }
    calibration["observations"] = []
    put("learning-calibration", "calibration", calibration)
    trials = []
    for phase, repetitions in [("warmup", 2), ("measured", 5)]:
        for repetition in range(repetitions):
            trials.append(
                {
                    "phase": phase,
                    "repetition": repetition,
                    "status": "accepted",
                    "reason": None,
                    "native_flag": 1,
                    "candidate": candidate_for("test"),
                    "metrics": c.original_metrics(problems["test"]["original"], candidate_for("test"), -0.5),
                    "timing": {
                        "preprocess": 1,
                        "features": 0,
                        "inference": 0,
                        "setup": 1,
                        "solve": 1,
                        "repair": 0,
                        "recovery": 1,
                        "validation": 1,
                    },
                    "full_cost": 5,
                    "clock": "contract-fixture",
                    "attempt_flags": [],
                    "removed_rows": [],
                    "attempt_native_flags": [],
                    "fallback_count": 0,
                }
            )
    result = {
        "problem": refs["problem-test"],
        "key": ["lifted", 0, "N01", 3, 0, 0],
        "method": "lifted",
        "semantic_transform": "S",
        "lane": "offline",
        "checkpoint": None,
        "calibration": None,
        "settings_sha256": settings["lifted"],
        "status": "accepted",
        "reason": None,
        "oracles": oracles_for("test"),
        "trials": trials,
        "injected_state": None,
        "certificate": None,
        "dimensions": {"original_n": 1, "original_m": 1, "canonical_n": 2, "canonical_m": 3},
        "memory_bytes": 0,
        "metric_policy_sha256": authority.manifest["normative_sha256"]["numerical-spec.md"],
        "diagnostic_native_flag": None,
    }
    put("learning-method-result", "result", result)
    evaluation = {
        "results": [refs["result"]],
        "expected_keyset_sha256": c.digest(
            b"".join(c.canonical_bytes(list(k)) for k in sorted(context.expected_result_keys))
        ),
        "denominators": {"expected": 1, "accepted": 1, "failed": 0, "incompatible": 0},
        "source_totals": [],
        "hypotheses": [
            {
                "method": method,
                "estimate": None,
                "interval": None,
                "qualified": False,
                "reason": "no-learned-fixture",
            }
            for method in ["learned_osqp", "learned_daqp"]
        ],
        "bootstrap": {
            "replicates": 10000,
            "quantile": "type7",
            "lower_p": 0.0125,
            "upper_p": 0.9875,
            "crossed_shared_draws": True,
            "draws_sha256": None,
            "draw_files": [],
        },
        "limits": "One hand-defined serialization key. Not a scientific matrix, observation, result or performance measurement.",
    }
    evaluation.update(
        diagnostics=[], diagnostic_denominators={"expected": 0, "passed": 0, "failed": 0, "missing": 0}
    )
    put("learning-evaluation", "evaluation", evaluation)
    export = {
        "evaluation": refs["evaluation"],
        "cases": [
            {"case_id": "N01", "results": [refs["result"]], "units": problems["test"]["original"]["units"]}
        ],
        "model_cards": [
            {
                "method": "learned_osqp",
                "checkpoint": refs["checkpoint"],
                "calibration": refs["calibration"],
                "license": "MIT",
                "limitations": "Untrained single-head contract provider only; no inference or held-out scientific evidence.",
            }
        ],
        "lane": "replay",
        "runtime_en": "missing",
        "supported_controls": [],
        "bounds_sha256": c.digest(c.canonical_bytes([])),
    }
    put("learning-export-index", "export", export)
    return context, docs, refs


def build_graph(context, docs, refs):
    """Additional untrained graph/checkpoint/calibration serialization provider."""
    root = context.root

    def put(kind, name, payload):
        nonlocal context
        doc = envelope(kind, name, payload, context)
        artifact = c.write_artifact(doc, name + ".json", context)
        ref = {"kind": kind, "artifact_id": name, "path": name + ".json", "sha256": artifact.raw_sha256}
        docs[name], refs[name] = doc, ref
        context = replace(context, catalog={**context.catalog, name: ref})
        return ref

    train = docs["problem-train"]["payload"]
    f = copy.deepcopy(docs["features"]["payload"])
    f.update(
        representation="graph-v1",
        normalizer=None,
        coordinate_order=[],
        raw_values=[],
        values=[],
        fit_access=[],
        graph=c.graph_coordinates(train["transform"])[0],
    )
    put("learning-features", "graph-features", f)
    label = copy.deepcopy(docs["labels"]["payload"])
    cal = docs["problem-calibration"]["payload"]
    candidate = {
        "x": [-0.5],
        "y": [-1.5],
        "lifted_x": [-0.5, 0.5],
        "lifted_y": [0, -1.5, 0],
        "epigraph": None,
    }
    metric = c.original_metrics(cal["original"], candidate, 0)
    metric = c.original_metrics(cal["original"], candidate, metric["objective"])
    oracles = []
    for backend, flag in [("stock_osqp", 1), ("clarabel", "Solved"), ("piqp", "PIQP_SOLVED")]:
        o = {
            "backend": backend,
            "settings_sha256": context.settings_hashes["oracle:" + backend],
            "accepted": True,
            "status": "accepted",
            "reason": None,
            "candidate": candidate,
            "metrics": metric,
            "native_flag": flag,
        }
        o["result_sha256"] = c.digest(c.canonical_bytes(o))
        oracles.append(o)
    label.update(
        problem=refs["problem-calibration"],
        oracle_results=oracles,
        cold_candidate=candidate,
        slack=[0, 0, 2, 0, 0.5],
        multipliers=[0, 0, 0, 1.5, 0],
        labels=[None, None, 0, 1, 0],
        mask=[False, False, True, True, True],
        fit_access=[],
    )
    put("learning-labels", "calibration-labels", label)
    checkpoint = copy.deepcopy(docs["checkpoint"]["payload"])
    parameters = []
    offset = 0
    streams = []
    for head, name, shape in c.parameter_shapes("learned_daqp", ["graph"], context.authority):
        count = __import__("math").prod(shape)
        random = name.endswith(".weight") and not name.startswith("norm")
        seed = (
            int.from_bytes(
                hashlib.sha256(f"softqp-learning-r2|L-2|41001|graph|{name}".encode()).digest()[:8], "little"
            )
            % 2**63
            if random
            else 0
        )
        rule = (
            ("xavier-output-gain1" if name.startswith("output") else "xavier-leakyrelu-slope0.1")
            if random
            else (
                "ones"
                if name.startswith("norm") and name.endswith("weight")
                else ("train-log-positive-odds" if name == "output_layer.lin3.bias" else "zeros")
            )
        )
        parameters.append(
            dict(
                head_id=head,
                name=name,
                shape=shape,
                dtype="float64-le",
                offset=offset,
                count=count,
                sha256=c.digest(bytes(count * 8)),
                initialization_seed=seed,
                initialization_rule=rule,
            )
        )
        if random:
            streams.append(
                dict(parameter="graph/" + name, seed=seed, sha256=H("unexecuted-graph-stream:" + name))
            )
        offset += count
    assert offset == 52098

    def numeric(name, data, format="raw-float64-le"):
        (root / name).write_bytes(data)
        return dict(path=name, sha256=c.digest(data), byte_count=len(data), format=format)

    weights = numeric("graph-untrained.f64", bytes(offset * 8))
    a = dict(
        method="learned_daqp",
        head_ids=["graph"],
        parameter_count=offset,
        parameters=parameters,
        dtype="float64",
        coverage="graph-contract-fixture",
    )
    checkpoint.update(
        method="learned_daqp",
        features=[refs["graph-features"]],
        architecture=a,
        architecture_sha256=c.digest(c.canonical_bytes(a)),
        epoch={"graph": 0},
        best_epoch={"graph": 0},
        normalizer_sha256=[],
        weights=weights,
        initial_weights=copy.deepcopy(weights),
        best_weights=copy.deepcopy(weights),
        initial_weights_sha256=weights["sha256"],
        history=[
            dict(
                head_id="graph",
                epoch=0,
                train_objective=0,
                validation_objective=0,
                gradient_finite=True,
                gradient_nonzero=False,
                optimizer_steps=0,
            )
        ],
        class_statistics=dict(
            labels=[refs["labels"]], N0=0.5, N1=0.5, weight0=1, weight1=1, positive_prior=0.5
        ),
    )
    checkpoint["optimizer"].update(
        weight_decay=0.01,
        state_file=numeric("graph-moments.f64", bytes(offset * 16)),
        tensors=[
            dict(
                parameter=p["head_id"] + "/" + p["name"],
                shape=p["shape"],
                first_moment_offset=p["offset"],
                second_moment_offset=p["offset"] + offset,
            )
            for p in parameters
        ],
    )
    checkpoint["rng"].update(
        streams=streams, state_file=numeric("graph-rng.u8", b"explicit-untrained-graph-provider", "raw-uint8")
    )
    put("learning-checkpoint", "graph-checkpoint", checkpoint)
    probabilities = [0.5, 0.5, 0.1, 0.9, 0.2]
    points = [(0.1, 0, 1 / 3), (0.9, 1, 1 / 3), (0.2, 0, 1 / 3)]
    mass = sum(w for p, y, w in points)
    brier = sum(w * (p - y) ** 2 for p, y, w in points) / mass
    ece = sum(abs(w * p - w * y) for p, y, w in points) / mass
    calibration = dict(
        method="learned_daqp",
        checkpoint=refs["graph-checkpoint"],
        split=refs["split"],
        applicability="threshold",
        source_ids=["fixture-source-calibration"],
        threshold_grid=[i / 10 for i in range(1, 10)],
        selected_threshold=0.8,
        objective="source-weighted-macro-F1",
        tie="largest-threshold",
        scores=[2 / 3] + [1] * 7 + [0],
        class_counts=[2, 1],
        mask_count=3,
        metrics=dict(f1=1, brier=brier, ece=ece, undefined_reason=None),
        observations=[dict(labels=refs["calibration-labels"], probabilities=probabilities)],
    )
    put("learning-calibration", "graph-calibration", calibration)
    return context, docs, refs


def save_context(context, path):
    """Explicit fixture-only configuration; never a scientific trust source."""
    value = dict(
        purpose="contract-fixture",
        protocol_id=context.protocol_id,
        protocol_sha256=context.protocol_sha256,
        source_lock_sha256=context.source_lock_sha256,
        registration_sha256=context.registration_sha256,
        producer_source_sha256=context.producer_source_sha256,
        generator_sha256=context.generator_sha256,
        dependency_lock_sha256=context.dependency_lock_sha256,
        settings_hashes=dict(context.settings_hashes),
        source_lock_utf8=context.source_lock_bytes.decode(),
        dependency_lock_utf8=context.dependency_lock_bytes.decode(),
        generator_source_utf8=context.generator_source_bytes.decode(),
        catalog={k: dict(v) for k, v in context.catalog.items()},
        problem_hashes=dict(context.problem_hashes),
        source_records=dict(context.source_records),
        fit_source_ids=list(context.fit_source_ids),
        expected_result_keys=[list(k) for k in context.expected_result_keys],
        expected_diagnostic_keys=[list(k) for k in context.expected_diagnostic_keys],
    )
    path.write_bytes(c.json_bytes(value))


def load_context(root):
    """Tests explicitly opt into provider mode after copying committed fixtures."""
    value = c.strict_loads((root / "fixture-context.json").read_bytes())
    assert value.pop("purpose") == "contract-fixture"
    value["source_lock_bytes"] = value.pop("source_lock_utf8").encode()
    value["dependency_lock_bytes"] = value.pop("dependency_lock_utf8").encode()
    value["generator_source_bytes"] = value.pop("generator_source_utf8").encode()
    value["producer_source_bytes"] = Path(c.__file__).read_bytes()
    value["fit_source_ids"] = tuple(value["fit_source_ids"])
    value["expected_result_keys"] = tuple(tuple(k) for k in value["expected_result_keys"])
    value["expected_diagnostic_keys"] = tuple(tuple(k) for k in value["expected_diagnostic_keys"])
    return c.AdmissionContext(
        root=root.resolve(), authority=c.Authority.load(HERE / "accepted-design"), allow_fixture=True, **value
    )
