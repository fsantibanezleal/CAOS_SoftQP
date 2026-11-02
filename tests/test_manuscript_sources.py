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


def compiler_module():
    spec = importlib.util.spec_from_file_location(
        "tested_manuscript_driver", ROOT / "scripts/build_manuscript.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expanded(manuscript):
    inventory = compiler_module().source_inventory(manuscript / "main.tex")
    return "\n".join((manuscript / p).read_text(encoding="utf-8") for p in inventory if p.endswith(".tex"))


def test_adversarial_manuscript_requires_native_article_source(manuscript):
    text = source(manuscript)
    assert re.search(r"\\documentclass(?:\[[^]]*\])?\{article\}", text)
    assert not re.search(r"\\chapter\b|\[chapter\]", expanded(manuscript))
    expected = "Preprint" if manuscript.name == "coupled-peak-study" else "Technical report"
    assert "\\newcommand{\\doctype}{" + expected + "}" in text
    assert not (HERE / "build-coupled-report.py").exists()
    assert "\\begin{document}" in text and "\\end{document}" in text


def test_adversarial_manuscript_requires_standard_front_matter(manuscript):
    text = expanded(manuscript)
    for name in ("doctype", "docversion", "docdate", "versiondoi", "conceptdoi", "headerblock"):
        assert "\\newcommand{\\" + name + "}" in text
    body = source(manuscript).split(r"\begin{document}", 1)[1]
    assert body.index(r"\maketitle") < body.index(r"\headerblock") < body.index(r"\begin{abstract}")
    assert "always latest" in text and "Not peer reviewed" in text
    assert r"\fbox{\parbox{0.94\textwidth}" in text


def test_adversarial_manuscript_requires_author_and_running_identity(manuscript):
    text = expanded(manuscript)
    assert r"\usepackage{orcidlink}" in text
    assert r"\orcidlink{0000-0002-0150-3246}" in text
    assert "CAOS Research program" in text and "CAOS Research programme" in text
    assert r"\usepackage{fancyhdr}" in text and r"\fancyhead[L]" in text
    assert r"\fancyhead[R]" in text and r"\pagestyle{fancy}" in text
    assert "linknavy" in text and "colorlinks=true" in text


def test_adversarial_manuscript_refuses_raster_equations(manuscript):
    text = expanded(manuscript)
    assert len(re.findall(r"\\begin\{(?:equation|align)\*?\}", text)) >= 10
    if manuscript.name == "coupled-peak-study":
        assert text.count(r"\begin{proof}") >= 2
    figures = re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", text)
    manifest = json.loads((manuscript / "generated/asset-manifest.json").read_text())
    assert set(figures) == {f["file"] for f in manifest["figures"]}
    assert len(figures) >= (6 if manuscript.name == "coupled-peak-study" else 10)
    from pypdf import PdfReader

    for name in figures:
        assert name.endswith(".pdf")
        assert all(not list(page.images) for page in PdfReader(manuscript / name).pages)


def test_adversarial_manuscript_results_match_accepted_evidence(manuscript):
    text = source(manuscript)
    assert r"\input{results.tex}" in text
    summary = json.loads((HERE / "results/summary/summary.json").read_text())
    primary = summary["primary"]
    results = (manuscript / "results.tex").read_text(encoding="utf-8")
    quantities = {
        "PrimaryEstimate": f"{100 * primary['estimate']:.6f}",
        "PrimaryLower": f"{100 * primary['confidence_interval'][0]:.6f}",
        "PrimaryUpper": f"{100 * primary['confidence_interval'][1]:.6f}",
        "PrimaryFailed": str(primary["failed_pairs"]),
        "PrimaryPopulation": str(primary["denominator"]),
    }
    quantities["SummaryDigest"] = hashlib.sha256(
        (HERE / "results/summary/summary.json").read_bytes()
    ).hexdigest()
    states = {
        "Accepted": "accepted",
        "AccuracyRejected": "accuracy-rejected",
        "Incompatible": "incompatible",
        "OracleFailed": "oracle-failed",
        "Timeout": "timeout",
    }
    for split, counts in summary["counts"].items():
        for macro, state in states.items():
            quantities[split.capitalize() + macro] = str(counts.get(state, 0))
    for name, value in quantities.items():
        assert "\\newcommand{\\" + name + "}{" + value + "}" in results
    assert primary["established"] is False


@pytest.mark.parametrize(
    "problem",
    [
        None,
        "exit",
        "missing-pdf",
        r"Overfull \hbox (1pt too wide)",
        r"Underfull \vbox (badness 10000)",
        "There were undefined references",
        "Citation `missing' on page 1 undefined",
        "Reference `missing' undefined",
        "LaTeX Font Warning: Missing font",
        "Package example Warning: Bad output",
        "Missing character: There is no glyph in font example!",
    ],
)
def test_adversarial_manuscript_build_uses_latex(tmp_path, problem):
    spec = importlib.util.spec_from_file_location(
        "manuscript_compiler_test", ROOT / "scripts/build_manuscript.py"
    )
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


@pytest.mark.parametrize(
    "mutation",
    [
        "empty-manifest",
        "partial-manifest",
        "positive-outcome",
        "forged-evidence",
        "forged-figure-review",
        "changed-figure",
    ],
)
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
        document["primary"].update(estimate=0.99, established=True, denominator=1, failed_pairs=0)
        path.write_text(json.dumps(document))
        manifest["summary.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif mutation in ("forged-evidence", "forged-figure-review"):
        path = (
            tmp_path
            / "results/reviews"
            / (
                "figure-review.json"
                if mutation == "forged-figure-review"
                else "final-campaign-evidence-review.json"
            )
        )
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


@pytest.mark.parametrize("changed_file", ["main.tex", "nested.tex", "refs.bib", "plot.pdf", "coverage.json"])
def test_adversarial_manuscript_source_change_during_build_is_refused(tmp_path, monkeypatch, changed_file):
    spec = importlib.util.spec_from_file_location(
        "source_bound_compiler", ROOT / "scripts/build_manuscript.py"
    )
    compiler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compiler)
    source_file = tmp_path / "main.tex"
    source_file.write_text(
        r"\documentclass{article}\begin{document}\input{nested}\includegraphics{plot}\bibliography{refs}\end{document}"
    )
    for name in ["nested.tex", "refs.bib", "plot.pdf", "coverage.json"]:
        (tmp_path / name).write_text("Original.")

    def changed(source_path, output):
        output.mkdir()
        pdf = output / "main.pdf"
        pdf.write_bytes(b"%PDF-1.7\n%%EOF")
        (tmp_path / changed_file).write_text("Changed after compilation.")
        return pdf

    monkeypatch.setattr(compiler, "compile_document", changed)
    with pytest.raises(RuntimeError, match="changed during compilation"):
        compiler.build(source_file, tmp_path / "compiled")


def test_adversarial_manuscripts_meet_current_content_bar(manuscript):
    compiler_module().require_content(manuscript / "main.tex")
    compiler_module().require_evidence(manuscript / "main.tex")


@pytest.mark.parametrize("path", ["../outside.tex", "missing.tex"])
def test_adversarial_nested_input_is_refused(tmp_path, path):
    (tmp_path.parent / "outside.tex").write_text("outside")
    source_file = tmp_path / "main.tex"
    source_file.write_text("\\input{" + path + "}")
    with pytest.raises(ValueError):
        compiler_module().source_inventory(source_file)


@pytest.mark.parametrize("group", ["methods", "contracts", "claims"])
def test_adversarial_coverage_cannot_alias_requirements(tmp_path, monkeypatch, group):
    slug = "coupled-peak-study" if group == "claims" else "soft-constraint-study"
    shutil.copytree(ROOT / "manuscripts" / slug, tmp_path / "manuscripts" / slug)
    for name in [
        "docs/design/SDD.md",
        "docs/contracts/catalog.md",
        "product.json",
        "scripts/manuscript_content_bar.py",
    ]:
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    cov_path = tmp_path / "manuscripts" / slug / "coverage.json"
    cov = json.loads(cov_path.read_text())
    first = next(iter(cov[group].values()))
    cov[group] = {key: first for key in cov[group]}
    cov_path.write_text(json.dumps(cov))
    compiler = compiler_module()
    # require_content resolves its repo from this driver path, as in a real checkout.
    monkeypatch.setattr(compiler, "__file__", str(tmp_path / "scripts/build_manuscript.py"))
    with pytest.raises(ValueError, match="alias"):
        compiler.require_content(tmp_path / "manuscripts" / slug / "main.tex")


@pytest.mark.parametrize(
    "mutation", ["positive-macro", "changed-population", "changed-estimate", "rehashed-manifest"]
)
def test_adversarial_original_study_tampering_is_refused(tmp_path, monkeypatch, mutation):
    compiler = compiler_module()
    path = "data/derived/experiments/campaign.json"
    campaign = tmp_path / path
    campaign.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / path, campaign)
    folder = tmp_path / "manuscripts/soft-constraint-study"
    folder.mkdir(parents=True)
    shutil.copyfile(
        ROOT / "manuscripts/soft-constraint-study/original-results.tex", folder / "original-results.tex"
    )
    canonical = subprocess.check_output(["git", "show", compiler.FROZEN_SOURCE + ":" + path], cwd=ROOT)
    monkeypatch.setattr(compiler, "ROOT", tmp_path)
    monkeypatch.setattr(compiler.subprocess, "check_output", lambda *a, **k: canonical)
    if mutation == "positive-macro":
        (folder / "original-results.tex").write_text("\\newcommand{\\OriginalEstimate}{99}")
    else:
        doc = json.loads(campaign.read_text())
        if mutation == "changed-population":
            doc["primary_endpoint"]["paired_samples"] = 1
        else:
            doc["primary_endpoint"]["median_relative_reduction"] = 0.99
        campaign.write_text(json.dumps(doc))
        if mutation == "rehashed-manifest":
            (tmp_path / "SHA256SUMS.json").write_text(
                json.dumps({path: hashlib.sha256(campaign.read_bytes()).hexdigest()})
            )
    with pytest.raises(ValueError, match="Original"):
        compiler.require_evidence(folder / "main.tex")


