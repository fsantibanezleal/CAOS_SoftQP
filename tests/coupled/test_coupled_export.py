"""Evidence replay fixtures use synthetic durations, never benchmark measurements."""

import csv
from dataclasses import replace
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
HAS_PEAK = importlib.util.find_spec('softqp.peak') is not None
pytestmark = pytest.mark.skipif(not HAS_PEAK, reason='Separate softqp0.2 coupled environment required')


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    from pipeline import coupled_export as consumer
    from pipeline.coupled_accuracy import accept
    from pipeline.coupled_analysis import analyze
    from pipeline.coupled_campaign import CSV_COLUMNS, file_hash
    from pipeline.coupled_cases import generated_batch
    from pipeline.coupled_contract import encode_batch
    from pipeline.coupled_freeze import canonical_digest
    from pipeline.coupled_plan import inventory
    from softqp.peak import solve_peak, PreparedPeakSolver
    import softqp
    from softqp import ext_builtin

    protocol = json.loads((ROOT/'docs/design/coupled-experiments-v1.json').read_text())
    protocol['generation']['sparse'].update(n=[4], group_size=2, condition=[1], curvature=['positive-definite'], quadratic=[1.])
    protocol['generation']['thermal']['horizon_hours'] = []
    protocol['seeds']['development'] = [20261104]  # exposed fixture seed, never heldout data
    protocol['methods'] = {key: protocol['methods'][key] for key in ('native', 'epigraph-default')}
    digest = canonical_digest(protocol)
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    anchor = dict(commit=commit, protocol_sha256=digest, review_sha256='0'*64)
    # This tests the downstream replay consumer, not acceptance of a real
    # preregistration. The separate verifier tests exercise that boundary.
    monkeypatch.setattr(consumer, 'verify_registration', lambda root, document: anchor)
    monkeypatch.setattr(consumer, 'verify_recorded_commit', lambda *args: None)
    monkeypatch.setattr(consumer, 'verify_installed_sdk', lambda document: {})
    plan = inventory(protocol, ['development'])
    spec = plan[0]
    batch = generated_batch(spec, 32)
    canonical = encode_batch(batch)
    batch_hash = canonical_digest(canonical)
    (tmp_path/'datasets').mkdir()
    (tmp_path/'datasets'/f'{spec["id"]}.json').write_text(json.dumps(canonical))
    checks, outputs, objectives = [], [], []
    native_checks, native_outputs = [], []
    native = PreparedPeakSolver(batch.problem)
    for update in batch.updates:
        current = replace(batch.problem, **update)
        oracle = solve_peak(current, 'epigraph', eps_abs=1e-10, eps_rel=1e-10, adaptive_rho=True, scaling=10)
        check = accept(current, oracle, tolerance=1e-7)
        assert check['state'] == 'accepted'
        checks.append(check)
        outputs.append(oracle)
        objectives.append(check['metrics']['objective'])
        native.update(**update)
        result = native.solve()
        check = accept(current, result, objectives[-1])
        assert check['state'] == 'accepted'
        native_outputs.append(result)
        native_checks.append(check)
    oracle_row = dict(spec, schema_version='1.0.0', kind='directional-coupled-observation', role='oracle',
                      method='__oracle__', repetition=None, warmup=False, state='accepted', reason=None,
                      objectives=objectives, frames=checks, backend_results=outputs, batch_sha256=batch_hash)
    records = []
    for repeat in range(-1, 3):
        for name in protocol['methods']:
            rows, backend = (native_checks, native_outputs) if name == 'native' else (checks, outputs)
            # Baseline common checks include its objective-reference field too.
            if name != 'native':
                rows = [accept(replace(batch.problem, **update), result, objective)
                        for update, result, objective in zip(batch.updates, outputs, objectives, strict=True)]
            records.append(dict(spec, schema_version='1.0.0', kind='directional-coupled-observation', role='method',
                                method=name, repetition=repeat, warmup=repeat < 0, state='accepted', reason=None,
                                elapsed_seconds=.8 if name == 'native' else 1., frames=rows,
                                backend_results=backend, batch_sha256=batch_hash))
    with (tmp_path/'trials.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
        for row in [oracle_row]+records:
            stream.write(json.dumps(row, allow_nan=False)+'\n')
    with (tmp_path/'trials.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    sdk = Path(softqp.__file__).resolve().parent
    native_hash = hashlib.sha256(Path(ext_builtin.__file__).read_bytes()).hexdigest()
    sdk_sources = {path.relative_to(sdk).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sdk.rglob('*.py')}
    provenance = dict(packages={name: importlib.metadata.version(name) for name in protocol['packages']},
                      native_binary_sha256=native_hash, sdk_python_sha256=sdk_sources,
                      registration=anchor, algebra_backend='builtin',
                      hardware=dict(machine='unit fixture', processor='unit fixture', logical_cpu_count=1))
    # The fixture remains bound to the supplied public package identities.
    assert native_hash in protocol['engine']['binary_sha256']
    compact = [{key: value for key, value in row.items() if key not in ('frames', 'backend_results')} for row in records]
    document = dict(schema_version='1.0.0', kind='directional-coupled-campaign', protocol_id=protocol['protocol_id'],
                    split='development', environment=provenance, source_sha256=protocol['source_sha256'], inventory=plan,
                    datasets=[dict(spec, oracle_state='accepted', oracle_reason=None, oracle_objectives=objectives,
                                   batch_sha256=batch_hash)], counts={'accepted': 6}, primary=analyze(compact, plan, protocol),
                    peak_worker_rss=0, worker_restarts=0, raw_sha256=file_hash(tmp_path/'trials.jsonl'),
                    csv_sha256=file_hash(tmp_path/'trials.csv'))
    (tmp_path/'protocol.json').write_text(json.dumps(protocol))
    (tmp_path/'campaign.json').write_text(json.dumps(document))
    return tmp_path


def test_complete_downstream_replay_and_exact_csv(evidence):
    from pipeline.coupled_export import validate_output
    result = validate_output(evidence)
    assert result['observations'] == 9
    assert result['independently_checked_frames'] == 288
    assert not result['primary']['established']


@pytest.mark.parametrize('mutation', ['raw-checksum', 'source-map', 'dataset-summary', 'frame-metric',
                                    'backend-label', 'omitted-row', 'csv-content', 'changed-input'])
def test_replay_rejects_tampering_even_when_outer_checksums_are_recomputed(evidence, mutation):
    from pipeline.coupled_campaign import file_hash
    from pipeline.coupled_export import validate_output
    from pipeline.coupled_freeze import canonical_digest
    document = json.loads((evidence/'campaign.json').read_text())
    rows = [json.loads(line) for line in (evidence/'trials.jsonl').read_text().splitlines()]
    if mutation == 'raw-checksum':
        (evidence/'trials.jsonl').write_text('')
    elif mutation == 'source-map':
        document['source_sha256'] = {'forged.py': '0'*64}
    elif mutation == 'dataset-summary':
        document['datasets'][0]['oracle_objectives'][0] += 1
    elif mutation == 'frame-metric':
        rows[1]['frames'][0]['metrics']['objective'] += 1
    elif mutation == 'backend-label':
        rows[1]['backend_results'][0]['method'] = 'epigraph'
    elif mutation == 'omitted-row':
        rows.pop()
    elif mutation == 'csv-content':
        path = evidence/'trials.csv'
        path.write_text(path.read_text().replace('0.8', '0.7', 1))
        document['csv_sha256'] = file_hash(path)
    else:
        path = next((evidence/'datasets').glob('*.json'))
        batch = json.loads(path.read_text())
        batch['problem']['A']['data'][0] *= 2
        path.write_text(json.dumps(batch))
        changed_hash = canonical_digest(batch)
        for row in rows:
            row['batch_sha256'] = changed_hash
        document['datasets'][0]['batch_sha256'] = changed_hash
    if mutation in ('frame-metric', 'backend-label', 'omitted-row', 'changed-input'):
        (evidence/'trials.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
        document['raw_sha256'] = file_hash(evidence/'trials.jsonl')
    (evidence/'campaign.json').write_text(json.dumps(document))
    with pytest.raises((ValueError, AssertionError)):
        validate_output(evidence)
