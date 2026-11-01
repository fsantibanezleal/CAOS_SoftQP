"""Run frozen offline scientific experiments in a fresh explicit output directory."""

import os

# Set before importing any numerical package, including in spawned Windows workers.
for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"

if __name__ == "__main__":
    import argparse
    from pathlib import Path
    from pipeline.softqp_campaign import run_campaign
    from pipeline.softqp_stream import export_stream

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["campaign", "stream"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", action="append", choices=["development", "heldout", "robustness"])
    args = parser.parse_args()
    if args.kind == "campaign":
        result = run_campaign(args.output, tuple(args.split or ["development", "heldout", "robustness"]))
        print(result["counts"], result["primary_endpoint"])
    else:
        print(export_stream(args.output))
