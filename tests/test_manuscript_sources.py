"""Manuscript acceptance boundaries that the rejected PDF workflow bypassed."""

import ast
import json
import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess
import shutil
from types import SimpleNamespace

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


def frozen_catalog():
    """The witness is the immutable Git object, not a mutable current table."""
    return subprocess.check_output([
        "git", "show", "2d3f299d80edad49c2599e61bb6e3c875c119043:docs/contracts/catalog.md"
    ], cwd=ROOT)


def test_reviewed_catalog_corrections_are_admitted(manuscript):
    compiler_module().require_evidence(manuscript / "main.tex")


@pytest.mark.parametrize("mask", range(32))
def test_adversarial_catalog_accepts_only_frozen_or_all_five_corrections(mask):
    compiler = compiler_module()
    original = frozen_catalog()
    current = (ROOT / "docs/contracts/catalog.md").read_bytes().replace(b"\r\n", b"\n")
    old_lines, repaired_lines = original.splitlines(keepends=True), current.splitlines(keepends=True)
    assert len(old_lines) == len(repaired_lines)
    changed = [index for index, (old, new) in enumerate(zip(old_lines, repaired_lines)) if old != new]
    assert len(changed) == 5
    candidate = old_lines.copy()
    for bit, index in enumerate(changed):
        if mask & (1 << bit):
            candidate[index] = repaired_lines[index]
    assert compiler.matches_frozen_input(
        "docs/contracts/catalog.md", original, b"".join(candidate)
    ) is (mask in {0, 31})


@pytest.mark.parametrize("mutation", [
    "state", "condition", "provenance", "surface", "english-reason", "spanish-meaning",
    "contract-version", "history", "schema-path", "arbitrary-prose", "extra-prose", "missing-state-table",
])
def test_adversarial_catalog_rejects_unreviewed_text_and_normative_changes(mutation):
    compiler = compiler_module()
    current = (ROOT / "docs/contracts/catalog.md").read_text(encoding="utf-8")
    replacements = {
        "state": ("| provider | status active |", "| available | status active |"),
        "condition": ("| provider | status active |", "| provider | status real |"),
        "provenance": ("| status active | declared provider kind |", "| status active | real |"),
        "surface": ("Show a visible provider label", "Hide the provider label"),
        "english-reason": ("the producer is incomplete.", "the producer is complete."),
        "spanish-meaning": ("el productor está incompleto.", "el productor está completo."),
        "contract-version": ("| softqp-index | 1.1.0 |", "| softqp-index | 9.0.0 |"),
        "history": ("| softqp-index | 1.0.0 | 2026-10-31 |", "| softqp-index | 1.0.1 | 2026-10-31 |"),
        "schema-path": ("docs/contracts/schemas/softqp-index.schema.json", "docs/contracts/schemas/forged.json"),
        "arbitrary-prose": ("Each schema file is the single source", "Each schema file is an optional source"),
    }
    if mutation == "extra-prose":
        candidate = current + "\nAn unrelated replacement explanation.\n"
    elif mutation == "missing-state-table":
        candidate = "\n".join(line for line in current.splitlines() if not line.startswith("| provider |")) + "\n"
    else:
        old, new = replacements[mutation]
        assert old in current
        candidate = current.replace(old, new)
    assert not compiler.matches_frozen_input("docs/contracts/catalog.md", frozen_catalog(), candidate.encode())


@pytest.mark.parametrize("mutation", ["intro", "missing-reason", "duplicate-reason"])
def test_adversarial_catalog_refuses_a_changed_correction_authority(mutation):
    compiler = compiler_module()
    original = frozen_catalog()
    lines = original.splitlines(keepends=True)
    if mutation == "intro":
        lines[2] = lines[2].replace(b"Phase 2", b"Phase 3")
    else:
        index = next(i for i, line in enumerate(lines) if line.startswith(b"| provider |"))
        if mutation == "missing-reason":
            lines[index] = b"| provider | unrelated replacement |\n"
        else:
            lines.append(lines[index])
    with pytest.raises(ValueError, match="catalog"):
        compiler.matches_frozen_input("docs/contracts/catalog.md", b"".join(lines), b"".join(lines))


def test_reviewed_catalog_correction_preserves_cross_checkout_line_endings():
    compiler = compiler_module()
    original = frozen_catalog()
    current = (ROOT / "docs/contracts/catalog.md").read_bytes().replace(b"\r\n", b"\n")
    assert compiler.matches_frozen_input("docs/contracts/catalog.md", original, current.replace(b"\n", b"\r\n"))
    assert compiler.matches_frozen_input("unrelated-input.json", b"{\n}\n", b"{\r\n}\r\n")
    assert not compiler.matches_frozen_input("unrelated-input.json", b"{\n}\n", b"{\n}\n ")


