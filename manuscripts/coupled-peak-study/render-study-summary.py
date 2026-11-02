"""Render complete, independently reviewed coupled evidence without new inference.

Only stdlib imports occur before the complete-split and review gates. Numerical
libraries are used for drawing after every timed split and its review finish.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

SPLITS = {'development': 48, 'heldout': 144, 'robustness': 18}
STATES = {'accepted', 'incompatible', 'oracle-failed', 'accuracy-rejected', 'failed', 'timeout', 'resource-limit'}


def digest(document):
    encoded = json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def compatible_methods(cell, protocol):
    compatible = set()
    for name, config in protocol['methods'].items():
        backend = config['backend']
        if backend not in ('native', 'epigraph', 'row-split-gsp', 'epigraph-daqp', 'epigraph-daqp-prox'):
            raise ValueError('Unknown registered backend in summary input')
        if backend == 'row-split-gsp' and cell['quadratic'] != 0:
            continue
        if backend == 'epigraph-daqp' and (cell['curvature'] != 'positive-definite' or cell['quadratic'] <= 0):
            continue
        if (backend == 'epigraph-daqp-prox' and config['settings'].get('lp_mode') == 'model'
                and not (cell['curvature'] == 'zero-hessian' and cell['quadratic'] == 0)):
            continue
        compatible.add(name)
    return compatible


def load_complete(studies, review_path, registration_path):
    paths = {split: studies/f'coupled-{split}-v1' for split in SPLITS}
    required = [directory/name for directory in paths.values()
                for name in ('campaign.json', 'validation.json', 'protocol.json')]
    if not all(path.is_file() for path in required):
        raise ValueError('All three complete splits are required before reading study outcomes')
    if not review_path.is_file() or not registration_path.is_file():
        raise ValueError('Independent final evidence acceptance and registration are required')
    review, registration = read(review_path), read(registration_path)
    if (review.get('decision') != 'ACCEPT_EVIDENCE'
            or review.get('protocol_sha256') != registration['protocol_sha256']):
        raise ValueError('Independent evidence review does not accept this registration')
    documents = {}
    source_commit = None
    for split, directory in paths.items():
        campaign, validation, protocol = [read(directory/name)
                                          for name in ('campaign.json', 'validation.json', 'protocol.json')]
        if (campaign['split'] != split or digest(protocol) != registration['protocol_sha256']
                or campaign['source_sha256'] != registration['source_sha256']
                or protocol['source_sha256'] != registration['source_sha256']
                or validation['state'] != 'validated'
                or validation['primary'] != campaign['primary']):
            raise ValueError(f'{split}: protocol/source/validation identity differs')
        if (review['campaign_sha256'][split] != digest(campaign)
                or review['validation_sha256'][split] != digest(validation)
                or review['raw_sha256'][split] != campaign['raw_sha256']):
            raise ValueError(f'{split}: evidence differs from the independent accepted receipt')
        if (len(campaign['inventory']) != SPLITS[split]
                or len({row['id'] for row in campaign['inventory']}) != SPLITS[split]
                or validation['observations'] != SPLITS[split]*37
                or any(type(value) is not int or value < 0 for value in campaign['counts'].values())
                or set(campaign['counts'])-STATES
                or sum(campaign['counts'].values()) != SPLITS[split]*27):
            raise ValueError(f'{split}: incomplete or invalid full observation denominator')
        declared_incompatible = sum(len(protocol['methods'])-len(compatible_methods(cell, protocol))
                                    for cell in campaign['inventory'])*3
        if campaign['counts'].get('incompatible', 0) != declared_incompatible:
            raise ValueError(f'{split}: incompatible count differs from registered semantics')
        current = campaign['environment']['registration']
        if (current['protocol_sha256'] != registration['protocol_sha256']
                or current['review_sha256'] != registration['review_sha256']):
            raise ValueError(f'{split}: runtime registration differs')
        if source_commit is not None and current['commit'] != source_commit:
            raise ValueError('Timed splits must share the same recorded source commit')
        source_commit = current['commit']
        documents[split] = campaign
    primary = documents['heldout']['primary']
    pairs = primary['pairs']
    inventory = documents['heldout']['inventory']
    if (primary['denominator'] != 144 or primary['seed_clusters'] != 6 or len(pairs) != 144
            or len({row['id'] for row in pairs}) != 144
            or {row['id'] for row in pairs} != {row['id'] for row in inventory}):
        raise ValueError('The primary figure requires all 144 registered paired scores')
    by_id = {row['id']: row for row in inventory}
    seeds = sorted({row['seed'] for row in inventory})
    if (len(seeds) != 6 or any(sum(row['seed'] == seed for row in inventory) != 24 for seed in seeds)
            or any(row['seed'] != by_id[row['id']]['seed'] for row in pairs)):
        raise ValueError('Primary seed clusters differ from the complete inventory')
    lower, upper = primary['confidence_interval']
    if (not all(type(value) in (int, float) and math.isfinite(value)
                for value in [primary['estimate'], lower, upper]+[row['reduction'] for row in pairs])
            or lower > upper
            or primary['estimate'] != statistics.median(row['reduction'] for row in pairs)):
        raise ValueError('Invalid primary estimate, interval or paired score')
    for row in pairs:
        reasons = row['failure_reasons']
        medians = row['median_seconds']
        expected = compatible_methods(by_id[row['id']], protocol)
        if (not isinstance(reasons, list) or any(not isinstance(reason, str) or not reason for reason in reasons)
                or not isinstance(medians, dict) or set(medians)-expected
                or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
                       for value in medians.values())):
            raise ValueError('Invalid paired timing or failure metadata')
        if reasons:
            if row['fastest_baseline'] is not None:
                raise ValueError('Failed pairs must retain no selected successful comparator')
        else:
            if set(medians) != expected or 'native' not in medians or len(medians) < 2:
                raise ValueError('Successful pairs require every compatible method median')
            comparator = min((name for name in medians if name != 'native'), key=lambda name: (medians[name], name))
            recomputed = 1-medians['native']/medians[comparator]
            if (row['fastest_baseline'] != comparator or row['reduction'] >= 1
                    or row['reduction'] != recomputed):
                raise ValueError('Paired score/comparator differs from the registered median ratio')
    minimum, maximum = min(row['reduction'] for row in pairs), max(row['reduction'] for row in pairs)
    if ((lower < minimum and not math.isclose(lower, minimum, rel_tol=1e-12, abs_tol=1e-12))
            or (upper > maximum and not math.isclose(upper, maximum, rel_tol=1e-12, abs_tol=1e-12))):
        raise ValueError('Cluster bootstrap interval lies outside the full observed score range')
    failures = sum(bool(row['failure_reasons']) for row in pairs)
    failure_observations = sum(value for state, value in documents['heldout']['counts'].items()
                               if state not in ('accepted', 'incompatible'))
    if not failures <= failure_observations <= failures*27:
        raise ValueError('Measured failure-state counts disagree with primary failed pairs')
    if (type(primary['failed_pairs']) is not int or failures != primary['failed_pairs']
            or any(row['failure_reasons'] and row['reduction'] != -1 for row in pairs)
            or type(primary['established']) is not bool
            or primary['established'] != (primary['estimate'] >= .1 and lower > 0 and failures == 0)):
        raise ValueError('Registered failure treatment or qualification differs')
    return documents, registration, review


def write_figures(documents, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none'})
    order = ['accepted', 'incompatible', 'oracle-failed', 'accuracy-rejected',
             'failed', 'timeout', 'resource-limit']
    states = sorted({state for doc in documents.values() for state in doc['counts']},
                    key=lambda state: (order.index(state) if state in order else len(order), state))
    colors = {'accepted': '#2877a6', 'incompatible': '#b2b7bd', 'oracle-failed': '#c28a16',
              'accuracy-rejected': '#aa3377', 'failed': '#bb3322', 'timeout': '#7a4c9f',
              'resource-limit': '#513e25'}
    fig, ax = plt.subplots(figsize=(11, 4.6))
    labels, left = list(SPLITS), [0, 0, 0]
    for state in states:
        values = [documents[split]['counts'].get(state, 0) for split in labels]
        ax.barh(labels, values, left=left, label=state, color=colors.get(state, '#555555'))
        left = [old+value for old, value in zip(left, values)]
    for index, total in enumerate(left):
        ax.annotate(str(total), (total, index), xytext=(5, 0), textcoords='offset points', va='center')
    ax.set_xlim(0, max(left)*1.13)
    ax.set_xlabel('Measured method observations (three repetitions; all declared cells)')
    ax.set_title('Complete registered observations: failures and incompatibilities retained')
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.20), ncol=3, fontsize=9)
    fig.text(.5, .025, 'Warmups and oracle rows remain in the raw journals. Synthetic forecast problems.',
             ha='center', fontsize=9)
    fig.subplots_adjust(left=.13, right=.98, top=.88, bottom=.29)
    for suffix in ('png', 'svg'):
        fig.savefig(output/f'observation-states.{suffix}', dpi=180, bbox_inches='tight')
    plt.close(fig)

    primary = documents['heldout']['primary']
    pairs = primary['pairs']
    seeds = sorted({row['seed'] for row in pairs})
    fig, ax = plt.subplots(figsize=(11, 5.8))
    for index, seed in enumerate(seeds):
        rows = sorted((row for row in pairs if row['seed'] == seed), key=lambda row: row['id'])
        for rank, row in enumerate(rows):
            y = index+(rank/(len(rows)-1)-.5)*.5
            failed = bool(row['failure_reasons'])
            ax.scatter(100*row['reduction'], y, color='#bb3322' if failed else '#2877a6',
                       marker='x' if failed else 'o', s=23 if failed else 13, alpha=.8)
    lower, upper = [100*value for value in primary['confidence_interval']]
    estimate = 100*primary['estimate']
    summary_y = len(seeds)+.15
    ax.hlines(summary_y, lower, upper, color='#111111', linewidth=2)
    ax.scatter([estimate], [summary_y], marker='D', color='#111111', s=37, zorder=4)
    ax.axvline(0, color='#888888', linewidth=.8)
    ax.axvline(10, color='#31598a', linestyle='--', linewidth=1, label='Registered 10% threshold')
    values = [100*row['reduction'] for row in pairs]+[lower, upper, 0, 10]
    span = max(max(values)-min(values), 10)
    ax.set_xlim(min(values)-.05*span, max(values)+.05*span)
    ax.set_ylim(-.6, summary_y+.65)
    ax.set_yticks(list(range(len(seeds)))+[summary_y], [str(seed) for seed in seeds]+['Overall median / 95% CI'])
    ax.set_xlabel('Registered paired reduction score (%)')
    conclusion = 'ESTABLISHED' if primary['established'] else 'NOT ESTABLISHED'
    fig.suptitle(f'Full primary: 144 instances, six seed clusters; registered criterion {conclusion}', y=.985, fontsize=11)
    fig.text(.21, .94, f'Median {estimate:.3f}%; 95% CI [{lower:.3f}%, {upper:.3f}%]\n'
            f'Failed pairs {primary["failed_pairs"]}/144 (red crosses retain prescribed -100% score)',
            va='top', fontsize=9)
    fig.legend(loc='upper right', bbox_to_anchor=(.98, .945), fontsize=9)
    fig.text(.5, .015, 'Complete 32-forecast operations on synthetic cases; one nonreserved host. '
             'No failed pair or baseline is deleted.', ha='center', fontsize=8.5)
    fig.subplots_adjust(left=.21, right=.98, top=.84, bottom=.15)
    for suffix in ('png', 'svg'):
        fig.savefig(output/f'primary-full-population.{suffix}', dpi=180, bbox_inches='tight')
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--studies', required=True, type=Path)
    parser.add_argument('--review', required=True, type=Path)
    parser.add_argument('--registration', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    documents, registration, review = load_complete(args.studies, args.review, args.registration)
    if args.check_only:
        print('Complete registered split and independent-evidence gates: PASS')
        return
    if args.output is None:
        parser.error('--output is required for rendering')
    args.output.mkdir(parents=True, exist_ok=False)
    facts = {'protocol_sha256': registration['protocol_sha256'], 'evidence_review_sha256': digest(review),
             'source_commit': documents['heldout']['environment']['registration']['commit'],
             'counts': {split: doc['counts'] for split, doc in documents.items()},
             'primary': documents['heldout']['primary'],
             'scope': 'Synthetic forecast problems; measured complete operations on one nonreserved host. '
                      'Statistical outcome is the frozen primary analysis; app release and deployment are separate.'}
    (args.output/'summary.json').write_text(json.dumps(facts, indent=2, allow_nan=False)+'\n',
                                         encoding='utf-8', newline='\n')
    write_figures(documents, args.output)
    files = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
             for path in args.output.iterdir() if path.is_file()}
    (args.output/'SHA256SUMS.json').write_text(json.dumps(files, indent=2)+'\n',
                                            encoding='utf-8', newline='\n')
    print(f'Rendered complete reviewed evidence to {args.output}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        print(f'Study summary refused: {error}', file=sys.stderr)
        raise SystemExit(2)
