"""Prospective, bounded full-batch experiment; execution requires a reviewed freeze."""

from dataclasses import replace
import importlib
import hashlib
import csv
import json
import multiprocessing as mp
import os
from pathlib import Path
import tempfile
import time

import numpy as np
from jsonschema import Draft202012Validator, ValidationError

from .coupled_accuracy import accept
from .coupled_analysis import analyze
from .coupled_cases import generated_batch
from .coupled_plan import inventory, incompatible
from .coupled_freeze import source_hashes as frozen_source_hashes, verify_registration, verify_installed_sdk
from .coupled_resources import process_memory
from .coupled_contract import encode_batch
from .coupled_freeze import canonical_digest

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT/'docs/design/coupled-experiments-v1.json'
OBSERVATION_SCHEMA = ROOT/'docs/contracts/schemas/softqp-coupled-observation.schema.json'
CSV_COLUMNS = ['id', 'split', 'seed', 'family', 'n', 'condition', 'group_size', 'horizon', 'zones', 'curvature',
               'quadratic', 'method', 'repetition', 'warmup', 'state', 'reason', 'elapsed_seconds', 'batch_sha256']


def _strict_json(text):
    def reject(token):
        raise ValueError(f'Nonfinite JSON numeric extension: {token}')
    return json.loads(text, parse_constant=reject)


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def method_settings(name, protocol):
    config = protocol['methods'][name]
    return config['backend'], dict(sorted(config['settings'].items()))


def oracle_batch(batch):
    from softqp.peak import solve_peak

    objectives, checks, outputs = [], [], []
    for update in batch.updates:
        current = replace(batch.problem, **update)
        result = solve_peak(current, 'epigraph', eps_abs=1e-10, eps_rel=1e-10,
                            max_iter=200000, adaptive_rho=True, scaling=10, alpha=1.6)
        checked = accept(current, result, tolerance=1e-7)
        checks.append(checked)
        outputs.append(result)
        if checked['state'] != 'accepted':
            return dict(state='oracle-failed', reason=checked['reason'], objectives=None,
                        failed_frame=len(objectives), metrics=checked['metrics'], frames=checks, backend_results=outputs)
        objectives.append(checked['metrics']['objective'])
    return dict(state='accepted', reason=None, objectives=objectives, frames=checks, backend_results=outputs)


def observe_batch(batch, name, objectives, protocol):
    from softqp.peak import PreparedPeakSolver
    from softqp.solvers import UnsupportedProblemError

    start = time.perf_counter()
    checks, outputs = [], []
    try:
        backend, settings = method_settings(name, protocol)
        workspace = PreparedPeakSolver(batch.problem, backend, **settings)
        for step, update in enumerate(batch.updates):
            workspace.update(**update)
            result = workspace.solve()
            current = replace(batch.problem, **update)
            checked = accept(current, result, objectives[step])
            checks.append(checked)
            outputs.append(result)
        elapsed = time.perf_counter()-start
        accepted = all(item['state'] == 'accepted' for item in checks)
        return dict(state='accepted' if accepted else 'accuracy-rejected',
                    reason=None if accepted else 'one or more batch frames failed the common gate',
                    elapsed_seconds=elapsed, frames=checks,
                    backend_results=outputs, dimensions=workspace.dimensions.copy())
    except UnsupportedProblemError as error:
        return dict(state='failed', reason=f'Unexpected incompatibility: {error}',
                    elapsed_seconds=time.perf_counter()-start, frames=checks, backend_results=outputs)
    except Exception as error:
        return dict(state='failed', reason=f'{type(error).__name__}: {error}',
                    elapsed_seconds=time.perf_counter()-start, frames=checks, backend_results=outputs)


