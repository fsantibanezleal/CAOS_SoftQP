"""Prospective paired analysis retaining the full registered denominator."""

import numpy as np

from .coupled_plan import inventory as registered_inventory, incompatible


def analyze(records, inventory, protocol):
    if len({cell['id'] for cell in inventory}) != len(inventory):
        raise ValueError('duplicate registered instance identity')
    primary = [cell for cell in inventory if cell['split'] == 'heldout']
    expected_inventory = registered_inventory(protocol, ['heldout'])
    if not primary:
        return dict(established=False, reason='no heldout observations in this split',
                    denominator=len(expected_inventory), observed_heldout=0, pairs=[])
    if sorted(primary, key=lambda cell: cell['id']) != sorted(expected_inventory, key=lambda cell: cell['id']):
        raise ValueError('supplied heldout inventory differs from the complete registered population')
    identities = {cell['id']: cell for cell in inventory}
    for row in records:
        if row['id'] not in identities or row['method'] not in protocol['methods']:
            raise ValueError('unregistered trial identity or method')
        if any(row.get(key) != value for key, value in identities[row['id']].items()):
            raise ValueError('trial metadata differs from its registered instance')
    measured = [row for row in records if not row['warmup']]
    grouped = {}
    for row in measured:
        grouped.setdefault((row['id'], row['method']), []).append(row)
    pairs = []
    expected = protocol['repetitions']['measured']
    methods = sorted(protocol['methods'])
    for cell in primary:
        durations, failure = {}, []
        for method in methods:
            rows = grouped.get((cell['id'], method), [])
            if (len(rows) != expected or any(type(row['repetition']) is not int for row in rows)
                    or {row['repetition'] for row in rows} != set(range(expected))):
                failure.append(f'{method}: missing or duplicate repetitions')
                continue
            declared = incompatible(cell, method, protocol)
            if declared and all(row['state'] == 'incompatible' and row.get('predeclared_incompatible')
                                and row.get('reason') == declared for row in rows):
                continue
            if declared:
                failure.append(f'{method}: registered incompatibility evidence differs')
                continue
            if not all(row['state'] == 'accepted' and isinstance(row.get('elapsed_seconds'), (int, float))
                       and not isinstance(row['elapsed_seconds'], bool)
                       and np.isfinite(row['elapsed_seconds']) and row['elapsed_seconds'] > 0 for row in rows):
                failure.append(f'{method}: unsuccessful registered observation')
                continue
            durations[method] = float(np.median([row['elapsed_seconds'] for row in rows]))
        baselines = {name: value for name, value in durations.items() if name != 'native'}
        if 'native' not in durations:
            failure.append('native: no accepted complete batch')
        if not baselines:
            failure.append('no accepted compatible baseline')
        if failure or 'native' not in durations or not baselines:
            reduction, comparator = -1., None
        else:
            comparator = min(baselines, key=lambda name: (baselines[name], name))
            reduction = 1.-durations['native']/baselines[comparator]
        pairs.append(dict(id=cell['id'], seed=cell['seed'], reduction=reduction,
                          fastest_baseline=comparator, failure_reasons=failure, median_seconds=durations))
    clusters = sorted({row['seed'] for row in pairs})
    if not pairs or not clusters:
        return dict(established=False, reason='no complete registered heldout inventory', pairs=pairs)
    rng = np.random.default_rng(protocol['seeds']['bootstrap'])
    by_seed = {seed: [row['reduction'] for row in pairs if row['seed'] == seed] for seed in clusters}
    draws = [float(np.median(np.concatenate([by_seed[int(seed)] for seed in
             rng.choice(clusters, size=len(clusters), replace=True)])))
             for _ in range(protocol['analysis']['bootstrap_resamples'])]
    estimate = float(np.median([row['reduction'] for row in pairs]))
    lower, upper = [float(value) for value in np.quantile(draws, [.025, .975], method='linear')]
    failures = sum(bool(row['failure_reasons']) for row in pairs)
    return dict(estimate=estimate, confidence_interval=[lower, upper], seed_clusters=len(clusters),
                denominator=len(pairs), failed_pairs=failures, pairs=pairs,
                established=estimate >= .1 and lower > 0 and failures == 0,
                failure_rule='Any missing/failed registered compatible observation assigns reduction -1 '
                             'for that entire instance; no denominator deletion or favourable baseline selection.')
