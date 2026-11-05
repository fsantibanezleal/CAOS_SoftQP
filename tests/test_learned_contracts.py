"""Real U1 producer/consumer controls; providers are not scientific evidence."""

from dataclasses import replace
import copy
from fractions import Fraction
import json
import os
from pathlib import Path
import runpy
import struct
import pytest
from pipeline.learned_comparison import contracts as c

PROVIDER = runpy.run_path(str(Path(__file__).parent / "fixtures/learned-contracts/provider.py"))
reseal, envelope, make_problem = PROVIDER["reseal"], PROVIDER["envelope"], PROVIDER["problem_payload"]


@pytest.fixture(scope="session")
def bundle(tmp_path_factory):
    return PROVIDER["build"](tmp_path_factory.mktemp("u1-provider"))


def refuse(document, context, label):
    doc = reseal(copy.deepcopy(document))
    output = context.root / ("refused-" + label + ".json")
    before = {p.name for p in context.root.iterdir()}
    with pytest.raises((c.ContractError, FileNotFoundError)):
        c.write_artifact(doc, output.name, context)
    assert not output.exists() and before == {p.name for p in context.root.iterdir()}
    path = context.root / ("malicious-" + label + ".json")
    path.write_bytes(c.json_bytes(doc))
    raw = path.read_bytes()
    with pytest.raises((c.ContractError, FileNotFoundError)):
        c.read_artifact(path, context, expected_sha256=c.digest(raw))
    assert path.read_bytes() == raw
    path.unlink()


@pytest.mark.parametrize("kind", c.KINDS)
def test_all_boundaries_roundtrip(bundle, kind):
    context, docs, refs = bundle
    document = next(d for d in docs.values() if d["kind"] == kind)
    artifact = c.validate_artifact(document, context)
    ref = refs[document["artifact_id"]]
    consumed = c.read_artifact(context.root / ref["path"], context, expected_sha256=ref["sha256"])
    assert artifact.raw == consumed.raw == c.json_bytes(document)
    first = c.write_artifact(document, "roundtrip-" + kind + "-1.json", context)
    second = c.write_artifact(document, "roundtrip-" + kind + "-2.json", context)
    assert first.raw == second.raw == artifact.raw and b"\r" not in first.raw and first.raw.endswith(b"\n")
    detached = consumed.document
    detached["artifact_id"] = "mutated-view"
    assert consumed.document["artifact_id"] != detached["artifact_id"]


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "bool",
        "nonfinite",
        "duplicate-key",
        "unknown-state",
        "float-integer",
        "CRLF",
        "negative-zero",
    ],
)
def test_strict_json_both_sides(bundle, mutation):
    context, docs, _ = bundle
    doc = copy.deepcopy(docs["problem-train"])
    if mutation == "unknown":
        doc["unexpected"] = 1
    elif mutation == "bool":
        doc["payload"]["original"]["q"][0] = True
    elif mutation == "unknown-state":
        doc["state"] = "ready"
    elif mutation == "float-integer":
        doc["payload"]["original"]["n"] = 1.0
    elif mutation in ["nonfinite", "negative-zero"]:
        doc["payload"]["original"]["q"][0] = float("nan") if mutation == "nonfinite" else -0.0
        before = list(context.root.iterdir())
        with pytest.raises(c.ContractError):
            c.write_artifact(doc, "must-not-write.json", context)
        assert before == list(context.root.iterdir())
        path = context.root / (mutation + ".json")
        path.write_bytes((json.dumps(doc) + "\n").encode())
        with pytest.raises(c.ContractError):
            c.read_artifact(path, context)
        path.unlink()
        return
    elif mutation in ["duplicate-key", "CRLF"]:
        raw = c.json_bytes(doc)
        raw = (
            raw.replace(b'"version": "1.0.0"', b'"version": "1.0.0", "version": "1.0.0"')
            if mutation == "duplicate-key"
            else raw.replace(b"\n", b"\r\n")
        )
        path = context.root / (mutation + ".json")
        path.write_bytes(raw)
        with pytest.raises(c.ContractError):
            c.read_artifact(path, context)
        path.unlink()
        return
    refuse(doc, context, mutation)


@pytest.mark.parametrize(
    "field",
    [
        "protocol_id",
        "protocol_sha256",
        "source_lock_sha256",
        "registration_sha256",
        "producer_source_sha256",
        "parent",
        "source",
        "coefficient",
        "protocol-registration",
    ],
)
def test_provenance_mutations(bundle, field):
    context, docs, _ = bundle
    doc = copy.deepcopy(docs["features"] if field == "parent" else docs["problem-train"])
    if field in ["protocol_id", "protocol_sha256", "source_lock_sha256"]:
        doc[field] = "forged" if field == "protocol_id" else "0" * 64
    elif field in ["registration_sha256", "producer_source_sha256"]:
        doc["provenance"][field] = "0" * 64
    elif field == "parent":
        doc["payload"]["problem"]["sha256"] = "0" * 64
    elif field == "source":
        doc["payload"]["source"]["parent_id"] = "relabelled-parent"
    elif field == "coefficient":
        p = doc["payload"]
        p["original"]["q"][0] = 0.125
        p["original_sha256"] = p["source"]["input_sha256"] = c.digest(c.canonical_bytes(p["original"]))
        p["transform"] = c.canonical_transform(p["original"])
        p["transform_sha256"] = c.digest(c.canonical_bytes(p["transform"]))
    else:
        doc = copy.deepcopy(docs["protocol"])
        doc["payload"]["registration_sha256"] = "0" * 64
    refuse(doc, context, "provenance-" + field)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate-CSC",
        "unsorted-CSC",
        "bad-offset",
        "shape",
        "mask",
        "reversed-bound",
        "negative-price",
        "unknown-unit",
        "unit-scale",
        "dual-map",
        "primal-map",
        "false-rank",
        "nonconvex",
        "false-symmetry",
        "hard-price",
        "unknown-transform",
    ],
)
def test_problem_mutations(bundle, mutation):
    context, docs, _ = bundle
    doc = copy.deepcopy(docs["problem-train"])
    p = doc["payload"]
    o = p["original"]
    if mutation in ["duplicate-CSC", "unsorted-CSC"]:
        o["A"]["data"] = [1, 2]
        o["A"]["indices"] = [0, 0] if mutation == "duplicate-CSC" else [1, 0]
        o["A"]["indptr"] = [0, 2]
    elif mutation == "bad-offset":
        o["A"]["indptr"] = [0, 7]
    elif mutation == "shape":
        o["P"]["shape"] = [2, 2]
    elif mutation == "mask":
        o["lower_finite"] = [False]
    elif mutation == "reversed-bound":
        o["lower"] = [2]
    elif mutation == "negative-price":
        o["penalty"]["upper_linear"] = [-1]
    elif mutation == "unknown-unit":
        o["units"]["row"] = ["pretend-unit"]
    elif mutation == "unit-scale":
        o["units"]["D_r"] = [101]
    elif mutation == "dual-map":
        p["transform"]["row_dual_map"][0]["coefficient"] = -1
    elif mutation == "primal-map":
        p["transform"]["x_original_indices"] = [1]
    elif mutation == "false-rank":
        p["curvature"]["rank"] = 0
    elif mutation == "nonconvex":
        o["P"]["data"] = [-1]
    elif mutation == "false-symmetry":
        o["n"] = 2
        o["P"] = c.csc([[1, 0.25], [0, 1]])
    elif mutation == "hard-price":
        o["penalty"]["soft"] = [False]
    else:
        p["transform"]["kind"] = "new-transform"
    refuse(doc, context, "problem-" + mutation)


