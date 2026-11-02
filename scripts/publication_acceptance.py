"""Require independently issued, hash-bound acceptance before manuscript mutations."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_acceptance(source, pdf, review, *, trusted_digest, phase):
    """The trusted digest must come from the independent reviewer, never a candidate file."""
    source, pdf, review = Path(source).resolve(), Path(pdf).resolve(), Path(review).resolve()
    if phase not in {'before-reservation', 'before-publication'}:
        raise ValueError('Unknown publication phase.')
    if not re.fullmatch('[0-9a-f]{64}', trusted_digest or '') or sha256(review) != trusted_digest:
        raise ValueError('Independent review does not match its externally supplied trust anchor.')
    report = json.loads(review.read_text(encoding='utf-8'))
    if (report.get('decision') != 'ACCEPT_MANUSCRIPTS' or report.get('phase') != phase
            or report.get('reviewer') != '/root/notebook_review'
            or report.get('author') != '/root'
            or report.get('unresolved_findings') != []):
        raise ValueError('Independent content, mathematics and page acceptance is absent.')
    spec = importlib.util.spec_from_file_location('publication_compiler', Path(__file__).with_name('build_manuscript.py'))
    compiler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compiler)
    compiler.require_content(source)
    compiler.require_evidence(source)
    receipt_path = pdf.with_suffix('.build.json')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    inventory, policies = compiler.source_inventory(source), compiler.policy_inventory(source)
    candidates = [d for d in report.get('documents', []) if d.get('slug') == source.parent.name]
    if len(candidates) != 1:
        raise ValueError('Independent review omits or duplicates this document.')
    doc = candidates[0]
    if (doc.get('pdf_sha256') != sha256(pdf) or doc.get('build_receipt_sha256') != sha256(receipt_path)
            or doc.get('inputs_sha256') != inventory or receipt.get('inputs_sha256') != inventory
            or receipt.get('policy_inputs_sha256') != policies
            or receipt.get('compiler_driver_sha256') != sha256(Path(__file__).with_name('build_manuscript.py'))
            or receipt.get('sha256') != sha256(pdf)
            or any(receipt.get(k) != 0 for k in ['warnings', 'overfull', 'underfull'])
            or not all(doc.get(k) is True for k in ['content_accepted', 'mathematics_accepted', 'all_pages_accepted'])):
        raise ValueError('Independent review does not bind the current complete source and PDF.')
    text = source.read_text(encoding='utf-8')
    title = re.search(r'\\title\{([^}]+)\}', text)
    if not title or doc.get('title') != title.group(1):
        raise ValueError('Independent review has a different title.')
    resource_type = 'publication-preprint' if doc.get('doctype') == 'Preprint' else 'publication-report'
    if doc.get('resource_type') != resource_type:
        raise ValueError('Independent review has an inconsistent Zenodo resource type.')
    for key, macro in [('doctype', 'doctype'), ('version', 'docversion'), ('concept_doi', 'conceptdoi'), ('version_doi', 'versiondoi')]:
        match = re.search(r'\\newcommand\{\\' + macro + r'\}\{([^}]+)\}', text)
        if not match or doc.get(key) != match.group(1):
            raise ValueError('Independent review has a different document identity: ' + key)
    if phase == 'before-publication' and doc['version_doi'] == doc['concept_doi']:
        raise ValueError('Final publication requires the reserved version DOI in the reviewed PDF.')
    return doc