@pytest.fixture
def copied_frozen_evidence(tmp_path, monkeypatch):
    """Exercise the actual loader against a complete small copy of its input boundary."""
    compiler = compiler_module()
    inputs = json.loads((ROOT / "manuscripts/shared/evidence-inputs.json").read_text(encoding="utf-8"))["inputs"]
    names = set(inputs)
    names.update({
        "manuscripts/shared/evidence-inputs.json", "manuscripts/coupled-peak-study/build.py",
        "scripts/build_manuscript.py",
        "manuscripts/coupled-peak-study/results/reviews/final-campaign-evidence-review.json",
        "manuscripts/coupled-peak-study/results/reviews/figure-review.json",
    })
    names.update(p.relative_to(ROOT).as_posix() for p in (HERE / "results/summary").iterdir() if p.is_file())
    folder = ROOT / "manuscripts/soft-constraint-study"
    names.update(p.relative_to(ROOT).as_posix() for p in (folder / "figures").iterdir() if p.is_file())
    names.update("manuscripts/soft-constraint-study/" + name
                 for name in ["main.tex", "results.tex", "original-results.tex", "generated/asset-manifest.json"])
    for name in names:
        dest = tmp_path / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    original_call = subprocess.check_output
    monkeypatch.setattr(compiler, "ROOT", tmp_path)
    monkeypatch.setattr(compiler.subprocess, "check_output", lambda command, **kwargs: original_call(command, cwd=ROOT))
    return compiler, tmp_path


@pytest.mark.parametrize("name", [
    "data/derived/softqp/C01.json", "docs/contracts/schemas/softqp-index.schema.json", "docs/contracts/catalog.md",
])
def test_adversarial_non_catalog_inputs_and_normative_catalog_still_require_exact_admission(copied_frozen_evidence, name):
    compiler, checkout = copied_frozen_evidence
    source_file = checkout / "manuscripts/soft-constraint-study/main.tex"
    compiler.require_evidence(source_file)
    path = checkout / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="Frozen asset input changed"):
        compiler.require_evidence(source_file)


@pytest.mark.parametrize("anchor_kind", ["historical", "projection-self-hash"])
def test_adversarial_public_display_projection_cannot_authorize_publication(manuscript, anchor_kind):
    spec = importlib.util.spec_from_file_location("actual_projection_guard", ROOT / "scripts/publication_acceptance.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    review = manuscript / "independent-review.json"
    projection = json.loads(review.read_text(encoding="utf-8"))
    assert projection["kind"] == "public-historical-review-projection/v1"
    assert projection["authoritative_for_admission"] is False
    anchor = projection["historical_raw_sha256"] if anchor_kind == "historical" else guard.sha256(review)
    with pytest.raises(ValueError):
        guard.require_acceptance(manuscript / "main.tex", manuscript / "main.pdf", review,
                                 trusted_digest=anchor, phase="before-publication")


def test_actual_portable_figure_acceptance_anchor_and_numeric_macros():
    spec = importlib.util.spec_from_file_location("actual_portable_figure_loader", HERE / "build.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    assert builder.FIGURE_REVIEW == "9230f67cb683db55b530f1e6465ef43cc5280ea27ded04687febbb769706ea91"
    figures = json.loads((HERE / "results/reviews/figure-review.json").read_text(encoding="utf-8"))
    assert builder.canonical_digest(figures) == builder.FIGURE_REVIEW
    expected = builder.result_macros()
    for slug in ["soft-constraint-study", "coupled-peak-study"]:
        assert (ROOT / "manuscripts" / slug / "results.tex").read_text(encoding="utf-8") == expected


def actual_asset_reader(checkout):
    """Load the actual producer function without executing its figure-writing top level."""
    path = ROOT / "manuscripts/shared/generate_assets.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    reader = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "read_blob")
    namespace = {"ROOT": checkout, "SOURCE": "2d3f299d80edad49c2599e61bb6e3c875c119043",
                 "INPUTS": {}, "subprocess": subprocess, "hashlib": hashlib, "importlib": importlib}
    exec(compile(ast.Module(body=[reader], type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def test_asset_producer_returns_the_frozen_blob_after_only_reviewed_catalog_corrections(copied_frozen_evidence):
    _, checkout = copied_frozen_evidence
    namespace = actual_asset_reader(checkout)
    original = frozen_catalog()
    assert (checkout / "docs/contracts/catalog.md").read_bytes().replace(b"\r\n", b"\n") != original
    assert namespace["read_blob"]("docs/contracts/catalog.md") == original
    assert namespace["INPUTS"]["docs/contracts/catalog.md"] == hashlib.sha256(original).hexdigest()


@pytest.mark.parametrize("mutation", ["catalog-prose", "numeric-byte", "schema-byte", "input-map", "forged-git-blob"])
def test_adversarial_asset_producer_refuses_other_edits_and_replaced_authority(copied_frozen_evidence, mutation):
    _, checkout = copied_frozen_evidence
    namespace = actual_asset_reader(checkout)
    paths = {"catalog-prose": "docs/contracts/catalog.md", "numeric-byte": "data/derived/softqp/C01.json",
             "schema-byte": "docs/contracts/schemas/softqp-index.schema.json"}
    name = paths.get(mutation, "docs/contracts/catalog.md")
    if mutation == "input-map":
        path = checkout / "manuscripts/shared/evidence-inputs.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["inputs"].pop(name)
        path.write_text(json.dumps(document), encoding="utf-8")
    elif mutation == "forged-git-blob":
        forged = frozen_catalog().replace(b"the producer is incomplete.", b"the producer is complete.")
        (checkout / name).write_bytes(forged)
        namespace["subprocess"] = SimpleNamespace(check_output=lambda *args, **kwargs: forged)
    else:
        path = checkout / name
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        namespace["read_blob"](name)
    assert name not in namespace["INPUTS"]