@pytest.mark.parametrize(
    "mutation",
    [
        "heldout-fit",
        "split-relabel",
        "parent-overlap",
        "reordered-feature",
        "normalizer-test",
        "normalizer-stale",
        "feature-shape",
        "feature-label",
        "unknown-head",
    ],
)
def test_split_and_features_mutations(bundle, mutation):
    context, docs, _ = bundle
    doc = copy.deepcopy(
        docs["split"] if mutation in ["heldout-fit", "split-relabel", "parent-overlap"] else docs["features"]
    )
    p = doc["payload"]
    if mutation == "heldout-fit":
        p["fit_source_ids"].append("fixture-source-test")
    elif mutation == "split-relabel":
        p["assignments"][0]["split"] = "train"
    elif mutation == "parent-overlap":
        p["assignments"][0]["parent_id"] = p["assignments"][1]["parent_id"]
    elif mutation == "reordered-feature":
        p["coordinate_order"][0], p["coordinate_order"][1] = (
            p["coordinate_order"][1],
            p["coordinate_order"][0],
        )
    elif mutation == "normalizer-test":
        p["normalizer"]["fit_source_ids"] = ["fixture-source-test"]
    elif mutation == "normalizer-stale":
        p["normalizer"]["mean"][0] += 0.1
    elif mutation == "feature-shape":
        p["values"].pop()
    elif mutation == "feature-label":
        p["label_feature"] = [1]
    else:
        p["head_id"] = "H-999-999"
    refuse(doc, context, "split-feature-" + mutation)


def test_real_fit_reader_refuses_heldout(bundle):
    context, _, refs = bundle
    path = context.root / refs["problem-test"]["path"]
    assert c.read_artifact(path, context).state == "provider"
    with pytest.raises(c.ContractError, match="held-out"):
        c.read_artifact(path, context, usage="fit")


@pytest.mark.parametrize(
    "mutation",
    [
        "pickle",
        "escape",
        "missing-weights",
        "stale-weight-hash",
        "wrong-shape",
        "constructor123",
        "head-omitted",
        "stale-normalizer",
        "stale-checkpoint",
        "test-calibration",
        "classification-for-L2WS",
        "numeric-nan",
        "missing-calibration",
    ],
)
def test_checkpoint_and_calibration_mutations(bundle, mutation):
    context, docs, refs = bundle
    doc = copy.deepcopy(
        docs["calibration"]
        if mutation in ["stale-checkpoint", "test-calibration", "classification-for-L2WS"]
        else docs["checkpoint"]
    )
    p = doc["payload"]
    if mutation == "pickle":
        p["weights"]["format"] = "pickle"
    elif mutation == "escape":
        p["weights"]["path"] = "../escape.f64"
    elif mutation == "missing-weights":
        p["weights"]["path"] = "missing.f64"
    elif mutation == "stale-weight-hash":
        p["weights"]["sha256"] = "0" * 64
    elif mutation == "wrong-shape":
        p["architecture"]["parameters"][0]["shape"] = [127]
    elif mutation == "constructor123":
        p["architecture"]["parameters"][1]["initialization_seed"] = 123
    elif mutation == "head-omitted":
        p["architecture"]["head_ids"] = []
    elif mutation == "stale-normalizer":
        p["normalizer_sha256"] = ["0" * 64]
    elif mutation == "stale-checkpoint":
        p["checkpoint"]["sha256"] = "0" * 64
    elif mutation == "test-calibration":
        p["source_ids"] = ["fixture-source-test"]
    elif mutation == "classification-for-L2WS":
        p["selected_threshold"] = 0.5
    elif mutation == "missing-calibration":
        doc = copy.deepcopy(docs["result"])
        p = doc["payload"]
        p["method"] = p["key"][0] = "learned_osqp"
        p["key"][1] = 41001
        p["settings_sha256"] = context.settings_hashes["learned_osqp"]
        p["checkpoint"] = refs["checkpoint"]
        p["injected_state"] = {"x": [0, 0], "y": [0, 0, 0], "scores": [], "flags": []}
    elif mutation == "numeric-nan":
        path = context.root / p["weights"]["path"]
        raw = path.read_bytes()
        path.write_bytes(struct.pack("<d", float("nan")) + raw[8:])
        try:
            with pytest.raises(c.ContractError):
                c.read_artifact(context.root / "checkpoint.json", context)
        finally:
            path.write_bytes(raw)
        return
    refuse(doc, context, "checkpoint-" + mutation)


@pytest.mark.parametrize(
    "mutation",
    [
        "no-metrics",
        "wrong-sign",
        "native-inexact",
        "copied-objective",
        "dropped-repetition",
        "unpriced-cost",
        "zero-cost",
        "hidden-time",
        "oracle-missing",
        "oracle-failure",
        "oracle-settings",
        "incompatible",
        "unknown-method",
        "wrong-seed",
        "failure-dropped",
    ],
)
def test_result_mutations(bundle, mutation):
    context, docs, _ = bundle
    doc = copy.deepcopy(docs["result"])
    p = doc["payload"]
    trial = p["trials"][0]
    if mutation == "no-metrics":
        trial["metrics"] = None
    elif mutation == "wrong-sign":
        trial["candidate"]["y"] = [1]
    elif mutation == "native-inexact":
        trial["native_flag"] = 2
    elif mutation == "copied-objective":
        trial["metrics"]["objective"] = -42
    elif mutation == "dropped-repetition":
        p["trials"].pop()
    elif mutation == "unpriced-cost":
        trial["metrics"]["penalty"] = 1
    elif mutation == "zero-cost":
        trial["full_cost"] = 0
    elif mutation == "hidden-time":
        trial["timing"]["repair"] = 10
    elif mutation == "oracle-missing":
        p["oracles"].pop()
    elif mutation == "oracle-failure":
        p["oracles"][0]["accepted"] = False
    elif mutation == "oracle-settings":
        p["oracles"][0]["settings_sha256"] = "0" * 64
    elif mutation == "incompatible":
        p["status"] = "incompatible"
        p["reason"] = "package unavailable"
    elif mutation == "unknown-method":
        p["method"] = p["key"][0] = "fake-method"
    elif mutation == "wrong-seed":
        p["key"][1] = 41001
    else:
        trial["status"] = "timeout"
        trial["reason"] = "trial deadline"
    refuse(doc, context, "result-" + mutation)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-key",
        "duplicate-key",
        "failure-denominator",
        "forged-estimate",
        "forged-interval",
        "keyset-relabel",
        "replay-unchecked",
        "replay-unit",
        "replay-control",
        "model-stale",
    ],
)
def test_evaluation_and_export_mutations(bundle, mutation):
    context, docs, _ = bundle
    doc = copy.deepcopy(
        docs["export"] if mutation.startswith("replay") or mutation == "model-stale" else docs["evaluation"]
    )
    p = doc["payload"]
    if mutation == "missing-key":
        p["results"] = []
    elif mutation == "duplicate-key":
        p["results"] *= 2
    elif mutation == "failure-denominator":
        p["denominators"]["failed"] = 1
    elif mutation == "forged-estimate":
        p["hypotheses"][0]["estimate"] = 0.5
    elif mutation == "forged-interval":
        p["hypotheses"][0]["interval"] = [0.2, 0.4]
        p["hypotheses"][0]["qualified"] = True
    elif mutation == "keyset-relabel":
        p["expected_keyset_sha256"] = "0" * 64
    elif mutation == "replay-unchecked":
        p["cases"][0]["results"][0]["artifact_id"] = "unevaluated"
    elif mutation == "replay-unit":
        p["cases"][0]["units"]["row"] = ["m"]
    elif mutation == "replay-control":
        p["supported_controls"] = ["unsupported-live-edit"]
    else:
        p["model_cards"][0]["calibration"]["sha256"] = "0" * 64
    refuse(doc, context, "evaluation-" + mutation)


@pytest.mark.parametrize(
    "path",
    [
        "../escape.json",
        "/absolute.json",
        "C:/escape.json",
        "https://bad/x",
        "bad\\x.json",
        "./alias.json",
        "protocol.json",
    ],
)
def test_atomic_output_refusal(bundle, path):
    context, docs, _ = bundle
    before = {p.name: p.read_bytes() for p in context.root.iterdir() if p.is_file()}
    with pytest.raises(c.ContractError):
        c.write_artifact(docs["problem-train"], path, context)
    assert before == {p.name: p.read_bytes() for p in context.root.iterdir() if p.is_file()}