def worker(task_path, result_path):
    """Bulk results use files; no blocking pipe receive escapes supervision."""
    try:
        task = _strict_json(Path(task_path).read_text(encoding='utf-8'))
        # Each observation gets a fresh process: preload every competing native
        # library symmetrically before the registered inner operation starts.
        for module in ('softqp.ext_builtin', 'osqp.ext_builtin', 'daqp'):
            importlib.import_module(module)
        batch = generated_batch(task['spec'], task['protocol']['frames'])
        canonical_batch = encode_batch(batch)
        batch_digest = canonical_digest(canonical_batch)
        result = oracle_batch(batch) if task['method'] == '__oracle__' else observe_batch(
            batch, task['method'], task['objectives'], task['protocol'])
        result.update(units=batch.units, description=batch.description)
        result['batch_sha256'] = batch_digest
        if task['method'] == '__oracle__':
            result['canonical_batch'] = canonical_batch
    except Exception as error:
        result = dict(state='failed', reason=f'{type(error).__name__}: {error}', elapsed_seconds=None)
    Path(result_path).write_text(json.dumps(result, allow_nan=False), encoding='utf-8')


class CoupledWorker:
    """One isolated worker per observation; startup/serialization is untimed but bounded."""

    def __init__(self, limits):
        self.limits, self.process = limits, None
        self.peak_rss, self.restarts = 0, 0

    def close(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(5)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(5)
            self.process.close()
            self.process = None

    def observe(self, spec, method, payload, deadline):
        start = time.monotonic()
        reason, state = None, 'failed'
        if start >= deadline:
            return dict(state='resource-limit', reason='Campaign wall limit reached', elapsed_seconds=None)
        with tempfile.TemporaryDirectory(prefix='softqp-coupled-') as directory:
            task_path, result_path = Path(directory)/'task.json', Path(directory)/'result.json'
            task = dict(spec=spec, method=method, **payload)
            encoded = json.dumps(task, allow_nan=False)
            if len(encoded.encode()) > 65536:
                raise ValueError('registered task exceeds the64KiB control-message budget')
            task_path.write_text(encoded, encoding='utf-8')
            self.process = mp.get_context('spawn').Process(target=worker,
                args=(str(task_path), str(result_path)), daemon=True)
            self.process.start()
            try:
                while self.process.is_alive():
                    try:
                        rss, high = process_memory(self.process.pid)
                        self.peak_rss = max(self.peak_rss, rss, high)
                    except (OSError, FileNotFoundError):
                        if self.process.is_alive():
                            raise
                        break
                    if max(rss, high) > self.limits['process_memory_limit_bytes']:
                        reason, state = 'Worker RSS exceeded registered limit', 'resource-limit'
                    elif time.monotonic()-start > self.limits['trial_timeout_seconds']:
                        reason, state = 'Trial exceeded registered wall limit', 'timeout'
                    elif time.monotonic() > deadline:
                        reason, state = 'Campaign wall limit reached', 'resource-limit'
                    if reason:
                        break
                    self.process.join(.01)
                if reason is None and time.monotonic()-start > self.limits['trial_timeout_seconds']:
                    reason, state = 'Trial exceeded registered wall limit', 'timeout'
                if reason is None and time.monotonic() > deadline:
                    reason, state = 'Campaign wall limit reached', 'resource-limit'
                if reason is None and self.process.exitcode == 0 and result_path.is_file():
                    if result_path.stat().st_size > 16777216:
                        reason, state = 'Worker output exceeded16MiB budget', 'resource-limit'
                    else:
                        try:
                            observation = _strict_json(result_path.read_text(encoding='utf-8'))
                            if not isinstance(observation, dict) or observation.get('state') not in (
                                    'accepted', 'failed', 'accuracy-rejected', 'oracle-failed'):
                                raise ValueError('missing or invalid worker result state')
                            if method == '__oracle__' and observation['state'] == 'accepted':
                                objectives = observation.get('objectives')
                                if (not isinstance(objectives, list) or len(objectives) != payload['protocol']['frames']
                                        or not all(type(value) in (int, float) and np.isfinite(value) for value in objectives)
                                        or not isinstance(observation.get('canonical_batch'), dict)):
                                    raise ValueError('incomplete or invalid oracle result')
                            if observation['state'] in ('accepted', 'accuracy-rejected'):
                                envelope = dict(spec, schema_version='1.0.0', kind='directional-coupled-observation',
                                                role='oracle' if method == '__oracle__' else 'method', method=method,
                                                repetition=None if method == '__oracle__' else 0, warmup=False, **observation)
                                Draft202012Validator(_strict_json(OBSERVATION_SCHEMA.read_text(encoding='utf-8'))).validate(envelope)
                            if time.monotonic()-start <= self.limits['trial_timeout_seconds'] and time.monotonic() <= deadline:
                                return observation
                            reason, state = 'Result reception exceeded registered deadline', 'timeout'
                        except (OSError, UnicodeError, ValueError, ValidationError) as error:
                            reason, state = f'Invalid worker output: {type(error).__name__}: {error}', 'failed'
                reason = reason or f'Worker exited without complete output (code {self.process.exitcode})'
                self.restarts += 1
                return dict(state=state, reason=reason, elapsed_seconds=None)
            finally:
                self.close()


def source_hashes(protocol):
    return frozen_source_hashes(ROOT, protocol)


def verify_freeze(protocol, split):
    if protocol['state'] != 'locked' or not protocol.get('independent_review'):
        raise RuntimeError('Study has not passed independent preregistration review')
    if source_hashes(protocol) != protocol['source_sha256']:
        raise RuntimeError('Study source differs from the reviewed freeze')
    registration = verify_registration(ROOT, protocol)
    for name, count in protocol['generation']['counts'].items():
        if len(inventory(protocol, [name])) != count:
            raise RuntimeError('registered inventory count differs from the generator')
    seed_sets = [set(protocol['seeds'][name]) for name in ('development', 'heldout', 'robustness')]
    if (any(len(seed_sets[i]) != len(protocol['seeds'][name]) for i, name in enumerate(('development', 'heldout', 'robustness')))
            or any(type(seed) is not int or seed < 0 for name in ('development', 'heldout', 'robustness') for seed in protocol['seeds'][name])
            or any(seed_sets[i] & seed_sets[j] for i in range(3) for j in range(i))
            or any(seeds & set(protocol['seeds']['excluded_exposed']) for seeds in seed_sets)):
        raise RuntimeError('split seeds overlap or reuse exposed engineering material')
    from .environment import environment
    import importlib.metadata

    provenance = environment()
    for package in protocol['packages']:
        provenance['packages'][package] = importlib.metadata.version(package)
    provenance['registration'] = registration
    from softqp.interface import default_algebra as softqp_algebra
    from osqp.interface import default_algebra as osqp_algebra
    if (os.environ.get('OSQP_ALGEBRA_BACKEND') != 'builtin'
            or softqp_algebra() != 'builtin' or osqp_algebra() != 'builtin'):
        raise RuntimeError('registered study requires the builtin CPU algebra in both wrappers')
    provenance['algebra_backend'] = 'builtin'
    provenance['sdk_python_sha256'] = verify_installed_sdk(protocol)
    import platform
    provenance['hardware'] = dict(machine=platform.machine(), processor=platform.processor(),
                                  logical_cpu_count=os.cpu_count())
    if any(provenance['packages'].get(name) != version for name, version in protocol['packages'].items()):
        raise RuntimeError('Study requires all registered dependency versions')
    if (provenance['engine_revision'] is not None or
            provenance['native_binary_sha256'] not in protocol['engine']['binary_sha256']):
        raise RuntimeError('Study requires an independently verified public wheel binary, not an editable build')
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        if os.environ.get(name) != '1':
            raise RuntimeError(f'{name} must be 1 before importing numerical libraries')
    if split not in ('development', 'heldout', 'robustness'):
        raise ValueError('unknown split')
    return provenance


def run_campaign(output, split):
    protocol = _strict_json(PROTOCOL.read_text(encoding='utf-8'))
    provenance = verify_freeze(protocol, split)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output/'datasets').mkdir()
    (output/'protocol.json').write_text(json.dumps(protocol, indent=2)+'\n', encoding='utf-8')
    plan = inventory(protocol, [split])
    records, datasets = [], []
    rng = np.random.default_rng(protocol['seeds']['order'])
    runner = CoupledWorker(protocol['operating_limits'])
    deadline = time.monotonic()+protocol['operating_limits']['wall_seconds']
    try:
        with (output/'trials.jsonl').open('x', encoding='utf-8', newline='\n') as raw:
            for number, spec in enumerate(plan):
                reference = runner.observe(spec, '__oracle__', dict(protocol=protocol), deadline)
                canonical_batch = reference.pop('canonical_batch', None)
                if canonical_batch is not None:
                    (output/'datasets'/f'{spec["id"]}.json').write_text(
                        json.dumps(canonical_batch, allow_nan=False)+'\n', encoding='utf-8')
                oracle_record = dict(spec, schema_version='1.0.0', kind='directional-coupled-observation',
                                     role='oracle', method='__oracle__', repetition=None, warmup=False, **reference)
                raw.write(json.dumps(oracle_record, allow_nan=False)+'\n')
                raw.flush()
                datasets.append(dict(spec, oracle_state=reference['state'], oracle_reason=reference.get('reason'),
                                     oracle_objectives=reference.get('objectives'), batch_sha256=reference.get('batch_sha256')))
                # Keep only objective references in the parent while methods run.
                reference = {key: reference[key] for key in ('state', 'reason', 'objectives', 'batch_sha256')
                             if key in reference}
                for repeat in range(-protocol['repetitions']['warmup'], protocol['repetitions']['measured']):
                    for name in rng.permutation(sorted(protocol['methods'])).tolist():
                        reason = incompatible(spec, name, protocol)
                        if reason:
                            observed = dict(state='incompatible', reason=reason,
                                            predeclared_incompatible=True, elapsed_seconds=None)
                        elif reference['state'] != 'accepted':
                            observed = dict(state='oracle-failed', reason=reference.get('reason'), elapsed_seconds=None)
                        elif time.monotonic() >= deadline:
                            observed = dict(state='resource-limit', reason='campaign wall limit reached', elapsed_seconds=None)
                        else:
                            observed = runner.observe(spec, name, dict(objectives=reference['objectives'],
                                                                       protocol=protocol), deadline)
                            if ((observed.get('batch_sha256') is not None or observed['state'] in ('accepted', 'accuracy-rejected'))
                                    and observed.get('batch_sha256') != reference.get('batch_sha256')):
                                observed.update(state='failed', reason='method/oracle canonical input hashes differ')
                        record = dict(spec, schema_version='1.0.0', kind='directional-coupled-observation',
                                      role='method', method=name, repetition=repeat, warmup=repeat < 0, **observed)
                        raw.write(json.dumps(record, allow_nan=False)+'\n')
                        raw.flush()
                        records.append({key: value for key, value in record.items()
                                        if key not in ('frames', 'backend_results', 'units', 'description')})
                print(f'{number+1}/{len(plan)} {spec["id"]}', flush=True)
    finally:
        runner.close()
    with (output/'trials.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(records)
    result = dict(schema_version='1.0.0', kind='directional-coupled-campaign',
                  protocol_id=protocol['protocol_id'], split=split, environment=provenance,
                  source_sha256=source_hashes(protocol), inventory=plan, datasets=datasets,
                  counts={state: sum(row['state'] == state for row in records if not row['warmup'])
                          for state in sorted({row['state'] for row in records})},
                  primary=analyze(records, plan, protocol), peak_worker_rss=runner.peak_rss,
                  worker_restarts=runner.restarts, raw_sha256=file_hash(output/'trials.jsonl'),
                  csv_sha256=file_hash(output/'trials.csv'))
    (output/'campaign.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    from .coupled_export import validate_output
    verified = validate_output(output)
    (output/'validation.json').write_text(json.dumps(verified, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return result