def test_nested_contracts_retain_conditional_consumer_semantics():
    folder = ROOT / "manuscripts/soft-constraint-study/generated"
    rows = json.loads((folder / "contract-readiness.json").read_text())["nested_fields"]
    assert any("(if)" in row[0] for row in rows)
    assert any("(then)" in row[0] and "provenance" in row[0] for row in rows)
    for path in folder.glob("contract-*.json"):
        for field, kind, constraint, unit in json.loads(path.read_text())["nested_fields"]:
            if kind in {"number", "integer"}:
                assert unit != "structural metadata / nested units", (path.name, field)


@pytest.mark.parametrize("mutation", [None, "erase-both-input-maps", "erase-figures"])
def test_adversarial_frozen_asset_inventory_cannot_be_erased(tmp_path, monkeypatch, mutation):
    compiler = compiler_module()
    slug = "soft-constraint-study"
    folder = tmp_path / "manuscripts" / slug
    source_folder = ROOT / "manuscripts" / slug
    paths = set(json.loads((ROOT / "manuscripts/shared/evidence-inputs.json").read_text())["inputs"])
    paths.update(
        "manuscripts/" + slug + "/" + p for p in compiler.source_inventory(source_folder / "main.tex")
    )
    paths.update(
        {
            "manuscripts/shared/evidence-inputs.json",
            "manuscripts/coupled-peak-study/build.py",
            "manuscripts/coupled-peak-study/results/reviews/final-campaign-evidence-review.json",
            "manuscripts/coupled-peak-study/results/reviews/figure-review.json",
        }
    )
    paths.update(p.relative_to(ROOT).as_posix() for p in (HERE / "results/summary").iterdir() if p.is_file())
    for name in paths:
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    original_call = subprocess.check_output
    monkeypatch.setattr(compiler, "ROOT", tmp_path)
    monkeypatch.setattr(
        compiler.subprocess, "check_output", lambda command, **kwargs: original_call(command, cwd=ROOT)
    )
    manifest_path = folder / "generated/asset-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if mutation == "erase-both-input-maps":
        manifest["source_inputs"] = {}
        evidence_path = tmp_path / "manuscripts/shared/evidence-inputs.json"
        evidence = json.loads(evidence_path.read_text())
        evidence["inputs"] = {}
        evidence_path.write_text(json.dumps(evidence))
    elif mutation == "erase-figures":
        manifest["figures"] = []
    manifest_path.write_text(json.dumps(manifest))
    if mutation is None:
        compiler.require_evidence(folder / "main.tex")
    else:
        with pytest.raises(ValueError, match="inventory"):
            compiler.require_evidence(folder / "main.tex")


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "missing",
        "forged",
        "transplanted",
        "changed-pdf",
        "changed-source",
        "wrong-type",
        "unreviewed-page",
        "no-final-doi",
    ],
)
def test_adversarial_publication_requires_independent_acceptance(tmp_path, mutation):
    driver = compiler_module()
    spec = importlib.util.spec_from_file_location(
        "tested_publication_guard", ROOT / "scripts/publication_acceptance.py"
    )
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    source_file = tmp_path / "main.tex"
    source_file.write_text(
        r"\documentclass{article}\title{Scientific result}\newcommand{\doctype}{Preprint}\newcommand{\docversion}{v1.0.0}\newcommand{\conceptdoi}{10.5281/zenodo.123}\newcommand{\versiondoi}{10.5281/zenodo.123}"
    )
    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfixture independently reviewed bytes\n%%EOF")
    inventory = driver.source_inventory(source_file)
    receipt = {
        "inputs_sha256": inventory,
        "policy_inputs_sha256": {},
        "compiler_driver_sha256": guard.sha256(ROOT / "scripts/build_manuscript.py"),
        "sha256": guard.sha256(pdf),
        "warnings": 0,
        "overfull": 0,
        "underfull": 0,
    }
    receipt_path = pdf.with_suffix(".build.json")
    receipt_path.write_text(json.dumps(receipt))
    doc = {
        "slug": tmp_path.name,
        "pdf_sha256": guard.sha256(pdf),
        "build_receipt_sha256": guard.sha256(receipt_path),
        "inputs_sha256": inventory,
        "content_accepted": True,
        "mathematics_accepted": True,
        "all_pages_accepted": True,
        "doctype": "Preprint",
        "version": "v1.0.0",
        "concept_doi": "10.5281/zenodo.123",
        "version_doi": "10.5281/zenodo.123",
        "title": "Scientific result",
        "resource_type": "publication-preprint",
    }
    report = {
        "decision": "ACCEPT_MANUSCRIPTS",
        "phase": "before-reservation",
        "reviewer": "/root/notebook_review",
        "author": "/root",
        "unresolved_findings": [],
        "documents": [doc],
    }
    review = tmp_path / "review.json"
    review.write_text(json.dumps(report))
    anchor = guard.sha256(review)
    if mutation == "missing":
        anchor = "0" * 64
    elif mutation == "forged":
        report["decision"] = "FORGED_ACCEPTANCE"
        review.write_text(json.dumps(report))
    elif mutation == "transplanted":
        doc["slug"] = "another-study"
    elif mutation == "changed-pdf":
        pdf.write_bytes(b"changed")
    elif mutation == "changed-source":
        source_file.write_text(source_file.read_text() + "\nChanged source.")
    elif mutation == "wrong-type":
        doc["resource_type"] = "publication-report"
    elif mutation == "unreviewed-page":
        doc["all_pages_accepted"] = False
    elif mutation == "no-final-doi":
        report["phase"] = "before-publication"
    if mutation not in {None, "missing", "forged", "changed-pdf", "changed-source"}:
        review.write_text(json.dumps(report))
        anchor = guard.sha256(review)
    kwargs = dict(trusted_digest=anchor, phase=report["phase"])
    if mutation is None:
        assert guard.require_acceptance(source_file, pdf, review, **kwargs)["slug"] == tmp_path.name
    else:
        with pytest.raises(ValueError):
            guard.require_acceptance(source_file, pdf, review, **kwargs)