def test_atomic_failure_cleans_temporary_and_preserves_existing(bundle, monkeypatch):
    context, docs, _ = bundle
    before = {p.name for p in context.root.iterdir()}

    def refuse_link(*args, **kwargs):
        raise OSError("forced publication refusal")

    monkeypatch.setattr(os, "link", refuse_link)
    with pytest.raises(c.ContractError):
        c.write_artifact(docs["problem-train"], "forced-refusal.json", context)
    assert before == {p.name for p in context.root.iterdir()}


@pytest.mark.parametrize("kind", c.KINDS)
def test_missing_and_fixture_lanes(bundle, kind):
    context, docs, _ = bundle
    missing = envelope(kind, "missing-" + kind, None, context, missing=True)
    artifact = c.write_artifact(missing, "missing-" + kind + ".json", context)
    assert artifact.payload is None and artifact.state == "missing" and artifact.reason
    production = replace(
        context,
        allow_fixture=False,
        expected_result_keys=context.authority.keys("method-status")
        + context.authority.keys("control-status"),
        expected_diagnostic_keys=context.authority.keys("diagnostic-status"),
    )
    with pytest.raises(c.ContractError, match="fixture"):
        c.validate_artifact(next(d for d in docs.values() if d["kind"] == kind), production)


def admit_problem(original, bundle, name, *, family="N01", regime=3, control="contract-fixture:semantic"):
    context, _, _ = bundle
    p = make_problem(original=original, control=control, family=family, regime=regime)
    ctx = replace(
        context,
        problem_hashes={**context.problem_hashes, name: p["original_sha256"]},
        source_records={**context.source_records, name: c.digest(c.canonical_bytes(p["source"]))},
    )
    doc = envelope("learning-problem", name, p, ctx)
    artifact = c.write_artifact(doc, name + ".json", ctx)
    ref = {"kind": doc["kind"], "artifact_id": name, "path": name + ".json", "sha256": artifact.raw_sha256}
    ctx = replace(ctx, catalog={**ctx.catalog, name: ref})
    return ctx, doc, ref


def test_one_sided_inactive_price(bundle):
    base = make_problem()["original"]
    for side in ["lower", "upper"]:
        o = copy.deepcopy(base)
        absent = "upper" if side == "lower" else "lower"
        o[absent] = [None]
        o[absent + "_finite"] = [False]
        for k in ["lower_linear", "upper_linear"]:
            o["penalty"][k] = [0.3]
        for k in ["lower_quadratic", "upper_quadratic"]:
            o["penalty"][k] = [2]
        ctx, doc, _ = admit_problem(o, bundle, "one-sided-" + side)
        assert doc["payload"]["transform"]["kind"] == "S"
        assert sum(b is not None for b in doc["payload"]["transform"][absent]) == (
            1 if absent == "lower" else 0
        )
        for x in [0, 2, -2] if side == "lower" else [1, -1, 3]:
            violation = max(o[side][0] - x, 0) if side == "lower" else max(x - o[side][0], 0)
            metric = c.original_metrics(o, {"x": [x], "y": [0]}, 0)
            assert metric["penalty"] == 0.3 * violation + violation**2
            if violation == 2:
                assert metric["penalty"] == 4.6
        changed = copy.deepcopy(o)
        changed["penalty"][absent + "_linear"] = [7]
        changed["penalty"][absent + "_quadratic"] = [9]
        _, other, _ = admit_problem(changed, bundle, "inactive-change-" + side)
        assert other["payload"]["transform"]["kind"] == "A"
        for x in [-2, 0, 1, 3]:
            assert (
                c.original_metrics(o, {"x": [x], "y": [0]}, 0)["penalty"]
                == c.original_metrics(changed, {"x": [x], "y": [0]}, 0)["penalty"]
            )


@pytest.mark.parametrize("family,n,m,expected_shape", [("N03", 2, 4, (6, 8)), ("N11", 8, 24, (32, 56))])
def test_N03_N11_declared_S_all_regimes(bundle, family, n, m, expected_shape):
    base = make_problem()["original"]
    for regime in range(6):
        o = copy.deepcopy(base)
        o.update(
            n=n,
            m=m,
            P=c.csc([[int(i == j) for j in range(n)] for i in range(n)]),
            A=c.csc([[int(j == i % n) for j in range(n)] for i in range(m)]),
            q=[0] * n,
        )
        o["lower"] = [None] * n + [regime / 10] * n + ([-1] * n if m == 3 * n else [])
        o["upper"] = [-regime / 10] * n + [None] * n + ([1] * n if m == 3 * n else [])
        o["lower_finite"] = [v is not None for v in o["lower"]]
        o["upper_finite"] = [v is not None for v in o["upper"]]
        o["penalty"] = {
            "soft": [True] * m,
            "lower_linear": [0.3] * m,
            "upper_linear": [0.3] * m,
            "lower_quadratic": [0] * m,
            "upper_quadratic": [0] * m,
        }
        o["units"].update(variable=["dimensionless"] * n, row=["dimensionless"] * m, D_x=[1] * n, D_r=[1] * m)
        ctx, doc, _ = admit_problem(
            o, bundle, f"{family}-r{regime}", family=family, regime=regime, control=None
        )
        t = doc["payload"]["transform"]
        assert t["kind"] == "S" and (t["n"], t["m"]) == expected_shape
        assert t["variable_order"] == [f"x:{j}" for j in range(n)] + [f"s:{i}" for i in range(m)]
        both = [i for i in range(m) if o["lower"][i] is not None and o["upper"][i] is not None]
        assert t["row_order"] == [f"top:{i}" for i in range(m)] + [f"lower:{i}" for i in both] + [
            f"nonnegative-s:{i}" for i in range(m)
        ]
        assert t["row_dual_map"] == [
            dict(original_row=i, canonical_row=i, coefficient=1) for i in range(m)
        ] + [dict(original_row=i, canonical_row=m + j, coefficient=1) for j, i in enumerate(both)]
        assert t["q"][n:] == [0.3] * m
        transformed_A = c.dense(t["A"])
        for i in range(m):
            assert transformed_A[i][n + i] == (-1 if o["upper"][i] is not None else 1)
        assert f"H-{t['n']}-{t['m']}" == ("H-6-8" if family == "N03" else "H-32-56")
        changed = copy.deepcopy(doc)
        p = changed["payload"]
        for side in ["lower", "upper"]:
            for i, b in enumerate(p["original"][side]):
                if b is None:
                    p["original"]["penalty"][side + "_linear"][i] = 0
        p["original_sha256"] = p["source"]["input_sha256"] = c.digest(c.canonical_bytes(p["original"]))
        p["transform"] = c.canonical_transform(p["original"])
        p["transform_sha256"] = c.digest(c.canonical_bytes(p["transform"]))
        assert p["transform"]["kind"] == "A"
        assert (p["transform"]["n"], p["transform"]["m"]) == ((6, 8) if family == "N03" else (40, 64))
        changed_ctx = replace(
            ctx,
            problem_hashes={**ctx.problem_hashes, doc["artifact_id"]: p["original_sha256"]},
            source_records={
                **ctx.source_records,
                doc["artifact_id"]: c.digest(c.canonical_bytes(p["source"])),
            },
        )
        refuse(changed, changed_ctx, f"zeroed-absent-{family}-{regime}")


