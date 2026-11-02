"""Manuscript acceptance boundaries that the rejected PDF workflow bypassed."""

import json
import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "manuscripts/coupled-peak-study"


@pytest.fixture(params=["coupled-peak-study", "soft-constraint-study"])
def manuscript(request):
    return ROOT / "manuscripts" / request.param


def source(manuscript=HERE):
    path = manuscript / "main.tex"
    assert path.is_file(), "The scientific manuscript requires editable main.tex."
    return path.read_text(encoding="utf-8")


def test_adversarial_manuscript_requires_native_report_source(manuscript):
    text = source(manuscript)
    assert re.search(r"\\documentclass(?:\[[^]]*\])?\{report\}", text)
    assert not (HERE / "build-coupled-report.py").exists()
    assert "\\begin{document}" in text and "\\end{document}" in text


def test_adversarial_manuscript_requires_standard_front_matter(manuscript):
    text = source(manuscript)
    for name in ("doctype", "docversion", "docdate", "versiondoi", "conceptdoi", "headerblock"):
        assert "\\newcommand{\\" + name + "}" in text
    body = text.split(r"\begin{document}", 1)[1]
    assert body.index(r"\maketitle") < body.index(r"\headerblock") < body.index(r"\begin{abstract}")
    assert "always latest" in text and "Not peer reviewed" in text
    assert r"\fbox{\parbox{0.94\textwidth}" in text


def test_adversarial_manuscript_requires_author_and_running_identity(manuscript):
    text = source(manuscript)
    assert r"\usepackage{orcidlink}" in text
    assert r"\orcidlink{0000-0002-0150-3246}" in text
    assert "CAOS open-research programme, Santiago, Chile" in text
    assert r"\usepackage{fancyhdr}" in text and r"\fancyhead[L]" in text
    assert r"\fancyhead[R]" in text and r"\pagestyle{fancy}" in text
    assert "linknavy" in text and "colorlinks=true" in text


def test_adversarial_manuscript_refuses_raster_equations(manuscript):
    text = source(manuscript)
    assert len(re.findall(r"\\begin\{(?:equation|align)\*?\}", text)) >= 10
    if manuscript.name == "coupled-peak-study":
        assert text.count(r"\begin{proof}") >= 2
    figures = re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", text)
    expected = ({"results/summary/primary-full-population.png", "results/summary/observation-states.png"}
                if manuscript.name == "coupled-peak-study" else
                {"figures/primary-effect.pdf", "figures/cold-times.pdf", "figures/conditioning.pdf",
                 "figures/control-stream.pdf", "figures/energy-policies.pdf"})
    assert set(figures) == expected and len(figures) == len(expected)


def test_adversarial_manuscript_results_match_accepted_evidence(manuscript):
    text = source(manuscript)
    assert r"\input{results.tex}" in text
    summary = json.loads((HERE / "results/summary/summary.json").read_text())
    primary = summary["primary"]
    results = (manuscript / "results.tex").read_text(encoding="utf-8")
    quantities = {"PrimaryEstimate": f'{100 * primary["estimate"]:.6f}',
                  "PrimaryLower": f'{100 * primary["confidence_interval"][0]:.6f}',
                  "PrimaryUpper": f'{100 * primary["confidence_interval"][1]:.6f}',
                  "PrimaryFailed": str(primary["failed_pairs"]),
                  "PrimaryPopulation": str(primary["denominator"])}
    quantities["SummaryDigest"] = hashlib.sha256((HERE / "results/summary/summary.json").read_bytes()).hexdigest()
    states = {"Accepted": "accepted", "AccuracyRejected": "accuracy-rejected",
              "Incompatible": "incompatible", "OracleFailed": "oracle-failed", "Timeout": "timeout"}
    for split, counts in summary["counts"].items():
        for macro, state in states.items():
            quantities[split.capitalize() + macro] = str(counts.get(state, 0))
    for name, value in quantities.items():
        assert "\\newcommand{\\" + name + "}{" + value + "}" in results
    assert primary["established"] is False


