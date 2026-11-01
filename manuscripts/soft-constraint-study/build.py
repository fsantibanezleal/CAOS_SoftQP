"""Build the scientific PDF twice and reject clipped lines or unresolved references."""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=ROOT / "output/pdf")
args = parser.parse_args()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=True)
latex = shutil.which("pdflatex")
if latex is None:
    raise RuntimeError("Install a LaTeX distribution with pdflatex before building the scientific report")
command = [latex, "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
           "-jobname=softqp-technical-report", f"-output-directory={output}", "main.tex"]
for _ in range(2):
    run = subprocess.run(command, cwd=HERE, capture_output=True, timeout=120)
    (output / "build.stdout.log").write_bytes(run.stdout + run.stderr)
    if run.returncode:
        raise RuntimeError(f"LaTeX build failed; inspect {output / 'build.stdout.log'}")
log = (output / "softqp-technical-report.log").read_text(encoding="utf-8", errors="replace")
if re.search(r"Overfull \\[hv]box|undefined references|Citation .+ undefined", log):
    raise RuntimeError("Report has clipped lines or unresolved references; inspect the final LaTeX log")
print(output / "softqp-technical-report.pdf")
