"""Package complete reviewed evidence, preserving and verifying every archived byte."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile

SCRIPT = Path(__file__).with_name('render-study-summary.py')
spec = importlib.util.spec_from_file_location('coupled_summary_guard', SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
CHUNK = 1024*1024


def checked_path(root, relative):
    path = (root/relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f'Missing or escaping evidence path: {relative}')
    return path


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:
        raise ValueError('Unsafe archive member name')
    return name


def file_digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(CHUNK):
            hasher.update(chunk)
    return hasher.hexdigest()


def make_bundle(app, studies, review_path, summary, figure_review_path, output):
    registration_path = app/'docs/design/coupled-experiments-v1.registration.json'
    documents, registration, review = guard.load_complete(studies, review_path, registration_path)
    for name in ('summary.json', 'SHA256SUMS.json'):
        if not (summary/name).is_file():
            raise ValueError('Completed reviewed summary artifacts are required')
    facts = guard.read(summary/'summary.json')
    if (facts['evidence_review_sha256'] != guard.digest(review)
            or facts['protocol_sha256'] != registration['protocol_sha256']
            or facts['primary'] != documents['heldout']['primary']
            or facts['counts'] != {split: doc['counts'] for split, doc in documents.items()}
            or facts['source_commit'] != documents['heldout']['environment']['registration']['commit']):
        raise ValueError('Summary artifacts do not represent accepted full evidence')
    sums = guard.read(summary/'SHA256SUMS.json')
    expected_summary = {'summary.json', 'observation-states.png', 'observation-states.svg',
                        'primary-full-population.png', 'primary-full-population.svg'}
    if set(sums) != expected_summary:
        raise ValueError('Incomplete or unexpected summary figure inventory')
    if not figure_review_path.is_file():
        raise ValueError('Independent figure appearance acceptance is required')
    figure_review = guard.read(figure_review_path)
    if (figure_review.get('decision') != 'ACCEPT_FIGURES'
            or figure_review.get('evidence_review_sha256') != guard.digest(review)
            or figure_review.get('summary_sha256') != sums['summary.json']
            or figure_review.get('renderer_sha256') != hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
            or figure_review.get('figure_sha256') != {name: value for name, value in sums.items() if name != 'summary.json'}):
        raise ValueError('Figure acceptance differs from the exact reviewed artifacts')
    output = output.resolve()
    partial = output.with_name(output.name+'.partial')
    checksum = output.with_name(output.name+'.sha256')
    if output.exists() or partial.exists() or checksum.exists():
        raise FileExistsError('Bundle, partial and checksum paths must all be new')
    entries = []
    for split, campaign in documents.items():
        root = studies/f'coupled-{split}-v1'
        expected = {'trials.jsonl': campaign['raw_sha256'], 'trials.csv': campaign['csv_sha256']}
        for name in ('campaign.json', 'validation.json', 'protocol.json', 'trials.jsonl', 'trials.csv'):
            path = checked_path(root, name)
            if name in ('campaign.json', 'validation.json', 'protocol.json'):
                payload = path.read_bytes()
                accepted = (review['campaign_sha256'][split] if name == 'campaign.json'
                            else review['validation_sha256'][split] if name == 'validation.json'
                            else registration['protocol_sha256'])
                if guard.digest(json.loads(payload)) != accepted:
                    raise ValueError('Metadata changed since independent review')
                entries.append((f'{split}/{name}', payload, hashlib.sha256(payload).hexdigest()))
            else:
                entries.append((f'{split}/{name}', path, expected[name]))
        datasets = campaign['datasets']
        if (len(datasets) != len(campaign['inventory'])
                or len({row['id'] for row in datasets}) != len(datasets)
                or {row['id'] for row in datasets} != {row['id'] for row in campaign['inventory']}):
            raise ValueError('Canonical dataset summaries do not cover the entire inventory')
        for dataset in datasets:
            if (dataset['oracle_state'] not in {'accepted', 'oracle-failed', 'failed', 'timeout', 'resource-limit'}
                    or dataset['oracle_state'] == 'accepted' and dataset.get('batch_sha256') is None):
                raise ValueError('Accepted oracle lacks canonical input identity')
            if not re.fullmatch(re.escape(split)+r'-[0-9]{4}', dataset['id']):
                raise ValueError('Invalid canonical dataset identity')
            if dataset.get('batch_sha256') is not None:
                name = f'datasets/{dataset["id"]}.json'
                path = checked_path(root, name)
                payload = path.read_bytes()
                if guard.digest(json.loads(payload)) != dataset['batch_sha256']:
                    raise ValueError('Canonical input differs from the oracle evidence')
                entries.append((f'{split}/{name}', path, hashlib.sha256(payload).hexdigest()))
    for name, expected in registration['source_sha256'].items():
        raw = checked_path(app, name).read_bytes().replace(b'\r\n', b'\n')
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Current source differs from the registered LF snapshot')
        entries.append((f'source/{name}', raw, expected))
    for name in ('coupled-experiments-v1.json', 'coupled-experiments-v1.review.json',
                 'coupled-experiments-v1.registration.json'):
        path = checked_path(app, 'docs/design/'+name)
        payload = path.read_bytes()
        expected = (registration['protocol_sha256'] if name == 'coupled-experiments-v1.json'
                    else registration['review_sha256'] if name == 'coupled-experiments-v1.review.json'
                    else guard.digest(registration))
        if guard.digest(json.loads(payload)) != expected:
            raise ValueError('Registration metadata changed during bundle preparation')
        entries.append((f'registration/{name}', payload, hashlib.sha256(payload).hexdigest()))
    for name, path, accepted in [('final-campaign-evidence-review.json', review_path, review),
                                 ('figure-review.json', figure_review_path, figure_review)]:
        payload = path.read_bytes()
        if guard.digest(json.loads(payload)) != guard.digest(accepted):
            raise ValueError('Independent review changed during bundle preparation')
        entries.append((f'review/{name}', payload, hashlib.sha256(payload).hexdigest()))
    entries.append(('tools/render-study-summary.py', SCRIPT.read_bytes(), figure_review['renderer_sha256']))
    entries.append(('tools/package-study-evidence.py', Path(__file__), None))
    entries.append(('source/LICENSE', checked_path(app, 'LICENSE'), None))
    for name in sorted(sums):
        entries.append((f'summary/{name}', checked_path(summary, name), sums[name]))
    sums_payload = (summary/'SHA256SUMS.json').read_bytes()
    if json.loads(sums_payload) != sums:
        raise ValueError('Summary checksums changed during bundle preparation')
    entries.append(('summary/SHA256SUMS.json', sums_payload, hashlib.sha256(sums_payload).hexdigest()))
    commit = documents['heldout']['environment']['registration']['commit']
    readme = f"""Coupled study evidence