def test_fully_free_S_row(bundle):
    o = make_problem()["original"]
    o.update(lower=[None], upper=[None], lower_finite=[False], upper_finite=[False])
    for k in ["lower_linear", "upper_linear"]:
        o["penalty"][k] = [0.3]
    for k in ["lower_quadratic", "upper_quadratic"]:
        o["penalty"][k] = [2]
    _, doc, _ = admit_problem(o, bundle, "fully-free-S", control="NC02-entirely-free-soft-row")
    t = doc["payload"]["transform"]
    assert (t["n"], t["m"]) == (2, 2) and t["lower"] == [None, 0] and t["upper"] == [None, None]
    assert t["q"][-1] == 0.3 and c.dense(t["P"])[1][1] == 2
    assert 0.3 * 1 + 2 * 1**2 / 2 == 1.3
    assert 0.3 * 0 + 2 * 0**2 / 2 == 0 and t["row_dual_map"] == [
        dict(original_row=0, canonical_row=0, coefficient=1)
    ]
    assert c.original_metrics(o, {"x": [7], "y": [0]}, 0)["penalty"] == 0
    assert c.original_metrics(o, {"x": [7], "y": [1]}, 0)["D"] == 1


def test_fully_free_A_row(bundle):
    o = make_problem()["original"]
    o.update(lower=[None], upper=[None], lower_finite=[False], upper_finite=[False])
    o["penalty"]["upper_linear"] = [2]
    _, doc, _ = admit_problem(o, bundle, "fully-free-A", control="NC02-entirely-free-soft-row")
    t = doc["payload"]["transform"]
    assert t["kind"] == "A" and (t["n"], t["m"]) == (1, 0) and t["row_dual_map"] == []
    assert c.original_metrics(o, {"x": [7], "y": [0]}, 0)["penalty"] == 0


def test_hard_and_zero_price_finite_sides(bundle):
    o = make_problem()["original"]
    o["penalty"] = {
        "soft": [False],
        **{k: [0] for k in ["lower_linear", "upper_linear", "lower_quadratic", "upper_quadratic"]},
    }
    ctx, doc, _ = admit_problem(o, bundle, "hard-unchanged")
    t = doc["payload"]["transform"]
    assert (t["n"], t["m"]) == (1, 1) and t["lower"] == [0] and t["upper"] == [1]
    bad = copy.deepcopy(doc)
    bad["payload"]["original"]["penalty"]["upper_linear"] = [0.1]
    refuse(bad, ctx, "hard-positive-price")
    o = make_problem(q=-2)["original"]
    o["penalty"]["upper_linear"] = [0]
    o["penalty"]["upper_quadratic"] = [0]
    _, doc, _ = admit_problem(o, bundle, "zero-price-finite")
    assert doc["payload"]["original"]["upper_finite"] == [True] and doc["payload"]["original"]["penalty"][
        "soft"
    ] == [True]
    assert c.original_metrics(o, {"x": [2], "y": [0]}, -2)["penalty"] == 0


@pytest.mark.parametrize(
    "name,valid",
    [
        ("NC22-unbounded-convex-objective", True),
        ("NC23-tiny-positive-curvature", False),
        ("NC24-tiny-positive-upper-recession", False),
    ],
)
def test_exact_unbounded_reader_refutes_tiny_dyadic_screens(bundle, name, valid):
    context, docs, _ = bundle
    frozen = next(v["fixture"] for v in context.authority.controls if v["id"] == name)
    o = make_problem()["original"]
    n, m = frozen["n"], frozen["m"]
    o.update(
        n=n,
        m=m,
        P=c.csc(frozen["P"]),
        A=c.csc(frozen["A"], n),
        q=frozen["q"],
        lower=frozen["lower"],
        upper=frozen["upper"],
        lower_finite=frozen["lower_finite"],
        upper_finite=frozen["upper_finite"],
    )
    o["penalty"] = {
        "soft": [False] * m,
        **{k: [0] * m for k in ["lower_linear", "upper_linear", "lower_quadratic", "upper_quadratic"]},
    }
    o["units"].update(row=["dimensionless"] * m, D_r=[1] * m)
    ctx, problem, ref = admit_problem(o, bundle, name, control=name)
    doc = copy.deepcopy(docs["result"])
    p = doc["payload"]
    doc["artifact_id"] = name + "-result"
    p.update(
        problem=ref,
        status="unbounded",
        reason="native-dual-infeasible-with-exact-proof-required",
        oracles=[],
        trials=[],
        certificate={
            "kind": "exact-hard-qp-recession",
            "anchor": [0],
            "direction": [1],
            "arithmetic": "exact-submitted-float64-dyadics",
            "screen_only": False,
        },
        dimensions={"original_n": 1, "original_m": m, "canonical_n": 1, "canonical_m": m},
    )
    if valid:
        p["diagnostic_native_flag"] = 5
        result = c.write_artifact(reseal(doc), name + "-result.json", ctx)
        assert c.read_artifact(ctx.root / (name + "-result.json"), ctx).raw_sha256 == result.raw_sha256
    else:
        p["diagnostic_native_flag"] = 5
        assert 2**-34 < 1e-9 and 2**-34 * 2**34 == 1
        expected_error = (
            "exact nonzero Pd" if name.startswith("NC23") else "exact upper anchor/recession violation"
        )
        with pytest.raises(c.ContractError, match=expected_error):
            c.validate_artifact(reseal(doc), ctx)
        refuse(doc, ctx, name + "-false-unbounded")
        inconclusive = copy.deepcopy(doc)
        inconclusive["artifact_id"] = name + "-inconclusive"
        inconclusive["payload"].update(status="inconclusive", reason="exact-proof-unavailable")
        inconclusive["payload"]["certificate"]["screen_only"] = True
        accepted = c.write_artifact(reseal(inconclusive), name + "-inconclusive.json", ctx)
        assert (
            c.read_artifact(ctx.root / (name + "-inconclusive.json"), ctx).raw_sha256 == accepted.raw_sha256
        )
        assert accepted.payload["status"] == "inconclusive"


def numeric_refuse(document, context, label, *, reason="lossless-float64"):
    """A sealed numeric input fails both APIs without publishing or rewriting it."""
    document = reseal(copy.deepcopy(document))
    original = copy.deepcopy(document)
    output = context.root / (label + "-output.json")
    before = {p.name for p in context.root.iterdir()}
    with pytest.raises(c.ContractError, match=reason):
        c.write_artifact(document, output.name, context)
    assert not output.exists() and before == {p.name for p in context.root.iterdir()}
    assert document == original
    source = context.root / (label + "-submitted.json")
    raw = c.json_bytes(document)
    source.write_bytes(raw)
    try:
        with pytest.raises(c.ContractError, match=reason):
            c.read_artifact(source, context, expected_sha256=c.digest(raw))
        assert source.read_bytes() == raw and not output.exists()
    finally:
        source.unlink()


def test_bounded_integer_recession_witness_refused_before_rounding(bundle):
    context, _, _ = bundle
    N = 2**54
    o = make_problem()["original"]
    o.update(
        n=2,
        m=2,
        P=c.csc([[0, 0], [0, 0]]),
        q=[-1, 0],
        A=c.csc([[1, -1], [N, -(N - 1)]]),
        lower=[0, None],
        upper=[0, 1],
        lower_finite=[True, False],
        upper_finite=[True, True],
    )
    o["penalty"] = {
        "soft": [False, False],
        **{k: [0, 0] for k in ["lower_linear", "upper_linear", "lower_quadratic", "upper_quadratic"]},
    }
    o["units"].update(variable=["dimensionless"] * 2, row=["dimensionless"] * 2, D_x=[1, 1], D_r=[1, 1])
    # Equality gives x1=x2, then the upper constraint is x1<=1; min -x1=-1.
    assert Fraction(N) + Fraction(-(N - 1)) == 1
    assert float(-(N - 1)) == -N
    for t in [0, 1, 2]:
        assert sum(Fraction(a) * t for a in [N, -(N - 1)]) == t
    payload = make_problem(original=o, control="contract-fixture:bounded-integer-witness")
    name = "bounded-integer-witness"
    ctx = replace(
        context,
        problem_hashes={**context.problem_hashes, name: payload["original_sha256"]},
        source_records={**context.source_records, name: c.digest(c.canonical_bytes(payload["source"]))},
    )
    doc = envelope("learning-problem", name, payload, ctx)
    assert -(N - 1) in doc["payload"]["original"]["A"]["data"]
    numeric_refuse(doc, ctx, name)


