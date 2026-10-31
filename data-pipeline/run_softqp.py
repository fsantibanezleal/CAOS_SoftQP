"""Bake SoftQP development results into an explicitly selected output root."""
import argparse
from pathlib import Path
from pipeline.softqp_run import bake

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cases',nargs='*')
    args=p.parse_args()
    result=bake(args.output,args.cases)
    raise SystemExit(1 if any(c['failed'] for c in result['cases']) else 0)
