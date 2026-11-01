"""Validate full coupled evidence and independently replay every accepted frame."""

from dataclasses import replace
import csv
import importlib.metadata
import json
from pathlib import Path
import subprocess

import numpy as np

from jsonschema import Draft202012Validator

from .coupled_accuracy import accept
from .coupled_analysis import analyze
from .coupled_contract import decode_batch, encode_batch
from .coupled_cases import generated_batch
from .coupled_freeze import canonical_digest, verify_registration, verify_installed_sdk, verify_recorded_commit
from .coupled_campaign import _strict_json, file_hash, CSV_COLUMNS
from .coupled_plan import inventory, incompatible

ROOT = Path(__file__).resolve().parents[2]


def _same_metrics(stored, recomputed):
    if stored['state'] != recomputed['state'] or stored['reason'] != recomputed['reason']:
        raise ValueError('stored acceptance state/reason differs from independent replay')
    left, right = stored['metrics'], recomputed['metrics']
    if left is None or right is None:
        if left != right:
            raise ValueError('stored failed-frame metrics differ from replay')
        return
    if set(left) != set(right) or any(not np.allclose(left[key], right[key], rtol=1e-8, atol=1e-10)
                                    for key in right):
        raise ValueError('stored original-space frame metrics differ from independent replay')


def validate_output(directory):
    directory = Path(directory)
    protocol = _strict_json((directory/'protocol.json').read_text(encoding='utf-8'))
    document = _strict_json((directory/'campaign.json').read_text(encoding='utf-8'))
    registration = verify_registration(ROOT, protocol)
    verify_installed_sdk(protocol)
    if any(importlib.metadata.version(name) != value for name, value in protocol['packages'].items()):
        raise ValueError('replay dependencies differ from the registered versions')
    schema_root = ROOT/'docs/contracts/schemas'
    Draft202012Validator(json.loads((schema_root/'softqp-coupled-campaign.schema.json').read_text())).validate(document)
    if file_hash(directory/'trials.jsonl') != document['raw_sha256'] or file_hash(directory/'trials.csv') != document['csv_sha256']:
        raise ValueError('raw JSONL or CSV checksum differs from evidence index')
    if canonical_digest(protocol) != document['environment']['registration']['protocol_sha256']:
        raise ValueError('protocol snapshot differs from the registered receipt')
    provenance = document['environment']
    if (document['source_sha256'] != protocol['source_sha256'] or provenance.get('algebra_backend') != 'builtin'
            or provenance['registration']['review_sha256'] != registration['review_sha256']
            or any(provenance['packages'].get(name) != version for name, version in protocol['packages'].items())
            or provenance['native_binary_sha256'] not in protocol['engine']['binary_sha256']
            or provenance['sdk_python_sha256'] != protocol['engine']['python_sha256_by_binary'].get(
                provenance['native_binary_sha256'])):
        raise ValueError('export provenance differs from the accepted registration/public wheel')
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor',
                    provenance['registration']['commit'], 'HEAD'], check=True, capture_output=True, timeout=5)
    verify_recorded_commit(ROOT, provenance['registration']['commit'], protocol)
    plan = inventory(protocol, [document['split']])
    if document['inventory'] != plan:
        raise ValueError('export inventory differs from the entire registered split')
    identities = {spec['id']: spec for spec in plan}
    validator = Draft202012Validator(json.loads((schema_root/'softqp-coupled-observation.schema.json').read_text()))
    references, records, batches, seen, datasets = {}, [], {}, set(), []
    checked_frames = 0
    with (directory/'trials.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            row = _strict_json(line)
            validator.validate(row)
            if row['id'] not in identities or any(row.get(key) != value for key, value in identities[row['id']].items()):
                raise ValueError('raw trial identity/metadata differs from the registered inventory')
            identity = row['id'], row['role'], row['method'], row['repetition']
            if identity in seen:
                raise ValueError('duplicate raw observation identity')
            seen.add(identity)
            dispatched = 'epigraph' if row['role'] == 'oracle' else protocol['methods'][row['method']]['backend']
            if any(backend.get('method') != dispatched for backend in row.get('backend_results', [])):
                raise ValueError('backend result labels differ from the registered dispatched method')
            if row['role'] == 'oracle':
                references.clear()
                batches.clear()
                datasets.append(dict(identities[row['id']], oracle_state=row['state'], oracle_reason=row['reason'],
                                     oracle_objectives=row.get('objectives'), batch_sha256=row.get('batch_sha256')))
                if row.get('batch_sha256'):
                    batch_document = _strict_json((directory/'datasets'/f'{row["id"]}.json').read_text())
                    if canonical_digest(batch_document) != row['batch_sha256']:
                        raise ValueError('canonical dataset hash differs from oracle')
                    expected_batch = encode_batch(generated_batch(identities[row['id']], protocol['frames']))
                    if canonical_digest(expected_batch) != row['batch_sha256']:
                        raise ValueError('canonical dataset differs from the frozen deterministic generator/specification')
                    batch = decode_batch(batch_document)
                    batches[row['id']] = batch
                if row['state'] == 'accepted':
                    references[row['id']] = row
                    for update, backend, objective, stored in zip(batch.updates, row['backend_results'], row['objectives'], row['frames'], strict=True):
                        checked = accept(replace(batch.problem, **update), backend, tolerance=1e-7)
                        _same_metrics(stored, checked)
                        if checked['state'] != 'accepted' or not np.isclose(objective, checked['metrics']['objective'], rtol=1e-10, atol=1e-10):
                            raise ValueError('stored oracle fails independent replay')
                        checked_frames += 1
                continue
            if row['warmup'] != (row['repetition'] < 0):
                raise ValueError('warmup flag disagrees with the registered repetition identity')
            declared = incompatible(identities[row['id']], row['method'], protocol)
            if (declared is not None) != (row['state'] == 'incompatible'):
                raise ValueError('exported incompatibility differs from registered semantics')
            if declared is not None and (row['reason'] != declared or not row.get('predeclared_incompatible')):
                raise ValueError('incompatibility explanation differs from registered semantics')
            if row['state'] == 'accepted':
                reference = references.get(row['id'])
                if reference is None or reference['batch_sha256'] != row['batch_sha256']:
                    raise ValueError('accepted method lacks a matching preceding oracle')
                batch = batches[row['id']]
                for update, backend, objective, stored in zip(batch.updates, row['backend_results'], reference['objectives'], row['frames'], strict=True):
                    checked = accept(replace(batch.problem, **update), backend, objective)
                    _same_metrics(stored, checked)
                    if checked['state'] != 'accepted':
                        raise ValueError('stored method frame fails independent replay')
                    checked_frames += 1
            records.append({key: value for key, value in row.items()
                            if key not in ('frames', 'backend_results', 'units', 'description')})
    expected = {(spec['id'], 'oracle', '__oracle__', None) for spec in plan}
    expected.update((spec['id'], 'method', method, repeat) for spec in plan for method in protocol['methods']
                    for repeat in range(-protocol['repetitions']['warmup'], protocol['repetitions']['measured']))
    if seen != expected:
        raise ValueError('raw journal does not contain exactly the full registered observation inventory')
    if document['datasets'] != datasets:
        raise ValueError('dataset summaries differ from raw oracle observations')
    with (directory/'trials.csv').open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        expected_csv = [{key: '' if row.get(key) is None else str(row.get(key, '')) for key in CSV_COLUMNS}
                        for row in records]
        if reader.fieldnames != CSV_COLUMNS or list(reader) != expected_csv:
            raise ValueError('CSV does not exactly represent the raw method observations')
    if analyze(records, plan, protocol) != document['primary']:
        raise ValueError('primary analysis differs from complete raw observations')
    counts = {state: sum(row['state'] == state for row in records if not row['warmup'])
              for state in sorted({row['state'] for row in records})}
    if counts != document['counts']:
        raise ValueError('state counts differ from the raw denominator')
    return dict(state='validated', observations=len(seen), independently_checked_frames=checked_frames,
                primary=document['primary'])