@pytest.mark.parametrize(
    "value",
    [
        2**53 + 1,
        -(2**53 + 1),
        2**54 - 1,
        -(2**54 - 1),
        2**54 + 1,
        -(2**54 + 1),
        2**54 + 2,
        -(2**54 + 2),
        10**400,
        -(10**400),
    ],
)
def test_lossy_integer_and_overflow_refused_both_sides(bundle, value):
    context, _, _ = bundle
    # Keep the path bounded even when the submitted integer has401digits.
    name = "numeric-integer-" + c.digest(str(value).encode())[:16]
    payload = make_problem(q=value, control="contract-fixture:lossless-number")
    ctx = replace(
        context,
        problem_hashes={**context.problem_hashes, name: payload["original_sha256"]},
        source_records={**context.source_records, name: c.digest(c.canonical_bytes(payload["source"]))},
    )
    numeric_refuse(envelope("learning-problem", name, payload, ctx), ctx, name)
    with pytest.raises(c.ContractError, match="float64"):
        c.rational(value)


@pytest.mark.parametrize(
    "value",
    [
        0,
        -1,
        2**53 - 1,
        2**53,
        2**53 + 2,
        2**54 - 2,
        -(2**54 - 2),
        2**54,
        2**54 + 4,
        -(2**54 + 4),
        2**-34,
        2**-1074,
        1e308,
    ],
)
def test_lossless_integer_neighbors_and_dyadics_roundtrip(bundle, value):
    name = "numeric-exact-" + c.digest(str(value).encode())[:16]
    original = make_problem(q=value)["original"]
    ctx, document, ref = admit_problem(original, bundle, name)
    admitted = c.read_artifact(ctx.root / ref["path"], ctx, expected_sha256=ref["sha256"])
    actual = admitted.payload["original"]["q"][0]
    assert actual == value and type(actual) is type(value)
    assert document["payload"]["original"]["q"][0] == value
    assert c.rational(actual) == Fraction(value)


@pytest.mark.parametrize(
    "field",
    [
        "P",
        "A",
        "q",
        "lower",
        "upper",
        "price",
        "unit",
        "canonical",
        "anchor",
        "direction",
    ],
)
def test_numeric_boundary_covers_original_transform_and_proof(bundle, field):
    context, docs, _ = bundle
    value = 2**54 - 1
    doc = copy.deepcopy(docs["result"] if field in ["anchor", "direction"] else docs["problem-train"])
    p = doc["payload"]
    if field in ["P", "A"]:
        p["original"][field]["data"][0] = value
    elif field in ["q", "lower", "upper"]:
        p["original"][field][0] = value
    elif field == "price":
        p["original"]["penalty"]["upper_linear"][0] = value
    elif field == "unit":
        p["original"]["units"]["D_x"][0] = value
    elif field == "canonical":
        p["transform"]["A"]["data"][0] = value
    else:
        p["certificate"] = dict(
            kind="exact-hard-qp-recession",
            anchor=[0],
            direction=[1],
            arithmetic="exact-submitted-float64-dyadics",
            screen_only=False,
        )
        p["certificate"][field][0] = value
    numeric_refuse(doc, context, "numeric-field-" + field)


@pytest.fixture(scope="session")
def graph_bundle(bundle):
    return PROVIDER["build_graph"](*bundle)


def test_integer_metadata_retains_exact_128bit_rng_serialization(bundle):
    context, _, _ = bundle
    name = "exact-integer-metadata"
    payload = make_problem(control="contract-fixture:integer-metadata")
    # Explicit serialization fields, not a claim that a scientific RNG ran.
    state = payload["source"]["rng_state"]
    state["state"].update(state=2**127 + 1, inc=2**128 - 1)
    payload["source"]["rng_state_sha256"] = c.digest(c.canonical_bytes(state))
    ctx = replace(
        context,
        problem_hashes={**context.problem_hashes, name: payload["original_sha256"]},
        source_records={**context.source_records, name: c.digest(c.canonical_bytes(payload["source"]))},
    )
    artifact = c.write_artifact(envelope("learning-problem", name, payload, ctx), name + ".json", ctx)
    result = c.read_artifact(ctx.root / (name + ".json"), ctx, expected_sha256=artifact.raw_sha256)
    assert result.payload["source"]["rng_state"]["state"] == {"state": 2**127 + 1, "inc": 2**128 - 1}


def test_rounded_decimal_token_cannot_replace_canonical_float64_bytes(bundle):
    name = "canonical-binary64-token"
    ctx, _, ref = admit_problem(make_problem(q=float(2**54))["original"], bundle, name)
    source = ctx.root / ref["path"]
    raw = source.read_bytes()
    token = json.dumps(float(2**54)).encode()
    assert token in raw
    malicious = raw.replace(token, (str(2**54 - 1) + ".0").encode(), 1)
    assert malicious != raw
    # The alternate token parses to the same float; the raw-byte check must refuse it.
    assert c.strict_loads(malicious) == c.strict_loads(raw)
    path = ctx.root / "rounded-decimal-token.json"
    path.write_bytes(malicious)
    try:
        with pytest.raises(c.ContractError, match="canonical"):
            c.read_artifact(path, ctx, expected_sha256=c.digest(malicious))
        assert path.read_bytes() == malicious and source.read_bytes() == raw
    finally:
        path.unlink()


def test_all_numeric_schema_nodes_declare_lossless_float64():
    def visit(value):
        if isinstance(value, dict):
            typ = value.get("type")
            if typ == "number" or isinstance(typ, list) and "number" in typ:
                assert value["format"] == "lossless-float64"
                return 1 + sum(visit(v) for v in value.values())
            return sum(visit(v) for v in value.values())
        if isinstance(value, list):
            return sum(map(visit, value))
        return 0

    counts = {
        kind: visit(c.strict_loads((c.SCHEMAS / ("softqp-" + kind + ".schema.json")).read_bytes()))
        for kind in c.KINDS
    }
    assert len(counts) == 11 and counts["learning-problem"] > 0 and counts["learning-method-result"] > 0


@pytest.mark.parametrize(
    "mutation",
    [
        "graph-order",
        "graph-edge",
        "graph-fit",
        "class-mass",
        "wrong-logit-bias",
        "calibration-grid",
        "calibration-tie",
        "calibration-observation",
        "calibration-score",
        "calibration-mask",
        "calibration-checkpoint",
    ],
)
def test_graph_and_calibration_real_boundaries(graph_bundle, mutation):
    context, docs, refs = graph_bundle
    for name in ["graph-features", "graph-checkpoint", "calibration-labels", "graph-calibration"]:
        assert c.read_artifact(context.root / refs[name]["path"], context).state == "provider"
    key = (
        "graph-features"
        if mutation.startswith("graph-")
        else ("graph-checkpoint" if mutation in ["class-mass", "wrong-logit-bias"] else "graph-calibration")
    )
    doc = copy.deepcopy(docs[key])
    p = doc["payload"]
    if mutation == "graph-order":
        p["graph"]["node_features"].reverse()
    elif mutation == "graph-edge":
        p["graph"]["edge_weight"][0] += 1
    elif mutation == "graph-fit":
        p["fit_access"] = ["fixture-source-test"]
    elif mutation == "class-mass":
        p["class_statistics"]["weight0"] = 2
    elif mutation == "wrong-logit-bias":
        next(t for t in p["architecture"]["parameters"] if t["name"] == "output_layer.lin1.bias")[
            "initialization_rule"
        ] = "train-log-positive-odds"
    elif mutation == "calibration-grid":
        p["threshold_grid"][0] = 0.05
    elif mutation == "calibration-tie":
        p["selected_threshold"] = 0.2
    elif mutation == "calibration-observation":
        p["observations"][0]["probabilities"][3] = 0.1
    elif mutation == "calibration-score":
        p["scores"][0] = 1
    elif mutation == "calibration-mask":
        p["mask_count"] = 0
    else:
        p["checkpoint"]["sha256"] = "0" * 64
    refuse(doc, context, mutation)