@pytest.mark.parametrize("problem", [None, "exit", "missing-pdf", r"Overfull \hbox (1pt too wide)",
                                   r"Underfull \vbox (badness 10000)", "There were undefined references",
                                   "Citation `missing' on page 1 undefined", "Reference `missing' undefined",
                                   "LaTeX Font Warning: Missing font", "Package example Warning: Bad output",
                                   "Missing character: There is no glyph in font example!"])
def test_adversarial_manuscript_build_uses_latex(tmp_path, problem):
    spec = importlib.util.spec_from_file_location("manuscript_compiler_test", ROOT / "scripts/build_manuscript.py")
    compiler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compiler)
    tex = tmp_path / "main.tex"
    tex.write_text(r"\documentclass{report}\begin{document}Native text.\end{document}")
    output = tmp_path / "compiled"
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        assert command[0] == "pdflatex" and "-halt-on-error" in command
        assert kwargs["cwd"] == tmp_path and kwargs["timeout"] == 120
        (output / "main.log").write_text(problem if problem else "Clean native output.")
        if problem != "missing-pdf":
            (output / "main.pdf").write_bytes(b"%PDF-1.7\n%%EOF")
        return subprocess.CompletedProcess(command, 1 if problem == "exit" else 0, b"", b"")

    if problem is None:
        assert compiler.compile_document(tex, output, compiler="pdflatex", runner=runner).is_file()
        assert len(calls) == 3
    else:
        with pytest.raises(RuntimeError):
            compiler.compile_document(tex, output, compiler="pdflatex", runner=runner)


@pytest.mark.parametrize("mutation", ["empty-manifest", "partial-manifest", "positive-outcome",
                                    "forged-evidence", "forged-figure-review", "changed-figure"])
def test_adversarial_manuscript_refuses_forged_acceptance(tmp_path, monkeypatch, mutation):
    spec = importlib.util.spec_from_file_location("study_build_test", HERE / "build.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    shutil.copytree(HERE / "results/summary", tmp_path / "results/summary")
    (tmp_path / "results/reviews").mkdir()
    for name in ("figure-review.json", "final-campaign-evidence-review.json"):
        shutil.copyfile(HERE / "results/reviews" / name, tmp_path / "results/reviews" / name)
    monkeypatch.setattr(builder, "HERE", tmp_path)
    assert builder.result_macros() == (HERE / "results.tex").read_text(encoding="utf-8")
    folder = tmp_path / "results/summary"
    manifest_path = folder / "SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text())
    if mutation == "empty-manifest":
        manifest = {}
    elif mutation == "partial-manifest":
        manifest.pop("observation-states.svg")
    elif mutation == "positive-outcome":
        path = folder / "summary.json"
        document = json.loads(path.read_text())
        document["primary"].update(estimate=.99, established=True, denominator=1, failed_pairs=0)
        path.write_text(json.dumps(document))
        manifest["summary.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif mutation in ("forged-evidence", "forged-figure-review"):
        path = tmp_path / "results/reviews" / (
            "figure-review.json" if mutation == "forged-figure-review" else "final-campaign-evidence-review.json")
        document = json.loads(path.read_text())
        document["decision"] = "FORGED_ACCEPTANCE"
        path.write_text(json.dumps(document))
    else:
        path = folder / "observation-states.png"
        path.write_bytes(b"forged figure")
        manifest[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        builder.result_macros()


def test_adversarial_manuscript_source_change_during_build_is_refused(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("source_bound_compiler", ROOT / "scripts/build_manuscript.py")
    compiler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compiler)
    source_file = tmp_path / "main.tex"
    source_file.write_text(r"\documentclass{report}\begin{document}Original.\end{document}")

    def changed(source_path, output):
        output.mkdir()
        pdf = output / "main.pdf"
        pdf.write_bytes(b"%PDF-1.7\n%%EOF")
        source_path.write_text("Changed source after compilation.")
        return pdf

    monkeypatch.setattr(compiler, "compile_document", changed)
    with pytest.raises(RuntimeError, match="changed during compilation"):
        compiler.build(source_file, tmp_path / "compiled")
