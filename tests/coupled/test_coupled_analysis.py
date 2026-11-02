"""Statistical-policy adversaries run without loading the new solver SDK."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'data-pipeline'))
from pipeline import coupled_analysis as MODULE  # noqa: E402
from pipeline.coupled_plan import inventory as planned, incompatible  # noqa: E402


def data():
    protocol = dict(methods={name: dict(backend=backend, settings={}) for name, backend in
                    [('native', 'native'), ('epigraph', 'epigraph'), ('gsp', 'row-split-gsp')]},
                    repetitions=dict(measured=3), seeds=dict(bootstrap=8711, heldout=list(range(6))),
                    generation=dict(sparse=dict(n=[4], group_size=2, condition=[1],
                    curvature=['positive-definite'], quadratic=[0.]), thermal=dict(zones=2,
                    horizon_hours=[], curvature=['positive-definite'])),
                    analysis=dict(bootstrap_resamples=100))
    inventory = planned(protocol, ['heldout'])
    records = [dict(cell, method=method, warmup=False, repetition=repeat,
                    state='accepted', elapsed_seconds=elapsed)
               for cell in inventory for repeat in range(3)
               for method, elapsed in [('native', .8), ('epigraph', 1.), ('gsp', 2.)]]
    return records, inventory, protocol


def test_fastest_registered_baseline_and_seed_bootstrap():
    records, inventory, protocol = data()
    result = MODULE.analyze(records, inventory, protocol)
    assert result['denominator'] == result['seed_clusters'] == 6
    assert result['estimate'] == pytest.approx(.2)
    assert result['established']
    assert {row['fastest_baseline'] for row in result['pairs']} == {'epigraph'}


@pytest.mark.parametrize('mutation', ['missing', 'failed', 'unexpected-incompatible', 'zero-time', 'nan-time'])
def test_adversarial_bad_baseline_cannot_disappear_or_improve_the_primary_endpoint(mutation):
    records, inventory, protocol = data()
    index = next(i for i, row in enumerate(records) if row['method'] == 'epigraph')
    if mutation == 'missing':
        records.pop(index)
    elif mutation == 'failed':
        records[index]['state'] = 'failed'
    elif mutation == 'unexpected-incompatible':
        records[index]['state'] = 'incompatible'
    else:
        records[index]['elapsed_seconds'] = 0 if mutation == 'zero-time' else float('nan')
    result = MODULE.analyze(records, inventory, protocol)
    assert result['denominator'] == 6 and result['failed_pairs'] == 1
    assert result['pairs'][0]['reduction'] == -1
    assert not result['established']


def test_predeclared_incompatibility_is_visible_and_warmups_do_not_enter_estimate():
    records, inventory, protocol = data()
    protocol['generation']['sparse']['quadratic'] = [1.]
    inventory = planned(protocol, ['heldout'])
    for row in records:
        row['quadratic'] = 1.
        if row['method'] == 'gsp':
            row.update(state='incompatible', predeclared_incompatible=True, elapsed_seconds=None,
                       reason=incompatible(row, 'gsp', protocol))
    records.append(dict(records[0], warmup=True, state='failed', elapsed_seconds=999))
    result = MODULE.analyze(records, inventory, protocol)
    assert result['established'] and result['failed_pairs'] == 0
    assert all('gsp' not in row['median_seconds'] for row in result['pairs'])


def test_adversarial_spoofed_compatibility_or_partial_population_cannot_qualify():
    records, inventory, protocol = data()
    for row in records:
        if row['method'] == 'epigraph':
            row.update(state='incompatible', predeclared_incompatible=True, reason='forged')
    result = MODULE.analyze(records, inventory, protocol)
    assert result['failed_pairs'] == 6 and not result['established']
    with pytest.raises(ValueError, match='complete registered'):
        MODULE.analyze(records, inventory[:1], protocol)
