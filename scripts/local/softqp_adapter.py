"""Domain adapter for the released local workflow; historical timings are never rerun."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline"))


def compatible(case, method):
    """Declared canonical adapter domain; inspect original inputs without solving."""
    import numpy as np

    if case.reference is not None:
        return method in {"lifted", "generalized"}
    problem, penalty = case.problem, case.problem.penalty
    if method == "generalized":
        return (np.array_equal(penalty.lower_linear, penalty.upper_linear)
                and np.array_equal(penalty.lower_quadratic, penalty.upper_quadratic))
    if method == "daqp":
        if problem.q.size > 2048 or problem.lower.size > 8192:
            return False
        if (np.any(penalty.soft & np.isfinite(problem.lower) & (penalty.lower_quadratic <= 0))
                or np.any(penalty.soft & np.isfinite(problem.upper) & (penalty.upper_quadratic <= 0))):
            return False
        try:
            np.linalg.cholesky(problem.P.toarray())
        except np.linalg.LinAlgError:
            return False
    return True


def validate(target):
    import numpy as np
    from pipeline.experiment_export import verify_campaign
    from pipeline.core.expect import check_document
    from pipeline.softqp_cases import cases
    from pipeline.softqp_rows import rows_for
    from pipeline.softqp_requests import encode_problem
    from pipeline.softqp_run import CANONICAL_MATRIX_METHODS, SETTINGS, reference_cost, verify_inventory

    authored = {case.id: case for case in cases()}
    baseline = json.loads((ROOT / "data-pipeline/validated-objectives.json").read_text(encoding="utf-8"))
    if baseline.get("schema") != "softqp.validated-objectives/v1" or set(baseline["cases"]) != set(authored):
        raise ValueError("The source-bound reviewed objective inventory must cover every authored case.")
    for value in baseline["cases"].values():
        objective = value["objective"]
        if isinstance(objective, bool) or not isinstance(objective, (int, float)) or not math.isfinite(objective):
            raise ValueError("The reviewed objective inventory must contain finite numerical references.")
    target = Path(target).resolve()
    derived = target / "data/derived"
    index = json.loads((derived / "softqp/index.json").read_text(encoding="utf-8"))
    identifiers = [row["case_id"] for row in index["cases"]]
    # This is the declared fifteen-case artifact inventory, not a generator call.
    expected = {f"C{number:02d}" for number in range(1, 16)}
    if set(identifiers) != expected or len(identifiers) != len(expected):
        raise ValueError("A complete SoftQP stage requires every declared case exactly once.")
    verify_inventory(derived / "softqp", index)
    for row in index["cases"]:
        case = authored[row["case_id"]]
        document = json.loads((derived / "softqp" / row["path"]).read_text(encoding="utf-8"))
        expected_problem = None if case.problem is None else encode_problem(case.problem)
        if document.get("problem") != expected_problem or document["settings"] != SETTINGS:
            raise ValueError("Exported problem and settings must match the authored source inputs.")
        if document["rows"] != rows_for(case):
            raise ValueError("Row units and hard/soft policy must match the authored original-space case.")
        runs = document["runs"]
        methods = [run["method"] for run in runs]
        if len(methods) != len(CANONICAL_MATRIX_METHODS) or set(methods) != set(CANONICAL_MATRIX_METHODS):
            raise ValueError("A complete authored case requires every canonical matrix method exactly once.")
        failed = any(run["state"] == "failed" for run in runs)
        if row["failed"] != failed or failed:
            raise ValueError("A complete local replay cannot contain failed cells or inconsistent failure flags.")
        calculated = {}
        for run in runs:
            result = run["result"]
            if (run["state"] == "available") != compatible(case, run["method"]):
                raise ValueError("Method compatibility must follow the authored inputs, not an invented result label.")
            if run["state"] == "incompatible":
                if result is not None or not run["reason"]:
                    raise ValueError("An incompatible method requires its reason and no returned result.")
            elif (result is None or result["method"] != run["method"] or run["reason"] is not None
                  or result["status_code"] not in ({1, 2} if run["method"] == "daqp" else {1})
                  or not result["x"]):
                raise ValueError("An available method requires a consistent successful backend result.")
            else:
                metrics = result["metrics"]
                if metrics is None:
                    raise ValueError("An available method requires complete scientific metrics.")
                x = np.asarray(result["x"])
                n = case.problem.q.size if case.problem is not None else case.reference[1].size
                if x.shape != (n,):
                    raise ValueError("Decision vector dimension differs from the authored original problem.")
                expected_metrics = (case.problem.evaluate(x) if case.problem is not None
                                    else reference_cost(case.reference, x))
                calculated[run["method"]] = expected_metrics
                for name, expected_value in expected_metrics.items():
                    value = metrics[name]
                    if (np.shape(value) != np.shape(expected_value)
                            or not np.allclose(value, expected_value, rtol=SETTINGS["eps_rel"], atol=SETTINGS["eps_abs"])):
                        raise ValueError("Scientific metrics do not match the original-space decision vector.")
        lifted = calculated["lifted"]["objective"]
        paired, referenced = copy.deepcopy(document), copy.deepcopy(document)
        for run, paired_run, reference_run in zip(runs, paired["runs"], referenced["runs"]):
            if run["state"] != "available":
                continue
            metrics = run["result"]["metrics"]
            authoritative = calculated[run["method"]]
            gap = abs(authoritative["objective"] - lifted)
            declared_gap = metrics["objective_gap_against_lifted"]
            if declared_gap is None or not np.isclose(declared_gap, gap, rtol=SETTINGS["eps_rel"], atol=SETTINGS["eps_abs"]):
                raise ValueError("Reported objective gap must match the independently recomputed lifted comparison.")
            paired_run["result"]["metrics"].update(authoritative, objective_gap_against_lifted=gap)
            reference_run["result"]["metrics"].update(authoritative)
            reference_run["result"]["metrics"]["objective_gap_against_lifted"] = abs(
                authoritative["objective"] - baseline["cases"][case.id]["objective"])
        # Reuse the original published hard/gap bands. These local copies do not
        # rewrite a candidate or change either registered experiment's criterion.
        check_document(paired)
        check_document(referenced)
    verify_campaign(derived / "experiments")
    configuration = json.loads((ROOT / "scripts/local/workflow.json").read_text(encoding="utf-8"))
    for name in configuration["stage_inputs"]:
        source, staged = ROOT / name, target / name
        if not staged.is_file() or hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(staged.read_bytes()).digest():
            raise ValueError("Frozen historical evidence differs from its declared source input.")


def generate(target):
    from pipeline.pipeline import run_all

    target = Path(target).resolve()
    if target.is_relative_to(ROOT) or not (target / "data/derived").is_dir():
        raise ValueError("SoftQP generation requires the workflow's external prepared stage.")
    # The released workflow has already copied byte-bound historical stage_inputs.
    # Only the authored case matrix is solved; no registered timing study is executed.
    run_all(output_root=target / "data/derived")
    validate(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["generate", "validate"])
    parser.add_argument("stage", type=Path)
    args = parser.parse_args()
    (generate if args.operation == "generate" else validate)(args.stage)


if __name__ == "__main__":
    main()
