"""Run the separately preregistered directional coupled-peak study."""

import os

for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '1'
os.environ['OSQP_ALGEBRA_BACKEND'] = 'builtin'

if __name__ == '__main__':
    import argparse
    from pathlib import Path
    from pipeline.coupled_campaign import run_campaign

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--split', choices=['development', 'heldout', 'robustness'])
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--validate-output', action='store_true')
    action.add_argument('--check-freeze', action='store_true')
    args = parser.parse_args()
    if args.check_freeze:
        import json
        from pipeline.coupled_campaign import PROTOCOL, verify_freeze
        print(verify_freeze(json.loads(PROTOCOL.read_text(encoding='utf-8')), args.split or 'development'))
    elif args.validate_output:
        if args.output is None:
            parser.error('validation requires --output')
        from pipeline.coupled_export import validate_output
        print(validate_output(args.output))
    else:
        if args.split is None or args.output is None:
            parser.error('run requires --split and --output')
        result = run_campaign(args.output, args.split)
        print(result['counts'], result['primary'])