@pytest.mark.parametrize(
    "mutation", ["variable-label", "equality-mask", "ambiguity-mask", "oracle-source", "native-flag"]
)
def test_label_masks_and_source_refusal(bundle, mutation):
    context, docs, _ = bundle
    doc = copy.deepcopy(docs["labels"])
    p = doc["payload"]
    if mutation == "variable-label":
        p["labels"][0] = 1
        p["mask"][0] = True
    elif mutation == "equality-mask":
        p["node_kind"][2] = "equality"
    elif mutation == "ambiguity-mask":
        p["labels"][3] = 1
        p["mask"][3] = True
    elif mutation == "oracle-source":
        p["oracle_source_sha256"] = "0" * 64
    else:
        p["cold_native_flag"] = -6
    refuse(doc, context, "label-" + mutation)


def test_oracle_and_runtime_missing_records_preserve_denominators(bundle):
    context, docs, _ = bundle
    missing = copy.deepcopy(docs["result"])
    p = missing["payload"]
    missing["artifact_id"] = "runtime-missing"
    p.update(status="missing", reason="runtime-not-installed", oracles=[])
    for trial in p["trials"]:
        trial.update(
            status="missing",
            reason="runtime-not-installed",
            native_flag=None,
            candidate=None,
            metrics=None,
            full_cost=0,
            timing={k: 0 for k in trial["timing"]},
        )
    artifact = c.write_artifact(reseal(missing), "runtime-missing.json", context)
    ref = dict(
        kind="learning-method-result",
        artifact_id="runtime-missing",
        path="runtime-missing.json",
        sha256=artifact.raw_sha256,
    )
    ctx = replace(context, catalog={**context.catalog, "runtime-missing": ref})
    evaluation = copy.deepcopy(docs["evaluation"])
    evaluation["artifact_id"] = "runtime-missing-evaluation"
    e = evaluation["payload"]
    e["results"] = [ref]
    e["denominators"].update(accepted=0, failed=1)
    c.write_artifact(reseal(evaluation), "runtime-missing-evaluation.json", ctx)
    bad = copy.deepcopy(evaluation)
    bad["payload"]["denominators"]["failed"] = 0
    refuse(bad, ctx, "missing-runtime-denominator")
    failed = copy.deepcopy(docs["labels"])
    failed["artifact_id"] = "oracle-missing-labels"
    l = failed["payload"]
    l.update(
        status="oracle-failed", reason="reference-not-installed", cold_candidate=None, cold_native_flag=None
    )
    for key in ["slack", "multipliers", "labels", "mask", "node_kind", "bound"]:
        l[key] = []
    for oracle in l["oracle_results"]:
        oracle.update(
            status="missing",
            reason="reference-not-installed",
            accepted=False,
            candidate=None,
            metrics=None,
            native_flag=None,
        )
        oracle["result_sha256"] = c.digest(
            c.canonical_bytes({k: v for k, v in oracle.items() if k != "result_sha256"})
        )
    c.write_artifact(reseal(failed), "oracle-missing-labels.json", context)
    bad = copy.deepcopy(failed)
    bad["payload"]["labels"] = [1]
    refuse(bad, context, "fabricated-label-after-oracle-failure")


def test_protocol_parent_missing_is_not_self_authorized(bundle):
    context, docs, _ = bundle
    doc = copy.deepcopy(docs["problem-train"])
    doc["protocol_ref"] = None
    refuse(doc, context, "absent-approved-protocol")


def test_same_size_numeric_change_cannot_use_consumer_cache(bundle):
    context, _, _ = bundle
    c.read_artifact(context.root / "checkpoint.json", context)
    path = context.root / "fixture-untrained.f64"
    raw = path.read_bytes()
    path.write_bytes(struct.pack("<d", 1) + raw[8:])
    try:
        with pytest.raises(c.ContractError):
            c.read_artifact(context.root / "checkpoint.json", context)
    finally:
        path.write_bytes(raw)


def test_symlink_and_checkout_output_refusal(bundle):
    context, docs, _ = bundle
    nested = context.root / "nested-checkout"
    nested.mkdir()
    (nested / ".git").write_bytes(b"contract-fixture\n")
    with pytest.raises(c.ContractError):
        c.write_artifact(docs["problem-train"], "nested-checkout/output.json", context)
    assert not (nested / "output.json").exists()
    alias = context.root / "symlink.json"
    try:
        alias.symlink_to(context.root / "protocol.json")
    except OSError:
        import subprocess

        junction = context.root / "junction"
        quoted_link = str(junction).replace("'", "''")
        quoted_target = str(context.root).replace("'", "''")
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"New-Item -ItemType Junction -Path '{quoted_link}' -Target '{quoted_target}' -ErrorAction Stop | Out-Null",
            ],
            check=True,
            capture_output=True,
        )
        try:
            assert junction.is_junction()
            with pytest.raises(c.ContractError):
                c.read_artifact(junction / "protocol.json", context)
            with pytest.raises(c.ContractError):
                c.write_artifact(docs["problem-train"], "junction/output.json", context)
        finally:
            os.rmdir(junction)
        return
    try:
        with pytest.raises(c.ContractError):
            c.read_artifact(alias, context)
        with pytest.raises(c.ContractError):
            c.write_artifact(docs["problem-train"], "symlink.json", context)
    finally:
        alias.unlink()


def test_diagnostic_inventory_and_independent_evidence_admission(bundle):
    context, docs, _ = bundle
    keys = context.authority.keys("diagnostic-status")
    assert len(keys) == len(set(keys)) == 101
    key = next(k for k in keys if k[0] == "NC23-tiny-positive-curvature")
    control = next(v for v in context.authority.controls if v["id"] == key[0])
    outcome = control["outcomes"][key[1]]
    ctx = replace(context, expected_diagnostic_keys=(key,))
    doc = copy.deepcopy(docs["evaluation"])
    doc["artifact_id"] = "diagnostic-missing-evaluation"
    item = dict(
        key=list(key),
        fixture_sha256=c.digest(c.canonical_bytes(control)),
        state="missing",
        expected_outcome=outcome,
        observed_outcome=None,
        reason="reader-not-executed",
        evidence=None,
    )
    doc["payload"].update(
        diagnostics=[item], diagnostic_denominators=dict(expected=1, passed=0, failed=0, missing=1)
    )
    c.write_artifact(reseal(doc), "diagnostic-missing-evaluation.json", ctx)
    bad = copy.deepcopy(doc)
    bad["payload"]["diagnostics"] = []
    refuse(bad, ctx, "dropped-diagnostic")
    log = b"Explicit contract fixture, not a solver or scientific observation.\n"
    (ctx.root / "diagnostic-fixture.txt").write_bytes(log)
    item.update(
        state="passed",
        observed_outcome=outcome,
        reason=None,
        evidence=dict(
            path="diagnostic-fixture.txt", sha256=c.digest(log), byte_count=len(log), format="utf8-log"
        ),
    )
    doc["payload"]["diagnostic_denominators"] = dict(expected=1, passed=1, failed=0, missing=0)
    refuse(doc, ctx, "unreviewed-diagnostic-evidence")
    sealed = replace(ctx, diagnostic_evidence={key: c.digest(log)})
    c.write_artifact(reseal(doc), "diagnostic-sealed-provider.json", sealed)


def test_trusted_authority_and_locks_cannot_be_replaced(bundle):
    context, docs, _ = bundle
    with pytest.raises(c.ContractError):
        replace(context, source_lock_bytes=b"changed-source-lock")
    with pytest.raises(c.ContractError):
        replace(context.authority, _matrix=b"{}\n")
    with pytest.raises(TypeError):
        context.catalog["protocol"]["sha256"] = "0" * 64
    doc = copy.deepcopy(docs["problem-train"])
    doc.update(purpose="scientific", state="available", reason=None)
    production = replace(
        context,
        allow_fixture=False,
        expected_result_keys=context.authority.keys("method-status")
        + context.authority.keys("control-status"),
        expected_diagnostic_keys=context.authority.keys("diagnostic-status"),
    )
    refuse(doc, production, "fixture-relabelled-scientific")


