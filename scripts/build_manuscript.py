"""Compile native manuscript sources and refuse unresolved or clipped typesetting."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def compile_document(source, output, *, compiler=None, runner=subprocess.run):
    source, output = Path(source).resolve(), Path(output).resolve()
    text = source.read_text(encoding="utf-8")
    if not re.search(r"\\documentclass(?:\[[^]]*\])?\{report\}", text):
        raise ValueError("A technical report requires native LaTeX report-class source.")
    compiler = compiler or shutil.which("pdflatex")
    if compiler is None:
        raise RuntimeError("Install a LaTeX distribution providing pdflatex.")
    output.mkdir(parents=True, exist_ok=False)
    command = [str(compiler), "-interaction=nonstopmode", "-halt-on-error",
               "-file-line-error", "-restrict-write18" if os.name == "nt" else "-shell-restricted", "-recorder",
               f"-output-directory={output}", source.name]
    for index in range(3):
        result = runner(command, cwd=source.parent, capture_output=True, timeout=120)
        (output / f"pass-{index + 1}.stdout.log").write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"LaTeX compilation failed on pass {index + 1}; inspect its log.")
    log = (output / f"{source.stem}.log").read_text(encoding="utf-8", errors="replace")
    problems = re.findall(
        r"^.*(?:Overfull \\[hv]box|Underfull \\[hv]box|undefined references|"
        r"(?:Citation|Reference) .+ undefined|multiply-defined labels|"
        r"LaTeX(?: Font)? Warning:|Package .+ Warning:|Missing character:).*$", log, re.MULTILINE)
    if problems:
        raise RuntimeError("Unresolved or clipped LaTeX output:\n" + "\n".join(problems))
    pdf = output / f"{source.stem}.pdf"
    if not pdf.is_file() or not pdf.read_bytes().startswith(b"%PDF-"):
        raise RuntimeError("The compiler did not produce a PDF.")
    return pdf


def build(source, output=None):
    source = Path(source).resolve()
    if output is None:
        scratch = os.environ.get("CAOS_TEMP_ROOT")
        if not scratch:
            raise ValueError("Set an external CAOS_TEMP_ROOT or supply --output explicitly.")
        scratch = Path(scratch).resolve()
        root = Path(__file__).resolve().parents[1]
        if scratch.is_relative_to(root):
            raise ValueError("CAOS_TEMP_ROOT must be outside the repository.")
        scratch.mkdir(parents=True, exist_ok=True)
        # Only allocate the name here; the compiler creates the actual fresh folder.
        output = Path(tempfile.mkdtemp(prefix="softqp-manuscript-", dir=scratch))
        output.rmdir()
    files = [source]
    text = source.read_text(encoding="utf-8")
    for name in re.findall(r"\\(?:input|includegraphics)(?:\[[^]]*\])?\{([^}]+)\}", text):
        path = source.parent / name
        if path.suffix == "":
            path = path.with_suffix(".tex")
        if not path.resolve().is_relative_to(source.parent):
            raise ValueError("Manuscript input escapes its source directory.")
        files.append(path)
    inputs = {path.relative_to(source.parent).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in files}
    driver = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    pdf = compile_document(source, output)
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != inputs[path.relative_to(source.parent).as_posix()]
           for path in files) or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != driver:
        raise RuntimeError("Manuscript source, figure or compiler driver changed during compilation.")
    receipt = {"state": "compiled-awaiting-independent-page-review", "engine": "pdflatex",
               "source_sha256": inputs[source.name], "inputs_sha256": inputs,
               "compiler_driver_sha256": driver,
               "bytes": pdf.stat().st_size, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
               "warnings": 0, "overfull": 0, "underfull": 0}
    pdf.with_suffix(".build.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return pdf


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(build(args.source, args.output))


if __name__ == "__main__":
    main()
