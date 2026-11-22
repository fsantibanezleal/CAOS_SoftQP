"""Small analytic SDK and existing v2 contract controls. No I1 record is issued."""
from hashlib import sha256
import importlib
import json
from pathlib import Path


def warm_imports():
    for name in ("numpy", "scipy.sparse", "osqp", "clarabel", "proxsuite", "piqp", "daqp",
                 "elastiqp", "softqp.learning.solvers", "torch_geometric.nn", "test_stream_inputs"):
        importlib.import_module(name)


def live_defaults(profile, stamp):
    import clarabel
    import daqp
    import elastiqp
    import osqp
    import piqp
    import proxsuite
    import softqp

    path = profile / "sdk-verify.py"
    raw = path.read_bytes()
    assert sha256(raw).hexdigest() == stamp["sdk_verify_sha256"]
    helper = {"__name__": "pinned_sdk_binary_probe"}
    exec(compile(raw, str(path), "exec", optimize=0), helper)
    defaults, serial = helper["defaults"], helper["serial"]
    actual = {}
    for mod in (osqp, softqp):
        settings = mod.ext_builtin.OSQPSettings()
        mod.ext_builtin.osqp_set_default_settings(settings)
        actual[mod.__name__] = defaults(settings)
    actual.update(
        clarabel=defaults(clarabel.DefaultSettings()),
        proxsuite=defaults(proxsuite.proxqp.sparse.QP(2, 1, 2).settings),
        piqp=defaults(piqp.SparseSolver().settings),
        daqp=serial(daqp.Model().settings),
        elastiqp=defaults(elastiqp.Settings("das")),
    )
    expected = (profile / "defaults.json").read_bytes()
    assert json.loads(expected) == actual
    return sha256(expected).hexdigest()


def reference():
    from pipeline.learned_comparison import contracts as c
    from pipeline.learned_comparison.native_labels import _prepare
    from test_learned_contracts import PROVIDER

    problems, evidence, summaries = [], [], []
    for sign in (1, -1):
        known = PROVIDER["problem_payload"]("train", 0)["original"]
        known["P"] = c.csc([[1.0]])
        known["A"] = c.csc([[1.0]])
        known["q"] = [-3.0 * sign]
        known["lower"], known["upper"] = [-1.0], [1.0]
        known["lower_finite"], known["upper_finite"] = [True], [True]
        known["penalty"] = {key: [False] if key == "soft" else [0.0] for key in known["penalty"]}
        problem = _prepare(known)
        oracle = problem.reference()
        observed = oracle.as_dict()
        assert observed["status"] == "oracle-agreed", observed
        assert abs(observed["objective"] + 2.5) < 1e-6, observed
        problems.append(problem)
        evidence.append(oracle)
        summaries.append(observed)
    return problems, evidence, {"cases": summaries, "sealed_reference": True}


def cold(problems, references):
    from pipeline.learned_comparison.native_labels import _actual_cold

    result = []
    for problem, oracle, sign in zip(problems, references, (1, -1)):
        observation, timing = _actual_cold(problem, oracle)
        candidate = observation["result"]
        assert abs(candidate["y"][0] - 2 * sign) < 1e-5, candidate
        assert abs(candidate["x"][0] - sign) < 1e-5, candidate
        result.append({"candidate": observation, "telemetry": timing})
    return {"signed_daqp_cases": result}


def gradient():
    import torch
    from torch_geometric.nn import LEConv

    rhs = torch.tensor([2., 8.], dtype=torch.float64, requires_grad=True)
    answer = torch.linalg.solve(torch.diag(torch.tensor([2., 4.], dtype=torch.float64)), rhs)
    answer.sum().backward()
    assert answer.tolist() == [1., 2.] and rhs.grad.tolist() == [.5, .25]
    conv = LEConv(1, 1).double()
    with torch.no_grad():
        conv.lin1.weight.fill_(2.)
        conv.lin1.bias.fill_(.5)
        conv.lin2.weight.fill_(3.)
        conv.lin3.weight.fill_(4.)
        conv.lin3.bias.fill_(1.)
    x = torch.tensor([[1.], [2.], [4.]], dtype=torch.float64, requires_grad=True)
    out = conv(x, torch.tensor([[0, 1], [1, 2]]), torch.tensor([2., 3.], dtype=torch.float64))
    out.sum().backward()
    assert out.tolist() == [[5.], [2.], [-5.5]] and x.grad.tolist() == [[8.], [4.], [-5.]]
    return dict(torch_gradient=rhs.grad.tolist(), leconv=out.tolist(), leconv_gradient=x.grad.tolist())


def reader(run):
    from pipeline.learned_comparison import contracts as c
    from pipeline.learned_comparison import stream_inputs as stream
    from test_learned_contracts import PROVIDER
    from test_stream_inputs import build_factored, phase_reader, put

    context, docs, refs = PROVIDER["build"](run / "fixture")
    roles = ("train", "validation", "calibration", "test")
    known = {"qualification-" + role: docs["problem-" + role]["payload"] for role in roles}
    protocol = refs["protocol"]
    context, sources, frames = build_factored(context, protocol, known)
    candidate = stream.derive_stream_payload(
        context, protocol, sources=sources, frames=list(frames.values()), fit_source_ids=list(context.fit_source_ids),
        exclusions=sorted(docs["dataset"]["payload"]["exclusions"]), attribution="Excluded runtime software fixture",
        license="MIT", labels=[{"frame_id": name, "ref": None, "state": "missing", "reason": "Excluded fixture"}
                              for name in known])
    context, ref = put(context, protocol, stream.STREAM, "qualification-stream", candidate)
    preflight = stream.preflight_stream(context, descriptor_id=ref["artifact_id"],
                                       expected_descriptor_sha256=ref["sha256"])
    materialized, digest = phase_reader(preflight, run / "fixture-train", "train")
    assert c.canonical_bytes(materialized.read_problem("qualification-train")) == c.canonical_bytes(known["qualification-train"])
    assert materialized.read_feature("qualification-train", "mlp-v1").document["coordinate_order"]
    try:
        materialized.read_problem("qualification-test")
    except c.ContractError:
        pass
    else:
        raise AssertionError("train reader accepted a held-out record")
    return dict(fixture_only=True, preflight_sha256=preflight.sha256, manifest_sha256=digest, blocked_test=True,
                logical_keys=len(materialized.logical_keys))