def test_exact_symmetry_refusal_with_other_dimensions_valid(bundle):
    o = make_problem()["original"]
    o.update(
        n=2,
        m=2,
        P=c.csc([[1, 0.25], [0.25, 1]]),
        A=c.csc([[1, 0], [0, 1]]),
        q=[0, 0],
        lower=[0, 0],
        upper=[1, 1],
        lower_finite=[True, True],
        upper_finite=[True, True],
    )
    o["penalty"] = {k: ([True, True] if k == "soft" else [1, 1]) for k in o["penalty"]}
    o["units"].update(variable=["dimensionless"] * 2, row=["dimensionless"] * 2, D_x=[1, 1], D_r=[1, 1])
    context, doc, _ = admit_problem(o, bundle, "symmetric-two-variable")
    bad = copy.deepcopy(doc)
    bad["payload"]["original"]["P"] = c.csc([[1, 0.25], [0.5, 1]])
    with pytest.raises(c.ContractError, match="symmetry"):
        c.validate_artifact(reseal(bad), context)
    refuse(bad, context, "asymmetric-P-valid-dimensions")


def test_weighted_peak_recovery_through_real_result_reader(bundle):
    context, docs, _ = bundle
    o = make_problem()["original"]
    o.update(
        q=[-19],
        lower=[None],
        upper=[0],
        lower_finite=[False],
        upper_finite=[True],
        formulation="peak",
        groups=[dict(group_id=0, rows=[0], lower_scale=[1], upper_scale=[4], linear=0.5, quadratic=1)],
    )
    o["penalty"] = {k: ([True] if k == "soft" else [0]) for k in o["penalty"]}
    o["units"].update(peak=["dimensionless"], D_t=[1])
    context, problem, ref = admit_problem(
        o, bundle, "weighted-peak-original", control="NC12-weighted-peak-dual"
    )
    candidate = dict(
        x=[1],
        y=[18],
        lifted_x=[1, 4],
        lifted_y=[4.5, 0],
        epigraph=dict(t=[4], lambda_lower=[0], lambda_upper=[4.5], mu=[0]),
    )
    metric = c.original_metrics(o, candidate, -8.5)
    assert metric["objective"] == -8.5 and metric["K"] == metric["F"] == 0 and metric["peak_values"] == [4]
    doc = copy.deepcopy(docs["result"])
    doc["artifact_id"] = "weighted-peak-result"
    p = doc["payload"]
    p.update(
        problem=ref,
        semantic_transform="G",
        dimensions=dict(original_n=1, original_m=1, canonical_n=2, canonical_m=2),
    )
    for oracle in p["oracles"]:
        oracle.update(candidate=copy.deepcopy(candidate), metrics=copy.deepcopy(metric))
        oracle["result_sha256"] = c.digest(
            c.canonical_bytes({k: v for k, v in oracle.items() if k != "result_sha256"})
        )
    for trial in p["trials"]:
        trial.update(candidate=copy.deepcopy(candidate), metrics=copy.deepcopy(metric))
    artifact = c.write_artifact(reseal(doc), "weighted-peak-result.json", context)
    assert (
        c.read_artifact(context.root / "weighted-peak-result.json", context).raw_sha256 == artifact.raw_sha256
    )
    bad = copy.deepcopy(doc)
    bad["payload"]["trials"][0]["candidate"]["y"] = [4.5]
    refuse(bad, context, "unweighted-peak-dual")
    bad = copy.deepcopy(doc)
    bad["payload"]["trials"][0]["candidate"]["epigraph"]["mu"] = [1]
    refuse(bad, context, "wrong-peak-group-stationarity")


def test_crossed_bootstrap_receipt_and_preserved_reversal(bundle):
    import numpy as np

    context, _, _ = bundle
    cold, learned = [1, 1, 100], [0.5, 0.5, 120]
    reduction = c.trajectory_reduction(cold, learned)
    assert reduction == 1 - 121 / 102 < 0 and sorted(1 - b / a for a, b in zip(cold, learned))[1] == 0.5
    totals = [
        dict(
            method="learned_osqp",
            seed=seed,
            family="N01",
            regime=3,
            source_index=0,
            learned=121,
            cold=102,
            reduction=reduction,
        )
        for seed in c.SEEDS
    ]
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([20261105, 41100, 0])))
    raw = bytearray()
    for _ in range(10000):
        raw.extend(int(x) for x in rng.integers(0, 3, size=3))
        raw.extend(int(x) for x in rng.integers(0, 1, size=1))
    path = context.root / "hand-array-bootstrap.u8"
    path.write_bytes(raw)
    ref = dict(path=path.name, sha256=c.digest(bytes(raw)), byte_count=len(raw), format="raw-uint8")
    interval = c._bootstrap_interval(totals, "learned_osqp", ref, context)
    assert interval == pytest.approx([reduction, reduction], abs=1e-15) and interval[1] < 0
    raw[0] = 3
    path.write_bytes(raw)
    ref["sha256"] = c.digest(bytes(raw))
    with pytest.raises(c.ContractError, match="seed draw"):
        c._bootstrap_interval(totals, "learned_osqp", ref, context)


def test_committed_examples_use_the_actual_independent_consumer(tmp_path):
    import shutil

    source = Path(__file__).parent / "fixtures/learned-contracts/provider-tree"
    destination = tmp_path / "committed-provider"
    shutil.copytree(source, destination)
    context = PROVIDER["load_context"](destination)
    examples = c.ROOT / "docs/contracts/examples"
    for kind in c.KINDS:
        example = examples / ("softqp-" + kind + ".json")
        document = c.strict_loads(example.read_bytes())
        ref = context.catalog[document["artifact_id"]]
        assert example.read_bytes() == (destination / ref["path"]).read_bytes()
        result = c.read_artifact(destination / ref["path"], context, expected_sha256=ref["sha256"])
        assert result.state == "provider" and result.payload is not None


def test_typed_boundaries_match_all_eleven_schema_required_fields():
    names = [
        "Protocol",
        "Problem",
        "Dataset",
        "Split",
        "Features",
        "Labels",
        "Checkpoint",
        "Calibration",
        "MethodResult",
        "Evaluation",
        "ExportIndex",
    ]
    for kind, name in zip(c.KINDS, names):
        schema = c.strict_loads((c.SCHEMAS / ("softqp-" + kind + ".schema.json")).read_bytes())
        assert set(c.Envelope.__required_keys__) == set(schema["properties"]) == set(schema["required"])
        payload = schema["properties"]["payload"]["anyOf"][0]
        assert (
            set(getattr(c, name + "Payload").__required_keys__)
            == set(payload["properties"])
            == set(payload["required"])
        )


def test_training_result_cannot_enter_heldout_ledger(bundle):
    context, docs, refs = bundle
    doc = copy.deepcopy(docs["result"])
    doc["payload"]["problem"] = refs["problem-train"]
    with pytest.raises(c.ContractError, match="held-out test source"):
        c.validate_artifact(reseal(doc), context)
    refuse(doc, context, "training-result-in-heldout-ledger")


def extra_problem(bundle, name, split, q):
    context, docs, refs = bundle
    p = make_problem(split, q)
    p["source"].update(source_id=name + "-source", parent_id=name + "-parent")
    ctx = replace(
        context,
        problem_hashes={**context.problem_hashes, name: p["original_sha256"]},
        source_records={**context.source_records, name: c.digest(c.canonical_bytes(p["source"]))},
    )
    doc = envelope("learning-problem", name, p, ctx)
    a = c.write_artifact(doc, name + ".json", ctx)
    ref = dict(kind="learning-problem", artifact_id=name, path=name + ".json", sha256=a.raw_sha256)
    return replace(ctx, catalog={**ctx.catalog, name: ref}), doc, ref


