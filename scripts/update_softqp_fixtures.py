"""Regenerate the analytic provider and its readiness without rerunning a solver."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline"))


def main():
    from pipeline.core.readiness import compute, write
    from pipeline.softqp_run import validate_document, verify_inventory
    from pipeline.core.manifest import export_manifests

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, required=True)
    args = parser.parse_args()
    fixture = args.fixture_root.resolve()
    source = ROOT / "data/derived/softqp"
    index = json.loads((source / "index.json").read_text(encoding="utf-8"))
    verify_inventory(source, index)
    target = fixture / "data/derived/softqp"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "C01.json", target / "C01.json")
    index["cases"] = [r for r in index["cases"] if r["case_id"] == "C01"]
    index["default_case"] = "C01"
    validate_document(index, "softqp-index")
    (target / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    export_manifests(fixture / "data/derived")
    lines = []
    inside = False
    for line in (ROOT / "docs/contracts/catalog.md").read_text(encoding="utf-8").splitlines():
        if line == "## Contracts":
            inside = True
            lines.append(line)
            continue
        if inside and line.startswith("## "):
            break
        if inside and line.startswith("|"):
            if not line.startswith("| id |") and not line.startswith("|---"):
                cells = line.strip("|").split("|")
                if cells[0].strip() not in ("api", "readiness"):
                    cells[-1] = " active "
                line = "|" + "|".join(cells) + "|"
            lines.append(line)
    catalog = fixture / "catalog.md"
    catalog.write_text(
        "# Fixture catalog\n\nProvider states for artifact substitution checks.\n\n"
        + "\n".join(lines)
        + "\n",
        encoding="utf-8",
    )
    write(
        fixture / "data/derived",
        compute(
            repo_root=ROOT,
            derived_root=fixture / "data/derived",
            models_dir=fixture / "models",
            catalog_path=catalog,
        ),
    )
    print("SoftQP analytic provider and readiness regenerated")


if __name__ == "__main__":
    main()
