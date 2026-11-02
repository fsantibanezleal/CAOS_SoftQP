"""Canonical batch producer/consumer and hostile sparse-input boundaries."""

import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT/'docs/contracts/schemas/softqp-coupled-batch.schema.json'
EXAMPLE = ROOT/'docs/contracts/examples/softqp-coupled-batch.json'
HAS_PEAK = importlib.util.find_spec('softqp.peak') is not None


@pytest.mark.parametrize('suffix', ['batch', 'observation', 'campaign'])
def test_committed_batch_schema_and_example(suffix):
    schema = json.loads((ROOT/f'docs/contracts/schemas/softqp-coupled-{suffix}.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(json.loads((ROOT/f'docs/contracts/examples/softqp-coupled-{suffix}.json').read_text()))


@pytest.mark.skipif(not HAS_PEAK, reason='Separate softqp0.2 coupled environment required')
def test_batch_producer_consumer_roundtrip():
    from pipeline.coupled_contract import encode_batch, decode_batch
    document = json.loads(EXAMPLE.read_text())
    batch = decode_batch(document)
    assert encode_batch(batch) == document
    assert len(batch.units['variable']) == len(batch.problem.q)
    assert np.isfinite(batch.problem.q).all()


@pytest.mark.skipif(not HAS_PEAK, reason='Separate softqp0.2 coupled environment required')
@pytest.mark.parametrize('mutation', ['negative-pointer', 'row-index', 'duplicate-row', 'vector-shape',
                                    'scale-shape', 'overlap', 'nan-update', 'unit-shape', 'side-pattern', 'bool-row'])
def test_adversarial_malformed_batch_rejects_before_native_setup(mutation):
    from pipeline.coupled_contract import decode_batch
    document = copy.deepcopy(json.loads(EXAMPLE.read_text()))
    problem = document['problem']
    if mutation == 'negative-pointer':
        problem['A']['indptr'][1] = -1
    elif mutation == 'row-index':
        problem['A']['indices'][0] = problem['A']['shape'][0]
    elif mutation == 'duplicate-row':
        problem['A']['indices'][1] = problem['A']['indices'][0]
    elif mutation == 'vector-shape':
        document['updates'][0]['q'].pop()
    elif mutation == 'scale-shape':
        problem['groups'][0]['lower_scale'].append(1.)
    elif mutation == 'overlap':
        problem['groups'].append(copy.deepcopy(problem['groups'][0]))
    elif mutation == 'nan-update':
        document['updates'][0]['lower'][0] = float('nan')
    elif mutation == 'unit-shape':
        document['units']['variable'].pop()
    elif mutation == 'side-pattern':
        document['updates'][0]['lower'][0] = None
    else:
        problem['groups'][0]['rows'][0] = True
    with pytest.raises((ValueError, ValidationError)):
        decode_batch(document)
