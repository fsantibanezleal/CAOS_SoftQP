"""Domain adapter for the released local workflow; historical timings are never rerun."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline"))


def validate(target):
    from pipeline.experiment_export import verify_campaign
    from pipeline.softqp_run import CANONICAL_MATRIX_METHODS, verify_inventory

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
        document = json.loads((derived / "softqp" / row["path"]).read_text(encoding="utf-8"))
        runs = document["runs"]
        methods = [run["method"] for run in runs]
        if len(methods) != len(CANONICAL_MATRIX_METHODS) or set(methods) != set(CANONICAL_MATRIX_METHODS):
            raise ValueError("A complete authored case requires every canonical matrix method exactly once.")
        failed = any(run["state"] == "failed" for run in runs)
        if row["failed"] != failed or failed:
            raise ValueError("A complete local replay cannot contain failed cells or inconsistent failure flags.")
        for run in runs:
            result = run["result"]
            if run["state"] == "incompatible":
                if result is not None or not run["reason"]:
                    raise ValueError("An incompatible method requires its reason and no returned result.")
            elif (result is None or result["method"] != run["method"] or run["reason"] is not None
                  or result["status_code"] not in ({1, 2} if run["method"] == "daqp" else {1})
                  or not result["x"]):
                raise ValueError("An available method requires a consistent successful backend result.")
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
