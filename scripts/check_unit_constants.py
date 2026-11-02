"""Author-time dimensional inventory; never imports or changes numerical modules."""

import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/units/float-constants.json"


def collect(root):
    modules, constants = [], {}
    for path in sorted((root / "data-pipeline").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        modules.append(relative)
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or type(node.value) is not float:
                continue
            owner = node
            while not isinstance(owner, ast.stmt):
                owner = parents[owner]
            context = ast.dump(owner, include_attributes=False)
            key = f"{relative}:{node.lineno}:{node.col_offset}"
            constants[key] = dict(value=repr(node.value),
                                  context_sha256=hashlib.sha256(context.encode()).hexdigest(),
                                  expression=source.splitlines()[node.lineno - 1].strip())
    return modules, constants


def findings(root, baseline):
    modules, actual = collect(root)
    errors = []
    if baseline.get("modules") != modules:
        errors.append("Owned module discovery changed: review added, removed or renamed Python modules")
    declared = baseline.get("constants", {})
    for key in sorted(set(actual) | set(declared)):
        if key not in declared:
            errors.append(f"{key}: new unreviewed float literal")
            continue
        if key not in actual:
            errors.append(f"{key}: stale inventory entry")
            continue
        row = declared[key]
        for field, value in actual[key].items():
            if row.get(field) != value:
                errors.append(f"{key}: float value or source context changed ({field})")
        for field in ("quantity", "unit", "rationale"):
            text = row.get(field)
            if not isinstance(text, str) or not text.strip() or "TODO" in text:
                errors.append(f"{key}: missing reviewed {field}")
        if isinstance(row.get("rationale"), str) and len(row["rationale"].split()) < 5:
            errors.append(f"{key}: rationale must explain this quantity and its dimensional role")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    errors = findings(args.root.resolve(), baseline)
    if errors:
        print("Unit inventory refused:\n" + "\n".join(errors))
        return 1
    print(f"Unit inventory: {len(baseline['constants'])} float occurrences in "
          f"{len(baseline['modules'])} owned modules; every quantity/unit/context declared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
