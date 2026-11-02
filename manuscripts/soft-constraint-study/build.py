"""Compile the native technical-report source with the shared LaTeX driver."""

import argparse
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path)
parser.add_argument("--refresh-results", action="store_true")
args = parser.parse_args()
study_spec = importlib.util.spec_from_file_location(
    "accepted_coupled_results", ROOT / "manuscripts/coupled-peak-study/build.py")
study = importlib.util.module_from_spec(study_spec)
study_spec.loader.exec_module(study)
expected = study.result_macros()
results = HERE / "results.tex"
if args.refresh_results:
    results.write_text(expected, encoding="utf-8", newline="\n")
    print("Accepted coupled-study numeric macros exported; no PDF built.")
    raise SystemExit(0)
if not results.is_file() or results.read_text(encoding="utf-8") != expected:
    raise ValueError("Coupled-study numbers differ from the accepted complete-study evidence.")
spec = importlib.util.spec_from_file_location("manuscript_compiler", ROOT / "scripts/build_manuscript.py")
compiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler)
print(compiler.build(HERE / "main.tex", args.output))
