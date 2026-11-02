"""Shared registered inventory and compatibility policy, independent of raw flags."""

import itertools


def inventory(protocol, splits):
    cells = []
    if len(splits) != len(set(splits)) or any(split not in ('development', 'heldout', 'robustness') for split in splits):
        raise ValueError('unknown or duplicate split')
    config = protocol['generation']
    for split in splits:
        count = 0
        for seed in protocol['seeds'][split]:
            if split == 'robustness':
                grid = config['robustness_cells']
            else:
                generic, thermal = config['sparse'], config['thermal']
                grid = [dict(family='sparse', n=n, group_size=generic['group_size'],
                             condition=condition, curvature=curvature)
                        for n, condition, curvature in itertools.product(generic['n'], generic['condition'], generic['curvature'])]
                grid += [dict(family='thermal', horizon=horizon, zones=thermal['zones'], curvature=curvature)
                         for horizon, curvature in itertools.product(thermal['horizon_hours'], thermal['curvature'])]
            for base, quadratic in itertools.product(grid, config['sparse']['quadratic']):
                cells.append(dict(base, id=f'{split}-{count:04d}', split=split,
                                  seed=seed, quadratic=quadratic))
                count += 1
    return cells


def incompatible(spec, name, protocol):
    config = protocol['methods'][name]
    if config['backend'] == 'row-split-gsp' and spec['quadratic'] != 0:
        return 'Published native grouped NORMINF implements linear peaks only.'
    if config['backend'] == 'epigraph-daqp' and (spec['quadratic'] == 0 or spec['curvature'] != 'positive-definite'):
        return 'Direct non-proximal DAQP requires a positive-definite augmented epigraph Hessian.'
    if config['settings'].get('lp_mode') == 'model' and (spec['curvature'] != 'zero-hessian' or spec['quadratic'] != 0):
        return 'Persistent zero-Hessian Model policy is registered only for LP cells.'
    return None
