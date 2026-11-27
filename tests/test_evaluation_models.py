"""Excluded fit/calibration projections and held-out model-only filesystem scope."""

from collections import Counter
from dataclasses import replace
from pathlib import Path
import runpy
import sys
from types import ModuleType

import pytest

from pipeline.learned_comparison import contracts as c
from pipeline.learned_comparison import evaluation_models as models
from pipeline.learned_comparison import learning_exports as exports
from pipeline.learned_comparison import training as t

pytest_plugins = ("test_learned_training",)


def assert_detached_reload(admitted_model, monkeypatch):
    from pipeline.learned_comparison import evaluation_worker
    from softqp.learning.parameters import weight_bytes

    prep = admitted_model.preprocessing
    head = prep["heads"][0]
    observed_priors = []
    original_load = evaluation_worker.load_numeric_model

    def observe_load(**kwargs):
        observed_priors.append(kwargs["prior"])
        return original_load(**kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(evaluation_worker, "load_numeric_model", observe_load)
        first, normalizer, digest, threshold = admitted_model.load_head(head)
        public_disposition = admitted_model.disposition
        public_disposition["threshold"] = 0.1 if threshold != 0.1 else 0.2
        public_weights = admitted_model.weights
        public_weights.update(path="other.f64", byte_count=8, sha256="0" * 64)
        tensor = admitted_model.tensors[0]
        tensor.update(offset=1, count=1, sha256="0" * 64)
        tensor["shape"][0] += 1
        if normalizer is not None:
            prep["normalizers"][0]["mean"][0] += 1
            prep["normalizers"][0]["scale"][0] += 1
        else:
            prep["class_statistics"]["positive_prior"] /= 2
        prep["heads"].clear()
        second, reloaded, second_digest, second_threshold = admitted_model.load_head(head)
    assert second_digest == digest == c.digest(weight_bytes(first)) == c.digest(weight_bytes(second))
    assert second_threshold == threshold
    if normalizer is None:
        prior = admitted_model.preprocessing["class_statistics"]["positive_prior"]
        assert observed_priors == [prior, prior] and reloaded is None
    else:
        assert observed_priors == [None, None]
        assert reloaded.numeric_sha256 == normalizer.numeric_sha256


def project(root, plan, runtime, readers, proofs, method, seed, monkeypatch):
    target = root / method
    target.mkdir()
    training = t.supervise_training(
        plan, runtime, method=method, seed=seed, destination=target / "training", fixture_stop_after=3
    )
    assert training.document["state"] == "fixture-exercise", training.document["reason"]
    checkpoint = training.document["checkpoints"]["final"]["sha256"]
    budget = t.LearningBudget((root,), training.root)
    if method == "learned_osqp":
        with monkeypatch.context() as patch:
            patch.setattr(t, "_LIMIT", budget.check() + 1)
            blocked = exports.export_training(
                target,
                "quota",
                training,
                plan=plan,
                runtime=runtime,
                budget=budget,
                require_live=runtime.verify,
            )
            assert all("disk budget" in value["reason"] for value in blocked.values())
            assert not (target / "quota-frozen").exists()
        with monkeypatch.context() as patch:

            def fail(*args, **kwargs):
                raise OSError("observed partial publication")

            patch.setattr(models, "publish_preprocessing", fail)
            blocked = exports.export_training(
                target,
                "partial",
                training,
                plan=plan,
                runtime=runtime,
                budget=budget,
                require_live=runtime.verify,
            )
            assert all(value["state"] == "unavailable" for value in blocked.values())
            assert (training.root / "training-run.json").is_file() and (target / "partial-frozen").is_dir()
    projected = exports.export_training(
        target, "training", training, plan=plan, runtime=runtime, budget=budget, require_live=runtime.verify
    )
    assert all(value["state"] == "available" for value in projected.values()), projected
    frozen_sha = projected["frozen"]["ref"]["sha256"]
    frozen = t.read_frozen_inference(
        target / "training-frozen",
        expected_receipt_sha256=frozen_sha,
        expected_run_sha256=training.sha256,
        expected_checkpoint_sha256=checkpoint,
        allow_fixture=True,
    )
    preprocessing = target / "training-preprocessing"
    pre_sha = projected["preprocessing"]["ref"]["sha256"]
    with pytest.raises(c.ContractError, match="stored bytes"):
        exports.validate_preprocessing(preprocessing, "a" * 64, frozen, context=plan.context)
    exports.validate_preprocessing(preprocessing, pre_sha, frozen, context=plan.context)
    calibration = readers["calibration"]
    cal_plan = t.CalibrationPlan.admit(
        None,
        context=plan.context,
        calibration=calibration,
        frozen_inference=frozen,
        native_role_proof=proofs["calibration"],
        expected_policy_sha256=calibration._identities["learning_policy_sha256"],
        expected_calibration_manifest_sha256=calibration.manifest_sha256,
        expected_receipt_sha256=frozen.sha256,
        expected_run_sha256=training.sha256,
        expected_checkpoint_sha256=checkpoint,
    )
    cal_root = target / "calibration"
    cal_result = t.supervise_calibration(cal_plan, runtime, cal_root)
    assert cal_result["state"] == ("calibrated" if method == "learned_daqp" else "not-applicable")
    cal_sha = c.digest((cal_root / "calibration.json").read_bytes())
    observed = exports.export_calibration(
        target,
        "calibration",
        cal_result,
        plan=cal_plan,
        runtime=runtime,
        budget=budget,
        require_live=runtime.verify,
        preprocessing_root=preprocessing,
        preprocessing_sha256=pre_sha,
    )
    assert observed["bundle"]["state"] == "available", observed
    bundle_root = target / "calibration-bundle"
    bundle_sha = observed["bundle"]["ref"]["sha256"]
    exports.seal_result(
        cal_root, {"schema": exports.RESULT, "exports": observed}, require_live=runtime.verify, budget=budget
    )
    assert (cal_root / "learning-result.json").is_file()
    doc = frozen.document
    trust = models.ModelTrust(
        bundle_root,
        preprocessing,
        frozen.root,
        bundle_sha,
        pre_sha,
        cal_sha,
        frozen.sha256,
        training.sha256,
        checkpoint,
        method,
        seed,
        doc["protocol"]["sha256"],
        doc["population_sha256"],
        doc["preflight_sha256"],
        plan.context.dependency_lock_sha256,
    )
    return trust, [training.root, cal_root]


def test_actual_frozen_models_load_with_no_role_or_original_job_roots(admitted, monkeypatch):
    root, runtime, plan, readers, proofs = admitted
    osqp, osqp_paths = project(root, plan, runtime, readers, proofs, "learned_osqp", 41001, monkeypatch)
    graph, graph_paths = project(root, plan, runtime, readers, proofs, "learned_daqp", 41002, monkeypatch)
    shadows = [
        plan.context.root,
        plan.train._root,
        plan.validation._root,
        readers["calibration"]._root,
        *osqp_paths,
        *graph_paths,
    ]
    hidden = [path.with_name(path.name + "-removed") for path in shadows]
    for path, renamed in zip(shadows, hidden, strict=True):
        path.rename(renamed)
    original = Path.open
    reads = Counter()

    def observed(path, *args, **kwargs):
        if kwargs.get("mode", args[0] if args else "r") == "rb":
            reads[path] += 1
        return original(path, *args, **kwargs)

    authority = plan.context.authority
    try:
        monkeypatch.setattr(Path, "open", observed)
        for trust in (osqp, graph):
            first = models.read_bundle(trust, authority=authority, allow_fixture=True)
            assert_detached_reload(first, monkeypatch)
            head = first.preprocessing["heads"][0]
            model, normalizer, weights, threshold = first.load_head(head)
            assert model.seed == trust.seed and len(weights) == 64
            assert (normalizer is None) == (trust is graph)
            assert (threshold is not None) == (trust is graph)
            with pytest.raises(c.ContractError):
                models.read_bundle(trust, authority=authority)
            with pytest.raises(c.ContractError):
                models.read_bundle(
                    replace(trust, method="learned_daqp" if trust is osqp else "learned_osqp"),
                    authority=authority,
                    allow_fixture=True,
                )
            with pytest.raises(c.ContractError, match="overlapping"):
                models.read_bundle(
                    replace(trust, preprocessing_root=trust.bundle_root),
                    authority=authority,
                    allow_fixture=True,
                )
            path = trust.preprocessing_root / "preprocessing.json"
            original_prep = path.read_bytes()
            altered = c.strict_loads(original_prep)
            if trust is graph:
                altered["class_statistics"]["positive_prior"] = 0.123
            else:
                altered["normalizers"][0]["scale"][0] += 1
            changed = c.canonical_bytes(altered)
            path.write_bytes(changed)
            try:
                with pytest.raises(c.ContractError, match="normalizer|statistics"):
                    models.read_bundle(
                        replace(trust, preprocessing_sha256=c.digest(changed)),
                        authority=authority,
                        allow_fixture=True,
                    )
            finally:
                path.write_bytes(original_prep)
            if trust is graph:
                path = trust.bundle_root / "bundle.json"
                original_bundle = path.read_bytes()
                altered = c.strict_loads(original_bundle)
                altered["disposition"]["threshold"] = 0.1 if threshold != 0.1 else 0.2
                changed = c.canonical_bytes(altered)
                path.write_bytes(changed)
                try:
                    with pytest.raises(c.ContractError, match="bundle provenance"):
                        models.read_bundle(
                            replace(trust, bundle_sha256=c.digest(changed)),
                            authority=authority,
                            allow_fixture=True,
                        )
                finally:
                    path.write_bytes(original_bundle)
        assert reads
        assert not any(path.is_relative_to(prefix) for path in reads for prefix in shadows + hidden)
        allowed = [
            path
            for trust in (osqp, graph)
            for path in (trust.bundle_root, trust.preprocessing_root, trust.frozen_root)
        ]
        observed_models = [path for path in reads if path.is_relative_to(root)]
        assert observed_models and all(
            any(path.is_relative_to(prefix) for prefix in allowed) for path in observed_models
        )
    finally:
        for path, renamed in zip(shadows, hidden, strict=True):
            renamed.rename(path)


def test_incomplete_roster_and_arbitrary_calibration_mapping_refused(tmp_path):
    with pytest.raises(c.ContractError, match="incomplete"):
        models.publish_roster(tmp_path, (), authority=object())
    with pytest.raises(c.ContractError, match="admitted calibration plan"):
        models.publish_bundle(
            tmp_path,
            preprocessing_root=None,
            calibration_root=None,
            expected_preprocessing="",
            expected_calibration="",
            plan={"state": "calibrated"},
            runtime=None,
        )


def test_complete_failure_roster_binds_independent_evidence_and_order(tmp_path):
    roster = []
    for method, seed in models._KEYS:
        root = tmp_path / f"{method}-{seed}"
        root.mkdir()
        details = dict(
            method=method,
            seed=seed,
            fixture_only=True,
            protocol_sha256="a" * 64,
            population_sha256="b" * 64,
            preflight_sha256="c" * 64,
            state="missing",
            reason="excluded software reason",
            stage="training",
        )
        evidence = c.canonical_bytes(dict(schema=models.ABSENCE, **details))
        (root / "evidence.json").write_bytes(evidence)
        body = c.canonical_bytes(dict(schema=models.FAILURE, **details, evidence_sha256=c.digest(evidence)))
        (root / "failure.json").write_bytes(body)
        roster.append(
            models.FailedModelTrust(root, c.digest(body), method, seed, "a" * 64, "b" * 64, "c" * 64)
        )
    order = tuple(roster)
    digest = models.publish_roster(tmp_path, order, authority=object(), allow_fixture=True)
    assert (
        len(
            models.read_roster(
                tmp_path, order, expected_sha256=digest, authority=object(), allow_fixture=True
            )
        )
        == 6
    )
    with pytest.raises(c.ContractError, match="reordered"):
        models.read_roster(
            tmp_path, order[::-1], expected_sha256=digest, authority=object(), allow_fixture=True
        )
    (order[0].root / "evidence.json").write_bytes(b"{}\n")
    with pytest.raises(c.ContractError, match="stored bytes"):
        models.read_roster(tmp_path, order, expected_sha256=digest, authority=object(), allow_fixture=True)


def test_registered_policy_v2_requires_independent_preprocessing(tmp_path, monkeypatch):
    platform = runpy.run_path(
        str(
            Path(__file__).parents[1] / "environments" / "method-extension-scientific" / "learning_runtime.py"
        )
    )
    raw = t.registered_learning_request("calibrate-model", "learned_osqp", 41001)
    policy = {
        "schema": "softqp.r4.learning-policy/1",
        "operation": "calibrate-model",
        "request_sha256": c.digest(raw),
        "profile_sha256": "b" * 64,
        "admission": {},
        "scope": {
            "roles": {"calibration": {}},
            "resume": None,
            "preflight": {},
            "frozen": {},
            "committed_artifact_receipt": {},
        },
        "output_root": str(tmp_path),
        "artifact_roots": [],
    }
    guardian = ModuleType("softqp_runtime_custody")
    guardian.read_active_learning_policy = lambda *_args, **_kwargs: c.canonical_bytes(policy)
    monkeypatch.setitem(sys.modules, guardian.__name__, guardian)
    with pytest.raises(c.ContractError, match="policy identity"):
        t.dispatch_registered_learning(raw, object())
    assert list(tmp_path.iterdir()) == []
    policy["schema"] = "softqp.r4.learning-policy/2"
    with pytest.raises(ValueError, match="scope differs"):
        platform["learning_scope"]((raw, c.canonical_bytes(policy)), "b" * 64)
    policy["scope"]["preprocessing"] = {"root": str(tmp_path), "sha256": "a" * 64}
    _, _, leaf = platform["learning_scope"]((raw, c.canonical_bytes(policy)), "b" * 64)
    assert leaf == tmp_path / "calibration-learned_osqp-41001" / "worker"


def test_stale_custody_leaves_result_unsealed(tmp_path):
    budget = t.LearningBudget((tmp_path,), tmp_path / "job")
    (tmp_path / "job").mkdir()

    def stale():
        raise c.ContractError("lost custody")

    with pytest.raises(c.ContractError, match="lost custody"):
        exports.seal_result(tmp_path / "job", {"schema": exports.RESULT}, require_live=stale, budget=budget)
    assert not (tmp_path / "job" / "learning-result.json").exists()


@pytest.mark.parametrize(
    "failure", ["post-guard", "post-budget", "replacement", "preexisting", "reread", "collision"]
)
def test_failed_result_seal_rolls_back_only_owned_marker(tmp_path, monkeypatch, failure):
    job = tmp_path / "job"
    budget = t.LearningBudget((tmp_path,), job)
    job.mkdir()
    marker = job / "learning-result.json"
    foreign = b"foreign fixture marker\n"
    result = {"schema": exports.RESULT}
    original_check = budget.check

    def live():
        if marker.is_file() and failure in ("post-guard", "replacement"):
            if failure == "replacement":
                marker.rename(job / "moved.json")
                marker.write_bytes(foreign)
            raise c.ContractError("post-publication custody failed")

    def check(extra_bytes=0):
        if marker.is_file() and failure == "post-budget":
            raise c.ContractError("post-publication budget failed")
        return original_check(extra_bytes=extra_bytes)

    monkeypatch.setattr(budget, "check", check)
    if failure == "preexisting":
        marker.write_bytes(foreign)
    if failure == "collision":
        original_rename = Path.rename

        def collide(source, destination):
            if destination == marker:
                marker.write_bytes(foreign)
            return original_rename(source, destination)

        monkeypatch.setattr(Path, "rename", collide)
    if failure == "reread":

        def reject(*args):
            raise c.ContractError("post-publication reread failed")

        monkeypatch.setattr(models, "_document", reject)
    expected = FileExistsError if failure == "collision" else c.ContractError
    with pytest.raises(expected):
        exports.seal_result(job, result, require_live=live, budget=budget)
    if failure in ("replacement", "preexisting", "collision"):
        assert marker.read_bytes() == foreign
    else:
        assert not marker.exists()
    assert not marker.with_suffix(".json.pending").exists()
    if failure == "replacement":
        assert (job / "moved.json").read_bytes() == c.canonical_bytes(result)


def test_missing_selected_head_does_not_publish(tmp_path):
    raw = c.canonical_bytes({"state": "failed", "checkpoints": {}})
    run = t.TrainingRun(tmp_path, raw, c.digest(raw))
    result = exports.export_training(
        tmp_path, "job", run, plan=None, runtime=None, budget=None, require_live=None
    )
    assert set(result) == {"frozen", "preprocessing"}
    assert all(row["state"] == "unavailable" and row["ref"] is None for row in result.values())
    assert list(tmp_path.iterdir()) == []
