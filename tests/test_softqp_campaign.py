"""Generator invariants and preregistered endpoint refusal, without held-out fitting."""

from dataclasses import replace
import json
from pathlib import Path
import time
import numpy as np
from pipeline.softqp_campaign import generated_problem, instances, primary_endpoint, BoundedWorker
from pipeline.experiment_common import oracle

ROOT = Path(__file__).resolve().parents[1]


def protocol():
    return json.loads((ROOT / "docs/design/experiments-v1.json").read_text(encoding="utf-8"))


def test_conditioning_changes_only_hessian():
    spec = dict(n=32, density=0.1, seed=1000, family="asymmetric-elastic", condition=1)
    first = generated_problem(spec)
    other = generated_problem(dict(spec, condition=1e6))
    assert (first.A != other.A).nnz == 0
    np.testing.assert_array_equal(first.q, other.q)
    np.testing.assert_array_equal(first.penalty.upper_linear, other.penalty.upper_linear)
    np.testing.assert_allclose(np.sqrt(first.A.multiply(first.A).sum(axis=1)).A1, 1)
    assert other.P.diagonal().max() / other.P.diagonal().min() == 1e6
    assert (~first.penalty.soft).sum() == int(0.2 * 64)
    l1 = generated_problem(dict(spec, family="asymmetric-l1"))
    assert l1.penalty.soft.all()
    assert not l1.penalty.lower_quadratic.any() and not l1.penalty.upper_quadratic.any()


def test_endpoint_retains_a_rejected_pair():
    rows = []
    for seed in range(3):
        for method, elapsed in [("asymmetric", 1), ("lifted", 2), ("daqp", 3)]:
            rows.append(dict(id=str(seed), seed=seed, split="heldout", family="asymmetric-elastic",
                             n=128, density=0.05, method=method, repetition=0, warmup=False,
                             state="accepted", elapsed_seconds=elapsed))
    result = primary_endpoint(rows, protocol())
    assert result["state"] == "met" and result["median_relative_reduction"] == 0.5
    rows[-1]["state"] = "accuracy-rejected"
    result = primary_endpoint(rows, protocol())
    assert result["state"] == "not-established" and result["rejected_pairs"] == 1


def test_planned_matrix_has_exact_split_sizes():
    assert [len(instances(protocol(), split)) for split in ("development", "heldout", "robustness")] == [144, 288, 24]


def test_adversarial_bounded_worker_keeps_invalid_input_as_failure(monkeypatch):
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(name, "1")
    problem = generated_problem(dict(n=4, density=0.2, seed=1000, family="asymmetric-elastic", condition=1))
    _, objective = oracle(problem)
    runner = BoundedWorker(protocol()["operating_limits"])
    try:
        good = runner.observe(problem, "asymmetric", objective, time.monotonic() + 30)
        assert good["state"] == "accepted"
        assert 0 < runner.peak_rss < 4 * 1024**3
        invalid = replace(problem, q=np.array([np.nan] * 4))
        bad = runner.observe(invalid, "asymmetric", objective, time.monotonic() + 30)
        assert bad["state"] == "failed" and "NaN" in bad["reason"]
    finally:
        runner.close()
