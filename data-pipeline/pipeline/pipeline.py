"""Explicit scientific bake and readiness CLI, with no model-training placeholder."""

from pathlib import Path
import argparse

REPO_ROOT = Path(__file__).resolve().parents[2]
REPO = REPO_ROOT
DERIVED = REPO_ROOT / "data/derived"
MANIFESTS = DERIVED / "manifests"
MODELS = REPO_ROOT / "models"
STAGES = ("validate", "assemble", "solve", "evaluate", "export")


def run_all(*, output_root):
    from .softqp_run import bake
    from .core.manifest import export_manifests
    from .core.readiness import compute, write

    target = Path(output_root)
    inventory = bake(target / "softqp")
    export_manifests(target)
    write(target, compute(repo_root=REPO, derived_root=target, models_dir=MODELS))
    if any(c["failed"] for c in inventory["cases"]):
        raise RuntimeError("scientific bake contains failed method cells")
    return inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", nargs="?", default="all", choices=["all", "readiness"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.case == "readiness":
        from .core.readiness import compute, write

        target = args.output or DERIVED
        write(target, compute(repo_root=REPO, derived_root=target, models_dir=MODELS))
        print("readiness ->", target / "readiness.json")
    else:
        if args.output is None:
            parser.error(
                "--output is required for a scientific bake, including an intentional canonical bake"
            )
        run_all(output_root=args.output)


if __name__ == "__main__":
    main()