======================

This archive contains all registered splits, raw journals, canonical inputs,
CSV, source snapshots, registration, independent evidence acceptance and plots.
Qualification is the frozen heldout/campaign.json primary.established value.
Evidence acceptance records the accuracy of the evidence, not a performance win.
The cases are synthetic forecasts; timings are complete 32-forecast operations
on the recorded nonreserved host. Source licensing is preserved in source/LICENSE.

Reproduction uses the public companion repository:
https://github.com/fsantibanezleal/CAOS_SoftQP
Check out {commit}, create the declared CPython 3.12 environment and install
experiments/coupled-v1/requirements.txt from the public package index. The frozen
runtime requires the committed registration and verified public SDK wheel.
Run data-pipeline/run_coupled_study.py --validate-output --output <extracted split>
for each split. Source snapshots use the registered LF-normalized byte identity;
all exported evidence bytes, including CSV line endings, remain unchanged.

MANIFEST.json hashes every other archive member. The external .sha256 file
identifies the complete ZIP after decompression/hash verification.
"""
    entries.append(('README.txt', readme.encode('utf-8'), None))
    names = [safe_name(name) for name, _, _ in entries]
    if len(names) != len(set(names)):
        raise ValueError('Duplicate archive member identity')
    output.parent.mkdir(parents=True, exist_ok=True)
    members = {}
    with partial.open('xb') as stream:
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6,
                             allowZip64=True) as archive:
            for name, source, expected in sorted(entries, key=lambda entry: entry[0]):
                hasher, size = hashlib.sha256(), 0
                with archive.open(name, 'w', force_zip64=True) as target:
                    if isinstance(source, bytes):
                        target.write(source)
                        hasher.update(source)
                        size = len(source)
                    else:
                        before = source.stat()
                        with source.open('rb') as original:
                            while chunk := original.read(CHUNK):
                                target.write(chunk)
                                hasher.update(chunk)
                                size += len(chunk)
                        after = source.stat()
                        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                            raise ValueError('Evidence changed while being archived')
                actual = hasher.hexdigest()
                if expected is not None and expected != actual:
                    raise ValueError(f'Registered member checksum differs: {name}')
                members[name] = {'sha256': actual, 'bytes': size}
            manifest = {'protocol_sha256': registration['protocol_sha256'], 'source_commit': commit,
                        'final_review_sha256': guard.digest(review), 'members': members}
            archive.writestr('MANIFEST.json', json.dumps(manifest, indent=2, allow_nan=False)+'\n')
        # Capture ownership from our exclusively created file descriptor.
        created = os.fstat(stream.fileno())
        owned_identity = (created.st_dev, created.st_ino)
    candidate_digest = file_digest(partial)
    with zipfile.ZipFile(partial) as archive:
        if json.loads(archive.read('MANIFEST.json')) != manifest:
            raise ValueError('Written archive manifest differs')
        if len(archive.namelist()) != len(members)+1 or set(archive.namelist()) != set(members)|{'MANIFEST.json'}:
            raise ValueError('Written ZIP inventory differs')
        for name, expected in members.items():
            hasher, size = hashlib.sha256(), 0
            with archive.open(name) as original:
                while chunk := original.read(CHUNK):
                    hasher.update(chunk)
                    size += len(chunk)
            if hasher.hexdigest() != expected['sha256'] or size != expected['bytes']:
                raise ValueError('Decompressed archive bytes differ from verified source')
    if file_digest(partial) != candidate_digest:
        raise ValueError('Archive container changed during decompression verification')
    # Refuse overwriting, then verify the published path against the verified
    # container identity. Retain .partial for diagnosis on any publication fault.
    current_partial = partial.lstat()
    if (current_partial.st_dev, current_partial.st_ino) != owned_identity:
        raise ValueError('Verified partial file identity changed before publication')
    published = False
    try:
        os.link(partial, output)
        published = True
        linked = output.lstat()
        if (linked.st_dev, linked.st_ino) != owned_identity:
            raise ValueError('Published path is not our verified file')
        if file_digest(output) != candidate_digest:
            raise ValueError('Published archive differs from the verified container')
        with checksum.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(f'{candidate_digest}  {output.name}\n')
    except Exception:
        if published and output.exists():
            current = output.lstat()
            if (current.st_dev, current.st_ino) == owned_identity:
                output.unlink()
        raise
    partial.unlink()
    return {'state': 'verified', 'archive': str(output), 'sha256': candidate_digest,
            'bytes': output.stat().st_size, 'members': len(members)+1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('app', 'studies', 'review', 'summary', 'figure-review', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(make_bundle(args.app, args.studies, args.review, args.summary, args.figure_review, args.output), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as error:
        print(f'Evidence bundle refused: {error}', file=sys.stderr)
        raise SystemExit(2)
