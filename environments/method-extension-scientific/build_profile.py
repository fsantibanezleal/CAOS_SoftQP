"""Build a candidate profile from exact public wheels and an owned installation."""
import importlib.metadata as metadata
import argparse
from pathlib import Path
import json
import runpy
import shutil
import subprocess
import sys
import secrets
from zipfile import ZipFile

from custody import encode, inventory, require, sha

BASELINE_SHA = "a4bfa531f8af72412cc6bfbaacf57e0cd3d9545a481a780a5caba96448629f3d"
ADDITIONS = {
    "jsonschema": "jsonschema/__init__.py",
    "jsonschema-specifications": "jsonschema_specifications/__init__.py",
    "referencing": "referencing/__init__.py",
    "rpds-py": "rpds/__init__.py",
}


def _build(product, scratch, runtime, baseline, test_tools, destination, *, source_commit=None):
    baseline_profile = (baseline / "provenance.json").read_bytes()
    require(sha(baseline_profile) == BASELINE_SHA, "baseline profile SHA256 differs")
    profile = json.loads(baseline_profile)
    scratch = scratch.resolve()
    runtime = runtime.resolve(strict=True)
    base = Path(sys.base_prefix).resolve(strict=True)
    site = runtime / "Lib" / "site-packages"
    source = scratch / "product-snapshot"
    tools = scratch / "test-only"
    committed = None
    if source_commit is None:
        source.mkdir()
        for rel in ("data-pipeline", "docs/contracts/schemas", "docs/contracts/examples",
                    "tests/fixtures/learned-contracts"):
            shutil.copytree(product / rel, source / rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for test in ("test_learned_contracts.py", "test_stream_inputs.py", "test_phase_inputs.py", "test_native_labels.py", "test_native_runtime.py", "test_heldout_inputs.py", "runtime_config.py", "test_candidate_runtime.py"):
            shutil.copyfile(product / "tests" / test, source / "tests" / test)
    else:
        from committed_source import snapshot

        committed = snapshot(product, source_commit, source)
    shutil.copytree(test_tools, tools, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(baseline, destination)
    lock = (scratch / "requirements.lock").read_bytes()
    require(lock.startswith((baseline / "requirements.lock").read_bytes()), "inherited lock changed")
    (destination / "requirements.lock").write_bytes(lock)
    additions = json.loads((scratch / "additions.json").read_bytes())
    checker = runpy.run_path(str(baseline / "check_lock.py"))
    normalize = checker["_distribution_name"]
    dists = list(metadata.distributions(path=[str(site)]))
    installed = {normalize(d.metadata["Name"]): d for d in dists}
    inherited = {normalize(d["name"]): d["version"] for d in profile["distributions"]}
    require(len(dists) == len(installed) == 49 and installed.keys() == inherited.keys() | ADDITIONS.keys(),
            "unexpected distribution alphabet")
    require(all(installed[name].version == version for name, version in inherited.items()),
            "inherited version changed")
    owners = {}
    for name, rel in ADDITIONS.items():
        approved = additions[name]
        dist = installed[name]
        require(dist.version == approved["version"], "wrong added distribution version")
        wheel = scratch / "wheels" / approved["filename"]
        require(sha(wheel.read_bytes()) == approved["sha256"], "added wheel bytes differ")
        license_rows = []
        with ZipFile(wheel) as archive:
            for member in sorted(dist.files, key=str):
                if not Path(str(member)).name.lower().startswith(("license", "copying", "notice")):
                    continue
                path = Path(dist.locate_file(member)).resolve(strict=True)
                data = path.read_bytes()
                require(data == archive.read(str(member)), "license differs from actual wheel")
                output = f"licenses/{name}/{len(license_rows):03}-{path.name}"
                (destination / output).parent.mkdir(parents=True, exist_ok=True)
                (destination / output).write_bytes(data)
                license_rows.append(dict(profile_relative_path=output,
                    installed_relative_path=path.relative_to(runtime).as_posix(), sha256=sha(data), bytes=len(data)))
        require(license_rows, f"missing wheel notices: {name}")
        entries = checker["source_manifest"](dist, runtime)
        extra = {}
        for key in ("metadata", "wheel"):
            member, = [f for f in dist.files if str(f).endswith(".dist-info/" + key.upper())]
            path = Path(dist.locate_file(member))
            extra[key + "_relative_path"] = path.relative_to(runtime).as_posix()
            extra[key + "_sha256"] = sha(path.read_bytes())
        profile["distributions"].append(dict(name=dist.metadata["Name"], version=dist.version,
            artifact_url=approved["url"], artifact_sha256=approved["sha256"],
            source_file_count=len(entries), source_manifest_sha256=sha(encode(entries)),
            licenses=license_rows, license_expression=dist.metadata.get("License-Expression"),
            declared_license=dist.metadata.get("License"), **extra))
        path = site / rel
        profile["imported_origins"][name.replace("-", "_") if name != "rpds-py" else "rpds"] = dict(
            relative_path=path.relative_to(runtime).as_posix(), sha256=sha(path.read_bytes()))
    for name, dist in installed.items():
        for member in dist.files:
            path = Path(dist.locate_file(member)).resolve(strict=True)
            if path.is_relative_to(runtime) and path.is_file() and path.suffix.lower() in (".py", ".pyd", ".dll"):
                rel = path.relative_to(runtime).as_posix()
                require(rel not in owners, "multiple distributions own identical source origin")
                owners[rel] = name
    manifest = dict(
        runtime=inventory(runtime, "runtime"), base=inventory(base, "base"),
        source=inventory(source, "source"), tools=inventory(tools, "tools"),
        module_owners=owners,
    )
    manifest_bytes = encode(manifest)
    (destination / "custody.json").write_bytes(manifest_bytes)
    shutil.copyfile(baseline / "verify.py", destination / "sdk-verify.py")
    guard_root = Path(__file__).parent if committed is None else product / "environments/method-extension-scientific"
    if committed is not None:
        require(Path(__file__).read_bytes() == (guard_root / "build_profile.py").read_bytes(),
                "profile factory differs from selected committed factory")
        (destination / "committed-source.json").write_bytes(encode(committed))
    probe = guard_root / "verify.py"
    controls = probe.with_name("controls.py")
    custody = guard_root / "custody.py"
    learning = probe.with_name("learning_runtime.py")
    native = probe.with_name("native_runtime.py")
    heldout = probe.with_name("heldout_runtime.py")
    evaluation = probe.with_name("evaluation_runtime.py")
    components = (probe, custody, controls, learning, native, heldout, evaluation)
    if committed is not None:
        components += (guard_root / "committed_source.py",)
    for path in components:
        shutil.copyfile(path, destination / path.name)
    profile["scientific_runtime"] = dict(format="softqp.product-runtime-custody/v1",
        manifest_sha256=sha(manifest_bytes), source_manifest_sha256=sha(encode(manifest["source"])),
        source_head=subprocess.check_output(["git", "--no-replace-objects", "-C", str(product), "rev-parse", "HEAD"]).decode().strip(),
        source_kind="qualification-snapshot-of-product-worktree" if committed is None else "committed-product-checkout",
        python_sha256=manifest["runtime"]["Scripts/python.exe"][1],
        base_python_sha256=manifest["base"]["python.exe"][1],
        python_dll_sha256=manifest["base"]["python312.dll"][1],
        verifier_sha256=sha(probe.read_bytes()), custody_module_sha256=sha(custody.read_bytes()),
        learning_runtime_sha256=sha(learning.read_bytes()), native_runtime_sha256=sha(native.read_bytes()), heldout_runtime_sha256=sha(heldout.read_bytes()),
        evaluation_runtime_sha256=sha(evaluation.read_bytes()),
        controls_sha256=sha(controls.read_bytes()), sdk_verify_sha256=sha((baseline / "verify.py").read_bytes()),
        engine_checker_sha256=sha((baseline / "check_lock.py").read_bytes()))
    if committed is not None:
        from committed_source import verify

        verify(product, source_commit, manifest["source"], committed)
        profile["scientific_runtime"].update(
            committed_source_sha256=sha((guard_root / "committed_source.py").read_bytes()),
            committed_git_manifest_sha256=sha(encode(committed)),
        )
    profile["parent_profile_sha256"] = BASELINE_SHA
    profile["requirements_sha256"] = sha(lock)
    profile["status"] = ("SCIENTIFIC_PRODUCT_RUNTIME_QUALIFICATION_CANDIDATE" if committed is None
                         else "SCIENTIFIC_PRODUCT_RUNTIME_COMMITTED_CANDIDATE")
    (destination / "provenance.json").write_bytes(encode(profile))
    return {"profile_sha256": sha(encode(profile)), "requirements_sha256": sha(lock),
            "counts": {key: len(value) for key, value in manifest.items()}}


def build(product, scratch, runtime, baseline, test_tools, destination, *, source_commit=None):
    if source_commit is None:
        return _build(product, scratch, runtime, baseline, test_tools, destination)
    require(product.is_absolute() and product.resolve(strict=True).parts == product.parts,
            "committed profile requires an exact absolute product checkout")
    require(destination.is_absolute() and destination.resolve().parts == destination.parts
            and scratch.is_absolute() and scratch.resolve(strict=True).parts == scratch.parts,
            "committed profile requires exact absolute output and scratch paths")
    parent = destination.parent.resolve(strict=True)
    require(not any((folder / ".git").exists() for folder in (parent, *parent.parents,
                    scratch, *scratch.parents)), "committed profile output or scratch is inside a checkout")
    require(not destination.exists(), "committed profile destination already exists")
    for protected in (product, runtime.resolve(strict=True), baseline.resolve(strict=True), test_tools.resolve(strict=True)):
        require(not destination.is_relative_to(protected) and not protected.is_relative_to(destination),
                "committed profile destination overlaps an input")
        require(not scratch.is_relative_to(protected) and not protected.is_relative_to(scratch),
                "committed profile scratch overlaps an input")
    require(not destination.is_relative_to(scratch) and not scratch.is_relative_to(destination),
            "committed profile output and scratch overlap")
    staged = parent / (destination.name + ".pending-" + secrets.token_hex(12))
    # The builder's copytree creates this exclusive stage. A failed stage remains
    # diagnostic evidence; only a complete verified profile gains the final name.
    summary = _build(product, scratch, runtime, baseline, test_tools, staged, source_commit=source_commit)
    from committed_source import admitted_checkout

    admitted_checkout(product, source_commit)
    staged.rename(destination)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("product", "scratch", "runtime", "baseline", "test_tools", "destination"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--source-commit")
    args = parser.parse_args()
    if args.source_commit is None:
        for name in ("product", "scratch", "runtime", "baseline", "test_tools", "destination"):
            setattr(args, name, getattr(args, name).resolve())
    result = build(args.product, args.scratch, args.runtime, args.baseline, args.test_tools, args.destination,
                   source_commit=args.source_commit)
    print(json.dumps(result, sort_keys=True))
