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
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
FROZEN_SOURCE = '2d3f299d80edad49c2599e61bb6e3c875c119043'
ORIGINAL_DIGEST = '3a79bc8abf63f70cac054c26bb5ec19bff0321e0047673d7bc3b239d380f00b5'
ASSET_INPUTS_DIGEST = 'a9d667292dbbe59e381692d106bbbdd23f8f71d4c5960209c048bcadb45766c1'
PAPER_FIGURES = {'scalar-objective', 'original-effect', 'cold-times', 'conditioning', 'stream-reuse',
                 'coupled-population', 'coupled-states', 'coupled-formulations', 'directional-lesson'}
REPORT_FIGURES = PAPER_FIGURES | {'architecture', 'formulation-size', 'compatibility', 'control-stream'}


def require_evidence(source):
    """Bind both scientific populations even when the shared driver is used directly."""
    source = Path(source).resolve()
    if not source.is_relative_to(ROOT / 'manuscripts'):
        return
    path = 'data/derived/experiments/campaign.json'
    raw = subprocess.check_output(['git', 'show', FROZEN_SOURCE + ':' + path], cwd=ROOT)
    live = (ROOT / path).read_bytes()
    if (hashlib.sha256(raw).hexdigest() != ORIGINAL_DIGEST
            or live.replace(b'\r\n', b'\n') != raw.replace(b'\r\n', b'\n')):
        raise ValueError('Original study differs from its immutable numerical authority.')
    campaign = json.loads(raw)
    ep = campaign['primary_endpoint']
    values = {'OriginalEstimate': 100 * ep['median_relative_reduction'],
              'OriginalLower': 100 * ep['confidence_interval_95'][0],
              'OriginalUpper': 100 * ep['confidence_interval_95'][1],
              'OriginalPairs': ep['paired_samples']}
    expected = '% Exact exported original-study summary; no inferential recomputation.\n'
    expected += ''.join('\\newcommand{\\' + name + '}{' +
                        (str(value) if name == 'OriginalPairs' else f'{value:.6f}') + '}\n'
                        for name, value in values.items())
    if (source.parent / 'original-results.tex').read_text(encoding='utf-8') != expected:
        raise ValueError('Original-study result macros differ from immutable evidence.')
    spec = importlib.util.spec_from_file_location('accepted_grouped_evidence', ROOT / 'manuscripts/coupled-peak-study/build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if (source.parent / 'results.tex').read_text(encoding='utf-8') != module.result_macros():
        raise ValueError('Grouped-study result macros differ from independent evidence.')
    manifest = json.loads((source.parent / 'generated/asset-manifest.json').read_text(encoding='utf-8'))
    declared = json.loads((ROOT / 'manuscripts/shared/evidence-inputs.json').read_text(encoding='utf-8'))
    identity = hashlib.sha256(json.dumps(declared['inputs'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if identity != ASSET_INPUTS_DIGEST:
        raise ValueError('Frozen evidence input inventory is incomplete or replaced.')
    if manifest['source_commit'] != FROZEN_SOURCE or declared['frozen_source'] != FROZEN_SOURCE or manifest['source_inputs'] != declared['inputs']:
        raise ValueError('Asset evidence identity differs from its frozen source.')
    for name, digest in declared['inputs'].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('Evidence path escapes repository.')
        canonical = subprocess.check_output(['git', 'show', FROZEN_SOURCE + ':' + name], cwd=ROOT)
        if hashlib.sha256(canonical).hexdigest() != digest or path.read_bytes().replace(b'\r\n', b'\n') != canonical.replace(b'\r\n', b'\n'):
            raise ValueError('Frozen asset input changed: ' + name)
    expected_figures = {'figures/' + name + '.pdf' for name in (PAPER_FIGURES if source.parent.name == 'coupled-peak-study' else REPORT_FIGURES)}
    if {f['file'] for f in manifest['figures']} != expected_figures or len(manifest['figures']) != len(expected_figures):
        raise ValueError('Derived vector figure inventory is incomplete or replaced.')
    for figure in manifest['figures']:
        path = (source.parent / figure['file']).resolve()
        if not path.is_relative_to(source.parent) or hashlib.sha256(path.read_bytes()).hexdigest() != figure['sha256']:
            raise ValueError('Derived vector figure differs from asset manifest.')


def policy_inventory(source):
    """Hash policy text with Git's LF normalization for cross-checkout identity."""
    if not Path(source).resolve().is_relative_to(ROOT / 'manuscripts'):
        return {}
    paths = [* (ROOT / 'manuscripts/shared').glob('*.py'),
             * (ROOT / 'manuscripts/shared').glob('*.json'),
             ROOT / 'manuscripts/shared/requirements.txt', ROOT / 'docs/design/SDD.md',
             ROOT / 'docs/contracts/catalog.md', ROOT / 'manuscripts/coupled-peak-study/build.py',
             ROOT / 'scripts/manuscript_content_bar.py']
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest() for p in sorted(paths)}


def source_inventory(source):
    """Resolve document-root paths as pdflatex does, including nested inputs."""
    source = Path(source).resolve()
    root = source.parent
    files, pending = {}, [source]
    pending += [p for p in [root / 'coverage.json', root / 'generated/asset-manifest.json'] if p.is_file()]
    while pending:
        path = pending.pop()
        if not path.is_relative_to(root):
            raise ValueError("Manuscript input escapes its source directory.")
        if not path.is_file():
            raise ValueError(f"Missing manuscript input: {path.name}")
        relative = path.relative_to(root).as_posix()
        if relative in files:
            continue
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.suffix != '.tex':
            continue
        text = re.sub(r'(?<!\\)%.*', '', path.read_text(encoding='utf-8'))
        for match in re.finditer(r'\\(input|include|includegraphics|bibliography)(?:\[[^]]*\])?\{([^}]+)\}', text):
            command, raw = match.groups()
            for name in raw.split(',') if command == 'bibliography' else [raw]:
                if '\\' in name:
                    raise ValueError('Dynamic manuscript file paths are not admitted.')
                target = root / name
                if not target.suffix:
                    target = target.with_suffix('.bib' if command == 'bibliography' else '.pdf' if command == 'includegraphics' else '.tex')
                pending.append(target.resolve())
    return files


def require_content(source):
    root = Path(__file__).resolve().parents[1]
    source = Path(source).resolve()
    if not source.is_relative_to(root / 'manuscripts'):
        return
    spec = importlib.util.spec_from_file_location('softqp_content_bar', root / 'scripts/manuscript_content_bar.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    findings = module.check(root, only=source.parent.name)
    cov = json.loads((source.parent / 'coverage.json').read_text(encoding='utf-8'))
    doc = module.load(source.parent)
    for group in ['methods', 'contracts', 'claims']:
        regions = []
        for label in cov.get(group, {}).values():
            _, holder = module.region_of(doc, label)
            if holder is not None:
                regions.append((holder.start, holder.end))
        if len(set(regions)) != len(regions):
            findings.append(f'{group}: distinct requirements alias the same content region')
    if cov['kind'] == 'technical-report':
        sdd = (root / 'docs/design/SDD.md').read_text(encoding='utf-8')
        ladder = sdd.split('## Method ladder', 1)[1].split('\n## ', 1)[0]
        ids = set(re.findall(r'^\|\s*((?:M|BS)-\d+)\s*\|', ladder, re.M))
        if set(cov.get('methods', {})) != ids:
            findings.append('Report coverage does not match every executable method row.')
    text = '\n'.join((source.parent / p).read_text(encoding='utf-8') for p in source_inventory(source) if p.endswith('.tex'))
    if re.search(r'\\chapter\b|\[chapter\]', text):
        findings.append('The base-derived section-based documents cannot contain chapter structure.')
    expected = 'Preprint' if cov['kind'] == 'manuscript' else 'Technical report'
    if f'\\newcommand{{\\doctype}}{{{expected}}}' not in source.read_text(encoding='utf-8'):
        findings.append('Document-type identity does not match coverage kind.')
    if findings:
        raise ValueError('Manuscript content/coverage refused:\n' + '\n'.join(findings))


def compile_document(source, output, *, compiler=None, runner=subprocess.run):
    source, output = Path(source).resolve(), Path(output).resolve()
    text = source.read_text(encoding="utf-8")
    if not re.search(r"\\documentclass(?:\[[^]]*\])?\{(?:article|report|IEEEtran|elsarticle|revtex4-2)\}", text):
        raise ValueError("A manuscript requires an admitted native LaTeX document class.")
    compiler = compiler or shutil.which("pdflatex")
    if compiler is None:
        raise RuntimeError("Install a LaTeX distribution providing pdflatex.")
    output.mkdir(parents=True, exist_ok=False)
    command = [str(compiler), "-interaction=nonstopmode", "-halt-on-error",
               "-file-line-error", "-restrict-write18" if os.name == "nt" else "-shell-restricted", "-recorder",
               f"-output-directory={output}", source.name]
    for index in range(6):
        result = runner(command, cwd=source.parent, capture_output=True, timeout=120)
        (output / f"pass-{index + 1}.stdout.log").write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"LaTeX compilation failed on pass {index + 1}; inspect its log.")
        if index == 0 and re.search(r'\\bibliography\{', text):
            bibtex = shutil.which('bibtex')
            if bibtex is None:
                raise RuntimeError('Install BibTeX for the cited bibliography.')
            env = dict(os.environ)
            env['BIBINPUTS'] = str(source.parent) + os.pathsep + env.get('BIBINPUTS', '')
            bibliography = runner([bibtex, source.stem], cwd=output, env=env,
                                  capture_output=True, timeout=120)
            (output / 'bibtex.stdout.log').write_bytes(bibliography.stdout + bibliography.stderr)
            if bibliography.returncode:
                raise RuntimeError('BibTeX compilation failed; inspect its external log.')
        if index >= 2:
            current_log = (output / f'{source.stem}.log').read_text(encoding='utf-8', errors='replace')
            if 'Label(s) may have changed' not in current_log:
                break
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
    require_content(source)
    require_evidence(source)
    inputs = source_inventory(source)
    policies = policy_inventory(source)
    driver = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    pdf = compile_document(source, output)
    if source_inventory(source) != inputs or policy_inventory(source) != policies or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != driver:
        raise RuntimeError("Manuscript source, figure or compiler driver changed during compilation.")
    require_evidence(source)
    receipt = {"state": "compiled-awaiting-independent-page-review", "engine": "pdflatex",
               "source_sha256": inputs[source.name], "inputs_sha256": inputs,
               "compiler_driver_sha256": driver,
               "policy_inputs_sha256": policies,
               "policy_text_newlines": "LF-normalized, matching committed Git text",
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
