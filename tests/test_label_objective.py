"""Original-objective agreement for actual label admission."""

from copy import deepcopy
from dataclasses import replace

import pytest

from pipeline.learned_comparison import contracts as c
from test_learned_contracts import PROVIDER, reseal


def register(context, kind, name, payload):
    doc = PROVIDER["envelope"](kind, name, payload, context)
    written = c.write_artifact(doc, name + ".json", context)
    ref = dict(kind=kind, artifact_id=name, path=name + ".json", sha256=written.raw_sha256)
    return replace(context, catalog={**context.catalog, name: ref}), ref


def test_adversarial_cold_label_stationarity_does_not_authorize_wrong_objective(tmp_path):
    context, docs, _ = PROVIDER["build"](tmp_path / "provider")
    original = deepcopy(docs["problem-train"]["payload"]["original"])
    original.update(n=2, P=c.csc([[1, 0], [0, 2**-80]]), A=c.csc([[1, 0]]), q=[0, 0])
    original["penalty"] = {key: [False] if key == "soft" else [0] for key in original["penalty"]}
    original["units"].update(variable=["dimensionless"] * 2, D_x=[1, 1])
    problem = PROVIDER["problem_payload"](original=original, control="contract-fixture:flat-curvature-label")
    problem_id = "flat-curvature-train"
    source = problem["source"]
    context = replace(
        context,
        problem_hashes={**context.problem_hashes, problem_id: problem["original_sha256"]},
        source_records={**context.source_records, problem_id: c.digest(c.canonical_bytes(source))},
    )
    context, problem_ref = register(context, "learning-problem", problem_id, problem)
    dataset = deepcopy(docs["dataset"]["payload"])
    next(entry for entry in dataset["problems"] if entry["source"]["split"] == "train").update(
        problem=problem_ref, source=source
    )
    dataset["problems"].sort(key=lambda entry: entry["problem"]["artifact_id"])
    context, dataset_ref = register(context, "learning-dataset", "flat-curvature-dataset", dataset)
    split = deepcopy(docs["split"]["payload"])
    split["dataset"] = dataset_ref
    next(entry for entry in split["assignments"] if entry["split"] == "train").update(
        problem_ids=[problem_id], input_sha256=c.digest(c.canonical_bytes([source["input_sha256"]]))
    )
    split["disjointness_sha256"] = c.digest(c.canonical_bytes(split["assignments"]))
    context, split_ref = register(context, "learning-split", "flat-curvature-split", split)

    good = {"x": [0, 0], "y": [0], "lifted_x": [0, 0], "lifted_y": [0], "epigraph": None}
    bad = {**good, "x": [0, 2**36], "lifted_x": [0, 2**36]}
    oracle_results = []
    for old in docs["labels"]["payload"]["oracle_results"]:
        result = {key: value for key, value in old.items() if key != "result_sha256"}
        result.update(candidate=good, metrics=c.original_metrics(original, good, 0))
        result["result_sha256"] = c.digest(c.canonical_bytes(result))
        oracle_results.append(result)
    reference = c._oracle(problem, oracle_results, context)
    assert reference == 0
    c._recovery(problem, bad, hard_limit=1e-8, limit=1e-8)
    local = c.original_metrics(original, bad, reference)
    assert local["K"] == 2**-44 and local["G"] == 2**-9
    assert all(local[key] == 0 for key in ("H", "F", "F_all", "D"))
    payload = deepcopy(docs["labels"]["payload"])
    payload.update(
        problem=problem_ref,
        split=split_ref,
        oracle_results=oracle_results,
        cold_candidate=good,
        slack=[0, 0, 1, 0],
        multipliers=[0, 0, 0, 0],
        labels=[None, None, 0, None],
        mask=[False, False, True, False],
        node_kind=["variable", "variable", "inequality", "inequality"],
        bound=[0, 0, 1, 0],
    )
    valid = c.write_artifact(
        PROVIDER["envelope"]("learning-labels", "positive", payload, context), "good.json", context
    )
    assert (
        c.read_artifact(context.root / "good.json", context, expected_sha256=valid.raw_sha256).payload
        == payload
    )
    forged = PROVIDER["envelope"]("learning-labels", "wrong-objective", payload, context)
    forged["payload"]["cold_candidate"] = bad
    raw = c.json_bytes(reseal(forged))
    path = context.root / "wrong-objective.json"
    path.write_bytes(raw)
    with pytest.raises(c.ContractError, match="cold label objective disagreement"):
        c.read_artifact(path, context, expected_sha256=c.digest(raw))
    assert path.read_bytes() == raw
