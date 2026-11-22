"""Build a candidate profile from exact public wheels and an owned installation."""
import importlib.metadata as metadata
from pathlib import Path
import json
import runpy
import shutil
import subprocess
import sys
from zipfile import ZipFile

from custody import encode, inventory, require, sha

BASELINE_SHA = "a4bfa531f8af72412cc6bfbaacf57e0cd3d9545a481a780a5caba96448629f3d"
ADDITIONS = {
    "jsonschema": "jsonschema/__init__.py",
    "jsonschema-specifications": "jsonschema_specifications/__init__.py",
    "referencing": "referencing/__init__.py",
    "rpds-py": "rpds/__init__.py",
}


def build(product, scratch, runtime, baseline, test_tools, destination):
    baseline_profile = (baseline / "provenance.json").read_bytes()
    require(sha(baseline_profile) == BASELINE_SHA, "baseline profile SHA256 differs")
    profile = json.loads(baseline_profile)
    scratch = scratch.resolve()
    runtime = runtime.resolve(strict=True)
    base = Path(sys.base_prefix).resolve(strict=True)
    site = runtime / "Lib" / "site-packages"
    source = scratch / "product-snapshot"
    tools = scratch / "test-only"
    source.mkdir()
    for rel in ("data-pipeline", "docs/contracts/schemas", "docs/contracts/examples",
                "tests/fixtures/learned-contracts"):
        shutil.copytree(product / rel, source / rel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for test in ("test_learned_contracts.py", "test_stream_inputs.py", "test_phase_inputs.py"):
        shutil.copyfile(product / "tests" / test, source / "tests" / test)
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
    probe = Path(__file__).with_name("verify.py")
    controls = probe.with_name("controls.py")
    custody = Path(__file__).with_name("custody.py")
    learning = probe.with_name("learning_runtime.py")
    for path in (probe, custody, controls, learning):
        shutil.copyfile(path, destination / path.name)
    profile["scientific_runtime"] = dict(format="softqp.product-runtime-custody/v1",
        manifest_sha256=sha(manifest_bytes), source_manifest_sha256=sha(encode(manifest["source"])),
        source_head=subprocess.check_output(["git", "-C", str(product), "rev-parse", "HEAD"]).decode().strip(),
        source_kind="qualification-snapshot-of-product-worktree",
        python_sha256=manifest["runtime"]["Scripts/python.exe"][1],
        base_python_sha256=manifest["base"]["python.exe"][1],
        python_dll_sha256=manifest["base"]["python312.dll"][1],
        verifier_sha256=sha(probe.read_bytes()), custody_module_sha256=sha(custody.read_bytes()),
        learning_runtime_sha256=sha(learning.read_bytes()),
        controls_sha256=sha(controls.read_bytes()), sdk_verify_sha256=sha((baseline / "verify.py").read_bytes()),
        engine_checker_sha256=sha((baseline / "check_lock.py").read_bytes()))
    profile["parent_profile_sha256"] = BASELINE_SHA
    profile["requirements_sha256"] = sha(lock)
    profile["status"] = "SCIENTIFIC_PRODUCT_RUNTIME_QUALIFICATION_CANDIDATE"
    (destination / "provenance.json").write_bytes(encode(profile))
    print(json.dumps({"profile_sha256": sha(encode(profile)), "requirements_sha256": sha(lock),
                      "counts": {key: len(value) for key, value in manifest.items()}}, sort_keys=True))


if __name__ == "__main__":
    build(*(Path(arg).resolve() for arg in sys.argv[1:]))