def retarget_result(bundle, ctx, ref, method):
    _, docs, refs = bundle
    doc = copy.deepcopy(docs["result"])
    p = doc["payload"]
    p.update(problem=ref, method=method, settings_sha256=ctx.settings_hashes[method])
    p["key"][0] = method
    problem = c.dependency(ref, ctx, ())
    candidate = dict(x=[0.5], y=[0], lifted_x=[0.5, 0], lifted_y=[0, 0, -1], epigraph=None)
    metric = c.original_metrics(problem["original"], candidate, -0.125)
    for o in p["oracles"]:
        o.update(candidate=copy.deepcopy(candidate), metrics=copy.deepcopy(metric))
        o["result_sha256"] = c.digest(c.canonical_bytes({k: v for k, v in o.items() if k != "result_sha256"}))
    for trial in p["trials"]:
        trial.update(
            candidate=copy.deepcopy(candidate),
            metrics=copy.deepcopy(metric),
            native_flag="Solved" if method == "clarabel" else 1,
        )
    return doc


def test_dataset_refuses_duplicate_registered_source_unit_slot(bundle):
    ctx, problem, ref = extra_problem(bundle, "duplicate-train-slot", "train", 0.125)
    _, docs, _ = bundle
    doc = copy.deepcopy(docs["dataset"])
    p = doc["payload"]
    p["problems"].append(dict(problem=ref, source=problem["payload"]["source"]))
    p["problems"].sort(key=lambda e: e["problem"]["artifact_id"])
    p["source_ids"] = sorted(p["source_ids"] + [problem["payload"]["source"]["source_id"]])
    p["counts"].update(problems=5, sources=5, train=2)
    with pytest.raises(c.ContractError, match="source-unit slot"):
        c.validate_artifact(reseal(doc), ctx)
    refuse(doc, ctx, "duplicate-source-unit-slot")


def test_pairing_refuses_individually_valid_different_inputs(bundle):
    ctx, problem, ref = extra_problem(bundle, "alternative-heldout-input", "test", -0.5)
    _, docs, refs = bundle
    doc = retarget_result(bundle, ctx, ref, "clarabel")
    doc["artifact_id"] = "alternative-clarabel-result"
    a = c.write_artifact(reseal(doc), "alternative-clarabel-result.json", ctx)
    newref = dict(
        kind="learning-method-result",
        artifact_id=doc["artifact_id"],
        path="alternative-clarabel-result.json",
        sha256=a.raw_sha256,
    )
    keys = ctx.expected_result_keys + (tuple(doc["payload"]["key"]),)
    ctx = replace(ctx, catalog={**ctx.catalog, doc["artifact_id"]: newref}, expected_result_keys=keys)
    evaluation = copy.deepcopy(docs["evaluation"])
    e = evaluation["payload"]
    e["results"] = [refs["result"], newref]
    e["denominators"].update(expected=2, accepted=2)
    e["expected_keyset_sha256"] = c.digest(b"".join(c.canonical_bytes(list(k)) for k in sorted(keys)))
    with pytest.raises(c.ContractError, match="different source-frame inputs"):
        c.validate_artifact(reseal(evaluation), ctx)
    refuse(evaluation, ctx, "unpaired-source-inputs")


def test_learned_result_requires_checkpoint_heldout_membership(bundle):
    ctx, problem, ref = extra_problem(bundle, "foreign-checkpoint-test-source", "test", -0.5)
    _, docs, refs = bundle
    doc = retarget_result(bundle, ctx, ref, "learned_osqp")
    p = doc["payload"]
    p["key"][1] = 41001
    p.update(
        checkpoint=refs["checkpoint"],
        calibration=refs["calibration"],
        injected_state=dict(x=[0, 0], y=[0, 0, 0], scores=[], flags=[]),
    )
    with pytest.raises(c.ContractError, match="checkpoint held-out split"):
        c.validate_artifact(reseal(doc), ctx)
    refuse(doc, ctx, "foreign-checkpoint-heldout-source")


@pytest.mark.parametrize("mutation", ["rank", "pure-L1", "hard-equality"])
def test_primary_problem_domains_match_registered_semantic_row(bundle, mutation):
    context, _, _ = bundle
    o = make_problem()["original"]
    family = "N01"
    if mutation == "rank":
        o["P"] = c.csc([[0]])
    elif mutation == "pure-L1":
        o["penalty"]["lower_quadratic"] = o["penalty"]["upper_quadratic"] = [0]
    else:
        family = "N04"
        o.update(
            n=2,
            m=6,
            P=c.csc([[1, 0], [0, 1]]),
            A=c.csc([[1, 0], [0, 1], [1, 0], [0, 1], [1, 0], [0, 1]]),
            q=[0, 0],
            lower=[0] * 6,
            upper=[0, 1, 1, 1, 1, 1],
            lower_finite=[True] * 6,
            upper_finite=[True] * 6,
        )
        o["penalty"] = {
            "soft": [False, False, True, True, True, True],
            **{
                k: [0, 0, 1, 1, 1, 1]
                for k in ["lower_linear", "upper_linear", "lower_quadratic", "upper_quadratic"]
            },
        }
        o["units"].update(variable=["dimensionless"] * 2, row=["dimensionless"] * 6, D_x=[1] * 2, D_r=[1] * 6)
    payload = make_problem(original=o, family=family)
    name = "domain-" + mutation
    ctx = replace(
        context,
        problem_hashes={**context.problem_hashes, name: payload["original_sha256"]},
        source_records={**context.source_records, name: c.digest(c.canonical_bytes(payload["source"]))},
    )
    doc = envelope("learning-problem", name, payload, ctx)
    with pytest.raises(c.ContractError, match="registered"):
        c.validate_artifact(doc, ctx)
    refuse(doc, ctx, "registered-domain-" + mutation)


@pytest.mark.parametrize("api", ["writer", "reader"])
def test_extreme_integer_parse_and_format_limits_are_contract_refusals(bundle, api):
    context, docs, _ = bundle
    output = context.root / ("extreme-integer-" + api + "-output.json")
    before = {p.name for p in context.root.iterdir()}
    document = copy.deepcopy(docs["problem-train"])
    if api == "writer":
        value = 10**5000
        document["payload"]["original"]["q"][0] = value
        with pytest.raises(c.ContractError, match="numeric.*representation"):
            c.write_artifact(document, output.name, context)
        assert document["payload"]["original"]["q"][0] == value
    else:
        raw = c.json_bytes(document)
        token = b'"q": [\n        0\n      ]'
        assert token in raw
        malicious = raw.replace(token, b'"q": [\n        ' + b"9" * 5000 + b"\n      ]", 1)
        assert malicious != raw and len(malicious) < 50000
        path = context.root / "extreme-integer-raw.json"
        path.write_bytes(malicious)
        try:
            with pytest.raises(c.ContractError, match="numeric.*representation"):
                c.read_artifact(path, context, expected_sha256=c.digest(malicious))
            assert path.read_bytes() == malicious
        finally:
            path.unlink()
    assert not output.exists() and before == {p.name for p in context.root.iterdir()}


@pytest.mark.parametrize("field,value", [("state", 2**128), ("inc", 2**128 + 1)])
def test_integer_metadata_maximum_remains_active_in_real_apis(bundle, field, value):
    context, _, _ = bundle
    name = "metadata-out-of-range-" + field
    payload = make_problem(control="contract-fixture:metadata-range")
    source = payload["source"]
    source["rng_state"]["state"][field] = value
    source["rng_state_sha256"] = c.digest(c.canonical_bytes(source["rng_state"]))
    ctx = replace(
        context,
        problem_hashes={**context.problem_hashes, name: payload["original_sha256"]},
        source_records={**context.source_records, name: c.digest(c.canonical_bytes(source))},
    )
    document = envelope("learning-problem", name, payload, ctx)
    numeric_refuse(document, ctx, name, reason="maximum")
